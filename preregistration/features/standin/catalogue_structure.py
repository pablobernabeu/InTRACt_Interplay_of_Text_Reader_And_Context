"""Structure-only table of the published English story table, written and read back.

The stand-in builder (build_standin.py) matches public stories to the English catalogue's
structure: each text's story id, kind, level, number of pages and whitespace tokens on
each page. This module writes that table from the published English story table
(story_texts/data/en-us/stories.csv.xz, in the extraction's STORY_COLS schema) and reads it
back for the builder.

It is a structural count, not a feature. The protocol commits that "No linguistic feature
registered here has been computed on the story texts, and none will be before in-principle
acceptance" (preregistration.qmd, Data provenance, sequestration and outcome blindness).
This module reads the text column only to divide it into pages and count whitespace tokens
and characters. It prints no text and writes none, and its output holds identifiers and
numbers only. It must not be extended to compute anything else on the story texts, and it
is tested on synthetic tables only. Running it on a published table is still a computation
on the story texts, so it needs the PI's go-ahead, recorded in the lab log and in the
sequestration disclosure, before it is run; the dry run uses the scout's table of
2 November 2026 as it is (jobs/arc/README.md, Prerequisites).

The table it writes reproduces, column for column and byte for byte, the structure table
that the English-pipeline scout wrote on 2 November 2026 (en_per_text_structure.tsv):

    id  kind  level  pages  tokens  chars_joined  tokens_per_page  chars_per_page

tab-separated with a header line, rows in the input's order. `kind` is "classic" when the
hero is "Public domain" and "generated" otherwise, and `level` is the reading level, with
"(blank)" where the catalogue leaves it empty. Pages are recovered as the extraction's
split_lines() recovers them: the first line of `text` is the title and each further line
is a page, with the two-character escape backslash-n decoded to a line break. The title is
excluded from every count, as the extraction's `words` column excludes it. `chars_joined`
counts the characters of the pages joined with one space (Materials: "Pages are joined
with a single space"), before the registered normalisation. The last two columns hold the
per-page counts separated by spaces.

With --with-combination a ninth column, `combination`, gives every text the id of the
first text (in table order) that shares its story: the same five attributes for a
generated text, the same tale for a classic. The builder uses it so that the young, mid
and old versions of one story share one synthetic story key. It adds a grouping of ids
already in the table and nothing else, and without it the table matches the scout's.

Usage (the main session runs it, once authorised; the tests use synthetic tables only):

    python -m standin.catalogue_structure STORIES.csv.xz OUT.tsv --authorisation TEXT [--with-combination]

--authorisation is required, as it is for lock_build.py: one line naming the PI's recorded
go-ahead (the lab-log entry). The command refuses to run without it, prints it, and writes it
with the source file's SHA-256 and the checks into OUT.tsv.authorisation.json beside the table,
which keeps the table itself byte-identical to the scout's.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import lzma
import re
import sys
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# The published schema, copied from story_texts/extract_story_texts.py so that the stand-in
# writes rows any reader of the published tables can read.
META_KEYS = ["hero", "world", "theme", "prompt", "sidekick", "age", "lang"]
STORY_COLS = ["id", "folder", *META_KEYS, "title", "pages", "words", "build_error", "text"]
# extract_story_texts.py: PD_HERO, the hero of every classic, and the escape it decodes.
CLASSIC_HERO = "Public domain"
LINE_BREAK = "\\n"
# extract_story_texts.py: PD_AGE_RE, the age suffix of a classic's folder name, so that the
# young and old versions of one tale group together.
PD_AGE_RE = re.compile(r"[\s_]*(old|young)(\s+current)?$", re.IGNORECASE)
# The scout's table writes an empty level as this label (length_profile.py).
BLANK_LEVEL = "(blank)"

STRUCTURE_COLS = ["id", "kind", "level", "pages", "tokens", "chars_joined", "tokens_per_page", "chars_per_page"]
COMBINATION_COL = "combination"

csv.field_size_limit(2**31 - 1)


class StructureError(ValueError):
    """A structure table that is malformed, inconsistent or not a structure table at all."""


@dataclass(frozen=True)
class Target:
    """One catalogue text as the stand-in sees it: identifiers and counts, never text."""

    story_id: str
    kind: str  # "generated" or "classic"
    level: str  # "" where the catalogue leaves the level empty
    tokens_per_page: tuple[int, ...]
    chars_joined: int | None = None
    combination: str = ""  # shared by the versions of one story

    @property
    def pages(self) -> int:
        """P, the number of pages."""
        return len(self.tokens_per_page)

    @property
    def tokens(self) -> int:
        """T, the whitespace tokens of all pages, the title excluded."""
        return sum(self.tokens_per_page)


def split_lines(text: str) -> tuple[str, list[str]]:
    """Return (title, [page texts]) for a text in the delivery's form.

    Copied verbatim from story_texts/extract_story_texts.py, so that a text divides into
    pages here exactly as the extraction divides it. A line break inside a page is written
    as the two characters backslash-n and decoded back into one.
    """
    body = text.replace("\r\n", "\n")
    if body.endswith("\n"):
        body = body[:-1]
    lines = [line.replace(LINE_BREAK, "\n") for line in body.split("\n")]
    return lines[0], lines[1:]


def _combination_key(row: dict) -> tuple[str, ...]:
    if row["hero"] == CLASSIC_HERO:
        return ("classic", PD_AGE_RE.sub("", row["folder"]))
    return ("generated", row["hero"], row["world"], row["theme"], row["prompt"], row["sidekick"])


def iter_structure(stories: Path, with_combination: bool = False, counts: Counter | None = None) -> Iterator[list]:
    """Yield one structure row per text of a published story table (STORY_COLS, xz-compressed CSV).

    `counts`, if given, collects the table's consistency checks and page maxima, numbers only.
    """
    first_of: dict[tuple[str, ...], str] = {}
    with lzma.open(stories, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = set(STORY_COLS) - set(reader.fieldnames or [])
        if missing:
            raise StructureError(f"{stories.name} lacks the columns {sorted(missing)} of the published schema")
        for row in reader:
            _, pages = split_lines(row["text"])
            kind = "classic" if row["hero"] == CLASSIC_HERO else "generated"
            level = row["age"] or BLANK_LEVEL
            ptok = [len(page.split()) for page in pages]
            pchar = [len(page) for page in pages]
            tokens = sum(ptok)
            chars = sum(pchar) + max(0, len(pages) - 1)
            if counts is not None:
                counts["texts"] += 1
                counts[f"texts|{kind}|{level}"] += 1
                counts["words_column_mismatches"] += str(tokens) != row["words"]
                counts["pages_column_mismatches"] += str(len(pages)) != row["pages"]
                counts["empty_pages"] += sum(1 for x in ptok if x == 0)
                counts["max_tokens_per_page"] = max(counts["max_tokens_per_page"], max(ptok, default=0))
                counts["max_chars_per_page"] = max(counts["max_chars_per_page"], max(pchar, default=0))
            out = [row["id"], kind, level, len(pages), tokens, chars, " ".join(map(str, ptok)),
                   " ".join(map(str, pchar))]
            if with_combination:
                out.append(first_of.setdefault(_combination_key(row), row["id"]))
            yield out


def write_structure(stories: Path, out: Path, with_combination: bool = False) -> dict:
    """Write the structure table for a published story table and return its checks (numbers only).

    The file is written under a temporary name and renamed once complete, so an
    interrupted run never leaves a table that looks finished.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    counts: Counter = Counter()
    header = STRUCTURE_COLS + ([COMBINATION_COL] if with_combination else [])
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\t".join(header) + "\n")
            for row in iter_structure(Path(stories), with_combination, counts):
                fh.write("\t".join(map(str, row)) + "\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(out)
    return dict(sorted(counts.items()))


def _open_structure(path: Path):
    if path.name.endswith(".tsv.xz"):
        return lzma.open(path, "rt", encoding="utf-8", newline="")
    if path.suffix == ".tsv":
        return open(path, encoding="utf-8", newline="")
    raise StructureError(f"{path.name}: a structure table is a .tsv or .tsv.xz file")


def read_structure(path: Path) -> list[Target]:
    """Read a structure table back into Targets, checking every row.

    A file with a `text` column is refused before any row is read: the stand-in builder
    takes the catalogue's structure only and never its texts (Data provenance,
    sequestration and outcome blindness).
    """
    path = Path(path)
    targets: list[Target] = []
    seen: set[tuple[str, str]] = set()
    with _open_structure(path) as fh:
        header = fh.readline().rstrip("\r\n").split("\t")
        if "text" in header:
            raise StructureError(f"{path.name} has a text column; the stand-in reads structure only, never story text")
        extra = header[len(STRUCTURE_COLS):]
        if header[:len(STRUCTURE_COLS)] != STRUCTURE_COLS or extra not in ([], [COMBINATION_COL]):
            raise StructureError(f"{path.name}: expected the columns {STRUCTURE_COLS} (and optionally "
                                 f"{COMBINATION_COL!r}), found {header}")
        has_combination = len(header) > len(STRUCTURE_COLS)
        for lineno, line in enumerate(fh, start=2):
            fields = line.rstrip("\r\n").split("\t")
            if len(fields) != len(header):
                raise StructureError(f"{path.name}:{lineno}: {len(fields)} fields, expected {len(header)}")
            sid, kind, level, pages, tokens, chars, tpp = fields[:7]
            if kind not in ("generated", "classic"):
                raise StructureError(f"{path.name}:{lineno}: kind {kind!r}")
            try:
                per_page = tuple(int(x) for x in tpp.split())
                n_pages, n_tokens = int(pages), int(tokens)
                n_chars = int(chars) if chars else None
            except ValueError as e:
                raise StructureError(f"{path.name}:{lineno}: {e}") from e
            if not per_page or len(per_page) != n_pages or sum(per_page) != n_tokens or min(per_page) < 1:
                raise StructureError(f"{path.name}:{lineno}: pages and tokens per page disagree, or a page is empty")
            level = "" if level == BLANK_LEVEL else level
            if (sid, level) in seen:
                raise StructureError(f"{path.name}:{lineno}: story {sid} at level {level!r} appears twice")
            seen.add((sid, level))
            targets.append(Target(story_id=sid, kind=kind, level=level, tokens_per_page=per_page,
                                  chars_joined=n_chars, combination=fields[8] if has_combination else sid))
    if not targets:
        raise StructureError(f"{path.name} holds no rows")
    return targets


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Command line: write the structure table and print its checks (numbers only).

    Reading a published story table is a computation on the story texts, so the command
    runs only with --authorisation, which names the PI's recorded go-ahead and is written
    beside the table (module docstring).
    """
    p = argparse.ArgumentParser(prog="python -m standin.catalogue_structure", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stories", type=Path, help="the published English story table, stories.csv.xz")
    p.add_argument("out", type=Path, help="the structure table to write (.tsv)")
    p.add_argument("--with-combination", action="store_true",
                   help="append the combination column that groups the versions of one story")
    p.add_argument("--authorisation", required=True,
                   help="one line naming the PI's recorded go-ahead (the lab-log entry); required")
    args = p.parse_args(argv)
    authorisation = args.authorisation.strip()
    if not authorisation or "\n" in args.authorisation or "\r" in args.authorisation:
        print("Stopped, no table written: --authorisation must be one non-empty line", file=sys.stderr)
        return 1
    print(f"Authorised: {authorisation}")
    out = Path(args.out)
    try:
        source_sha256 = _sha256(args.stories)
        checks = write_structure(args.stories, out, args.with_combination)
    except (OSError, StructureError, lzma.LZMAError) as e:
        print(f"Stopped, no table written: {e}", file=sys.stderr)
        return 1
    record = {"authorisation": authorisation, "source": str(args.stories), "source_sha256": source_sha256,
              "table": out.name, "table_sha256": _sha256(out), "with_combination": args.with_combination,
              "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "checks": checks}
    sidecar = out.with_name(out.name + ".authorisation.json")
    tmp = sidecar.with_name(sidecar.name + ".tmp")
    tmp.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(sidecar)
    print(json.dumps(checks, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
