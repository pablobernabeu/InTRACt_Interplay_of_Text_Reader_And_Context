# Run records

`DESIGN.md`, Tests: "Tests marked `gpu` or `models` run on ARC, and their results are kept in `records/`.
Outputs on real data never enter the repository. Only run records (input hashes, code commit, environment lock
hashes, model pins verified, timings) do." This folder holds those records, copied back from ARC
(`$INTRACT_RECORDS`, `/data/educ-intract/educ1242/intract_features/records`, and each run's work folder).

## What belongs here

One folder per run or build, named by date and run, for instance `2026-11-20_smoke/`:

| File | Source on ARC | Shows |
|---|---|---|
| `envs/<env>.freeze.txt` | `$INTRACT_RECORDS/envs/` | each environment's installed packages, the lock's SHA-256, the CUDA build |
| `staging/models.json`, `resources.json`, `verify.json` | `$INTRACT_RECORDS/staging/` | every pin fetched and verified, with any failure |
| `conversions.json` | `$INTRACT_MODELS/conversions.json` | the SHA-256 of each converted safetensors file, and the tensor-by-tensor check against its source |
| `overlay-*.json` | `$FEAT/work/<run>/_runs/` | which hashes and overrides a run's config filled in, and from which conversion record |
| `timing.tsv`, `timing.json` | `$FEAT/work/<run>/_summary/` | each stage's measured cost, throughput, fixed and compute time, and projection to the catalogue |
| `_timing/`, `_runs/` | `$FEAT/work/<run>/<lang>/_timing/`, `$FEAT/work/<run>/_runs/<lang>/` | the timing record of every shard, and its side record: environment that ran, CPUs, process-tree CPU, cold start |
| `_probe/` | `$FEAT/work/<run>/_probe/<cold\|warm>/<stage>/<lang>/_timing/` | the one-document probes behind the fixed/compute split (timing records only) |
| `rows_vs_smoke.json` | `$FEAT/work/full/_summary/` | the smoke rows against the same rows of the full run, with each run's hash |
| `bf16_check.json` | `$FEAT/work/smoke_bf16/_summary/` | the P08 bf16 check: text-value agreement of XGLM-4.5B, CorPipe and MetricX-24 with fp32 |
| `jobs.csv` | the ledger's rows for the run | job ids, requests and GPU-hours |
| `tests/` | ARC runs of the `gpu` and `models` tests | their results |

## What never belongs here

- Any story text, or anything computed on the story texts beyond the structural counts the configuration already
  quotes (`config/stages/aggregate_timing.toml` [catalogue]). No feature is computed on them before in-principle
  acceptance.
- Pipeline outputs (documents, segments, parses, feature records, embeddings), including those on the public
  stand-in: they are large, and the code rebuilds them from the pinned inputs.
- The stand-in table itself and its `selection.tsv`. The builder and its pins are the record. Its
  `standin_manifest.json` also holds the catalogue's structure (token quantiles, character totals), so whether it is
  copied here follows the PI's decision on depositing the structure table (`standin/README.md`).

## Transcribing converted pins

The SHA-256 of a converted file is `null` in `config/models.lock.json` until the first build records it. Copy
each file's hash from `conversions.json` into the matching entry's `files` table, with the date and the build's
job id in the commit message. Later builds are then checked against the committed value, and
`jobs/arc/staging.py run-config` stops a run whose converted files differ from it.
