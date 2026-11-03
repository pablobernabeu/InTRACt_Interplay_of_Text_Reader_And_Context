"""Frozen rule segmenters that the segmentation checks score against.

Outcome-neutral quality checks: "The second requires English SaT to reach an F1 of .95 against a
frozen rule segmenter on the served English texts." The rule is SEG-3, the English rule segmenter
of the benchmark (``presub/translated_union/scripts/tu_common.segment``, verbatim from
``rigour/segmentation/scripts/mt_more.py`` and ``verify-seg/scripts/ts_gold.py``). On the 20
public stories of the benchmark, SaT agreed with it on all 382 boundaries (S3). Feature plan v3
states what it encodes: "A quotation and its speech verb form one sentence."

``internal_orth_ends`` is the benchmark's frozen target-only gold rule
(``tu_common.internal_orth_ends``, verbatim from ``rigour/verify-segmentation/scripts/
ags_construct_eval.py``), "conservative for abbreviations, ordinals and initials" (S3). It scores
the union segmenter on the translated benchmark; English does not use it.

The logic is unchanged. The word lists and character sets now come from
``config/stages/seg_check.toml`` ([rule] and [orth_rule]); the tests pin them to the frozen values,
because changing one would change the reference that SaT is scored against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EnglishRule:
    """Constants of the frozen English rule segmenter (SEG-3)."""

    abbreviations: frozenset[str]
    tag_verbs: frozenset[str]
    terminal: str
    closing_quotes: str
    opening_quotes: str
    word_pattern: str
    conjunction: str
    max_tag_words: int
    tag_verb_window: int
    cand: re.Pattern = field(init=False, repr=False, compare=False)
    stop: re.Pattern = field(init=False, repr=False, compare=False)
    word: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        # SEG-3's candidate: a run of terminal marks, any closing quotes, then whitespace (not consumed).
        object.__setattr__(self, "cand", re.compile(
            "[" + re.escape(self.terminal) + "]+[" + re.escape(self.closing_quotes) + "]*(?=\\s)"))
        object.__setattr__(self, "stop", re.compile(
            "[" + re.escape(self.terminal) + "]|[" + re.escape(self.opening_quotes) + "]"))
        object.__setattr__(self, "word", re.compile(self.word_pattern))

    @classmethod
    def from_config(cls, rule_cfg: dict) -> EnglishRule:
        """Build the rule from the [rule] table of config/stages/seg_check.toml."""
        return cls(abbreviations=frozenset(rule_cfg["abbreviations"]), tag_verbs=frozenset(rule_cfg["tag_verbs"]),
                   terminal=rule_cfg["terminal"], closing_quotes=rule_cfg["closing_quotes"],
                   opening_quotes=rule_cfg["opening_quotes"], word_pattern=rule_cfg["word_pattern"],
                   conjunction=rule_cfg["conjunction"], max_tag_words=int(rule_cfg["max_tag_words"]),
                   tag_verb_window=int(rule_cfg["tag_verb_window"]))


def speech_tag_follows(rest: str, rule: EnglishRule) -> bool:
    """Whether the text after a closing quotation mark opens a speech tag ("... ," she said), which
    keeps the quotation and its speech verb in one sentence."""
    if not rest:
        return False
    if rest[0].islower():
        return True
    m = rule.stop.search(rest)
    clause = rest[: m.start()] if m else rest
    if m and m.group(0) in rule.opening_quotes:
        return False
    words = rule.word.findall(clause)
    if rule.conjunction in clause:
        return False
    return 0 < len(words) <= rule.max_tag_words and any(w.lower() in rule.tag_verbs
                                                         for w in words[: rule.tag_verb_window])


def _strip(text: str, a: int, b: int) -> tuple[int, int]:
    # str.strip() on text[a:b], as offsets
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b


def rule_spans(text: str, rule: EnglishRule) -> list[tuple[int, int]]:
    """SEG-3's sentences as ``[start, end)`` spans of ``text``, surrounding whitespace trimmed.

    ``[text[a:b] for a, b in rule_spans(text, rule)]`` equals the benchmark's ``segment(text)``.
    """
    spans, start = [], 0
    for m in rule.cand.finditer(text):
        end = m.end()
        tok_start = text.rfind(" ", 0, m.start()) + 1
        if text[tok_start:end] in rule.abbreviations:
            continue
        rest = text[end:].lstrip()
        if not rest:
            continue
        closes_quote = m.group(0)[-1] in rule.closing_quotes
        if closes_quote and speech_tag_follows(rest, rule):
            continue
        if not closes_quote and rest[0].islower():
            continue
        spans.append(_strip(text, start, end))
        start = end
    a, b = _strip(text, start, len(text))
    if b > a:
        spans.append((a, b))
    return spans


def rule_sentences(text: str, rule: EnglishRule) -> list[str]:
    """SEG-3's sentences as strings, as the benchmark's ``segment(text)`` returned them."""
    return [text[a:b] for a, b in rule_spans(text, rule)]


@dataclass(frozen=True)
class OrthRule:
    """Constants of the frozen target-only gold rule (``internal_orth_ends``)."""

    terminal: frozenset[str]
    closers: frozenset[str]
    openers: frozenset[str]
    cjk_terminal: frozenset[str]
    max_abbreviation_letters: int

    @classmethod
    def from_config(cls, cfg: dict) -> OrthRule:
        """Build the rule from the [orth_rule] table of config/stages/seg_check.toml."""
        return cls(terminal=frozenset(cfg["terminal"]), closers=frozenset(cfg["closers"]),
                   openers=frozenset(cfg["openers"]), cjk_terminal=frozenset(cfg["cjk_terminal"]),
                   max_abbreviation_letters=int(cfg["max_abbreviation_letters"]))


def internal_orth_ends(text: str, spans, rule: OrthRule, cjk: bool) -> set[int]:
    """Orthographic sentence ends (last non-space character) strictly inside each rendering span.

    ``cjk`` replaces the benchmark's test of a FLORES code starting with "zho". The semicolon stays a
    terminal mark in every language, as frozen.
    """
    out = set()
    for a, b in spans:
        k = a
        while k < b - 1:
            ch = text[k]
            if ch in rule.terminal or ch in rule.cjk_terminal:
                j = k + 1
                while j < b and text[j] in rule.closers:
                    j += 1
                end = j - 1
                if cjk:
                    # The frozen rule had two branches here, for a full-width mark followed by a space and
                    # by anything else; both add the end, so they reduce to this one condition.
                    if ch in rule.cjk_terminal and j < b:
                        out.add(end)
                    k = j
                    continue
                if j < b and text[j].isspace():
                    jj = j
                    while jj < b and text[jj].isspace():
                        jj += 1
                    if jj < b:
                        c2 = text[jj]
                        ok = c2.isdigit() or c2 in rule.openers or (
                            c2.isalpha() and (c2.isupper() or c2.upper() == c2.lower()))
                        if ok and ch == ".":
                            before = text[a:k].split()
                            w = before[-1] if before else ""
                            letters = sum(c.isalpha() for c in w)
                            if any(c.isdigit() for c in w) or "." in w or "/" in w or (
                                    letters <= rule.max_abbreviation_letters):
                                ok = False
                        if ok:
                            out.add(end)
                k = j
                continue
            k += 1
    return out
