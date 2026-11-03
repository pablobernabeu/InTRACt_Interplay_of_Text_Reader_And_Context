"""Direct-speech spans and dialogue share, a covariate in every confirmatory model.

Measures: "Dialogue share is the proportion of a text's words that lie inside direct speech, detected from the
quotation marks catalogued by the Unicode Common Locale Data Repository". S3, the detector: "Dialogue spans are
detected from the primary and alternate quotation pairs of release 47 of the Unicode Common Locale Data
Repository ... Any further marks that the structural counts admit are added. The direction of every ambiguous mark
is read from its spacing. A line-initial dialogue dash opens a turn that runs to the end of the line, if line
breaks survive within pages, and an opener unmatched at the end of its page closes there. In Hebrew, a straight
double or single quotation mark is a gershayim or geresh only when letters stand on both sides". S3, dialogue
share row: "The share of a text's words whose first letter lies inside direct speech".

The quotation pairs come from config/languages.toml (`quotes`): the CLDR 47 primary and alternate pairs of the
locale plus the marks the structural counts admit. Detection runs on the text after the stage-wide normalisation
(NFC, invisible format characters removed), never on lookup keys (S3).

Promoted from nonnative/names-dialogue-freq/scripts/dialogue.py (spans: pairs, the apostrophe guard on
single-quote marks, dash turns) and nonnative/verify-names-dialogue-sweep/scripts/safeguard_decomposition.py
(dir_only: straight double quotes read in a second pass, with direction from spacing). The dir_only variant is the
one that produced the registered provisional figures (P54: "The spacing rule provisionally lifts Arabic to
r = .848 and kappa = .772"); the benchmark's minimum-span safeguard is not registered and is not applied.
Two changes follow the registered text where it differs from the benchmark: each locale uses its own CLDR primary
and alternate pairs (the benchmark added a fixed union of pairs and the primary pair only), and an opener closes
at the end of its page (the benchmark scored single stories without pages).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from intract_features.records import PAGE_JOINER  # the joining space is never inside speech


def _is_letter(ch: str) -> bool:
    # dialogue.py's _is_letter: any letter or number, used by the spacing rules
    return unicodedata.category(ch)[0] in "LN"


@dataclass(frozen=True)
class QuoteInventory:
    """The marks of one locale and the rules that read them."""

    pairs: tuple[tuple[str, str], ...]
    apostrophe_marks: frozenset[str]
    dashes: frozenset[str]
    dash_turns: bool
    letter_flanked: frozenset[str]
    open_context: str
    guard_open_context: str

    @classmethod
    def from_config(cls, quotes: Iterable[Sequence[str]], cfg: Mapping[str, Any], iso: str) -> QuoteInventory:
        """Build the inventory from languages.toml's `quotes` and the [dialogue] table of the stage config."""
        pairs = tuple((str(o), str(c)) for o, c in quotes)
        flanked = cfg.get("letter_flanked", {}).get(iso, [])
        return cls(pairs=pairs, apostrophe_marks=frozenset(cfg["apostrophe_marks"]), dashes=frozenset(cfg["dashes"]),
                   dash_turns=bool(cfg["dash_turns"]), letter_flanked=frozenset(flanked),
                   open_context=str(cfg["open_context"]), guard_open_context=str(cfg["guard_open_context"]))

    def asymmetric(self) -> dict[str, set[str]]:
        """Opener to closers, for the pairs whose opener and closer differ."""
        out: dict[str, set[str]] = {}
        for o, c in self.pairs:
            if o != c:
                out.setdefault(o, set()).add(c)
        return out

    def symmetric(self) -> set[str]:
        """Marks that open and close alike (the straight double quote), read with direction from spacing."""
        return {o for o, c in self.pairs if o == c}


def _flanked(text: str, i: int, inv: QuoteInventory) -> bool:
    # S3's Hebrew rule: a straight mark with letters on both sides is a gershayim or geresh, not a delimiter
    return (text[i] in inv.letter_flanked and 0 < i < len(text) - 1
            and _is_letter(text[i - 1]) and _is_letter(text[i + 1]))


def _pass_pairs(page: str, inv: QuoteInventory) -> list[bool]:
    """dialogue.spans over the pairs whose opener and closer differ, plus dash turns.

    No nesting: while a quotation is open, other openers are ordinary characters. A mark that doubles as an
    apostrophe opens only after a space, the line start or opening punctuation and before a letter, and closes
    only after a non-space and before a non-letter, so "don't" and "Tom's" never close a quotation.
    """
    pairs = inv.asymmetric()
    guarded = {o for o, cs in pairs.items() if o in inv.apostrophe_marks or cs & inv.apostrophe_marks}
    n = len(page)
    inside = [False] * n
    open_ch: str | None = None
    closers: set[str] = set()
    line_start, dash_turn = True, False
    for i, c in enumerate(page):
        if c == "\n":
            dash_turn = False  # a dash turn runs to the end of its line
            line_start = True
            continue
        if inv.dash_turns and line_start and c in inv.dashes and open_ch is None:
            dash_turn = True
            line_start = False
            continue
        if not c.isspace():
            line_start = False
        if _flanked(page, i, inv):
            inside[i] = open_ch is not None or dash_turn
            continue
        prev = page[i - 1] if i > 0 else " "
        nxt = page[i + 1] if i + 1 < n else " "
        if open_ch is None:
            if c in pairs:
                if c in guarded and not ((prev.isspace() or prev in inv.guard_open_context) and _is_letter(nxt)):
                    inside[i] = dash_turn
                    continue
                open_ch, closers = c, pairs[c]
                continue
            inside[i] = dash_turn
        else:
            if c in closers:
                if open_ch in guarded and (prev.isspace() or _is_letter(nxt)):
                    inside[i] = True
                    continue
                open_ch, closers = None, set()
                continue
            inside[i] = True
    return inside  # an opener still open at the page end has marked everything after it: it closes there


def _pass_symmetric(page: str, inv: QuoteInventory) -> list[bool]:
    """safeguard_decomposition.dir_only over marks that open and close alike, per page.

    A mark opens where it follows a space or opening punctuation and precedes a non-space, and closes where it
    follows a non-space and precedes a space, punctuation or the end; where the spacing says both or neither, it
    closes an open quotation or else opens one. A mark that doubles as an apostrophe takes the stricter guard of
    the first pass instead, and is no delimiter where the guard admits neither direction.
    """
    marks = inv.symmetric()
    n = len(page)
    inside = [False] * n
    if not marks:
        return inside
    open_at: dict[str, int | None] = dict.fromkeys(marks)
    for i, c in enumerate(page):
        if c not in marks or _flanked(page, i, inv):
            continue
        prev = page[i - 1] if i > 0 else " "
        nxt = page[i + 1] if i + 1 < n else " "
        if c in inv.apostrophe_marks:
            if (prev.isspace() or prev in inv.guard_open_context) and _is_letter(nxt):
                kind = "open"
            elif not prev.isspace() and not _is_letter(nxt):
                kind = "close"
            else:
                continue
        else:
            opener = (prev.isspace() or prev in inv.open_context) and not nxt.isspace()
            closer = (nxt.isspace() or unicodedata.category(nxt)[0] in "PZ" or i + 1 == n) and not prev.isspace()
            if opener and not closer:
                kind = "open"
            elif closer and not opener:
                kind = "close"
            else:
                kind = "close" if open_at[c] is not None else "open"
        if kind == "open":
            open_at[c] = i
        elif open_at[c] is not None:
            for k in range(open_at[c] + 1, i):
                inside[k] = True
            open_at[c] = None
    for start in open_at.values():
        if start is not None:  # an opener unmatched at the end of its page closes there
            for k in range(start + 1, n):
                inside[k] = True
    return inside


def page_speech(page: str, inv: QuoteInventory) -> list[bool]:
    """One flag per character of a page: True inside direct speech, delimiters excluded."""
    a = _pass_pairs(page, inv)
    b = _pass_symmetric(page, inv)
    return [x or y for x, y in zip(a, b, strict=True)]


def speech_mask(pages: Sequence[str], inv: QuoteInventory) -> list[bool]:
    """Flags over the document text (the pages joined with one space), detected page by page."""
    out: list[bool] = []
    for k, page in enumerate(pages):
        if k:
            out.extend([False] * len(PAGE_JOINER))
        out.extend(page_speech(page, inv))
    return out


def speech_words(mask: Sequence[bool], anchors: Iterable[int]) -> tuple[int, int]:
    """(words whose first letter or digit lies inside speech, words).

    `anchors` are the registered words' first letters or digits (text.words.Word.anchor), so a word counts
    by "its first letter" (S3, dialogue share row) whatever punctuation its token carries.
    """
    inside = total = 0
    for k in anchors:
        total += 1
        inside += bool(mask[k])
    return inside, total


def share(inside: int, total: int) -> float | None:
    """Dialogue share, or None for a text without words (undefined by construction)."""
    return inside / total if total else None


def spans_with_speech(mask: Sequence[bool], anchors: Sequence[int], spans: Iterable[tuple[int, int]]) -> list[bool]:
    """For each [start, end) span (a sentence), whether one of the words anchored in it starts inside speech.

    This is the sentence-level speech status that the registered reported-speech rule and its kappa gate read
    (S3, Validation without human annotation), attributed to sentences as bench_dialogue_mt.py attributes it.
    """
    out = []
    for start, end in spans:
        out.append(any(mask[k] for k in anchors if start <= k < end))
    return out
