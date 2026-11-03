#!/bin/bash
# Run one pipeline stage over its shards on ARC; every stage's sbatch template, the combined GPU job and the bf16
# check call it.
#     bash run_stage.sh <stage> <run> [--lang L] [--env NAME] [--input PATH] [--limit N] [--shards all|I,J,...]
#                       [--set STAGE.TABLE.KEY=VALUE ...]
# <run> names the work folder, $INTRACT_WORK_ROOT/<run> (smoke, full, smoke_bf16). In an array job the shard is the
# array task id; otherwise every shard runs in turn in this allocation, which is how a GPU stage avoids one queue
# wait per shard. The stage's environment is the one its STAGE declares (cli.Stage.env) unless --env names another.
# --set changes a value in this run's copy of config/ only (staging.py run-config), as the bf16 check does.
#
# Resuming (RESUME=1, the default): a shard is skipped only when its timing record was written by this very code
# (INTRACT_CODE_COMMIT, never a dirty or unknown one), its outputs are still there and every input is older than
# the record (staging.py resume-plan), so a resubmission after a time-out repeats nothing that finished and a fix
# upstream reruns what depends on it. RESUME=0 reruns every shard.
#
# Probes (PROBE=1, the default): the invocation that runs shard 0 also runs the stage on one document before the
# shards (the cold probe, which pays the job's cold start) and after them (the warm probe), each in its own work
# folder under <run>/_probe/, reading the run's inputs through links. aggregate_timing uses them to tell fixed
# costs from compute (config/stages/aggregate_timing.toml, [probe] and [split]). A failed probe stops nothing.
#
# Side records: bash's `time` gives the user and system CPU of each shard's whole process tree (the UDPipe server
# and phonemizer included, which cli.py's process_time leaves out), and <work>/_runs/<lang>/<stage>-shard-<i>-of-
# <n>.json records it with the environment that actually ran, the CPUs allocated and whether the process started
# cold (no process of the stage had finished earlier in this job).
set -eo pipefail
STAGE=${1:?stage}; RUN=${2:?run}; shift 2
LANG_=en-us; ENV_OVERRIDE=; INPUT=; LIMIT=; SHARDS=; SETS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --lang) LANG_=$2; shift 2 ;;
    --env) ENV_OVERRIDE=$2; shift 2 ;;
    --input) INPUT=$2; shift 2 ;;
    --limit) LIMIT=$2; shift 2 ;;
    --shards) SHARDS=$2; shift 2 ;;
    --set) SETS+=(--set "$2"); shift 2 ;;
    *) echo "run_stage.sh: unknown argument $1" >&2; exit 2 ;;
  esac
done

source /data/educ-intract/educ1242/intract_features/code/jobs/arc/env.sh core
set -u
WORK=$INTRACT_WORK_ROOT/$RUN
STAGING=$INTRACT_CODE/jobs/arc/staging.py
mkdir -p "$WORK"
# pipeline.toml [shards] default: every stage of a run uses the same number, since artefact names carry it.
NSHARDS=${NSHARDS:-$(python -I -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["shards"]["default"])' \
  "$INTRACT_CODE/config/pipeline.toml")}
# The stage's declaration and the probe settings, read once in core, where every stage module imports.
eval "$(python -I - "$STAGE" "$INTRACT_CODE/config/stages/aggregate_timing.toml" <<'PY'
import shlex
import sys
import tomllib

from intract_features.cli import discover

stage = discover()[sys.argv[1]].STAGE
with open(sys.argv[2], "rb") as fh:
    probe = tomllib.load(fh)["probe"]
print(f"STAGE_ENV={shlex.quote(stage.env)}")
print(f"STAGE_OUTPUTS={shlex.quote(' '.join(stage.outputs))}")
print(f"PROBE_DIR={shlex.quote(probe['dir'])}")
print(f"PROBE_LIMIT={int(probe['limit'])}")
print(f"PROBE_STAGE={0 if stage.name in probe['exclude'] else 1}")
PY
)"
ENV_NAME=${ENV_OVERRIDE:-$STAGE_ENV}
if [ "$ENV_NAME" != "$STAGE_ENV" ]; then
  echo "run_stage.sh: $STAGE declares env=$STAGE_ENV and runs in $ENV_NAME (--env)"
fi

# The run's config: the committed config with the conversion pins j0_build recorded (staging.py run-config) and any
# --set. It is written per process (the combined GPU job runs shards side by side), so a later conversion cannot
# change a config under a running stage.
RUN_CONFIG=$TMPDIR/config-$STAGE-$$
trap 'rm -rf "$RUN_CONFIG"; intract_tmp_cleanup' EXIT
python -I "$STAGING" run-config --out "$RUN_CONFIG" ${SETS[@]+"${SETS[@]}"}
# What the overlay changed is kept with the run's outputs, beside the timing records it explains.
mkdir -p "$WORK/_runs"
cp "$RUN_CONFIG/OVERLAY.json" "$WORK/_runs/overlay-$STAGE-${SLURM_JOB_ID:-local}_${SLURM_ARRAY_TASK_ID:-0}-$$.json"

if [ -n "${SLURM_ARRAY_TASK_ID:-}" ] && [ -z "$SHARDS" ]; then
  SHARD_LIST=$SLURM_ARRAY_TASK_ID
elif [ -z "$SHARDS" ] || [ "$SHARDS" = all ]; then
  SHARD_LIST=$(seq -s ' ' 0 $((NSHARDS - 1)))
else
  SHARD_LIST=${SHARDS//,/ }
fi
for s in $SHARD_LIST; do
  if [ "$s" -ge "$NSHARDS" ]; then echo "run_stage.sh: shard $s is outside 0..$((NSHARDS - 1))" >&2; exit 2; fi
done
EXTRA_INPUT=()
[ -n "$INPUT" ] && EXTRA_INPUT=(--input "$INPUT")

shards_to_run() {  # work shards: the shards whose records cannot be trusted (all of them with RESUME=0)
  if [ "${RESUME:-1}" != 1 ]; then echo "$2"; return 0; fi
  python -I "$STAGING" resume-plan --stage "$STAGE" --work "$1" --lang "$LANG_" --nshards "$NSHARDS" \
    --shards "$2" ${EXTRA_INPUT[@]+"${EXTRA_INPUT[@]}"}
}
RUN_LIST=$(shards_to_run "$WORK" "$SHARD_LIST")

write_side() {  # shard work cold probe_kind [real user sys]
  python -I - "$2/_runs/$LANG_/$STAGE-shard-$1-of-$NSHARDS.json" "$STAGE" "$LANG_" "$1" "$NSHARDS" "$ENV_NAME" \
    "${VIRTUAL_ENV:-}" "${INTRACT_STAGE_CPUS:-${SLURM_CPUS_PER_TASK:-}}" "$3" "$4" "${@:5}" <<'PY'
import json
import os
import platform
import sys

path, stage, lang, shard, nshards, env, venv, cpus, cold, kind, *times = sys.argv[1:]


def seconds(text):
    # bash prints the time with the locale's decimal mark
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


real, user, system = (list(map(seconds, times)) + [None, None, None])[:3]
rec = {"stage": stage, "lang": lang, "shard": int(shard), "nshards": int(nshards), "env_active": env,
       "virtual_env": venv or None, "cpus": int(cpus) if cpus else None, "cold": cold == "true",
       "probe": kind or None, "host": platform.node(), "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
       "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
       "code_commit": os.environ.get("INTRACT_CODE_COMMIT"),
       "process_tree": {"real_seconds": real, "user_seconds": user, "sys_seconds": system}}
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path + ".tmp", "w", encoding="utf-8") as fh:
    json.dump(rec, fh, indent=1, sort_keys=True)
    fh.write("\n")
os.replace(path + ".tmp", path)
PY
}

run_one() {  # shard work limit probe_kind
  local s=$1 work=$2 limit=$3 kind=$4 cold=false tfile rc=0 args TIMEFORMAT='%R %U %S'
  [ -e "$TMPDIR/warm.$STAGE" ] || cold=true
  echo "== $STAGE shard $s of $NSHARDS${kind:+ ($kind probe)} ($RUN, $LANG_, env $ENV_NAME, cold=$cold) $(date -u +%FT%TZ)"
  args=(run "$STAGE" --config "$RUN_CONFIG" --work "$work" --lang "$LANG_" --shard "$s" --nshards "$NSHARDS")
  [ -n "$INPUT" ] && args+=(--input "$INPUT")
  [ -n "$limit" ] && args+=(--limit "$limit")
  tfile=$(mktemp "$TMPDIR/time.XXXXXX")
  # The stage's own stderr goes to fd 3 (the job log); only the time keyword's line lands in $tfile.
  { time python -I -m intract_features "${args[@]}" 2>&3 ; } 3>&2 2>"$tfile" || rc=$?
  if [ "$rc" -ne 0 ]; then rm -f "$tfile"; return "$rc"; fi
  touch "$TMPDIR/warm.$STAGE"
  # The side record only adds to the timing record, so failing to write it never fails a finished shard.
  # shellcheck disable=SC2046
  write_side "$s" "$work" "$cold" "$kind" $(tail -n 1 "$tfile") || echo "== $STAGE shard $s: side record not written"
  rm -f "$tfile"
}

probe_needed() {  # cold|warm: link the run's inputs into the probe's folder; print 1 if the probe must run
  local pwork=$WORK/$PROBE_DIR/$1/$STAGE d name
  mkdir -p "$pwork/$LANG_"
  # The probe reads the run's inputs through links and writes its one-document outputs and records in its own
  # folder, so nothing of the run is overwritten.
  for d in "$WORK/$LANG_"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    case "$name" in _*) continue ;; esac
    case " $STAGE_OUTPUTS " in *" $name "*) continue ;; esac
    ln -sfn "$WORK/$LANG_/$name" "$pwork/$LANG_/$name"
  done
  if [ -n "$(shards_to_run "$pwork" 0)" ]; then echo 1; else echo 0; fi
}
probe() {  # cold|warm
  run_one 0 "$WORK/$PROBE_DIR/$1/$STAGE" "$PROBE_LIMIT" "$1" \
    || echo "== $STAGE $1 probe FAILED (does not stop the run; aggregate_timing falls back to timers or no split)"
}

# Every decision that reads the stage modules is taken here, in core, before the stage's own environment loads.
PROBE_COLD=0; PROBE_WARM=0
if [ "${PROBE:-1}" = 1 ] && [ "$PROBE_STAGE" = 1 ] && [[ " $SHARD_LIST " == *" 0 "* ]]; then
  PROBE_COLD=$(probe_needed cold)
  PROBE_WARM=$(probe_needed warm)
fi

if [ "$ENV_NAME" != core ]; then intract_env "$ENV_NAME"; fi
if [ "$PROBE_COLD" = 1 ]; then probe cold; fi
for s in $SHARD_LIST; do
  if [[ " $RUN_LIST " != *" $s "* ]]; then
    echo "== $STAGE shard $s of $NSHARDS: done before by this code, skipped"
    continue
  fi
  run_one "$s" "$WORK" "$LIMIT" ""
done
if [ "$PROBE_WARM" = 1 ]; then probe warm; fi
echo "== $STAGE done $(date -u +%FT%TZ)"
