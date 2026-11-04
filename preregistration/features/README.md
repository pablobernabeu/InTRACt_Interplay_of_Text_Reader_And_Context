# The InTRACt feature pipeline

This package computes the registered text features of InTRACt, a Stage 1 Registered Report on children's reading
in the Let's Story app. The features are registered in the protocol (`../preregistration.qmd`, Materials, Measures
and Outcome-blind dimension reduction) and its supplement (`../supplementary.qmd`, S3 above all).
`SPECIFICATION.md` maps each registered quantity to the function that computes it, `DESIGN.md` fixes the contracts
every module follows, and `LICENCES.md` lists the licence of every model, resource and corpus the pipeline uses.

This is the first version, built on 3 November 2026 for a dry run on ARC, Oxford's Slurm cluster. The dry run runs
the English path on a public stand-in at the catalogue's scale, to measure what each stage costs. The stories
themselves are processed only after in-principle acceptance.

## Public data only, behind a lock

The protocol commits that "No linguistic feature registered here has been computed on the story texts, and none will
be before in-principle acceptance" (`../preregistration.qmd`, Data provenance, sequestration and outcome
blindness). Before acceptance the pipeline therefore reads public data only:

- the **stand-in** (`standin/`): stories from the public SimpleStories dataset, matched one for one to the English
  catalogue's texts by length and cut into exactly their numbers of pages, built from a structure table that holds
  identifiers and counts and no text;
- **FLORES-200**, for the stages that compare languages, after the English dry run;
- public test material: the SimpleStories test split, UD treebanks, TinyStories and synthetic fixtures.

The documents stage, the way text enters the feature stages, puts every input behind the catalogue lock
(`src/intract_features/lock.py`, configured in `config/stages/documents.toml` [lock]). The lock refuses any file
whose SHA-256 a published manifest of the story texts records, any file inside the folders that hold them, and,
once `lock_build` has fingerprinted the published tables, any text whose normalised tokens match a catalogue
text's, whatever file it was copied into. It opens only when the record of in-principle acceptance matches a
checksum committed to git. `qe_metricx`, which reads page pairs, applies the same lock. Two tools outside the
stages read a published story table: `lock_build`, which fingerprints every text, and
`standin/catalogue_structure.py`, which counts pages, tokens and characters. Both refuse to run without
`--authorisation`, which names the PI's go-ahead as recorded in the lab log and the sequestration disclosure.

## Layout

```
features/
  README.md  DESIGN.md  SPECIFICATION.md  LICENCES.md  pyproject.toml
  src/intract_features/
    cli.py  config.py  records.py         command line, configuration, document model and artefact storage
    lock.py  lock_build.py                the catalogue lock and the tool that fingerprints the published tables
    io/catalogue.py                       the published table schema (also read for the stand-in)
    text/                                 normalisation, the registered word function, titles, keyed samples,
    segment/                              the SaT call, the union segmenter, the frozen rules, the diagnostics
    parse/                                the parser units, the CoNLL-U artefacts, Stanza and UDPipe 2
    features/                             grammatical, lexical, diversity, discourse, surprisal and similarity features
    reference/                            CorPipe 26, the MetricX-24 port and the word aligner
    stages/                               the fourteen stages, one module each
  config/                                 pipeline.toml, languages.toml, stages/<stage>.toml, the model and
                                          resource locks, and the lock's frozen checksum records (lock/)
  standin/                                the public stand-in builder
  envs/                                   the four hash-locked environments for ARC
  jobs/arc/                               the ARC job templates, the run wrapper, staging and the budget guard
  records/                                run records copied back from ARC (no outputs on real data)
  tests/unit/  tests/gpu/  tests/golden/  unit tests, GPU and model tests for ARC, golden fixtures
```

## Stages

Each stage is one module in `src/intract_features/stages/` and writes one artefact under
`<work>/<lang>/<artefact>/shard-<i>-of-<n>.<ext>` (`DESIGN.md` gives the table of inputs and outputs). The status
says how far each stage was checked on 3 November 2026. Nothing has yet run on ARC, so no stage has met its real
model on a GPU.

| Stage | Device, environment | Computes | Status |
|---|---|---|---|
| `documents` | CPU, `core` | rows in the catalogue's schema to normalised documents, behind the lock | Run through the command line under the real lock on SimpleStories; smoke rows equal full-run rows. Page titles excluded by default (G1b, pending the PI) |
| `sat` | GPU, `core` | the registered SaT sentence boundaries | Reproduces the benchmark's registered F1 values and English SaT's 382 of 382 boundaries; run with a tiny random model on CPU. The real model on a GPU awaits ARC |
| `seg_check` | CPU, `core` | English SaT against the frozen rule segmenter (boundary F1 of 95, 0.95 on the code's scale) and the five-sentence floor | Tested with a fake SaT; the bootstrap reproduces the benchmark's. Computes in the `--shard 0` run only |
| `parse_stanza` | CPU, `core` | the Stanza 1.15.0 parse of every registered sentence | Run with the real Stanza 1.15.0 and the pinned English models on CPU (stand-in smoke) |
| `parse_udpipe` | GPU, `udpipe` | the UDPipe 2 parse on a local deterministic server | Tested against a stand-in server; UDPipe 2 under TensorFlow awaits ARC |
| `features_gramlex` | CPU, `core` | grammatical, lexical, diversity and page features | Counts equal the error model's gfeat on 62 UD files. Subordination is written as an empirical logit, a conflict with the registered ratio (CF-01) |
| `features_discourse` | CPU, `core` | overlap, continuation, connectives, dialogue share, names, affect and spoken duration | Run with the real phonemizer 3.4.0 and eSpeak NG 1.52.0; the MEmoLon reader has not met the real English table |
| `surprisal_goldfish` | GPU, `core` | corrected word surprisal, Goldfish 1 GB (anchor) and 100 MB | Tested with tiny random models on CPU. The registered mean waits for the name rule (P06, P53) and is written as null |
| `surprisal_xglm` | GPU, `core` | corrected word surprisal, XGLM-4.5B contrast | As `surprisal_goldfish`; its bf16 path is checked against fp32 on ARC |
| `encode_e5` | GPU, `core` | adjacent-sentence similarity, multilingual-e5-large-instruct | Tested with tiny random encoders on CPU |
| `encode_bgem3` | GPU, `core` | adjacent-sentence similarity, BGE-M3 (sensitivity) | As `encode_e5` |
| `coref_corpipe` | GPU, `corpipe` | CorPipe 26 coreference chains on every English source | The official script runs end to end with a tiny umT5 on CPU, in fp32 and bf16 |
| `qe_metricx` | GPU, `core` | MetricX-24 reference-free quality estimates of page pairs | The port reproduces the official tokenisation on 44,439 public inputs and the official forward pass on a tiny checkpoint; admitted only after the validation on ARC with the real weights |
| `aggregate_timing` | CPU, `core` | the timing records of a run in one table, with a projection to the catalogue | Tested on hand-built records and on the local smoke run |

`list-stages` prints the same list:

```
python -m intract_features list-stages
```

## Environments

| Environment | Python | What runs there |
|---|---|---|
| `core` | 3.12 | every stage not named below, `qe_metricx`'s port and the stand-in builder |
| `udpipe` | 3.12 | `parse_udpipe` and the UDPipe 2 server |
| `corpipe` | 3.12 | `coref_corpipe` and the official CorPipe 26 script |
| `metricx` | 3.11 | no stage: the official MetricX-24 code, for the one-off validation of the port |

`envs/README.md` gives the pins and how the hash-locked `envs/<env>.lock` files were compiled. Locally only the
standard library is needed: every stage imports its heavy libraries inside functions.

## Running the tests

From this folder, with Python 3.12 or later:

```
python -m pip install -e ".[dev]"
python -I -X utf8 -m pytest tests/unit -q -p no:cacheprovider
ruff check . --no-cache
```

Tests that need NumPy, pyarrow, wordfreq, torch, transformers, Stanza, minnt or a downloaded file skip without
them. Tests marked `gpu` or `models` are deselected by default (`pyproject.toml`); on ARC, or with the files they
need, run them with `-m "gpu or models"`. They find their inputs through environment variables, among them
`INTRACT_SIMPLESTORIES_DIR` (the SimpleStories test split), `INTRACT_TU_DIR` (the translated benchmark's files),
`INTRACT_XLMR_TOKENIZER_DIR`, `INTRACT_PHONEMIZE_PYTHON`, `INTRACT_ESPEAK_LIBRARY` and `INTRACT_ESPEAK_DATA`,
`INTRACT_GFEAT_REPRO_DIRS` and `INTRACT_OLD_GFEAT`, `INTRACT_CORPIPE_SRC` and `INTRACT_TEST_CONFIG`; each test's
docstring names what it reads. `.github/workflows/features.yml` runs ruff and the unit tests on Python 3.12 with NumPy and
wordfreq installed.

## Running a stage

A stage runs one shard of one language. The command line reads `config/` (or `--config`), writes the stage's
artefact under `--work` and a timing record under `<work>/<lang>/_timing/`:

```
python -m intract_features run documents --work WORK --lang en-us --input STANDIN/en-us/stories.csv.xz --shard 0 --nshards 4
python -m intract_features run sat --work WORK --lang en-us --shard 0 --nshards 4
python -m intract_features run seg_check --work WORK --lang en-us --shard 0 --nshards 4
```

Every stage of a run must use the same number of shards. `--limit K` keeps the first K documents of a shard.
The GPU stages load their models from folders verified against `config/models.lock.json`; locally they run only
with the fakes the unit tests inject through `ctx.extra`.

The stand-in is built from the features folder, because `standin/` sits beside the installed package:

```
python -m standin.build_standin download --dest SHARDS
python -m standin.build_standin build --structure STRUCTURE.tsv --shards SHARDS --out STANDIN [--smoke]
```

## The dry run on ARC

`jobs/arc/README.md` sets out the prerequisites and the chain. In short, after syncing this folder to ARC, copying
the two manifest files the lock reads and the structure table, and choosing a GPU-hour cap:

```
cd /data/educ-intract/educ1242/intract_features/code/jobs/arc
bash submit_chain.sh --cap 25 --build --dry-run     # the plan and the budget check; nothing is submitted
bash submit_chain.sh --cap 25 --build               # J0 build, then the smoke chain, then the full chain
```

J0 builds the environments, fetches and verifies every pinned model and converts the pickled Goldfish and BGE-M3
weights to safetensors. Each run (the smoke run on the smallest 1
per cent of targets, then the full run on all 40,559) builds the stand-in, runs `documents`, then every GPU stage
in one L40S allocation, then the CPU feature stages and `aggregate_timing`. `compare_runs.sbatch` sets the smoke
run's rows against the full run's, and `gpu_bf16.sbatch` runs the P08 bf16 check. The budget guard
(`jobs/arc/budget_guard.py`) refuses a submission that would take the ledger past the cap. No job sends mail.

## Where the Feature Specification stands

`SPECIFICATION.md` is a first draft of 3 November 2026, revised the same day after review, and is not frozen. It
covers the English path in 97 rows: 16 implemented, 39 implemented with a default that awaits a decision, 1 in
conflict with the registered text and 41 not yet built. It lists 10 gaps (G1a to G9), 35 open choices (FS-01 to
FS-36; FS-21 became the conflict CF-01), and what the translations need from English. `tests/unit/test_spec_anchors.py`
checks every quotation, code reference, setting and pin it contains. The draft becomes the frozen specification
when the inventory is frozen under the protocol's fourth rule, before any feature is linked to outcome data.

## Open problems

- **Smoke rows against full rows.** `features_discourse` decides names over the whole catalogue, so its name
  covariates and the affect means with the name exclusion differ between the smoke and the full run by
  construction, and `compare_runs` will report those rows as different. Whether to leave those fields out of the
  comparison or to rescore the smoke rows with the full inventory is undecided.
- **The stand-in's acceptance check** misses its 1st and 5th percentiles of tokens per page, and the young group's
  95th. It is recorded and
  does not stop the run (`config/stages/standin.toml`, `[acceptance] enforce = false`), pending the PI.
- **Decisions for the PI** that change registered quantities: page titles leaving the denominator (G1b), the form
  of subordination (CF-01) and the direct-speech rule (G6); the others are listed in `SPECIFICATION.md`.
- **Pins still pending.** The safetensors converted from the pickled Goldfish and BGE-M3 weights are hashed by the
  ARC build; until those hashes are transcribed into `config/models.lock.json`, each run's copy of `config/`
  carries them.
- **Unverified on Linux and ARC.** Nothing here has run on ARC or on Linux; the GPU and model tests, the
  environments' builds and the continuous-integration workflow are written but not yet run there.
- **Memory.** `features_discourse` holds a shard's parsed documents in memory, about 3 GiB per shard of the English
  catalogue at four shards, which the dry run will measure.
