#!/bin/bash
#SBATCH --job-name=if_seg_check
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Stage seg_check (CPU, one task): English SaT against the frozen rule segmenter (F1 >= .95) and the five-sentence
# floor. Rule-based and light. The report covers every shard, so run_stage.sh runs the shards in turn and only the
# shard 0 run computes and writes it; the others return at once (stages/seg_check.py).
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh seg_check "$@"
