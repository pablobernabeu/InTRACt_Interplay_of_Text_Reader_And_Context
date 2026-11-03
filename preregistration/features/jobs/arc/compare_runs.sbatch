#!/bin/bash
#SBATCH --job-name=if_compare_runs
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# DESIGN.md, Determinism: "The 1 per cent smoke run's rows must equal the same rows of the full run, and the run
# records compare their hashes." compare_runs.py rows reads both runs' artefacts (CPU, offline, no text printed) and
# writes $INTRACT_WORK_ROOT/<larger>/_summary/rows_vs_<smaller>.json; the job fails if a row differs.
# Usage: sbatch compare_runs.sbatch <smaller run> <larger run>   (submit_chain.sh: smoke full)
set -eo pipefail
SMALL=${1:?the smaller run, for instance smoke}; LARGE=${2:?the larger run, for instance full}
source /data/educ-intract/educ1242/intract_features/code/jobs/arc/env.sh core
trap intract_tmp_cleanup EXIT
set -u
python -I "$INTRACT_CODE/jobs/arc/compare_runs.py" rows --base "$INTRACT_WORK_ROOT/$LARGE" \
  --other "$INTRACT_WORK_ROOT/$SMALL" --out "$INTRACT_WORK_ROOT/$LARGE/_summary/rows_vs_$SMALL.json"
