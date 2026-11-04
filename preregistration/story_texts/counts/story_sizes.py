"""Texts, pages and whitespace tokens per language, from the published tables' pages and words columns.

Usage: python -I -X utf8 story_sizes.py <story_texts/data> <locale>,<locale>,...
"""
import csv, lzma, statistics, sys
csv.field_size_limit(10**9)
base = sys.argv[1]
for lang in sys.argv[2].split(","):
    pages = words = n = 0
    per_text = []
    with lzma.open(f"{base}/{lang}/stories.csv.xz", "rt", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            n += 1
            pages += int(row["pages"])
            w = int(row["words"])
            words += w
            per_text.append(w)
    print(f"{lang}: texts={n} pages={pages} whitespace_tokens={words:,} median_per_text={statistics.median(per_text):.0f}")
