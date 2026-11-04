"""Metadata-only check: how many attribute combinations the English table holds and how many
reading levels each has. Reads the metadata columns only; the text column is never touched.
Usage: python -I -X utf8 versions_check.py <stories.csv.xz>
"""
import csv
import lzma
import sys
from collections import Counter, defaultdict

csv.field_size_limit(2**31 - 1)
levels = defaultdict(set)
pd_levels = defaultdict(set)
with lzma.open(sys.argv[1], "rt", encoding="utf-8", newline="") as f:
    for r in csv.DictReader(f):
        if r["hero"] == "Public domain":
            pd_levels[r["folder"].rsplit(" ", 1)[0]].add(r["age"])
            continue
        levels[(r["hero"], r["world"], r["theme"], r["prompt"], r["sidekick"])].add(r["age"])
print("generated attribute combinations:", len(levels))
print("levels per combination:", Counter(len(v) for v in levels.values()))
print("distinct values per attribute:", [len({k[i] for k in levels}) for i in range(5)])
print("classic folders (age suffix removed):", len(pd_levels), Counter(len(v) for v in pd_levels.values()))
