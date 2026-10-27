"""
Extract the Let's Story texts from the data controller's two deliveries.

WHAT IT READS
The data controller has delivered the story texts twice, in two forms.

1 October 2026, US English only: StoryReview, a browser viewer built by the data
controller's own build_story_review.py. The viewer keeps its data as JSON wrapped in a
call that a <script> tag can load, and removing the wrapper leaves plain JSON:

    data/index.js        window.STORY_INDEX={...};   one row per story, with metadata
    data/text/cNNNN.js   STORY_CHUNK(n,[...]);        the full texts, 500 per file

26 October 2026, every language: two zip files exported directly from the app's
content. Each holds a folder per language and in it one plain-text file per story,
named after the story's attributes exactly as the viewer's folders are:

    <lang>/<Hero>-<World>-<Theme>-<PromptType>-<Sidekick>-<Age>.txt

The first line of a file is the story's title and each further line is one page. The
files carry no page markers. A line break inside a page is written as the two
characters \n, which split_lines() decodes when it divides a text into pages. The
stories table keeps every file exactly as delivered. A story keeps the Story ID the
viewer gave its English text, read from the viewer's id_map.json, so every language's
version of one story shares one ID.

WHAT IT WRITES
Into the output folder, which defaults to a folder inside the git-ignored delivery.
From the viewer:

    stories.csv            one row per story: the viewer's Story ID, the folder the text
                           came from, the seven metadata fields, title, page and word
                           counts, and the text exactly as delivered
    pages.csv              one row per page: Story ID, position (1, 2, ...), the number
                           the page marker carries, and the page text

From the zip files, the same rows, one xz-compressed table per language, because the
21 languages take about 2.7 GB uncompressed. No pages table is written, since a page is
a line and split_lines() recovers the pages from the text column:

    stories/<lang>.csv.xz  the rows of one language, ordered by Story ID

From either:

    anomalies.csv          texts whose structure is unusual (see below), one row each
    extraction_record.json the checksum of every file read, the counts, and the run

HOW IT CHECKS ITSELF
Any failure below stops the run with exit status 1, so a partial or misread extraction
cannot be mistaken for a complete one.

For the viewer, the run confirms before writing anything that the wrappers have the
expected form, that every declared chunk file is present, that Story IDs are unique,
that the index and the chunk files correspond one to one, and that its own page and
word counts reproduce the ones the viewer stores.

For the zip files, the run confirms that every entry is a .txt file one folder deep,
that each folder is named as a locale (en-us), that no story appears twice in a
language, that every file name is a folder the viewer gave an ID, and that every file
decodes as UTF-8. Python's zipfile checks each file's CRC-32 as it reads it. The zip
files are read through a memory map: on the machine that ran the first extraction of
this delivery, an operating-system seek was occasionally ignored, and a memory map
does not seek. Tables are written under a temporary name and renamed only once the
whole run has succeeded.

Unusual texts are reported, not removed, because they may be exactly what the app
served. In the viewer, they are pages whose markers skip or repeat a number, empty
pages, texts without page markers, and stories the build script could not parse as
JSON. In the zip files, they are empty titles, title lines that hold a page marker in
place of a title, empty pages, page markers inside a page, backslashes other than the
line-break escape, every language's version of a story whose English text marks a page
as missing, texts whose number of pages differs from that of the same story in English,
and repetitive texts. A text counts as repetitive when zlib compresses it to less than
half the median ratio of its language, which is what a few words repeated many times
do.

WORD COUNTS
`words` counts whitespace-separated tokens in the pages, the title and any page
markers excluded, which is the viewer's count. It is kept so that the recount can be
checked against the viewer's index. It is not the word definition of the protocol's
feature pipeline, and it does not count words in Chinese, which is written without
spaces.

HOW TO RUN
    python extract_story_texts.py                      # the 26 October zip files
    python extract_story_texts.py --viewer             # the 1 October viewer
    python extract_story_texts.py --zips A.zip B.zip --ids D:/id_map.json --out D:/extracted
    python extract_story_texts.py --workers 2           # fewer languages at once, less memory

English is extracted first, since every other language is compared with it, and the
other languages are then compressed in parallel worker processes.

Standard library only, Python 3.8 or later. Paths default relative to this file, so
the working directory does not matter.
"""
import argparse
import csv
import datetime
import hashlib
import json
import lzma
import mmap
import os
import platform
import re
import sys
import statistics
import zipfile
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

VERSION = "2026-10-26"
HERE = Path(__file__).resolve().parent
DELIVERY = HERE.parent / "Oxford-40k-stories"
ZIPS = sorted(DELIVERY.glob("Oxford-40k-stories-All-languages_P*.zip"))
META_KEYS = ["hero", "world", "theme", "prompt", "sidekick", "age", "lang"]
STORY_COLS = ["id", "folder", *META_KEYS, "title", "pages", "words", "build_error", "text"]
ANOMALY_COLS = ["id", "folder", "lang", "age", "issue", "detail"]
LOCALE = re.compile(r"^[a-z]{2,3}-[a-z]{2}$")
REFERENCE_LANG = "en-us"
# Preset 6 is xz's default. Preset 9 made a 30 MB sample of the English table only 3 per
# cent smaller, at the same speed, and needs about 700 MB of memory per table, which
# would allow one language at a time on the machine that ran the first extraction.
XZ_PRESET = 6

# The viewer names a classic's folder "PD_<tale> <age>", in several spellings. Copied
# from build_story_review.py so that a file name parses exactly as the viewer's folder did.
PD_AGE_RE = re.compile(r"[\s_]*(old|young)(\s+current)?$", re.IGNORECASE)
PD_HERO = "Public domain"

# Quotation marks that enclose a title on its first line, opening to closing. The
# viewer's titles came from a JSON field without them.
QUOTE_PAIRS = {'"': '"', "'": "'", "\u201c": "\u201d", "\u201e": "\u201c", "\u00ab": "\u00bb",
               "\u00bb": "\u00ab", "\u300a": "\u300b", "\u300c": "\u300d", "\u300e": "\u300f",
               "\u2018": "\u2019", "\u201a": "\u2018", "\u201d": "\u201d"}

# In the zip files, the escape for a line break inside a page, and the note one English
# text carries where its page was lost before export.
LINE_BREAK = "\\n"
STRAY_BACKSLASH = re.compile(r"\\(?!n)")
MISSING_NOTE = "(this page was missing)"
REPETITION = 0.5

csv.field_size_limit(2**31 - 1)

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


def parse_folder(name):
    """The metadata a viewer folder name encodes, as build_story_review.py parses it."""
    empty = {"hero": "", "world": "", "theme": "", "prompt": "", "sidekick": "", "age": ""}
    if name.startswith("PD_"):
        m = PD_AGE_RE.search(name)
        return dict(empty, hero=PD_HERO, age=m.group(1).lower() if m else "")
    parts = name.split("-")
    if len(parts) < 6:
        return dict(empty, hero=name)
    return {"hero": parts[0], "world": "-".join(parts[1:-4]), "theme": parts[-4], "prompt": parts[-3],
            "sidekick": parts[-2], "age": parts[-1]}


def clean_title(line):
    """The first line without the quotation marks that enclose it."""
    title = line.strip()
    while len(title) >= 2 and QUOTE_PAIRS.get(title[0]) == title[-1]:
        title = title[1:-1].strip()
    return title


def split_lines(text):
    """Return (title, [page texts]) for a text in the zip files' form.

    A line break inside a page or title is written as the two characters \\n, where the
    1 October viewer held a real line break, so each is decoded back into one."""
    body = text.replace("\r\n", "\n")
    if body.endswith("\n"):
        body = body[:-1]
    lines = [line.replace(LINE_BREAK, "\n") for line in body.split("\n")]
    return lines[0], lines[1:]


def open_zip(path):
    # A memory map, because a seek on the file itself was occasionally ignored (see above).
    # The map keeps its own handle, so the file can be closed once it exists.
    with open(path, "rb") as f:
        return zipfile.ZipFile(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ))


def read_zips(zips, id_map):
    """Return ({lang: {Story ID: (folder, zip path, entry name)}}, files read, ID source)."""
    ids = {}
    for key, story_id in json.loads(id_map.read_text(encoding="utf-8")).items():
        folder, _, lang = key.rpartition("/")
        if lang != REFERENCE_LANG or folder in ids:
            raise ExtractionError(f"{id_map.name}: unexpected key {key!r}")
        ids[folder] = story_id
    if len(set(ids.values())) != len(ids):
        raise ExtractionError(f"{id_map.name}: a Story ID is given to more than one folder")

    entries, files = {}, []
    for path in zips:
        z = open_zip(path)
        n = 0
        for info in z.infolist():
            if info.is_dir():
                continue
            lang, sep, name = info.filename.partition("/")
            if not sep or "/" in name or not name.endswith(".txt") or not LOCALE.match(lang):
                raise ExtractionError(f"{path.name}: unexpected entry {info.filename!r}")
            folder = name[:-len(".txt")]
            if folder not in ids:
                raise ExtractionError(f"{path.name}: {info.filename!r} names no story the viewer gave an ID")
            by_id = entries.setdefault(lang, {})
            if ids[folder] in by_id:
                raise ExtractionError(f"{info.filename!r} appears more than once")
            by_id[ids[folder]] = (folder, str(path), info.filename)
            n += 1
        files.append({"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path), "entries": n})
    if REFERENCE_LANG not in entries:
        raise ExtractionError(f"the zip files hold no {REFERENCE_LANG} folder")
    source = {"file": id_map.name, "bytes": id_map.stat().st_size, "sha256": sha256(id_map)}
    return entries, files, source


def zip_row(story_id, folder, lang, raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ExtractionError(f"{lang}/{folder}.txt is not UTF-8: {e}")
    title, pages = split_lines(text)
    meta = dict(parse_folder(folder), lang=lang)
    return dict(id=story_id, folder=folder, **meta, title=clean_title(title), pages=len(pages),
                words=len(" ".join(pages).split()), build_error="", text=text,
                _title=title, _pages=pages, _stray=len(STRAY_BACKSLASH.findall(text)))


def zip_anomalies(s, reference_pages, missing_pages):
    """Unusual structure in one text. reference_pages and missing_pages hold the English
    texts' page counts and the pages they mark as missing, both by Story ID."""
    found = []
    if not s["_title"].strip():
        found.append(("empty title", ""))
    elif PAGE_RE.match(s["_title"]):
        found.append(("title line is a page marker", s["_title"].strip()))
    empty = [str(n) for n, page in enumerate(s["_pages"], 1) if not page.strip()]
    if empty:
        found.append(("empty page", "page " + ", ".join(empty)))
    marked = [str(n) for n, page in enumerate(s["_pages"], 1) if PAGE_RE.search(page)]
    if marked:
        found.append(("page marker inside a page", "page " + ", ".join(marked)))
    if s["_stray"]:
        found.append(("backslash other than a line-break escape", f"{s['_stray']} in the text"))
    if s["id"] in missing_pages:
        found.append((f"page marked missing in {REFERENCE_LANG}", "page " + ", ".join(map(str, missing_pages[s["id"]]))))
    ref = reference_pages.get(s["id"])
    if s["lang"] != REFERENCE_LANG and ref is not None and ref != s["pages"]:
        found.append((f"page count differs from {REFERENCE_LANG}", f"{s['pages']} pages, {REFERENCE_LANG} has {ref}"))
    return [dict(id=s["id"], folder=s["folder"], lang=s["lang"], age=s["age"], issue=i, detail=d) for i, d in found]


_ZIPS = {}


def write_language(lang, items, tmp, reference_pages, missing_pages):
    """Write one language's table to tmp; return (lang, stories, pages, anomalies, English
    page counts, English pages marked missing). Runs in a worker process."""
    english = lang == REFERENCE_LANG
    pages, anomalies, own_pages, own_missing, ratios = 0, [], {}, {}, {}
    with lzma.open(tmp, "wt", encoding="utf-8", newline="", preset=XZ_PRESET) as f:
        w = csv.writer(f)
        w.writerow(STORY_COLS)
        for story_id, (folder, path, name) in sorted(items.items()):
            if path not in _ZIPS:
                _ZIPS[path] = open_zip(path)
            raw = _ZIPS[path].read(name)
            s = zip_row(story_id, folder, lang, raw)
            if english:
                own_pages[story_id] = s["pages"]
                lost = [n for n, page in enumerate(s["_pages"], 1) if MISSING_NOTE in page.lower()]
                if lost:
                    own_missing[story_id] = lost
            anomalies += zip_anomalies(s, own_pages if english else reference_pages,
                                       own_missing if english else missing_pages)
            ratios[story_id] = (len(zlib.compress(raw, 6)) / max(len(raw), 1), folder, s["age"])
            pages += s["pages"]
            w.writerow([s[k] for k in STORY_COLS])
    # A text that repeats a few words many times compresses far better than its language's
    # texts usually do. Half the median separates such texts from the rest with a wide
    # margin: in the delivery of 26 October, the least compressible 0.1 per cent of every
    # language still reach 0.84 of its median, and six texts fall below 0.4.
    median = statistics.median(r for r, _, _ in ratios.values())
    for story_id, (r, folder, age) in ratios.items():
        if r < REPETITION * median:
            anomalies.append(dict(id=story_id, folder=folder, lang=lang, age=age, issue="repetitive text",
                                  detail=f"compresses to {r / median:.2f} of the language's median ratio"))
    anomalies.sort(key=lambda a: a["id"])
    return lang, len(items), pages, anomalies, own_pages, own_missing


def extract_zips(zips, id_map, out, workers):
    entries, files, source = read_zips(zips, id_map)
    tables = out / "stories"
    tables.mkdir(parents=True, exist_ok=True)
    stale = {p.name[:-len(".csv.xz")] for p in tables.glob("*.csv.xz")} - set(entries)
    if stale:
        raise ExtractionError(f"{tables} holds tables for {sorted(stale)}, which these zip files lack")

    # English goes first, because every other language's page count is compared with it.
    others = sorted(set(entries) - {REFERENCE_LANG})
    tmp = {lang: tables / f"{lang}.csv.xz.tmp" for lang in entries}
    results = {}
    try:
        lang, n, pages, anomalies, reference_pages, missing_pages = write_language(
            REFERENCE_LANG, entries[REFERENCE_LANG], tmp[REFERENCE_LANG], {}, {})
        results[lang] = (n, pages, anomalies)
        print(f"{lang}: {n:,} stories, {pages:,} pages", flush=True)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            jobs = [pool.submit(write_language, lang, entries[lang], tmp[lang], reference_pages, missing_pages)
                    for lang in others]
            for job in as_completed(jobs):
                lang, n, pages, anomalies, _, _ = job.result()
                results[lang] = (n, pages, anomalies)
                print(f"{lang}: {n:,} stories, {pages:,} pages", flush=True)
    except BaseException:
        for path in tmp.values():
            if path.exists():
                path.unlink()
        raise
    for path in tmp.values():
        os.replace(path, path.with_name(path.name[:-len(".tmp")]))

    anomalies = [a for lang in [REFERENCE_LANG] + others for a in results[lang][2]]
    counts = {lang: results[lang][:2] for lang in results}

    write_csv(out / "anomalies.csv", ANOMALY_COLS, ([a[k] for k in ANOMALY_COLS] for a in anomalies))
    by_issue = {}
    for a in anomalies:
        issue = a["issue"]
        by_issue.setdefault(issue, {}).setdefault(a["lang"], 0)
        by_issue[issue][a["lang"]] += 1
    return {
        "script_version": VERSION,
        "run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "delivery_form": "zip",
        "reference_lang": REFERENCE_LANG,
        "stories": sum(n for n, _ in counts.values()),
        "pages": sum(p for _, p in counts.values()),
        "stories_by_lang": {lang: counts[lang][0] for lang in sorted(counts)},
        "anomalies": len(anomalies),
        "anomalies_by_issue_and_lang": by_issue,
        "id_source": source,
        "files": files,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zips", type=Path, nargs="+", default=ZIPS, help="the zip files of 26 October 2026")
    ap.add_argument("--ids", type=Path, default=DELIVERY / "StoryReview" / "id_map.json",
                    help="the viewer's id_map.json, which gives each story its Story ID")
    ap.add_argument("--viewer", type=Path, nargs="?", const=DELIVERY / "StoryReview",
                    help="read the 1 October viewer (default folder if no path is given) instead of the zip files")
    ap.add_argument("--out", type=Path, default=DELIVERY / "extracted", help="output folder")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1),
                    help="languages compressed at once after English, about 100 MB of memory each")
    ap.add_argument("--version", action="version", version=VERSION)
    args = ap.parse_args()

    if args.viewer is None:
        if not args.zips:
            sys.exit(f"Stopped, nothing written: no zip files in {DELIVERY}")
        try:
            record = extract_zips(args.zips, args.ids, args.out, args.workers)
        except (OSError, ValueError, zipfile.BadZipFile, ExtractionError) as e:
            sys.exit(f"Stopped, no table written: {e}")
        (args.out / "extraction_record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                                                         encoding="utf-8")
        print(f"{record['stories']:,} stories in {len(record['stories_by_lang'])} languages, "
              f"{record['anomalies']:,} anomalies, listed in anomalies.csv")
        print(f"Written to {args.out}")
        return

    try:
        index, chunks, files = read_viewer(args.viewer)
        stories = build_stories(index, chunks)
    except (OSError, ValueError, ExtractionError) as e:
        sys.exit(f"Stopped, nothing written: {e}")

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "stories.csv", STORY_COLS, ([s[k] for k in STORY_COLS] for s in stories))
    write_csv(args.out / "pages.csv", ["id", "lang", "page", "page_label", "text"],
              ([s["id"], s["lang"], n, label, body]
               for s in stories for n, (label, body) in enumerate(s["_pages"], 1)))
    anomalies = [a for s in stories for a in find_anomalies(s)]
    write_csv(args.out / "anomalies.csv", ANOMALY_COLS, ([a[k] for k in ANOMALY_COLS] for a in anomalies))

    record = {
        "script_version": VERSION,
        "run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "delivery_form": "viewer",
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
