#!/bin/bash
#SBATCH --job-name=if_sat
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=01:30:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Stage sat (GPU, every shard in this one allocation): the registered SaT boundaries. TU-2 measured 221,000
# characters a second on L40S, so the catalogue's 101.7 million characters take about 8 minutes; model loading and
# the 3-7 minute cold imports per shard dominate.
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh sat "$@"
