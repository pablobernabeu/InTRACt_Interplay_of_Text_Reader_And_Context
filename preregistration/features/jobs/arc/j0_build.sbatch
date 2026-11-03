#!/bin/bash
#SBATCH --job-name=if_j0_build
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# J0, the build (CPU, online, public data only): the core, udpipe and corpipe environments, hash-locked; every
# pinned model, code checkout and resource fetched at its full commit and checked by SHA-256; the pickled Goldfish
# and BGE-M3 weights converted to safetensors and checked tensor by tensor; the SimpleStories train shards; eSpeak NG
# 1.52.0 built from its tag (ARC has no module for it); a final offline verification. Every step skips what is
# already in place and verified (build_envs.sh keeps an environment whose lock is unchanged; staging.py checks a
# file before fetching it), so a resubmission after a time-out repeats nothing that finished.
# The metricx environment is built by j0_metricx.sbatch, which nothing waits for, and the optional safetensors copy
# of MetricX-24 (no stage reads it) is converted only on request (staging.py models --include-optional).
# The memory covers the largest conversion here, BGE-M3's 2.3 GB of pickles held twice while it is checked.
set -eo pipefail
CODE=/data/educ-intract/educ1242/intract_features/code
export HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0
source "$CODE/jobs/arc/env.sh" ""
trap intract_tmp_cleanup EXIT
set -u
mkdir -p "$INTRACT_MODELS" "$INTRACT_RESOURCES" "$INTRACT_SRC" "$INTRACT_OPT" "$INTRACT_RECORDS" "$INTRACT_INPUTS"
STAGING="$CODE/jobs/arc/staging.py"

echo "== 1. environments $(date -u +%FT%TZ)"
bash "$CODE/envs/build_envs.sh" core udpipe corpipe

echo "== 2. room for the models $(date -u +%FT%TZ)"
intract_env core
# The models land in the pre-submission hub cache and the converted weights in $INTRACT_MODELS, both on
# /data/educ-intract. The build stops here if the free space reported for $FEAT cannot hold what is still missing,
# with a tenth to spare, instead of failing part way through a 10 GB file. (Whether df reports the project's quota
# or the file system's free space depends on how /data is mounted: UNVERIFIED, so both are logged.)
need=$(python -I "$STAGING" disk-plan)
avail=$(df -B1 --output=avail "$FEAT" | tail -n 1 | tr -d ' ')
df -h "$FEAT" "$PRESUB/cache" || true
echo "still to download and convert: $need bytes; available under $FEAT: $avail bytes"
if [ "$avail" -lt $(( need + need / 10 )) ]; then
  echo "J0: not enough space for the models; free some or raise the quota, then resubmit" >&2
  exit 3
fi

echo "== 3. models: fetch at full commits, verify, convert $(date -u +%FT%TZ)"
python -I "$STAGING" models

echo "== 4. resources $(date -u +%FT%TZ)"
python -I "$STAGING" resources

echo "== 5. SimpleStories train shards (standin.toml pins each one) $(date -u +%FT%TZ)"
# The stand-in sits beside the installed package, so it runs as a module from the code root; -E and -s keep the
# environment's variables and the user site out, as -I would, while letting the code root stay importable.
(cd "$INTRACT_CODE" && python -E -s -m standin.build_standin download --dest "$INTRACT_RESOURCES/simplestories")

echo "== 6. eSpeak NG $(date -u +%FT%TZ)"
eval "$(python -I "$STAGING" espeak-plan)"
if [ ! -x "$ESPEAK_PREFIX/bin/espeak-ng" ]; then
  if [ ! -d "$ESPEAK_SRC/.git" ]; then
    git clone --quiet --branch "$ESPEAK_TAG" --depth 1 "$ESPEAK_REPO" "$ESPEAK_SRC"
  fi
  [ "$(git -C "$ESPEAK_SRC" rev-parse HEAD)" = "$ESPEAK_COMMIT" ] || { echo "eSpeak NG tag is not at $ESPEAK_COMMIT"; exit 3; }
  (
    # A subshell, so the build toolchain's modules do not replace the Python environment of the later steps.
    module purge
    # shellcheck disable=SC2086
    module load $ESPEAK_MODULES
    cd "$ESPEAK_SRC"
    ./autogen.sh
    # shellcheck disable=SC2086
    ./configure --prefix="$ESPEAK_PREFIX" $ESPEAK_CONFIGURE
    make -j "${SLURM_CPUS_PER_TASK:-4}"
    make install
  )
fi
# env.sh exports the library and data paths only when the build exists, so read them again.
source "$CODE/jobs/arc/env.sh" core
python -I "$STAGING" espeak-check

echo "== 7. offline verification of every pin $(date -u +%FT%TZ)"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
intract_env core
python -I "$STAGING" verify
python -I -m intract_features list-stages
df -h "$FEAT" || true
echo "J0 done $(date -u +%FT%TZ); records in $INTRACT_RECORDS"
