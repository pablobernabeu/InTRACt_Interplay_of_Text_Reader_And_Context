"""The benchmark's boundary scorer, the segmentation diagnostics and the five-sentence floor.

Scoring is the benchmark's (``presub/translated_union/scripts/tu_common.py``: ``canon``, ``counts``,
``prf``, ``boot_prf``), which TU-3 used for English SaT against the rule: per-text true positive,
false positive and false negative counts, micro-averaged precision, recall and F1, and percentile
95% intervals from a cluster bootstrap over texts. Materials: "Boundary accuracy is scored without
counting as an error a quotation mark placed on the other side of a boundary"; S3: "exact matching is
reported beside that score".

The diagnostics follow S3: "Per language, we will report the mean and standard deviation of sentence
length and the proportion of sentences ending without a terminal mark. For every text, we will report
the ratios of its sentences and of its terminal marks to those of its English source, with their
median, interquartile range and share within 10 per cent. These diagnostics decide nothing."

The floor is Outcome-blind dimension reduction: "A text whose English source has fewer than five
sentences enters no family's solution in any language." Its minimum is pipeline.toml [floor].
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Iterable, Sequence

# ---------------------------------------------------------------- the boundary scorer


def canon(text: str, i: int, quotes: Iterable[str]) -> int:
    """Quote-tolerant boundary: move back over whitespace and quotation marks."""
    quotes = frozenset(quotes)
    while i > 0 and (text[i] in quotes or text[i].isspace()):
        i -= 1
    return i


def counts(pred: set[int], gold: set[int]) -> tuple[int, int, int]:
    """(true positives, false positives, false negatives) of two boundary sets."""
    return len(pred & gold), len(pred - gold), len(gold - pred)


def prf(tp: float, fp: float, fn: float) -> tuple[float, float, float]:
    """Precision, recall and F1, each 0 when undefined."""
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def score_text(text: str, pred: Iterable[int], gold: Iterable[int],
               quotes: Iterable[str]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Quote-tolerant and exact counts of one text, as TU-3 scored English SaT against the rule."""
    quotes = frozenset(quotes)
    pred, gold = set(pred), set(gold)
    tolerant = counts({canon(text, b, quotes) for b in pred}, {canon(text, g, quotes) for g in gold})
    return tolerant, counts(pred, gold)


def bootstrap_rng(seed: int, spawn_key: int):
    """NumPy generator ``SeedSequence(seed, spawn_key=(spawn_key,))``, the benchmark's per-language stream."""
    import numpy as np

    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=(spawn_key,)))


def boot_prf(rows: Sequence[Sequence[int]], rng, n_boot: int) -> dict:
    """Point P, R and F1 (0 to 100) with percentile 95% intervals over texts, as the benchmark's ``boot_prf``.

    The keys ``F1_unrounded`` and ``F1_ci_unrounded`` (0 to 1) are additions, so that a decision at .95
    never rests on a rounded value.
    """
    import numpy as np

    a = np.asarray(rows, dtype=float).reshape(-1, 3)
    if len(a) == 0:
        return {"n_texts": 0}
    p, r, f = prf(*a.sum(0))
    idx = rng.integers(0, len(a), (n_boot, len(a)))
    s = a[idx].sum(1)
    tp, fp, fn = s[:, 0], s[:, 1], s[:, 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        P = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
        R = np.where(tp + fn > 0, tp / (tp + fn), 0.0)
        F = np.where(P + R > 0, 2 * P * R / (P + R), 0.0)

    def q(v):
        return [round(100 * float(np.percentile(v, 2.5)), 1), round(100 * float(np.percentile(v, 97.5)), 1)]

    return {"P": round(100 * float(p), 1), "R": round(100 * float(r), 1), "F1": round(100 * float(f), 1),
            "P_ci": q(P), "R_ci": q(R), "F1_ci": q(F), "n_texts": len(a), "tp": int(a[:, 0].sum()),
            "fp": int(a[:, 1].sum()), "fn": int(a[:, 2].sum()), "n_boot": n_boot,
            "F1_unrounded": float(f),
            "F1_ci_unrounded": [float(np.percentile(F, 2.5)), float(np.percentile(F, 97.5))]}


# ---------------------------------------------------------------- summaries


def percentile(values: Sequence[float], q: float) -> float:
    """NumPy's default ('linear') percentile, in pure Python, with NumPy's two-sided interpolation."""
    x = sorted(values)
    if not x:
        raise ValueError("percentile of an empty sequence")
    h = (len(x) - 1) * (q / 100.0)
    lo = math.floor(h)
    hi = min(lo + 1, len(x) - 1)
    t = h - lo
    a, b = x[lo], x[hi]
    # numpy.lib._function_base_impl._lerp: from the nearer end, so that t = 1 returns b exactly
    return b - (b - a) * (1 - t) if t >= 0.5 else a + (b - a) * t


def quantiles(values: Sequence[float], qs: Sequence[float]) -> dict[str, float]:
    """Named percentiles ("p50" and so on) of a sequence."""
    return {f"p{q:g}": percentile(values, q) for q in qs}


def mean_sd(values: Sequence[float]) -> tuple[float | None, float | None]:
    """Mean and sample standard deviation (n - 1), None where undefined."""
    n = len(values)
    if n == 0:
        return None, None
    m = math.fsum(values) / n
    if n == 1:
        return m, None
    return m, math.sqrt(math.fsum((v - m) ** 2 for v in values) / (n - 1))


def ratio_summary(values: Iterable[float | None]) -> dict | None:
    """Median, interquartile range and share within 10 per cent of 1, as TU-3 summarised ratios to English."""
    v = [x for x in values if x is not None and math.isfinite(x)]
    if not v:
        return None
    return {"median": round(percentile(v, 50), 3), "iqr": [round(percentile(v, 25), 3), round(percentile(v, 75), 3)],
            "share_within_10pct": round(sum(abs(x - 1) <= 0.10 for x in v) / len(v), 3), "n": len(v)}


# ---------------------------------------------------------------- per-text diagnostics


def ends_with_terminal(text: str, end: int, terminal: Iterable[str], closing: Iterable[str]) -> bool:
    """Whether the sentence ending at ``end`` (exclusive) ends in a terminal mark, closing marks skipped."""
    terminal, closing = frozenset(terminal), frozenset(closing)
    i = end - 1
    while i > 0 and text[i] in closing:
        i -= 1
    return i >= 0 and text[i] in terminal


def terminal_marks(text: str, terminal: Iterable[str]) -> int:
    """Number of terminal marks in a text (the numerator of the terminal-mark ratio to English)."""
    terminal = frozenset(terminal)
    return sum(ch in terminal for ch in text)


def nonspace_length(text: str, a: int, b: int) -> int:
    """Non-space characters in text[a:b], the union segmenter's length unit."""
    return sum(not ch.isspace() for ch in text[a:b])


def words_per_span(anchors: Sequence[int], spans: Sequence[tuple[int, int]]) -> list[int]:
    """Registered words in each ``[start, end)`` span, a word belonging to the span that holds its anchor.

    ``anchors`` are the words' anchors in text order (``text.words.words``: the offset of a word's first
    letter or digit), which no sentence boundary can split.
    """
    return [bisect_left(anchors, b) - bisect_left(anchors, a) for a, b in spans]


def floor_excluded(n_english_sentences: int, minimum: int) -> bool:
    """The five-sentence floor: True when the English source has fewer than ``minimum`` sentences."""
    return n_english_sentences < minimum
