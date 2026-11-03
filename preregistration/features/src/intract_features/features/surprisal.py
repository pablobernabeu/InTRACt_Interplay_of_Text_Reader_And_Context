"""Word surprisal under a causal language model: the registered windows, the beginning-of-word correction, text means.

The registered rules, quoted:

- qmd Materials: "A word's surprisal is the sum of the surprisals of its subword tokens. Because the model's tokens
  mark where a word begins, that sum credits part of one word's ending to the next, and a registered correction moves
  it back. The mean is taken over the words of the outcome's denominator, excluding names and words containing a
  character the model cannot encode." and "Surprisal is computed with the names present in context and excluded only
  from the mean."
- S3: "Each text is scored in windows of 512 tokens, the model's maximum, each beginning with the start token `[CLS]`
  as in training and never ending with `[SEP]`. Windows advance by 256 tokens, and the last one ends at the text's
  final token. Each token's surprisal is taken from the first window that contains it, so every token after the first
  window is scored with at least 255 tokens of preceding context." "Word surprisal therefore takes the correction of
  Pimentel and Meister (2024), with `[SEP]` in the set of boundary tokens." "A fixed table replaces characters that a
  language's tokeniser cannot encode [...] with equivalents in its vocabulary. A word that still holds an unknown
  token leaves the mean." "Per language, we will report the mean and maximum subword-token count per text, the
  tokens-per-word ratio, the replacement counts and the proportion of texts longer than one window."
- qmd Timeline, the budget guard: the inference-only models "run with 16-bit (bf16) weights and 32-bit
  log-probabilities. That step is taken only if their text means agree with those at full precision at r >= .995 on
  the public benchmark scored before submission."

Feature plan v3 ("Surprisal", "Specification") fixes the rest, and every value is read from the stage's
configuration: windows of "[CLS] plus up to 511 tokens at a stride of 256, the last window ending at the final token";
"the log mass of the boundary set (pieces starting with U+2581, plus [SEP])"; "Word surprisal is
Si = sum sj + lambda_f(i) - lambda_f(i+1)"; normalisation that joins pages with one space, collapses whitespace and
trims the ends before the replacement table; and the descriptive next-word entropy, within-text SD and surprisal
per character.

Promoted from the benchmark engines predictability/scripts/gf_scorer.py (windows, boundary log-mass, entropy, word
aggregation) and verify-surprisal/scripts/gf.py (loading, boundary mask), with the checks of
verify-surprisal/scripts/t_pm.py (telescoping identity, S >= 0, brute-force word probability) as unit tests. What
changed: words are the registered words (text/words.py), not str.split() tokens, so a token of punctuation alone adds
its surprisal to the word it attaches to; weights are read only from a safetensors file verified against its pin,
never by unpickling at run time; every forward call has a fixed shape; and TF32 is turned off through PyTorch's
fp32_precision API. Everything outside the model runs in plain Python, so the unit tests need neither torch nor
numpy. All surprisals are in nats.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import statistics
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import batched
from pathlib import Path
from typing import Protocol

from intract_features import records
from intract_features.text import words as text_words

NAN = float("nan")
_SPACE = " "


class AlignmentError(ValueError):
    """The model's tokens could not be placed on the registered words of a text."""


# ------------------------------------------------------------------------------------------------ text preparation


@dataclass(frozen=True)
class PreparedText:
    """A document's text as the language model reads it, with the registered words located in it.

    ``text`` is the document's text with every White_Space run collapsed to one space and the ends trimmed (plan v3).
    ``word_spans`` holds one ``[start, end)`` span over ``text`` for each registered word of the document, in order
    (text.words.words), widened over the punctuation-only tokens attached to it (text.words.word_extents), so the
    spans tile every non-space character and every subword token belongs to exactly one word.
    """

    story_id: str
    text: str
    word_spans: tuple[tuple[int, int], ...]

    @property
    def n_words(self) -> int:
        """The number of registered words."""
        return len(self.word_spans)


def collapse_whitespace(text: str) -> tuple[str, list[tuple[int, int]], list[int]]:
    """The White_Space tokens of ``text`` joined by one space, with each token's source span and new start offset.

    Whitespace is the registered word function's (the Unicode White_Space property), so the collapsed text has the
    same tokens, and so the same words, as the text served.
    """
    tokens = text_words.whitespace_tokens(text)
    starts, pos = [], 0
    for s, e in tokens:
        starts.append(pos)
        pos += e - s + 1
    return _SPACE.join(text[s:e] for s, e in tokens), tokens, starts


def opening_marks(quote_pairs: Iterable[Sequence[str]]) -> frozenset[str]:
    """The opening marks of a language's quotation pairs whose two marks differ.

    A mark that both opens and closes, such as the straight double quote, cannot be read from the character alone, so
    it is not treated as an opener (PENDING the Feature Specification, with the attachment side of punctuation).
    """
    return frozenset(pair[0] for pair in quote_pairs if len(pair) == 2 and pair[0] != pair[1])


def prepare_text(story_id: str, text: str, *, openers: Iterable[str] = (), breaks: Iterable[int] = ()) -> PreparedText:
    """Collapse a document's whitespace and place its registered words, each with its attached punctuation.

    ``breaks`` are offsets in ``text`` where a line begins without a line-break character, such as page starts, which
    word_extents reads for turn-initial dashes. Every extent starts and ends on a token boundary, so it maps exactly.
    """
    collapsed, tokens, new_starts = collapse_whitespace(text)
    extents = text_words.word_extents(text, openers=frozenset(openers), breaks=frozenset(breaks))
    by_start = {s: i for i, (s, _) in enumerate(tokens)}
    by_end = {e: i for i, (_, e) in enumerate(tokens)}
    spans = []
    for a, b in extents:
        i, j = by_start[a], by_end[b]
        spans.append((new_starts[i], new_starts[j] + tokens[j][1] - tokens[j][0]))
    return PreparedText(story_id=story_id, text=collapsed, word_spans=tuple(spans))


# ------------------------------------------------------------------------------------------------ replacement table


def table_from_code_points(pairs: Iterable[Sequence[int]]) -> dict[str, str]:
    """The replacement table from its configured [source, replacement] code-point pairs (one source, one entry)."""
    table: dict[str, str] = {}
    for pair in pairs:
        src, dst = chr(int(pair[0])), chr(int(pair[1]))
        if src in table:
            raise ValueError(f"U+{ord(src):04X} appears twice in the replacement table")
        table[src] = dst
    return check_table(table)


def check_table(table: Mapping[str, str]) -> dict[str, str]:
    """Validate the replacement table: each entry maps one character to one, so no character offset moves."""
    for src, dst in table.items():
        if len(src) != 1 or len(dst) != 1:
            raise ValueError(f"replacement {src!r} -> {dst!r} must map one character to one")
        if src == dst:
            raise ValueError(f"replacement {src!r} maps a character to itself")
    return dict(table)


def active_replacements(table: Mapping[str, str], is_unknown: Callable[[str], bool]) -> dict[str, str]:
    """The entries that apply to one tokeniser.

    Plan v3: "apply the replacement table, but only where the language's tokeniser encodes a character as unknown and
    the replacement is in its vocabulary".
    """
    return {src: dst for src, dst in check_table(table).items() if is_unknown(src) and not is_unknown(dst)}


def apply_replacements(text: str, active: Mapping[str, str]) -> tuple[str, dict[str, int]]:
    """Apply the active entries and count each source character replaced (S3 reports "the replacement counts")."""
    if not active:
        return text, {}
    counts = {src: text.count(src) for src in sorted(active)}
    counts = {k: v for k, v in counts.items() if v}
    if not counts:
        return text, {}
    return text.translate(str.maketrans(dict(active))), counts


# ------------------------------------------------------------------------------------------------ windows


@dataclass(frozen=True)
class Window:
    """Text tokens ``[start, end)`` scored together after the start token; tokens from ``keep_from`` take its values."""

    start: int
    end: int
    keep_from: int


def plan_windows(n_tokens: int, positions: int, stride: int) -> list[Window]:
    """The registered windows of a text of ``n_tokens`` subword tokens.

    A window has ``positions`` positions, the first holding the start token, so it scores up to ``positions - 1``
    text tokens. Windows start at 0, ``stride``, ``2 * stride`` and so on, and the last one is moved back so that it
    ends at the text's final token (S3: "the last one ends at the text's final token"; plan v3: "the last window
    ending at the final token"), which the benchmark engine gf_scorer.py did with ``min(a + stride, T - W)``. Each
    token keeps the values of the first window that contains it, so a token after the first window has at least
    ``positions - 1 - stride`` tokens of context (255 for the registered 512 and 256).
    """
    span = positions - 1
    if span < 1:
        raise ValueError("a window needs at least two positions")
    if not 1 <= stride <= span:
        raise ValueError(f"the stride must lie in [1, {span}], not {stride}")
    if n_tokens <= 0:
        return []
    starts = [0]
    while starts[-1] + span < n_tokens:
        starts.append(min(starts[-1] + stride, n_tokens - span))
    plan, done = [], 0
    for a in starts:
        b = min(a + span, n_tokens)
        plan.append(Window(start=a, end=b, keep_from=done))
        done = b
    return plan


def window_inputs(ids: Sequence[int], plan: Sequence[Window], start_id: int) -> list[list[int]]:
    """The model input of each window: the start token, then the window's text tokens, and never an end token."""
    return [[start_id, *ids[w.start:w.end]] for w in plan]


# ------------------------------------------------------------------------------------------------ token scores


@dataclass(frozen=True)
class WindowScores:
    """One window's outputs, by position of its input.

    ``target_logp[k]`` is the log-probability of input token ``k + 1`` given inputs ``0..k`` (one fewer value than
    the input has positions). ``boundary_logmass[k]`` is the log of the probability that the token after inputs
    ``0..k`` lies in the boundary set, and ``entropy[k]`` the entropy of that next-token distribution, at every
    position including the last.
    """

    target_logp: Sequence[float]
    boundary_logmass: Sequence[float]
    entropy: Sequence[float]


@dataclass(frozen=True)
class TokenScores:
    """Per text token: surprisal, the boundary log-mass and entropy of the distribution that predicts it, context.

    ``context`` counts the text tokens before a token in the window that scored it. ``boundary_end`` is the boundary
    log-mass after the text's final token, which closes the last word, and ``first_window_end`` the first token that
    a later window scored.
    """

    surprisal: list[float]
    boundary_before: list[float]
    entropy_before: list[float]
    context: list[int]
    boundary_end: float
    n_windows: int
    first_window_end: int

    def min_context_after_first_window(self) -> int | None:
        """The least context of any token after the first window (S3: "at least 255 tokens"), None for one window."""
        rest = self.context[self.first_window_end:]
        return min(rest) if rest else None


def token_scores(n_tokens: int, plan: Sequence[Window], scores: Sequence[WindowScores]) -> TokenScores:
    """Take each token's values from the first window that contains it (S3), and the end mass from the last window."""
    if len(plan) != len(scores):
        raise ValueError(f"{len(scores)} window results for {len(plan)} windows")
    s, lam, ent, ctx = [NAN] * n_tokens, [NAN] * n_tokens, [NAN] * n_tokens, [-1] * n_tokens
    lam_end = NAN
    for w, sc in zip(plan, scores, strict=True):
        if len(sc.target_logp) != w.end - w.start or len(sc.boundary_logmass) != w.end - w.start + 1:
            raise ValueError("a window's results do not match its length")
        for i in range(w.keep_from, w.end):
            k = i - w.start  # output position k predicts input position k + 1, which is text token i
            s[i] = -float(sc.target_logp[k])
            lam[i] = float(sc.boundary_logmass[k])
            ent[i] = float(sc.entropy[k])
            ctx[i] = k
        if w.end == n_tokens:
            lam_end = float(sc.boundary_logmass[w.end - w.start])
    return TokenScores(surprisal=s, boundary_before=lam, entropy_before=ent, context=ctx, boundary_end=lam_end,
                       n_windows=len(plan), first_window_end=plan[0].end if plan else 0)


# ------------------------------------------------------------------------------------------------ words


def assign_tokens(text: str, offsets: Sequence[tuple[int, int]], word_spans: Sequence[tuple[int, int]]) -> list[int]:
    """The word of each subword token, from the token's character offsets in ``text``.

    A token belongs to the word that holds its first non-space character. A token with none, a bare word-start marker
    whose offsets cover only a space or nothing, belongs to the word of the next non-space character, as in the
    benchmark (t_pm.py, words_and_tokens). The tokens of a word must be contiguous, as the correction assumes.
    """
    starts = [a for a, _ in word_spans]
    n = len(text)
    out: list[int] = []
    for a, b in offsets:
        q = a
        while q < b and text[q] == _SPACE:
            q += 1
        if q >= b:
            q = max(a, b)
            while q < n and text[q] == _SPACE:
                q += 1
        if q >= n:
            if not word_spans:
                raise AlignmentError("a token lies in a text without words")
            w = len(word_spans) - 1  # a trailing marker closes the last word
        else:
            w = bisect_right(starts, q) - 1
            if w < 0 or not word_spans[w][0] <= q < word_spans[w][1]:
                raise AlignmentError(f"the token at offsets {(a, b)} lies in no word")
        out.append(w)
    if any(x > y for x, y in zip(out, out[1:], strict=False)):
        raise AlignmentError("the tokens of a word are not contiguous")
    return out


@dataclass(frozen=True)
class WordScores:
    """Per registered word: corrected and uncorrected surprisal (None for a word that received no token)."""

    corrected: list[float | None]
    uncorrected: list[float | None]
    first_token: list[int]
    identity_residual: float


def word_surprisal(scores: TokenScores, token_word: Sequence[int], n_words: int) -> WordScores:
    """Sum each word's token surprisals and apply the beginning-of-word correction.

    Pimentel and Meister (2024), for a tokeniser whose pieces mark the beginning of a word, with the end of sequence
    in the boundary set B: ``S(w) = sum of s_j over w's tokens + lambda(first token of w) - lambda(first token of the
    next word)``, where ``lambda(i) = log P(next piece in B | context before token i)`` and the text's end mass
    closes the last word (plan v3: "Si = sum sj + lambda_f(i) - lambda_f(i+1)"). The terms telescope, so the corrected
    and uncorrected text totals differ by ``lambda(first token) - lambda(end)``; ``identity_residual`` is the
    floating-point departure from that identity (t_pm.py, test (i)). A word that the tokeniser gave no token, because
    its normaliser deleted all its characters, has no value, and the chain skips it.
    """
    unc = [0.0] * n_words
    first = [-1] * n_words
    for i, w in enumerate(token_word):
        unc[w] += scores.surprisal[i]
        if first[w] < 0:
            first[w] = i
    tokenised = [w for w in range(n_words) if first[w] >= 0]
    corrected: list[float | None] = [None] * n_words
    for k, w in enumerate(tokenised):
        before = scores.boundary_before[first[w]]
        after = scores.boundary_before[first[tokenised[k + 1]]] if k + 1 < len(tokenised) else scores.boundary_end
        corrected[w] = unc[w] + before - after
    uncorrected: list[float | None] = [unc[w] if first[w] >= 0 else None for w in range(n_words)]
    if tokenised:
        total_c = math.fsum(corrected[w] for w in tokenised)
        total_s = math.fsum(scores.surprisal)
        residual = total_c - total_s - (scores.boundary_before[first[tokenised[0]]] - scores.boundary_end)
    else:
        residual = 0.0
    return WordScores(corrected=corrected, uncorrected=uncorrected, first_token=first, identity_residual=residual)


def text_mean(values: Sequence[float | None], exclude: Iterable[bool] | None = None) -> float | None:
    """Mean of the word values not excluded and not None, or None when no word is left.

    Use it to apply the frozen name mask to stored per-word values: ``exclude`` holds one flag per word, True for a
    name (qmd Materials: names are "excluded only from the mean") and True for every word that
    ``diagnostics.words_unknown`` lists, because the stored values keep those words although the registered mean
    leaves out "words containing a character the model cannot encode" (qmd Materials).
    """
    flags = [False] * len(values) if exclude is None else list(exclude)
    if len(flags) != len(values):
        raise ValueError(f"{len(flags)} flags for {len(values)} words")
    kept = [v for v, x in zip(values, flags, strict=True) if v is not None and not x]
    return math.fsum(kept) / len(kept) if kept else None


# ------------------------------------------------------------------------------------------------ tokeniser


class Tokeniser(Protocol):
    """What the scorer needs from a tokeniser: ids with character offsets, and vocabulary lookups."""

    def encode(self, text: str) -> tuple[list[int], list[tuple[int, int]]]:
        """Token ids and ``[start, end)`` character offsets in ``text``, without special tokens."""

    def token_to_id(self, token: str) -> int | None:
        """The id of a piece, or None."""

    def id_to_token(self, i: int) -> str | None:
        """The piece of an id, or None beyond the vocabulary."""


class HFTokeniser:
    """A tokeniser read from a tokenizer.json with the ``tokenizers`` library (plan v3: "tokenizers.Tokenizer.from_file
    (tokenizer.json) with add_special_tokens=False, because AutoTokenizer fails on these tokenisers under
    transformers 5")."""

    def __init__(self, path: str | os.PathLike):
        from tokenizers import Tokenizer

        self._tok = Tokenizer.from_file(str(path))

    def encode(self, text: str) -> tuple[list[int], list[tuple[int, int]]]:
        """Token ids and character offsets, special tokens left out."""
        enc = self._tok.encode(text, add_special_tokens=False)
        return list(enc.ids), [(int(a), int(b)) for a, b in enc.offsets]

    def token_to_id(self, token: str) -> int | None:
        """The id of a piece, or None."""
        return self._tok.token_to_id(token)

    def id_to_token(self, i: int) -> str | None:
        """The piece of an id, or None."""
        return self._tok.id_to_token(i)


def boundary_mask(tokeniser: Tokeniser, size: int, marker: str, end_of_sequence: int) -> list[bool]:
    """The boundary set B over the model's ``size`` outputs: pieces that begin with the word-start marker, plus the end
    of sequence (S3: "with `[SEP]` in the set of boundary tokens"). Outputs beyond the tokeniser's vocabulary, such as
    Goldfish's unused placeholders, are not in B."""
    mask = [False] * size
    for i in range(size):
        piece = tokeniser.id_to_token(i)
        if piece is not None and piece.startswith(marker):
            mask[i] = True
    if not 0 <= end_of_sequence < size:
        raise ValueError(f"end-of-sequence id {end_of_sequence} lies outside the {size} outputs")
    mask[end_of_sequence] = True
    return mask


# ------------------------------------------------------------------------------------------------ scoring


class LMBackend(Protocol):
    """A language model that scores window inputs; ``positions`` is its maximum input length."""

    positions: int

    def score(self, windows: Sequence[Sequence[int]]) -> list[WindowScores]:
        """One WindowScores per input, in order."""


@dataclass(frozen=True)
class TextScore:
    """Everything one model gives one text: word values and the counts S3 reports."""

    n_tokens: int
    n_windows: int
    tokens: TokenScores | None
    words: WordScores | None
    word_unknown: list[bool]
    unknown_tokens: int
    replacements: dict[str, int]
    error: str | None = None


@dataclass
class Scorer:
    """Scores prepared texts with one tokeniser and one model under the registered windows."""

    tokeniser: Tokeniser
    backend: LMBackend
    start_id: int
    unknown_id: int
    positions: int
    stride: int
    table: Mapping[str, str]
    active: dict[str, str] = field(init=False)

    def __post_init__(self):
        if self.positions > self.backend.positions:
            raise ValueError(f"windows of {self.positions} positions exceed the model's {self.backend.positions}")
        self.active = active_replacements(self.table, self.is_unknown)

    def is_unknown(self, ch: str) -> bool:
        """Whether the tokeniser encodes a character as unknown, tested between two letters as repl_check.py did."""
        ids, _ = self.tokeniser.encode(f"a{ch}a")
        return self.unknown_id in ids

    def score(self, texts: Sequence[PreparedText], strict: bool = True) -> list[TextScore]:
        """Score a group of texts; their windows go to the model together, which fixed shapes make harmless.

        A text without a registered word (punctuation alone) is not scored: its mean is undefined by construction.
        """
        encoded, plans, inputs, owners = [], [], [], []
        for k, p in enumerate(texts):
            model_text, repl = apply_replacements(p.text, self.active)
            ids, offsets = self.tokeniser.encode(model_text) if p.n_words else ([], [])
            plan = plan_windows(len(ids), self.positions, self.stride)
            encoded.append((model_text, ids, offsets, repl))
            plans.append(plan)
            for x in window_inputs(ids, plan, self.start_id):
                inputs.append(x)
                owners.append(k)
        results = self.backend.score(inputs) if inputs else []
        by_text: list[list[WindowScores]] = [[] for _ in texts]
        for k, r in zip(owners, results, strict=True):
            by_text[k].append(r)
        out = []
        for p, (model_text, ids, offsets, repl), plan, res in zip(texts, encoded, plans, by_text, strict=True):
            unknown = [i == self.unknown_id for i in ids]
            if not p.n_words:
                out.append(TextScore(n_tokens=0, n_windows=0, tokens=None, words=None, word_unknown=[],
                                     unknown_tokens=0, replacements=repl, error="no registered words"))
                continue
            try:
                tok_word = assign_tokens(model_text, offsets, p.word_spans)
            except AlignmentError as e:
                if strict:
                    raise AlignmentError(f"{p.story_id}: {e}") from e
                out.append(TextScore(n_tokens=len(ids), n_windows=len(plan), tokens=None, words=None,
                                     word_unknown=[False] * p.n_words, unknown_tokens=sum(unknown),
                                     replacements=repl, error=str(e)))
                continue
            ts = token_scores(len(ids), plan, res)
            ws = word_surprisal(ts, tok_word, p.n_words)
            word_unknown = [False] * p.n_words
            for i, w in enumerate(tok_word):
                if unknown[i]:
                    word_unknown[w] = True
            out.append(TextScore(n_tokens=len(ids), n_windows=len(plan), tokens=ts, words=ws,
                                 word_unknown=word_unknown, unknown_tokens=sum(unknown), replacements=repl))
        return out


# ------------------------------------------------------------------------------------------------ text summaries


def _round(x: float | None, decimals: int | None) -> float | None:
    if x is None or not math.isfinite(x):
        return None
    return round(x, decimals) if decimals is not None else x


def summarise(result: TextScore, text: PreparedText, names: Sequence[bool] | None, *, sd_ddof: int = 0,
              store_words: bool = True, decimals: int | None = 6) -> tuple[dict, dict]:
    """The text values and diagnostics of one model's scores.

    Values: ``mean`` is the registered text mean, over registered words that are not names, hold no unknown token and
    were tokenised (qmd Materials), None when no name mask is given; ``mean_all_words`` keeps the names (plan v3:
    "The all-word mean and its correlation with the primary are reported"). Diagnostics hold the counts S3 reports,
    the descriptive measures of plan v3 and, if ``store_words``, the per-word corrected surprisals, so that the
    registered mean can be recomputed under the frozen name mask with text_mean, excluding the names and the words
    listed in ``words_unknown``.
    """
    n = text.n_words
    if names is not None and len(names) != n:
        raise ValueError(f"{text.story_id}: {len(names)} name flags for {n} words")
    diag: dict = {"tokens": result.n_tokens, "windows": result.n_windows, "unknown_tokens": result.unknown_tokens,
                  "replacements": result.replacements, "characters": len(text.text)}
    if result.error is not None or result.words is None or result.tokens is None:
        diag["error"] = result.error or "not scored"
        return {"mean": None, "mean_all_words": None}, diag
    ws, ts = result.words, result.tokens
    untokenised = [i for i in range(n) if ws.corrected[i] is None]
    unknown = [i for i in range(n) if result.word_unknown[i]]
    usable = [ws.corrected[i] is not None and not result.word_unknown[i] for i in range(n)]
    counted = [u and not (names is not None and names[i]) for i, u in enumerate(usable)]
    mean_all = text_mean(ws.corrected, [not u for u in usable])
    mean = text_mean(ws.corrected, [not c for c in counted]) if names is not None else None
    chosen = counted if names is not None else usable
    vals = [ws.corrected[i] for i in range(n) if chosen[i]]
    unc = [ws.uncorrected[i] for i in range(n) if chosen[i]]
    ent = [ts.entropy_before[ws.first_token[i]] for i in range(n) if chosen[i]]
    diag.update({
        "words": n,
        "words_unknown": unknown,
        "words_untokenised": untokenised,
        "names_applied": names is not None,
        "names_excluded": sum(1 for i in range(n) if usable[i] and names is not None and names[i]),
        "counted_words": sum(chosen),
        "identity_residual": ws.identity_residual,
        "min_word_surprisal": min((v for v in ws.corrected if v is not None), default=None),
        "min_context_after_first_window": ts.min_context_after_first_window(),
        "descriptive": {
            "word_set": "names_excluded" if names is not None else "all_words",
            "mean_uncorrected": math.fsum(unc) / len(unc) if unc else None,
            "sd": (statistics.pstdev(vals) if sd_ddof == 0 else statistics.stdev(vals)) if len(vals) > sd_ddof
            else None,
            "mean_next_token_entropy": math.fsum(ent) / len(ent) if ent else None,
            "surprisal_per_character": math.fsum(ts.surprisal) / len(text.text) if text.text else None,
        },
    })
    if store_words:
        diag["word_surprisal"] = [_round(v, decimals) for v in ws.corrected]
    return {"mean": mean, "mean_all_words": mean_all}, diag


# ------------------------------------------------------------------------------------------------ agreement


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson's r of two equal-length sequences, or None when either has no variance or fewer than three values."""
    if len(xs) != len(ys):
        raise ValueError("sequences of different lengths")
    if len(xs) < 3:
        return None
    mx, my = math.fsum(xs) / len(xs), math.fsum(ys) / len(ys)
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    syy = math.fsum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def precision_agreement(pairs: Sequence[tuple[float, float]], threshold: float) -> dict:
    """Agreement of reduced-precision text means with full-precision ones (pairs of (fp32, bf16) values).

    qmd Timeline: the bf16 step "is taken only if their text means agree with those at full precision at r >= .995
    on the public benchmark scored before submission". ``passes`` is that test on these pairs.
    """
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    r = pearson([a for a, _ in pairs], [b for _, b in pairs])
    return {"texts": len(pairs), "r": r, "threshold": threshold,
            "max_abs_difference": max((abs(a - b) for a, b in pairs), default=None),
            "passes": r is not None and r >= threshold}


def keyed_fraction(story_id: str, purpose: str, keys: Mapping) -> float:
    """A story's position in [0, 1) under the keyed hash of a purpose (records.keyed_hash, gap G7's key string)."""
    h = records.keyed_hash(purpose, story_id, prefix=str(keys.get("prefix", "intract")),
                           version=str(keys.get("version", "v1")))
    return int(h[:16], 16) / float(1 << 64)


# ------------------------------------------------------------------------------------------------ torch runtime


def configure_torch(runtime: Mapping) -> dict:
    """Fix PyTorch's numerics before the model loads, and return the settings read back for the run record.

    DESIGN.md, Determinism: "Language models and encoders run in fp32 with TF32 off". Plan v3: "IEEE fp32 with TF32
    disabled through PyTorch's fp32_precision API". In torch 2.14 setting ``torch.backends.fp32_precision`` to "ieee"
    carries to cuBLAS, cuDNN and its convolution and RNN settings, whose defaults allow TF32; the legacy
    ``allow_tf32`` flags are used only on a torch without that API, because reading them after the new API has been
    used raises. cuBLAS reads its workspace setting when CUDA starts, so it is set first.
    """
    if runtime.get("deterministic_algorithms", True):
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", str(runtime.get("cublas_workspace_config", ":4096:8")))
    if runtime.get("offline", True):
        # Nothing is fetched at run time: every file comes from the verified folder.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    import torch

    precision = str(runtime.get("fp32_precision", "ieee"))
    state: dict = {"torch": torch.__version__}
    if hasattr(torch.backends, "fp32_precision"):
        torch.backends.fp32_precision = precision
        torch.backends.cuda.matmul.fp32_precision = precision
        torch.backends.cudnn.fp32_precision = precision
        torch.backends.cudnn.conv.fp32_precision = precision
        torch.backends.cudnn.rnn.fp32_precision = precision
        state["fp32_precision"] = {"generic": torch.backends.fp32_precision,
                                   "cuda_matmul": torch.backends.cuda.matmul.fp32_precision,
                                   "cudnn_conv": torch.backends.cudnn.conv.fp32_precision,
                                   "cudnn_rnn": torch.backends.cudnn.rnn.fp32_precision}
    else:
        tf32 = precision == "tf32"
        torch.backends.cuda.matmul.allow_tf32 = tf32
        torch.backends.cudnn.allow_tf32 = tf32
        torch.set_float32_matmul_precision("high" if tf32 else "highest")
        state["allow_tf32"] = tf32
    if runtime.get("deterministic_algorithms", True):
        torch.use_deterministic_algorithms(True, warn_only=True)
    state["deterministic_algorithms"] = torch.are_deterministic_algorithms_enabled()
    seed = runtime.get("seed")
    if seed is not None:
        torch.manual_seed(int(seed))  # inference draws nothing at random; set for the record
    return state


def resolve_device(name: str) -> str:
    """"auto" picks CUDA when visible; a CUDA device that is not visible stops the stage instead of falling back."""
    import torch

    if name == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if name.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("the stage is configured for CUDA, but no GPU is visible")
    return name


def check_loading(info: Mapping, allowed_missing: Sequence[str], allowed_unexpected: Sequence[str]) -> None:
    """Refuse a checkpoint that left weights unloaded or carried weights the model does not have.

    ``info`` is transformers' loading information. Old GPT-2 checkpoints carry the causal-mask buffers ``attn.bias``
    and ``attn.masked_bias``, which current models rebuild, and omit the output layer tied to the embeddings; the
    patterns allowed for each model are in the stage configuration.
    """
    problems = []
    for key in info.get("missing_keys", ()) or ():
        if not any(re.search(p, key) for p in allowed_missing):
            problems.append(f"missing {key}")
    for key in info.get("unexpected_keys", ()) or ():
        if not any(re.search(p, key) for p in allowed_unexpected):
            problems.append(f"unexpected {key}")
    for item in info.get("mismatched_keys", ()) or ():
        problems.append(f"mismatched {item}")
    for msg in info.get("error_msgs", ()) or ():
        problems.append(f"error {msg}")
    if problems:
        raise RuntimeError("the checkpoint does not match the model: " + "; ".join(problems[:10]))


def load_causal_lm(folder: Path, *, dtype: str, device: str, attn_implementation: str,
                   allowed_missing: Sequence[str] = (), allowed_unexpected: Sequence[str] = ()):
    """Load a causal language model from a verified folder, reading only its safetensors weights.

    ``use_safetensors=True`` means transformers never falls back to a pickled ``pytorch_model.bin``: Goldfish ships
    only a pickle, so the environment build converts it once (convert_pickled_checkpoint) and pins the result.
    """
    import torch
    from transformers import AutoModelForCausalLM

    model, info = AutoModelForCausalLM.from_pretrained(
        str(folder), dtype=getattr(torch, dtype), attn_implementation=attn_implementation, use_safetensors=True,
        local_files_only=True, output_loading_info=True)
    check_loading(info, allowed_missing, allowed_unexpected)
    model.to(device)
    model.eval()  # dropout off
    return model


def convert_pickled_checkpoint(src: str | os.PathLike, dst: str | os.PathLike, *, drop: Sequence[str] = (),
                               tied: Mapping[str, str] | None = None) -> dict:
    """Environment-build helper: convert a pickled PyTorch state dict (``pytorch_model.bin``) to safetensors.

    It runs once, in the build job that records the result's SHA-256 in config/models.lock.json, never in a stage:
    stages load only the converted file, after verifying that hash. ``torch.load`` runs with ``weights_only=True``,
    which refuses any pickled object other than tensors and plain containers. Keys matching a pattern in ``drop`` are
    left out (obsolete buffers such as GPT-2's ``attn.bias``), and so is each key of ``tied`` whose tensor equals the
    one it is tied to (GPT-2's output layer, ``lm_head.weight``, tied to ``transformer.wte.weight``), since
    safetensors stores no shared tensors and the model re-ties them on loading.
    """
    import torch
    from safetensors.torch import save_file

    src, dst = Path(src), Path(dst)
    state = torch.load(src, map_location="cpu", weights_only=True)
    tied = dict(tied or {})
    out, dropped = {}, []
    for key, value in state.items():
        if any(re.search(p, key) for p in drop):
            dropped.append(key)
            continue
        target = tied.get(key)
        if target is not None and target in state and torch.equal(value, state[target]):
            dropped.append(key)
            continue
        out[key] = value.detach().clone().contiguous()
    source_sha = records.sha256_file(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    save_file(out, str(tmp), metadata={"format": "pt", "source_sha256": source_sha})
    tmp.replace(dst)
    return {"source": src.name, "source_sha256": source_sha, "file": dst.name, "sha256": records.sha256_file(dst),
            "tensors": len(out), "dropped": sorted(dropped)}


@dataclass(frozen=True)
class ModelSettings:
    """How one language model is loaded and run, from a stage's [tokens], [windows], [replacements], [precision],
    [runtime] and [loading] tables (config/stages/surprisal_*.toml)."""

    start: str
    end_of_sequence: str
    unknown: str
    padding: str
    marker: str
    positions: int
    stride: int
    table: dict[str, str]
    mode: str
    logprob_dtype: str
    device: str
    attn_implementation: str
    windows_per_batch: int
    pad_to_window: bool
    positions_per_chunk: int
    allowed_missing: tuple[str, ...]
    allowed_unexpected: tuple[str, ...]
    allowed_modes: tuple[str, ...]

    @classmethod
    def from_config(cls, cfg: Mapping) -> ModelSettings:
        """Read the settings and refuse values the registered rules exclude."""
        tok, win, prec, rt, ld = cfg["tokens"], cfg["windows"], cfg["precision"], cfg["runtime"], cfg["loading"]
        s = cls(start=tok["start"], end_of_sequence=tok["end_of_sequence"], unknown=tok["unknown"],
                padding=tok["padding"], marker=tok["word_start_marker"], positions=int(win["positions"]),
                stride=int(win["stride"]), table=table_from_code_points(cfg["replacements"]["code_points"]),
                mode=str(prec["mode"]),
                logprob_dtype=str(prec["logprob_dtype"]), device=str(rt["device"]),
                attn_implementation=str(rt["attn_implementation"]), windows_per_batch=int(rt["windows_per_batch"]),
                pad_to_window=bool(rt["pad_to_window"]), positions_per_chunk=int(rt["positions_per_chunk"]),
                allowed_missing=tuple(ld["allowed_missing"]), allowed_unexpected=tuple(ld["allowed_unexpected"]),
                allowed_modes=tuple(prec["allowed_modes"]))
        if s.mode not in s.allowed_modes:
            raise ValueError(f"precision mode {s.mode!r} is not allowed for this stage ({s.allowed_modes})")
        if s.logprob_dtype not in ("float32", "float64"):
            raise ValueError("log-probabilities are computed in 32 bits or more (qmd Timeline)")
        plan_windows(1, s.positions, s.stride)  # validates the geometry
        return s


MODE_DTYPES = {"fp32": "float32", "bf16": "bfloat16"}


def pin_label(models_lock: Mapping, key: str) -> str:
    """``repo@revision`` of a pinned model, for the records."""
    entry = models_lock.get(key) or (models_lock.get("models") or {}).get(key) or {}
    return f"{entry.get('repo') or key}@{entry.get('revision') or entry.get('commit') or 'unpinned'}"


def load_scorers(key: str, settings: ModelSettings, models_lock: Mapping, modes: Sequence[str]) -> dict[str, Scorer]:
    """Verify a pinned model folder and build one Scorer per precision mode, sharing the tokeniser.

    DESIGN.md: "Code verifies a pin before it loads the file." The pin is checked by segment.sat's
    resolve_pinned_snapshot, so every stage reads one lock format. Each mode loads the weights from the verified
    file in its own dtype, so a bf16 model never needs a second full-precision copy in GPU memory (XGLM-4.5B takes
    about 18 GB in fp32 and 9 GB in bf16 on a 48 GB L40S).
    """
    from intract_features.segment.sat import resolve_pinned_snapshot

    folder = resolve_pinned_snapshot(models_lock, key)
    tokeniser = HFTokeniser(folder / "tokenizer.json")
    ids = {name: tokeniser.token_to_id(piece) for name, piece in (("start", settings.start),
                                                                  ("end_of_sequence", settings.end_of_sequence),
                                                                  ("unknown", settings.unknown),
                                                                  ("padding", settings.padding))}
    missing = [name for name, i in ids.items() if i is None]
    if missing:
        raise ValueError(f"{key}: the tokeniser has no piece for {missing}")
    device = resolve_device(settings.device)
    out: dict[str, Scorer] = {}
    mask: list[bool] | None = None
    for mode in modes:
        if mode not in settings.allowed_modes or mode not in MODE_DTYPES:
            raise ValueError(f"precision mode {mode!r} is not allowed for this stage")
        m = load_causal_lm(folder, dtype=MODE_DTYPES[mode], device=device,
                           attn_implementation=settings.attn_implementation,
                           allowed_missing=settings.allowed_missing, allowed_unexpected=settings.allowed_unexpected)
        if mask is None:
            size = m.get_output_embeddings().weight.shape[0]
            mask = boundary_mask(tokeniser, size, settings.marker, ids["end_of_sequence"])
        limit = int(getattr(m.config, "n_positions", None) or m.config.max_position_embeddings)
        backend = TorchCausalLM(m, mask, positions=limit, windows_per_batch=settings.windows_per_batch,
                                pad_to_window=settings.pad_to_window, pad_id=ids["padding"],
                                logprob_dtype=settings.logprob_dtype, positions_per_chunk=settings.positions_per_chunk,
                                device=device)
        out[mode] = Scorer(tokeniser=tokeniser, backend=backend, start_id=ids["start"], unknown_id=ids["unknown"],
                           positions=settings.positions, stride=settings.stride, table=settings.table)
    return out


@dataclass(frozen=True)
class OutputSettings:
    """What a surprisal record stores ([stage], [descriptive] and [output] tables)."""

    strict: bool
    docs_per_group: int
    store_words: bool
    decimals: int | None
    sd_ddof: int

    @classmethod
    def from_config(cls, cfg: Mapping) -> OutputSettings:
        """Read the output settings."""
        out = cls(strict=bool(cfg["stage"]["strict"]), docs_per_group=int(cfg["stage"]["docs_per_group"]),
                  store_words=bool(cfg["output"]["store_word_values"]),
                  decimals=int(cfg["output"]["decimals"]) if cfg["output"].get("decimals") is not None else None,
                  sd_ddof=int(cfg["descriptive"]["sd_ddof"]))
        if out.sd_ddof not in (0, 1):
            raise ValueError("descriptive.sd_ddof must be 0 (population SD) or 1 (sample SD)")
        if out.docs_per_group < 1:
            raise ValueError("stage.docs_per_group must be at least 1")
        return out


def score_documents(documents: Iterable[records.Document], models: Mapping[str, Scorer], *,
                    value_names: Mapping[str, str], labels: Mapping[str, str], openers: Iterable[str],
                    out: OutputSettings, names_for: Callable[[str], Sequence[bool] | None], tally: dict,
                    timers: dict, checks: Mapping[str, Scorer] | None = None,
                    check_selected: Callable[[str], bool] | None = None,
                    check_pairs: dict[str, list] | None = None) -> Iterable[dict]:
    """Yield one record per document, scoring groups of documents with every model in ``models``.

    ``models`` maps a model name (a Goldfish tier, or "xglm") to its Scorer and ``value_names`` that name to the
    registered value it gives. ``checks`` holds an fp32 Scorer per model for the bf16 check: documents for which
    ``check_selected`` is true are scored again at full precision, and the pairs of text means are collected in
    ``check_pairs`` for precision_agreement. ``tally`` and ``timers`` collect the counts and seconds of the timing
    record.
    """
    import time

    openers = frozenset(openers)
    for group in batched(documents, out.docs_per_group):
        prepared = [prepare_text(d.story_id, d.text, openers=openers, breaks=[a for a, _ in d.page_spans()])
                    for d in group]
        results: dict[str, list[TextScore]] = {}
        for name, scorer in models.items():
            t0 = time.perf_counter()
            results[name] = scorer.score(prepared, strict=out.strict)
            timers[name] = timers.get(name, 0.0) + time.perf_counter() - t0
        checked: dict[str, dict[str, TextScore]] = {}
        if checks and check_selected is not None:
            chosen = [k for k, d in enumerate(group) if check_selected(d.story_id)]
            for name, scorer in checks.items():
                t0 = time.perf_counter()
                got = scorer.score([prepared[k] for k in chosen], strict=out.strict) if chosen else []
                timers[f"{name}_fp32_check"] = timers.get(f"{name}_fp32_check", 0.0) + time.perf_counter() - t0
                checked[name] = {group[k].story_id: r for k, r in zip(chosen, got, strict=True)}
        for k, doc in enumerate(group):
            p = prepared[k]
            names = names_for(doc.story_id)
            names_mismatch = False
            if names is not None:
                names = list(names)
                if len(names) != p.n_words:
                    if out.strict:
                        raise ValueError(f"{doc.story_id}: {len(names)} name flags for {p.n_words} words")
                    names, names_mismatch = None, True
                    tally["names_mismatch"] = tally.get("names_mismatch", 0) + 1
            values, models_diag = {}, {}
            for name in models:
                res = results[name][k]
                v, diag = summarise(res, p, names, sd_ddof=out.sd_ddof, store_words=out.store_words,
                                    decimals=out.decimals)
                diag["model"] = labels[name]
                values[value_names[name]] = v["mean"]
                values[f"{value_names[name]}_all_words"] = v["mean_all_words"]
                if name in checked and doc.story_id in checked[name]:
                    cv, _ = summarise(checked[name][doc.story_id], p, names, store_words=False)
                    diag["fp32_check"] = cv
                    if check_pairs is not None:
                        key = "mean" if names is not None else "mean_all_words"
                        check_pairs.setdefault(name, []).append((cv[key], v[key]))
                models_diag[name] = diag
                _tally(tally, name, res, diag)
            tally["documents"] = tally.get("documents", 0) + 1
            tally["words"] = tally.get("words", 0) + p.n_words
            tally["characters"] = tally.get("characters", 0) + len(doc.text)
            yield {"story_id": doc.story_id, "lang": doc.lang,
                   "values": {k: records.finite_or_none(v) for k, v in values.items()},
                   "diagnostics": _strict_json({"text_sha256": hashlib.sha256(doc.text.encode("utf-8")).hexdigest(),
                                                "words": p.n_words, "names_applied": names is not None,
                                                "names_mismatch": names_mismatch, "models": models_diag})}


def _tally(tally: dict, name: str, res: TextScore, diag: Mapping) -> None:
    def add(key: str, v: int) -> None:
        tally[key] = tally.get(key, 0) + v

    add(f"tokens_{name}", res.n_tokens)
    add(f"windows_{name}", res.n_windows)
    add(f"unknown_tokens_{name}", res.unknown_tokens)
    add(f"words_with_unknown_{name}", len(diag.get("words_unknown", ())))
    add(f"replacements_{name}", sum(res.replacements.values()))
    add(f"texts_beyond_one_window_{name}", int(res.n_windows > 1))
    add(f"errors_{name}", int(res.error is not None))
    tally[f"max_tokens_{name}"] = max(tally.get(f"max_tokens_{name}", 0), res.n_tokens)


def _strict_json(obj):
    """Map every non-finite float to None, recursively (DESIGN.md: every file is strict JSON)."""
    if isinstance(obj, float):
        return records.finite_or_none(obj)
    if isinstance(obj, Mapping):
        return {k: _strict_json(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_strict_json(v) for v in obj]
    return obj


class TorchCausalLM:
    """A causal language model's window scores under fixed batch shapes.

    DESIGN.md, Determinism: "Batches have fixed shapes wherever padding could change a result." With
    ``pad_to_window``, every forward call holds ``windows_per_batch`` windows, each right-padded to ``positions``;
    a short last batch is filled with copies of its first window, whose outputs are discarded. Under the causal mask
    no real position sees the padding, and with the shape fixed no row's result depends on the other rows, so a
    text's values do not depend on which texts share its call, and the smoke run's rows equal the full run's.
    Without padding a window goes alone, at its own length. The output layer runs per window in chunks of
    ``positions_per_chunk``, which bounds the memory of the log-softmax over the vocabulary; logits are cast to
    ``logprob_dtype`` first, so bf16 weights give 32-bit log-probabilities (qmd Timeline).
    """

    def __init__(self, model, mask: Sequence[bool], *, positions: int, windows_per_batch: int, pad_to_window: bool,
                 pad_id: int, logprob_dtype: str, positions_per_chunk: int, device: str):
        import torch

        if not pad_to_window and windows_per_batch != 1:
            raise ValueError("windows of different lengths can share a call only when they are padded")
        self.torch = torch
        self.model = model
        self.base = model.base_model
        self.head = model.get_output_embeddings()
        size = self.head.weight.shape[0]
        if len(mask) != size:
            raise ValueError(f"a boundary mask of {len(mask)} entries for {size} outputs")
        self.mask = torch.tensor(list(mask), dtype=torch.bool, device=device)
        self.positions = positions
        self.windows_per_batch = windows_per_batch
        self.pad_to_window = pad_to_window
        self.pad_id = pad_id
        self.logprob_dtype = getattr(torch, logprob_dtype)
        self.positions_per_chunk = positions_per_chunk
        self.device = device
        self.forward_calls = 0
        self.positions_computed = 0

    def score(self, windows: Sequence[Sequence[int]]) -> list[WindowScores]:
        """Score window inputs in order (each the start token plus up to ``positions - 1`` text tokens)."""
        torch = self.torch
        out: list[WindowScores] = []
        for chunk in batched(range(len(windows)), self.windows_per_batch):
            rows = [list(windows[i]) for i in chunk]
            if any(len(r) > self.positions or len(r) < 2 for r in rows):
                raise ValueError("a window is empty or longer than the model's positions")
            if self.pad_to_window:
                rows += [rows[0]] * (self.windows_per_batch - len(rows))
                x = torch.full((len(rows), self.positions), self.pad_id, dtype=torch.long)
                for j, r in enumerate(rows):
                    x[j, :len(r)] = torch.tensor(r, dtype=torch.long)
            else:
                x = torch.tensor(rows, dtype=torch.long)
            x = x.to(self.device)
            with torch.inference_mode():
                hidden = self.base(input_ids=x, use_cache=False).last_hidden_state
                self.forward_calls += 1
                self.positions_computed += int(x.numel())
                for j, i in enumerate(chunk):
                    n = len(windows[i])
                    out.append(self._window(hidden[j, :n], x[j, 1:n]))
        return out

    def _window(self, hidden, targets) -> WindowScores:
        torch = self.torch
        n = hidden.shape[0]
        tl, bl, en = [], [], []
        for a in range(0, n, self.positions_per_chunk):
            b = min(a + self.positions_per_chunk, n)
            logp = torch.log_softmax(self.head(hidden[a:b]).to(self.logprob_dtype), dim=-1)
            t = targets[a:min(b, n - 1)]
            if t.numel():
                tl.append(logp[: t.shape[0]].gather(-1, t.unsqueeze(-1)).squeeze(-1))
            bl.append(torch.logsumexp(logp.masked_fill(~self.mask, float("-inf")), dim=-1))
            en.append(-(logp.exp() * logp).sum(-1))
        cat = torch.cat
        return WindowScores(target_logp=cat(tl).double().cpu().tolist() if tl else [],
                            boundary_logmass=cat(bl).double().cpu().tolist(),
                            entropy=cat(en).double().cpu().tolist())
