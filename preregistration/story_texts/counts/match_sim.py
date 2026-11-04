"""Feasibility of length-matching the catalogue's English structure with single SimpleStories stories.

Approximates the train split (2,115,696 stories) by the test split's whitespace-token distribution
replicated 99 times, then matches every catalogue text (structure-only token counts) to an unused
candidate within +/-3% of its token count, in a seeded random order, and counts the targets that
would need a join of two or more stories. Public data and structure-only counts only.
Usage: <venv python> -I -X utf8 match_sim.py <test.parquet> <en_per_text_structure.tsv>
"""
import random
import sys
from bisect import bisect_left
from collections import Counter, defaultdict

import pyarrow.parquet as pq

TOL = 0.03
stories = pq.read_table(sys.argv[1], columns=["story", "generation_id", "num_stories_in_completion"]).to_pydict()
n_test = [len(s.split()) for s in stories["story"]]
gid = stories["generation_id"]
print("test stories", len(gid), "distinct generation_id", len(set(gid)),
      "stories per completion (num_stories_in_completion)", Counter(stories["num_stories_in_completion"]).most_common(4))

pool = Counter()
for n in n_test:
    pool[n] += 99  # approximate train split
targets = defaultdict(list)
with open(sys.argv[2], encoding="utf-8") as f:
    next(f)
    for line in f:
        _, kind, level, pages, tok, *_ = line.split("\t")
        targets[f"{kind}|{level}"].append(int(tok))

rng = random.Random(20261103)
order = [(g, t) for g, ts in targets.items() for t in ts]
rng.shuffle(order)
lengths = sorted(pool)
need_join = Counter()
matched = Counter()
for g, t in order:
    lo, hi = int(t * (1 - TOL)), int(t * (1 + TOL)) + 1
    i = bisect_left(lengths, lo)
    best = None
    while i < len(lengths) and lengths[i] < hi:
        n = lengths[i]
        if pool[n] > 0 and (best is None or abs(n - t) < abs(best - t)):
            best = n
        i += 1
    if best is None:
        need_join[g] += 1
    else:
        pool[best] -= 1
        matched[g] += 1
for g in sorted(targets):
    tot = len(targets[g])
    print(f"{g:18s} targets {tot:6d}  single-story matches {matched[g]:6d}  joins needed {need_join[g]:6d} "
          f"({100 * need_join[g] / tot:.1f}%)")
