#!/bin/bash
#SBATCH --job-name=if_features_discourse
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=06:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%A_%a.out
# Stage features_discourse (CPU, array over shards): overlap, continuation, connectives, dialogue share, names,
# MEmoLon affect and the eSpeak NG spoken duration. phonemizer runs as a second process (hence two CPUs) and the
# English MEmoLon table (97.6 MB) is held in memory. eSpeak NG and MEmoLon at this scale are unmeasured.
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh features_discourse "$@"
