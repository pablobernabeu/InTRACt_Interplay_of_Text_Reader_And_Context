#!/bin/bash
#SBATCH --job-name=if_parse_udpipe
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Stage parse_udpipe (GPU, environment udpipe, every shard in this allocation). TU-4u measured 6,356 words a second
# for English on L40S, about 55 minutes for the catalogue, and each shard starts its own server (185 s on L40S).
# The server's 8 TensorFlow threads (parse_udpipe.toml) set the CPU request.
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh parse_udpipe "$@"
