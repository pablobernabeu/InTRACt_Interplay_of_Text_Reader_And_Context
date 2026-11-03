"""Tests of io.catalogue, on synthetic tables only.

The extraction script's definitions (story_texts/extract_story_texts.py) are read from its source with
ast and executed alone. The script is never imported, because importing it lists the delivery folder,
and none of its data is opened. The parse artefacts' CoNLL-U has one reader and writer,
intract_features.parse, tested in test_parse.py.
"""

import ast
import csv
import lzma
import random
import re
from pathlib import Path

import pytest

from intract_features.io import catalogue

EXTRACT = Path(__file__).resolve().parents[3] / "story_texts" / "extract_story_texts.py"
LEVELS = frozenset({"young", "mid", "old"})


def extraction(names):
    """Run the named top-level definitions of the extraction script, in file order, in a fresh namespace."""
    if not EXTRACT.is_file():
        pytest.skip(f"{EXTRACT} is not in this checkout")
    tree = ast.parse(EXTRACT.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
             or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) in names for t in n.targets))]
    found = {n.name if isinstance(n, ast.FunctionDef) else n.targets[0].id for n in nodes}
    assert found == set(names), f"the extraction script no longer defines {set(names) - found}"
    namespace = {"re": re}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(EXTRACT), "exec"), namespace)
    return namespace


# ---- the published schema and the extraction's rules ----
def test_schema_is_the_extractions():
    ns = extraction({"META_KEYS", "STORY_COLS"})
    assert ns["STORY_COLS"] == catalogue.STORY_COLS
    assert ns["META_KEYS"] == catalogue.META_KEYS


PIECES = ["Title", "“A Tale”", "Once upon a time.", "Tom ran.", "\n", "\n", "\r\n", "\\n", "\\n", "\\", "\r",
          " ", "  ", "\t", "\xe9", "e\N{COMBINING ACUTE ACCENT}", "\N{ZERO WIDTH SPACE}", "Page 3: x", "", "\\\\n"]


def synthetic_texts(n=3000, seed=20261103):
    rng = random.Random(seed)
    fixed = ["", "\n", "Title", "Title\n", "Title\nPage one.", "Title\nPage one.\n", "Title\r\nOne\r\nTwo\r\n",
             "Title\nOne\\nstill one\nTwo", "Title\n\nEmpty page above", "T\\nitle\nP", "Title\nback\\slash",
             "Title\nOne\n\n", "Title\rNot a break\nPage"]
    return fixed + ["".join(rng.choice(PIECES) for _ in range(rng.randint(0, 25))) for _ in range(n)]


def test_split_lines_is_the_extractions():
    ref = extraction({"LINE_BREAK", "split_lines"})["split_lines"]
    for text in synthetic_texts():
        assert catalogue.split_lines(text) == ref(text), repr(text)


def test_page_marker_and_title_line_checks_are_the_extractions():
    ns = extraction({"REFERENCE_LANG", "PAGE_RE", "zip_anomalies"})
    assert (ns["PAGE_RE"].pattern, ns["PAGE_RE"].flags) == (catalogue.PAGE_RE.pattern, catalogue.PAGE_RE.flags)
    lines = ["", " ", "\t", "Title", "Page 1: Once", "page 12 : x", "  Page 3:", "Page: 1", "Pages 1: x", "A Page 1: x",
             "\N{NO-BREAK SPACE}Page 2: y", "Page 1:x", "Title\nPage 2: y", "\n", "Page\n1: x"]
    for line in lines + [t.split("\n")[0] for t in synthetic_texts(n=500)]:
        s = {"id": "1", "folder": "f", "lang": "en-us", "age": "young", "pages": 1, "_title": line, "_pages": ["x"],
             "_stray": 0}
        issues = {a["issue"] for a in ns["zip_anomalies"](s, {}, {})} & {catalogue.EMPTY_TITLE,
                                                                         catalogue.PAGE_MARKER_TITLE}
        assert issues == ({catalogue.title_line_issue(line)} - {None}), repr(line)


@pytest.mark.parametrize("folder", [
    "Hero-World-Theme-Prompt-Sidekick-young", "Hero-Deep-Dark-Wood-Theme-Prompt-Sidekick-old",
    "Hero-World-Theme-Prompt-Sidekick-Mid", "PD_Momotaro old", "PD_Red Riding Hood_young current",
    "PD_Untitled tale", "Short-name",
])
def test_kind_and_level_follow_parse_folder(folder):
    ref = extraction({"PD_AGE_RE", "PD_HERO", "parse_folder"})
    meta = ref["parse_folder"](folder)
    row = {"id": "1", "folder": folder, "hero": meta["hero"], "age": meta["age"]}
    assert catalogue.kind_of(row) == ("classic" if meta["hero"] == ref["PD_HERO"] else "generated")
    expected = meta["age"].strip().lower()
    if expected and expected not in LEVELS:
        with pytest.raises(catalogue.CatalogueFormatError):
            catalogue.level_of(row, LEVELS)
    else:
        assert catalogue.level_of(row, LEVELS) == expected


# ---- reading tables ----
def zip_text(title, pages):
    """A text in the zip delivery's form: the title line, then one line per page, \\n inside a page."""
    return "\n".join([title] + [p.replace("\n", "\\n") for p in pages]) + "\n"


def make_row(story_id, page_texts, *, title="A Title", folder=None, age="young", lang="en-us", **over):
    folder = folder or f"Hero-World-Theme-Prompt-Sidekick-{age}"
    hero = "Public domain" if folder.startswith("PD_") else "Hero"
    row = {"id": story_id, "folder": folder, "hero": hero, "world": "World", "theme": "Theme", "prompt": "Prompt",
           "sidekick": "Sidekick", "age": age, "lang": lang, "title": title, "pages": str(len(page_texts)),
           "words": str(len(" ".join(page_texts).split())), "build_error": "", "text": zip_text(title, page_texts)}
    row.update(over)
    return row


def write_table(path, rows, header=None, bom=False):
    header = header or catalogue.STORY_COLS
    opener = lzma.open if path.name.endswith(".xz") else open
    with opener(path, "wt", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            w.writerow([row.get(c, "") for c in header])
    return path


@pytest.mark.parametrize("name", ["t.csv", "t.csv.xz"])
def test_read_and_parse_rows(tmp_path, name):
    rows = [make_row("1", ["Once upon a time.", "Tom ran\nhome."]),
            make_row("2", ["Long ago."], folder="PD_Momotaro old", age="old"),
            make_row("3", ["x " * 70_000], age="")]  # a field above the csv module's default limit
    path = write_table(tmp_path / name, rows)
    parsed = [catalogue.parse_row(r, levels=LEVELS) for r in catalogue.read_rows(path)]
    assert [p.story_id for p in parsed] == ["1", "2", "3"]
    first = parsed[0]
    assert first.title_line == "A Title"
    assert first.pages == ("Once upon a time.", "Tom ran\nhome.")
    # The in-page line break separates "ran" from "home.", so the viewer's count is 7.
    assert (first.level, first.kind, first.catalogue_words, first.words_consistent) == ("young", "generated", 7, True)
    assert first.meta["folder"] == "Hero-World-Theme-Prompt-Sidekick-young"
    assert (parsed[1].kind, parsed[1].level) == ("classic", "old")
    assert parsed[2].level == ""


def test_byte_order_mark_and_extra_columns(tmp_path):
    header = [*catalogue.STORY_COLS, "standin_source"]
    row = make_row("1", ["One."], standin_source="SimpleStories")
    path = write_table(tmp_path / "t.csv", [row], header=header, bom=True)
    (got,) = catalogue.read_rows(path)
    assert got["id"] == "1" and got["standin_source"] == "SimpleStories"


def test_schema_errors(tmp_path):
    bad_header = [c for c in catalogue.STORY_COLS if c != "words"]
    with pytest.raises(catalogue.CatalogueFormatError, match="missing"):
        list(catalogue.read_rows(write_table(tmp_path / "a.csv", [make_row("1", ["x"])], header=bad_header)))
    path = tmp_path / "b.csv"
    path.write_text(",".join(catalogue.STORY_COLS) + "\n1,2,3\n", encoding="utf-8")
    with pytest.raises(catalogue.CatalogueFormatError, match="3 fields where the header has 14"):
        list(catalogue.read_rows(path))
    (tmp_path / "c.csv").write_text("", encoding="utf-8")
    with pytest.raises(catalogue.CatalogueFormatError, match="empty"):
        list(catalogue.read_rows(tmp_path / "c.csv"))
    with pytest.raises(catalogue.CatalogueFormatError):
        catalogue.open_text(tmp_path / "d.tsv")


@pytest.mark.parametrize("over, message", [
    ({"pages": "5"}, "pages column"),
    ({"pages": "two"}, "not an integer"),
    ({"hero": "Public domain"}, "disagree"),
    ({"age": "teen"}, "none of the levels"),
    ({"id": " 7"}, "whitespace"),
    ({"lang": ""}, "no lang"),
])
def test_row_errors(over, message):
    with pytest.raises(catalogue.CatalogueFormatError, match=message):
        catalogue.parse_row(make_row("7", ["One.", "Two."], **over), levels=LEVELS)


def test_blank_lines_are_skipped(tmp_path):
    path = write_table(tmp_path / "t.csv", [make_row("1", ["One."]), make_row("2", ["Two."])])
    content = path.read_bytes()  # the csv module ends rows with CRLF; the text fields hold LF only
    path.write_bytes(content.replace(b"\r\n", b"\r\n\r\n", 2) + b"\r\n\r\n")
    assert path.read_bytes().count(b"\r\n\r\n") == 3
    assert [r["id"] for r in catalogue.read_rows(path)] == ["1", "2"]


def test_rows_can_be_read_from_an_open_stream(tmp_path):
    path = write_table(tmp_path / "t.csv", [make_row("1", ["One."])])
    with open(path, encoding="utf-8", newline="") as fh:
        assert [r["id"] for r in catalogue.iter_rows(fh, "stream")] == ["1"]
    with pytest.raises(catalogue.CatalogueFormatError, match="stream: the table is empty"):
        list(catalogue.iter_rows(iter([]), "stream"))


def test_word_column_mismatch_is_reported_not_fatal():
    parsed = catalogue.parse_row(make_row("1", ["One two."], words="9"), levels=LEVELS)
    assert parsed.words_consistent is False and parsed.catalogue_words == 9
