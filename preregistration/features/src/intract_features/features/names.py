"""The name inventory, the name mask and the name covariates.

Materials: "Names are taken from a frozen inventory, built after acceptance and before linkage by a two-route rule
that no person reviews. A type is a name if the Stanza parse tags at least half its occurrences as a proper noun,
or as X in Arabic, the tag its treebank gives names." The second route projects names from the English source
through word alignment, so it applies to translations only; English, the source, has the first route alone. The
exact rule awaits P06 and P53, and this module implements the registered text as written.

Materials also registers the covariates: "Name-token share, the empirical logit of the proportion of words in the
outcome's unit that are names, therefore enters every model as a covariate. We will also report the number of
distinct name types per hundred words and the mean repetitions per type, counting types by lemma." Names are
excluded "from every norm-based mean", which `name_flags` supports.

The inventory is built over a language's whole catalogue, so `NameCounts` accumulates over every shard and
`inventory` freezes it. Types are keyed on the normalised lower-cased form, as the benchmark's rule R1 keyed them
(nonnative/names-dialogue-freq/scripts/bench_names_tagonly.py, key and tagname), and occurrences are the parse's
non-punctuation syntactic words, as there.
"""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Word = Mapping[str, Any]
Key = Callable[[Word], str]


def is_punctuation(word: Word) -> bool:
    """bench_names_tagonly.is_punct: tagged PUNCT or SYM, or made only of punctuation, symbols and separators."""
    return word["upos"] in ("PUNCT", "SYM") or all(unicodedata.category(ch)[0] in "PSZ" for ch in word["form"])


class NameCounts:
    """Per type: how many occurrences the parse tags as a name, and how many occurrences there are."""

    def __init__(self) -> None:
        self.tagged: Counter[str] = Counter()
        self.total: Counter[str] = Counter()

    def add(self, words: Iterable[Word], key: Key, name_upos: Collection[str]) -> None:
        """Count the occurrences in one sentence, punctuation excluded."""
        for w in words:
            if is_punctuation(w):
                continue
            k = key(w)
            self.total[k] += 1
            if w["upos"] in name_upos:
                self.tagged[k] += 1

    def merge(self, other: NameCounts) -> None:
        """Add another shard's counts."""
        self.tagged.update(other.tagged)
        self.total.update(other.total)

    def inventory(self, min_share: float) -> frozenset[str]:
        """Types whose tagged share of occurrences is at least `min_share` (Materials: "at least half")."""
        return frozenset(k for k, n in self.total.items() if n and self.tagged[k] / n >= min_share)

    def to_json(self) -> dict:
        """The counts as a strict-JSON dict, keys sorted, so that shards can hand them on to be merged."""
        return {"tagged": dict(sorted(self.tagged.items())), "total": dict(sorted(self.total.items()))}

    @classmethod
    def from_json(cls, obj: Mapping[str, Mapping[str, int]]) -> NameCounts:
        """Counts written by to_json."""
        out = cls()
        out.tagged.update(obj["tagged"])
        out.total.update(obj["total"])
        return out


def inventory_digest(inventory: Iterable[str]) -> str:
    """SHA-256 of the sorted inventory, one type per line, so that run records can compare inventories."""
    return hashlib.sha256("\n".join(sorted(inventory)).encode("utf-8")).hexdigest()


def write_inventory(path: str | os.PathLike, inventory: Iterable[str]) -> None:
    """Write a frozen inventory atomically: one normalised type per line, sorted.

    This is the format features_gramlex reads under its name rule "inventory" (lexical.load_inventory), so both
    stages can mask the same names. A type holding a line break could not round-trip, so it is refused.
    """
    types = sorted(inventory)
    bad = [t for t in types if not t or any(ch in t for ch in "\r\n\x0b\x0c\x1c\x1d\x1e\x85  ")]
    if bad:
        raise ValueError(f"name types that cannot be written one per line: {bad[:3]!r}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Every shard job of a language writes the same inventory, possibly at once and from nodes that share process
    # ids on a shared file system, so each takes its own temporary name before the rename.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.writelines(t + "\n" for t in types)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def read_inventory(path: str | os.PathLike) -> frozenset[str]:
    """Read a frozen inventory written by write_inventory (one type per line, LF or CRLF line ends).

    A checkout that converts line ends gives the file CRLF; lexical.load_inventory, the reader features_gramlex
    uses, strips both too, so the two stages read the same types from one file.
    """
    with open(path, encoding="utf-8", newline="\n") as fh:
        return frozenset(line.rstrip("\r\n") for line in fh if line.strip())


def name_flags(words: Sequence[Word], inventory: Collection[str], key: Key) -> list[bool]:
    """One flag per syntactic word: True where the word's type is in the inventory, whatever its tag."""
    return [(not is_punctuation(w)) and key(w) in inventory for w in words]


def words_overlapping(word_spans: Sequence[tuple[int, int]], spans: Iterable[tuple[int, int]]) -> int:
    """How many word spans (in text order) overlap at least one of `spans`.

    A word of the outcome's unit is a name when a token holding a name overlaps it, so "Tom's" and "Tom," are
    name words; this matches features_gramlex's word rule "any" (lexical.classify_words), under which a word is a
    name when any letter- or digit-bearing syntactic word in it is one.
    """
    marks = sorted(spans)
    hit = 0
    j = 0
    for ws, we in word_spans:
        while j < len(marks) and marks[j][1] <= ws:
            j += 1
        k = j
        while k < len(marks) and marks[k][0] < we:
            if marks[k][1] > ws:
                hit += 1
                break
            k += 1
    return hit


def empirical_logit(k: int, n: int, offset: float) -> float | None:
    """log((k + offset) / (n - k + offset)), defined for a text with at least one word."""
    if n <= 0:
        return None
    return math.log((k + offset) / (n - k + offset))


@dataclass(frozen=True)
class NameMeasures:
    """The registered name covariates of one text, with the counts behind them."""

    n_words: int
    name_words: int
    name_tokens: int
    name_types: int

    def share(self) -> float | None:
        """Proportion of the words in the outcome's unit that are names."""
        return self.name_words / self.n_words if self.n_words else None

    def share_elogit(self, offset: float) -> float | None:
        """Name-token share on the empirical-logit scale, the covariate's registered form."""
        return empirical_logit(self.name_words, self.n_words, offset)

    def types_per(self, per: float) -> float | None:
        """Distinct name types, counted by lemma, per `per` words."""
        return per * self.name_types / self.n_words if self.n_words else None

    def tokens_per_type(self) -> float | None:
        """Mean occurrences per name type (the registered "mean repetitions per type"; PENDING reading)."""
        return self.name_tokens / self.name_types if self.name_types else None
