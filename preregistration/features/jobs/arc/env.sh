# Sourced by every feature-pipeline job on ARC (and by interactive sessions), after the #SBATCH lines:
#     source /data/educ-intract/educ1242/intract_features/code/jobs/arc/env.sh [core|udpipe|corpipe|metricx]
# Adapted from the pre-submission strands' common/env.sh, whose lessons it keeps:
# * The home quota is nearly full (13.5 of 15 GB) and ~/.bashrc prepends another project's environment and conda
#   to PATH, so jobs are submitted with --export=NONE, PATH is rebuilt here and no cache ever lives under $HOME.
# * A clean batch shell does not define `module`; the htc compute nodes have /etc/profile.d/modules.sh but no
#   lmod.sh (sourcing lmod.sh alone failed every batch job on 22 October 2026).
# * Keras, Triton, the CUDA JIT cache and XDG data wrote to ~ until their variables were set (23 October 2026).
# * Models and data are staged by j0_build; every later job runs offline against the pinned snapshots.
# The caller sets its own shell options (set -eo pipefail); nounset is relaxed while this file runs, because the
# Lmod and venv activation scripts read unset variables.
_intract_opts=$-
set +u

export FEAT=/data/educ-intract/educ1242/intract_features
# The pre-submission area, whose content-addressed caches are reused so that nothing is downloaded twice: the
# Hugging Face hub cache (snapshots by commit), the uv and pip wheel caches (by hash), the Stanza 1.15.0 models
# (checked against the pinned resources.json), the UDPipe 2 checkout and the extracted 2.17 model archive.
export PRESUB=/data/educ-intract/educ1242/intract_presub
export INTRACT_CODE=$FEAT/code
export INTRACT_WORK_ROOT=$FEAT/work
export INTRACT_ENVS=$FEAT/envs
export INTRACT_MODELS=$FEAT/models
export INTRACT_RESOURCES=$FEAT/resources
export INTRACT_INPUTS=$FEAT/inputs
export INTRACT_SRC=$FEAT/src
export INTRACT_OPT=$FEAT/opt
export INTRACT_LOGS=$FEAT/logs
export INTRACT_RECORDS=$FEAT/records
export INTRACT_LEDGER=$FEAT/jobs.csv

export PATH=/usr/local/bin:/usr/bin:/bin
unset PYTHONPATH PYTHONHOME CONDA_PREFIX CONDA_DEFAULT_ENV VIRTUAL_ENV

for _f in /etc/profile.d/lmod.sh /etc/profile.d/modules.sh; do
  if [ -f "$_f" ]; then source "$_f"; fi
done
unset _f
if ! type module >/dev/null 2>&1; then source /usr/share/lmod/lmod/init/bash; fi

# Content-addressed caches shared with the pre-submission strands. A model is only ever fetched at a full commit
# (jobs/arc/staging.py refuses anything else), so no shared refs/main moves under the earlier strands.
export HF_HOME=$PRESUB/cache/hf
export HF_HUB_CACHE=$HF_HOME/hub
export HF_HUB_DISABLE_TELEMETRY=1
export UV_CACHE_DIR=$PRESUB/cache/uv
export PIP_CACHE_DIR=$PRESUB/cache/pip
export STANZA_RESOURCES_DIR=$PRESUB/cache/stanza
export INTRACT_UDPIPE_SRC=$PRESUB/src/udpipe2
export INTRACT_UDPIPE_MODELS=$PRESUB/data/udpipe2/udpipe2-ud-2.17-251125
# Caches that are not content-addressed stay in this pipeline's own area.
export XDG_CACHE_HOME=$FEAT/cache/xdg
export XDG_DATA_HOME=$FEAT/cache/xdg-data
export TORCH_HOME=$FEAT/cache/torch
export TFHUB_CACHE_DIR=$FEAT/cache/tfhub
export MPLCONFIGDIR=$FEAT/cache/mpl
export KERAS_HOME=$FEAT/cache/keras
export TRITON_CACHE_DIR=$FEAT/cache/triton
export CUDA_CACHE_PATH=$FEAT/cache/nv
export TMPDIR=$FEAT/tmp/${SLURM_JOB_ID:-interactive}_${SLURM_ARRAY_TASK_ID:-0}
mkdir -p "$XDG_CACHE_HOME" "$XDG_DATA_HOME" "$TORCH_HOME" "$TFHUB_CACHE_DIR" "$MPLCONFIGDIR" "$KERAS_HOME" \
         "$TRITON_CACHE_DIR" "$CUDA_CACHE_PATH" "$TMPDIR" "$INTRACT_LOGS"

# Third-party code checkouts and the eSpeak NG build (j0_build). coref_corpipe.toml reads INTRACT_CORPIPE_SRC.
export INTRACT_CORPIPE_SRC=$INTRACT_SRC/crac2026-corpipe
export INTRACT_METRICX_SRC=$INTRACT_SRC/metricx
# supplementary.qmd S3: "eSpeak NG 1.52.0 phones, through phonemizer 3.4.0". phonemizer finds the library through
# PHONEMIZER_ESPEAK_LIBRARY, and the library its data through ESPEAK_DATA_PATH.
export INTRACT_ESPEAK=$INTRACT_OPT/espeak-ng-1.52.0
if [ -e "$INTRACT_ESPEAK/lib/libespeak-ng.so" ]; then
  export PHONEMIZER_ESPEAK_LIBRARY=$INTRACT_ESPEAK/lib/libespeak-ng.so
  export ESPEAK_DATA_PATH=$INTRACT_ESPEAK/share/espeak-ng-data
  export PATH=$INTRACT_ESPEAK/bin:$PATH
fi

# A job submitted from the home directory starts there, and anything written to the working directory would land
# under the nearly full home quota, so such a job moves to the project area. Every script uses absolute paths.
_home=${HOME:-$(getent passwd "$(id -u)" | cut -d: -f6)}
if [ "$PWD" = "$_home" ]; then cd "$FEAT"; fi
unset _home

# Offline after staging. j0_build exports HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 before sourcing this file.
export HF_HUB_OFFLINE=${HF_HUB_OFFLINE:-1}
export TRANSFORMERS_OFFLINE=${TRANSFORMERS_OFFLINE:-1}

# Determinism (DESIGN.md: "Language models and encoders run in fp32 with TF32 off"); each stage also sets these
# in code. Deterministic cuBLAS workspace, no TF32 anywhere, TensorFlow op determinism for UDPipe 2, and minnt's own
# TF32 switch, which minnt.startup() turns on unless told otherwise (coref_corpipe.toml).
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export NVIDIA_TF32_OVERRIDE=0
export TF_DETERMINISTIC_OPS=1
export TF_ENABLE_ONEDNN_OPTS=0
export MINNT_ALLOW_TF32=0
# PYTHONHASHSEED reaches only Python processes started without -I or -E. Every pipeline process runs with -I (the
# stages, the UDPipe server and phonemizer, as in the pre-submission jobs) or -E (the stand-in builder), so string
# hashing is randomised in all of them and no output may depend on set or dict order of strings. The smoke-against-
# full row comparison and the reruns check exactly that (compare_runs.py). The value serves interactive tools only.
export PYTHONHASHSEED=0

# The job's temporary folder belongs to the script that sourced this file first in the job (the sbatch script, or
# run_stage.sh when a template execs it); scripts it calls inherit INTRACT_TOPLEVEL and leave the folder alone, so
# the combined GPU job's lane never loses its files to a finishing stage. The owner calls intract_tmp_cleanup on
# exit; submit_chain.sh sweeps the folders of jobs that ended without it (killed at their time limit). Outside a
# Slurm job nothing is removed, since interactive sessions share $FEAT/tmp/interactive_0.
if [ -z "${INTRACT_TOPLEVEL:-}" ]; then export INTRACT_TOPLEVEL=$$; fi
intract_tmp_cleanup() {
  if [ -n "${SLURM_JOB_ID:-}" ] && [ "${INTRACT_TOPLEVEL:-}" = "$$" ] && [ -d "${TMPDIR:-}" ]; then
    case "$TMPDIR" in "$FEAT"/tmp/?*) rm -rf "$TMPDIR" ;; esac
  fi
  return 0
}

# The code version every timing record carries (cli.py reads INTRACT_CODE_COMMIT): the commit when the code root
# is a git work tree, otherwise a SHA-256 over the code's files, since the root is usually synced without .git.
if [ -z "${INTRACT_CODE_COMMIT:-}" ]; then
  if git -C "$INTRACT_CODE" rev-parse HEAD >/dev/null 2>&1; then
    INTRACT_CODE_COMMIT=$(git -C "$INTRACT_CODE" rev-parse HEAD)
    if [ -n "$(git -C "$INTRACT_CODE" status --porcelain 2>/dev/null)" ]; then
      INTRACT_CODE_COMMIT="$INTRACT_CODE_COMMIT-dirty"
    fi
  elif [ -d "$INTRACT_CODE/src" ]; then
    # Only the folders present are hashed, and a failure leaves the value "unknown" instead of stopping a caller
    # that runs with set -e and pipefail.
    _items=()
    for _p in pyproject.toml src config jobs envs standin; do
      if [ -e "$INTRACT_CODE/$_p" ]; then _items+=("$_p"); fi
    done
    INTRACT_CODE_COMMIT="tree-sha256:$( (cd "$INTRACT_CODE" && find "${_items[@]}" -type f ! -path '*/__pycache__/*' \
      ! -path '*.egg-info/*' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16) || echo unknown)"
    unset _items _p
  fi
  export INTRACT_CODE_COMMIT
fi

# The Python module each environment was built on (envs/README.md): metricx needs CPython 3.11, because
# sentencepiece 0.1.99 and tokenizers 0.13.x publish no 3.12 wheels.
intract_python_module() {
  case "$1" in
    metricx) echo Python/3.11.5-GCCcore-13.2.0 ;;
    *) echo Python/3.12.3-GCCcore-13.3.0 ;;
  esac
}

# Activate one environment; calling it again switches environments within a job (the combined GPU job does).
intract_env() {
  local name=$1 had_u=0
  case $- in *u*) had_u=1; set +u ;; esac
  if [ -n "${VIRTUAL_ENV:-}" ] && type deactivate >/dev/null 2>&1; then deactivate; fi
  module purge
  module load "$(intract_python_module "$name")"
  if [ ! -x "$INTRACT_ENVS/$name/bin/python" ]; then
    echo "environment $name is not built: run jobs/arc/j0_build.sbatch first" >&2
    [ $had_u = 1 ] && set -u
    return 3
  fi
  source "$INTRACT_ENVS/$name/bin/activate"
  echo "=== env $name $(date -u +%Y-%m-%dT%H:%M:%SZ) job=${SLURM_JOB_ID:-none} task=${SLURM_ARRAY_TASK_ID:-none}" \
       "node=$(hostname) code=${INTRACT_CODE_COMMIT:-unknown}"
  echo "python=$(python -c 'import sys; print(sys.version.split()[0])') venv=$VIRTUAL_ENV"
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
  fi
  python -I -c 'import importlib.metadata as m
for p in ("torch", "transformers", "tensorflow", "tf-keras", "stanza", "wtpsplit", "numpy", "huggingface-hub",
          "ufal.udpipe", "minnt", "udapi", "datasets", "sentencepiece", "safetensors", "phonemizer", "wordfreq"):
    try: print(p, m.version(p))
    except m.PackageNotFoundError: pass' || true
  [ $had_u = 1 ] && set -u
  return 0
}

if [ -n "${1:-}" ]; then
  intract_env "$1"
else
  module purge
  module load "$(intract_python_module core)"
fi

case $_intract_opts in *u*) set -u ;; esac
unset _intract_opts
