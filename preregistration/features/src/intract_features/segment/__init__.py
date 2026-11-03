"""Sentence segmentation: the registered SaT call, the union segmenter and the frozen check rules.

Modules:

- ``sat``: the registered Segment any Text (SaT) call for English (Materials, the segmentation
  paragraph; supplementary.qmd S3), from per-character boundary probabilities to sentence spans.
- ``union``: the union segmenter that the translations use (S3, the projection paragraph). English
  does not use it.
- ``rules``: the frozen English rule segmenter that the second segmentation check scores SaT
  against (Outcome-neutral quality checks), and the frozen target-only rule of the benchmark gold.
- ``diagnostics``: the benchmark's boundary scorer, the segmentation diagnostics of S3 and the
  five-sentence floor (Outcome-blind dimension reduction).

The ``segments`` artefact holds one record per document:

``story_id``, ``lang``
    as in the ``documents`` artefact.
``segmenter``
    ``"sat"`` for the registered SaT call. In English this is the registered segmentation. In a
    translation it is SaT alone, which is the union segmenter's input and the fallback that the
    segmentation checks can impose, not the served segmentation.
``is_source``
    whether the language is the English source of every translation.
``text_sha256``
    SHA-256 of the document's joined text, so that a stale artefact is caught.
``n_characters``, ``n_sentences``
``sentence_fields``, ``sentences``
    ``[start, end, page_start, page_end]`` per sentence: a ``[start, end)`` span over
    ``Document.text`` with surrounding whitespace trimmed, and the indices of the pages that hold
    its first and last characters.
``newline_forced``
    boundaries that only an in-page line break forced (plan v3: "counting the boundaries that
    newlines force").
``candidates``
    ``{"pos": [...], "p": [...]}``: p', the boundary probability maximised over a character and the
    whitespace run after it, at the union segmenter's candidate positions only. Each value is the
    float32 the model gave, written with nine significant digits so that it reads back exactly.
``floor``
    for the English source only: ``{"min_english_sentences": 5, "excluded": bool}``.

Boundary convention (the benchmark's seglib2): a boundary is the index of the last non-space
character of every sentence of a text except the last, so ``end - 1`` of each sentence but the
last.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from typing import NamedTuple

SENTENCE_FIELDS = ("start", "end", "page_start", "page_end")


class Sentence(NamedTuple):
    """One sentence of a segments record."""

    start: int
    end: int
    page_start: int
    page_end: int


def sentences_from_record(rec: dict) -> list[Sentence]:
    """The sentences of a ``segments`` record, checked against its declared field order."""
    fields = tuple(rec.get("sentence_fields", SENTENCE_FIELDS))
    if fields != SENTENCE_FIELDS:
        raise ValueError(f"unexpected sentence fields {fields!r}; this reader knows {SENTENCE_FIELDS!r}")
    return [Sentence(*row) for row in rec["sentences"]]


def boundaries_of(spans: Sequence[Sequence[int]]) -> list[int]:
    """Boundary offsets (the last character of every sentence but the last) from ``[start, end)`` spans."""
    return [int(span[1]) - 1 for span in spans[:-1]]


def page_index(page_starts: Sequence[int], offset: int) -> int:
    """Index of the page holding character ``offset``, given each page's start offset in the joined text.

    A joining space belongs to the page before it, as in ``records.Document.page_of``; the bisection
    keeps the lookup logarithmic for long classics.
    """
    if offset < 0:
        raise ValueError(f"negative offset {offset}")
    return bisect_right(page_starts, offset) - 1


def page_anchors(page_spans: Sequence[tuple[int, int]], spans: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """The pages holding the first and last characters of each ``[start, end)`` span."""
    if not spans:
        return []  # a document without pages (a title-only row) has no sentence, and no shard should stop for it
    starts = [a for a, _ in page_spans]
    if not starts:
        raise ValueError("a document needs at least one page")
    total = page_spans[-1][1]
    out = []
    for a, b in spans:
        if not 0 <= a < b <= total:
            raise ValueError(f"span {(a, b)} lies outside the text (length {total})")
        out.append((page_index(starts, a), page_index(starts, b - 1)))
    return out
