# Pinned environments for ARC

The feature pipeline runs on ARC in four virtual environments, each built from a lock in which every package
is pinned to one version and to the SHA-256 of its files (`DESIGN.md`, Environments). A stage names the
environment it runs in (`cli.Stage.env`), and `jobs/arc/run_stage.sh` activates it.

| Environment | Python | Main pins | Stages | Why separate |
|---|---|---|---|---|
| `core` | 3.12.3 | torch 2.14.1+cu126, transformers 5.19.0, wtpsplit 2.2.2, stanza 1.15.0, wordfreq 3.1.1, phonemizer 3.4.0, numpy 2.5.4, scipy 1.18.1, pyarrow 26.0.0 | every stage not listed below | |
| `udpipe` | 3.12.3 | tensorflow 2.21.0, tf-keras 2.21.0, transformers 4.57.6, ufal.udpipe 1.4.0.1 | `parse_udpipe` | TensorFlow for UDPipe 2 and its mBERT embeddings |
| `corpipe` | 3.12.3 | torch 2.10.0+cu126, transformers 5.2.0, minnt 1.1.1, udapi 0.5.2 | `coref_corpipe` | CorPipe 26 requires torch~=2.10.0 and transformers~=5.2.0 |
| `metricx` | 3.11.5 | transformers 4.30.2, sentencepiece 0.1.99, datasets 2.13.1, torch 2.5.1 | none in the dry run: the official MetricX-24 code, for validating the port in `reference/metricx_qe.py` | MetricX-24's official pins |

The Python versions are ARC's modules `Python/3.12.3-GCCcore-13.3.0` and `Python/3.11.5-GCCcore-13.2.0`.
The metricx environment needs 3.11, because sentencepiece 0.1.99 and tokenizers 0.13.3, which transformers
4.30.2 requires, publish no CPython 3.12 wheels. The `intract_features` package is installed into the other
three only: it requires Python 3.12 or later.

The protocol pins some of these versions itself. Supplementary S3 registers wtpsplit 2.2.2, Stanza 1.15.0,
phonemizer 3.4.0 and eSpeak NG 1.52.0. eSpeak NG is a C library, so `jobs/arc/j0_build.sbatch` builds it from
its tag (`config/resources.lock.json`), because ARC has no module for it.

## Files

| File | Contents |
|---|---|
| `<env>.in` | The top-level requirements, with the reason for each pin |
| `<env>.lock` | The hash-locked closure that `build_envs.sh` installs with `--require-hashes` |
| `constraints/<env>.txt` | The constraints `core`, `udpipe` and `corpipe` were compiled with (below) |
| `build_envs.sh` | Builds the environments on ARC (`j0_build.sbatch` and `j0_metricx.sbatch` call it) |

## How the locks were compiled

On 3 November 2026, with uv 0.11.20, for `x86_64-manylinux_2_28`, from copies of the `.in` files, so that each
lock's annotations name only `<env>.in` and `presub-freeze.txt` (for core, udpipe and corpipe, a copy of
`constraints/<env>.txt` under that name):

```
uv pip compile core.in --generate-hashes --python-version 3.12.3 --python-platform x86_64-manylinux_2_28 \
  --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cu126 \
  --index-strategy unsafe-best-match --emit-index-url -c presub-freeze.txt -o core.lock
uv pip compile udpipe.in  ... --index-url https://pypi.org/simple --emit-index-url -c presub-freeze.txt
uv pip compile corpipe.in ... (as core) -c presub-freeze.txt
uv pip compile metricx.in --generate-hashes --python-version 3.11.5 --python-platform x86_64-manylinux_2_28 \
  --index-url https://pypi.org/simple --emit-index-url --exclude-newer 2024-12-13T00:00:00Z -o metricx.lock
```

Each lock's header records the exact command, and the constraints are kept in `constraints/`, so a compile can be
repeated from the repository. They come from the freeze records of the pre-submission environments that ran on
ARC between 22 and 24 October 2026, so every package those environments share with these keeps the version that
ran there: for `core`, the union of translated_union's `seg`, `mt` and `stanza115`, error_model's `stanza115` and
`em`, and third_parser's `stanza_tp`, which held no conflicting versions; for `udpipe`, error_model's `udpipe2`;
for `corpipe`, core's set without the torch, transformers, tokenizers, triton, CUDA and hub packages, which
CorPipe's own pins set instead.

The metricx set is resolved from PyPI as of the date of the pinned MetricX commit (fc4978eb, 12 December 2024).
Its official requirements pin transformers, sentencepiece and datasets to releases of mid-2023 and leave
torch, accelerate, pyarrow, fsspec and pandas open. Resolved against 2026 releases, those open dependencies
would meet APIs the 2023 pins do not know. The date resolves them to what a fresh install met when MetricX-24
was published, which gives torch 2.5.1, whose PyPI build carries CUDA 12.4 libraries. The L40S nodes' driver,
580.65.06 in the pre-submission job logs, supports them. Four departures from the official file are made
deliberately: `git+https://github.com/google-research/mt-metrics-eval` is left out, because it serves
meta-evaluation only and a git dependency cannot be hash-locked; numpy is held below 2.0, a release a year
younger than those pins; and protobuf 3.20.3 and fsspec 2023.6.0 are pinned, because `predict.py` does not run
without them. transformers 4.30.2 converts mt5-xl's `spiece.model` with a converter that needs protobuf and whose
generated module fails under protobuf 4 and later, and datasets 2.13.1 refuses its own cache under the fsspec of
December 2024. Both failures were reproduced with the lock's versions on Python 3.11.5 on 3 November 2026, and the
lock was recompiled with these two pins, which changed fsspec, added protobuf and dropped setuptools (the package
is not installed in this environment); every other package kept its version and hashes.

## Checks against the environments that already ran

- `udpipe.lock` holds the same 57 packages, versions and file hashes as the error model's `udpipe2.lock`, the
  environment whose fresh-server reruns on L40S were byte-identical in 46 of 46 files.
- `core.lock` agrees with translated_union's `seg.lock` (SaT, e5) in version and hashes on all 72 packages
  they share, and with error_model's `stanza115.lock` in version on all 56 they share.
- `tests/unit/test_budget_guard.py` checks that every requirement in every lock carries hashes and that each
  `==` pin of a `.in` file is the version locked.

## Building on ARC

```
bash /data/educ-intract/educ1242/intract_features/code/envs/build_envs.sh [core] [udpipe] [corpipe] [metricx]
```

The script bootstraps uv 0.12.24 from a wheel pinned by its PyPI SHA-256, because ARC's uv module (0.2.30)
is too old for these locks. It then builds each environment in place: `uv pip sync --require-hashes` from
the lock, the package installed editable without dependencies or build isolation (setuptools comes from the
lock), `uv pip check`, an import check, and a freeze record in `$INTRACT_RECORDS/envs/<env>.freeze.txt`.
Wheels are hard-linked from the pre-submission uv cache, which already holds most of them. A stamp file,
written only after every check has passed, records the lock's SHA-256, the Python module and the uv version; an
environment whose stamp matches and whose import check passes again is kept (its editable install is refreshed),
so a resubmitted J0 does not rebuild it. `FORCE=1` rebuilds anyway. J0 builds core, udpipe and corpipe;
`j0_metricx.sbatch` builds metricx, apart, because no stage of the dry run needs it.

## To recompile

Change the `.in` file, copy `constraints/<env>.txt` to `presub-freeze.txt` beside it (core, udpipe and corpipe),
and rerun its command from that folder. A recompilation picks the newest versions that the constraints allow, so
a lock is the reproducible record and an `.in` file only states the intent. Rebuild the environment with
`FORCE=1` and rerun the pipeline's tests afterwards.

## Not yet verified

- That the CorPipe code runs under torch 2.10.0+cu126 and transformers 5.2.0 on ARC. Both are within its stated
  requirements, and the j0 import check covers the packages.
- That the official MetricX-24 `predict.py` runs end to end in the metricx environment. `j0_metricx` checks only
  that `metricx24.models` imports.
- Containers. Apptainer was not found on the login node, and no build host is named (plan critique, item 11),
  so the uv environments are the primary route.
