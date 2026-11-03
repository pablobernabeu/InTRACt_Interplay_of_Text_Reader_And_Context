#!/bin/bash
#SBATCH --job-name=if_surprisal_xglm
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# Stage surprisal_xglm (GPU, every shard in this allocation): XGLM-4.5B in fp32 with TF32 off. The released
# checkpoint is fp16 (10.15 GB; 5,076,815,872 parameters, all F16, by its safetensors header at the pinned commit),
# so fp32 means those weights upcast, about 20.3 GB on a 46 GB L40S. Never timed. At about 10 GFLOP per token
# (2 x parameters) and an assumed 40 per cent of the L40S's 91.6 fp32 TFLOPS, about 3,600 tokens a second, the
# catalogue's 45 million token positions take about 3.5 hours (UNVERIFIED).
set -eo pipefail
exec bash /data/educ-intract/educ1242/intract_features/code/jobs/arc/run_stage.sh surprisal_xglm "$@"
