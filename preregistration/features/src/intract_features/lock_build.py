"""Build the catalogue lock's fingerprint files and its frozen checksum records.

    python -m intract_features.lock_build fingerprints --tables DIR --out CONFIG_DIR --authorisation TEXT
                                          [--langs en-us de-de ...] [--rev REV [--suffix S] [--repo PATH]]
    python -m intract_features.lock_build checksums --rev REV --out FILE [--folder F] [--repo PATH]

`fingerprints` reads each language's story table, <tables>/<lang>/stories.csv.xz (stories.csv if that
is what the folder holds), splits every text into its title line and pages with
io.catalogue.split_lines, as the extraction does, and writes <out>/catalogue_fingerprints_<label>.txt:
comment lines naming the fingerprint's definition, the source table, its SHA-256 and the
authorisation, then the fingerprints of every text (lock.listed_fingerprints), sorted and unique. The
label is the language, or <lang>-<suffix>. With no --langs, every folder of <tables> that holds a
table is read. With --rev, the tables are streamed from the repository's history at that revision,
with no copy written to disk, and --tables is their folder's path inside the repository; the suffix
then defaults to the revision's short commit id. The command ends by printing the labels written,
for [lock] required_fingerprints in config/stages/documents.toml.

`checksums` writes the checksums that one publication's manifest.json and extraction_record.json
record (<folder> at revision REV, by default preregistration/story_texts/data) into a frozen record
that [lock] manifests can list, so that the lock keeps refusing that publication's files after its
manifests are replaced. Only the checksums and the sources' provenance are written, never a count.

Running `fingerprints` on the published tables reads every story text: it applies the registered
normalisation and White_Space tokenisation and hashes the result. A fingerprint is not a registered
linguistic feature (Data provenance, sequestration and outcome blindness: "No linguistic feature
registered here has been computed on the story texts, and none will be before in-principle
acceptance"), but the run is a computation on the texts. It therefore needs the PI's go-ahead,
recorded in the lab log and in the sequestration disclosure, before it runs. --authorisation names
that record, and every file written carries it. Builders and tests run the command only on synthetic
tables. Every path is required, so nothing runs on a default location by accident.

For the published tables, the main session runs, once authorised:

    python -m intract_features.lock_build fingerprints --tables preregistration/story_texts/data \\
        --out preregistration/features/config --authorisation "<lab-log entry>"
    python -m intract_features.lock_build fingerprints --rev 03413a4 --suffix 2026-10-18 \\
        --tables preregistration/story_texts/data --langs en-us \\
        --out preregistration/features/config --authorisation "<lab-log entry>"
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import lzma
import re
import subprocess
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, TextIO

from intract_features.io.catalogue import iter_rows, open_text, split_lines
from intract_features.lock import (
    DEFAULT_CONFIG_DIR,
    EMPTY_FINGERPRINT,
    FINGERPRINT_HEX_DIGITS,
    FINGERPRINT_VERSION,
    listed_fingerprints,
    recorded_checksum_entries,
)
from intract_features.records import sha256_file

TABLE_NAMES = ("stories.csv.xz", "stories.csv")
OUTPUT = "catalogue_fingerprints_{label}.txt"
PUBLISHED_FOLDER = "preregistration/story_texts/data"
MANIFESTS = ("manifest.json", "extraction_record.json")
# The repository that holds this package: features/ lies inside it.
DEFAULT_REPO = DEFAULT_CONFIG_DIR.parent
# Labels and revisions become file names and git arguments, so they are kept to plain characters.
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_REV_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/^~-]*$")


class BuildError(RuntimeError):
    """A table, a revision or a manifest could not be read as the command needs."""


# ---------------------------------------------------------------- fingerprints of one table
def fingerprints_from_text(fh: TextIO, name: str) -> tuple[list[str], int]:
    """The sorted, unique listed fingerprints of every text of a table open as text, and the rows read."""
    found: set[str] = set()
    rows = 0
    for row in iter_rows(fh, name):
        rows += 1
        title_line, pages = split_lines(row["text"])
        found |= listed_fingerprints(title_line, pages)
    found.discard(EMPTY_FINGERPRINT)
    return sorted(found), rows


def fingerprints_of(table: Path) -> list[str]:
    """The sorted, unique listed fingerprints of every text in a table file, texts without a token left out."""
    with open_text(table) as fh:
        return fingerprints_from_text(fh, Path(table).name)[0]


def find_table(folder: Path) -> Path | None:
    """The story table a language folder holds, or None."""
    for name in TABLE_NAMES:
        if (folder / name).is_file():
            return folder / name
    return None


def write_fingerprints(path: Path, values: Sequence[str], *, source: str, source_sha256: str, rows: int,
                       authorisation: str) -> None:
    """Write a fingerprint file atomically: its header comments, then one fingerprint per line."""
    header = [
        f"# Catalogue lock fingerprints, version {FINGERPRINT_VERSION} (intract_features.lock.listed_fingerprints).",
        f"# Each line is the first {FINGERPRINT_HEX_DIGITS} hexadecimal digits of the SHA-256 of one reading of "
        "a text:",
        "# its White_Space tokens joined by one space, after the registered normalisation of each line.",
        "# A text gives its pages and, if it holds page markers, its lines with the markers removed.",
        f"# Source: {source}, SHA-256 {source_sha256}, rows {rows}.",
        f"# Authorised: {authorisation}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join([*header, *values]) + "\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)


# ---------------------------------------------------------------- reading the repository's history
def _git(repo: Path, *args: str) -> bytes:
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        raise BuildError(f"git {' '.join(args)} could not run: {e}") from e
    if done.returncode != 0:
        raise BuildError(f"git {' '.join(args)} failed: {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout


def git_toplevel(repo: Path) -> Path:
    """The top folder of the repository that holds `repo`."""
    return Path(_git(Path(repo), "rev-parse", "--show-toplevel").decode("utf-8").strip())


def git_commit(top: Path, rev: str) -> str:
    """The full id of the commit a revision names."""
    if not _REV_RE.match(rev):
        raise BuildError(f"{rev!r} is not a revision this command accepts")
    return _git(top, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").decode("ascii").strip()


def git_commit_date(top: Path, commit: str) -> str:
    """The commit's date, as YYYY-MM-DD."""
    return _git(top, "show", "-s", "--format=%cs", commit).decode("ascii").strip()


def git_tree(top: Path, commit: str, folder: str) -> list[tuple[str, str, str]]:
    """(type, object id, name) of each entry of a folder at a commit."""
    out = []
    for entry in _git(top, "ls-tree", "-z", f"{commit}:{folder}").split(b"\0"):
        if entry:
            meta, name = entry.split(b"\t", 1)
            _, kind, oid = meta.decode("ascii").split()
            out.append((kind, oid, name.decode("utf-8")))
    return out


def git_find_table(top: Path, commit: str, folder: str) -> tuple[str, str] | None:
    """(repository path, blob id) of the story table a language folder holds at a commit, or None."""
    blobs = {name: oid for kind, oid, name in git_tree(top, commit, folder) if kind == "blob"}
    for name in TABLE_NAMES:
        if name in blobs:
            return f"{folder}/{name}", blobs[name]
    return None


class _HashingReader(io.RawIOBase):
    """A raw reader that hashes every byte it passes on."""

    def __init__(self, raw: BinaryIO, digest):
        self._raw, self._digest = raw, digest

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        n = self._raw.readinto(b)
        if n:
            self._digest.update(memoryview(b)[:n])
        return n or 0


@contextmanager
def git_blob_text(top: Path, commit: str, path: str) -> Iterator[tuple[TextIO, object]]:
    """A blob at a commit, streamed from git and opened as UTF-8 text (decompressed for .xz).

    Yields the text stream and the SHA-256 object that sees the blob's bytes; the digest is complete
    once the block exits. Nothing is written to disk.
    """
    proc = subprocess.Popen(["git", "-C", str(top), "cat-file", "blob", f"{commit}:{path}"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    digest = hashlib.sha256()
    try:
        buffered = io.BufferedReader(_HashingReader(proc.stdout, digest), buffer_size=1 << 20)
        # No context manager: the readers stacked on the pipe must stay open until the pipe has been
        # drained below, and the finally block closes the pipe itself.
        binary = lzma.LZMAFile(buffered) if path.endswith(".xz") else buffered  # noqa: SIM115
        text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
        yield text, digest
        # Hash any bytes the reader left, so the digest is the blob's own.
        for _ in iter(lambda: buffered.read(1 << 20), b""):
            pass
        text.detach()
    finally:
        proc.stdout.close()
        error = proc.stderr.read().decode("utf-8", "replace").strip()
        proc.stderr.close()
        code = proc.wait()
    if code != 0:
        raise BuildError(f"git cat-file {commit}:{path} failed: {error}")


def published_checksums(top: Path, rev: str, folder: str = PUBLISHED_FOLDER,
                        files: Sequence[str] = MANIFESTS) -> dict:
    """The frozen checksum record of one publication: the SHA-256 values its manifests record, with provenance."""
    commit = git_commit(top, rev)
    sources, checksums = [], []
    for name in files:
        path = f"{folder}/{name}"
        data = _git(top, "cat-file", "blob", f"{commit}:{path}")
        try:
            obj = json.loads(data.decode("utf-8"))
        except ValueError as e:
            raise BuildError(f"{path} at {commit[:12]} is not JSON: {e}") from e
        entries = recorded_checksum_entries(obj)
        if not entries:
            raise BuildError(f"{path} at {commit[:12]} records no SHA-256")
        blob = _git(top, "rev-parse", "--verify", f"{commit}:{path}").decode("ascii").strip()
        sources.append({"file": name, "git_blob": blob, "bytes": len(data),
                        "file_sha256": hashlib.sha256(data).hexdigest()})
        checksums += [{"source": name, "key": key, "sha256": value} for key, value in entries]
    return {
        "what": ("The SHA-256 values one publication's story_texts/data manifests record, frozen so that the "
                 "catalogue lock (lock.py) keeps refusing that publication's files after later manifests replace "
                 "these. Written by `python -m intract_features.lock_build checksums`; only checksums and the "
                 "sources' provenance are kept."),
        "publication": {"commit": commit, "date": git_commit_date(top, commit), "folder": folder},
        "sources": sources,
        "checksums": checksums,
    }


def write_json(path: Path, obj: dict) -> None:
    """Write strict JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8",
                       newline="\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)


# ---------------------------------------------------------------- commands
def _label(value: str) -> str:
    if not _LABEL_RE.match(value):
        raise BuildError(f"{value!r} cannot label a fingerprint file (letters, digits, '.', '_' and '-' only)")
    return value


def _repo_folder(top: Path, tables: Path) -> str:
    """--tables as a path inside the repository, in git's form."""
    if tables.is_absolute():
        try:
            return tables.resolve().relative_to(top.resolve()).as_posix()
        except ValueError:
            raise BuildError(f"--tables {tables} is not inside the repository {top}") from None
    return tables.as_posix().strip("/")


def run_fingerprints(args: argparse.Namespace) -> list[str]:
    """Write the fingerprint files; return the labels written."""
    if "\n" in args.authorisation or "\r" in args.authorisation or not args.authorisation.strip():
        raise BuildError("--authorisation must be one non-empty line")
    written = []
    if args.rev is None:
        if args.suffix is not None:
            raise BuildError("--suffix applies to tables read with --rev")
        if not args.tables.is_dir():
            raise BuildError(f"--tables {args.tables} is not a folder")
        langs = args.langs or sorted(d.name for d in args.tables.iterdir() if d.is_dir() and find_table(d))
        if not langs:
            raise BuildError(f"no folder of {args.tables} holds a story table")
        for lang in langs:
            table = find_table(args.tables / lang)
            if table is None:
                raise BuildError(f"{args.tables / lang} holds no story table")
            with open_text(table) as fh:
                values, rows = fingerprints_from_text(fh, table.name)
            label = _label(lang)
            out = args.out / OUTPUT.format(label=label)
            write_fingerprints(out, values, source=f"{lang}/{table.name}", source_sha256=sha256_file(table),
                               rows=rows, authorisation=args.authorisation.strip())
            print(f"{out}: fingerprints written: {len(values)}")
            written.append(label)
        return written

    top = git_toplevel(args.repo)
    commit = git_commit(top, args.rev)
    folder = _repo_folder(top, args.tables)
    suffix = _label(args.suffix or commit[:7])
    langs = args.langs or sorted(name for kind, _, name in git_tree(top, commit, folder)
                                 if kind == "tree" and git_find_table(top, commit, f"{folder}/{name}"))
    if not langs:
        raise BuildError(f"no folder of {folder} at {commit[:12]} holds a story table")
    for lang in langs:
        found = git_find_table(top, commit, f"{folder}/{lang}")
        if found is None:
            raise BuildError(f"{folder}/{lang} at {commit[:12]} holds no story table")
        path, blob = found
        with git_blob_text(top, commit, path) as (fh, digest):
            values, rows = fingerprints_from_text(fh, path)
        label = _label(f"{lang}-{suffix}")
        out = args.out / OUTPUT.format(label=label)
        write_fingerprints(out, values, source=f"git {commit[:12]}:{path} (blob {blob})",
                           source_sha256=digest.hexdigest(), rows=rows, authorisation=args.authorisation.strip())
        print(f"{out}: fingerprints written: {len(values)}")
        written.append(label)
    return written


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point; returns the exit status."""
    p = argparse.ArgumentParser(prog="intract_features.lock_build", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fingerprints", help="write catalogue_fingerprints_<label>.txt from story tables")
    f.add_argument("--tables", type=Path, required=True,
                   help="folder holding <lang>/stories.csv.xz (with --rev, its path inside the repository)")
    f.add_argument("--out", type=Path, required=True, help="folder to write catalogue_fingerprints_<label>.txt in")
    f.add_argument("--authorisation", required=True,
                   help="where the PI's go-ahead for this run is recorded (for example a lab-log entry)")
    f.add_argument("--langs", nargs="+", help="locales to read (default: every folder holding a table)")
    f.add_argument("--rev", help="read the tables from the repository's history at this revision")
    f.add_argument("--suffix", help="label suffix for tables read with --rev (default: the short commit id)")
    f.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="a folder inside the repository (with --rev)")
    c = sub.add_parser("checksums", help="freeze the checksums of one publication's manifests")
    c.add_argument("--rev", required=True, help="the commit of the publication")
    c.add_argument("--out", type=Path, required=True, help="the JSON file to write")
    c.add_argument("--folder", default=PUBLISHED_FOLDER, help="the manifests' folder inside the repository")
    c.add_argument("--files", nargs="+", default=list(MANIFESTS), help="the manifest files to read")
    c.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="a folder inside the repository")
    args = p.parse_args(argv)

    try:
        if args.cmd == "fingerprints":
            labels = run_fingerprints(args)
            print("Labels written, for [lock] required_fingerprints in config/stages/documents.toml: "
                  + json.dumps(labels))
        else:
            record = published_checksums(git_toplevel(args.repo), args.rev, args.folder, args.files)
            write_json(args.out, record)
            print(f"{args.out}: checksums written: {len(record['checksums'])} from {record['publication']['commit']}")
    except BuildError as e:
        p.error(str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
