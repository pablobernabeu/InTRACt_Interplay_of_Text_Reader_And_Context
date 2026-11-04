"""Build the length-matched stand-in corpus for the English dry run from SimpleStories.

Before in-principle acceptance the feature pipeline may not run on the story texts
(preregistration.qmd, Data provenance, sequestration and outcome blindness: "No linguistic
feature registered here has been computed on the story texts, and none will be before
in-principle acceptance"), yet the dry run on ARC has to measure what every stage costs at
the catalogue's scale.
This builder makes a public stand-in with the English catalogue's structure: each
catalogue text gets public stories of nearly its length, cut into exactly its number of
pages at nearly its page lengths. Its inputs are the catalogue's structure table
(catalogue_structure.py), which holds identifiers and counts and no text, and the
SimpleStories train split, pinned by revision and by the SHA-256 of each parquet shard.

The design is the English-pipeline planning review's of 2-3 November 2026 (section 5, "planning review s5"
below). README.md in this folder sets it out, and config/stages/standin.toml holds every
constant beside the words of the design it implements.

1. Candidates. Each story's lines are stripped and empty ones dropped; n is its number of
   whitespace tokens, stories with n < 50 are dropped, and each candidate is keyed by
   k = SHA-256("intract-standin|v1|cand|" + generation_id).
2. Targets. Each catalogue text is keyed by K = SHA-256("intract-standin|v1|target|" +
   story id + "|" + level), with T = its whitespace tokens, and processed in ascending K.
3. Selection. The unused candidate with |n - T| <= 0.03 T and the smallest |n - T|, ties
   to the smallest k. Failing that, m = ceil(T/500) pieces, each aimed at T/m and the last
   at the remainder, each chosen by the same rule or else by the nearest unused n, and
   joined in ascending k.
4. Paging. Page j ends after token round(N * (t_1 + ... + t_j) / T), snapped to the
   nearest token within 6 that ends a sentence, with cuts increasing and pages non-empty.
5. Output. The published table schema (STORY_COLS), with id "SI" + the rank of K.
6. Sizes. The smoke set is the smallest 1 per cent of K; selection runs in ascending K, so
   its rows are exactly the first rows of the full build.
7-9. Acceptance checks, the character ratios that project costs to the catalogue, and a
   manifest that records every pin, switch and output hash.

Usage, from the features directory (the stand-in sits outside the installed package):

    python -m standin.build_standin download --dest DIR
    python -m standin.build_standin verify --shards DIR
    python -m standin.build_standin build --structure STRUCTURE.tsv --shards DIR --out OUT [--smoke | --limit N]

Standard library only, apart from pyarrow, which is imported when parquet is read.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import io
import json
import lzma
import math
import os
import platform
import sys
import time
import tomllib
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Protocol

from . import typography
from .catalogue_structure import CLASSIC_HERO, STORY_COLS, StructureError, Target, read_structure, split_lines

BUILDER_VERSION = "1"
FEATURES = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = FEATURES / "config"
# The delivery's escape for a line break inside a page, which split_lines() decodes.
LINE_BREAK_ESCAPE = "\\n"
TABLE_NAME = "stories.csv.xz"
SELECTION_NAME = "selection.tsv"
MANIFEST_NAME = "standin_manifest.json"
NOTICE_NAME = "NOTICE-SimpleStories.txt"
# extract_story_texts.py compresses the published tables at xz preset 6; the stand-in matches.
XZ_PRESET = 6
SELECTION_COLS = ["id", "rank", "story_id", "kind", "level", "story_key", "pages", "target_tokens",
                  "standin_tokens", "m", "within_tolerance", "generation_ids", "piece_tokens", "pieces_in_tolerance"]


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


class StandinError(RuntimeError):
    """A failure that stops the build."""


class PinError(StandinError):
    """A source file that is missing or whose size or SHA-256 differs from its pin."""


class PoolExhausted(StandinError):
    """No unused candidate is left for a target."""


# --- Configuration -------------------------------------------------------------------------


@dataclass(frozen=True)
class Pin:
    """One pinned source file: its path in the dataset repository, its size and its SHA-256."""

    path: str
    size: int
    sha256: str

    @property
    def name(self) -> str:
        """The file's name, under which it is kept in a local shard directory."""
        return self.path.rsplit("/", 1)[-1]


def _exact(value: float | int | str) -> Fraction:
    # TOML numbers arrive as floats. Their shortest decimal form is read exactly, so 0.03 is
    # 3/100 and the tolerance test |n - T| <= 0.03 T carries no rounding error.
    return Fraction(str(value))


@dataclass(frozen=True)
class Settings:
    """The stand-in's constants, read from config/stages/standin.toml (see the comments there)."""

    repo: str
    revision: str
    base_url: str
    licence: str
    splits: dict[str, tuple[Pin, ...]]
    expected_rows: dict[str, int]
    candidate_key: str
    target_key: str
    target_separator: str
    min_tokens: int
    drop_backslash: bool
    duplicate_ids: str
    tolerance: Fraction
    join_unit: int
    snap_window: int
    terminal_marks: tuple[str, ...]
    closers: str
    rounding: str
    line_breaks: str
    id_prefix: str
    story_key_prefix: str
    lang: str
    trailing_newline: bool
    smoke_fraction: Fraction
    acceptance_quantiles: tuple[float, ...]
    text_tolerance: Fraction
    page_tolerance: Fraction
    enforce_acceptance: bool
    typography: bool
    typography_rules: dict[str, bool]
    batch_size: int
    notice: str

    @classmethod
    def load(cls, config_dir: Path = DEFAULT_CONFIG) -> Settings:
        """Read config/stages/standin.toml and check its values."""
        cfg = tomllib.loads((Path(config_dir) / "stages" / "standin.toml").read_text(encoding="utf-8"))
        src, keys, cand, sel = cfg["source"], cfg["keys"], cfg["candidates"], cfg["selection"]
        pag, out, acc, typo = cfg["paging"], cfg["output"], cfg["acceptance"], cfg["typography"]
        settings = cls(
            repo=src["repo"], revision=src["revision"], base_url=src["base_url"], licence=src["licence"],
            splits={name: tuple(Pin(f["path"], int(f["size"]), f["sha256"].lower()) for f in files)
                    for name, files in src["splits"].items()},
            expected_rows={k: int(v) for k, v in src["rows"].items()},
            candidate_key=keys["candidate"], target_key=keys["target"], target_separator=keys["target_separator"],
            min_tokens=int(cand["min_tokens"]), drop_backslash=bool(cand["drop_backslash"]),
            duplicate_ids=cand["duplicate_ids"],
            tolerance=_exact(sel["tolerance"]), join_unit=int(sel["join_unit"]),
            snap_window=int(pag["snap_window"]), terminal_marks=tuple(pag["terminal_marks"]),
            closers="".join(pag["closers"]), rounding=pag["rounding"], line_breaks=pag["line_breaks"],
            id_prefix=out["id_prefix"], story_key_prefix=out["story_key_prefix"], lang=out["lang"],
            trailing_newline=bool(out["trailing_newline"]),
            smoke_fraction=_exact(cfg["sizes"]["smoke_fraction"]),
            acceptance_quantiles=tuple(acc["quantiles"]), text_tolerance=_exact(acc["text_tolerance"]),
            page_tolerance=_exact(acc["page_tolerance"]), enforce_acceptance=bool(acc["enforce"]),
            typography=bool(typo["enabled"]),
            typography_rules={k: bool(typo[k]) for k in ("quotes", "apostrophes", "ellipsis", "dashes")},
            batch_size=int(cfg["io"]["batch_size"]), notice=cfg["licence"]["notice"],
        )
        settings.check()
        return settings

    def check(self) -> None:
        """Refuse values the builder cannot apply as documented."""
        problems = []
        if len(self.revision) != 40 or any(c not in "0123456789abcdef" for c in self.revision):
            problems.append("revision must be a full 40-character commit hash")
        for name, pins in self.splits.items():
            for pin in pins:
                if len(pin.sha256) != 64 or any(c not in "0123456789abcdef" for c in pin.sha256) or pin.size < 1:
                    problems.append(f"split {name}: {pin.path} needs a size and a 64-character SHA-256")
        if self.duplicate_ids not in ("keep_first", "fail"):
            problems.append("duplicate_ids must be 'keep_first' or 'fail'")
        if self.rounding not in ("half_up", "half_even"):
            problems.append("rounding must be 'half_up' or 'half_even'")
        if self.line_breaks not in ("space", "escape"):
            problems.append("line_breaks must be 'space' or 'escape'")
        if not 0 < self.tolerance < 1 or not 0 < self.smoke_fraction <= 1:
            problems.append("tolerance and smoke_fraction must lie in (0, 1)")
        if self.min_tokens < 1 or self.join_unit < 1 or self.snap_window < 0 or self.batch_size < 1:
            problems.append("min_tokens, join_unit and batch_size must be positive and snap_window non-negative")
        if not self.acceptance_quantiles or any(not 0 <= q <= 100 for q in self.acceptance_quantiles):
            problems.append("acceptance quantiles must be given and lie in [0, 100]")
        if self.text_tolerance <= 0 or self.page_tolerance <= 0:
            problems.append("acceptance tolerances must be positive")
        if not self.terminal_marks:
            problems.append("paging.terminal_marks must not be empty")
        if problems:
            raise StandinError("config/stages/standin.toml: " + "; ".join(problems))

    def to_record(self) -> dict:
        """The settings as JSON for the manifest, fractions written as exact strings."""
        rec = {}
        for f in dataclasses.fields(self):
            v = getattr(self, f.name)
            if isinstance(v, Fraction):
                v = str(v)
            elif f.name == "splits":
                v = {k: [dataclasses.asdict(p) for p in pins] for k, pins in v.items()}
            elif f.name == "notice":
                continue
            rec[f.name] = v
        return rec


# --- Source files --------------------------------------------------------------------------


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """SHA-256 hex digest of a file, read sequentially."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify_file(path: Path, pin: Pin) -> None:
    """Raise PinError unless the file has the pinned size and SHA-256."""
    path = Path(path)
    if not path.is_file():
        raise PinError(f"{path} is missing")
    size = path.stat().st_size
    if size != pin.size:
        raise PinError(f"{path.name}: {size} bytes, pinned {pin.size}")
    digest = sha256_file(path)
    if digest != pin.sha256:
        raise PinError(f"{path.name}: SHA-256 {digest}, pinned {pin.sha256}")


def verify_shards(directory: Path, pins: Sequence[Pin], log: Callable[[str], None] = _log) -> list[Path]:
    """Check every pinned shard in `directory` by size and SHA-256 before anything reads it."""
    paths = []
    for pin in pins:
        path = Path(directory) / pin.name
        verify_file(path, pin)
        log(f"verified {pin.name} ({pin.size:,} bytes, SHA-256 {pin.sha256[:12]}...)")
        paths.append(path)
    return paths


def download(pins: Sequence[Pin], dest: Path, settings: Settings, log: Callable[[str], None] = _log) -> list[Path]:
    """Fetch the pinned files at the pinned revision into `dest`, verifying each before keeping it.

    The dataset is public, so no token is sent, and the request carries only a User-Agent
    naming this tool. A file already present is verified and kept, or reported if it
    differs from its pin; it is never overwritten silently.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for pin in pins:
        target = dest / pin.name
        if target.exists():
            verify_file(target, pin)
            log(f"{pin.name}: already present and verified")
            paths.append(target)
            continue
        url = f"{settings.base_url.rstrip('/')}/datasets/{settings.repo}/resolve/{settings.revision}/{pin.path}"
        tmp = target.with_name(target.name + ".part")
        h, size = hashlib.sha256(), 0
        request = urllib.request.Request(url, headers={"User-Agent": f"intract-standin-builder/{BUILDER_VERSION}"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response, open(tmp, "wb") as out:
                for block in iter(lambda r=response: r.read(1 << 20), b""):
                    out.write(block)
                    h.update(block)
                    size += len(block)
            if size != pin.size or h.hexdigest() != pin.sha256:
                raise PinError(f"{pin.name}: downloaded {size} bytes with SHA-256 {h.hexdigest()}, "
                               f"pinned {pin.size} and {pin.sha256}")
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        tmp.replace(target)
        log(f"{pin.name}: downloaded and verified")
        paths.append(target)
    return paths


class Source(Protocol):
    """Where candidate stories come from: one scan of every row, then a fetch of the chosen rows."""

    record: dict
    expected_rows: int | None

    def scan(self) -> Iterator[tuple[int, int, str | None, str | None]]:
        """Yield (shard, row, generation_id, story) for every row, in file order."""
        ...

    def fetch(self, wanted: set[tuple[int, int]]) -> dict[tuple[int, int], tuple[str, str, str]]:
        """Return {(shard, row): (generation_id, story, topic)} for the wanted rows."""
        ...


class ParquetSource:
    """The pinned SimpleStories parquet shards, read in batches to keep memory low.

    Files are memory-mapped, because on the machine that ran the extraction an
    operating-system seek was occasionally ignored (extract_story_texts.py), and a map
    does not seek.
    """

    def __init__(self, paths: Sequence[Path], batch_size: int, record: dict | None = None,
                 expected_rows: int | None = None) -> None:
        self.paths = [Path(p) for p in paths]
        self.batch_size = batch_size
        self.record = record or {"files": [p.name for p in self.paths]}
        self.expected_rows = expected_rows

    def scan(self) -> Iterator[tuple[int, int, str | None, str | None]]:
        """Yield (shard, row, generation_id, story) for every row of every shard, in file order."""
        import pyarrow.parquet as pq

        for shard, path in enumerate(self.paths):
            pf = pq.ParquetFile(path, memory_map=True)
            row = 0
            for batch in pf.iter_batches(batch_size=self.batch_size, columns=["generation_id", "story"]):
                gids = batch.column("generation_id").to_pylist()
                stories = batch.column("story").to_pylist()
                for gid, story in zip(gids, stories, strict=True):
                    yield shard, row, gid, story
                    row += 1

    def fetch(self, wanted: set[tuple[int, int]]) -> dict[tuple[int, int], tuple[str, str, str]]:
        """Return {(shard, row): (generation_id, story, topic)}, reading only the row groups that hold them."""
        import pyarrow.parquet as pq

        by_shard: dict[int, list[int]] = defaultdict(list)
        for shard, row in wanted:
            by_shard[shard].append(row)
        found = {}
        for shard, rows in sorted(by_shard.items()):
            rows.sort()
            pf = pq.ParquetFile(self.paths[shard], memory_map=True)
            start, i = 0, 0
            # Only the row groups that hold a wanted row are read, one at a time.
            for group in range(pf.metadata.num_row_groups):
                end = start + pf.metadata.row_group(group).num_rows
                need = []
                while i < len(rows) and rows[i] < end:
                    need.append(rows[i] - start)
                    i += 1
                if need:
                    need_set, local = set(need), 0
                    for batch in pf.iter_batches(batch_size=self.batch_size, row_groups=[group],
                                                 columns=["generation_id", "story", "topic"]):
                        for j in range(batch.num_rows):
                            if local + j in need_set:
                                found[(shard, start + local + j)] = tuple(
                                    batch.column(c)[j].as_py() for c in ("generation_id", "story", "topic"))
                        local += batch.num_rows
                start = end
        return found


class InMemorySource:
    """Candidate stories held in memory as (generation_id, story, topic), all in shard 0.

    For tests and small experiments; the build reads the pinned parquet shards.
    """

    def __init__(self, rows: Sequence[tuple[str, str, str]], record: dict | None = None) -> None:
        self.rows = list(rows)
        self.record = record or {"source": "in-memory", "rows": len(self.rows)}
        self.expected_rows = len(self.rows)

    def scan(self) -> Iterator[tuple[int, int, str | None, str | None]]:
        """Yield (0, row, generation_id, story) for every row."""
        for row, (gid, story, _) in enumerate(self.rows):
            yield 0, row, gid, story

    def fetch(self, wanted: set[tuple[int, int]]) -> dict[tuple[int, int], tuple[str, str, str]]:
        """Return {(0, row): (generation_id, story, topic)} for the wanted rows."""
        return {(s, r): self.rows[r] for s, r in wanted if s == 0}


# --- Candidates and selection --------------------------------------------------------------


def candidate_lines(story: str) -> list[str]:
    """A story's stripped, non-empty lines (planning review s5 step 1: "Strip the lines of each story and drop
    empty ones")."""
    return [line.strip() for line in story.splitlines() if line.strip()]


def candidate_key(generation_id: str, prefix: str) -> bytes:
    """k = SHA-256(prefix + generation_id), the candidate's key (planning review s5 step 1)."""
    return hashlib.sha256((prefix + generation_id).encode("utf-8")).digest()


@dataclass(frozen=True)
class Pick:
    """One chosen candidate: its key, whitespace tokens and place in the source."""

    key: bytes
    n: int
    shard: int
    row: int


class CandidatePool:
    """Unused candidates grouped by token count n, each group in ascending key order.

    Selection always takes, among candidates of one token count, the unused one with the
    smallest key (planning review s5 step 3: "ties broken by the smallest k"), so a group is used
    from its head and a pointer replaces deletion. An entry is the 32-byte key followed by
    the shard (2 bytes) and the row (4 bytes), so sorting entries sorts by key, and the
    train split's 2.1 million stories fit in about 0.2 GB.
    """

    def __init__(self) -> None:
        self._groups: dict[int, list[bytes]] = defaultdict(list)
        self._heads: dict[int, int] = defaultdict(int)
        self.min_n, self.max_n, self.size = 0, -1, 0

    def add(self, key: bytes, n: int, shard: int, row: int) -> None:
        """Add a candidate; call freeze() once every candidate is in."""
        self._groups[n].append(key + shard.to_bytes(2, "big") + row.to_bytes(4, "big"))

    def freeze(self, duplicate_ids: str = "keep_first") -> int:
        """Sort every group and resolve repeated keys; return how many candidates were dropped.

        Two candidates share a key only if they share a generation_id, which is unique in
        the test split but unverified in the train split. "keep_first" keeps the first in
        shard and row order, which sorts first among equal keys; "fail" stops the build.
        """
        dropped: set[bytes] = set()
        previous = None
        for entry in sorted(e for group in self._groups.values() for e in group):
            if entry[:32] == previous:
                dropped.add(entry)
            previous = entry[:32]
        if dropped and duplicate_ids == "fail":
            raise StandinError(f"{len(dropped)} candidates repeat another's generation_id")
        for n in list(self._groups):
            group = sorted(e for e in self._groups[n] if e not in dropped) if dropped else sorted(self._groups[n])
            if group:
                self._groups[n] = group
            else:
                del self._groups[n]
        self.size = sum(len(g) for g in self._groups.values())
        if self._groups:
            self.min_n, self.max_n = min(self._groups), max(self._groups)
        return len(dropped)

    def _head(self, n: int) -> bytes | None:
        group = self._groups.get(n)
        if group is None:
            return None
        i = self._heads[n]
        return group[i] if i < len(group) else None

    def _take(self, n: int) -> Pick:
        entry = self._groups[n][self._heads[n]]
        self._heads[n] += 1
        self.size -= 1
        return Pick(key=entry[:32], n=n, shard=int.from_bytes(entry[32:34], "big"),
                    row=int.from_bytes(entry[34:38], "big"))

    def select(self, aim: Fraction, tolerance: Fraction | None) -> Pick | None:
        """Take the unused candidate nearest to `aim` tokens, ties to the smallest key, or return None.

        With a tolerance, only candidates with |n - aim| <= tolerance * aim qualify (planning review
        s5 step 3); without one, the nearest unused n of any length does. Token counts are
        visited outwards from the aim in order of distance, in exact integer arithmetic.
        """
        if self.max_n < self.min_n:
            return None
        num, den = aim.numerator, aim.denominator
        lower = num // den
        upper = lower + 1
        lower = min(lower, self.max_n)  # nothing above max_n exists, so start from it
        upper = max(upper, self.min_n)  # nothing below min_n exists
        while True:
            d_lo = num - lower * den if lower >= self.min_n else None
            d_hi = upper * den - num if upper <= self.max_n else None
            if d_lo is None and d_hi is None:
                return None
            d = d_hi if d_lo is None else d_lo if d_hi is None else min(d_lo, d_hi)
            # |n - aim| <= tol * aim, with |n - aim| = d / den and aim = num / den.
            if tolerance is not None and d * tolerance.denominator > tolerance.numerator * num:
                return None
            level = []
            if d_lo == d:
                level.append(lower)
                lower -= 1
            if d_hi == d:
                level.append(upper)
                upper += 1
            heads = [(entry, n) for n in level if (entry := self._head(n)) is not None]
            if heads:
                return self._take(min(heads)[1])


def within_tolerance(n: int, total: int, tolerance: Fraction) -> bool:
    """|n - T| <= tolerance * T, in integers (planning review s5 step 3)."""
    return abs(n - total) * tolerance.denominator <= tolerance.numerator * total


@dataclass(frozen=True)
class Selection:
    """The candidates chosen for one target, in the order of the text (ascending key)."""

    pieces: tuple[Pick, ...]
    m: int
    pieces_in_tolerance: tuple[bool, ...]

    @property
    def tokens(self) -> int:
        """N, the whitespace tokens of the chosen text."""
        return sum(p.n for p in self.pieces)


def select_for(pool: CandidatePool, total: int, settings: Settings) -> Selection:
    """Choose the stand-in text for a target of `total` tokens (planning review s5 step 3).

    A single candidate within the tolerance if one exists. Otherwise m = ceil(T/500)
    pieces: each but the last aimed at T/m, the last at the remainder, each chosen by the
    same rule (the tolerance taken on its own aim) or else by the nearest unused n. With
    m = 1, which happens when T <= 500, the single piece is the nearest unused n. Pieces
    are concatenated in ascending key.
    """
    pick = pool.select(Fraction(total), settings.tolerance)
    if pick is not None:
        return Selection((pick,), 1, (True,))
    m = -(-total // settings.join_unit)
    chosen: list[tuple[Pick, bool]] = []
    for i in range(m):
        aim = Fraction(total, m) if i < m - 1 else Fraction(total - sum(p.n for p, _ in chosen))
        pick = pool.select(aim, settings.tolerance)
        within = pick is not None
        if pick is None:
            pick = pool.select(aim, None)
        if pick is None:
            raise PoolExhausted(f"no unused candidate left for a target of {total} tokens")
        chosen.append((pick, within))
    chosen.sort(key=lambda pw: pw[0].key)
    return Selection(tuple(p for p, _ in chosen), m, tuple(w for _, w in chosen))


# --- Paging --------------------------------------------------------------------------------


def is_sentence_final(token: str, terminal_marks: tuple[str, ...], closers: str) -> bool:
    """True if the token ends in a terminal mark once closing quotation marks and brackets are skipped."""
    core = token.rstrip(closers)
    return bool(core) and core.endswith(terminal_marks)


def _round_ratio(a: int, b: int, rounding: str) -> int:
    if rounding == "half_up":
        return (2 * a + b) // (2 * b)
    return round(Fraction(a, b))  # Fraction rounds half to even


def page_cuts(n_tokens: int, tokens_per_page: Sequence[int], final: Sequence[bool], window: int,
              rounding: str = "half_up") -> list[int]:
    """The token after which each page but the last ends, counting tokens from 1 (planning review s5 step 4).

    Page j's ideal end is round(N * (t_1 + ... + t_j) / T). It snaps to the nearest token
    within `window` of that end whose `final` flag is set, ties going to the earlier token,
    among the tokens that keep cuts increasing and leave every later page at least one
    token. With no such token, the ideal end is kept, moved into that range if needed.
    """
    pages, total = len(tokens_per_page), sum(tokens_per_page)
    if pages < 1 or min(tokens_per_page) < 1:
        raise ValueError("every target page holds at least one token")
    if n_tokens < pages:
        raise ValueError(f"{n_tokens} tokens cannot fill {pages} non-empty pages")
    cuts, previous, cumulative = [], 0, 0
    for j in range(1, pages):
        cumulative += tokens_per_page[j - 1]
        ideal = _round_ratio(n_tokens * cumulative, total, rounding)
        low, high = previous + 1, n_tokens - (pages - j)
        best = None
        for i in range(max(ideal - window, low), min(ideal + window, high) + 1):
            # Ascending order with a strict comparison keeps the earlier token on a tie.
            if final[i - 1] and (best is None or abs(i - ideal) < abs(best - ideal)):
                best = i
        cut = best if best is not None else min(max(ideal, low), high)
        cuts.append(cut)
        previous = cut
    return cuts


def render_pages(tokens: Sequence[str], line_ends: Sequence[bool], cuts: Sequence[int], line_breaks: str) -> list[str]:
    """Join each page's tokens with single spaces, or, with line_breaks="escape", keep paragraph
    breaks inside a page as the delivery's two-character escape (gap G9)."""
    bounds = [0, *cuts, len(tokens)]
    pages = []
    for a, b in zip(bounds, bounds[1:], strict=False):
        if line_breaks == "space":
            pages.append(" ".join(tokens[a:b]))
            continue
        parts = [tokens[a]]
        for i in range(a + 1, b):
            parts.append(LINE_BREAK_ESCAPE if line_ends[i - 1] else " ")
            parts.append(tokens[i])
        pages.append("".join(parts))
    return pages


def make_title(topic: str | None) -> str:
    """The title line: the topic on one line, without backslashes, which the delivery format reserves."""
    return " ".join((topic or "").replace("\\", " ").split())


# --- Building ------------------------------------------------------------------------------


def target_key(target: Target, settings: Settings) -> bytes:
    """K = SHA-256(prefix + story id + "|" + level), the target's key (planning review s5 step 2)."""
    text = settings.target_key + target.story_id + settings.target_separator + target.level
    return hashlib.sha256(text.encode("utf-8")).digest()


def rank_targets(targets: Sequence[Target], settings: Settings) -> list[Target]:
    """Targets in ascending K, the order in which they are processed and written."""
    keyed = sorted((target_key(t, settings), i) for i, t in enumerate(targets))
    return [targets[i] for _, i in keyed]


def story_keys(ranked: Sequence[Target], prefix: str) -> dict[str, str]:
    """One synthetic story key per combination, numbered by its first text in ascending K.

    The versions of one story share it (planning review s5 step 5: "The three versions of each
    combination share a synthetic story key"). It is computed over every target, so a
    smoke build gives each row the key the full build gives it.
    """
    first: dict[str, int] = {}
    for t in ranked:
        first.setdefault(t.combination or t.story_id, len(first) + 1)
    return {combo: f"{prefix}{rank}" for combo, rank in first.items()}


def smoke_size(n_targets: int, fraction: Fraction) -> int:
    """The smoke set's size, 1 per cent of the targets rounded up: 406 of 40,559."""
    return math.ceil(n_targets * fraction)


def group_of(target: Target) -> str:
    """The reporting group: the level for a generated text, "classic" for every classic."""
    return "classic" if target.kind == "classic" else (target.level or "(blank)")


@dataclass
class BuiltRow:
    """What the acceptance checks and the projection need from one written row."""

    target: Target
    selection: Selection
    page_tokens: list[int]
    chars_joined: int


def build_row(target: Target, rank: int, story_key: str, selection: Selection,
              texts: dict[tuple[int, int], tuple[str, str, str]], settings: Settings,
              typo_counts: Counter) -> tuple[list, BuiltRow]:
    """The published-schema row for one target, with a self-check that split_lines() reads it back."""
    tokens: list[str] = []
    line_ends: list[bool] = []
    for pick in selection.pieces:
        _, story, _ = texts[(pick.shard, pick.row)]
        start = len(tokens)
        for line in candidate_lines(story):
            words = line.split()
            tokens.extend(words)
            line_ends.extend([False] * (len(words) - 1) + [True])
        if len(tokens) - start != pick.n:
            raise StandinError(f"row {pick.row} of shard {pick.shard} has changed between the two passes")
    final = [is_sentence_final(t, settings.terminal_marks, settings.closers) for t in tokens]
    # Cuts are taken on the ASCII tokens, so the typography switch cannot move a page break.
    cuts = page_cuts(len(tokens), target.tokens_per_page, final, settings.snap_window, settings.rounding)
    shown = tokens
    first_topic = texts[(selection.pieces[0].shard, selection.pieces[0].row)][2]
    title = make_title(first_topic)
    if settings.typography:
        shown, counts = typography.transform_tokens(tokens, **settings.typography_rules)
        title, title_counts = typography.transform_text(title, **settings.typography_rules)
        typo_counts.update(counts)
        typo_counts.update(title_counts)
    pages = render_pages(shown, line_ends, cuts, settings.line_breaks)
    text = "\n".join([title, *pages]) + ("\n" if settings.trailing_newline else "")

    read_title, read_pages = split_lines(text)
    page_tokens = [len(p.split()) for p in read_pages]
    if (read_title != title or len(read_pages) != target.pages or sum(page_tokens) != len(tokens)
            or min(page_tokens) < 1):
        raise StandinError(f"target {target.story_id} ({target.level}): the written text does not read back")

    classic = target.kind == "classic"
    level = target.level
    if classic:
        folder = f"PD_{story_key} {level}" if level else f"PD_{story_key}"
    else:
        folder = f"{story_key}-{level}" if level else story_key
    row_by_col = {"id": f"{settings.id_prefix}{rank}", "folder": folder,
                  "hero": CLASSIC_HERO if classic else story_key, "world": "", "theme": "", "prompt": "",
                  "sidekick": "", "age": level, "lang": settings.lang, "title": title, "pages": target.pages,
                  "words": len(tokens), "build_error": "", "text": text}
    built = BuiltRow(target=target, selection=selection, page_tokens=page_tokens,
                     chars_joined=len(" ".join(read_pages)))
    return [row_by_col[c] for c in STORY_COLS], built


class _HashedCsv:
    """Write rows in the published tables' CSV dialect and hash the data rows as written."""

    def __init__(self, fh) -> None:
        self._fh, self._buf = fh, io.StringIO()
        self._csv = csv.writer(self._buf)  # the default dialect, as extract_story_texts.py writes
        self.sha = hashlib.sha256()
        self.rows = 0

    def _encode(self, row: list) -> str:
        self._csv.writerow(row)
        s = self._buf.getvalue()
        self._buf.seek(0)
        self._buf.truncate(0)
        return s

    def header(self, row: list) -> None:
        self._fh.write(self._encode(row))

    def write(self, row: list) -> None:
        s = self._encode(row)
        self._fh.write(s)
        self.sha.update(s.encode("utf-8"))
        self.rows += 1


def build(targets: Sequence[Target], source: Source, out: Path, settings: Settings, *, limit: int | None = None,
          structure_record: dict | None = None, log: Callable[[str], None] = _log) -> dict:
    """Build the stand-in for the first `limit` targets in ascending K (every target when None).

    Writes <out>/<lang>/stories.csv.xz, <out>/selection.tsv, <out>/NOTICE-SimpleStories.txt
    and <out>/standin_manifest.json, and returns the manifest. Candidates are consumed in
    ascending K, so the rows of a limited build are exactly the first rows of the full one.
    """
    started = time.time()
    ranked = rank_targets(targets, settings)
    n_all = len(ranked)
    smoke_n = smoke_size(n_all, settings.smoke_fraction)
    if limit is not None and not 1 <= limit <= n_all:
        raise StandinError(f"limit must lie between 1 and {n_all}")
    todo = ranked if limit is None else ranked[:limit]
    keys_of = story_keys(ranked, settings.story_key_prefix)
    timing = {}

    # Pass 1: every row, keeping only each candidate's key, length and place.
    t0 = time.time()
    pool = CandidatePool()
    scan = Counter()
    for shard, row, gid, story in source.scan():
        scan["rows_read"] += 1
        if scan["rows_read"] % 500_000 == 0:
            log(f"scanned {scan['rows_read']:,} rows")
        if not gid or story is None:
            scan["dropped_missing_field"] += 1
            continue
        n = len(story.split())
        if n < settings.min_tokens:
            scan["dropped_short"] += 1
            continue
        if settings.drop_backslash and "\\" in story:
            scan["dropped_backslash"] += 1
            continue
        pool.add(candidate_key(gid, settings.candidate_key), n, shard, row)
    scan["dropped_duplicate_id"] = pool.freeze(settings.duplicate_ids)
    scan["candidates"] = pool.size
    if source.expected_rows is not None and scan["rows_read"] != source.expected_rows:
        raise StandinError(f"read {scan['rows_read']:,} rows, the pinned split has {source.expected_rows:,}")
    timing["scan_seconds"] = round(time.time() - t0, 3)
    log(f"{scan['candidates']:,} candidates from {scan['rows_read']:,} rows")

    # Selection, strictly in ascending K: each target sees only what earlier targets left.
    t0 = time.time()
    selections = [select_for(pool, t.tokens, settings) for t in todo]
    timing["select_seconds"] = round(time.time() - t0, 3)

    # Pass 2: the chosen rows only, each checked against the key it was chosen by.
    t0 = time.time()
    wanted = {(p.shard, p.row) for s in selections for p in s.pieces}
    texts = source.fetch(wanted)
    for s in selections:
        for p in s.pieces:
            got = texts.get((p.shard, p.row))
            if got is None or candidate_key(got[0], settings.candidate_key) != p.key:
                raise StandinError(f"row {p.row} of shard {p.shard} was not read back as chosen")
    timing["fetch_seconds"] = round(time.time() - t0, 3)

    t0 = time.time()
    out = Path(out)
    table = out / settings.lang / TABLE_NAME
    table.parent.mkdir(parents=True, exist_ok=True)
    tmp = table.with_name(table.name + ".tmp")
    built: list[BuiltRow] = []
    typo_counts: Counter = Counter()
    sel_lines = ["\t".join(SELECTION_COLS)]
    prefix_sha = None
    try:
        with lzma.open(tmp, "wt", encoding="utf-8", newline="", preset=XZ_PRESET) as fh:
            writer = _HashedCsv(fh)
            writer.header(STORY_COLS)
            for rank, (target, selection) in enumerate(zip(todo, selections, strict=True), start=1):
                skey = keys_of[target.combination or target.story_id]
                row, b = build_row(target, rank, skey, selection, texts, settings, typo_counts)
                writer.write(row)
                built.append(b)
                if writer.rows == smoke_n:
                    prefix_sha = writer.sha.copy().hexdigest()
                within = within_tolerance(selection.tokens, target.tokens, settings.tolerance)
                gids = [texts[(p.shard, p.row)][0] for p in selection.pieces]
                sel_lines.append("\t".join(map(str, [
                    row[0], rank, target.story_id, target.kind, target.level, skey, target.pages, target.tokens,
                    selection.tokens, selection.m, int(within), ",".join(gids),
                    ",".join(str(p.n) for p in selection.pieces),
                    ",".join(str(int(w)) for w in selection.pieces_in_tolerance)])))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(table)
    _write_text(out / SELECTION_NAME, "\n".join(sel_lines) + "\n")
    _write_text(out / NOTICE_NAME, notice_text(settings))
    timing["write_seconds"] = round(time.time() - t0, 3)

    accept = acceptance(built, settings)
    accept["enforced"] = settings.enforce_acceptance
    manifest = {
        "builder": {"version": BUILDER_VERSION, "typography_version": typography.VERSION,
                    "files": {p.name: sha256_file(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
                    "code_commit": os.environ.get("INTRACT_CODE_COMMIT", "unknown"),
                    "python": platform.python_version(), "pyarrow": _pyarrow_version()},
        "settings": settings.to_record(),
        "source": {**source.record, **dict(sorted(scan.items()))},
        "structure": structure_record or {},
        "sizes": {"targets": n_all, "built": len(todo), "limit": limit, "smoke_size": smoke_n,
                  "smoke": limit == smoke_n},
        "selection": selection_summary(built, settings),
        "outputs": {"table": {"path": table.relative_to(out).as_posix(), "sha256": sha256_file(table),
                              "rows": writer.rows, "rows_sha256": writer.sha.hexdigest(),
                              "rows_sha256_first": {"rows": smoke_n, "sha256": prefix_sha} if prefix_sha else None},
                    "selection": {"path": SELECTION_NAME, "sha256": sha256_file(out / SELECTION_NAME)},
                    "notice": {"path": NOTICE_NAME, "licence": settings.licence}},
        "acceptance": accept,
        "projection": projection(built),
        "typography": {"enabled": settings.typography, "rules": settings.typography_rules,
                       "line_breaks": settings.line_breaks, "replacements": dict(sorted(typo_counts.items()))},
        "timing": {**timing, "wall_seconds": round(time.time() - started, 3),
                   "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
    }
    _write_text(out / MANIFEST_NAME, json.dumps(manifest, indent=1, ensure_ascii=False, allow_nan=False) + "\n")
    log(f"wrote {writer.rows:,} rows to {table}; acceptance {'passed' if accept['passed'] else 'FAILED'}")
    return manifest


TYPOGRAPHY_CLAUSE = ", and their punctuation was made typographic,"


def notice_text(settings: Settings) -> str:
    """The MIT notice written beside the table, saying what the builder changed under the settings of this build."""
    if settings.typography:
        return settings.notice
    # A build with typography off changed no punctuation, so the notice must not say it did.
    return settings.notice.replace(TYPOGRAPHY_CLAUSE, "")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)


def _pyarrow_version() -> str | None:
    module = sys.modules.get("pyarrow")
    return getattr(module, "__version__", None) if module else None


# --- Checks and records --------------------------------------------------------------------


def quantile(sorted_values: Sequence[float], q: float) -> float | None:
    """Type-7 quantile (linear interpolation, numpy's default), as the planning review's length profile computed."""
    if not sorted_values:
        return None
    h = (len(sorted_values) - 1) * q / 100
    lo = int(h)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (h - lo) * (sorted_values[hi] - sorted_values[lo])


def _compare(catalogue: list[int], standin: list[int], quantiles: Sequence[float], tolerance: Fraction) -> dict:
    cat, si = sorted(catalogue), sorted(standin)
    rows, passed = [], True
    for q in quantiles:
        c, s = quantile(cat, q), quantile(si, q)
        within = abs(Fraction(s) - Fraction(c)) <= tolerance * Fraction(c)
        passed &= within
        rows.append({"q": q, "catalogue": c, "standin": s, "relative": round((s - c) / c, 5), "within": within})
    return {"tolerance": str(tolerance), "quantiles": rows, "min": [cat[0], si[0]], "max": [cat[-1], si[-1]],
            "passed": passed}


def acceptance(rows: Sequence[BuiltRow], settings: Settings) -> dict:
    """Planning review s5 step 7: pages per text identical; per group, tokens-per-text quantiles within
    3 per cent and tokens-per-page quantiles within 10 per cent of the catalogue's."""
    groups: dict[str, tuple[list, list, list, list]] = defaultdict(lambda: ([], [], [], []))
    identical = True
    for r in rows:
        t = r.target
        identical &= len(r.page_tokens) == t.pages
        for g in (group_of(t), "all"):
            ct, st, cp, sp = groups[g]
            ct.append(t.tokens)
            st.append(sum(r.page_tokens))
            cp.extend(t.tokens_per_page)
            sp.extend(r.page_tokens)
    result: dict = {"pages_per_text_identical": identical, "groups": {}}
    passed = identical
    for g, (ct, st, cp, sp) in sorted(groups.items()):
        text = _compare(ct, st, settings.acceptance_quantiles, settings.text_tolerance)
        page = _compare(cp, sp, settings.acceptance_quantiles, settings.page_tolerance)
        passed &= text["passed"] and page["passed"]
        result["groups"][g] = {"texts": len(ct), "tokens_per_text": text, "tokens_per_page": page}
    result["passed"] = passed
    return result


def selection_summary(rows: Sequence[BuiltRow], settings: Settings) -> dict:
    """Per group: single matches within the tolerance, single fallbacks, joins and their share."""
    out: dict = {}
    for r in rows:
        for g in (group_of(r.target), "all"):
            s = out.setdefault(g, {"texts": 0, "single_within": 0, "single_nearest": 0, "joins": 0,
                                   "joins_with_nearest_piece": 0, "outside_tolerance": 0, "m": Counter()})
            sel, total = r.selection, r.target.tokens
            s["texts"] += 1
            s["m"][sel.m] += 1
            if sel.m == 1:
                s["single_within" if sel.pieces_in_tolerance[0] else "single_nearest"] += 1
            else:
                s["joins"] += 1
                s["joins_with_nearest_piece"] += not all(sel.pieces_in_tolerance)
            s["outside_tolerance"] += not within_tolerance(sel.tokens, total, settings.tolerance)
    for s in out.values():
        s["m"] = {str(k): v for k, v in sorted(s["m"].items())}
        s["share_joins"] = round(s["joins"] / s["texts"], 5)
    return dict(sorted(out.items()))


def projection(rows: Sequence[BuiltRow]) -> dict:
    """Planning review s5 step 8: the catalogue-to-stand-in ratio of characters (pages joined with one space)
    by group, which scales the character- and subword-driven stages measured on the stand-in."""
    acc: dict[str, list] = defaultdict(lambda: [0, 0, 0, 0, True])
    for r in rows:
        for g in (group_of(r.target), "all"):
            a = acc[g]
            if r.target.chars_joined is None:
                a[4] = False
            else:
                a[0] += r.target.chars_joined
            a[1] += r.chars_joined
            a[2] += r.target.tokens
            a[3] += sum(r.page_tokens)
    out = {}
    for g, (cc, sc, ct, st, complete) in sorted(acc.items()):
        out[g] = {"catalogue_chars": cc if complete else None, "standin_chars": sc,
                  "catalogue_tokens": ct, "standin_tokens": st,
                  "char_ratio": round(cc / sc, 5) if complete and sc else None,
                  "catalogue_chars_per_token": round(cc / ct, 4) if complete and ct else None,
                  "standin_chars_per_token": round(sc / st, 4) if st else None}
    return out


# --- Command line --------------------------------------------------------------------------


def _structure_record(path: Path, targets: Sequence[Target]) -> dict:
    groups = Counter(f"{t.kind}|{t.level or '(blank)'}" for t in targets)
    return {"file": path.name, "sha256": sha256_file(path), "rows": len(targets),
            "combination_column": any(t.combination != t.story_id for t in targets),
            "texts_by_kind_and_level": dict(sorted(groups.items()))}


def main(argv: list[str] | None = None) -> int:
    """Command line for download, verify and build; see the module docstring."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="the pipeline's config directory")
    common.add_argument("--split", default="train", help="the pinned split to use (train; test for checks)")
    p = argparse.ArgumentParser(prog="python -m standin.build_standin", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", parents=[common], help="fetch and verify the pinned shards")
    d.add_argument("--dest", type=Path, required=True)
    v = sub.add_parser("verify", parents=[common], help="verify the pinned shards in a directory")
    v.add_argument("--shards", type=Path, required=True)
    b = sub.add_parser("build", parents=[common], help="build the stand-in table")
    b.add_argument("--structure", type=Path, required=True, help="the structure table (catalogue_structure.py)")
    b.add_argument("--shards", type=Path, required=True, help="the directory holding the pinned shards")
    b.add_argument("--out", type=Path, required=True)
    size = b.add_mutually_exclusive_group()
    size.add_argument("--smoke", action="store_true", help="the smoke set: the smallest 1 per cent of K")
    size.add_argument("--limit", type=int, help="the first LIMIT targets in ascending K")
    b.add_argument("--typography", choices=("on", "off"), help="override the config switch")
    b.add_argument("--line-breaks", choices=("space", "escape"), help="override the config switch")
    args = p.parse_args(argv)

    try:
        settings = Settings.load(args.config)
        if args.split not in settings.splits:
            p.error(f"--split must be one of {sorted(settings.splits)}")
        pins = settings.splits[args.split]
        if args.cmd == "download":
            download(pins, args.dest, settings)
            return 0
        if args.cmd == "verify":
            verify_shards(args.shards, pins)
            return 0
        overrides = {}
        if args.typography:
            overrides["typography"] = args.typography == "on"
        if args.line_breaks:
            overrides["line_breaks"] = args.line_breaks
        settings = dataclasses.replace(settings, **overrides)
        targets = read_structure(args.structure)
        paths = verify_shards(args.shards, pins)
        record = {"repo": settings.repo, "revision": settings.revision, "licence": settings.licence,
                  "split": args.split, "files": [dict(dataclasses.asdict(pin), verified=True) for pin in pins]}
        source = ParquetSource(paths, settings.batch_size, record, settings.expected_rows.get(args.split))
        limit = smoke_size(len(targets), settings.smoke_fraction) if args.smoke else args.limit
        manifest = build(targets, source, args.out, settings, limit=limit,
                         structure_record=_structure_record(args.structure, targets))
    except (StandinError, StructureError, OSError, KeyError, lzma.LZMAError) as e:
        print(f"Stopped: {e}", file=sys.stderr)
        return 1
    # Outputs are written either way. A failed acceptance check is always printed and recorded in the manifest;
    # it sets the exit status only when standin.toml [acceptance] enforce is true (PENDING the PI's ruling).
    if manifest["acceptance"]["passed"]:
        return 0
    failed = sorted(g for g, r in manifest["acceptance"]["groups"].items()
                    if not (r["tokens_per_text"]["passed"] and r["tokens_per_page"]["passed"]))
    print(f"acceptance check FAILED in {', '.join(failed) or 'the page counts'}; see {MANIFEST_NAME}"
          + ("" if settings.enforce_acceptance else " ([acceptance] enforce = false: exit status 0)"), file=sys.stderr)
    return 3 if settings.enforce_acceptance else 0


if __name__ == "__main__":
    raise SystemExit(main())
