"""Reading tables in the catalogue's published schema.

The schema is extract_story_texts.py's STORY_COLS: id, folder, the seven metadata fields (hero,
world, theme, prompt, sidekick, age, lang), title, pages, words, build_error and text, one row per
story, as .csv or xz-compressed .csv.xz. The text column holds each zip file exactly as delivered:
"The first line of a file is the story's title and each further line is one page", and "A line break
inside a page is written as the two characters \\n". split_lines(), PAGE_RE, the two title-line checks
of zip_anomalies() and parse_folder()'s classic rule are copied from the extraction (story_texts/
extract_story_texts.py at commit 5227d8b, git blob b6527e0; SHA-256 fde0c10ce3134c06... as committed,
75e1f2a0795e2584... in a Windows checkout with CRLF line endings), and tests/unit/test_io.py checks
that the copies behave identically to the script in the working tree.

This module reads rows and maps them to the parts of a records.Document. It applies neither the
catalogue lock (lock.py) nor the normalisation (text/normalise.py): stages/documents.py applies both,
in that order, before anything else is computed on a text. The protocol commits that "No linguistic
feature registered here has been computed on the story texts, and none will be before in-principle
acceptance" (Data provenance, sequestration and outcome blindness), so nothing here points at them by
default, and the tests run on synthetic tables.
"""

from __future__ import annotations

import csv
import lzma
import re
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

META_KEYS = ["hero", "world", "theme", "prompt", "sidekick", "age", "lang"]
STORY_COLS = ["id", "folder", *META_KEYS, "title", "pages", "words", "build_error", "text"]

# The extraction's escape for a line break inside a page.
LINE_BREAK = "\\n"

# extract_story_texts.parse_folder: a classic's folder is named "PD_<tale> <age>", and its hero
# field is set to "Public domain".
CLASSIC_PREFIX = "PD_"
CLASSIC_HERO = "Public domain"

SUFFIXES = (".csv", ".csv.xz")

# A classic's text can exceed the csv module's default field limit of 128 KB. 2**31 - 1 is the
# largest value a C long holds on Windows, where sys.maxsize overflows it.
FIELD_SIZE_LIMIT = 2**31 - 1

# The page marker of the data controller's build script, copied verbatim by the extraction, which
# uses it to report a title line that holds a page marker in place of a title. The 1 October viewer's
# texts (the table published on 18 October 2026) mark every page with it.
PAGE_RE = re.compile(r"^\s*Page\s+\d+\s*:\s*", re.IGNORECASE | re.MULTILINE)

# The issues zip_anomalies() reports about a title line, in its words.
EMPTY_TITLE = "empty title"
PAGE_MARKER_TITLE = "title line is a page marker"


class CatalogueFormatError(ValueError):
    """A table or row that does not follow the published schema."""


def split_lines(text):
    """Return (title, [page texts]) for a text in the zip files' form.

    A line break inside a page or title is written as the two characters \\n, where the
    1 October viewer held a real line break, so each is decoded back into one."""
    # Copied verbatim from story_texts/extract_story_texts.py (commit 5227d8b), so that a text divides
    # into exactly the pages the published extraction recovers. Keep it unchanged.
    body = text.replace("\r\n", "\n")
    if body.endswith("\n"):
        body = body[:-1]
    lines = [line.replace(LINE_BREAK, "\n") for line in body.split("\n")]
    return lines[0], lines[1:]


@dataclass(frozen=True)
class CatalogueRow:
    """One row of a table in the published schema, split into its title line and pages.

    `title_line` and `pages` are as delivered, with the line-break escapes decoded and nothing
    normalised. `catalogue_words` is the table's own `words` column, the viewer's whitespace count
    (str.split over the pages joined with spaces), which is not the registered word count;
    `words_consistent` says whether the row's pages reproduce it.
    """

    story_id: str
    lang: str
    level: str
    kind: str
    title_line: str
    pages: tuple[str, ...]
    catalogue_words: int
    words_consistent: bool
    meta: dict = field(default_factory=dict, compare=False)


def open_text(path: Path) -> TextIO:
    """Open a .csv or .csv.xz table as UTF-8 text for the csv module (a byte order mark is skipped)."""
    path = Path(path)
    name = path.name.lower()
    if name.endswith(".csv.xz"):
        return lzma.open(path, "rt", encoding="utf-8-sig", newline="")
    if name.endswith(".csv"):
        return open(path, encoding="utf-8-sig", newline="")
    raise CatalogueFormatError(f"{path.name}: a table must be one of {', '.join(SUFFIXES)}")


def read_rows(path: Path) -> Iterator[dict[str, str]]:
    """Yield each row of a .csv or .csv.xz table as a dict keyed by column name (iter_rows)."""
    with open_text(path) as fh:
        yield from iter_rows(fh, Path(path).name)


def iter_rows(fh: TextIO, name: str) -> Iterator[dict[str, str]]:
    """Yield each row of a table open as text, checking the schema as it reads.

    Every column of STORY_COLS must be present; further columns are passed through. A blank line
    holds no field and is skipped. Any other row whose field count differs from the header's stops
    the read. `name` labels the table in error messages.
    """
    csv.field_size_limit(FIELD_SIZE_LIMIT)
    reader = csv.reader(fh)
    try:
        header = next(reader)
    except StopIteration:
        raise CatalogueFormatError(f"{name}: the table is empty") from None
    missing = [c for c in STORY_COLS if c not in header]
    if missing:
        raise CatalogueFormatError(f"{name}: columns {missing} of the published schema are missing")
    if len(set(header)) != len(header):
        raise CatalogueFormatError(f"{name}: a column name is repeated in the header")
    for row in reader:
        if not row:
            continue
        if len(row) != len(header):
            raise CatalogueFormatError(f"{name}, line {reader.line_num}: {len(row)} fields where the header has "
                                       f"{len(header)}, so the row does not follow the published schema")
        yield dict(zip(header, row, strict=True))


def title_line_issue(title_line: str) -> str | None:
    """What the extraction's zip_anomalies() reports about a title line, or None.

    EMPTY_TITLE for a blank line, PAGE_MARKER_TITLE for a line that starts with a page marker, the
    first line of a page taken for the title, in which case that page is missing from the pages.
    """
    if not title_line.strip():
        return EMPTY_TITLE
    if PAGE_RE.match(title_line):
        return PAGE_MARKER_TITLE
    return None


def kind_of(row: dict[str, str]) -> str:
    """Return "classic" for a folder named PD_..., as extract_story_texts.parse_folder reads it, else "generated".

    parse_folder sets the hero field to "Public domain" for exactly those folders, so a row whose
    hero and folder disagree does not follow the published schema.
    """
    classic = row["folder"].startswith(CLASSIC_PREFIX)
    if classic != (row["hero"] == CLASSIC_HERO):
        raise CatalogueFormatError(f"story {row['id']!r}: folder {row['folder']!r} and hero {row['hero']!r} "
                                   f"disagree on whether it is a classic")
    return "classic" if classic else "generated"


def level_of(row: dict[str, str], levels: Collection[str]) -> str:
    """The reading level from the age field, lower-cased; an empty age stays an empty level."""
    level = row["age"].strip().lower()
    if level and level not in levels:
        raise CatalogueFormatError(f"story {row['id']!r}: age {row['age']!r} is none of the levels {sorted(levels)}")
    return level


def _integer(row: dict[str, str], column: str) -> int:
    try:
        return int(row[column])
    except ValueError:
        raise CatalogueFormatError(f"story {row['id']!r}: {column} {row[column]!r} is not an integer") from None


def parse_row(row: dict[str, str], *, levels: Collection[str],
              split: tuple[str, Sequence[str]] | None = None) -> CatalogueRow:
    """Split a row's text into its title line and pages and check the row against its own counts.

    `split` passes split_lines(row["text"]) when the caller has already made it, as the documents
    stage does so that the lock sees each row before anything else is computed on it.
    """
    story_id = row["id"].strip()
    if not story_id or story_id != row["id"]:
        raise CatalogueFormatError(f"story id {row['id']!r} is empty or carries surrounding whitespace")
    if not row["lang"]:
        raise CatalogueFormatError(f"story {story_id!r} has no lang")
    title_line, pages = split if split is not None else split_lines(row["text"])
    declared_pages = _integer(row, "pages")
    if declared_pages != len(pages):
        raise CatalogueFormatError(f"story {story_id!r}: the pages column gives {declared_pages}, "
                                   f"the text holds {len(pages)}")
    catalogue_words = _integer(row, "words")
    meta = {k: row[k] for k in ("folder", "hero", "world", "theme", "prompt", "sidekick", "age")}
    meta.update(catalogue_title=row["title"], catalogue_words=catalogue_words, build_error=row["build_error"])
    return CatalogueRow(story_id=story_id, lang=row["lang"], level=level_of(row, levels), kind=kind_of(row),
                        title_line=title_line, pages=tuple(pages), catalogue_words=catalogue_words,
                        words_consistent=catalogue_words == len(" ".join(pages).split()), meta=meta)
