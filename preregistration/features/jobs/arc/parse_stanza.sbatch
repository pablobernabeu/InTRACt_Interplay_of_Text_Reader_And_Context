#!/bin/bash
#SBATCH --job-name=if_parse_stanza
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=06:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%A_%a.out
# Stage parse_stanza (CPU, array over shards, one torch thread as parse_stanza.toml sets). TU-4s measured 583
# syntactic words per CPU-second for English on htc; the catalogue's 17.3 million whitespace tokens, at 1.14 to 1.27
# parser words each, give about 2.5 hours per shard of four. 24 GB is parse_stanza.toml's guidance until the dry
# run has measured the peak (8 GB killed seven TU-4s tasks whose padded batches held a loop).
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh parse_stanza "$@"
