#!/bin/bash
#SBATCH --job-name=if_gpu_bf16
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --time=02:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# The P08 bf16 check (preregistration.qmd, Timeline: the bf16 step "is taken only if their text means agree with
# those at full precision at r >= .995 on the public benchmark scored before submission"; synthesis 2.4, step 3).
# XGLM-4.5B, CorPipe and MetricX-24 run again in bf16 on the inputs of a finished fp32 run, and compare_runs.py bf16
# sets their text values against the fp32 run's. Nothing in the chain depends on this job, and it decides nothing:
# its record, $INTRACT_WORK_ROOT/<run>_bf16/_summary/bf16_check.json, settles P08.
#
# Usage: sbatch gpu_bf16.sbatch <fp32 run> [--qe-env NAME]
# The bf16 run lives in $INTRACT_WORK_ROOT/<fp32 run>_bf16 and reads the fp32 run's documents, Stanza parse and qe
# pairs through links. Its config differs from the committed one only in the three precision settings, each set with
# run_stage.sh --set in the run's own copy of config/. XGLM keeps check_fraction = 1.0 (surprisal_xglm.toml), so the
# stage also scores fp32 itself and records its own agreement beside the comparison. No probes run (PROBE=0): this
# job measures precision, not cost. On the smoke run (406 texts, 400 pairs) it needs about an hour, most of it loading.
set -eo pipefail
BASE=${1:?the fp32 run, for instance smoke}; shift
QE_ENV=core
while [ $# -gt 0 ]; do
  case "$1" in
    --qe-env) QE_ENV=$2; shift 2 ;;
    *) echo "gpu_bf16: unknown argument $1" >&2; exit 2 ;;
  esac
done
CODE=/data/educ-intract/educ1242/intract_features/code
source "$CODE/jobs/arc/env.sh" core
trap intract_tmp_cleanup EXIT
set -u
RUNNER="$CODE/jobs/arc/run_stage.sh"
B=$INTRACT_WORK_ROOT/$BASE
RUN=${BASE}_bf16
W=$INTRACT_WORK_ROOT/$RUN
QE_INPUT=$B/_input/qe_pairs_de-de.jsonl.gz
for art in documents parses_stanza; do
  [ -d "$B/en-us/$art" ] || { echo "gpu_bf16: $B/en-us/$art is missing; the fp32 run must finish first" >&2; exit 3; }
  mkdir -p "$W/en-us"
  ln -sfn "$B/en-us/$art" "$W/en-us/$art"
done
export PROBE=0

failed=()
bash "$RUNNER" surprisal_xglm "$RUN" --set 'surprisal_xglm.precision.mode="bf16"' || failed+=(surprisal_xglm)
bash "$RUNNER" coref_corpipe "$RUN" --set 'coref_corpipe.runtime.dtype="bfloat16"' || failed+=(coref_corpipe)
bash "$RUNNER" qe_metricx "$RUN" --lang de-de --input "$QE_INPUT" --env "$QE_ENV" \
  --set 'qe_metricx.runtime.dtype="bfloat16"' || failed+=(qe_metricx)

# The comparison's own verdict is in its record; a model below the threshold does not fail the job.
python -I "$CODE/jobs/arc/compare_runs.py" bf16 --base "$B" --other "$W" --out "$W/_summary/bf16_check.json" \
  || echo "gpu_bf16: at least one model is below the threshold or was not compared (see bf16_check.json)"
if [ ${#failed[@]} -gt 0 ]; then
  echo "gpu_bf16 $BASE finished with failures: ${failed[*]} $(date -u +%FT%TZ)"
  exit 4
fi
echo "gpu_bf16 $BASE done $(date -u +%FT%TZ)"
