#!/bin/bash
#SBATCH --job-name=if_aggregate_timing
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Stage aggregate_timing (CPU, one task): every timing record of the run in one table, with throughput per unit and
# a projection to the full English catalogue (config/stages/aggregate_timing.toml). submit_chain.sh makes it depend
# afterany on the run's jobs, so a run that fails part way still reports what it measured. It reads the whole run,
# so it runs as one shard, and always again (RESUME=0), since its table must reflect the records as they now stand.
set -eo pipefail
NSHARDS=1 RESUME=0 exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh aggregate_timing "$@"
