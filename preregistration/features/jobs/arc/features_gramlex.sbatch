#!/bin/bash
#SBATCH --job-name=if_features_gramlex
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%A_%a.out
# Stage features_gramlex (CPU, array over shards): the grammatical, lexical, diversity and page features from both
# parses. Unmeasured at scale; the limit leaves room until the dry run times it.
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh features_gramlex "$@"
