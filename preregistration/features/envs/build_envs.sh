#!/bin/bash
# Build the hash-locked environments of the feature pipeline on ARC (DESIGN.md, Environments).
# Usage, inside a job (j0_build.sbatch) or an interactive session on a compute node:
#     bash /data/educ-intract/educ1242/intract_features/code/envs/build_envs.sh [core] [udpipe] [corpipe] [metricx]
# With no names it builds all four. Each environment is built from scratch from envs/<name>.lock with
# --require-hashes, so a rebuild installs exactly the same files; the intract_features package itself is then
# installed editable, without dependencies and without build isolation (setuptools comes from the lock). A freeze
# record and an import check are written for each environment.
# An environment already built from the same lock, interpreter module and uv is kept (its stamp file says so, and
# its import check passes again), so a resubmitted J0 does not spend half an hour per environment rebuilding what is
# there; FORCE=1 rebuilds it anyway.
# Why a bootstrap uv: ARC's uv module is 0.2.30, too old for these locks (pre-submission strand translated_union).
set -eo pipefail
export HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0
# Pass an empty argument: a sourced file sees the caller's positional parameters otherwise.
source /data/educ-intract/educ1242/intract_features/code/jobs/arc/env.sh ""
set -u

ENVS=("$@")
[ ${#ENVS[@]} -eq 0 ] && ENVS=(core udpipe corpipe metricx)
LOCKS=$INTRACT_CODE/envs
RECORD_DIR=$INTRACT_RECORDS/envs
mkdir -p "$INTRACT_ENVS" "$RECORD_DIR"

# uv 0.12.24, the version the pre-submission environments were synced with; the hash is PyPI's digest of the
# manylinux x86_64 wheel (https://pypi.org/pypi/uv/0.12.24/json, read 3 November 2026).
UV_VERSION=0.12.24
UV_WHEEL_SHA256=e47005957dca320272ad68960b591b854b6bf0c3288368efb096d9ccd06b8404
UVENV=$INTRACT_ENVS/_uv
if [ ! -x "$UVENV/bin/uv" ] || [ "$("$UVENV/bin/uv" --version | cut -d' ' -f2)" != "$UV_VERSION" ]; then
  rm -rf "$UVENV"
  python -m venv "$UVENV"
  req=$(mktemp "$TMPDIR/uv-req.XXXXXX")
  printf 'uv==%s --hash=sha256:%s\n' "$UV_VERSION" "$UV_WHEEL_SHA256" > "$req"
  "$UVENV/bin/pip" install --no-input --disable-pip-version-check --require-hashes --only-binary=:all: -r "$req"
  rm -f "$req"
fi
UV=$UVENV/bin/uv
"$UV" --version
# Hard links between the shared uv cache and the environments: both sit on /data/educ-intract, and copying the
# multi-gigabyte CUDA wheels onto NFS took about 30 minutes per environment (pre-submission error model).
export UV_NO_CONFIG=1 UV_LINK_MODE=hardlink

# The indexes each lock was compiled against (envs/README.md). torch comes from the PyTorch cu126 index for core
# and corpipe, and every other package from PyPI; unsafe-best-match is the strategy the locks were compiled with.
index_args() {
  case "$1" in
    core|corpipe) echo --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cu126 \
                       --index-strategy unsafe-best-match ;;
    *) echo --index-url https://pypi.org/simple ;;
  esac
}

# What each environment must import, as a smoke test of the build (the stages import more, lazily).
smoke_imports() {
  case "$1" in
    core) echo "torch transformers wtpsplit stanza numpy scipy safetensors sentencepiece wordfreq phonemizer pyarrow huggingface_hub intract_features" ;;
    udpipe) echo "tensorflow tf_keras transformers ufal.udpipe ufal.chu_liu_edmonds numpy intract_features" ;;
    corpipe) echo "torch transformers minnt udapi sentencepiece numpy intract_features" ;;
    metricx) echo "torch transformers datasets sentencepiece safetensors numpy" ;;
  esac
}

# Whether the intract_features package is installed into the environment. Not into metricx: the package asks for
# Python >= 3.12 (pyproject.toml), and that environment runs only the official MetricX-24 code, against which the
# port in reference/metricx_qe.py is validated (qe_metricx.toml [validation]).
installs_package() { [ "$1" != metricx ]; }

import_check() {  # name python
  local mod
  for mod in $(smoke_imports "$1"); do
    "$2" -I -c "import importlib, sys; importlib.import_module(sys.argv[1])" "$mod" || return 1
  done
}

for name in "${ENVS[@]}"; do
  lock=$LOCKS/$name.lock
  [ -s "$lock" ] || { echo "missing $lock"; exit 3; }
  module purge
  module load "$(intract_python_module "$name")"
  py=$(command -v python3)
  lock_sha=$(sha256sum "$lock" | cut -c1-64)
  echo "== $name: $lock_sha $lock; interpreter $py $("$py" -c 'import sys; print(sys.version.split()[0])')"
  dest=$INTRACT_ENVS/$name
  stamp="lock $lock_sha module $(intract_python_module "$name") uv $UV_VERSION"
  if [ "${FORCE:-0}" != 1 ] && [ -x "$dest/bin/python" ] && [ "$(cat "$dest/.intract-build" 2>/dev/null)" = "$stamp" ] \
     && import_check "$name" "$dest/bin/python"; then
    echo "== $name: built before from this lock, kept (FORCE=1 rebuilds)"
    # The editable install is refreshed (offline, seconds), so the package's metadata follows the synced code.
    if installs_package "$name"; then
      "$UV" pip install --python "$dest/bin/python" --no-deps --no-build-isolation --offline -e "$INTRACT_CODE"
    fi
    continue
  fi
  # A virtual environment is not relocatable (its scripts name its own path), so it is rebuilt in place.
  rm -rf "$dest"
  "$UV" venv --python "$py" "$dest"
  # shellcheck disable=SC2046
  "$UV" pip sync --python "$dest/bin/python" --require-hashes $(index_args "$name") "$lock"
  if installs_package "$name"; then
    "$UV" pip install --python "$dest/bin/python" --no-deps --no-build-isolation --offline -e "$INTRACT_CODE"
  fi
  "$UV" pip check --python "$dest/bin/python"
  import_check "$name" "$dest/bin/python"
  {
    echo "# $name built $(date -u +%Y-%m-%dT%H:%M:%SZ) on $(hostname) with $("$UV" --version)"
    echo "# lock $(sha256sum "$lock" | cut -c1-64) envs/$name.lock; module $(intract_python_module "$name")"
    "$UV" pip freeze --python "$dest/bin/python"
    "$dest/bin/python" -I -c 'import sys, importlib.util as u
print("python", sys.version.split()[0])
if u.find_spec("torch"):
    import torch; print("torch", torch.__version__, "cuda", torch.version.cuda, "cudnn", torch.backends.cudnn.version())
if u.find_spec("tensorflow"):
    import tensorflow as tf; print("tensorflow", tf.__version__, tf.sysconfig.get_build_info().get("cuda_version"))'
  } > "$RECORD_DIR/$name.freeze.txt"
  cat "$RECORD_DIR/$name.freeze.txt"
  # Written last, so only a build that passed every check above is ever kept.
  echo "$stamp" > "$dest/.intract-build"
done
echo "build_envs done $(date -u +%FT%TZ): ${ENVS[*]}"
