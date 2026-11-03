#!/bin/bash
#SBATCH --job-name=if_encode_bgem3
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=01:30:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Stage encode_bgem3 (GPU, every shard in this allocation): BGE-M3 dense vectors in fp32 from the converted
# safetensors. Never timed; it has e5's XLM-R-large shape, so e5's rate is the expectation.
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh encode_bgem3 "$@"
