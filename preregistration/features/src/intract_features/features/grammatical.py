"""Grammatical features of one parse: the registered counting rules, promoted from gfeat.py.

gfeat.py (error_model, SHA-256 5c4f4d9c, 23 October 2026) was the single implementation of the per-sentence
counts that the error model, the translated benchmark and the third-parser pilot shared, so kappa_U, Var_D and
Var_Seg describe the same anchors as the features computed here. Its rules are kept exactly:

- Punctuation: a word whose base relation is punct is removed and the remaining positions are renumbered (Liu,
  2008); a dependent of a punctuation word is reattached to that word's nearest non-punctuation ancestor, so no
  dependency is lost. The part-of-speech tag is not consulted.
- Clauses: the root and the main relations are main clauses, the subordinate relations are subordinate clauses,
  and a predicate conjunct of a clause head inherits its type. Open clausal complements are not clauses (qmd
  Materials).
- Direct speech (gap G6): a ccomp or csubj head inside direct speech counts as main. By default direct speech is
  still gfeat's approximation, quotation-mark spans read independently of tokenisation (a mark at the start or end
  of a word's form acts as a standalone mark just before or after that word); the "detector_spans" rule takes it
  from the registered dialogue detector instead, and which of the two is registered awaits the specification.

Removed in promotion: the noun-phrase depth variants and the xcomp-as-subordinate variant, which no registered
quantity uses (noun-phrase elaboration replaced depth, S3), and gfeat's own word counts, which the registered word
function replaces (Measures). Every relation set comes from config/stages/features_gramlex.toml.

Sentences are gfeat-shaped dicts: ``words`` (id, form, lemma, upos, head, deprel), ``tokens`` (surface forms) and
``token_words`` (the word ids of each surface token). `parse_conllu` reads any CoNLL-U into that shape, UD gold
included; the pipeline's parse artefacts are read with intract_features.parse.read_conllu, their producers' reader.
"""

from __future__ import annotations

import gzip
import math
import unicodedata
from bisect import bisect_right
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

SPEECH_RULES = ("quote_marks", "none", "detector_spans")
COUNT_KEYS = ("n", "dist", "ndep", "main", "sub", "open", "speech_main", "nouns", "npe_mods")
NAN = float("nan")


@dataclass(frozen=True)
class GrammarRules:
    """The counting rules, read once from the [grammatical] table of the stage configuration."""

    subordinate: frozenset[str]
    main: frozenset[str]
    open: frozenset[str]
    conjunct: str
    predicate_upos: frozenset[str]
    predicate_dependents: frozenset[str]
    punct: str
    elaboration: frozenset[str]
    elaboration_heads: frozenset[str]
    logit_offset: float
    speech_rule: str
    speech_main: frozenset[str]
    quote_marks: frozenset[str]

    @classmethod
    def from_config(cls, stage_cfg: Mapping) -> GrammarRules:
        """Build the rules from the stage configuration (the parsed features_gramlex.toml)."""
        g = stage_cfg["grammatical"]
        s = g["speech"]
        if s["rule"] not in SPEECH_RULES:
            raise ValueError(f"grammatical.speech.rule must be one of {SPEECH_RULES}, not {s['rule']!r}")
        return cls(subordinate=frozenset(g["subordinate_relations"]), main=frozenset(g["main_relations"]),
                   open=frozenset(g["open_relations"]), conjunct=g["conjunct_relation"],
                   predicate_upos=frozenset(g["predicate_upos"]),
                   predicate_dependents=frozenset(g["predicate_dependents"]), punct=g["punct_relation"],
                   elaboration=frozenset(g["elaboration_relations"]),
                   elaboration_heads=frozenset(g["elaboration_head_upos"]),
                   logit_offset=float(g["empirical_logit_offset"]), speech_rule=s["rule"],
                   speech_main=frozenset(s["main_relations"]), quote_marks=frozenset(s["quote_marks"]))


def base(relation: str) -> str:
    """The universal relation before any subtype (``acl:relcl`` -> ``acl``)."""
    return relation.split(":")[0]


# ---------------------------------------------------------------- CoNLL-U


def _new_sentence() -> dict:
    return {"sent_id": None, "newdoc": None, "text": None, "words": [], "tokens": [], "token_words": []}


def parse_conllu(lines: Iterable[str]) -> Iterator[dict]:
    """Sentences of a CoNLL-U stream.

    Each sentence is a dict with ``sent_id``, ``newdoc`` (the id of a document it opens, else None), ``text``,
    ``words`` (syntactic words after multi-word-token expansion: id, form, lemma, upos, head, deprel), ``tokens``
    (surface forms, a multi-word token once) and ``token_words`` (the word ids of each surface token). Empty nodes
    are skipped, as in gfeat.py. A block holding comments but no word lines is still a sentence, as the parse
    artefacts write a sentence the parser returned nothing for.
    """
    cur, seen, mwt_end = _new_sentence(), False, 0
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line:
            if seen:
                yield cur
            cur, seen, mwt_end = _new_sentence(), False, 0
            continue
        if line.startswith("#"):
            key, sep, value = line[1:].partition("=")
            key = key.strip()
            if sep and key == "newdoc id":
                cur["newdoc"] = value.strip()
            elif sep and key == "sent_id":
                cur["sent_id"] = value.strip()
                seen = True
            elif sep and key == "text":
                cur["text"] = value[1:] if value.startswith(" ") else value
                seen = True
            continue
        cols = line.split("\t")
        if len(cols) < 8:
            raise ValueError(f"malformed CoNLL-U line: {line!r}")
        seen = True
        tid = cols[0]
        if "-" in tid:
            a, b = (int(x) for x in tid.split("-"))
            mwt_end = b
            cur["tokens"].append(cols[1])
            cur["token_words"].append(tuple(range(a, b + 1)))
            continue
        if "." in tid:
            continue
        i = int(tid)
        # A head written as "_" is read as the root, as translated_union's reader did; parsers write integers.
        head = int(cols[6]) if cols[6] not in ("_", "") else 0
        cur["words"].append({"id": i, "form": cols[1], "lemma": cols[2], "upos": cols[3], "head": head,
                             "deprel": cols[7]})
        if i > mwt_end:
            cur["tokens"].append(cols[1])
            cur["token_words"].append((i,))
    if seen:
        yield cur


def read_conllu(path: Path) -> list[dict]:
    """All sentences of a CoNLL-U file, plain or gzipped (see parse_conllu)."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return list(parse_conllu(fh))


def align_tokens(text: str, forms: Sequence[str]) -> tuple[list[tuple[int, int] | None], str]:
    """[start, end) offsets in `text` of each surface token, and how they were found.

    Tokens are matched on non-whitespace characters, as rel2.align_eval matched gold and parsed tokens, so a
    token keeps its place even where a tokeniser normalised a character. Status: "exact" when the characters
    agree, "length" when only their number agrees, "scaled" when the numbers differ and positions are scaled
    proportionally (an approximation the stage counts), "empty" when the text has no non-space character. A token
    with no non-space character gets None.
    """
    positions = [i for i, ch in enumerate(text) if not ch.isspace()]
    counts = [sum(1 for ch in f if not ch.isspace()) for f in forms]
    total, size = sum(counts), len(positions)
    if not positions or total == 0:
        return [None] * len(forms), "empty"
    if total == size:
        same = "".join(ch for f in forms for ch in f if not ch.isspace()) == "".join(text[i] for i in positions)
        status = "exact" if same else "length"
    else:
        status = "scaled"
    spans: list[tuple[int, int] | None] = []
    c = 0
    for n in counts:
        if n == 0:
            spans.append(None)
            continue
        if status == "scaled":
            # integer arithmetic, so the scaled positions cannot depend on floating-point rounding
            a = min(c * size // total, size - 1)
            b = min(max((c + n) * size // total - 1, a), size - 1)
        else:
            a, b = c, c + n - 1
        spans.append((positions[a], positions[b] + 1))
        c += n
    return spans, status


# ---------------------------------------------------------------- per-sentence counts (gfeat.py)


def sent_struct(sent: Mapping, punct: str) -> tuple[dict, list[dict], dict, dict, dict]:
    """The punctuation-free tree of a sentence: (words by id, kept words, renumbered positions, heads, children).

    A word whose base relation is `punct` is removed; a head that is punctuation is replaced by its nearest
    non-punctuation ancestor (the root, 0, if there is none).
    """
    words = sent["words"]
    byid = {w["id"]: w for w in words}
    removed = {w["id"] for w in words if base(w["deprel"]) == punct}
    kept = [w for w in words if w["id"] not in removed]
    pos = {w["id"]: k + 1 for k, w in enumerate(kept)}

    def head(wid: int) -> int:
        hd = byid[wid]["head"]
        while hd != 0 and hd in removed:
            hd = byid[hd]["head"]
        return hd

    heads = {w["id"]: head(w["id"]) for w in kept}
    kids: dict[int, list[int]] = {w["id"]: [] for w in kept}
    for w in kept:
        if heads[w["id"]] != 0:
            kids[heads[w["id"]]].append(w["id"])
    return byid, kept, pos, heads, kids


def quote_edges(form: str, marks: frozenset[str]) -> tuple[int, int, bool]:
    """(marks at the start, marks at the end, whether a body remains) of a form.

    A form made only of marks has no body, and all its marks count as leading.
    """
    i = 0
    while i < len(form) and form[i] in marks:
        i += 1
    j = len(form)
    while j > i and form[j - 1] in marks:
        j -= 1
    return i, len(form) - j, j > i


def speech_span(words: Sequence[Mapping], marks: frozenset[str]) -> set[int]:
    """Ids of the words strictly between paired quotation marks, the marks paired in order of occurrence.

    Each word unfolds into its leading marks, itself and its trailing marks, so a mark left attached to a word acts
    exactly as the same mark split off as a token beside it, and a mark inside a form is not read (gfeat.py).
    """
    seq: list[int | None] = []  # None for a mark, a word id otherwise, in text order
    for w in words:
        lead, trail, body = quote_edges(w["form"], marks)
        seq += [None] * lead + ([w["id"]] if body else []) + [None] * trail
    inside: set[int] = set()
    open_at = None
    for k, x in enumerate(seq):
        if x is None:
            if open_at is None:
                open_at = k
            else:
                inside.update(y for y in seq[open_at + 1:k] if y is not None)
                open_at = None
    return inside


def first_letter_or_digit(text: str, span: tuple[int, int]) -> int:
    """Offset of the first letter (not a modifier letter) or digit in text[span], else the span's start.

    The registered word function anchors a word the same way (text/words.py), and S3 places a word in direct
    speech by "its first letter".
    """
    for i in range(span[0], span[1]):
        cat = unicodedata.category(text[i])
        if cat[0] == "N" or (cat[0] == "L" and cat != "Lm"):
            return i
    return span[0]


def speech_ids_from_mask(text: str, token_spans: Sequence[tuple[int, int] | None],
                         token_words: Sequence[Sequence[int]], mask: Sequence[bool]) -> set[int]:
    """Word ids whose surface token's first letter or digit lies inside direct speech (gap G6, the detector route).

    `mask` flags each character of `text` that the registered dialogue detector puts inside direct speech
    (features.dialogue.speech_mask), and `token_spans` are offsets into the same text.
    """
    inside: set[int] = set()
    for span, ids in zip(token_spans, token_words, strict=True):
        if span is not None and span[1] > span[0] and mask[first_letter_or_digit(text, span)]:
            inside.update(ids)
    return inside


def sentence_counts(sent: Mapping, rules: GrammarRules, *, speech_ids: set[int] | None = None) -> dict[str, int]:
    """Counts of one sentence under the registered rules.

    Keys: n (non-punctuation words), dist and ndep (summed dependency distance and its dependencies), main, sub and
    open (clause heads; open clausal complements are counted apart and enter no clause count), speech_main (heads
    moved from subordinate to main by the direct-speech rule), nouns and npe_mods (common nouns and their
    elaborating dependents). `speech_ids` supplies direct speech under the "detector_spans" rule.
    """
    byid, kept, pos, heads, kids = sent_struct(sent, rules.punct)
    dist = sum(abs(pos[w["id"]] - pos[heads[w["id"]]]) for w in kept if heads[w["id"]] != 0)
    ndep = sum(1 for w in kept if heads[w["id"]] != 0)
    if rules.speech_rule == "quote_marks":
        speech = speech_span(sent["words"], rules.quote_marks)
    elif rules.speech_rule == "none":
        speech = set()
    else:
        if speech_ids is None:
            raise ValueError("the detector_spans speech rule needs the detector's speech_ids")
        speech = speech_ids

    def predicate(wid: int) -> bool:
        if byid[wid]["upos"] in rules.predicate_upos:
            return True
        return any(base(byid[c]["deprel"]) in rules.predicate_dependents for c in kids[wid])

    # Clause types are assigned from the root downwards (breadth first), so a conjunct sees its head's type.
    order: list[int] = []
    frontier = [w["id"] for w in kept if heads[w["id"]] == 0]
    while frontier:
        order.extend(frontier)
        frontier = [c for x in frontier for c in kids[x]]
    ctype: dict[int, str] = {}
    nspeech = 0
    for wid in order:
        b = base(byid[wid]["deprel"])
        if heads[wid] == 0 or b in rules.main:
            ctype[wid] = "main"
        elif b in rules.subordinate:
            if b in rules.speech_main and wid in speech:
                ctype[wid] = "main"
                nspeech += 1
            else:
                ctype[wid] = "sub"
        elif b in rules.open:
            ctype[wid] = "open"
        elif b == rules.conjunct and ctype.get(heads[wid]) in ("main", "sub") and predicate(wid):
            ctype[wid] = ctype[heads[wid]]
    types = list(ctype.values())
    nouns = [w["id"] for w in kept if w["upos"] in rules.elaboration_heads]
    npe_mods = sum(1 for v in nouns for c in kids[v] if base(byid[c]["deprel"]) in rules.elaboration)
    return {"n": len(kept), "dist": dist, "ndep": ndep, "main": types.count("main"), "sub": types.count("sub"),
            "open": types.count("open"), "speech_main": nspeech, "nouns": len(nouns), "npe_mods": npe_mods}


# ---------------------------------------------------------------- text-level features


def sum_counts(counts: Iterable[Mapping[str, int]]) -> dict[str, int]:
    """Sentence counts summed over a text, with `sentences`, the sentences that hold a non-punctuation word.

    A sentence with no such word enters no denominator, as in gfeat.py.
    """
    tot = dict.fromkeys(COUNT_KEYS, 0)
    tot["sentences"] = 0
    for c in counts:
        for k in COUNT_KEYS:
            tot[k] += c[k]
        tot["sentences"] += c["n"] > 0
    return tot


def parse_features(tot: Mapping[str, int], rules: GrammarRules) -> dict[str, float]:
    """The four parse-based anchors of one text from its summed counts; NaN where a denominator is zero.

    Ratios of sums pool over the text (plan v3: "pooled over the text"), so long sentences weigh by their size.
    """
    m, o = tot["sentences"], rules.logit_offset
    return {
        "mean_dependency_distance": tot["dist"] / tot["ndep"] if tot["ndep"] else NAN,
        "clauses_per_sentence": (tot["main"] + tot["sub"]) / m if m else NAN,
        "subordination": math.log((tot["sub"] + o) / (tot["main"] + o)) if m else NAN,
        "noun_phrase_elaboration": tot["npe_mods"] / tot["nouns"] if tot["nouns"] else NAN,
    }


def parse_diagnostics(tot: Mapping[str, int]) -> dict[str, float]:
    """Descriptive counts of one parse of a text: sentences, words, clauses, the raw ratio, the xcomp rate (per
    1,000 non-punctuation words, as gfeat.py reported it) and the heads the direct-speech rule moved."""
    ratio = tot["sub"] / tot["main"] if tot["main"] else NAN
    return {"sentences": tot["sentences"], "syntactic_words": tot["n"], "main_clauses": tot["main"],
            "subordinate_clauses": tot["sub"], "subordinate_main_ratio": ratio,
            "xcomp_per_1000_words": 1000 * tot["open"] / max(1, tot["n"]), "speech_main_heads": tot["speech_main"]}


# ---------------------------------------------------------------- mean sentence length (registered words)


def words_per_sentence(anchors: Iterable[int], sentence_spans: Sequence[tuple[int, int]]) -> tuple[list[int], int]:
    """Words of the outcome's unit in each sentence, placed by their anchors, and how many fell in no sentence.

    Sentences are [start, end) spans in order and do not overlap, as the segmentation writes them. The anchor is
    the word's first letter or digit (text.words.Word.anchor) or its first character, by configuration.
    """
    starts = [s for s, _ in sentence_spans]
    counts = [0] * len(sentence_spans)
    outside = 0
    for a in anchors:
        k = bisect_right(starts, a) - 1
        if k >= 0 and a < sentence_spans[k][1]:
            counts[k] += 1
        else:
            outside += 1
    return counts, outside


def mean_sentence_length(counts: Sequence[int], count_empty: bool) -> float:
    """Registered words per sentence. It is not averaged over parsers (qmd Materials: "Each feature but sentence
    length is the unweighted mean of its values under two parsers"); a segment with no word enters the
    denominator only when `count_empty` is set."""
    used = list(counts) if count_empty else [c for c in counts if c > 0]
    return sum(used) / len(used) if used else NAN
