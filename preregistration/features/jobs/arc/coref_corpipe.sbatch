#!/bin/bash
#SBATCH --job-name=if_coref_corpipe
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Stage coref_corpipe (GPU, environment corpipe, every shard in this allocation): CorPipe 26 with its umT5-xl
# one-stage model on every English source, reading the Stanza parse (gap G8 default). Never timed anywhere; the
# 7.5 GB checkpoint is read once per shard.
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh coref_corpipe "$@"
