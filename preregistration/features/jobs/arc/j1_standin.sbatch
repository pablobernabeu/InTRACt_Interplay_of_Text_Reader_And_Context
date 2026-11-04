#!/bin/bash
#SBATCH --job-name=if_j1_standin
#SBATCH --clusters=htc
#SBATCH --account=educ-intract
#SBATCH --partition=short
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --export=NONE
#SBATCH --output=/data/educ-intract/educ1242/intract_features/logs/%x_%j.out
# J1, the inputs of one run (CPU, offline): the length-matched SimpleStories stand-in (standin/build_standin.py,
# the smoke set with "smoke") and the English-German pairs on which qe_metricx is timed (staging.py qe-pairs).
# Usage: sbatch j1_standin.sbatch <smoke|full> [<qe pairs limit>]
# The structure table, $INTRACT_INPUTS/en-us/structure.tsv, is a structural count of the English catalogue
# (identifiers and numbers, no text) that the PI copies to ARC: the planning review's table of 2 November serves as it is,
# since standin/catalogue_structure.py reads the combination column as optional (jobs/arc/README.md,
# Prerequisites). This job never reads the story texts. A failed acceptance check is printed and recorded in
# _input/standin_manifest.json; it stops the chain (exit 3) only when standin.toml [acceptance] enforce is true,
# which the PI decides (the default, false, lets the dry run go on).
set -eo pipefail
RUN=${1:?smoke or full}; QE_LIMIT=${2:-}
source /data/educ-intract/educ1242/intract_features/code/jobs/arc/env.sh core
trap intract_tmp_cleanup EXIT
set -u
WORK=$INTRACT_WORK_ROOT/$RUN
STRUCTURE=$INTRACT_INPUTS/en-us/structure.tsv
[ -s "$STRUCTURE" ] || { echo "missing $STRUCTURE (see jobs/arc/README.md, Prerequisites)"; exit 3; }
mkdir -p "$WORK/_input"
size=()
[ "$RUN" = smoke ] && size=(--smoke)
(cd "$INTRACT_CODE" && python -E -s -m standin.build_standin build --structure "$STRUCTURE" \
   --shards "$INTRACT_RESOURCES/simplestories" --out "$WORK/_input" ${size[@]+"${size[@]}"})
ls -l "$WORK/_input" "$WORK/_input/en-us"
limit=()
[ -n "$QE_LIMIT" ] && limit=(--limit "$QE_LIMIT")
python -I "$INTRACT_CODE/jobs/arc/staging.py" qe-pairs --mt "$PRESUB/translated_union/mt/madlad_de.jsonl" \
  --lang de-de --out "$WORK/_input/qe_pairs_de-de.jsonl.gz" ${limit[@]+"${limit[@]}"}
echo "J1 $RUN done $(date -u +%FT%TZ)"
