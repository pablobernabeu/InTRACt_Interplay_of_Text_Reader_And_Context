"""Typographic punctuation for the ASCII-only SimpleStories text.

SimpleStories guarantees ASCII in its English stories (dataset card at the pinned
revision: "ASCII-only guarantee for the English dataset"), whereas the catalogue's English
texts carry typographic quotation marks (preregistration/README.md records that seven
texts were edited between the two deliveries "to straighten typographic quotation
marks"). A stand-in left in ASCII would never exercise the dialogue detector's curly
quotation marks (supplementary.qmd S3: "Dialogue spans are detected from the primary and
alternate quotation pairs of release 47 of the Unicode Common Locale Data Repository"),
the ambiguity between the right single quotation mark and the apostrophe, the ellipsis
character among the terminal marks, or the em dash that the surprisal stage's replacement
table handles (S3: "such as the em dash (U+2014) in 10 of the 18 tokenisers"). The
dry-run critique (item 8) asked for typographic punctuation to be injected
deterministically, and this module does that.

The transform is deterministic and works one whitespace token at a time. It never adds,
removes or moves a whitespace character, and it never empties a token, so the
whitespace-token counts that the stand-in is matched on are unchanged. It is also
idempotent. The rules, applied to each token in this order:

1. Ellipsis. Each run of three full stops becomes the ellipsis character U+2026, left to
   right, so "...." becomes an ellipsis followed by a full stop.
2. Dashes. A token made only of hyphens ("-", "--", "---") becomes an em dash (U+2014),
   as do a run of two or more hyphens inside a token and a hyphen next to a straight
   double quotation mark ('him-"A' becomes 'him—"A' before rule 3). Hyphens inside words
   are kept.
3. Double quotation marks. A straight double quotation mark opens (U+201C) at the start
   of a token or after an opening bracket, dash or opening quotation mark, and closes
   (U+201D) elsewhere. A mark standing alone as a token opens unless a double quotation
   is already open in the text.
4. Single quotation marks and apostrophes. A straight single quotation mark opens
   (U+2018) at the start of a token, or after an opening bracket, dash or opening
   quotation mark, when a letter follows that does not begin a common elision ('em,
   'tis, 'twas, 'cause, 'til, 'bout, 'round, 'n'). Everywhere else, including before a
   digit ('90s), it becomes U+2019, which typeset English uses for both the apostrophe
   and the closing single quotation mark.

The rules mirror the patterns of the SimpleStories test split: in it, 76,729 straight
double quotation marks begin a token and 76,723 end one, and 22,745 of the straight single
quotation marks stand between two letters.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

VERSION = "1"

LEFT_DOUBLE = "“"
RIGHT_DOUBLE = "”"
LEFT_SINGLE = "‘"
RIGHT_SINGLE = "’"  # also the apostrophe, as in typeset English
ELLIPSIS = "…"
EM_DASH = "—"
EN_DASH = "–"

# After these characters a quotation mark opens: brackets, dashes and opening quotation marks.
_OPENERS = frozenset("([{-" + EM_DASH + EN_DASH + LEFT_DOUBLE + LEFT_SINGLE)
# A token-initial apostrophe before these words marks an elision, not an opening quotation mark.
_ELISIONS = frozenset({"em", "tis", "twas", "cause", "til", "bout", "round", "n"})
_HYPHEN_RUN = re.compile(r"-{2,}")
_HYPHEN_BY_QUOTE = re.compile(r'-(?=")|(?<=")-')
_LETTERS = re.compile(r"[A-Za-z]+")
# The same whitespace as str.split(), so that tokens here are the tokens the stand-in is matched on.
_WHITESPACE = re.compile(r"(\s+)")


def transform_tokens(tokens: Sequence[str], *, quotes: bool = True, apostrophes: bool = True,
                     ellipsis: bool = True, dashes: bool = True) -> tuple[list[str], Counter]:
    """Apply the typographic rules to a text's whitespace tokens, in reading order.

    Returns the new tokens, one for each input token and none of them empty, and a
    counter of the replacements made. The state that decides a quotation mark standing
    alone as a token runs across the whole sequence, so a text should be passed whole.
    """
    counts: Counter = Counter()
    state = {"double": False, "single": False}
    out = []
    for token in tokens:
        if ellipsis and "..." in token:
            counts["ellipsis"] += token.count("...")
            token = token.replace("...", ELLIPSIS)
        if dashes and "-" in token:
            token = _dashes(token, counts)
        if (quotes and '"' in token) or (apostrophes and "'" in token):
            token = _quotes(token, state, counts, quotes=quotes, apostrophes=apostrophes)
        out.append(token)
    return out, counts


def transform_text(text: str, *, quotes: bool = True, apostrophes: bool = True, ellipsis: bool = True,
                   dashes: bool = True) -> tuple[str, Counter]:
    """Apply the typographic rules to a string, keeping every whitespace run exactly where it was."""
    parts = _WHITESPACE.split(text)
    # re.split with a capturing group alternates tokens (even indices) and whitespace runs (odd);
    # a token slot is empty only at a string that starts or ends with whitespace.
    slots = [i for i in range(0, len(parts), 2) if parts[i]]
    new, counts = transform_tokens([parts[i] for i in slots], quotes=quotes, apostrophes=apostrophes,
                                   ellipsis=ellipsis, dashes=dashes)
    for i, token in zip(slots, new, strict=True):
        parts[i] = token
    return "".join(parts), counts


def _dashes(token: str, counts: Counter) -> str:
    if set(token) == {"-"}:
        counts["em_dash"] += 1
        return EM_DASH
    token, runs = _HYPHEN_RUN.subn(EM_DASH, token)
    token, by_quote = _HYPHEN_BY_QUOTE.subn(EM_DASH, token)
    counts["em_dash"] += runs + by_quote
    return token


def _quotes(token: str, state: dict, counts: Counter, *, quotes: bool, apostrophes: bool) -> str:
    out: list[str] = []
    last = len(token) - 1
    for i, ch in enumerate(token):
        if (ch == '"' and quotes) or (ch == "'" and apostrophes):
            prev = out[-1] if out else None
            nxt = token[i + 1] if i < last else None
            at_open = prev is None or prev in _OPENERS
            if ch == '"':
                # A mark alone as a token cannot be read from its neighbours, so it toggles.
                opening = at_open and (nxt is not None or not state["double"])
                out.append(LEFT_DOUBLE if opening else RIGHT_DOUBLE)
                state["double"] = opening
                counts["double_open" if opening else "double_close"] += 1
            else:
                opening = False
                if at_open:
                    if nxt is None:
                        opening = not state["single"]
                    elif not nxt.isdigit():
                        word = _LETTERS.match(token, i + 1)
                        opening = word is not None and word.group(0).lower() not in _ELISIONS
                out.append(LEFT_SINGLE if opening else RIGHT_SINGLE)
                if opening:
                    state["single"] = True
                elif nxt is None or not nxt.isalnum():
                    # Only a mark that ends a word can close a quotation; one inside "don't" cannot.
                    state["single"] = False
                counts["single_open" if opening else "single_close_or_apostrophe"] += 1
        else:
            out.append(ch)
    return "".join(out)
