"""Tests of features.grammatical, features.parsemean and the features_gramlex stage.

The hand-built cases are those of error_model/scripts/test_gfeat_rules.py (part 1), ported unchanged. Its parts 1b
and 2 need UD files and the earlier gfeat.py, so they run as `models` tests when INTRACT_GFEAT_REPRO_DIRS (folders
of .conllu files, separated by os.pathsep) and INTRACT_OLD_GFEAT (the earlier gfeat.py) are set.
"""

import copy
import dataclasses
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path

import pytest

from intract_features import cli, records
from intract_features import config as config_mod
from intract_features.features import grammatical as G
from intract_features.features import parsemean
from intract_features.parse.long_units import LongUnitRule
from intract_features.stages import features_gramlex as stage
from intract_features.text import words as text_words

FEATURES = Path(__file__).resolve().parents[2]
GOLDEN = FEATURES / "tests" / "golden" / "features_gramlex"
CFG = config_mod.load(FEATURES / "config")
STAGE_CFG = CFG["stages"]["features_gramlex"]
RULES = G.GrammarRules.from_config(STAGE_CFG)
RULES_NONE = dataclasses.replace(RULES, speech_rule="none")
LONG = LongUnitRule.from_config(CFG, STAGE_CFG["parser_mean"]["long_unit_config_stage"])
KEYS = ["n", "dist", "ndep", "main", "sub", "open", "nouns", "npe_mods"]


def W(rows):
    """A gfeat-shaped sentence from (id, form, upos, head, deprel) rows."""
    return {"text": None, "tokens": [r[1] for r in rows], "token_words": [(r[0],) for r in rows],
            "words": [{"id": i, "form": f, "lemma": "_", "upos": u, "head": h, "deprel": d} for i, f, u, h, d in rows]}


def counts(rows, rules=RULES, **kw):
    return G.sentence_counts(W(rows), rules, **kw)


# ---------------------------------------------------------------- test_gfeat_rules.py, part 1

SAID = [(1, "He", "PRON", 2, "nsubj"), (2, "said", "VERB", 0, "root"), (3, "\u201C", "PUNCT", 5, "punct"),
        (4, "I", "PRON", 5, "nsubj"), (5, "came", "VERB", 2, "ccomp"), (6, "and", "CCONJ", 7, "cc"),
        (7, "saw", "VERB", 5, "conj"), (8, "\u201D", "PUNCT", 5, "punct")]


def test_ccomp_inside_quotation_marks_is_main_and_its_predicate_conjunct_follows():
    c = counts(SAID)
    assert (c["main"], c["sub"], c["speech_main"]) == (3, 0, 1)


def test_speech_rule_none_restores_the_earlier_count():
    c = counts(SAID, RULES_NONE)
    assert (c["main"], c["sub"], c["speech_main"]) == (1, 2, 0)


def test_without_marks_or_with_single_quotes_the_ccomp_stays_subordinate():
    noquote = [r for r in SAID if r[1] not in "\u201C\u201D"]
    c = counts(noquote)
    assert (c["main"], c["sub"]) == (1, 2)
    single = [(r[0], "\u2018" if r[1] == "\u201C" else "\u2019" if r[1] == "\u201D" else r[1], *r[2:]) for r in SAID]
    c = counts(single)
    assert (c["main"], c["sub"]) == (1, 2)


def test_dependent_of_punctuation_is_reattached_and_positions_renumbered():
    # word 3 (punct, head 2) has a dependent, word 4, which is reattached to 2; positions become 1 2 _ 3
    pun = [(1, "A", "DET", 2, "det"), (2, "dog", "NOUN", 0, "root"), (3, "-", "PUNCT", 2, "punct"),
           (4, "big", "ADJ", 3, "amod")]
    c = counts(pun)
    assert (c["n"], c["ndep"], c["dist"], c["npe_mods"]) == (3, 2, 2, 1)


SPLIT = [(1, "Ali", "PROPN", 7, "nsubj"), (2, '"', "PUNCT", 3, "punct"), (3, "Geldim", "VERB", 7, "ccomp"),
         (4, "ve", "CCONJ", 5, "cc"), (5, "g\u00F6rd\u00FCm", "VERB", 3, "conj"), (6, '"', "PUNCT", 3, "punct"),
         (7, "dedi", "VERB", 0, "root"), (8, ".", "PUNCT", 7, "punct")]
ATTACHED = [(1, "Ali", "PROPN", 5, "nsubj"), (2, '"Geldim', "VERB", 5, "ccomp"), (3, "ve", "CCONJ", 4, "cc"),
            (4, 'g\u00F6rd\u00FCm"', "VERB", 2, "conj"), (5, "dedi", "VERB", 0, "root"), (6, ".", "PUNCT", 5, "punct")]


def test_marks_attached_to_words_count_as_the_same_marks_split_off():
    # Turkish PUD as Stanza and UDPipe tokenise it ('"Son', 'sayida"', '."') against UD gold, which splits marks
    cs, ca = counts(SPLIT), counts(ATTACHED)
    assert (cs["main"], cs["sub"], cs["speech_main"]) == (3, 0, 1)
    assert ca == cs
    assert counts(ATTACHED, RULES_NONE)["sub"] == 2  # the rule is still what moves the count


def test_standalone_opening_mark_closed_by_a_mark_glued_to_the_full_stop():
    mixed = [(1, "Ali", "PROPN", 2, "nsubj"), (2, "dedi", "VERB", 0, "root"), (3, ":", "PUNCT", 2, "punct"),
             (4, '"', "PUNCT", 5, "punct"), (5, "Geldim", "VERB", 2, "ccomp"), (6, '."', "PUNCT", 5, "punct")]
    mixed_split = mixed[:5] + [(6, ".", "PUNCT", 5, "punct"), (7, '"', "PUNCT", 5, "punct")]
    cm, cms = counts(mixed), counts(mixed_split)
    assert (cm["main"], cm["sub"], cm["speech_main"]) == (2, 0, 1)
    assert cm == cms


@pytest.mark.parametrize("forms, inside", [
    (["a", 'b"', "c", 'd"', "e"], {3, 4}),  # a mark at the end of a word opens the span after that word
    (["\u201Ea\u201C", "b"], {1}),  # both marks on one word
    (['"', "a", 'sistemi"ne', "b", '"'], {2, 3, 4}),  # a mark inside a form is not read
    (['""', "a", '"'], set()),  # a form of two marks opens and closes; the last mark is unpaired
    (["\u2018a\u2019", "b"], set()),  # single quotes are not marks, attached or not
])
def test_speech_span_reads_marks_at_word_edges_only(forms, inside):
    words = [{"id": i + 1, "form": f} for i, f in enumerate(forms)]
    assert G.speech_span(words, RULES.quote_marks) == inside


# ---------------------------------------------------------------- further counting rules


def test_open_clausal_complement_is_not_a_clause_and_a_non_predicate_conjunct_is_not_one_either():
    rows = [(1, "She", "PRON", 2, "nsubj"), (2, "wanted", "VERB", 0, "root"), (3, "to", "PART", 4, "mark"),
            (4, "go", "VERB", 2, "xcomp"), (5, "and", "CCONJ", 6, "cc"), (6, "home", "NOUN", 2, "conj")]
    c = counts(rows)
    assert (c["main"], c["sub"], c["open"]) == (1, 0, 1)


def test_subtypes_parataxis_and_inherited_subordination():
    rows = [(1, "It", "PRON", 2, "nsubj"), (2, "rained", "VERB", 0, "root"), (3, "because", "SCONJ", 5, "mark"),
            (4, "clouds", "NOUN", 5, "nsubj"), (5, "came", "VERB", 2, "advcl"), (6, "and", "CCONJ", 7, "cc"),
            (7, "stayed", "VERB", 5, "conj"), (8, "that", "PRON", 9, "nsubj"), (9, "grew", "VERB", 4, "acl:relcl"),
            (10, "we", "PRON", 11, "nsubj"), (11, "ran", "VERB", 2, "parataxis")]
    c = counts(rows)
    assert (c["main"], c["sub"]) == (2, 3)  # rained, ran | came, stayed (inherits), grew (acl:relcl)
    assert (c["nouns"], c["npe_mods"]) == (1, 1)  # clouds, with its acl


def test_elaboration_counts_only_registered_relations_of_common_nouns():
    rows = [(1, "the", "DET", 3, "det"), (2, "big", "ADJ", 3, "amod"), (3, "dog", "NOUN", 0, "root"),
            (4, "Rex", "PROPN", 3, "appos"), (5, "two", "NUM", 3, "nummod"), (6, "Tom", "PROPN", 0, "root"),
            (7, "tall", "ADJ", 6, "amod")]
    c = counts(rows)
    assert (c["nouns"], c["npe_mods"]) == (1, 3)  # det left out; the PROPN head is not a common noun


def test_detector_spans_rule_needs_and_uses_speech_ids():
    det = dataclasses.replace(RULES, speech_rule="detector_spans")
    with pytest.raises(ValueError):
        counts(SAID, det)
    assert counts(SAID, det, speech_ids={5, 7})["speech_main"] == 1
    assert counts(SAID, det, speech_ids=set())["sub"] == 2


def test_speech_ids_from_the_detector_mask_read_each_token_by_its_first_letter():
    text = 'He said: "Go now," and ran.'
    mask = [10 <= i < 17 for i in range(len(text))]  # Go now, (the detector leaves the marks themselves out)
    tokens = [(0, 2), (3, 7), (7, 8), (9, 10), (10, 12), (13, 16), (16, 17), (17, 18), None]
    ids = [(1,), (2,), (3,), (4,), (5,), (6,), (7,), (8,), (9,)]
    assert G.speech_ids_from_mask(text, tokens, ids, mask) == {5, 6, 7}
    assert G.first_letter_or_digit('"Go', (0, 3)) == 1 and G.first_letter_or_digit("--", (0, 2)) == 0


def test_unknown_speech_rule_is_refused():
    cfg = copy.deepcopy(STAGE_CFG)
    cfg["grammatical"]["speech"]["rule"] = "guess"
    with pytest.raises(ValueError):
        G.GrammarRules.from_config(cfg)


def test_text_features_pool_counts_and_leave_undefined_values_undefined():
    tot = G.sum_counts([counts(SAID), counts([(1, ".", "PUNCT", 0, "punct")])])
    assert tot["sentences"] == 1  # the punctuation-only sentence enters no denominator
    f = G.parse_features(tot, RULES)
    assert f["clauses_per_sentence"] == 3
    assert f["subordination"] == pytest.approx(math.log(0.5 / 3.5))
    assert math.isnan(f["noun_phrase_elaboration"])  # no common noun
    empty = G.parse_features(G.sum_counts([]), RULES)
    assert all(math.isnan(v) for v in empty.values())


# ---------------------------------------------------------------- CoNLL-U reader and token alignment

CONLLU = """# newdoc id = D1
# sent_id = D1-0
# text = I can't go.
1\tI\tI\tPRON\tPRP\t_\t3\tnsubj\t_\t_
2-3\tcan't\t_\t_\t_\t_\t_\t_\t_\t_
2\tca\tcan\tAUX\tMD\t_\t4\taux\t_\t_
3\tn't\tnot\tPART\tRB\t_\t4\tadvmod\t_\t_
3.1\tgo\tgo\tVERB\t_\t_\t_\t_\t_\t_
4\tgo\tgo\tVERB\tVB\t_\t0\troot\t_\t_
5\t.\t.\tPUNCT\t.\t_\t4\tpunct\t_\t_

# sent_id = D1-1
# text = ...

# newdoc id = D2
# sent_id = D2-0
# text = Hi
1\tHi\thi\tINTJ\tUH\t_\t_\troot\t_\t_

"""


def test_reader_expands_multiword_tokens_skips_empty_nodes_and_keeps_empty_sentences():
    sents = list(G.parse_conllu(CONLLU.splitlines(keepends=True)))
    assert [s["sent_id"] for s in sents] == ["D1-0", "D1-1", "D2-0"]
    first = sents[0]
    assert first["newdoc"] == "D1" and first["text"] == "I can't go."
    assert [w["form"] for w in first["words"]] == ["I", "ca", "n't", "go", "."]
    assert first["tokens"] == ["I", "can't", "go", "."]
    assert first["token_words"] == [(1,), (2, 3), (4,), (5,)]
    assert sents[1]["words"] == [] and sents[1]["text"] == "..."  # kept, so sentence k stays sentence k
    assert sents[2]["words"][0]["head"] == 0  # a head written "_" is read as the root


def test_read_conllu_reads_gzipped_files(tmp_path):
    p = tmp_path / "shard-0-of-1.conllu.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        fh.write(CONLLU)
    sents = G.read_conllu(p)
    assert [s["newdoc"] for s in sents] == ["D1", None, "D2"]


@pytest.mark.parametrize("text, forms, status, spans", [
    ("He said, \u201CHi.\u201D", ["He", "said", ",", "\u201C", "Hi", ".", "\u201D"], "exact",
     [(0, 2), (3, 7), (7, 8), (9, 10), (10, 12), (12, 13), (13, 14)]),
    ("\u201CHi\u201D", ['"', "Hi", '"'], "length", [(0, 1), (1, 3), (3, 4)]),  # a normalised mark keeps its place
    ("10 000 cats", ["10 000", "cats"], "exact", [(0, 6), (7, 11)]),  # a token holding a space
    ("abcd", ["ab", "cd", "ef"], "scaled", [(0, 1), (1, 2), (2, 4)]),
    ("   ", ["a"], "empty", [None]),
])
def test_align_tokens(text, forms, status, spans):
    got, st = G.align_tokens(text, forms)
    assert st == status
    assert got == spans


# ---------------------------------------------------------------- mean sentence length


def test_words_go_to_the_sentence_holding_their_first_letter():
    text = "He ran. \u201CStop!\u201D she said."
    words = text_words.words(text)
    sentences = [(0, 9), (9, 25)]  # a boundary that puts the opening mark of "Stop!" in the first sentence
    assert G.words_per_sentence([w.anchor for w in words], sentences) == ([2, 3], 0)
    assert G.words_per_sentence([w.start for w in words], sentences) == ([3, 2], 0)
    assert G.words_per_sentence([w.start for w in words], [(0, 7)]) == ([2], 3)


def test_mean_sentence_length_leaves_out_segments_without_words_unless_told_otherwise():
    assert G.mean_sentence_length([4, 0, 2], count_empty=False) == 3
    assert G.mean_sentence_length([4, 0, 2], count_empty=True) == 2
    assert math.isnan(G.mean_sentence_length([0], count_empty=False))


# ---------------------------------------------------------------- parser mean and the long-unit rule

SHORT = [(1, "A", "DET", 2, "det"), (2, "cat", "NOUN", 3, "nsubj"), (3, "sat", "VERB", 0, "root")]
LONG_ST = [(1, "Dogs", "NOUN", 2, "nsubj"), (2, "bark", "VERB", 0, "root"), (3, "loudly", "ADV", 2, "advmod")]
LONG_UD = [(1, "Dogs", "NOUN", 3, "nsubj"), (2, "bark", "NOUN", 1, "compound"), (3, "loudly", "ADV", 0, "root")]


def test_long_unit_takes_stanza_in_both_members():
    assert LONG.max_words == 100  # S3: "longer than 100 words", configured once in parse_udpipe.toml
    st = [counts(SHORT), counts(LONG_ST)]
    ud = [counts(SHORT), counts(LONG_UD)]
    mean, diag = parsemean.grammatical_features(st, ud, [3, 101], RULES, LONG)
    assert diag["long_units"] == 1
    assert diag["udpipe"]["mean_dependency_distance"] == diag["stanza"]["mean_dependency_distance"]
    assert diag["udpipe_alone"]["mean_dependency_distance"] != diag["stanza"]["mean_dependency_distance"]
    assert mean == {k: diag["stanza"][k] for k in mean}
    # at exactly the threshold the unit is not long, and the members differ
    mean, diag = parsemean.grammatical_features(st, ud, [3, 100], RULES, LONG)
    assert diag["long_units"] == 0
    s, u = diag["stanza"]["mean_dependency_distance"], diag["udpipe"]["mean_dependency_distance"]
    assert s != u and mean["mean_dependency_distance"] == pytest.approx((s + u) / 2)


def test_parser_mean_is_undefined_without_both_members_but_reports_the_one_present():
    st = [counts(SHORT)]
    mean, diag = parsemean.grammatical_features(st, None, [3], RULES, LONG)
    assert all(math.isnan(v) for v in mean.values())
    assert "stanza" in diag and "udpipe" not in diag
    assert parsemean.parser_mean({"a": 1.0, "b": float("nan")}, {"a": 2.0, "b": 1.0})["a"] == 1.5


# ---------------------------------------------------------------- the stage on the golden fixture


def _pin_golden_counts(cfg):
    """Pin the fixture's count list in the test's copy of resources.lock.json: the stage refuses an unpinned list
    (features_gramlex.toml, [lexical.frequency] require_pin)."""
    sha = hashlib.sha256((GOLDEN / "counts.tsv").read_bytes()).hexdigest()
    res = cfg.setdefault("resources", {})
    table = res["resources"] if isinstance(res.get("resources"), dict) else res
    table["count_list/counts.tsv"] = sha
    return cfg


def _golden_work(tmp_path):
    work = tmp_path / "work"
    docs = [json.loads(x) for x in (GOLDEN / "documents.jsonl").read_text(encoding="utf-8").splitlines()]
    segs = [json.loads(x) for x in (GOLDEN / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
    records.write_jsonl(records.artefact_path(work, "en-us", "documents", 0, 1), docs)
    records.write_jsonl(records.artefact_path(work, "en-us", "segments", 0, 1), segs)
    for name, src in (("parses_stanza", "stanza.conllu"), ("parses_udpipe", "udpipe.conllu")):
        p = records.artefact_path(work, "en-us", name, 0, 1, ext="conllu.gz")
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8", newline="\n") as fh:
            fh.write((GOLDEN / src).read_text(encoding="utf-8"))
    cfg = copy.deepcopy(CFG)
    cfg["stages"]["features_gramlex"]["lexical"]["frequency"].update(resource="count_list",
                                                                     count_list=str(GOLDEN / "counts.tsv"))
    return work, _pin_golden_counts(cfg)


def _run(work, cfg):
    ctx = cli.StageContext(stage=stage.STAGE, config=cfg, lang="en-us", work=work)
    rec = cli.run_stage(stage, ctx)
    out = {r["story_id"]: r for r in records.read_jsonl(ctx.path("features_gramlex"))}
    return rec, out


EXPECTED = json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))


def test_stage_reproduces_the_golden_values(tmp_path):
    rec, out = _run(*_golden_work(tmp_path))
    for sid in ("S1", "S2"):
        values = out[sid]["values"]
        for k, v in EXPECTED[sid].items():
            if v is None:
                assert values[k] is None, (sid, k)
            else:
                assert values[k] == pytest.approx(v, rel=1e-12, abs=1e-12), (sid, k)
        assert set(values) == set(out["S1"]["values"])  # the same keys whatever is missing
    d1, d2 = out["S1"]["diagnostics"], out["S2"]["diagnostics"]
    e1, e2 = EXPECTED["diagnostics"]["S1"], EXPECTED["diagnostics"]["S2"]
    for member in ("stanza", "udpipe"):
        for k, v in e1[member].items():
            assert d1["grammatical"][member][k] == pytest.approx(v), (member, k)
    assert d1["grammatical"]["long_units"] == e1["long_units"]
    assert d1["grammatical"]["stanza"]["speech_main_heads"] == e1["speech_main_heads"]
    assert d1["pages"] == {"page_breaks": 1, "page_breaks_inside_sentence": 0}
    assert d1["missing"] == [] and d1["udpipe_alternatives"]["mattr"] == pytest.approx(0.9)
    for k, v in e2["stanza"].items():
        assert d2["grammatical"]["stanza"][k] == pytest.approx(v), k
    assert d2["missing"] == e2["missing"]
    assert d2["lexical"]["density"]["lexical_density_syntactic_word"] == pytest.approx(
        e2["lexical_density_syntactic_word"])
    first = (GOLDEN / "documents.jsonl").read_text(encoding="utf-8").splitlines()[0]
    doc = records.Document.from_json(json.loads(first))
    bare, _ = stage.document_features(doc, text_words.words(doc.text), None, None, None, _env())
    assert set(bare["values"]) == set(out["S1"]["values"])  # a record with no input has every key, undefined
    c = rec["counts"]
    assert (c["documents"], c["words"], c["sentences"], c["udpipe_unusable"]) == (2, 24, 6, 1)
    assert c["characters"] == 76 + 46 and c["frequency_resource"]["resource"] == "counts.tsv"
    # Stanza's offsets come from the artefact's TokenRange; the UDPipe fixture has none, so its come from alignment
    assert (c["stanza_offsets_token_range"], c["udpipe_offsets_exact"]) == (6, 4)
    assert not any(k.endswith("_out_of_order") for k in c)


def test_detector_route_of_the_speech_rule_gives_the_same_counts_on_the_fixture(tmp_path):
    work, cfg = _golden_work(tmp_path)
    cfg["stages"]["features_gramlex"]["grammatical"]["speech"]["rule"] = "detector_spans"
    _, out = _run(work, cfg)
    g = out["S1"]["diagnostics"]["grammatical"]
    assert g["stanza"]["speech_main_heads"] == 1 and g["udpipe"]["speech_main_heads"] == 1
    for k in ("subordination", "clauses_per_sentence"):
        assert out["S1"]["values"][k] == pytest.approx(EXPECTED["S1"][k])


def test_stage_reads_parses_as_the_parse_module_writes_them(tmp_path):
    """The Stanza artefact is rewritten by parse.parse_shard, the parse stages' own writer, from the fixture's trees,
    so the stage reads the producers' format: `# span`, TokenRange found by their alignment, and an empty block."""
    from intract_features import parse as P

    work, cfg = _golden_work(tmp_path)
    docs = [records.Document.from_json(json.loads(x))
            for x in (GOLDEN / "documents.jsonl").read_text(encoding="utf-8").splitlines()]
    segs = {r["story_id"]: P.spans_from_record(r, "sentences") for r in
            (json.loads(x) for x in (GOLDEN / "segments.jsonl").read_text(encoding="utf-8").splitlines())}
    trees = {s.text: s.tokens for d in P.read_conllu(GOLDEN / "stanza.conllu") for s in d.sentences}

    def parse_fn(texts):
        # the parser returns nothing for S2's first sentence, which must then be written as an empty block
        return [None if x == "Sparkle cannot fly." else [P.Token(form=t.form, words=t.words) for t in trees[x]]
                for x in texts]

    items = [(d, P.document_units(d, segs[d.story_id])) for d in docs]
    P.parse_shard(records.artefact_path(work, "en-us", "parses_stanza", 0, 1, ext="conllu.gz"), items, parse_fn,
                  max_skip=8)
    rec, out = _run(work, cfg)
    for k in ("mean_dependency_distance", "noun_phrase_elaboration", "word_length", "lexical_density", "mattr"):
        assert out["S1"]["values"][k] == pytest.approx(EXPECTED["S1"][k]), k
    s2 = out["S2"]["diagnostics"]["grammatical"]["stanza"]
    assert s2["sentences"] == 1 and s2["clauses_per_sentence"] == 1.0  # the empty sentence enters no denominator
    assert (rec["counts"]["stanza_offsets_token_range"], rec["counts"]["stanza_offsets_empty"]) == (5, 1)


def test_stage_in_strict_mode_refuses_a_missing_parse_and_leaves_no_artefact(tmp_path):
    work, cfg = _golden_work(tmp_path)
    cfg["stages"]["features_gramlex"]["stage"]["strict"] = True
    with pytest.raises(ValueError, match="udpipe: no parse"):
        _run(work, cfg)
    assert not records.artefact_path(work, "en-us", "features_gramlex", 0, 1).exists()


def test_segments_out_of_the_documents_order_leave_a_story_without_segments(tmp_path):
    work, cfg = _golden_work(tmp_path)
    p = records.artefact_path(work, "en-us", "segments", 0, 1)
    records.write_jsonl(p, list(records.read_jsonl(p))[::-1])
    rec, out = _run(work, cfg)
    assert rec["counts"]["segments_missing"] == 1 and out["S1"]["diagnostics"]["missing"] == ["segments: none"]
    assert out["S2"]["values"]["mean_sentence_length"] == pytest.approx(3.5)


def _env(**changes):
    cfg = copy.deepcopy(CFG)
    g = cfg["stages"]["features_gramlex"]
    g["lexical"]["frequency"].update(resource="count_list", count_list=str(GOLDEN / "counts.tsv"))
    for path, value in changes.items():
        table, key = path.split("__")
        g[table][key] = value
    return stage.GramlexEnv.build(_pin_golden_counts(cfg), "en-us")


def test_document_without_segments_keeps_every_key():
    env = _env()
    doc = records.Document(story_id="X", lang="en-us", level="mid", kind="generated", title="T", pages=("A b.",))
    rec, info = stage.document_features(doc, text_words.words(doc.text), None, None, None, env)
    assert info["segments_missing"] == 1 and rec["values"]["word_count"] == 2
    assert rec["values"]["mean_sentence_length"] is None and rec["values"]["mattr"] is None
    assert {"mean_dependency_distance", "mattr_window25", "rare_share", "pages_per_100_words"} <= set(rec["values"])


def test_document_with_no_sentence_needs_no_parse():
    doc = records.Document(story_id="X", lang="en-us", level="mid", kind="generated", title="T", pages=("",))
    rec, info = stage.document_features(doc, [], [], None, None, _env())
    assert rec["diagnostics"]["missing"] == [] and "stanza_unusable" not in info


def test_bad_word_anchor_is_refused():
    with pytest.raises(ValueError):
        _env(sentences__word_anchor="middle")


def test_segment_spans_refuse_a_stale_record():
    doc = records.Document(story_id="X", lang="en-us", level="mid", kind="generated", title="T", pages=("A b.",))
    rec = {"story_id": "X", "sentences": [[0, 4, 0, 0]],
           "text_sha256": hashlib.sha256(doc.text.encode("utf-8")).hexdigest()}
    assert stage._segment_spans(rec, doc) == [(0, 4)] and stage._segment_spans(None, doc) is None
    with pytest.raises(ValueError, match="stale"):
        stage._segment_spans({**rec, "text_sha256": "0" * 64}, doc)


def test_aligned_reader_stops_at_a_later_story_and_counts_broken_order():
    order = {"a": 0, "b": 1, "c": 2, "d": 3}
    a = stage.Aligned([("a", 1), ("c", 3), ("d", 4)], order)
    assert (a.get("a"), a.get("b"), a.get("c"), a.get("d")) == (1, None, 3, 4)  # b is missing; c is not consumed
    a = stage.Aligned([("b", 2), ("a", 1), ("x", 0), ("c", 3)], order)
    assert a.get("a") is None and a.get("b") == 2 and a.get("c") == 3
    assert (a.out_of_order, a.unknown) == (1, 1)
    assert stage.Aligned([], order).get("a") is None


def test_unimplemented_languages_are_refused():
    with pytest.raises(NotImplementedError):
        stage.check_language({"iso": "ko", "spaced": True})
    with pytest.raises(NotImplementedError):
        stage.check_language({"iso": "zh", "spaced": False})


# ---------------------------------------------------------------- test_gfeat_rules.py, parts 1b and 2, on UD files

REPRO_DIRS = os.environ.get("INTRACT_GFEAT_REPRO_DIRS", "")
OLD_GFEAT = os.environ.get("INTRACT_OLD_GFEAT", "")
BIG = ("de_hdt", "ru_syntagrus")  # left out to keep the run within minutes, as in test_gfeat_rules.py


def _repro_paths():
    return sorted(p for d in REPRO_DIRS.split(os.pathsep) if d for p in Path(d).glob("*.conllu")
                  if not p.name.startswith(BIG))


def _load_old_gfeat():
    spec = importlib.util.spec_from_file_location("gfeat_old", OLD_GFEAT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.models
@pytest.mark.skipif(not (REPRO_DIRS and OLD_GFEAT), reason="needs INTRACT_GFEAT_REPRO_DIRS and INTRACT_OLD_GFEAT")
def test_counts_without_the_speech_rule_reproduce_the_earlier_gfeat_on_ud_files():
    old = _load_old_gfeat()
    paths = _repro_paths()
    assert paths, "no .conllu files found"
    n = touched = 0
    for p in paths:
        mine = [s for s in G.read_conllu(p) if s["words"]]
        theirs = old.read_conllu(p)
        assert len(mine) == len(theirs), p
        for s, t in zip(mine, theirs, strict=True):
            assert [(w["id"], w["form"], w["upos"], w["head"], w["deprel"]) for w in s["words"]] == \
                   [(w["id"], w["form"], w["upos"], w["head"], w["deprel"]) for w in t["words"]], p
            assert s["tokens"] == t["tokens"], p
            new, ref = G.sentence_counts(t, RULES_NONE), old.sentence_counts(t)
            assert all(new[k] == ref[k] for k in KEYS), (p, t["text"])
            touched += G.sentence_counts(t, RULES)["speech_main"] > 0
            n += 1
    print(f"{len(paths)} files, {n} sentences; the direct-speech rule touches {touched} sentences")


def _span_standalone(words):
    inside, open_at = set(), None
    for k, w in enumerate(words):
        if w["form"] in RULES.quote_marks:
            if open_at is None:
                open_at = k
            else:
                inside.update(x["id"] for x in words[open_at + 1:k])
                open_at = None
    return inside


def _glue(words, forward):
    out, pend = [], []
    for w in words:
        if w["form"] not in RULES.quote_marks:
            out.append({**w, "form": "".join(p["form"] for p in pend) + w["form"]})
            pend = []
        elif forward:
            pend.append(w)
        elif out:
            out[-1] = {**out[-1], "form": out[-1]["form"] + w["form"]}
        else:
            out.append(w)
    return out + pend


@pytest.mark.models
@pytest.mark.skipif(not REPRO_DIRS, reason="needs INTRACT_GFEAT_REPRO_DIRS")
def test_speech_span_matches_the_standalone_rule_and_survives_gluing_on_ud_files():
    marks = RULES.quote_marks
    nq = 0
    for p in _repro_paths():
        for s in G.read_conllu(p):
            if not any(ch in marks for w in s["words"] for ch in w["form"]):
                continue
            nq += 1
            new = G.speech_span(s["words"], marks)
            if not any(w["form"] not in marks and sum(G.quote_edges(w["form"], marks)[:2]) for w in s["words"]):
                assert new == _span_standalone(s["words"]), (p, s["text"])
            for fwd in (True, False):
                assert G.speech_span(_glue(s["words"], fwd), marks) == new, (p, fwd, s["text"])
    assert nq > 0
