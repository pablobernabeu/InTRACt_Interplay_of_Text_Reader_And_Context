#!/bin/bash
#SBATCH --job-name=if_j0_metricx
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# The metricx environment (MetricX-24's official pins on Python 3.11) and a check that the official code at its
# pinned commit imports under them. It is built apart from J0 because no stage of the dry run runs in it: qe_metricx
# runs the validated port in core (jobs/arc/README.md, Points to settle), and this environment serves the port's
# validation against the official code (qe_metricx.toml [validation]). A failure of the 2023 pins or of the
# Python/3.11.5 module therefore holds up nothing; nothing depends on this job. It runs after J0, which stages the
# MetricX checkout with the other pins.
set -eo pipefail
CODE=/data/educ-intract/educ1242/intract_features/code
export HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0
source "$CODE/jobs/arc/env.sh" ""
trap intract_tmp_cleanup EXIT
set -u

echo "== the metricx environment $(date -u +%FT%TZ)"
bash "$CODE/envs/build_envs.sh" metricx

echo "== the official MetricX-24 code imports under its pins $(date -u +%FT%TZ)"
intract_env metricx
# Run from the checkout, so its metricx24 package imports; -E and -s keep the environment's variables and the user
# site out, as -I would, while the working directory stays importable.
(cd "$INTRACT_METRICX_SRC" && python -E -s -c 'from metricx24 import models; print("metricx24.models", models.__name__)')
echo "J0 metricx done $(date -u +%FT%TZ)"
