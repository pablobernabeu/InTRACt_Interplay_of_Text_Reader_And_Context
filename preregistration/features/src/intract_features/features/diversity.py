"""Lexical diversity: the moving-average type-token ratio (MATTR) and the Measure of Textual Lexical Diversity.

qmd Materials: "Diversity is the moving-average type-token ratio over windows of 50 content lemmas. Its
per-language correlations with the content-form and all-word versions and with the Measure of Textual Lexical
Diversity will be reported." S3 adds windows of 25 and 100 as variants and cites Covington and McFall (2010) for
MATTR and McCarthy and Jarvis (2010) for MTLD.

`mattr` is the per-text reference loop of lexrules.mattr_ref and b4_pud_units.mattr. `mattr_batch` is em_core.py's
vectorised version for many synthetic texts at once, promoted with its test; the stage uses `mattr`. `mtld` is new:
forward and reverse passes, each the token count over the factor count, a factor closing when the running
type-token ratio reaches the factor size (.72; or falls below it, by configuration) and the remainder adding the
partial factor (1 - TTR) / (1 - .72); the two passes are averaged. How short texts and factor edges are treated
is configured, not set here (config/stages/features_gramlex.toml, [diversity]).

Keys follow lexrules.content_lemma: the lower-cased lemma (else the form), the surface form where the language's
Stanza package has no lemmatiser, and no lower-casing where the configuration says so. Lower-casing is
language-aware (critique item 19).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from intract_features.features.lexical import Token, is_wordlike, lower

NAN = float("nan")


@dataclass(frozen=True)
class DiversityRules:
    """The diversity settings, read once from the [diversity] table of the stage configuration."""

    window: int
    variant_windows: tuple[int, ...]
    short_text: str
    mtld_threshold: float
    mtld_inclusive: bool
    mtld_min_factor_tokens: int
    mtld_unit: str
    lemma_is_form: bool
    keep_case: bool
    dotted_i: bool

    @classmethod
    def from_config(cls, stage_cfg: Mapping, iso: str) -> DiversityRules:
        """Build the settings for one language from the stage configuration."""
        d = stage_cfg["diversity"]
        rules = cls(window=int(d["window"]), variant_windows=tuple(int(w) for w in d["variant_windows"]),
                    short_text=d["short_text"], mtld_threshold=float(d["mtld_threshold"]),
                    mtld_inclusive=bool(d["mtld_inclusive"]), mtld_min_factor_tokens=int(d["mtld_min_factor_tokens"]),
                    mtld_unit=d["mtld_unit"], lemma_is_form=iso in d["lemma_is_form_languages"],
                    keep_case=iso in d["keep_case_languages"],
                    dotted_i=iso in stage_cfg["lexical"]["casing"]["dotted_i_languages"])
        if rules.short_text not in ("ttr", "missing"):
            raise ValueError(f"diversity.short_text must be 'ttr' or 'missing', not {rules.short_text!r}")
        if rules.mtld_unit not in ("content_lemma", "all_word"):
            raise ValueError(f"diversity.mtld_unit must be 'content_lemma' or 'all_word', not {rules.mtld_unit!r}")
        return rules


# ---------------------------------------------------------------- MATTR


def mattr(seq: Sequence, window: int, short_text: str) -> float:
    """MATTR of one sequence (Covington and McFall, 2010): the mean type-token ratio of every window of `window`
    consecutive units.

    The distinct counts are summed as integers and divided once, which equals the mean of the window ratios up to
    one rounding. A sequence no longer than the window takes its type-token ratio ("ttr", the benchmarks' rule) or
    is undefined ("missing"); an empty one is undefined.
    """
    n = len(seq)
    if n == 0:
        return NAN
    if n <= window:
        return len(set(seq)) / n if short_text == "ttr" else NAN
    counts: dict = {}
    for x in seq[:window]:
        counts[x] = counts.get(x, 0) + 1
    total = len(counts)
    for i in range(window, n):
        old, new = seq[i - window], seq[i]
        counts[old] -= 1
        if counts[old] == 0:
            del counts[old]
        counts[new] = counts.get(new, 0) + 1
        total += len(counts)
    return total / ((n - window + 1) * window)


def mattr_batch(tok, ustart, uend, rows, cols, n_texts: int, vocab: int, window: int):
    """MATTR of many texts at once, each text a run of units given as (rows, cols) pairs (em_core.mattr_batch).

    A position p, whose type last occurred at q (-1 if never), is that type's first occurrence in window i exactly
    when max(p - w + 1, q + 1, 0) <= i <= min(p, n - w), so the windows' type counts sum to the summed lengths of
    those ranges. Texts no longer than the window take types over tokens. The previous occurrence comes from one
    in-place sort of the packed key ((text * V + type) << bits) | position, which puts equal (text, type) groups
    side by side in position order, with no argsort or gather. Needs numpy.
    """
    import numpy as np

    lens = uend[cols] - ustart[cols]
    n_tok = int(lens.sum())
    out = np.full(n_texts, np.nan)
    if n_tok == 0:
        return out
    before = np.cumsum(lens) - lens
    idx = np.repeat(ustart[cols] - before, lens) + np.arange(n_tok)
    t = tok[idx].astype(np.int64)
    tid = np.repeat(rows, lens).astype(np.int64)
    n_t = np.bincount(tid, minlength=n_texts)
    start_t = np.cumsum(n_t) - n_t
    sh = int(max(int(n_t.max()), 1)).bit_length()
    if int(n_texts) * int(vocab) >= (1 << (62 - sh)):
        raise OverflowError("the packed MATTR key would overflow 64 bits")
    key = ((tid * vocab + t) << sh) | (np.arange(n_tok, dtype=np.int64) - start_t[tid])
    del t, idx
    key.sort()
    g = key >> sh
    p = key & ((1 << sh) - 1)
    first = np.empty(n_tok, bool)
    first[0] = True
    first[1:] = g[1:] != g[:-1]
    q = np.empty(n_tok, np.int64)
    q[0] = -1
    q[1:] = p[:-1]
    q[first] = -1
    tid = g // vocab
    n = n_t[tid]
    c = np.maximum(np.minimum(p, n - window) - np.maximum(np.maximum(p - window + 1, q + 1), 0) + 1, 0)
    sum_c = np.bincount(tid, weights=c, minlength=n_texts)
    distinct = np.bincount(tid, weights=first, minlength=n_texts)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(n_t > window, sum_c / ((n_t - window + 1) * window), distinct / np.maximum(n_t, 1))
    out[n_t == 0] = np.nan
    return out


# ---------------------------------------------------------------- MTLD


def mtld_factors(seq: Sequence, threshold: float, inclusive: bool, min_factor: int) -> tuple[int, int, int]:
    """One pass of MTLD: (full factors, tokens left over, types among them).

    The running type-token ratio is updated token by token; when it reaches the threshold (or falls below it when
    `inclusive` is false) in a factor of at least `min_factor` tokens, the factor is counted and the count restarts.
    """
    full = count = 0
    types: set = set()
    for x in seq:
        count += 1
        types.add(x)
        ttr = len(types) / count
        if (ttr <= threshold if inclusive else ttr < threshold) and count >= min_factor:
            full += 1
            count = 0
            types = set()
    return full, count, len(types)


def mtld_pass(seq: Sequence, threshold: float, inclusive: bool, min_factor: int) -> float:
    """Tokens per factor in one direction, the remainder counted as the partial factor (1 - TTR) / (1 - threshold).

    Undefined when no factor accrues, as when every token is a new type.
    """
    full, rest, rest_types = mtld_factors(seq, threshold, inclusive, min_factor)
    factors = full + ((1 - rest_types / rest) / (1 - threshold) if rest else 0.0)
    return len(seq) / factors if factors > 0 else NAN


def mtld(seq: Sequence, threshold: float, inclusive: bool, min_factor: int) -> float:
    """MTLD (McCarthy and Jarvis, 2010): the mean of the forward and the reverse pass; undefined for an empty
    sequence or when either pass is."""
    if not seq:
        return NAN
    forward = mtld_pass(seq, threshold, inclusive, min_factor)
    reverse = mtld_pass(list(reversed(seq)), threshold, inclusive, min_factor)
    return (forward + reverse) / 2


# ---------------------------------------------------------------- sequences and features


def diversity_sequences(tokens: Sequence[Token], rules: DiversityRules) -> dict[str, list[str]]:
    """The unit sequences of one text, in text order: content lemmas, content forms and all words.

    Content words already exclude names (lexical.build_tokens). All words are every syntactic word bearing a
    letter or digit, names included, as in b4_pud_units.py. Forms are lower-cased in every language, as there;
    lemma keys keep their case where the configuration says so (lexrules.content_lemma).
    """
    def lemma_key(w) -> str:
        key = w.form if rules.lemma_is_form else w.lemma
        return key if rules.keep_case else lower(key, rules.dotted_i)

    content = [w for t in tokens for w in t.words if w.content]
    return {"content_lemma": [lemma_key(w) for w in content],
            "content_form": [lower(w.form, rules.dotted_i) for w in content],
            "all_word": [lower(w.form, rules.dotted_i) for t in tokens for w in t.words if is_wordlike(w.form)]}


def diversity_features(seqs: Mapping[str, Sequence[str]], rules: DiversityRules) -> tuple[dict[str, float], dict]:
    """MATTR over content lemmas (the anchor), its registered variants and MTLD, with diagnostics."""
    lem = seqs["content_lemma"]
    values = {"mattr": mattr(lem, rules.window, rules.short_text)}
    for w in rules.variant_windows:
        values[f"mattr_window{w}"] = mattr(lem, w, rules.short_text)
    values["mattr_content_forms"] = mattr(seqs["content_form"], rules.window, rules.short_text)
    values["mattr_all_words"] = mattr(seqs["all_word"], rules.window, rules.short_text)
    args = (rules.mtld_threshold, rules.mtld_inclusive, rules.mtld_min_factor_tokens)
    other = "all_word" if rules.mtld_unit == "content_lemma" else "content_lemma"
    values["mtld"] = mtld(seqs[rules.mtld_unit], *args)
    diag = {"content_lemmas": len(lem), "all_words": len(seqs["all_word"]), f"mtld_{other}": mtld(seqs[other], *args)}
    return values, diag
