#!/bin/bash
#SBATCH --job-name=if_surprisal_goldfish
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=02:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Stage surprisal_goldfish (GPU, every shard in this allocation): both Goldfish tiers in fp32, from the safetensors
# that j0_build converted. Never timed on a GPU (one laptop thread scored 81 tokens a second with windows); the
# catalogue is about 28 million token positions per tier with the 512/256 windows, so the limit is generous.
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh surprisal_goldfish "$@"
