"""How many texts per language compress far better than the language's median (a repetition check).

Usage: python -I -X utf8 repetition_scan.py [data_dir]   (default: story_texts/data beside this folder)
Run on 26 October 2026 on the delivery's extracted tables, which are byte-identical to the published
story_texts/data/<locale>/stories.csv.xz (SHA-256 of all 21 compared on 4 November 2026).
"""
import csv
import lzma
import statistics
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

csv.field_size_limit(2**31 - 1)
TABLES = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data"


def scan(path):
    ratios = []
    with lzma.open(path, "rt", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            b = row["text"].encode("utf-8")
            ratios.append((len(zlib.compress(b, 6)) / len(b), int(row["id"]), int(row["pages"])))
    med = statistics.median(r for r, _, _ in ratios)
    out = []
    for frac in (0.5, 0.6, 0.7):
        out.append((frac, sorted((round(r / med, 3), i, p) for r, i, p in ratios if r < frac * med)))
    lo = sorted(r / med for r, _, _ in ratios)
    return path.parent.name, round(med, 3), round(lo[len(lo) // 1000], 3), out


if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=4) as pool:
        for lang, med, p01, out in pool.map(scan, sorted(TABLES.glob("*/stories.csv.xz"))):
            print(lang, "median", med, "0.1th percentile of ratio/median", p01,
                  {frac: (len(v), v[:8]) for frac, v in out}, flush=True)
