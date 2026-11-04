"""Corpus-level aggregates of the published English story texts, for compute planning only.

Reports totals and distribution percentiles over the whole corpus. It writes no per-text
feature, links nothing to any outcome and runs no dimension reduction.
"""
import csv
import lzma
import re
import statistics
import sys
from collections import Counter, defaultdict

path = sys.argv[1]
csv.field_size_limit(2**31 - 1)
SENT_END = re.compile(r"[.!?…]+[\"'”’)\]]*(?=\s|$)")
PAGE = re.compile(r"Page \d+:")

n = 0
words_total = chars_total = sent_total = pages_total = 0
per_text_words = []
per_text_chars = []
by_group = defaultdict(list)
cols = None
with lzma.open(path, "rt", encoding="utf-8", newline="") as fh:
    reader = csv.DictReader(fh)
    cols = reader.fieldnames
    for row in reader:
        text = row["text"]
        body = PAGE.sub(" ", text)
        w = len(body.split())
        c = len(body)
        s = len(SENT_END.findall(body))
        n += 1
        words_total += w
        chars_total += c
        sent_total += s
        pages_total += len(PAGE.findall(text))
        per_text_words.append(w)
        per_text_chars.append(c)
        key = row.get("age") or "?"
        kind = "classic" if row.get("folder", "").startswith("PD_") else "generated"
        by_group[(kind, key)].append(w)


def pct(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


print("columns:", cols)
print(f"texts {n:,}; words {words_total:,}; chars {chars_total:,}; sentence ends {sent_total:,}; pages {pages_total:,}")
print(f"words/text mean {words_total / n:.1f}; chars/word {chars_total / words_total:.2f}; words/sentence {words_total / max(sent_total, 1):.2f}")
for q in (0, 0.05, 0.5, 0.95, 0.99, 1):
    print(f"  words p{int(q * 100):>3}: {pct(per_text_words, q):,.0f}   chars p{int(q * 100):>3}: {pct(per_text_chars, q):,.0f}")
print("by group (kind, level): n, mean words, median, max")
for key, xs in sorted(by_group.items()):
    print(f"  {key}: {len(xs):,}, {statistics.mean(xs):.0f}, {statistics.median(xs):.0f}, {max(xs):,}")
