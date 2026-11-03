#!/bin/bash
#SBATCH --job-name=if_documents
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%A_%a.out
# Stage documents (CPU, array over shards): the stand-in's rows to normalised documents behind the catalogue lock.
# Each task reads the whole table and keeps its shard's stories, a few minutes for 40,559 rows.
# Arguments: <run> --input <stand-in stories.csv.xz> (submit_chain.sh passes them).
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh documents "$@"
