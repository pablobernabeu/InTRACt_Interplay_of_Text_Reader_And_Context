"""Frequency table of pages per text by kind and level, and page-length shape, from the
structure-only TSV written by length_profile.py. Numbers only.

Usage: python -I -X utf8 pages_table.py <en_per_text_structure.tsv>
"""
import statistics
import sys
from collections import Counter, defaultdict

rows = []
with open(sys.argv[1], encoding="utf-8") as f:
    next(f)
    for line in f:
        i, kind, level, pages, tok, ch, tpp, cpp = line.rstrip("\n").split("\t")
        rows.append((kind, level, int(pages), int(tok), int(ch), [int(x) for x in tpp.split()]))

tab = defaultdict(Counter)
for kind, level, pages, *_ in rows:
    tab[f"{kind}|{level}"][pages] += 1
for g in sorted(tab):
    n = sum(tab[g].values())
    top = ", ".join(f"{p}:{c} ({100 * c / n:.1f}%)" for p, c in sorted(tab[g].items(), key=lambda x: -x[1])[:6])
    print(f"{g:18s} n={n:6d}  {top}")

# Position profile: mean tokens on page k of a text with the modal page count, generated only.
for level, modal in (("young", 17), ("mid", 17), ("old", 20)):
    sel = [r[5] for r in rows if r[0] == "generated" and r[1] == level and r[2] == modal]
    means = [round(statistics.fmean(t[k] for t in sel), 1) for k in range(modal)]
    print(f"{level:6s} modal {modal} pages, n={len(sel)}: mean tokens by page position {means}")

# Correlation of pages with tokens per text, and of tokens with characters per text, generated only.
def corr(a, b):
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    sa = sum((x - ma) ** 2 for x in a) ** 0.5
    sb = sum((y - mb) ** 2 for y in b) ** 0.5
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)

for level in ("young", "mid", "old"):
    sel = [r for r in rows if r[0] == "generated" and r[1] == level]
    print(level, "r(pages, tokens) =", round(corr([r[2] for r in sel], [r[3] for r in sel]), 3),
          " r(tokens, chars) =", round(corr([r[3] for r in sel], [r[4] for r in sel]), 3),
          " chars per token =", round(sum(r[4] for r in sel) / sum(r[3] for r in sel), 3))
# Texts per (pages, level) cell outside the modal count, generated
odd = Counter((r[1], r[2]) for r in rows if r[0] == "generated" and r[2] not in (17, 20))
print("generated texts off the 17/20-page modes:", sum(odd.values()))
