# Design of the feature pipeline

This note fixes the contracts that every module follows. It is the reference for
anyone adding a stage. The registered rules themselves are in the protocol
(`../preregistration.qmd`) and its supplement (`../supplementary.qmd`, S3 above all).
`SPECIFICATION.md` maps each registered quantity to the function that computes it, and
`README.md` says how to run the pipeline and where each stage stands.

## What runs where, and when

Before in-principle acceptance the pipeline runs only on public data:

- the **stand-in**, public children's stories matched to the catalogue's page and word
  counts (`standin/`);
- **FLORES-200**, for the stages that compare languages.

`lock.py` refuses the catalogue's story texts until acceptance is on record. The
registered 1 per cent pilot on the stories comes after acceptance.

## Data model

- **Document** (`records.Document`): one text of one language version. Its `pages`
  are normalised once at load time: NFC, with invisible format characters removed
  (S3). `text` joins the pages with a single space (Materials), and every character
  offset in every artefact refers to that string. The delivered title line is kept in
  `title` and read by no feature (gap G1a). Page-initial titles found under S3's rule are
  cut out of their pages into `meta.page_titles` by default (gap G1b, pending the PI).
  `meta.keyed_hash` holds the story's keyed hash, which depends on its identifier alone.
- **Words**: the registered word function (`text/words.py`) returns `[start, end)`
  spans over `text`. A word is "a whitespace-delimited token of the text as served that
  contains at least one letter or digit", and a token of punctuation alone attaches to
  a neighbouring word (Measures). `text.words.LINE_BREAK`, the decoded line feed, is the one
  in-page line break the text rules read (titles, dash turns, word extents); the parse stages
  flatten every line-break character to a space before parsing.
- **Sentences** (artefact `segments`, one record per document): `[start, end)` spans over
  `text`, trimmed of whitespace, from the registered SaT call for English (`segment/`),
  each with the index of the page it starts and ends on (`sentences`, with
  `sentence_fields`). The record also holds `segmenter` ("sat"), `is_source`,
  `text_sha256` (so that a stale artefact is caught), `n_sentences`, `newline_forced` (the
  boundaries only a line break forced), `candidates` (p' at the union segmenter's
  candidate positions) and, for the English source, the five-sentence `floor` flag.
- **Parses** (artefacts `parses_stanza` and `parses_udpipe`, extension `conllu.gz`):
  CoNLL-U, one file per parser and shard, written and read by `intract_features.parse`
  alone. Each document starts with `# newdoc id = <story_id>` and each sentence carries
  `# sent_id = <story_id>-<k>`, `# text = ...` and `# span = <start>:<end>`. Sentence k,
  counted from 0, is sentence k of the segmentation artefact. `# text` is the sentence with
  each line break replaced by one space, so its offsets are unchanged. MISC holds
  `TokenRange=<start>:<end>` in `text` and `SpaceAfter=No`. A sentence the parser returned
  nothing for keeps its block, ending in `# parse = empty`, after `# refused = <reason>`
  when the parser refused it (UDPipe's 1,000-word limit). A document with no sentence
  writes no block. In the parse stages' counts, `words` are syntactic words.
- **Feature records**: one JSON object per document per stage, holding `story_id`,
  `lang`, `values` (registered quantities by name) and `diagnostics` (anything else).
  Non-finite numbers are written as `null`, and every file is strict JSON.

## Artefacts and stages

Artefacts live at `<work>/<lang>/<artefact>/shard-<i>-of-<n>.<ext>`, written
atomically: a temporary file is renamed into place, so a job killed at its time limit
never leaves a file that looks complete. A story's shard is a keyed hash of its id
(`records.shard_of`, with the key of `config/pipeline.toml` [keys]), so every language
version of a story falls in the same shard.

The first version has fourteen stages and twelve artefacts:

| Stage | Device, environment | Reads | Writes |
|---|---|---|---|
| `documents` | CPU, `core` | `--input` table in the catalogue's schema, behind the lock | `documents`, and a run manifest beside each shard |
| `sat` | GPU, `core` | `documents` | `segments` |
| `seg_check` | CPU, `core` | `documents`, `segments` (every shard) | `<work>/<lang>/_checks/seg_check.json`, from the run with `--shard 0` |
| `parse_stanza` | CPU, `core` | `documents`, `segments` | `parses_stanza` |
| `parse_udpipe` | GPU, `udpipe` | `documents`, `segments` | `parses_udpipe` |
| `features_gramlex` | CPU, `core` | `documents`, `segments`, `parses_stanza`, `parses_udpipe` | `features_gramlex` |
| `features_discourse` | CPU, `core` | `documents`, `segments`, `parses_stanza` (every shard, for the name inventory) | `features_discourse`, and `name_inventory.txt` |
| `surprisal_goldfish` | GPU, `core` | `documents` | `surprisal_goldfish` |
| `surprisal_xglm` | GPU, `core` | `documents` | `surprisal_xglm` |
| `encode_e5` | GPU, `core` | `documents`, `segments` | `encode_e5` |
| `encode_bgem3` | GPU, `core` | `documents`, `segments` | `encode_bgem3` |
| `coref_corpipe` | GPU, `corpipe` | `documents`, `parses_stanza` | `coref_corpipe` |
| `qe_metricx` | GPU, `core` | `--input` page pairs, behind the lock | `qe_metricx` |
| `aggregate_timing` | CPU, `core` | every timing record of a run | `<work>/_summary/timing.tsv` and `timing.json` |

A stage is one module in `src/intract_features/stages/`. It defines:

```python
STAGE = Stage(name="sat", inputs=("documents",), outputs=("segments",), device="gpu", env="core",
              description="registered SaT sentence boundaries for English")

def run(ctx: StageContext) -> dict:   # returns counts for the timing record
    ...
```

The command line discovers the module, so no shared registry is edited. Every stage
module imports its heavy libraries (torch, transformers, Stanza, wtpsplit, TensorFlow,
NumPy) inside functions only, because the command line imports every stage module in
whichever environment runs. Every run writes a timing record to `<work>/<lang>/_timing/`,
with wall and CPU seconds, peak memory, the GPU and its peak allocation, and the counts
the stage returns. A stage should return at least `documents`, `words` and `characters`,
and `tokens` where it runs a subword model, so that costs can be projected per unit;
`whitespace_tokens` lets the projection use the catalogue's own unit, and a compute timer
(`seconds_<name>`) lets it separate loading from compute.

Tests and smoke runs inject models through `ctx.extra` (`sat_backend`, `scorers`,
`encoder`, `stanza_model_dir`, `udpipe_url`); the command line passes none.

Library code lives outside `stages/`, in `text/`, `io/`, `segment/`, `parse/`,
`features/` and `reference/`, with `lock.py` and `lock_build.py` beside them. A stage
module only reads artefacts, calls library functions and writes artefacts.

## Configuration

- Every registered constant, seed and key string lives in `config/`, never in code.
- Shared values are in `config/pipeline.toml`, and per-language values in
  `config/languages.toml`.
- Each stage's constants are in its own `config/stages/<stage>.toml`, with a comment
  quoting the anchor in the protocol. Some stages read another stage's table, which must
  then change in step: `features_gramlex` reads `parse_udpipe.toml` [long_units] and, on
  the G6 detector route, `features_discourse.toml` [dialogue]; `features_discourse` reads
  `features_gramlex.toml` [lexical.normalisation] and [lexical.casing]; `parse_udpipe`
  reads `parse_stanza.toml` [input] and [segments]; `seg_check` reads `sat.toml` and
  `documents.toml` [keyed_sample]; `qe_metricx` reads `documents.toml` [lock] and
  [normalise].
- Model and resource pins (repository, revision, file SHA-256, licence) are in
  `config/models.lock.json` and `config/resources.lock.json`.
- Code verifies a pin before it loads the file. Weights that ship only as pickles are
  converted to safetensors by the ARC build, whose hashes cannot be known before; the
  committed lock holds them as null, and `jobs/arc/staging.py run-config` writes each
  run's copy of `config/` with the hashes the build recorded. `run-config --set` changes a
  value in that copy only (the bf16 check uses it).
- The catalogue lock resolves its files (`documents.toml` [lock]) against the code's own
  `config/` (`lock.DEFAULT_CONFIG_DIR`), whatever `--config` names, because a run's
  temporary copy cannot carry paths relative to the repository; tests pass
  `ctx.extra["config_dir"]`.

## Environments

The ARC jobs use hash-locked uv environments in `envs/`, one per pin set:

| Environment | Main contents | Why separate |
|---|---|---|
| `core` | torch 2.14.1, transformers 5.19.0, Stanza 1.15.0, wtpsplit 2.2.2, wordfreq 3.1.1, phonemizer 3.4.0 (eSpeak NG 1.52.0 as a program), pyarrow; every stage below not named elsewhere, `qe_metricx`'s port included | |
| `udpipe` | TensorFlow 2.21 and transformers 4.57.6 for UDPipe 2 (`parse_udpipe`) | UDPipe's pins |
| `corpipe` | torch 2.10.0 and transformers 5.2.0 for CorPipe 26 (`coref_corpipe`) | CorPipe's pins conflict with `core` |
| `metricx` | Python 3.11 and transformers 4.30.2: the official MetricX-24 code, for the one-off validation of the port in `reference/metricx_qe.py`; no stage runs here | MetricX's pins conflict with `core`, and this package needs Python 3.12 |

Container definitions follow once Apptainer is confirmed on ARC's compute nodes.

## Determinism

- Language models and encoders run in fp32 with TF32 off. bf16 is used only where the
  budget guard allows it, and the bf16 check reports agreement with fp32
  (`jobs/arc/gpu_bf16.sbatch`, P08).
- Batches have fixed shapes wherever padding could change a result.
- Seeds come from `config/`.
- A rerun on the same GPU model must give identical outputs. The 1 per cent smoke run's
  rows must equal the same rows of the full run, and the run records compare their hashes
  (`jobs/arc/compare_runs.sbatch`). A record must therefore depend only on its own story
  and the configuration: the documents stage stores a story's keyed hash, not a rank over
  the input. One known exception is open: the name covariates and the affect means with
  the name exclusion depend on the catalogue-wide name inventory, so they differ between a
  smoke and a full run by construction (README.md, Open problems).
- Every stage process runs under `python -I`, so string hashing is randomised and no
  output may depend on hash order; the row comparison checks this too.

## Tests

- `tests/unit/` runs anywhere, on tiny hand-built fixtures; `test_integration.py` holds
  the contracts between the parts (stage and artefact names, environments, keys,
  documentation).
- `tests/golden/` holds small public fixtures with expected outputs.
- Tests marked `gpu` or `models` run on ARC, and their results are kept in `records/`.
- `.github/workflows/features.yml` at the repository's root runs ruff and the unit tests on Python 3.12.
- Outputs on real data never enter the repository. Only run records (input hashes,
  code commit, environment lock hashes, model pins verified, timings) do.
