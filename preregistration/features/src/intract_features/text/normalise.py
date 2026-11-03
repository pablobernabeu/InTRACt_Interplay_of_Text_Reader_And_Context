"""The registered normalisation, applied once to every text when it is loaded (S3).

supplementary.qmd, S3: "Before any stage runs, each text is normalised once to Unicode normalisation
form NFC and stripped of invisible format characters, and its pages are joined with one space."

`normalise` is promoted exactly from the translated-union benchmark, where seglib2.normalise and
tu_common.normalise are the same function (presub/translated_union/scripts): NFC first, then
deletion of a fixed set of format characters. seglib2.py has one copy (SHA-256 60b1e485ad3430f9...).
tu_common.py has two, and both are cited: the copy of 23 October 2026 kept in presub/_pre_20261103
(SHA-256 5ef80254e3d883dd...) and the presub/ copy edited on 3 November 2026 (SHA-256
aae704e68737f0d3...), whose edit added languages and left DELETE, DEL_RE and normalise unchanged.
The deleted set is the operational meaning of "invisible format characters":

    U+200B..U+200F  zero width space, zero width non-joiner and joiner, left-to-right and
                    right-to-left marks
    U+202A..U+202E  the bidirectional embeddings and overrides, and their pop
    U+2060..U+2069  word joiner, the invisible mathematical operators (U+2065 is unassigned) and
                    the bidirectional isolates
    U+061C          Arabic letter mark
    U+FEFF          zero width no-break space, the byte order mark

The set is not general category Cf as a whole. Among the 149 Cf characters it keeps (Unicode 15.1)
are the soft hyphen U+00AD, the Arabic number signs U+0600..U+0605, U+180E, the deprecated format
characters U+206A..U+206F, the interlinear annotation characters U+FFF9..U+FFFB and the tag
characters of emoji flag sequences, U+E0001 and U+E0020..U+E007F. The benchmarks ran with exactly
this set, so it is kept here; whether it is complete is for the Feature Specification to settle.

Because NFC runs before the deletion, a deleted joiner can leave a base letter and a combining mark
adjacent but uncomposed ("e", U+200D, U+0301 becomes "e", U+0301), so the output is not always in
NFC, and a second call can change it. The registered rule normalises each text once, at load time,
and stages/documents.py does exactly that.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence

FORM = "NFC"

# The Unicode Character Database of the running Python decides NFC and every general category the
# word function reads. Python 3.12 ships 15.0.0 and 3.13 ships 15.1.0; the documents stage records
# the version it ran with and compares it with the one config/stages/documents.toml names.
UNICODE_VERSION = unicodedata.unidata_version

# [first, last] inclusive code point ranges of the deleted format characters, in the benchmark's
# order. config/stages/documents.toml repeats them beside the anchor, and tests/unit/test_text.py
# keeps the two equal.
FORMAT_CHARACTER_RANGES: tuple[tuple[int, int], ...] = (
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x2069),
    (0x061C, 0x061C),
    (0xFEFF, 0xFEFF),
)


def characters(ranges: Iterable[Sequence[int]]) -> frozenset[str]:
    """The characters of inclusive [first, last] code point ranges."""
    out: set[str] = set()
    for pair in ranges:
        if len(pair) != 2:
            raise ValueError(f"a range is [first, last], not {pair!r}")
        first, last = int(pair[0]), int(pair[1])
        if not 0 <= first <= last <= 0x10FFFF:
            raise ValueError(f"invalid code point range {pair!r}")
        out.update(chr(c) for c in range(first, last + 1))
    return frozenset(out)


def _deletion_pattern(chars: frozenset[str]) -> re.Pattern[str]:
    if not chars:
        return re.compile(r"(?!)")  # matches nothing
    # \U escapes keep the class readable whatever the characters are.
    return re.compile("[" + "".join(f"\\U{ord(c):08x}" for c in sorted(chars)) + "]")


DELETED: frozenset[str] = characters(FORMAT_CHARACTER_RANGES)
_DELETE_RE = _deletion_pattern(DELETED)


def normalise(text: str) -> str:
    """The registered normalisation: NFC, then the characters of FORMAT_CHARACTER_RANGES removed.

    Identical to the benchmark's seglib2.normalise. Configuration-independent, so the catalogue
    lock's fingerprints (lock.py) never depend on a setting.
    """
    return _DELETE_RE.sub("", unicodedata.normalize(FORM, text))


class Normaliser:
    """The registered normalisation with its deleted set read from configuration.

    The documents stage builds one from config/stages/documents.toml [normalise], so the set the
    Feature Specification cites is the set that runs. Built with the defaults it equals `normalise`.
    """

    def __init__(self, ranges: Iterable[Sequence[int]] = FORMAT_CHARACTER_RANGES, form: str = FORM):
        if form != FORM:
            raise ValueError(f"the registered normalisation is {FORM} (S3), not {form!r}")
        self.deleted = characters(ranges)
        self._re = _deletion_pattern(self.deleted)

    def __call__(self, text: str) -> str:
        """Normalise one string."""
        return self._re.sub("", unicodedata.normalize(FORM, text))

    def with_stats(self, text: str) -> tuple[str, int, bool]:
        """(normalised text, number of format characters deleted, whether NFC changed the text)."""
        nfc = unicodedata.normalize(FORM, text)
        out = self._re.sub("", nfc)
        return out, len(nfc) - len(out), nfc != text
