"""The union segmenter of the translations. English does not use it.

Ported from the benchmark's ``presub/translated_union/scripts/union_lib.py`` (itself ported from
``rigour/segmentation/scripts/ags_lib.py``), whose port test reproduced the earlier benchmark
exactly. The search, the page anchors and the terminal additions are unchanged; the registered
constants now come from ``config/stages/sat.toml`` ([candidates], [colon_rule] and [union]), and
the legacy switches that only the port test needed are gone.

The specification, from supplementary.qmd S3 (the projection paragraph) and feature plan v3 ("The
union segmenter"):

- p'(c) is the maximum of SaT's probability over character c and the whitespace run after it.
- "Candidates are the characters that end a whitespace token, are punctuation or have a boundary
  probability of at least 10^-5, and a colon is never one."
- "For an English source of m sentences, an exact Viterbi search chooses m - 1 increasing
  candidates. It maximises the summed log-odds of the chosen boundaries plus a length term for
  each target segment", the log-likelihood of the segment's non-space length under a normal model
  centred on its English sentence's length times the text's own length ratio (Gale and Church,
  1993), with a variance per language from FLORES-200 dev. "No weight is tuned."
- "Where the structural counts confirm that a translation's pages match its English source's, the
  search runs page by page."
- "The union then adds every boundary of the registered model on the translation that falls at a
  terminal mark, skipping closing quotation marks."
- "A text with fewer candidates than projected boundaries has its sentence-based features declared
  missing" (the functions return None).

The character-level helpers are pure Python so that the SaT stage can choose and store candidate
positions without NumPy; the search imports NumPy when it runs.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache

# In Python's str patterns \s is exactly str.isspace() (tests/unit/test_segment.py checks every code point),
# so these scans run the benchmark's character loops at C speed with the same results.
_WS_RUN = re.compile(r"\s+")
_TOKEN_END = re.compile(r"\S(?=\s)")


@lru_cache(maxsize=8192)
def _is_punctuation(ch: str) -> bool:
    return unicodedata.category(ch).startswith("P")


@dataclass(frozen=True)
class UnionSettings:
    """The registered constants of the union segmenter, read from the sat stage's configuration."""

    floor: float
    colons: frozenset[str]
    terminal_marks: frozenset[str]
    semicolon_langs: frozenset[str]
    closing_marks: frozenset[str]
    eps: float
    quote_term: bool
    quote_term_weight: float
    quote_anchors: frozenset[str]

    @classmethod
    def from_config(cls, stage_cfg: dict) -> UnionSettings:
        """Build the settings from ``config/stages/sat.toml`` as loaded by ``config.load``."""
        u = stage_cfg["union"]
        return cls(floor=float(stage_cfg["candidates"]["floor"]),
                   colons=frozenset(stage_cfg["colon_rule"]["colons"]),
                   terminal_marks=frozenset(u["terminal_marks"]),
                   semicolon_langs=frozenset(u["semicolon_terminal_langs"]),
                   closing_marks=frozenset(u["closing_marks"]),
                   eps=float(u["eps"]),
                   quote_term=bool(u["quote_term"]),
                   quote_term_weight=float(u["quote_term_weight"]),
                   quote_anchors=frozenset(u["quote_anchors"]))

    def terminal_set(self, lang: str) -> frozenset[str]:
        """Terminal marks for a language: ';' ends a sentence only in Greek, where NFC maps the question mark to it."""
        return (self.terminal_marks | {";"}) if lang in self.semicolon_langs else self.terminal_marks


def _floats(p: Sequence[float]) -> list[float]:
    # A NumPy array converts to Python floats in one C call; a per-element loop over it would be slow.
    return p.tolist() if hasattr(p, "tolist") else list(p)


def char_boundary_probs(text: str, p: Sequence[float]) -> list[float]:
    """p'(c): the maximum of p over character c and the whitespace run after it (0 inside such runs).

    A leading whitespace run, which no character precedes, keeps its maximum on its first position, as in
    the benchmark's loop.
    """
    p = _floats(p)
    n = len(text)
    if len(p) != n:
        raise ValueError(f"{len(p)} probabilities for {n} characters")
    out = list(p)
    for m in _WS_RUN.finditer(text):
        s, e = m.span()
        k = s - 1 if s > 0 else 0
        out[k] = max(p[k:e])
        if e > k + 1:
            out[k + 1:e] = [0.0] * (e - k - 1)
    return out


def last_nonspace(text: str) -> int:
    """Index of the last non-space character of a text, or -1 when it has none."""
    last = len(text) - 1
    while last >= 0 and text[last].isspace():
        last -= 1
    return last


def candidates(text: str, pprime: Sequence[float], floor: float, colons: Iterable[str]) -> list[int]:
    """Candidate boundary positions: non-space characters before the last one that end a whitespace token,
    are Unicode punctuation or have p' of at least ``floor``; a colon is never one."""
    colons = frozenset(colons)
    last = last_nonspace(text)
    if last <= 0:
        return []
    cand = {m.start() for m in _TOKEN_END.finditer(text)}
    punct = {ch for ch in set(text) if _is_punctuation(ch)}
    if punct:
        cand.update(i for i, ch in enumerate(text) if ch in punct)
    cand.update(i for i, v in enumerate(pprime) if v >= floor)
    return sorted(c for c in cand if c < last and not text[c].isspace() and text[c] not in colons)


def nonspace_prefix(text: str) -> list[int]:
    """a[i] = number of non-space characters in text[:i]."""
    out = [0] * (len(text) + 1)
    run = 0
    for i, ch in enumerate(text):
        if not ch.isspace():
            run += 1
        out[i + 1] = run
    return out


def quote_prefix(text: str, anchors: Iterable[str]) -> list[int]:
    """a[i] = number of anchor quotation marks in text[:i]."""
    anchors = frozenset(anchors)
    out = [0] * (len(text) + 1)
    run = 0
    for i, ch in enumerate(text):
        if ch in anchors:
            run += 1
        out[i + 1] = run
    return out


def _cuts(text: str, bounds: Iterable[int]) -> list[int]:
    return [-1, *sorted(bounds), len(text) - 1]


def quote_counts(text: str, bounds: Iterable[int], anchors: Iterable[str]) -> list[int]:
    """Anchor quotation marks in each sentence that a boundary set defines."""
    qp = quote_prefix(text, anchors)
    cuts = _cuts(text, bounds)
    return [qp[b + 1] - qp[a + 1] for a, b in zip(cuts[:-1], cuts[1:], strict=True)]


def spans_lens(text: str, bounds: Iterable[int]) -> list[int]:
    """Non-space characters in each sentence that a boundary set defines (the length term's unit)."""
    nsp = nonspace_prefix(text)
    cuts = _cuts(text, bounds)
    return [nsp[b + 1] - nsp[a + 1] for a, b in zip(cuts[:-1], cuts[1:], strict=True)]


def project(text: str, p: Sequence[float] | None, eng_lens: Sequence[int], s2: float, settings: UnionSettings,
            eng_quotes: Sequence[int] | None = None, w_q: float = 0.0,
            pprime: Sequence[float] | None = None) -> tuple[list[int] | None, dict]:
    """Project the English sentence ends onto a translation by the exact Viterbi search.

    Returns the sorted boundaries, or None when the text has fewer candidates than projected boundaries
    (its sentence-based features are then missing), and a diagnostics dict. ``pprime`` may replace ``p``
    when the probabilities come from a ``segments`` record, which stores p' at candidate positions.
    The quotation-mark term (``eng_quotes`` with ``w_q`` > 0) stays off unless admitted (S3; pending).
    """
    import numpy as np

    m = len(eng_lens)
    if m <= 1:
        return [], {"K": 0}
    if pprime is None:
        if p is None:
            raise ValueError("project needs p or pprime")
        pp_list = char_boundary_probs(text, p)
    else:
        pp_list = _floats(pprime)
        if len(pp_list) != len(text):
            raise ValueError(f"{len(pp_list)} values of p' for {len(text)} characters")
    pp = np.asarray(pp_list, dtype=float)
    pos = np.asarray(candidates(text, pp_list, settings.floor, settings.colons), dtype=int)
    K = len(pos)
    if m - 1 > K:
        return None, {"K": K, "infeasible": True}
    q = np.clip(pp[pos], settings.eps, 1 - settings.eps)
    s = np.log(q) - np.log1p(-q)
    nsp = np.asarray(nonspace_prefix(text), dtype=np.int64)
    tot = float(nsp[-1])
    cum = nsp[pos + 1].astype(float)
    L = np.asarray(eng_lens, dtype=float)
    c = tot / L.sum() if L.sum() > 0 else 1.0
    use_q = eng_quotes is not None and w_q > 0
    if use_q:
        qp = np.asarray(quote_prefix(text, settings.quote_anchors), dtype=np.int64)
        qcum = qp[pos + 1].astype(float)
        qtot = float(qp[-1])
        Q = np.asarray(eng_quotes, dtype=float)
        use_q = qtot == Q.sum() and qtot > 0

    def ll(lens, Li):
        # Gale and Church (1993): the variance grows with the English length; the floor of 1 keeps a
        # one-character sentence from dominating.
        mu, var = c * Li, max(s2 * Li, 1.0)
        return -(lens - mu) ** 2 / (2.0 * var)

    def qpen(qs, Qi):
        return -w_q * (qs != Qi) if use_q else 0.0

    NEG = -1e18
    dp = ll(cum, L[0]) + s + (qpen(qcum, Q[0]) if use_q else 0.0)
    tri = np.tril(np.ones((K, K), dtype=bool), k=-1)  # tri[k, j]: candidate j precedes candidate k
    seglen = cum[:, None] - cum[None, :]
    segq = (qcum[:, None] - qcum[None, :]) if use_q else None
    backs = []
    for i in range(1, m - 1):
        M = dp[None, :] + ll(seglen, L[i])
        if use_q:
            M = M + qpen(segq, Q[i])
        M = np.where(tri, M, NEG)
        arg = M.argmax(axis=1)
        dp = M[np.arange(K), arg] + s
        dp[0] = NEG  # the first candidate cannot close a later sentence
        backs.append(arg)
    final = dp + ll(tot - cum, L[m - 1]) + (qpen(qtot - qcum, Q[m - 1]) if use_q else 0.0)
    k = int(final.argmax())
    chosen = [k]
    for arg in reversed(backs):
        k = int(arg[k])
        chosen.append(k)
    return sorted(int(pos[j]) for j in chosen), {"K": K, "used_quote_term": bool(use_q)}


def project_pages(text: str, p: Sequence[float] | None, eng_text: str, eng_bounds: Iterable[int],
                  e_page_ends: Sequence[int], t_page_ends: Sequence[int], s2: float, settings: UnionSettings,
                  pprime: Sequence[float] | None = None) -> tuple[list[int] | None, dict]:
    """Page-anchored projection: the page ends (the last non-space character of each non-final page, in
    both languages) are fixed boundaries, and the search runs inside each page on the English SaT
    sentences that fall in it."""
    eng_bounds = list(eng_bounds)
    nsp_e = nonspace_prefix(eng_text)
    pb = set(t_page_ends)
    e_cuts = [-1, *e_page_ends, len(eng_text) - 1]
    t_cuts = [-1, *t_page_ends, len(text) - 1]
    if len(e_cuts) != len(t_cuts):
        raise ValueError("page anchors need the same number of pages in both texts")
    p_list = None if p is None else _floats(p)
    pp_list = None if pprime is None else _floats(pprime)
    infeasible = 0
    for (ea, eb2), (ta, tb) in zip(zip(e_cuts[:-1], e_cuts[1:], strict=True), zip(t_cuts[:-1], t_cuts[1:], strict=True),
                                   strict=True):
        e_in = sorted(b for b in eng_bounds if ea < b < eb2)
        ecc = [ea, *e_in, eb2]
        lens = [nsp_e[y + 1] - nsp_e[x + 1] for x, y in zip(ecc[:-1], ecc[1:], strict=True)]
        if len(lens) > 1:
            # A page slice starts at the whitespace after the previous page end and ends at its own last
            # non-space character, so p' of the slice equals p' of the whole text at every candidate.
            bb, _ = project(text[ta + 1:tb + 1], None if p_list is None else p_list[ta + 1:tb + 1], lens, s2,
                            settings, pprime=None if pp_list is None else pp_list[ta + 1:tb + 1])
            if bb is None:
                infeasible += 1
                continue
            pb |= {ta + 1 + x for x in bb}
    if infeasible:
        return None, {"infeasible_pages": infeasible}
    return sorted(pb), {}


def terminal_additions(text: str, sat_bounds: Iterable[int], terminal: Iterable[str],
                       closing: Iterable[str]) -> set[int]:
    """Registered SaT boundaries whose last character, closing quotation marks skipped, is a terminal mark."""
    terminal, closing = frozenset(terminal), frozenset(closing)
    out = set()
    for b in sat_bounds:
        i = b
        while i > 0 and text[i] in closing:
            i -= 1
        if text[i] in terminal:
            out.add(b)
    return out


def union(text: str, p: Sequence[float] | None, eng_lens: Sequence[int], s2: float, sat_bounds: Iterable[int],
          lang: str, settings: UnionSettings, eng_quotes: Sequence[int] | None = None,
          pprime: Sequence[float] | None = None) -> tuple[list[int] | None, list[int] | None, set[int], dict]:
    """Projection plus the terminal-mark SaT boundaries: (boundaries or None, projected, additions, diagnostics)."""
    w_q = settings.quote_term_weight if settings.quote_term else 0.0
    proj, diag = project(text, p, eng_lens, s2, settings, eng_quotes=eng_quotes, w_q=w_q, pprime=pprime)
    if proj is None:
        return None, None, set(), diag
    adds = terminal_additions(text, sat_bounds, settings.terminal_set(lang), settings.closing_marks) - set(proj)
    return sorted(set(proj) | adds), proj, adds, diag


def at_space_or_terminal(text: str, b: int, terminal: Iterable[str], closing: Iterable[str]) -> bool:
    """The third segmentation check's test: a boundary followed by a whitespace run, or ending in a terminal
    mark once closing quotation marks are skipped (Outcome-neutral quality checks)."""
    if b + 1 < len(text) and text[b + 1].isspace():
        return True
    closing = frozenset(closing)
    i = b
    while i > 0 and text[i] in closing:
        i -= 1
    return text[i] in frozenset(terminal)
