"""Causal and contrastive connective densities in English, two anchors of ReferentialContinuity.

S3, connective induction: "The causal anchors are because, therefore, thus and clause-initial so, and the
contrastive anchors are but, however, although, though, even though, even if and whereas." S3, connective
density row: "Connectives per 100 words of the outcome's unit, counting the cues a reader met in the version
served". The registered log(1 + x) transform is applied at the dimension reduction, so densities stay raw here.
The density without "so" serves the registered sensitivity analysis "The inventory induced without the English
anchor so" (same row).

English is the source language, so its inventory is the anchor list itself. The translations' induced
inventories are matched with the same `Matcher` after acceptance.

Promoted from nonnative/discourse/scripts/conn_lib.py (Matcher: longest match first, then ordered discontinuous
entries) and rigour/discourse/scripts/rc_features.py (count_conn: lower-cased forms with the typographic
apostrophe folded, contrastive before causal, the clause-initial rule for "so").

Two rules are defaults pending the Feature Specification, each behind a switch in
config/stages/features_discourse.toml: rc_features.py's operationalisation of "clause-initial", and the detection
of the expression "not X but Y", which S3's hygiene rule blocks ("Hygiene rules block pronouns, finite verbs,
names, numerals and the expressions and so on and not X but Y") but which no benchmark implemented.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from intract_features.features.overlap import base_relation

Word = Mapping[str, Any]
Form = tuple  # a contiguous form is a tuple of tokens; a discontinuous one a tuple of such tuples

CAUSAL = "causal"
CONTRASTIVE = "contrastive"


def normalise_form(form: str) -> str:
    """rc_features.py: lower case, with the typographic apostrophe folded to the ASCII one."""
    return form.lower().replace("’", "'")


class Matcher:
    """Longest-match-first contiguous matching plus ordered discontinuous entries (conn_lib.Matcher).

    Contiguous forms are matched left to right, the longest form first at each position, and a matched token is
    never reused. Discontinuous forms are then matched in sorted order on the tokens left over.
    """

    def __init__(self, forms: Iterable[Form]):
        self.cont: set[tuple[str, ...]] = set()
        self.disc: set[tuple[tuple[str, ...], ...]] = set()
        for f in forms:
            if f and isinstance(f[0], tuple):
                self.disc.add(f)
            elif f:
                self.cont.add(f)
        self.maxlen = max([len(c) for c in self.cont] + [1])

    def match(self, words: Sequence[str]) -> list[tuple[Form, list[int]]]:
        """Matches in `words` (already normalised) as (form, token indices)."""
        used = [False] * len(words)
        out: list[tuple[Form, list[int]]] = []
        i = 0
        while i < len(words):
            hit = None
            for length in range(min(self.maxlen, len(words) - i), 0, -1):
                t = tuple(words[i:i + length])
                if t in self.cont and not any(used[i:i + length]):
                    hit = (t, list(range(i, i + length)))
                    break
            if hit:
                out.append(hit)
                for k in hit[1]:
                    used[k] = True
                i = hit[1][-1] + 1
            else:
                i += 1
        for parts in sorted(self.disc):
            pos, found = 0, []
            for p in parts:
                length, ok = len(p), False
                while pos + length <= len(words):
                    if tuple(words[pos:pos + length]) == p and not any(used[pos:pos + length]):
                        found.extend(range(pos, pos + length))
                        pos += length
                        ok = True
                        break
                    pos += 1
                if not ok:
                    found = None
                    break
            if found:
                out.append((parts, found))
                for k in found:
                    used[k] = True
        return out


def _forms(entries: Iterable[str]) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(normalise_form(t) for t in e.split()) for e in entries)


@dataclass(frozen=True)
class AnchorSpec:
    """The English anchors and the rules that qualify two of them, read from the stage configuration."""

    causal: tuple[tuple[str, ...], ...]
    contrastive: tuple[tuple[str, ...], ...]
    clause_initial: tuple[tuple[str, ...], ...]  # causal only where clause-initial ("so")
    clause_boundary_before: frozenset[str]
    sentence_initial_quotes: frozenset[str]
    blocked_before: frozenset[str]  # the token after a clause-initial anchor that disqualifies it
    block_not_x_but_y: bool
    not_but_forms: frozenset[str]
    negators: frozenset[str]
    clause_subject_relations: frozenset[str]

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any]) -> AnchorSpec:
        """Build the spec from the [connectives] table of config/stages/features_discourse.toml."""
        norm = frozenset
        return cls(
            causal=_forms(cfg["causal"]),
            contrastive=_forms(cfg["contrastive"]),
            clause_initial=_forms(cfg["causal_clause_initial"]),
            clause_boundary_before=norm(normalise_form(x) for x in cfg["clause_boundary_before"]),
            sentence_initial_quotes=norm(normalise_form(x) for x in cfg["sentence_initial_quotes"]),
            blocked_before=norm(normalise_form(x) for x in cfg["clause_initial_blocked_before"]),
            block_not_x_but_y=bool(cfg["block_not_x_but_y"]),
            not_but_forms=norm(normalise_form(x) for x in cfg["not_x_but_y_forms"]),
            negators=norm(normalise_form(x) for x in cfg["negators"]),
            clause_subject_relations=frozenset(cfg["clause_subject_relations"]),
        )

    def labels(self) -> dict[tuple[str, ...], str]:
        """Form to class; a form listed in two classes is a configuration error."""
        out: dict[tuple[str, ...], str] = {}
        for cls_name, forms in ((CONTRASTIVE, self.contrastive), (CAUSAL, self.causal + self.clause_initial)):
            for f in forms:
                if f in out and out[f] != cls_name:
                    raise ValueError(f"connective {' '.join(f)!r} is listed as both causal and contrastive")
                out[f] = cls_name
        return out


@dataclass
class SentenceCounts:
    """Anchor hits in one sentence. `clause_initial` counts the hits of "so", which are included in `causal`."""

    causal: int = 0
    contrastive: int = 0
    clause_initial: int = 0
    not_x_but_y_blocked: int = 0


def is_clause_initial(i: int, forms: Sequence[str], spec: AnchorSpec) -> bool:
    """rc_features.count_conn's rule for "so" at position i of a sentence's normalised forms.

    Clause-initial means sentence-initial, second after a sentence-initial quotation mark, or after a comma,
    semicolon, colon, dash or "and"; and the anchor is not followed by a blocked token ("so that", "so on",
    "so forth", "so far", "so much", "so many", or an auxiliary or modal, as in "so did I").
    """
    nxt = forms[i + 1] if i + 1 < len(forms) else ""
    if nxt in spec.blocked_before:
        return False
    if i == 0 or forms[i - 1] in spec.clause_boundary_before:
        return True
    return i == 1 and forms[0] in spec.sentence_initial_quotes


def is_not_x_but_y(i: int, words: Sequence[Word], spec: AnchorSpec) -> bool:
    """True where word i ("but") coordinates the corrective expression "not X but Y" (PENDING operationalisation).

    The word must be the cc dependent of a conjunct Y whose head conjunct X carries a negator ("not", "n't") as
    an advmod dependent, directly or under another advmod ("not only X but also Y"); and Y must have no subject of
    its own. A Y with its own subject is a coordinated clause ("I did not want to go, but I went"), the ordinary
    contrastive use, which stays counted.
    """
    w = words[i]
    if base_relation(w["deprel"]) != "cc":
        return False
    by_id = {x["id"]: x for x in words}
    kids: dict[int, list[Word]] = defaultdict(list)
    for x in words:
        kids[x["head"]].append(x)
    y = by_id.get(w["head"])
    if y is None or base_relation(y["deprel"]) != "conj":
        return False
    x = by_id.get(y["head"])
    if x is None:
        return False
    if any(base_relation(c["deprel"]) in spec.clause_subject_relations for c in kids.get(y["id"], ())):
        return False

    def negated(node: Word, depth: int) -> bool:
        for c in kids.get(node["id"], ()):
            if base_relation(c["deprel"]) == "advmod":
                if normalise_form(c["form"]) in spec.negators:
                    return True
                if depth == 0 and negated(c, 1):
                    return True
        return False

    return negated(x, 0)


class ConnectiveCounter:
    """Counts the registered anchors in the syntactic words of a sentence."""

    def __init__(self, spec: AnchorSpec):
        self.spec = spec
        self.label = spec.labels()
        self.clause_initial = set(spec.clause_initial)
        self.matcher = Matcher(self.label)

    def count(self, words: Sequence[Word]) -> SentenceCounts:
        """Hits in one sentence; `words` are its syntactic words in order."""
        forms = [normalise_form(w["form"]) for w in words]
        out = SentenceCounts()
        for form, idxs in self.matcher.match(forms):
            cls_name = self.label[form]
            if form in self.clause_initial:
                if not is_clause_initial(idxs[0], forms, self.spec):
                    continue
                out.clause_initial += 1
            if (self.spec.block_not_x_but_y and len(idxs) == 1 and forms[idxs[0]] in self.spec.not_but_forms
                    and is_not_x_but_y(idxs[0], words, self.spec)):
                out.not_x_but_y_blocked += 1
                continue
            if cls_name == CAUSAL:
                out.causal += 1
            else:
                out.contrastive += 1
        return out


def per_words(count: int, n_words: int, per: float) -> float | None:
    """A count per `per` words of the outcome's unit, or None for a text without words."""
    return per * count / n_words if n_words else None
