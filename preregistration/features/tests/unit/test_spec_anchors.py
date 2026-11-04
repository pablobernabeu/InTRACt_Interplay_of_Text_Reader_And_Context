"""SPECIFICATION.md quotes the protocol verbatim and names code, settings and pins that exist.

The Feature Specification maps each registered quantity of the English path to the function that computes it, and
each row quotes the protocol passage that registers the quantity. A protocol edit, a renamed function, a changed
default or a moved pin would make the specification wrong without anyone noticing, so these tests read the
specification and check it against the protocol, the package source and the configuration.

An anchor is written ``qmd § <section>: "<quote>"`` for preregistration.qmd or ``supp § <section>: "<quote>"`` for
supplementary.qmd, with " / " between nested headings. A quote matches when it occurs in the named section's own
text, outside its subsections, after both sides are put in NFC, HTML comments are removed, Markdown emphasis and
code markers (*, _ and backticks) are dropped and runs of whitespace become one space. Quotes are checked against the
working copy and, where git is available, against the committed protocol, because the specification quotes only
text that the two share.

Nothing here imports the package. Functions are found by parsing its source with ast, so the tests run without any
of the pipeline's heavy dependencies.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import tomllib
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

FEATURES = Path(__file__).resolve().parents[2]
PREREGISTRATION = FEATURES.parent
SPEC = FEATURES / "SPECIFICATION.md"
PACKAGE = FEATURES / "src" / "intract_features"
CONFIG = FEATURES / "config"
PROTOCOL = {"qmd": PREREGISTRATION / "preregistration.qmd", "supp": PREREGISTRATION / "supplementary.qmd"}
PENDING = PREREGISTRATION / "pending_benchmarks.md"
MODELS_LOCK = CONFIG / "models.lock.json"
# The configuration files whose text may hold a commit or checksum that the specification cites outside a pin.
# config/lock/ is left out: it records the published catalogue's checksums, which the specification never cites.
CONFIG_TEXTS = ("*.json", "*.toml", "stages/*.toml")

# The columns of every feature table, and the stage names fixed for this version of the pipeline (DESIGN.md: one
# module per stage in src/intract_features/stages/).
FEATURE_COLUMNS = ("id", "quantity", "role", "anchor", "module and function", "stage", "pins", "status")
STAGES = frozenset({"documents", "sat", "seg_check", "parse_stanza", "parse_udpipe", "features_gramlex",
                    "features_discourse", "surprisal_goldfish", "surprisal_xglm", "encode_e5", "encode_bgem3",
                    "coref_corpipe", "qe_metricx", "aggregate_timing"})
NO_STAGE = "none"
ROLES = frozenset({"anchor", "component", "covariate", "sensitivity", "diagnostic", "mask", "input",
                   "reference for translations"})
TRANSLATION_OUTPUTS = 14

ROW_ID = re.compile(r"\b[A-Z]{3}-\d{2}\b")
ROW_RANGE = re.compile(r"\b([A-Z]{3})-(\d{2}) to \1-(\d{2})\b")
# The planning review's gaps G1 to G9; a gap split in two takes a letter (G1a, G1b).
GAP_ID = re.compile(r"G[1-9][a-z]?")
OPEN_ID = re.compile(r"FS-\d{2}")
CONFLICT_ID = re.compile(r"CF-\d{2}")
PENDING_ID = re.compile(r"P\d{2}")
# A section label never spans a line and holds no quotation mark or angle bracket, so the placeholder
# `qmd § <section>: "<quote>"` in the specification's own explanation is not read as an anchor.
ANCHOR = re.compile(r'\b(qmd|supp) § ([^:"<>\n]+?): "([^"]+)"')
CODE_REF = re.compile(r"`([\w/]+\.py):([\w.]+)`")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
# A setting: a file under config/, then a table, a key and a TOML literal, each optional from the right; a top-level
# key has no table.
CONFIG_REF = re.compile(r"`((?:stages/)?\w+\.toml)(?: \[([\w.]+)\])?(?: (\w+)(?: = ([^`]+))?)?`")
# A code span naming a table alone, such as `[aligner]`; token names such as `[CLS]` are upper case.
TABLE_ALONE = re.compile(r"\[[a-z_][\w.]*\]")
PIN_REF = re.compile(r"`([\w.-]+/[\w.-]+)@([0-9a-f]{7,40})`")
# A commit prefix or a checksum: a standalone run of 7 to 64 lower-case hexadecimal digits.
HEX = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,64}(?![0-9A-Za-z])")
STATUS = re.compile(r"(?:implemented|default pending (?P<ids>[^()]+)|conflict (?P<conflicts>[^()]+)"
                    r"|not yet built(?: \((?P<waits>[^()]+)\))?)")
HEADING = re.compile(r"(#{1,6})\s+(.+?)\s*(?:\{[^}]*\})?\s*")
SEPARATOR = re.compile(r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*")
EMPHASIS = re.compile(r"[*_`]")
COMMENT = re.compile(r"<!--.*?-->", re.S)
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


# ---------------------------------------------------------------- reading the specification


@dataclass(frozen=True)
class Table:
    """A Markdown pipe table: its lower-cased header, its rows of cells and the 1-based line of its header."""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    line: int

    def column(self, name: str) -> list[str]:
        """The cells of the column headed `name`, one per row ("" where a row is short)."""
        at = self.header.index(name)
        return [row[at] if at < len(row) else "" for row in self.rows]


@dataclass(frozen=True)
class Anchor:
    """One quoted anchor: where it sits in the specification, the protocol file, the heading path and the quote."""

    line: int
    file: str
    section: tuple[str, ...]
    quote: str


def split_cells(line: str) -> tuple[str, ...]:
    """The cells of one table row, stripped; a pipe escaped as backslash-pipe stays inside its cell."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return tuple(cell.strip().replace("\\|", "|") for cell in UNESCAPED_PIPE.split(body))


def tables(markdown: str) -> list[Table]:
    """Every pipe table of a Markdown document, in order."""
    lines = markdown.splitlines()
    out, i = [], 0
    while i + 1 < len(lines):
        if lines[i].lstrip().startswith("|") and SEPARATOR.fullmatch(lines[i + 1]):
            header = tuple(cell.lower() for cell in split_cells(lines[i]))
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            out.append(Table(header, tuple(split_cells(row) for row in lines[i + 2:j]), i + 1))
            i = j
        else:
            i += 1
    return out


def anchors(markdown: str) -> list[Anchor]:
    """Every anchor in a document, in tables and in prose alike."""
    out = []
    for m in ANCHOR.finditer(markdown):
        section = tuple(part.strip() for part in m.group(2).split(" / "))
        out.append(Anchor(markdown.count("\n", 0, m.start()) + 1, m.group(1), section, m.group(3)))
    return out


def feature_rows(markdown: str) -> list[tuple[int, tuple[str, ...]]]:
    """(line, cells) of every row of every feature table."""
    out = []
    for table in tables(markdown):
        if table.header == FEATURE_COLUMNS:
            out += [(table.line + 2 + k, cells) for k, cells in enumerate(table.rows)]
    return out


def by_column(cells: Sequence[str]) -> dict[str, str]:
    """A feature row's cells keyed by column name; a short row lacks the trailing columns."""
    return dict(zip(FEATURE_COLUMNS, cells, strict=False))


def stages_of(cells: Mapping[str, str]) -> list[str]:
    """The stage names a feature row's stage column lists."""
    return [s.strip().strip("`") for s in cells.get("stage", "").split(",")]


def table_headed(markdown: str, *columns: str) -> Table:
    """The one table whose header starts with `columns`."""
    found = [t for t in tables(markdown) if t.header[:len(columns)] == columns]
    assert len(found) == 1, f"expected one table headed {columns!r}, found {len(found)}"
    return found[0]


# ---------------------------------------------------------------- matching quotes against the protocol


def normalise(text: str) -> str:
    """NFC, HTML comments removed, Markdown emphasis and code markers dropped, whitespace runs collapsed.

    The protocol carries `<!-- PENDING: Pnn -->` comments inside sentences and writes emphasis that a quote in a
    table cell need not repeat; both sides go through this function, so a verbatim quote always matches.
    """
    text = COMMENT.sub(" ", unicodedata.normalize("NFC", text))
    return " ".join(EMPHASIS.sub("", text).split())


def headings(lines: Sequence[str]) -> list[tuple[int, int, str]]:
    """(line index, level, title) of every heading outside the YAML front matter and fenced blocks."""
    start = 0
    if lines and lines[0].strip() == "---":
        start = next((k + 1 for k in range(1, len(lines)) if lines[k].strip() in ("---", "...")), 0)
    out, fenced = [], False
    for k in range(start, len(lines)):
        if lines[k].lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        m = None if fenced else HEADING.fullmatch(lines[k])
        if m:
            out.append((k, len(m.group(1)), m.group(2)))
    return out


def label_matches(label: str, title: str) -> bool:
    """A label names a heading by its whole title or by the part before a full stop or space, such as "S3"."""
    return title == label or (title.startswith(label) and title[len(label)] in ". ")


def section_text(text: str, path: Sequence[str], *, own: bool = False) -> str | None:
    """The text under a heading path, outer heading first, up to the next heading of the same level or above.

    With `own`, the text stops at the section's first subsection, so that a quote is found only under the deepest
    heading that holds it.
    """
    lines = text.splitlines()
    heads = headings(lines)
    lo, hi, level = 0, len(lines), 0
    for label in path:
        found = next(((k, lvl) for k, lvl, title in heads
                      if lo <= k < hi and lvl > level and label_matches(label, title)), None)
        if found is None:
            return None
        k, lvl = found
        end = next((j for j, other, _ in heads if j > k and other <= lvl), len(lines))
        lo, hi, level = k + 1, min(end, hi), lvl
    if own:
        hi = next((j for j, _, _ in heads if lo <= j < hi), hi)
    return "\n".join(lines[lo:hi])


def anchor_problems(markdown: str, protocol: Mapping[str, str]) -> list[str]:
    """Every anchor whose section is missing or whose quote does not occur in that section's own text."""
    problems: list[str] = []
    sections: dict[tuple[str, tuple[str, ...]], tuple[str, str] | None] = {}
    whole = {key: normalise(text) for key, text in protocol.items()}
    for a in anchors(markdown):
        key = (a.file, a.section)
        if key not in sections:
            own = section_text(protocol[a.file], a.section, own=True)
            full = section_text(protocol[a.file], a.section)
            sections[key] = None if own is None or full is None else (normalise(own), normalise(full))
        where = f"SPECIFICATION.md:{a.line}: {a.file} § {' / '.join(a.section)}"
        if sections[key] is None:
            problems.append(f"{where}: no such section")
            continue
        own_text, full_text = sections[key]
        quote = normalise(a.quote)
        if quote in own_text:
            continue
        if quote in full_text:
            problems.append(f"{where}: the quote is in a subsection, so name the deepest heading: {a.quote[:90]!r}")
            continue
        elsewhere = [k for k, t in whole.items() if quote in t]
        hint = f" (it occurs in {', '.join(elsewhere)} outside that section)" if elsewhere else ""
        problems.append(f"{where}: quote not found{hint}: {a.quote[:90]!r}")
    return problems


# ---------------------------------------------------------------- code and configuration


def _names(node: ast.stmt) -> set[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {t.id for t in node.targets if isinstance(t, ast.Name)}
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()


def defines(tree: ast.Module, dotted: str) -> bool:
    """Whether a module defines `name` at top level, or `Class.member` inside a top-level class."""
    body: list[ast.stmt] = tree.body
    for part in dotted.split("."):
        node = next((n for n in body if part in _names(n)), None)
        if node is None:
            return False
        body = node.body if isinstance(node, ast.ClassDef) else []
    return True


@cache
def module_tree(relpath: str) -> ast.Module | None:
    """The parsed source of a module of the package, or None if the file does not exist."""
    path = PACKAGE / relpath
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path)) if path.is_file() else None


def config_value(data: Mapping, table: str | None, key: str | None) -> tuple[bool, object]:
    """(found, value) of `key` in the dotted `table` of a parsed TOML file.

    With no table, `key` is a top-level key; with no key, the result says whether the table (or the file) exists.
    """
    node: object = data
    for part in table.split(".") if table else ():
        if not isinstance(node, Mapping) or part not in node:
            return False, None
        node = node[part]
    if key is None:
        return isinstance(node, Mapping), node
    if not isinstance(node, Mapping) or key not in node:
        return False, None
    return True, node[key]


@cache
def config_file(relpath: str) -> dict | None:
    """A parsed configuration file under config/, or None if it does not exist."""
    path = CONFIG / relpath
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


@cache
def config_hex() -> frozenset[str]:
    """Every standalone hexadecimal run of 7 to 64 digits in the configuration's text, comments included."""
    out: set[str] = set()
    for pattern in CONFIG_TEXTS:
        for path in sorted(CONFIG.glob(pattern)):
            out.update(HEX.findall(path.read_text(encoding="utf-8")))
    return frozenset(out)


def locked_revisions(lock: Mapping) -> dict[str, set[str]]:
    """Repository to pinned commits, from the entries of models.lock.json.

    An entry is keyed by its repository (a suffix after "@" names a variant of the same commit, such as a converted
    file) and gives `revision`, or names the repository that holds its files in `models_repo` with `models_revision`,
    or a source checkout in `source_repo` (a GitHub URL) with `source_commit`.
    """
    out: dict[str, set[str]] = {}
    for key, entry in lock.get("models", {}).items():
        if not isinstance(entry, Mapping):
            continue
        if isinstance(entry.get("revision"), str):
            out.setdefault(key.split("@")[0], set()).add(entry["revision"])
        if isinstance(entry.get("models_repo"), str) and isinstance(entry.get("models_revision"), str):
            out.setdefault(entry["models_repo"], set()).add(entry["models_revision"])
        if isinstance(entry.get("source_repo"), str) and isinstance(entry.get("source_commit"), str):
            repo = entry["source_repo"].removeprefix("https://github.com/").removesuffix(".git").strip("/")
            out.setdefault(repo, set()).add(entry["source_commit"])
    return out


def status_ids(status: str) -> list[str] | None:
    """The gap, open-choice, conflict and pending ids a status names, or None if the status is malformed."""
    m = STATUS.fullmatch(status)
    if m is None:
        return None
    named = m.group("ids") or m.group("conflicts") or m.group("waits") or ""
    return [part.strip() for part in named.split(",") if part.strip()]


def line_of(markdown: str, offset: int) -> int:
    """The 1-based line of a character offset."""
    return markdown.count("\n", 0, offset) + 1


def listed_rows(cell: str) -> set[str]:
    """The row ids a cell names, with a range such as "LEX-01 to LEX-03" expanded."""
    out = set(ROW_ID.findall(cell))
    for prefix, first, last in ROW_RANGE.findall(cell):
        out |= {f"{prefix}-{n:02d}" for n in range(int(first), int(last) + 1)}
    return out


def is_hex_reference(token: str) -> bool:
    """A hexadecimal run counts as a commit or checksum when it holds both a digit and a letter."""
    return any(c.isdigit() for c in token) and any(c.isalpha() for c in token)


# ---------------------------------------------------------------- fixtures


@cache
def spec_text() -> str:
    """SPECIFICATION.md, which lives in the package directory and must exist wherever the tests run."""
    return SPEC.read_text(encoding="utf-8")


def protocol_texts() -> dict[str, str]:
    """The protocol and its supplement, or a skip where this checkout does not hold them."""
    missing = [path.name for path in PROTOCOL.values() if not path.is_file()]
    if missing:
        pytest.skip(f"the protocol is not in this checkout: {', '.join(missing)}")
    return {key: path.read_text(encoding="utf-8") for key, path in PROTOCOL.items()}


def committed_protocol_texts() -> dict[str, str]:
    """The protocol and its supplement as committed at HEAD, or a skip where git or the repository is missing."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not available, so the committed protocol cannot be read")
    try:
        top = subprocess.run([git, "-C", str(PREREGISTRATION), "rev-parse", "--show-toplevel"], capture_output=True,
                             check=True, timeout=60).stdout.decode("utf-8").strip()
        out = {}
        for key, path in PROTOCOL.items():
            rel = path.resolve().relative_to(Path(top).resolve()).as_posix()
            shown = subprocess.run([git, "-C", top, "show", f"HEAD:{rel}"], capture_output=True, check=True,
                                   timeout=60)
            out[key] = shown.stdout.decode("utf-8")
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        pytest.skip(f"the committed protocol cannot be read: {err}")
    return out


def defined_row_ids() -> set[str]:
    """The ids of the specification's feature rows."""
    return {cells[0] for _, cells in feature_rows(spec_text()) if cells}


# ---------------------------------------------------------------- the matcher itself


def test_matching_rules_on_a_fixture():
    # A heading inside the front matter or a fenced block would end section A early, so the A / C case below
    # fails with "no such section" if either is not skipped.
    protocol = {
        "qmd": "---\n# yaml comment\ntitle: x\n---\n# A\n\n## B\n\nThe *word* is `here`.<!-- PENDING: P01 --> Next\n"
               "line.\n\n```{=latex}\n# not a heading\n```\n\n## C\n\nOther text.\n\n# S3. Long title\n\nTail.\n",
        "supp": "",
    }
    assert "no such section" in anchor_problems('qmd § yaml comment: "title"', protocol)[0]
    assert anchor_problems('qmd § A / B: "The word is here. Next line."', protocol) == []
    assert anchor_problems('qmd § B: "The *word* is `here`."', protocol) == []
    assert anchor_problems('qmd § S3: "Tail."', protocol) == []
    outside = anchor_problems('qmd § A / C: "The word is here."', protocol)
    assert len(outside) == 1 and "outside that section" in outside[0]
    # A quote under a subsection must name the subsection, not only the section above it.
    nested = anchor_problems('qmd § A: "The word is here."', protocol)
    assert len(nested) == 1 and "subsection" in nested[0]
    assert "no such section" in anchor_problems('qmd § Z: "Tail."', protocol)[0]
    assert "no such section" in anchor_problems('qmd § S: "Tail."', protocol)[0]  # "S" names no heading
    assert anchors('`qmd § <section>: "<quote>"`') == []


def test_tables_cells_and_definitions_on_fixtures():
    found = tables("text\n\n| a | b |\n|---|---|\n| x \\| y | `z` |\n\nmore\n")
    assert found == [Table(("a", "b"), (("x | y", "`z`"),), 3)]
    assert found[0].column("b") == ["`z`"]
    tree = ast.parse("class A:\n    x: int = 1\n    def b(self):\n        pass\nC = 2\ndef d():\n    pass\n")
    assert all(defines(tree, name) for name in ("A", "A.b", "A.x", "C", "d"))
    assert not any(defines(tree, name) for name in ("B", "A.c", "d.e"))
    assert config_value({"t": {"u": {"k": 1}}}, "t.u", "k") == (True, 1)
    assert config_value({"t": {"u": {"k": 1}}}, "t.u", None)[0]
    assert config_value({"t": {}}, "t.u", "k") == (False, None)
    assert config_value({"k": 0, "t": {}}, None, "k") == (True, 0)
    assert config_value({"t": {}}, None, "k") == (False, None)
    assert status_ids("default pending G1a, FS-02, P48") == ["G1a", "FS-02", "P48"]
    assert status_ids("conflict CF-01, G6") == ["CF-01", "G6"]
    assert status_ids("not yet built (G3)") == ["G3"]
    assert status_ids("implemented") == [] and status_ids("not yet built") == []
    assert status_ids("done") is None and status_ids("conflict") is None
    assert listed_rows("LEX-01 to LEX-03, DSC-09 and SEG-3") == {"LEX-01", "LEX-02", "LEX-03", "DSC-09"}
    lock = {"models": {"a/b": {"revision": "abc1"}, "a/b@converted": {"revision": "abc1"},
                       "tool-1.0": {"models_repo": "c/d", "models_revision": "def2"},
                       "tool-2.0": {"source_repo": "https://github.com/e/f", "source_commit": "0123"}, "note": "text"}}
    assert locked_revisions(lock) == {"a/b": {"abc1"}, "c/d": {"def2"}, "e/f": {"0123"}}
    ref = CONFIG_REF.fullmatch("`stages/x.toml top = 0`")
    assert ref is not None and ref.groups() == ("stages/x.toml", None, "top", "0")
    assert CONFIG_REF.fullmatch("`[lexical.names] rule = \"x\"`") is None
    hex_runs = [m.group() for m in HEX.finditer("a 5227d8b, deadbee0 and 0x200B; e5 or abc1234x")]
    assert hex_runs == ["5227d8b", "deadbee0"]
    assert is_hex_reference("5227d8b") and not is_hex_reference("20261026") and not is_hex_reference("defaced")


# ---------------------------------------------------------------- the specification


def test_every_anchor_occurs_verbatim_in_its_section():
    found = anchors(spec_text())
    assert len(found) >= len(feature_rows(spec_text())), "every feature row quotes at least one anchor"
    problems = anchor_problems(spec_text(), protocol_texts())
    assert not problems, "anchors that do not match the protocol:\n" + "\n".join(problems)


def test_every_anchor_occurs_verbatim_in_the_committed_protocol():
    # The working copy may hold the PI's uncommitted edits; a quote taken from one of them would be lost if the edit
    # were dropped, so the specification quotes only text that HEAD also holds.
    problems = anchor_problems(spec_text(), committed_protocol_texts())
    assert not problems, "anchors that do not match the committed protocol:\n" + "\n".join(problems)


def test_feature_rows_are_well_formed():
    rows = feature_rows(spec_text())
    assert rows, "SPECIFICATION.md has no feature table"
    problems, seen = [], set()
    for line, raw in rows:
        where = f"SPECIFICATION.md:{line}"
        if len(raw) != len(FEATURE_COLUMNS):
            problems.append(f"{where}: {len(raw)} cells, the header has {len(FEATURE_COLUMNS)}")
            continue
        cells = by_column(raw)
        row_id = cells["id"]
        if not ROW_ID.fullmatch(row_id) or row_id in seen:
            problems.append(f"{where}: id {row_id!r} is malformed or repeated")
        seen.add(row_id)
        roles = [r.strip() for r in cells["role"].split(",")]
        problems += [f"{where}: unknown role {r!r}" for r in roles if r not in ROLES]
        stages = stages_of(cells)
        if stages != [NO_STAGE] and not set(stages) <= STAGES:
            problems.append(f"{where}: stage {cells['stage']!r} is not in the fixed stage list")
        # Every quote must be an anchor the matcher reads, so a malformed one cannot escape the check.
        leftover = ANCHOR.sub("", cells["anchor"]).replace("<br>", "").strip()
        if not ANCHOR.search(cells["anchor"]) or leftover:
            problems.append(f"{where}: the anchor cell holds text that is not an anchor: {leftover[:60]!r}")
        if status_ids(cells["status"]) is None:
            problems.append(f"{where}: status {cells['status']!r} is not one of the four forms")
        elif not cells["status"].startswith("not yet built"):
            if not CODE_REF.search(cells["module and function"]):
                problems.append(f"{where}: a built row names no `module.py:function`")
            if stages == [NO_STAGE]:
                problems.append(f"{where}: a built row names no stage")
            problems += [f"{where}: stage module {s}.py does not exist" for s in stages
                         if s != NO_STAGE and not (PACKAGE / "stages" / f"{s}.py").is_file()]
    assert not problems, "\n".join(problems)


def test_status_ids_are_defined():
    spec = spec_text()
    gaps = set(table_headed(spec, "gap").column("gap"))
    open_choices = set(table_headed(spec, "id", "open choice").column("id"))
    conflicts = set(table_headed(spec, "id", "conflict").column("id"))
    pending = None
    if PENDING.is_file():
        pending = {cells[0] for t in tables(PENDING.read_text(encoding="utf-8")) for cells in t.rows
                   if cells and PENDING_ID.fullmatch(cells[0])}
    problems = []
    for line, raw in feature_rows(spec):
        cells = by_column(raw)
        m = STATUS.fullmatch(cells.get("status", ""))
        if m is None:
            continue  # test_feature_rows_are_well_formed reports it
        is_conflict = m.group("conflicts") is not None
        where = f"SPECIFICATION.md:{line}: {cells['id']}"
        for ident in status_ids(cells["status"]) or []:
            known = ((GAP_ID.fullmatch(ident) and ident in gaps) or (OPEN_ID.fullmatch(ident) and ident in open_choices)
                     or (CONFLICT_ID.fullmatch(ident) and ident in conflicts)
                     or (PENDING_ID.fullmatch(ident) and (pending is None or ident in pending)))
            if not known:
                problems.append(f"{where} names {ident!r}, which is not defined")
            # A conflict is never settled by a default, so its id belongs to a conflict status alone, and a conflict
            # status names only departures: conflicts, and gaps whose default departs from the registered text.
            if CONFLICT_ID.fullmatch(ident) and not is_conflict:
                problems.append(f"{where} names the conflict {ident} outside a conflict status")
            if is_conflict and not (CONFLICT_ID.fullmatch(ident) or GAP_ID.fullmatch(ident)):
                problems.append(f"{where}: a conflict status names {ident!r}, which is not a conflict or a gap")
    assert not problems, "\n".join(problems)


def test_gaps_open_choices_conflicts_translation_outputs_and_stages_are_complete():
    spec = spec_text()
    gaps = table_headed(spec, "gap").column("gap")
    assert all(GAP_ID.fullmatch(g) for g in gaps) and len(set(gaps)) == len(gaps) and gaps == sorted(gaps)
    assert sorted({g[:2] for g in gaps}) == [f"G{n}" for n in range(1, 10)], "every gap G1 to G9 has a row, in order"
    choices = table_headed(spec, "id", "open choice").column("id")
    assert all(OPEN_ID.fullmatch(c) for c in choices) and len(set(choices)) == len(choices)
    conflicts = table_headed(spec, "id", "conflict").column("id")
    assert all(CONFLICT_ID.fullmatch(c) for c in conflicts) and len(set(conflicts)) == len(conflicts)
    outputs = table_headed(spec, "#").column("#")
    assert outputs == [str(n) for n in range(1, TRANSLATION_OUTPUTS + 1)]
    stages = table_headed(spec, "stage").column("stage")
    assert sorted(stages) == sorted(STAGES), "the stage map lists each fixed stage once"


def test_gaps_open_choices_and_conflicts_list_exactly_the_rows_whose_status_names_them():
    # Sections 3 and 4 say which rows each item affects, and each row's status names the items that affect it; the
    # two are written separately, so they are checked against each other.
    spec = spec_text()
    listed: dict[str, set[str]] = {}
    for table, column in ((table_headed(spec, "gap"), "where"), (table_headed(spec, "id", "open choice"), "rows"),
                          (table_headed(spec, "id", "conflict"), "rows")):
        listed |= {ident: listed_rows(cell) for ident, cell in zip(table.column(table.header[0]),
                                                                   table.column(column), strict=True)}
    named: dict[str, set[str]] = {}
    for _, raw in feature_rows(spec):
        cells = by_column(raw)
        for ident in status_ids(cells.get("status", "")) or []:
            if GAP_ID.fullmatch(ident) or OPEN_ID.fullmatch(ident) or CONFLICT_ID.fullmatch(ident):
                named.setdefault(ident, set()).add(cells["id"])
    problems = []
    for ident in sorted(set(listed) | set(named)):
        only_listed = listed.get(ident, set()) - named.get(ident, set())
        only_named = named.get(ident, set()) - listed.get(ident, set())
        if only_listed or only_named:
            problems.append(f"{ident}: listed in its table but not named in the status of {sorted(only_listed)}; "
                            f"named in the status of {sorted(only_named)} but not listed")
    assert not problems, "\n".join(problems)


def test_stage_map_lists_the_rows_each_stage_writes():
    spec = spec_text()
    table = table_headed(spec, "stage")
    mapped = {stage: listed_rows(cell) for stage, cell in zip(table.column("stage"), table.column("rows"), strict=True)}
    named: dict[str, set[str]] = {stage: set() for stage in STAGES}
    for _, raw in feature_rows(spec):
        cells = by_column(raw)
        for stage in stages_of(cells):
            if stage in named:
                named[stage].add(cells["id"])
    problems = []
    for stage in sorted(STAGES):
        only_map = mapped.get(stage, set()) - named[stage]
        only_rows = named[stage] - mapped.get(stage, set())
        if only_map or only_rows:
            problems.append(f"{stage}: the map lists {sorted(only_map)} whose stage column does not name it, and "
                            f"omits {sorted(only_rows)} whose stage column does")
    assert not problems, "\n".join(problems)


def test_checklist_accounts_for_every_row():
    # Section 7 maps the planning review's inventory onto the rows, or lists a row as one the planning review missed,
    # so a new row has to be placed there too.
    spec = spec_text()
    start = spec.find("\n## 7.")
    assert start >= 0, "SPECIFICATION.md has no section 7"
    missing = sorted(defined_row_ids() - listed_rows(spec[start:]))
    assert not missing, f"rows section 7 does not account for: {missing}"


def test_every_row_id_mentioned_is_defined():
    spec = spec_text()
    defined = defined_row_ids()
    problems = [f"SPECIFICATION.md:{line_of(spec, m.start())}: {m.group()} is not a feature row"
                for m in ROW_ID.finditer(spec) if m.group() not in defined]
    assert not problems, "\n".join(problems)


def test_every_code_reference_exists():
    spec = spec_text()
    problems = []
    for m in CODE_REF.finditer(spec):
        relpath, dotted = m.groups()
        tree = module_tree(relpath)
        if tree is None:
            problems.append(f"SPECIFICATION.md:{line_of(spec, m.start())}: {relpath} does not exist")
        elif not defines(tree, dotted):
            problems.append(f"SPECIFICATION.md:{line_of(spec, m.start())}: {relpath} defines no {dotted}")
    assert not problems, "\n".join(problems)


def test_every_pin_matches_the_model_lock():
    if not MODELS_LOCK.is_file():
        pytest.skip("config/models.lock.json is not in this checkout")
    revisions = locked_revisions(json.loads(MODELS_LOCK.read_text(encoding="utf-8")))
    spec = spec_text()
    found = list(PIN_REF.finditer(spec))
    assert found, "SPECIFICATION.md writes no repository@commit pin"
    problems = []
    for m in found:
        repo, prefix = m.groups()
        pinned = revisions.get(repo, set())
        if not any(rev.startswith(prefix) for rev in pinned):
            held = ", ".join(sorted(r[:12] for r in pinned)) or "no entry"
            problems.append(f"SPECIFICATION.md:{line_of(spec, m.start())}: {repo}@{prefix} (the lock holds {held})")
    assert not problems, "\n".join(problems)


def test_every_other_commit_or_checksum_occurs_in_the_configuration():
    # A commit or checksum written outside a `repository@commit` pin would otherwise escape every check.
    spec = spec_text()
    pins = [m.span() for m in PIN_REF.finditer(spec)]
    known = config_hex()
    problems = []
    for m in HEX.finditer(spec):
        token = m.group()
        if not is_hex_reference(token) or any(a <= m.start() < b for a, b in pins):
            continue
        if not any(h.startswith(token) for h in known):
            problems.append(f"SPECIFICATION.md:{line_of(spec, m.start())}: {token} occurs in no file of config/")
    assert not problems, "\n".join(problems)


def test_every_setting_is_written_in_the_checked_form():
    # A setting written without its file, such as `[table] key = value`, would escape the check below, so every
    # code span that looks like one must be a full reference. Spans with a placeholder (<...>) explain the form.
    spec = spec_text()
    problems = []
    for m in CODE_SPAN.finditer(spec):
        body = m.group(1)
        if "<" in body:
            continue
        looks_like_setting = " = " in body or ".toml [" in body or TABLE_ALONE.fullmatch(body)
        if looks_like_setting and not CONFIG_REF.fullmatch(m.group(0)):
            problems.append(f"SPECIFICATION.md:{line_of(spec, m.start())}: {m.group(0)} names a setting without "
                            f"the form `stages/<stage>.toml [table] key = value`")
    assert not problems, "\n".join(problems)


def test_every_configuration_reference_matches_config():
    spec = spec_text()
    problems = []
    for m in CONFIG_REF.finditer(spec):
        relpath, table, key, literal = m.groups()
        where = f"SPECIFICATION.md:{line_of(spec, m.start())}: {m.group(0)}"
        data = config_file(relpath)
        if data is None:
            problems.append(f"{where}: config/{relpath} does not exist")
            continue
        found, value = config_value(data, table, key)
        if not found:
            problems.append(f"{where}: no such {'key' if key else 'table'}")
            continue
        if literal is not None:
            try:
                expected = tomllib.loads(f"value = {literal}")["value"]
            except tomllib.TOMLDecodeError as err:
                problems.append(f"{where}: the value is not a TOML literal ({err})")
                continue
            if value != expected:
                problems.append(f"{where}: config holds {value!r}")
    assert not problems, "\n".join(problems)
