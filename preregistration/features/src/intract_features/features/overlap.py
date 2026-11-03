"""Referential overlap and anaphoric continuation, two measures of ReferentialContinuity.

Referential overlap is an anchor of ReferentialContinuity (Outcome-blind dimension reduction). Materials:
"Referential overlap is the proportion of adjacent sentence pairs sharing at least one content lemma in a
nominal position". S3, referential overlap row: "a content lemma is in a nominal position when its universal
part-of-speech tag is NOUN or PROPN, or X in Arabic, whose treebank tags names X".

Anaphoric continuation is the registered sensitivity variant (S3, same row): "Anaphoric continuation, which
also counts a pair as continuous when the next sentence's main clause has a third-person pronoun subject or,
where the dropped-subject gate is passed, a dropped one." The dropped-subject clause "can apply only in the
eight null-subject languages" (S3, Validation without human annotation), so it has no English branch here.

Promoted from presub/translated_union/scripts/tu6_features.py (refov), presub/error_model/scripts/em_counts.py
and lexrules.overlap_key (the adjacent-pair flags and the lemma key) and rigour/discourse/scripts/rc_features.py
(ana_cont and main_subject_pron3).

A sentence is a sequence of syntactic words, each a mapping with the CoNLL-U fields id, form, lemma, upos,
feats, head and deprel, with multi-word token ranges and empty nodes already removed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from typing import Any

Word = Mapping[str, Any]


def base_relation(deprel: str) -> str:
    """Universal part of a dependency relation: "nsubj:pass" gives "nsubj"."""
    return deprel.split(":")[0]


def parse_feats(feats: str | None) -> dict[str, str]:
    """The CoNLL-U FEATS column as a dict; "_" or an empty column gives an empty dict."""
    if not feats or feats == "_":
        return {}
    out = {}
    for item in feats.split("|"):
        name, sep, value = item.partition("=")
        if sep:
            out[name] = value
    return out


def lemma_or_form(word: Word, use_form: bool = False) -> str:
    """The word's lemma, or its form where the lemma is missing or the language's lemma is its form.

    lexrules.overlap_key takes the form in Chinese and Thai and wherever the lemma column is "_" or empty
    (S3: "Stanza's Thai package also has no lemmatiser, so a Thai lemma is its surface form").
    """
    lemma = word.get("lemma") or "_"
    if use_form or lemma == "_":
        return word["form"]
    return lemma


def nominal_keys(words: Iterable[Word], nominal_upos: Collection[str], key: Callable[[Word], str]) -> frozenset[str]:
    """Keys of the words in a nominal position (UPOS in `nominal_upos`), for one sentence."""
    return frozenset(key(w) for w in words if w["upos"] in nominal_upos)


def adjacent_pairs(parsed: Sequence[bool]) -> list[tuple[int, int]]:
    """Index pairs (k, k + 1) of adjacent sentences that both have a parse.

    A pair with an unparsed member is left out rather than scored as non-overlapping, since its overlap is unknown;
    the stage reports how many pairs it left out.
    """
    return [(k, k + 1) for k in range(len(parsed) - 1) if parsed[k] and parsed[k + 1]]


def overlap_flags(key_sets: Sequence[Collection[str]], pairs: Sequence[tuple[int, int]] | None = None) -> list[bool]:
    """One flag per adjacent sentence pair: True where the two sentences share a key (all pairs by default)."""
    if pairs is None:
        pairs = [(k, k + 1) for k in range(len(key_sets) - 1)]
    return [bool(set(key_sets[a]) & set(key_sets[b])) for a, b in pairs]


def share(flags: Sequence[bool]) -> float | None:
    """Proportion of True flags, or None for a text with no adjacent pair.

    A text of one sentence has no pair, so its overlap is undefined by construction, and the registered rule
    lists and omits such values instead of entering a constant (Outcome-blind dimension reduction).
    """
    return sum(flags) / len(flags) if flags else None


def _children(words: Sequence[Word]) -> dict[int, list[Word]]:
    kids: dict[int, list[Word]] = defaultdict(list)
    for w in words:
        kids[w["head"]].append(w)  # in word order, as rc_features.py builds its dependents lists
    return kids


def is_predicate(word: Word, kids: Mapping[int, Sequence[Word]], predicate_dependents: Collection[str]) -> bool:
    """rc_features.is_pred: a VERB or AUX, or a word with a subject, copula, auxiliary or expletive dependent."""
    if word["upos"] in ("VERB", "AUX"):
        return True
    return any(base_relation(c["deprel"]) in predicate_dependents for c in kids.get(word["id"], ()))


def main_clause_head(words: Sequence[Word], handover_upos: Collection[str], handover_relations: Collection[str],
                     predicate_dependents: Collection[str]) -> Word | None:
    """The head of the sentence's main clause, as rc_features.main_subject_pron3 finds it.

    The root heads the main clause, except that a root tagged CCONJ or PART (a fragment such as "And then.")
    hands it to its first predicate dependent attached by parataxis, conj or advcl.
    """
    roots = [w for w in words if w["head"] == 0]
    if not roots:
        return None
    kids = _children(words)
    head = roots[0]
    if head["upos"] in handover_upos:
        candidates = [d for d in kids.get(head["id"], ()) if base_relation(d["deprel"]) in handover_relations
                      and is_predicate(d, kids, predicate_dependents)]
        if candidates:
            head = candidates[0]
    return head


def has_third_person_pronoun_subject(words: Sequence[Word], subject_relations: Collection[str],
                                     handover_upos: Collection[str], handover_relations: Collection[str],
                                     predicate_dependents: Collection[str]) -> bool:
    """True where the main clause's subject is a third-person personal pronoun (rc_features.main_subject_pron3).

    The subject relation is matched in full ("nsubj" or "nsubj:pass" in rc_features.py), and a pronoun whose
    FEATS omit PronType or Person counts as personal or as third person, as in rc_features.py.
    """
    head = main_clause_head(words, handover_upos, handover_relations, predicate_dependents)
    if head is None:
        return False
    for dep in _children(words).get(head["id"], ()):
        if dep["deprel"] in subject_relations and dep["upos"] == "PRON":
            feats = parse_feats(dep.get("feats"))
            if feats.get("PronType", "Prs") == "Prs" and feats.get("Person", "3") == "3":
                return True
    return False


def continuation_flags(overlap: Sequence[bool], pronoun_subject: Sequence[bool],
                       pairs: Sequence[tuple[int, int]] | None = None) -> list[bool]:
    """Anaphoric continuation per adjacent pair: overlap, or a pronoun subject in the pair's second sentence.

    `pronoun_subject` has one flag per sentence, and `overlap` one per pair of `pairs` (all pairs by default).
    """
    if pairs is None:
        pairs = [(k, k + 1) for k in range(len(pronoun_subject) - 1)]
    if len(pairs) != len(overlap):
        raise ValueError(f"{len(overlap)} overlap flags for {len(pairs)} pairs")
    return [o or pronoun_subject[b] for o, (_, b) in zip(overlap, pairs, strict=True)]
