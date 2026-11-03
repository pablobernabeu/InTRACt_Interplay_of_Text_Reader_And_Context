"""The registered word function, the only one in the pipeline.

Measures (preregistration.qmd): "A word, in the processing outcome's denominator and in every
per-word quantity, is a whitespace-delimited token of the text as served that contains at least one
letter or digit. A token of punctuation alone attaches to a neighbouring word."

Promoted from the error-model benchmark's lexrules.registered_words (presub/error_model/scripts/
lexrules.py), with exactly its semantics. Two copies of that file exist, and both are cited: the copy
of 22 October 2026 kept in presub/_pre_20261103 (SHA-256 2dc7fac3c2806948...) and the presub/ copy
edited on 3 November 2026 (SHA-256 fed2de71bc29c668...). The edit added Turkish casing keys and the
four new languages; WS, is_reg_word and registered_words are the same in both.

- Whitespace is the Unicode White_Space property: U+0009..U+000D, U+0020, U+0085, U+00A0, U+1680,
  U+2000..U+200A, U+2028, U+2029, U+202F, U+205F and U+3000. str.split() is not used, because it
  also splits on U+001C..U+001F, which are not White_Space (feature plan v3, "Definition of a word").
- A token is a word if it holds a character of general category N (a digit or other number) or L
  other than Lm.
- A token made only of modifier letters (Lm, such as Thai U+0E46 or the prolonged sound mark U+30FC)
  is not a word: it joins the preceding word.

lexrules counted words. This module returns them as [start, end) spans over the text, one per word,
so their number equals lexrules' count for every string (tests/unit/test_text.py compares the two on
fixed and random strings). A span is the word's own whitespace token. Attachment never changes the
count, and a span that stays inside its token never crosses whitespace, so a sentence or page
boundary assigns every word unambiguously by its anchor, the offset of its first letter or digit.
word_extents() widens the spans over the tokens attached to them, for stages that need that.

Chinese and Thai do not separate words with spaces, so there the registered word is a token of the
frozen word segmenter (Measures), which the parse stages supply. In every other language, Korean
eojeols and Arabic and Hebrew orthographic words included, it is this function's token.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection
from functools import lru_cache
from typing import NamedTuple

# The Unicode White_Space property, unchanged since Unicode 6.3 removed U+180E from it.
WHITE_SPACE: frozenset[str] = frozenset(
    chr(c)
    for c in (*range(0x0009, 0x000E), 0x0020, 0x0085, 0x00A0, 0x1680, *range(0x2000, 0x200B),
              0x2028, 0x2029, 0x202F, 0x205F, 0x3000)
)
_TOKEN_RE = re.compile("[^" + "".join(f"\\u{ord(c):04x}" for c in sorted(WHITE_SPACE)) + "]+")

# The one in-page line break (gap G9). The delivery writes a line break inside a page as a backslash
# followed by n, and io.catalogue.split_lines() decodes that escape into a line feed, the only line
# break a page can hold. Every rule that looks for the start of a line uses this one character: the
# page-initial titles (text/titles.py), turn-initial dashes here, the dialogue detector's dash turns
# and SaT's forced boundaries. A carriage return, U+2028 or another character that str.splitlines()
# would honour is ordinary whitespace inside a page.
LINE_BREAK = "\n"

# Tokens longer than this are scanned without the cache, so a pathological unspaced run cannot
# fill it.
_CACHED_TOKEN_LENGTH = 64


class Word(NamedTuple):
    """One registered word: its token's [start, end) span and the offset of its first letter or digit."""

    start: int
    end: int
    anchor: int


def _first_word_character(token: str) -> int:
    for i, ch in enumerate(token):
        cat = unicodedata.category(ch)
        if cat[0] == "N" or (cat[0] == "L" and cat != "Lm"):
            return i
    return -1


_first_word_character_cached = lru_cache(maxsize=1 << 16)(_first_word_character)


def _anchor(token: str) -> int:
    if len(token) <= _CACHED_TOKEN_LENGTH:
        return _first_word_character_cached(token)
    return _first_word_character(token)


def is_word_token(token: str) -> bool:
    """True if a token holds a letter other than a modifier letter, or a digit (lexrules.is_reg_word)."""
    return _anchor(token) >= 0


def whitespace_tokens(text: str) -> list[tuple[int, int]]:
    """[start, end) spans of every White_Space-delimited token, words or not."""
    return [m.span() for m in _TOKEN_RE.finditer(text)]


def words(text: str) -> list[Word]:
    """The registered words of a text, in order."""
    out = []
    for m in _TOKEN_RE.finditer(text):
        a = _anchor(m.group())
        if a >= 0:
            start, end = m.span()
            out.append(Word(start, end, start + a))
    return out


def word_spans(text: str) -> list[tuple[int, int]]:
    """[start, end) spans of the registered words of a text: the registered word function."""
    return [(w.start, w.end) for w in words(text)]


def count_words(text: str | None) -> int:
    """The number of registered words, equal to lexrules.registered_words (None counts as empty, as there)."""
    if not text:
        return 0
    return sum(1 for m in _TOKEN_RE.finditer(text) if _anchor(m.group()) >= 0)


def _is_modifier_only(token: str) -> bool:
    return all(unicodedata.category(ch) == "Lm" for ch in token)


def _starts_line(text: str, start: int, breaks: Collection[int]) -> bool:
    i = start
    while i > 0 and text[i - 1] in WHITE_SPACE:
        i -= 1
        if text[i] == LINE_BREAK:
            return True
    return i == 0 or any(i <= b <= start for b in breaks)


def _joins_following(text: str, start: int, end: int, openers: Collection[str], breaks: Collection[int]) -> bool:
    token = text[start:end]
    if _is_modifier_only(token):
        return False
    if openers and all(ch in openers for ch in token):
        return True
    return all(unicodedata.category(ch) == "Pd" for ch in token) and _starts_line(text, start, breaks)


def word_extents(text: str, *, openers: Collection[str] = (), breaks: Collection[int] = ()) -> list[tuple[int, int]]:
    """Each registered word's span widened over the non-word tokens attached to it.

    Measures registers only that "A token of punctuation alone attaches to a neighbouring word". The
    side follows the feature plan v3 and is PENDING the Feature Specification: "A punctuation-only
    token joins the preceding word, except that an opening quotation mark, a turn-initial dash or a
    text-initial token joins the following word. A token made only of modifier letters (category Lm,
    such as Thai ๆ) joins the preceding word." Here an opening quotation mark is a token made only of
    characters in `openers` (the caller passes its language's opening marks), and a turn-initial dash
    is a token made only of dash punctuation (category Pd) at the start of a line (after LINE_BREAK),
    or at an offset in `breaks` such as a page start. In a run of non-word tokens between two words, the first token
    that joins the following word takes every later token of the run with it, so extents never
    overlap and keep the words' order. Tokens after the last word join it. The extents' number
    equals count_words(text).
    """
    tokens = whitespace_tokens(text)
    is_word = [_anchor(text[s:e]) >= 0 for s, e in tokens]
    word_positions = [i for i, w in enumerate(is_word) if w]
    if not word_positions:
        return []
    extents = [[tokens[i][0], tokens[i][1]] for i in word_positions]
    # Text-initial tokens have no preceding word, so they join the first word.
    extents[0][0] = tokens[0][0]
    extents[-1][1] = tokens[-1][1]
    for k in range(len(word_positions) - 1):
        run = range(word_positions[k] + 1, word_positions[k + 1])
        split = next((i for i in run if _joins_following(text, *tokens[i], openers, breaks)), run.stop)
        if split > run.start:
            extents[k][1] = tokens[split - 1][1]
        if split < run.stop:
            extents[k + 1][0] = tokens[split][0]
    return [(a, b) for a, b in extents]
