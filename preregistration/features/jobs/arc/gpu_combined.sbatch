#!/bin/bash
#SBATCH --job-name=if_gpu_combined
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=120G
#SBATCH --time=12:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Every GPU stage of one run in one L40S allocation, so the run waits in the L40S queue once (the pre-submission
# L40S jobs waited 29 to 30 hours each). Stanza and seg_check run on the allocation's CPUs while the GPU works, so
# CorPipe, which reads the Stanza parse, needs no second allocation either. The request is one GPU's share of an
# L40S node (64 cores, 503 GB, four GPUs: sinfo, 3 November 2026).
#
#   A    sat                                       (GPU; its segments feed everything below)
#   lane parse_stanza, seg_check                    (CPU, in the background, one process per shard, GPU hidden)
#   B    parse_udpipe encode_e5 encode_bgem3 surprisal_goldfish qe_metricx      (GPU, while the lane runs)
#   C    coref_corpipe                              (GPU, once the lane's Stanza parse is complete)
#   D    surprisal_xglm                             (GPU; longest and last, so a time-out loses the least)
#
# Usage: sbatch gpu_combined.sbatch <run> [--qe-input PATH] [--qe-limit N] [--qe-env NAME]
# Every stage skips shards finished before by the same code (run_stage.sh), so a resubmission after a time-out
# resumes. Each stage also runs its cold and warm one-document probes (run_stage.sh), about 2 to 8 minutes a stage,
# which let aggregate_timing separate loading from compute. On the full run the expectation is about 10.5 hours
# (sat 0.5; B about 3; C about 2; D about 3.5, untimed models included; probes about 1); the smoke run about 2.5.
set -eo pipefail
RUN=${1:?run}; shift
QE_INPUT=; QE_LIMIT=; QE_ENV=
while [ $# -gt 0 ]; do
  case "$1" in
    --qe-input) QE_INPUT=$2; shift 2 ;;
    --qe-limit) QE_LIMIT=$2; shift 2 ;;
    --qe-env) QE_ENV=$2; shift 2 ;;
    *) echo "gpu_combined: unknown argument $1" >&2; exit 2 ;;
  esac
done
CODE=/data/educ-intract/educ1242/intract_features/code
RUNNER="$CODE/jobs/arc/run_stage.sh"
source "$CODE/jobs/arc/env.sh" core
trap intract_tmp_cleanup EXIT
set -u
WORK=$INTRACT_WORK_ROOT/$RUN
NSHARDS=$(python -I -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["shards"]["default"])' \
  "$CODE/config/pipeline.toml")
QE_INPUT=${QE_INPUT:-$WORK/_input/qe_pairs_de-de.jsonl.gz}
LANE_LOGS=$INTRACT_LOGS/lane_${SLURM_JOB_ID:-interactive}
mkdir -p "$LANE_LOGS"

# A failed stage does not stop the job: the stages that do not need its output still run and are timed, and the
# job exits non-zero at the end, so nothing downstream of it starts (afterok).
failed=()
gpu_stage() {  # stage [extra run_stage.sh arguments]
  local stage=$1; shift
  echo "#### $stage $(date -u +%FT%TZ)"
  bash "$RUNNER" "$stage" "$RUN" "$@" || { failed+=("$stage"); echo "#### $stage FAILED"; return 1; }
}
qe_args=(--lang de-de --input "$QE_INPUT")
[ -n "$QE_LIMIT" ] && qe_args+=(--limit "$QE_LIMIT")
[ -n "$QE_ENV" ] && qe_args+=(--env "$QE_ENV")

if gpu_stage sat; then
  echo "#### lane: parse_stanza and seg_check, one process per shard $(date -u +%FT%TZ)"
  pids=()
  # Each lane process is single-threaded (parse_stanza.toml sets one torch thread), so its side record counts one
  # CPU, the share a CPU array task of its own would request, not the allocation's 16.
  for s in $(seq 0 $((NSHARDS - 1))); do
    CUDA_VISIBLE_DEVICES="" INTRACT_STAGE_CPUS=1 bash "$RUNNER" parse_stanza "$RUN" --shards "$s" \
      > "$LANE_LOGS/parse_stanza_$s.log" 2>&1 &
    pids+=($!)
  done
  CUDA_VISIBLE_DEVICES="" INTRACT_STAGE_CPUS=1 bash "$RUNNER" seg_check "$RUN" > "$LANE_LOGS/seg_check.log" 2>&1 &
  pids+=($!)

  gpu_stage parse_udpipe || true
  gpu_stage encode_e5 || true
  gpu_stage encode_bgem3 || true
  gpu_stage surprisal_goldfish || true
  gpu_stage qe_metricx "${qe_args[@]}" || true

  echo "#### waiting for the lane $(date -u +%FT%TZ)"
  lane_failed=0
  for pid in "${pids[@]}"; do
    wait "$pid" || lane_failed=1
  done
  tail -n 3 "$LANE_LOGS"/*.log || true
  if [ "$lane_failed" = 1 ]; then
    failed+=(lane)
    echo "#### a lane process failed (logs in $LANE_LOGS); coref_corpipe needs the Stanza parse and is skipped"
  else
    gpu_stage coref_corpipe || true
  fi
else
  echo "#### sat failed: only the stages that read documents or the pairs alone run"
  gpu_stage surprisal_goldfish || true
  gpu_stage qe_metricx "${qe_args[@]}" || true
fi
gpu_stage surprisal_xglm || true

if [ ${#failed[@]} -gt 0 ]; then
  echo "gpu_combined $RUN finished with failures: ${failed[*]} $(date -u +%FT%TZ)"
  exit 4
fi
echo "gpu_combined $RUN done $(date -u +%FT%TZ)"
