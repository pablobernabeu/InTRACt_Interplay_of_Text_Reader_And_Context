#!/bin/bash
#SBATCH --job-name=if_encode_e5
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=01:30:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Stage encode_e5 (GPU, every shard in this allocation): multilingual-e5-large-instruct in fp32. TU-5 measured 1,341
# sentences a second on L40S; at 8.6 to 12 words a sentence the catalogue's 1.4 to 2.0 million sentences take
# 18 to 25 minutes.
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh encode_e5 "$@"
