"""The long-unit rule of the two-parser mean, and the check of the units UDPipe refuses as too long.

Supplementary S3: "A unit longer than 100 words takes Stanza's parse in both members of the mean. UDPipe 2 failed on
3 of the 5 Arabic units over 150 words, whereas Stanza tracked gold above that length. The share of such units is
reported per language, a language above 1 per cent is flagged, and the calibration applies the same rule."

So a long unit contributes Stanza's counts twice and no parser disagreement. The rule is applied where the members
are combined (the grammatical features), and both parses stay complete in their artefacts: S3 also has both parsers
run "on every sentence of every text".

Words are counted as the error model and the translated benchmark counted them (presub/error_model/scripts/
em_counts.py, presub/translated_union/scripts/tu6_features.py): the registered word function in spaced scripts, and
Stanza's tokens with a letter or digit in Chinese and Thai, whose words are the tokens of the segmenter of the
Stanza package (Measures). "Longer than 100" is strict: a unit of exactly 100 words is not long. Callers pass the
counts, so the rule shares the word function of every other per-word quantity; unit_word_counts() gives them for a
spaced script, placing each registered word in the unit that holds its first letter or digit, as features_gramlex
does by default ([sentences] word_anchor = "first_alnum").

The upstream UDPipe 2 server refuses a sentence of more than 1,000 of its words (udpipe2_server.py at the pinned
commit, TooLongError). Such a unit is long under S3 unless most of its UDPipe tokens are not registered words, so
its missing UDPipe parse costs the mean nothing. RefusalCheck verifies that for every refused unit.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from intract_features.parse import Refused, Unit
from intract_features.text.words import words as registered_words

T = TypeVar("T")


@dataclass(frozen=True)
class LongUnitRule:
    """The rule's two registered constants, read from config/stages/parse_udpipe.toml ([long_units])."""

    max_words: int
    flag_share: float

    @classmethod
    def from_config(cls, cfg: dict, stage: str = "parse_udpipe") -> LongUnitRule:
        """Read the constants from the merged configuration."""
        table = cfg["stages"][stage]["long_units"]
        return cls(max_words=int(table["max_words"]), flag_share=float(table["flag_share"]))

    def is_long(self, n_words: int) -> bool:
        """S3: "longer than 100 words"."""
        return n_words > self.max_words

    def mask(self, word_counts: Sequence[int]) -> list[bool]:
        """Which units of a text are long."""
        return [self.is_long(n) for n in word_counts]

    def udpipe_member(self, stanza: Sequence[T], udpipe: Sequence[T], word_counts: Sequence[int]) -> list[T]:
        """The second member of the mean, unit by unit: Stanza's value for a long unit, UDPipe's otherwise.

        Works on anything aligned with the units, such as parses or per-unit count vectors.
        """
        if not len(stanza) == len(udpipe) == len(word_counts):
            raise ValueError(f"{len(stanza)} Stanza, {len(udpipe)} UDPipe values for {len(word_counts)} units")
        return [s if self.is_long(n) else u for s, u, n in zip(stanza, udpipe, word_counts, strict=True)]

    def udpipe_pair_member(self, stanza_pairs: Sequence[T], udpipe_pairs: Sequence[T],
                           word_counts: Sequence[int]) -> list[T]:
        """The second member for a quantity of adjacent unit pairs, such as an overlap flag.

        Pair i joins units i and i + 1, and it keeps UDPipe's value only if neither unit is long, as the error model's
        member did (em_counts.py: "an adjacent pair keeps U's overlap flag only if neither sentence is long").
        """
        n = len(word_counts)
        if not len(stanza_pairs) == len(udpipe_pairs) == max(n - 1, 0):
            raise ValueError(f"{len(stanza_pairs)} and {len(udpipe_pairs)} pair values for {n} units")
        long_ = self.mask(word_counts)
        return [s if long_[i] or long_[i + 1] else u
                for i, (s, u) in enumerate(zip(stanza_pairs, udpipe_pairs, strict=True))]

    def summary(self, word_counts: Sequence[int]) -> dict:
        """The per-language report: the share of long units (and of their words) and the 1 per cent flag."""
        long_ = self.mask(word_counts)
        long_words = sum(n for n, is_long in zip(word_counts, long_, strict=True) if is_long)
        return self.summary_from_counts(len(word_counts), sum(long_), sum(word_counts), long_words)

    def summary_from_counts(self, units: int, long_units: int, words: int | None = None,
                            long_words: int | None = None) -> dict:
        """The same report from counts summed over shards or texts, as an aggregation step holds them.

        S3: "The share of such units is reported per language, a language above 1 per cent is flagged". The flag is
        strict: a share of exactly 1 per cent is not above it.
        """
        share = long_units / units if units else 0.0
        out = {"units": units, "long_units": long_units, "share_units": share, "max_words": self.max_words,
               "flag_share": self.flag_share, "flagged": share > self.flag_share}
        if words is not None and long_words is not None:
            out.update(words=words, long_words=long_words, share_words=long_words / words if words else 0.0)
        return out


def unit_word_counts(doc_text: str, units: Sequence[Unit]) -> list[int]:
    """Registered words per unit in a spaced script, each placed in the unit that holds its first letter or digit.

    Units are the stripped, ordered, non-overlapping spans of parse.document_units. A word whose anchor lies in no
    unit is counted in none.
    """
    starts = [u.start for u in units]
    counts = [0] * len(units)
    for w in registered_words(doc_text):
        k = bisect_right(starts, w.anchor) - 1
        if k >= 0 and w.anchor < units[k].end:
            counts[k] += 1
    return counts


@dataclass
class RefusalCheck:
    """The units UDPipe refused (parse.Refused), checked against the long-unit rule; feeds parse_shard's observe.

    A refused unit that is long loses nothing, because S3 gives it Stanza's parse in both members. One that is not
    long would leave the UDPipe member without that unit, which no registered rule covers: it is flagged in the run
    record and on stderr, or, with `fail`, fails the shard (config [refusals] refused_not_long, PENDING the Feature
    Specification). Where the registered words come from the Stanza segmenter (Chinese and Thai, `spaced` false),
    the UDPipe stage cannot count them, and such a unit is reported as unchecked.
    """

    rule: LongUnitRule
    spaced: bool
    fail: bool
    refused: int = 0
    long: int = 0
    not_long: int = 0
    unchecked: int = 0
    max_words: int = 0
    not_long_units: list[str] = field(default_factory=list)

    def observe(self, doc, units: Sequence[Unit], parses: Sequence[object]) -> None:
        """Check the refused units of one document."""
        refused = [i for i, p in enumerate(parses) if isinstance(p, Refused)]
        if not refused:
            return
        counts = unit_word_counts(doc.text, units) if self.spaced else None
        for i in refused:
            self.refused += 1
            if counts is None:
                self.unchecked += 1
                continue
            n = counts[i]
            self.max_words = max(self.max_words, n)
            if self.rule.is_long(n):
                self.long += 1
            else:
                self.not_long += 1
                self.not_long_units.append(f"{doc.story_id}-{units[i].k}")

    def problem(self) -> str | None:
        """The failure message when a refused unit is not long and `fail` is set, else None."""
        if self.fail and self.not_long:
            return (f"UDPipe refused {self.not_long} unit(s) of at most {self.rule.max_words} registered words "
                    f"(not long under S3), e.g. {self.not_long_units[:3]}")
        return None

    def record(self) -> dict:
        """Counts for the run record (no text: unit identifiers go to stderr only)."""
        return {"refused_units": self.refused, "long": self.long, "not_long": self.not_long,
                "unchecked": self.unchecked, "max_registered_words": self.max_words,
                "rule_max_words": self.rule.max_words, "fail_on_not_long": self.fail}
