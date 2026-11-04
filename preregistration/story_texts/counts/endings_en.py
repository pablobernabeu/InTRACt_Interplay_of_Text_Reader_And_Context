"""English endings and page breaks, classified. Structure only (punctuation at boundaries).

Usage: python -I -X utf8 endings_en.py [preregistration_dir]   (default: two folders up from this file)
"""
import collections
import csv
import lzma
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "story_texts"))
from extract_story_texts import split_lines  # noqa: E402

csv.field_size_limit(2**31 - 1)
CLOSE = set('.!?"\'”’»)…—–-*~')
END_WORD = re.compile(r"(^|\n)\s*(the\s+)?end\.?\s*$", re.I)
MARKER = re.compile(r"\n\s*(P|Pa|Pag|Page|Page\s+\d+\s*:?)\s*$")

cats = collections.Counter()
lists = collections.defaultdict(list)
inner = collections.Counter()
inner_ids = collections.defaultdict(list)
pages_of = {}
with lzma.open(REPO / "story_texts" / "data" / "en-us" / "stories.csv.xz", "rt", encoding="utf-8", newline="") as f:
    for r in csv.DictReader(f):
        i, n = int(r["id"]), int(r["pages"])
        title, pages = split_lines(r["text"])
        pages_of[i] = n
        last = pages[-1].rstrip()
        if not last:
            cats["empty last page"] += 1
            continue
        if MARKER.search(last):
            cats["ends on a cut-off page marker"] += 1
            lists["marker"].append((i, n))
        elif END_WORD.search(last):
            cats["ends with 'End'"] += 1
        elif last[-1] in CLOSE:
            cats["closing punctuation"] += 1
        else:
            cats["stops mid-sentence"] += 1
            lists["mid"].append((i, n))
        for k, p in enumerate(pages[:-1], 1):
            s = p.rstrip()
            if s and s[-1] not in CLOSE and not MARKER.search(s) and not END_WORD.search(s):
                inner["page ends mid-sentence"] += 1
                inner_ids[i].append(k)

print(dict(cats))
for key in ("mid", "marker"):
    ids = lists[key]
    by_len = collections.Counter("short (<15 pages)" if n < 15 else "full length" for _, n in ids)
    print(key, len(ids), dict(by_len), "classics:", sum(i > 40500 for i, _ in ids))
    print("   ids:", [i for i, _ in ids])
print("inner pages ending mid-sentence:", dict(inner), "in", len(inner_ids), "stories; first:", list(inner_ids.items())[:30])
