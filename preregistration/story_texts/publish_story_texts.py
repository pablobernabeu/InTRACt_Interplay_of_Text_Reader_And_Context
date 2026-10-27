"""
Write the story texts in the form this repository publishes, or check that form.

WHAT IT READS
The tables extract_story_texts.py writes into the git-ignored delivery: anomalies.csv,
extraction_record.json and the stories, either as one stories.csv (the viewer of
1 October 2026) or as one compressed table per language in stories/ (the zip files of
26 October 2026). The record's delivery_form says which.

WHAT IT WRITES
Into data/ beside this file:

    <lang>/stories.csv.xz    the rows of stories.csv in one language, xz-compressed. Each
                             decompresses to exactly the bytes the extraction wrote for
                             those rows, under the same header
    anomalies.csv            copied unchanged
    extraction_record.json   the extraction's record without viewer_source, the data
                             controller's path to the folder it built the viewer from
    manifest.json            the size and SHA-256 of every file above, and for each
                             language its story count and the SHA-256 of its table
                             uncompressed

pages.csv is not published. It holds the same texts split at their page markers, and
split_pages() in extract_story_texts.py reproduces it from the text column.

The texts in the app's other languages are published the same way: run the extraction
on the delivery that holds them, then this script. A delivery is expected to hold every
language, English included, because the record and the anomalies list describe one
extraction. The run stops if data/ already holds a language the extraction lacks.

HOW IT CHECKS ITSELF
Before writing, the run confirms that rewriting the extraction's stories row by row
reproduces their bytes exactly, so each language's table holds its rows as extracted,
and that the counts per language match the extraction record. A table the extraction
already compressed is also checked to hold rows in its own language only, and is
copied byte for byte. --check reads data/ alone and
confirms that every file has the size and checksum the manifest gives, that each table
decompresses to its recorded checksum and story count with every row in its own
language, that the languages and counts agree with the record, and that data/ holds no
file the manifest does not list. The Check workflow runs it on every push. Either form
stops with exit status 1 on any failure.

HOW TO RUN
    python publish_story_texts.py
    python publish_story_texts.py --extracted D:/extracted
    python publish_story_texts.py --check

Standard library only, Python 3.8 or later.
"""
import argparse
import csv
import hashlib
import json
import lzma
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXTRACTED = HERE.parent / "Oxford-40k-stories" / "extracted"
DATA = HERE / "data"
TABLE = "stories.csv.xz"
DROPPED = ("viewer_source",)

# A public-domain text can exceed the csv module's default field limit of 128 KB.
csv.field_size_limit(2**31 - 1)


class PublishError(Exception):
    pass


class Sink:
    """A target for csv.writer that hashes what it is given and, optionally, compresses it."""

    def __init__(self, path=None):
        self.sha = hashlib.sha256()
        self.bytes = 0
        self.xz = lzma.open(path, "wb", preset=9) if path else None

    def write(self, s):
        b = s.encode("utf-8")
        self.sha.update(b)
        self.bytes += len(b)
        if self.xz:
            self.xz.write(b)

    def close(self):
        if self.xz:
            self.xz.close()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def describe(path):
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def rewrite(stories, sink, lang=None):
    """Write the rows of stories.csv in `lang` (every row if None) to sink; return the count."""
    with open(stories, encoding="utf-8", newline="") as f:
        rows = csv.reader(f)
        header = next(rows)
        col = header.index("lang")
        w = csv.writer(sink)
        w.writerow(header)
        n = 0
        for row in rows:
            if lang is None or row[col] == lang:
                w.writerow(row)
                n += 1
    sink.close()
    return n


def write_text(path, text):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def decompressed(path):
    """Return (bytes, SHA-256) of an xz file's content."""
    sha, size = hashlib.sha256(), 0
    with lzma.open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            sha.update(block)
            size += len(block)
    return size, sha.hexdigest()


def verify_table(path, lang):
    """Confirm that a compressed table rewrites to itself with every row in `lang`; return its row count."""
    sink, n = Sink(), 0
    with lzma.open(path, "rt", encoding="utf-8", newline="") as f:
        rows = csv.reader(f)
        header = next(rows)
        col = header.index("lang")
        w = csv.writer(sink)
        w.writerow(header)
        for row in rows:
            if row[col] != lang:
                raise PublishError(f"{path.name}: a row in {row[col]!r}")
            w.writerow(row)
            n += 1
    if (sink.bytes, sink.sha.hexdigest()) != decompressed(path):
        raise PublishError(f"{path.name}: rewriting the table does not reproduce it")
    return n


def publish(extracted):
    record = json.loads((extracted / "extraction_record.json").read_text(encoding="utf-8"))
    langs = {k: v for k, v in record["stories_by_lang"].items() if v}
    present = {p.name for p in DATA.iterdir() if p.is_dir()} if DATA.exists() else set()
    if present - set(langs):
        raise PublishError(f"data/ holds {sorted(present - set(langs))}, which this extraction lacks")

    manifest = {"languages": {}, "files": {}}
    if record.get("delivery_form") == "zip":
        # The extraction already wrote one compressed table per language. Each is checked
        # and copied byte for byte, so the published file is the extraction's.
        for lang, expected in langs.items():
            source = extracted / "stories" / f"{lang}.csv.xz"
            n = verify_table(source, lang)
            if n != expected:
                raise PublishError(f"{lang}: {n} stories, the record gives {expected}")
            folder = DATA / lang
            folder.mkdir(parents=True, exist_ok=True)
            target, tmp = folder / TABLE, folder / (TABLE + ".tmp")
            tmp.write_bytes(source.read_bytes())
            if sha256(tmp) != sha256(source):
                tmp.unlink()
                raise PublishError(f"{lang}: the copy differs from the extraction's table")
            os.replace(tmp, target)
            size, sha = decompressed(target)
            manifest["languages"][lang] = dict(file=f"{lang}/{TABLE}", stories=n, **describe(target),
                                               uncompressed_bytes=size, uncompressed_sha256=sha)
            print(f"{lang}: {n:,} stories, {target.stat().st_size / 2**20:.1f} MB")
    else:
        stories = extracted / "stories.csv"
        whole = Sink()
        if rewrite(stories, whole) != record["stories"] or whole.sha.hexdigest() != sha256(stories):
            raise PublishError("rewriting stories.csv does not reproduce it, or its row count differs from the record")
        for lang, expected in langs.items():
            folder = DATA / lang
            folder.mkdir(parents=True, exist_ok=True)
            target, tmp = folder / TABLE, folder / (TABLE + ".tmp")
            sink = Sink(tmp)
            n = rewrite(stories, sink, lang)
            if n != expected:
                tmp.unlink()
                raise PublishError(f"{lang}: {n} stories, the record gives {expected}")
            os.replace(tmp, target)
            manifest["languages"][lang] = dict(file=f"{lang}/{TABLE}", stories=n, **describe(target),
                                               uncompressed_bytes=sink.bytes,
                                               uncompressed_sha256=sink.sha.hexdigest())
            print(f"{lang}: {n:,} stories, {target.stat().st_size / 2**20:.1f} MB")

    tmp = DATA / "anomalies.csv.tmp"
    tmp.write_bytes((extracted / "anomalies.csv").read_bytes())
    os.replace(tmp, DATA / "anomalies.csv")
    public = {k: v for k, v in record.items() if k not in DROPPED}
    write_text(DATA / "extraction_record.json", json.dumps(public, indent=2, ensure_ascii=False) + "\n")
    for name in ("anomalies.csv", "extraction_record.json"):
        manifest["files"][name] = describe(DATA / name)
    write_text(DATA / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    print(f"Written to {DATA}")


def check():
    problems = []
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    record = json.loads((DATA / "extraction_record.json").read_text(encoding="utf-8"))
    listed = {"manifest.json"}
    entries = [(e["file"], e) for e in manifest["languages"].values()] + list(manifest["files"].items())
    for name, entry in entries:
        listed.add(name)
        path = DATA / name
        if not path.is_file():
            problems.append(f"{name}: missing")
        elif describe(path) != {"bytes": entry["bytes"], "sha256": entry["sha256"]}:
            problems.append(f"{name}: size or checksum differs from the manifest")

    for lang, entry in manifest["languages"].items():
        path = DATA / entry["file"]
        if not path.is_file():
            continue
        sha, size, n, foreign = hashlib.sha256(), 0, 0, 0
        with lzma.open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                sha.update(block)
                size += len(block)
        with lzma.open(path, "rt", encoding="utf-8", newline="") as f:
            rows = csv.reader(f)
            col = next(rows).index("lang")
            for row in rows:
                n += 1
                foreign += row[col] != lang
        if (size, sha.hexdigest()) != (entry["uncompressed_bytes"], entry["uncompressed_sha256"]):
            problems.append(f"{entry['file']}: decompresses to a different table than the manifest records")
        if n != entry["stories"] or foreign:
            problems.append(f"{entry['file']}: {n} stories, {foreign} in another language; the manifest gives "
                            f"{entry['stories']}")

    in_record = {k: v for k, v in record["stories_by_lang"].items() if v}
    if in_record != {k: e["stories"] for k, e in manifest["languages"].items()}:
        problems.append("the stories per language differ between the record and the manifest")
    if record["stories"] != sum(in_record.values()):
        problems.append("the record's story total differs from its count per language")
    on_disk = {p.relative_to(DATA).as_posix() for p in DATA.rglob("*") if p.is_file()}
    for extra in sorted(on_disk - listed):
        problems.append(f"{extra}: in data/ but not in the manifest")

    for line in problems:
        print(line)
    total = sum(e["stories"] for e in manifest["languages"].values())
    print(f"{total:,} stories in {len(manifest['languages'])} language(s), {len(problems)} problem(s)")
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extracted", type=Path, default=EXTRACTED, help="the extraction's output folder")
    ap.add_argument("--check", action="store_true", help="check data/ instead of writing it")
    args = ap.parse_args()
    if args.check:
        return check()
    try:
        publish(args.extracted)
    except (OSError, ValueError, KeyError, PublishError) as e:
        sys.exit(f"Stopped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
