#!/bin/bash
#SBATCH --job-name=if_qe_metricx
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Stage qe_metricx (GPU, every shard in this allocation): MetricX-24-Hybrid-XL reference-free QE. The stand-in has
# no translations, so the dry run times it on the translated benchmark's English-German pairs (staging.py qe-pairs,
# built by j1_standin). Arguments: <run> --lang de-de --input <pairs> [--env core] (submit_chain.sh passes them).
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh qe_metricx "$@"
