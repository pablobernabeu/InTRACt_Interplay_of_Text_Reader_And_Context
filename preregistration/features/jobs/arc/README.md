# ARC jobs for the English dry run

These jobs run the feature pipeline on ARC, Oxford's Slurm cluster, on the public stand-in: SimpleStories
stories matched to the English catalogue's page and word counts (`standin/`). The dry run measures what each
stage costs at the catalogue's scale. The protocol commits that no feature is computed on the story texts
before in-principle acceptance. No job here reads them, and the documents stage puts every input behind the
catalogue lock (`src/intract_features/lock.py`).

## Layout on ARC

| Folder | Holds |
|---|---|
| `$FEAT = /data/educ-intract/educ1242/intract_features` | everything below |
| `$FEAT/code` | this `features` folder, synced from the repository (`pyproject.toml` at its top) |
| `$FEAT/story_texts/data` | `manifest.json` and `extraction_record.json` only: the checksums the catalogue lock refuses |
| `$FEAT/inputs/en-us/structure.tsv` | the structure table of the English catalogue (identifiers and counts, no text) |
| `$FEAT/envs` | the four environments (`envs/README.md`) and the bootstrap uv |
| `$FEAT/models` | safetensors converted from pickled weights, and `conversions.json` |
| `$FEAT/resources` | MEmoLon's English table, the SimpleStories shards, FLORES-200 |
| `$FEAT/src`, `$FEAT/opt` | the CorPipe, MetricX and eSpeak NG checkouts; the eSpeak NG 1.52.0 build |
| `$FEAT/work/<run>` | each run's artefacts (`smoke`, `full`, `smoke_bf16`), with `_input`, `_runs`, `_probe` and `_summary` |
| `$FEAT/logs`, `$FEAT/tmp`, `$FEAT/records` | job logs, per-job temporary folders, run records |
| `$FEAT/jobs.csv` | the job ledger |

`env.sh` defines these folders. It reuses the pre-submission area's content-addressed caches, so nothing is
downloaded twice. These are the Hugging Face hub cache, the uv and pip caches, the Stanza 1.15.0 models (checked
against the frozen `resources.json`), the UDPipe 2 checkout at 223da86 and the extracted 2.17 model archive.
Every model is fetched at a full commit and never by branch name, so a shared `refs/main` never moves under
the earlier strands. Caches that are not content-addressed stay in `$FEAT/cache`.

## Prerequisites (by hand, before the first submission)

1. Sync this folder to `$FEAT/code` (for instance with `rsync -a --exclude __pycache__ --exclude '*.egg-info'`).
   From Windows, build the copy with `git -c core.autocrlf=false archive --prefix=code/ HEAD:preregistration/features`:
   with `core.autocrlf` on, `git archive` writes CRLF line ends, and bash then stops at `set -o pipefail`.
   When the code root has no `.git`, `env.sh` records a SHA-256 of its files as `INTRACT_CODE_COMMIT`, and
   every timing record carries it.
2. Copy `preregistration/story_texts/data/manifest.json` and `extraction_record.json` to
   `$FEAT/story_texts/data/`. They hold checksums only. The lock resolves them against the code's own `config/`
   (`../../story_texts/data/`) and refuses to run without either (`documents.toml`, `on_missing_manifest`), so
   `submit_chain.sh` checks for both before it submits anything.
3. Copy the structure table to `$FEAT/inputs/en-us/structure.tsv`. The scout's table of 2 November serves as it
   is: its eight columns are the builder's required ones, and `standin/catalogue_structure.py` reads the ninth,
   `combination`, as optional, giving each story id its own combination when it is absent. Writing the table again
   with `python -m standin.catalogue_structure <stories.csv.xz> structure.tsv --with-combination --authorisation
   "<lab-log entry>"` would let the three reading levels of a story share one synthetic key, which the timing run
   does not need. That would be a new structural pass over the catalogue file, so it is the PI's decision, and the
   command refuses to run without the authorisation.
4. Choose the GPU-hour cap for the budget guard.

## Running

```
cd /data/educ-intract/educ1242/intract_features/code/jobs/arc
bash submit_chain.sh --cap 25 --build --dry-run     # the plan, the budget check, nothing submitted
bash submit_chain.sh --cap 25 --build               # J0, then the smoke chain, then the full chain
```

Without `--build` the chain assumes the environments and models are in place; `--after JOBID` chains it to a
running build. `--runs smoke` submits the smoke chain alone, and `--bf16 none` leaves out the bf16 check. All
jobs use `--export=NONE`, `--account=educ-intract` and `--clusters=htc`; GPU jobs request `--partition=short
--gres=gpu:l40s:1` (`--gpu-partition medium` when a limit needs more than 12 hours). No job asks Slurm to send
mail. The default plan requests 18 L40S GPU-hours: 4 for the smoke GPU job, 12 for the full one and 2 for the
bf16 check.

### The chain

| Job | Template | Resources | Depends on |
|---|---|---|---|
| J0 build | `j0_build.sbatch` | CPU 8, 64 GB, 8 h | |
| J0 metricx | `j0_metricx.sbatch` | CPU 4, 32 GB, 2 h | J0 (nothing depends on it) |
| J1 inputs | `j1_standin.sbatch <run>` | CPU 2, 8 GB | J0, or the smoke run's J1, documents and GPU jobs |
| documents | `documents.sbatch` | array of 4 shards, CPU 1, 8 GB | J1 |
| GPU stages | `gpu_combined.sbatch <run>` (combined mode) | 1 L40S, 16 CPU, 120 GB, 4 h smoke, 12 h full | documents |
| features | `features_gramlex.sbatch`, `features_discourse.sbatch` | arrays of 4 shards | the GPU job |
| aggregate | `aggregate_timing.sbatch` | CPU 1, 4 GB | every job of the run (afterany) |
| bf16 check | `gpu_bf16.sbatch smoke` | 1 L40S, 8 CPU, 96 GB, 2 h | the smoke GPU job (nothing depends on it) |
| row check | `compare_runs.sbatch smoke full` | CPU 1, 8 GB | both runs (afterany; nothing depends on it) |

The full chain's J1 depends afterok on the smoke run's J1, documents and GPU jobs. It does not wait for the smoke
run's CPU feature stages, so the full GPU job joins the L40S queue as soon as the smoke GPU job has succeeded:
Slurm counts a job's age only from when its dependencies are met, and each pre-submission L40S job waited 29 to 30
hours. A job whose afterok dependency fails is cancelled (`--kill-on-invalid-dep=yes`) instead of waiting for
ever, as the pre-submission TU-6 and EM-6 did. Each run's aggregate then still reports what was measured.

**Combined mode** (the default) runs every GPU stage of a run in one L40S allocation. `gpu_combined.sbatch` runs
`sat`. It then starts `parse_stanza` (one process per shard, GPU hidden) and `seg_check` on the allocation's CPUs.
While they run, the GPU takes `parse_udpipe`, `encode_e5`, `encode_bgem3`, `surprisal_goldfish` and `qe_metricx`.
Once the Stanza parse is complete it runs `coref_corpipe`, and `surprisal_xglm` comes last. A failed stage does not
stop the stages that do not need its output. The job exits non-zero at the end, so nothing after it starts. The
full run is expected to take about 10.5 hours with the probes, and the smoke run about 2.5. The request is one
GPU's share of an L40S node, which has 64 cores, 503 GB and four GPUs (`sinfo`, 3 November 2026).

**Separate mode** (`--mode separate`) gives every stage its own job, one template each. CPU stages run as
arrays over the shards, and each GPU stage runs every shard in turn in one allocation. The time limits are in
`submit_chain.sh` and come from the rates measured before submission:

| Stage | Device | Rate measured before submission | Full-run limit |
|---|---|---|---|
| `sat` | L40S | 221,000 characters a second (TU-2) | 1.5 h |
| `parse_stanza` | CPU, 1 thread, 24 GB | 583 words per CPU-second (TU-4s) | 6 h per shard |
| `parse_udpipe` | L40S | 6,356 words a second, 185 s server start (TU-4u) | 3 h |
| `encode_e5` | L40S | 1,341 sentences a second (TU-5) | 1.5 h |
| `encode_bgem3` | L40S | none; e5's shape | 1.5 h |
| `surprisal_goldfish` | L40S | none on a GPU | 2 h |
| `surprisal_xglm` | L40S | none; about 3.5 h estimated from FLOPs | 8 h |
| `coref_corpipe` | L40S | none | 6 h |
| `qe_metricx` | L40S | none | 2 h |
| `documents`, `seg_check`, `features_gramlex`, `features_discourse` | CPU | none at this scale | 1 to 6 h per shard |

### What J0 does

1. Builds the core, udpipe and corpipe environments (`envs/build_envs.sh`), keeping any already built from the
   same lock.
2. Checks that the free space under `$FEAT` holds what is still to be downloaded and converted
   (`staging.py disk-plan`), with a tenth to spare, and stops otherwise.
3. Runs `staging.py models`. It fetches every entry of `config/models.lock.json` at its commit, checks every
   file's SHA-256, writes `refs/main` where third-party code loads a snapshot by name (umT5-xl for CorPipe's xl
   model; mT5-large and mT5-xl for its large fallback), clones the CorPipe and MetricX code at their commits, and
   verifies the Stanza and UDPipe files already staged. It then converts the pickled Goldfish and BGE-M3 weights
   to safetensors with `features.surprisal.convert_pickled_checkpoint`, compares every tensor with its source,
   and records the converted files' SHA-256 in `$FEAT/models/conversions.json`. The safetensors copy of
   MetricX-24 is marked optional in the lock: no stage reads it, so it is converted only with
   `--include-optional`.
4. Runs `staging.py resources`: MEmoLon's `en.tsv`, read from the 2.36 GB Zenodo archive by HTTP range requests
   and checked against the archive's CRC-32 and its pinned SHA-256; the wordfreq list inside the locked wheel;
   FLORES-200, copied from the pre-submission area; and the translated benchmark's German outputs.
5. Fetches the SimpleStories train shards (`standin.build_standin download`, which checks each one).
6. Builds eSpeak NG 1.52.0 from its tag (commit 4870adfa) with the toolchain modules named in
   `config/resources.lock.json`, then checks the version phonemizer reports exactly as the duration feature
   does.
7. Runs `staging.py verify` offline, so every pin is checked once more.

Every step skips what is in place and verified, so a resubmission after a time-out repeats nothing that
finished. `j0_metricx.sbatch` builds the metricx environment and checks that the official MetricX-24 code imports
under its pins. It runs after J0, which stages that code, and nothing waits for it: no stage of the dry run runs
in that environment (see Points to settle), so a failure of its 2023 pins or of the Python 3.11 module holds up
nothing.

### Disk

By the sizes pinned in the lock, J0 adds 39.2 GB of new snapshots to the pre-submission hub cache, which both
areas share on `/data/educ-intract`: the two MetricX-24 shards (15.0 GB), XGLM-4.5B (10.2 GB), CorPipe's xl and
large models (7.5 and 2.5 GB), BGE-M3 (2.3 GB) and the smaller pins; the SaT, e5 and UDPipe mBERT snapshots are
already there. The conversions add 3.3 GB under `$FEAT/models`, and the optional MetricX-24 copy would add 15.0 GB
more. The project's quota is not known (UNVERIFIED): J0 logs `df` for `$FEAT` and the cache before it starts and
after it ends.

### Pins of converted weights

The converted files cannot be hashed before they exist, so their SHA-256 is `null` in the committed lock.
Every job therefore starts with `staging.py run-config`, which copies `config/` to a temporary folder. It fills
each null hash from `conversions.json` and sets the converted entry's `path`, so the stages verify and load the
converted folder. A committed hash that disagrees with the recorded conversion stops the job. The overlay's
record is kept in `$FEAT/work/<run>/_runs/`. After the first build, transcribe the hashes from
`$FEAT/records/staging/models.json` (or `conversions.json`) into `config/models.lock.json`, and later builds are
then checked against them.

## Resuming

`run_stage.sh` skips a shard only when its timing record was written by the code that would run now
(`INTRACT_CODE_COMMIT`; a dirty or unknown version is never trusted), its outputs are still there, and every
input file is older than the record (`staging.py resume-plan`). `cli.py` writes the record only after the stage's
outputs are complete. A resubmitted job therefore continues where it stopped, and after a code fix, or a rerun of
the stage upstream, the shards concerned run again instead of keeping stale artefacts and timings. `RESUME=0`
reruns everything.

## Probes, side records and the projection

The point of the dry run is the cost of each stage on the catalogue, so `run_stage.sh` records more than the
timing record `cli.py` writes:

- **Probes.** The invocation that runs shard 0 also runs the stage on one document, once before the shards (the
  cold probe, which pays the job's cold start, such as the 3-7 minute imports from the network file system that
  the pre-submission jobs met) and once after them (the warm probe). Each probe runs in its own folder,
  `<run>/_probe/<cold|warm>/<stage>/`, and reads the run's inputs through links. A failed probe stops nothing.
  `documents` is not probed, since each of its tasks reads the whole input table whatever the limit. Set
  `PROBE=0` to skip them.
- **Side records.** For every shard, `<run>/_runs/<lang>/<stage>-shard-<i>-of-<n>.json` records the environment
  that actually ran (so `qe_metricx` run with `--env core` is not reported as metricx), the CPUs allocated, the
  user and system CPU of the shard's whole process tree from bash's `time` (the UDPipe server and phonemizer
  included, which `cli.py`'s `process_time` leaves out), and whether the process started cold.

`aggregate_timing` turns these into `<run>/_summary/timing.tsv` and `timing.json`
(`config/stages/aggregate_timing.toml`). Two rules keep its projection sound:

- **Units.** A stage's time is scaled by the catalogue's total in the unit its cost follows, over the amount of
  that same unit the stage processed. The catalogue counts whitespace tokens, characters and texts, so the parse
  stages and `features_gramlex` are scaled by whitespace tokens, never by the syntactic words they count (1.14 to
  1.27 per whitespace token), and the text-reading stages by characters. A stage that does not count the unit
  borrows it from `sat` for the same documents of the same shard.
- **Fixed costs.** Only compute is scaled. The split comes from the probes, else from the compute timers a
  stage reports (`seconds_encode`, `seconds_<model>`), else from fixed costs it reports (UDPipe's server start).
  Fixed costs recur once per process of the catalogue run, and cold starts as often as they did here. The table
  reports the fixed and the compute part separately, and beside them the unsplit projection, which scales
  everything and is an upper bound.

CPU stages are projected in core-hours of their allocation (wall time times the CPUs allocated), which is what
ARC bills. GPU-hours in the table are sums of stage wall times; an allocation is billed for its whole elapsed
time, which `budget_guard.py report` shows.

## Determinism and precision checks

- **Rows.** `compare_runs.sbatch smoke full` sets every row of the smoke run against the same story's row in the
  full run, artefact by artefact, and records the rows compared and equal and a SHA-256 over each run's compared
  rows (DESIGN.md, Determinism). Every stage process runs with randomised string hashing (`env.sh`), so equal
  rows also show that no output depends on hash order. The job fails if a row differs.
- **bf16 (P08).** `gpu_bf16.sbatch smoke` reruns XGLM-4.5B, CorPipe and MetricX-24 in bf16 on the smoke run's
  inputs, changing only their precision settings in the run's copy of `config/` (`run_stage.sh --set`), and
  `compare_runs.py bf16` sets their text values against the fp32 ones at the registered r >= .995
  (`surprisal_xglm.toml`, `agreement_threshold`). XGLM also scores fp32 itself (`check_fraction = 1.0`) and its
  own agreement is reported beside. CorPipe has no registered text value; its text mean is the share of adjacent
  sentence pairs its chains link, pending the Feature Specification.

## Budget guard

```
python -I budget_guard.py report                                  # requested, used, committed L40S GPU-hours
python -I budget_guard.py check --cap 25 --add 18                 # status 3 if the cap would be exceeded
```

The guard reads the ledger rows whose gres requests an L40S by name (`gpu:l40s`), tells jobs apart by cluster and
job id, and reads Slurm accounting with `sacct -X -D`, so every allocation of a requeued task counts. *Requested*
is what the jobs asked for. *Used* is elapsed time times allocated GPUs, summed over array tasks and allocations.
*Committed* adds the requested share of every task not yet finished to the time used. A number it cannot trust (a
non-finite or negative request, cap or addition) makes `check` refuse with status 3, so it fails closed.
`submit_chain.sh` runs `check` with the plan's total before it submits anything.

This guard only adds up the ledger against a cap. The protocol's budget guard after acceptance
(preregistration.qmd, Timeline) is a different rule: a pilot on 1 per cent of the catalogue times every GPU step
and projects the total, and if the projection exceeds 400 L40S GPU-hours three steps apply in order (bf16 for
XGLM-4.5B, MetricX-24 and the coreference resolver, only if the P08 check has passed; a smaller coreference model;
the projected-coreference anchor on the keyed sample alone). `aggregate_timing` makes the projection that rule
needs, and the bf16 check settles its first step.

## The ledger

`submit_chain.sh` appends one row per job to `$FEAT/jobs.csv` under `flock`. The columns are those of the
pre-submission ledger: `job_id, cluster, strand, purpose, gres, walltime, gpu_hours_requested, submitted_utc,
outputs, postprocess_command`.

## Temporary folders

Each job works in `$FEAT/tmp/<job>_<task>`. The script that sourced `env.sh` first in the job owns the folder
and removes it on exit; scripts it calls leave it alone, so the combined job's background lane never loses its
files to a finishing stage. A job killed at its time limit cannot clean up, so `submit_chain.sh` removes the
folders of jobs that `squeue` no longer lists, and removes nothing when `squeue` does not answer.

## Outputs and records

Each run writes its artefacts under `$FEAT/work/<run>/<lang>/` and its timing records under `<lang>/_timing/`.
The aggregate job writes `$FEAT/work/<run>/_summary/timing.tsv` and `timing.json`; the row check writes
`full/_summary/rows_vs_smoke.json` and the bf16 check `smoke_bf16/_summary/bf16_check.json`. Copy the run records
to `records/` in the repository as `records/README.md` describes. The outputs themselves stay on ARC.

## Points to settle

- `qe_metricx.py` declares the core environment, where its port (`reference/metricx_qe.py`) is validated with
  torch 2.14 and transformers 5.19. The metricx environment holds MetricX's official pins (transformers 4.30.2,
  Python 3.11) for the one-off validation of the port only. `submit_chain.sh --qe-env` remains for running the
  stage elsewhere; its default, core, is the stage's own.
- The dry run times `qe_metricx` on the translated benchmark's English-German pairs (MADLAD-400, 40,055 sentence
  pairs; 400 in the smoke run), because the stand-in has no translations.
- `seg_check` computes its report in the run with `--shard 0` only; the other shards return at once, so the
  combined job's loop over the shards does the work once, and separate mode submits it as a single task.
- The stand-in's acceptance check misses its 1st and 5th percentiles of tokens per page (`standin/README.md`). J1
  records the failure in `_input/standin_manifest.json` and goes on, because `standin.toml` [acceptance] `enforce`
  is false; set it to true to make a failed check stop the chain (exit 3), once the PI has ruled.
- `cli.py` could record the split itself (a mark after loading), the active environment and the CPU time of child
  processes; the probes and side records stand in for that until it does.
- The catalogue lock resolves its files against the code's own `config/` (`lock.DEFAULT_CONFIG_DIR`), not against
  the run's temporary copy that `run_stage.sh` passes as `--config`, because that copy cannot carry the paths
  relative to the repository (`../../story_texts/data/`). The two hold the same `[lock]` table, since `run-config`
  copies `config/` and changes only the model pins and `--set` values.
