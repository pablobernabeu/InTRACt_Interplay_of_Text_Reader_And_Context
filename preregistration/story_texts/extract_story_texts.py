"""
Extract the Let's Story texts from the data controller's StoryReview viewer.

WHAT IT READS
The data controller delivered the story texts as StoryReview, a browser viewer built by
its own build_story_review.py. The viewer keeps its data as JSON wrapped in a call that
a <script> tag can load:

    data/index.js        window.STORY_INDEX={...};   one row per story, with metadata
    data/text/cNNNN.js   STORY_CHUNK(n,[...]);        the full texts, 500 per file

Removing the wrapper leaves plain JSON, so every text can be read without a browser.

WHAT IT WRITES
Into the output folder, which defaults to a folder inside the git-ignored delivery:

    stories.csv            one row per story: the viewer's Story ID, the folder the text
                           came from, the seven metadata fields, title, page and word
                           counts, and the text exactly as delivered
    pages.csv              one row per page: Story ID, position (1, 2, ...), the number
                           the page marker carries, and the page text
    anomalies.csv          texts whose structure is unusual (see below), one row each
    extraction_record.json the checksum of every file read, the counts, and the run

HOW IT CHECKS ITSELF
Before writing anything, the run confirms that the wrappers have the expected form,
that every declared chunk file is present, that Story IDs are unique, that the index
and the chunk files correspond one to one, and that its own page and word counts
reproduce the ones the viewer stores. Any failure stops the run with exit status 1
and writes nothing, so a partial or misread extraction cannot be mistaken for a
complete one.

Unusual texts are reported, not removed, because they may be exactly what the app
served. They are pages whose markers skip or repeat a number, empty pages, texts
without page markers, and stories the build script could not parse as JSON.

WORD COUNTS
`words` is the viewer's count, whitespace-separated tokens once the page markers are
removed. It is kept so that the recount can be checked against the index, and it is not
the word definition of the protocol's feature pipeline.

HOW TO RUN
    python extract_story_texts.py
    python extract_story_texts.py --viewer D:/StoryReview --out D:/extracted

Standard library only, Python 3.8 or later. Paths default relative to this file, so
the working directory does not matter.
"""
import argparse
import csv
import datetime
import hashlib
import json
import platform
import re
import sys
from pathlib import Path

VERSION = "2026-10-01"
HERE = Path(__file__).resolve().parent
DELIVERY = HERE.parent / "Oxford-40k-stories"
META_KEYS = ["hero", "world", "theme", "prompt", "sidekick", "age", "lang"]

# The build script counts pages and words with PAGE_RE, and the viewer splits a text
# into pages with PAGE_SPLIT. Both are copied verbatim so that this extraction divides
# a text exactly as the data controller's tools do.
PAGE_RE = re.compile(r"^\s*Page\s+\d+\s*:\s*", re.IGNORECASE | re.MULTILINE)
PAGE_SPLIT = re.compile(r"^[ \t]*Page\s+(\d+)\s*:\s*", re.IGNORECASE | re.MULTILINE)


class ExtractionError(Exception):
    pass


def unwrap(path, prefix, suffix):
    """Return (match, payload) for a file of the form <prefix>JSON<suffix>."""
    raw = path.read_text(encoding="utf-8")
    head = re.match(prefix, raw)
    if not head or not raw.endswith(suffix):
        raise ExtractionError(f"{path.name}: not in the viewer's format")
    return head, json.loads(raw[head.end():len(raw) - len(suffix)])


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def split_pages(text):
    """Return [(label, page_text)], label being the number the marker carries."""
    parts = PAGE_SPLIT.split(text)
    # A preamble before the first marker is kept as label 0, as the viewer shows it.
    pages = [(0, parts[0])] if parts[0].strip() else []
    pages += [(int(parts[i]), parts[i + 1]) for i in range(1, len(parts), 2)]
    # Line endings are normalised here because the public-domain texts use CRLF and the
    # generated ones LF. stories.csv keeps each text as delivered.
    return [(label, body.replace("\r\n", "\n").strip()) for label, body in pages]


def read_viewer(viewer):
    data = viewer / "data"
    _, index = unwrap(data / "index.js", r"window\.STORY_INDEX=", ";\n")
    files = [data / "index.js"]
    chunks = {}
    for path in sorted((data / "text").glob("c*.js")):
        head, texts = unwrap(path, r"STORY_CHUNK\((\d+),", ");\n")
        chunks[int(head.group(1))] = texts
        files.append(path)
    if sorted(chunks) != list(range(index["chunks"])):
        raise ExtractionError(f"index declares {index['chunks']} chunk files, found {sorted(chunks)}")
    return index, chunks, files


def build_stories(index, chunks):
    col = {c: i for i, c in enumerate(index["columns"])}
    stories, used, mismatches = [], set(), []
    for row in index["rows"]:
        c, pos = row[col["chunk"]], row[col["pos"]]
        try:
            text = chunks[c][pos]
        except (KeyError, IndexError):
            raise ExtractionError(f"Story ID {row[col['id']]} points to a missing text (chunk {c}, position {pos})")
        used.add((c, pos))
        meta = {k: index["fields"][k][row[col["meta"]][i]] for i, k in enumerate(META_KEYS)}
        pages = split_pages(text)
        words = len(PAGE_RE.sub(" ", text).split())
        n_markers = len(PAGE_RE.findall(text))
        if (words, n_markers) != (row[col["words"]], row[col["pages"]]) or n_markers != sum(l > 0 for l, _ in pages):
            mismatches.append(row[col["id"]])
        # The index leaves `folder` empty when it equals the metadata joined by hyphens.
        folder = row[col["folder"]] or "-".join(meta[k] for k in META_KEYS[:-1])
        stories.append(dict(id=row[col["id"]], folder=folder, **meta, title=row[col["title"]],
                            pages=n_markers, words=words, build_error=row[col["err"]],
                            text=text, _pages=pages))

    ids = [s["id"] for s in stories]
    slots = {(c, i) for c, texts in chunks.items() for i in range(len(texts))}
    if len(set(ids)) != len(ids):
        raise ExtractionError(f"{len(ids) - len(set(ids))} duplicated Story IDs")
    if slots != used:
        raise ExtractionError(f"{len(slots - used)} texts belong to no index row")
    if mismatches:
        raise ExtractionError(f"page or word recount differs from the index for {len(mismatches)} stories, "
                              f"first Story IDs {mismatches[:5]}")
    return stories


def find_anomalies(s):
    labels = [label for label, _ in s["_pages"] if label > 0]
    found = []
    if s["build_error"]:
        found.append(("build error", s["build_error"]))
    if not labels:
        found.append(("no page markers", ""))
    elif labels != list(range(1, len(labels) + 1)):
        found.append(("page numbers skip or repeat", " ".join(map(str, labels))))
    empty = [str(label) for label, body in s["_pages"] if not body]
    if empty:
        found.append(("empty page", "page " + ", ".join(empty)))
    return [dict(id=s["id"], folder=s["folder"], lang=s["lang"], age=s["age"], issue=i, detail=d) for i, d in found]


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--viewer", type=Path, default=DELIVERY / "StoryReview", help="the StoryReview folder")
    ap.add_argument("--out", type=Path, default=DELIVERY / "extracted", help="output folder")
    ap.add_argument("--version", action="version", version=VERSION)
    args = ap.parse_args()

    try:
        index, chunks, files = read_viewer(args.viewer)
        stories = build_stories(index, chunks)
    except (OSError, ValueError, ExtractionError) as e:
        sys.exit(f"Stopped, nothing written: {e}")

    args.out.mkdir(parents=True, exist_ok=True)
    story_cols = ["id", "folder", *META_KEYS, "title", "pages", "words", "build_error", "text"]
    write_csv(args.out / "stories.csv", story_cols, ([s[k] for k in story_cols] for s in stories))
    write_csv(args.out / "pages.csv", ["id", "lang", "page", "page_label", "text"],
              ([s["id"], s["lang"], n, label, body]
               for s in stories for n, (label, body) in enumerate(s["_pages"], 1)))
    anomalies = [a for s in stories for a in find_anomalies(s)]
    write_csv(args.out / "anomalies.csv", ["id", "folder", "lang", "age", "issue", "detail"],
              ([a[k] for k in ("id", "folder", "lang", "age", "issue", "detail")] for a in anomalies))

    record = {
        "script_version": VERSION,
        "run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "viewer_generated": index["generated"],
        "viewer_source": index["source"],
        "stories": len(stories),
        "pages": sum(len(s["_pages"]) for s in stories),
        "stories_by_lang": {v: sum(s["lang"] == v for s in stories) for v in index["fields"]["lang"]},
        "anomalies": len(anomalies),
        "files": [{"file": p.relative_to(args.viewer).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)}
                  for p in files],
    }
    (args.out / "extraction_record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                                                     encoding="utf-8")

    print(f"{record['stories']:,} stories, {record['pages']:,} pages, languages {record['stories_by_lang']}")
    print(f"{len(anomalies)} anomalies in {len({a['id'] for a in anomalies})} stories, listed in anomalies.csv")
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
