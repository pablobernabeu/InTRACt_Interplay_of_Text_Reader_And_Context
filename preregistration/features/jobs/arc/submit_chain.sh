#!/bin/bash
# Submit the English dry run on the public stand-in: the smoke chain (the smallest 1 per cent of K, 406 texts), then
# the full chain (40,559 texts). The full chain starts once the smoke run's inputs and its GPU stages have succeeded
# (afterok); it does not wait for the smoke run's CPU feature stages, so the full GPU job joins the L40S queue hours
# earlier. Each run's aggregate_timing job depends afterany on that run's jobs, so a run that fails part way still
# reports what it measured. With both runs, compare_runs.sbatch then sets the smoke rows against the full run's
# (DESIGN.md, Determinism), and gpu_bf16.sbatch runs the P08 bf16 check on a finished fp32 run; neither gates
# anything. Before anything is submitted, budget_guard.py checks the L40S GPU-hours requested against --cap, and
# every submitted job gets one row in the ledger, $INTRACT_LEDGER, with the pre-submission ledger's columns.
#
# Usage, on an ARC login node:
#   bash submit_chain.sh --cap HOURS [--mode combined|separate] [--runs smoke,full] [--build] [--bf16 RUN|none]
#                        [--after JOBID] [--gpu-partition short|medium] [--qe-env NAME] [--dry-run]
#   --cap            L40S GPU-hours the account may be committed to after this submission (budget_guard.py)
#   --mode           combined (default): one L40S allocation per run runs every GPU stage, Stanza on its CPUs;
#                    separate: one job per stage, GPU stages each in their own allocation
#   --build          submit j0_build first and make the chain depend on it; j0_metricx follows j0_build, and
#                    nothing waits for it
#   --bf16 RUN       the fp32 run the bf16 check reads (default smoke when the smoke run is submitted); none skips it
#   --after JOBID    make the first job depend afterok on JOBID (for instance a running j0_build)
#   --qe-env NAME    the environment qe_metricx runs in (default core, the one qe_metricx.py declares and the
#                    port is validated in; see jobs/arc/README.md)
#   --dry-run        print the plan and the budget check, submit nothing, write no ledger row
set -eo pipefail
CAP=; MODE=combined; RUNS=smoke,full; BUILD=0; AFTER=; GPU_PARTITION=short; QE_ENV=core; BF16=default
DRY_RUN=${DRY_RUN:-0}
while [ $# -gt 0 ]; do
  case "$1" in
    --cap) CAP=$2; shift 2 ;;
    --mode) MODE=$2; shift 2 ;;
    --runs) RUNS=$2; shift 2 ;;
    --build) BUILD=1; shift ;;
    --bf16) BF16=$2; shift 2 ;;
    --after) AFTER=$2; shift 2 ;;
    --gpu-partition) GPU_PARTITION=$2; shift 2 ;;
    --qe-env) QE_ENV=$2; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "submit_chain.sh: unknown argument $1" >&2; exit 2 ;;
  esac
done
[ -n "$CAP" ] || { echo "submit_chain.sh: --cap is required (L40S GPU-hours)" >&2; exit 2; }
case "$MODE" in combined|separate) ;; *) echo "--mode must be combined or separate" >&2; exit 2 ;; esac

source /data/educ-intract/educ1242/intract_features/code/jobs/arc/env.sh ""
set -u
J=$INTRACT_CODE/jobs/arc
LEDGER=$INTRACT_LEDGER
NSHARDS=$(python -I -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["shards"]["default"])' \
  "$INTRACT_CODE/config/pipeline.toml")
ARRAY=0-$((NSHARDS - 1))
IFS=, read -r -a run_list <<< "$RUNS"
for run in "${run_list[@]}"; do
  case "$run" in smoke|full) ;; *) echo "--runs takes smoke and full" >&2; exit 2 ;; esac
done
if [ "$BF16" = default ]; then
  BF16=none
  for run in "${run_list[@]}"; do [ "$run" = smoke ] && BF16=smoke; done
fi
if [ "$BF16" != none ] && [[ ",$RUNS," != *",$BF16,"* ]]; then
  echo "--bf16 $BF16 names a run that is not submitted here (--runs $RUNS)" >&2; exit 2
fi

# --- prerequisites (jobs/arc/README.md) -------------------------------------------------------------------------
# The documents stage's catalogue lock (documents.toml [lock], on_missing_manifest = "refuse") needs both files; a
# missing one would otherwise surface only after the job's wait in the queue.
missing=()
[ -s "$INTRACT_INPUTS/en-us/structure.tsv" ] || missing+=("$INTRACT_INPUTS/en-us/structure.tsv (the structure table)")
for f in manifest.json extraction_record.json; do
  [ -s "$FEAT/story_texts/data/$f" ] || missing+=("$FEAT/story_texts/data/$f (the catalogue lock's checksums)")
done
if [ ${#missing[@]} -gt 0 ]; then
  printf 'submit_chain.sh: missing prerequisite: %s\n' "${missing[@]}" >&2
  exit 3
fi
mkdir -p "$INTRACT_LOGS"

# --- temporary folders of jobs that are gone ---------------------------------------------------------------------
# A job removes its own $FEAT/tmp/<job>_<task> on exit (env.sh, intract_tmp_cleanup), but one killed at its time limit
# cannot, so the folders of jobs that no longer appear in squeue (on any cluster) are removed here. Nothing is removed
# unless squeue answered, since an empty answer from a failed call would look like no job running.
if [ "$DRY_RUN" != 1 ] && [ -d "$FEAT/tmp" ] && command -v squeue >/dev/null 2>&1 \
   && live_jobs=$(squeue -M all -h -u "$(id -un)" -o %A 2>/dev/null); then
  live=" $(echo "$live_jobs" | tr '\n' ' ') "
  for d in "$FEAT"/tmp/*_*; do
    [ -d "$d" ] || continue
    jid=$(basename "$d"); jid=${jid%%_*}
    case "$jid" in ''|*[!0-9]*) continue ;; esac
    [[ "$live" == *" $jid "* ]] || rm -rf "$d"
  done
fi

# --- time limits ------------------------------------------------------------------------------------------------
# Full-run limits come from the measured pre-submission rates with a margin (each template's header says which);
# smoke limits cover the 3-7 minute cold imports and model loading that dominate 406 texts, and the probes.
declare -A T_SMOKE=([documents]=00:20:00 [sat]=00:45:00 [seg_check]=00:20:00 [parse_stanza]=00:45:00
  [parse_udpipe]=01:00:00 [features_gramlex]=00:45:00 [features_discourse]=01:00:00 [surprisal_goldfish]=00:45:00
  [surprisal_xglm]=01:00:00 [encode_e5]=00:45:00 [encode_bgem3]=00:45:00 [coref_corpipe]=01:00:00
  [qe_metricx]=01:00:00 [aggregate_timing]=00:15:00 [j1_standin]=00:45:00 [gpu_combined]=04:00:00
  [gpu_bf16]=02:00:00 [compare_runs]=00:30:00 [j0_build]=08:00:00 [j0_metricx]=02:00:00)
declare -A T_FULL=([documents]=01:00:00 [sat]=01:30:00 [seg_check]=01:00:00 [parse_stanza]=06:00:00
  [parse_udpipe]=03:00:00 [features_gramlex]=04:00:00 [features_discourse]=06:00:00 [surprisal_goldfish]=02:00:00
  [surprisal_xglm]=08:00:00 [encode_e5]=01:30:00 [encode_bgem3]=01:30:00 [coref_corpipe]=06:00:00
  [qe_metricx]=02:00:00 [aggregate_timing]=00:30:00 [j1_standin]=02:00:00 [gpu_combined]=12:00:00
  [gpu_bf16]=04:00:00 [compare_runs]=01:00:00 [j0_build]=08:00:00 [j0_metricx]=02:00:00)
# qe_metricx is timed on a slice of the 40,055 English-German pairs in the smoke run.
QE_SMOKE_LIMIT=400

hours() {  # a Slurm time limit ([D-]HH:MM:SS, MM:SS or MM) in hours
  awk -v t="$1" 'BEGIN {
    d = 0
    if (index(t, "-")) { split(t, a, "-"); d = a[1]; n = split(a[2], p, ":"); h = p[1]; m = (n > 1) ? p[2] : 0; s = (n > 2) ? p[3] : 0 }
    else { n = split(t, p, ":"); if (n == 3) { h = p[1]; m = p[2]; s = p[3] } else if (n == 2) { h = 0; m = p[1]; s = p[2] } else { h = 0; m = p[1]; s = 0 } }
    printf "%.6f\n", d * 24 + h + m / 60 + s / 3600 }'
}
limit_for() {  # run stage
  if [ "$1" = smoke ]; then echo "${T_SMOKE[$2]}"; else echo "${T_FULL[$2]}"; fi
}

# --- the plan ---------------------------------------------------------------------------------------------------
# Each planned job: name|run|template|gpu (1 or 0)|array (0 or 1)|dependency names (space separated)|afterany|args
PLAN=()
plan() { PLAN+=("$1|$2|$3|$4|$5|$6|$7|$8"); }
first_dep=""
if [ "$BUILD" = 1 ]; then
  plan j0 - j0_build.sbatch 0 0 "" 0 ""
  plan j0_metricx - j0_metricx.sbatch 0 0 "j0" 0 ""
  first_dep=j0
fi
prev_gate=$first_dep
declare -A GPU_JOBS
for run in "${run_list[@]}"; do
  W=$INTRACT_WORK_ROOT/$run
  qe_limit=""; [ "$run" = smoke ] && qe_limit=$QE_SMOKE_LIMIT
  plan "$run.j1" "$run" j1_standin.sbatch 0 0 "$prev_gate" 0 "$run $qe_limit"
  plan "$run.documents" "$run" documents.sbatch 0 1 "$run.j1" 0 "$run --input $W/_input/en-us/stories.csv.xz"
  if [ "$MODE" = combined ]; then
    gpu_args="$run --qe-env $QE_ENV"; [ -n "$qe_limit" ] && gpu_args="$gpu_args --qe-limit $qe_limit"
    plan "$run.gpu" "$run" gpu_combined.sbatch 1 0 "$run.documents" 0 "$gpu_args"
    plan "$run.features_gramlex" "$run" features_gramlex.sbatch 0 1 "$run.gpu" 0 "$run"
    plan "$run.features_discourse" "$run" features_discourse.sbatch 0 1 "$run.gpu" 0 "$run"
    gpu_jobs="$run.gpu"
    gate="$run.j1 $run.documents $run.gpu $run.features_gramlex $run.features_discourse"
  else
    qe_args="$run --lang de-de --input $W/_input/qe_pairs_de-de.jsonl.gz --env $QE_ENV"
    [ -n "$qe_limit" ] && qe_args="$qe_args --limit $qe_limit"
    plan "$run.sat" "$run" sat.sbatch 1 0 "$run.documents" 0 "$run"
    # One task: seg_check's report covers every shard and only its shard 0 run computes it (stages/seg_check.py).
    plan "$run.seg_check" "$run" seg_check.sbatch 0 0 "$run.sat" 0 "$run"
    plan "$run.parse_stanza" "$run" parse_stanza.sbatch 0 1 "$run.sat" 0 "$run"
    plan "$run.parse_udpipe" "$run" parse_udpipe.sbatch 1 0 "$run.sat" 0 "$run"
    plan "$run.encode_e5" "$run" encode_e5.sbatch 1 0 "$run.sat" 0 "$run"
    plan "$run.encode_bgem3" "$run" encode_bgem3.sbatch 1 0 "$run.sat" 0 "$run"
    plan "$run.surprisal_goldfish" "$run" surprisal_goldfish.sbatch 1 0 "$run.documents" 0 "$run"
    plan "$run.surprisal_xglm" "$run" surprisal_xglm.sbatch 1 0 "$run.documents" 0 "$run"
    plan "$run.coref_corpipe" "$run" coref_corpipe.sbatch 1 0 "$run.parse_stanza" 0 "$run"
    plan "$run.qe_metricx" "$run" qe_metricx.sbatch 1 0 "$run.j1" 0 "$qe_args"
    plan "$run.features_gramlex" "$run" features_gramlex.sbatch 0 1 "$run.parse_stanza $run.parse_udpipe" 0 "$run"
    plan "$run.features_discourse" "$run" features_discourse.sbatch 0 1 "$run.parse_stanza" 0 "$run"
    gpu_jobs="$run.sat $run.parse_udpipe $run.encode_e5 $run.encode_bgem3 $run.surprisal_goldfish"
    gpu_jobs="$gpu_jobs $run.surprisal_xglm $run.coref_corpipe $run.qe_metricx"
    gate="$run.j1 $run.documents $run.seg_check $run.parse_stanza $gpu_jobs $run.features_gramlex"
    gate="$gate $run.features_discourse"
  fi
  GPU_JOBS[$run]=$gpu_jobs
  plan "$run.aggregate" "$run" aggregate_timing.sbatch 0 0 "$gate" 1 "$run"
  # The next run waits for this run's inputs and GPU stages only (see the header).
  prev_gate="$run.j1 $run.documents $gpu_jobs"
  last_gate=$gate
done
if [ "$BF16" != none ]; then
  plan "$BF16.bf16" "$BF16" gpu_bf16.sbatch 1 0 "${GPU_JOBS[$BF16]}" 0 "$BF16 --qe-env $QE_ENV"
fi
if [[ ",$RUNS," == *",smoke,"* ]] && [[ ",$RUNS," == *",full,"* ]]; then
  plan "full.compare" full compare_runs.sbatch 0 0 "$last_gate smoke.aggregate" 1 "smoke full"
fi

# --- budget -----------------------------------------------------------------------------------------------------
total=0
for item in "${PLAN[@]}"; do
  IFS='|' read -r name run tpl gpu array deps anyok args <<< "$item"
  stage=${tpl%.sbatch}
  if [ "$gpu" = 1 ]; then
    lim=$(limit_for "$run" "$stage")
    total=$(awk -v a="$total" -v b="$(hours "$lim")" 'BEGIN { printf "%.6f\n", a + b }')
  fi
done
echo "plan: ${#PLAN[@]} jobs ($MODE mode, runs $RUNS, bf16 check $BF16), L40S GPU-hours requested $total, cap $CAP"
ledger_args=(--ledger "$LEDGER")
[ -s "$LEDGER" ] || ledger_args=(--ledger "$LEDGER" --no-sacct)
python -I "$J/budget_guard.py" check --cap "$CAP" --add "$total" "${ledger_args[@]}"

# --- submission -------------------------------------------------------------------------------------------------
csvq() { local s=${1//\"/\"\"}; printf '"%s"' "$s"; }
if [ ! -s "$LEDGER" ] && [ "$DRY_RUN" != 1 ]; then
  echo "job_id,cluster,strand,purpose,gres,walltime,gpu_hours_requested,submitted_utc,outputs,postprocess_command" \
    > "$LEDGER"
fi
declare -A JID
fake=900000
sub() {  # name run template gpu array deps afterany args
  local name=$1 run=$2 tpl=$3 gpu=$4 array=$5 deps=$6 anyok=$7 args=$8 stage lim opts=() dep_ids=() d
  stage=${tpl%.sbatch}
  lim=$(limit_for "$run" "$stage")
  local job_name="if-$run-$stage"; [ "$run" = - ] && job_name="if-$stage"
  opts=(--parsable --job-name="$job_name" --time="$lim")
  if [ "$gpu" = 1 ]; then opts+=(--partition="$GPU_PARTITION"); fi
  if [ "$array" = 1 ]; then opts+=(--array="$ARRAY"); fi
  for d in $deps; do dep_ids+=("${JID[$d]}"); done
  if [ ${#dep_ids[@]} -eq 0 ] && [ -n "$AFTER" ] && [ "$name" != j0 ]; then dep_ids=("$AFTER"); fi
  local depspec=""
  if [ ${#dep_ids[@]} -gt 0 ]; then
    local kind=afterok; [ "$anyok" = 1 ] && kind=afterany
    depspec="$kind:$(IFS=:; echo "${dep_ids[*]}")"
    # A job whose afterok dependency failed is cancelled instead of pending for ever (the pre-submission TU-6 and
    # EM-6 sat in DependencyNeverSatisfied), which also lets the run's afterany aggregate job start.
    opts+=(--dependency="$depspec" --kill-on-invalid-dep=yes)
  fi
  local gres=none gpuh=0 tasks=1
  [ "$array" = 1 ] && tasks=$NSHARDS
  if [ "$gpu" = 1 ]; then
    gres=gpu:l40s:1
    gpuh=$(awk -v h="$(hours "$lim")" -v n="$tasks" 'BEGIN { printf "%.3f\n", h * n }')
  fi
  local purpose="dry run $run: $stage"
  [ "$run" = - ] && purpose="$stage"
  [ "$array" = 1 ] && purpose="$purpose (array $ARRAY)"
  [ -n "$depspec" ] && purpose="$purpose; $depspec"
  local outputs="$INTRACT_WORK_ROOT/$run/<lang>/<artefact>/; _timing/$stage-shard-*"
  local post=none
  case "$stage" in
    aggregate_timing) post="cat $INTRACT_WORK_ROOT/$run/_summary/timing.tsv" ;;
    compare_runs) outputs="$INTRACT_WORK_ROOT/full/_summary/rows_vs_smoke.json"; post="cat $outputs" ;;
    gpu_bf16) outputs="$INTRACT_WORK_ROOT/${run}_bf16/"; post="cat $INTRACT_WORK_ROOT/${run}_bf16/_summary/bf16_check.json" ;;
    j0_build) outputs="$INTRACT_ENVS; $INTRACT_MODELS; $INTRACT_RECORDS/staging"; purpose="J0 build" ;;
    j0_metricx) outputs="$INTRACT_ENVS/metricx; $INTRACT_RECORDS/envs/metricx.freeze.txt" ;;
  esac
  local jid cluster out
  # shellcheck disable=SC2086
  if [ "$DRY_RUN" = 1 ]; then
    fake=$((fake + 1)); jid=$fake; cluster=htc
    echo "DRY sbatch ${opts[*]} $J/$tpl $args  [gpu_h=$gpuh]"
  else
    out=$(sbatch "${opts[@]}" "$J/$tpl" $args)
    jid=${out%%;*}; cluster=${out#*;}; [ "$cluster" = "$out" ] && cluster=htc
    local row
    row="$jid,$cluster,intract_features,$(csvq "$purpose"),$gres,$lim,$gpuh,$(date -u +%Y-%m-%dT%H:%M:%SZ),$(csvq "$outputs"),$(csvq "$post")"
    ( flock 9; echo "$row" >> "$LEDGER" ) 9>>"$LEDGER.lock"
    echo "SUBMITTED $row"
  fi
  JID[$name]=$jid
}
for item in "${PLAN[@]}"; do
  IFS='|' read -r name run tpl gpu array deps anyok args <<< "$item"
  sub "$name" "$run" "$tpl" "$gpu" "$array" "$deps" "$anyok" "$args"
done
echo "submitted: $(for k in "${!JID[@]}"; do printf '%s=%s ' "$k" "${JID[$k]}"; done)"
