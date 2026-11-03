"""Valence and arousal: text means (covariates) and standard deviations (descriptive).

Materials: "Affective features are the mean and the variability of valence and of arousal." Measures: mean valence
and mean arousal enter every model as covariates; "The variability of valence and of arousal ... will be computed
for description only". S3, valence and arousal row: the resource is "MEmoLon, induced for 91 languages from a
single procedure" (MTL_grouped v1.0, doi:10.5281/zenodo.3756607, CC BY 4.0), and "Lookups try the language-aware
lower case, the surface form and the lemma, then a script fallback ... Rows equal to a language file's
unknown-word default are dropped." English has no script fallback (S3 names one for Arabic, Hebrew, Korean,
Chinese and Thai only).

Means are taken over content tokens (Materials, third rule: "those whose universal part-of-speech tag is NOUN,
VERB, ADJ or ADV"), names excluded (Materials: names are excluded "from every norm-based mean"), and each mean is
also reported without the exclusion ("Each norm-based mean is reported with and without the exclusion"). Every
measure reports the proportion of tokens it matched (Materials, third rule).

Promoted from affect-narrativity-duration/scripts/memolon_flores.py and verify-affect/scripts/flores_affect.py and
lexicon_profile.py (the file layout, dropping default rows, dropping multi-word entries, token-weighted means over
matched tokens). The two earlier scripts dropped the rows equal to the file's modal tuple; this module drops those
equal to the final <UNK> row, the unknown-word default S3 names. That the two tuples agree in every language file is
UNVERIFIED: lexicon_profile.py found the <UNK> row last but did not compare it with the modal tuple.
"""

from __future__ import annotations

import math
import os
import statistics
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

COLUMNS = ("word", "valence", "arousal", "dominance", "joy", "anger", "sadness", "fear", "disgust")
UNKNOWN_ROW = "<UNK>"

Word = Mapping[str, Any]


def read_last_line(path: str | os.PathLike, chunk: int = 4096) -> str:
    """The last non-empty line of a text file, read from its end."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        end = fh.tell()
        buf = b""
        pos = end
        while pos > 0:
            step = min(chunk, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + buf
            # Trailing blank or whitespace-only lines are not the last row.
            lines = buf.rstrip(b" \t\r\n").split(b"\n")
            if len(lines) > 1 or pos == 0:
                return lines[-1].rstrip(b"\r").decode("utf-8")
    return ""


@dataclass(frozen=True)
class AffectLexicon:
    """Valence and arousal by word, after the registered row filters."""

    values: dict[str, tuple[float, float]]
    default: tuple[float, ...]
    rows: int
    default_rows: int
    multiword_rows: int


def _row(line: str, path) -> tuple[str, tuple[float, ...]]:
    fields = line.rstrip("\r\n").split("\t")
    if len(fields) != len(COLUMNS):
        raise ValueError(f"{path}: expected {len(COLUMNS)} tab-separated fields, got {len(fields)}: {line[:80]!r}")
    values = tuple(float(x) for x in fields[1:])
    # float() reads "nan" and "inf"; such a value would stop the stage later, in the standard deviation, far from its
    # cause, so the file is refused here.
    if not all(math.isfinite(v) for v in values):
        raise ValueError(f"{path}: a non-finite value in the row of {fields[0]!r}")
    return fields[0], values


def load_memolon(path: str | os.PathLike, keys: Collection[str] | None = None,
                 drop_multiword: bool = True) -> AffectLexicon:
    """Read one MEmoLon language file (word and eight values, tab-separated, header first, <UNK> last).

    The unknown-word default is the eight-value tuple of the final <UNK> row; every row equal to it carries no
    word-specific value and is dropped, as is the <UNK> row itself (S3; verify-affect lexicon_profile.py found the
    <UNK> row last in every language file). A non-finite value refuses the file. Multi-word entries are dropped
    because lookups are single syntactic words. With `keys`, only those words are kept, which saves memory on a
    2-million-row file when a shard needs a few thousand.
    """
    last = read_last_line(path)
    word, default = _row(last, path)
    if word != UNKNOWN_ROW:
        raise ValueError(f"{path}: the last row is {word!r}, not {UNKNOWN_ROW!r}; cannot identify the default")
    values: dict[str, tuple[float, float]] = {}
    rows = n_default = n_multi = 0
    with open(path, encoding="utf-8", newline="") as fh:
        header = fh.readline().rstrip("\r\n").split("\t")
        if tuple(header) != COLUMNS:
            raise ValueError(f"{path}: unexpected header {header}")
        for line in fh:
            if not line.strip():
                continue
            w, vals = _row(line, path)
            rows += 1
            if w == UNKNOWN_ROW or vals == default:
                # counted with the <UNK> row itself, as verify-affect lexicon_profile.py counts default rows
                n_default += 1
                continue
            if drop_multiword and " " in w:
                n_multi += 1
                continue
            if keys is not None and w not in keys:
                continue
            values.setdefault(w, (vals[0], vals[1]))
    return AffectLexicon(values=values, default=default, rows=rows, default_rows=n_default, multiword_rows=n_multi)


def candidate_keys(word: Word, lower: Callable[[str], str], order: Sequence[str]) -> list[str]:
    """Lookup keys in the registered order: "lower" (language-aware lower case of the form), "surface", "lemma"."""
    out = []
    for step in order:
        if step == "lower":
            k = lower(word["form"])
        elif step == "surface":
            k = word["form"]
        elif step == "lemma":
            k = word.get("lemma") or "_"
            if k == "_":
                continue
        else:
            raise ValueError(f"unknown lookup step {step!r}")
        if k not in out:
            out.append(k)
    return out


def lookup(values: Mapping[str, tuple[float, float]], keys: Iterable[str]) -> tuple[float, float] | None:
    """The first key's values found in the lexicon, or None."""
    for k in keys:
        v = values.get(k)
        if v is not None:
            return v
    return None


@dataclass(frozen=True)
class AffectSummary:
    """Token-weighted affect of one text over its matched content tokens."""

    content_tokens: int
    matched_tokens: int
    valence_mean: float | None
    valence_sd: float | None
    arousal_mean: float | None
    arousal_sd: float | None

    def coverage(self) -> float | None:
        """Matched-token proportion (Materials, third rule: "every measure reports the proportion of tokens it
        matched")."""
        return self.matched_tokens / self.content_tokens if self.content_tokens else None


def _sd(xs: Sequence[float], ddof: int) -> float | None:
    if len(xs) <= ddof:
        return None
    return statistics.stdev(xs) if ddof == 1 else statistics.pstdev(xs)


def summarise(matched: Sequence[tuple[float, float]], content_tokens: int, ddof: int) -> AffectSummary:
    """Means and standard deviations of the matched values; None where no token matched (undefined by
    construction), and SDs None below ddof + 1 matched tokens."""
    if ddof not in (0, 1):
        raise ValueError("ddof must be 0 or 1")
    val = [v for v, _ in matched]
    aro = [a for _, a in matched]
    return AffectSummary(content_tokens=content_tokens, matched_tokens=len(matched),
                         valence_mean=statistics.fmean(val) if val else None, valence_sd=_sd(val, ddof),
                         arousal_mean=statistics.fmean(aro) if aro else None, arousal_sd=_sd(aro, ddof))


def text_affect(words: Iterable[Word], is_name: Iterable[bool], values: Mapping[str, tuple[float, float]],
                lower: Callable[[str], str], order: Sequence[str], content_upos: Collection[str],
                ddof: int) -> tuple[AffectSummary, AffectSummary]:
    """(with the name exclusion, without it) over the content syntactic words of a text."""
    with_ex: list[tuple[float, float]] = []
    without: list[tuple[float, float]] = []
    n_with = n_without = 0
    for w, name in zip(words, is_name, strict=True):
        if w["upos"] not in content_upos:
            continue
        v = lookup(values, candidate_keys(w, lower, order))
        n_without += 1
        if v is not None:
            without.append(v)
        if name:
            continue
        n_with += 1
        if v is not None:
            with_ex.append(v)
    return summarise(with_ex, n_with, ddof), summarise(without, n_without, ddof)
