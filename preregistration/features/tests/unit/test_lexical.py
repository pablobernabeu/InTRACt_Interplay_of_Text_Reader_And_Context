"""Tests of features.lexical: lookup normalisation, letters, frequency resources, names, word length and density."""

import copy
import dataclasses
import hashlib
import math
from pathlib import Path

import pytest

from intract_features import config as config_mod
from intract_features.features import grammatical as G
from intract_features.features import lexical as L

FEATURES = Path(__file__).resolve().parents[2]
STAGE_CFG = config_mod.load(FEATURES / "config")["stages"]["features_gramlex"]
NORM = STAGE_CFG["lexical"]["normalisation"]
DOTTED = STAGE_CFG["lexical"]["casing"]["dotted_i_languages"]
RULES = L.LexicalRules.from_config(STAGE_CFG, "en")
LETTERS_CFG = STAGE_CFG["lexical"]["letters"]


def key(lex):
    return L.LookupNormaliser(NORM, lex, DOTTED)


# ---------------------------------------------------------------- casing and normalisation


def test_lower_applies_the_dotted_i_rule_only_where_configured():
    assert L.lower("I\u0130", True) == "\u0131i"
    assert L.lower("I", False) == "i"
    # a decomposed capital I with a combining dot above is composed first, so it is one type with the composed form
    assert L.lower("I\u0307stanbul", True) == L.lower("\u0130stanbul", True) == "istanbul"
    assert DOTTED == ["tr"]


def test_english_key_deletes_invisible_marks_maps_apostrophes_and_composes():
    k = key("en")
    assert k("Don\u2019t") == "don't" and k("don\u02BCt") == "don't"
    assert k("ca\u00ADt\u200B") == "cat"
    assert k("Cafe\u0301") == "caf\u00E9"  # NFC first


def test_arabic_key():
    k = key("ar")
    assert k("\uFEFB") == "\u0644\u0627"  # a presentation-form ligature takes NFKC
    assert k("\u0623\u064E\u0643\u0640\u0644") == "\u0627\u0643\u0644"  # hamza alef -> alef, fatha and tatweel go
    assert k("\u0661\u0629\u0649") == "\u0661\u0629\u0649"  # digits, teh marbuta and alef maksura stay


def test_hebrew_key_drops_points_keeps_the_maqaf_and_maps_geresh():
    k = key("he")
    assert k("\u05E9\u05B8\u05C1\u05DC\u05D5\u05B9\u05DD") == "\u05E9\u05DC\u05D5\u05DD"
    assert k("\u05D1\u05BE\u05D9\u05EA") == "\u05D1\u05BE\u05D9\u05EA"
    assert k("\u05D2\u05F3") == "\u05D2'" and k("\u05E6\u05D4\u05F4\u05DC") == '\u05E6\u05D4"\u05DC'


def test_turkish_romanian_and_russian_keys():
    assert key("tr")("\u0130stanbul") == "istanbul" and key("tr")("ISPARTA") == "\u0131sparta"
    assert key("en")("ISPARTA") == "isparta"
    assert key("ro")("\u015E\u0162") == "\u0219\u021B"
    assert key("ru")("\u0401\u0436") == "\u0435\u0436"


def test_traditional_chinese_key_converts_and_maps_variants():
    pytest.importorskip("opencc")
    assert key("zh-hant")("\u59B3") == "\u4F60"


# ---------------------------------------------------------------- letters


@pytest.mark.parametrize("iso, word, n", [
    ("en", "na\u00EFve", 5), ("en", "x\u0303", 1), ("en", "3rd", 2), ("en", "well-known", 9),
    ("ko", "\uD55C\uAD6D", 6),  # two blocks of three jamo each after canonical decomposition
    ("zh", "\u4E2D\u6587ab", 2),
    ("th", "\u0E01\u0E48\u0E32", 2),  # consonant and vowel; the tone mark is left out
    ("ar", "\u0643\u064E\u062A\u064E\u0628\u064E", 3), ("ar", "\u0643\u0640\u062A\u0628", 3),  # no marks, no tatweel
    ("he", "\u05E9\u05B8\u05C1\u05DC\u05D5\u05B9\u05DD", 4),
])
def test_letters_by_script(iso, word, n):
    assert L.LetterCounter(LETTERS_CFG, iso)(word) == n


# ---------------------------------------------------------------- frequency resources


def test_count_list_takes_the_laplace_smoothed_zipf_and_its_floor():
    cl = L.CountList({"big": 99, "kite": 9}, name="t", n_tokens=999_998, n_types=2)  # (N + T) / 1e6 = 1
    assert cl.lookup("big") == (pytest.approx(5.0), False)
    assert cl.lookup("kite")[0] == pytest.approx(4.0)
    assert cl.lookup("far") == (pytest.approx(3.0), True) and cl.floor == pytest.approx(3.0)
    own = L.CountList({"a": 8, "b": 1}, name="t")  # N = 9 and T = 2 taken from the counts
    assert own.lookup("a")[0] == pytest.approx(math.log10(9 / 11e-6) + 3)


def test_count_list_file_and_pins(tmp_path):
    p = tmp_path / "list.tsv"
    p.write_text("# comment\na\t3\nb\t1\na\t2\n", encoding="utf-8")
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    assert L.verify_pin(p, {}, "count_list/list.tsv") == "unpinned"
    assert L.verify_pin(p, {"x": sha}, "x") == "verified"
    assert L.verify_pin(p, {"x": {"sha256": sha}}, "x") == "verified"
    with pytest.raises(RuntimeError):
        L.verify_pin(p, {"x": "0" * 64}, "x")
    cl = L.load_count_list(p, {"count_list/list.tsv": sha})
    assert cl.pin == "verified" and cl.n_tokens == 6 and cl.n_types == 2
    assert cl.lookup("a")[0] == pytest.approx(math.log10(6 / 8e-6) + 3)


def test_build_frequency_resource_refuses_bad_settings():
    freq = dict(STAGE_CFG["lexical"]["frequency"])
    with pytest.raises(ValueError):
        L.build_frequency_resource({**freq, "resource": "count_list", "count_list": ""}, "en")
    with pytest.raises(ValueError):
        L.build_frequency_resource({**freq, "resource": "subtlex"}, "en")


def test_wordfreq_list_reads_the_interim_resource_exactly():
    wordfreq = pytest.importorskip("wordfreq")
    freq = {**STAGE_CFG["lexical"]["frequency"], "require_pin": False}
    wl = L.build_frequency_resource(freq, "en")
    assert wl.floor == 1.01 and wl.lookup("the") == (7.73, False) and wl.lookup("zzqxv") == (1.01, True)
    d = wordfreq.get_frequency_dict("en", "best")
    for w in ("the", "kite", "dragon", "sparkle", "huge"):
        assert wl.lookup(w)[0] == pytest.approx(math.log10(d[w]) + 9, abs=1e-12)  # lexrules.FreqList's form
    sha = L.sha256_of(wl.path)
    pinned = L.WordfreqList("en", "best", "3.1.1", {f"wordfreq-3.1.1/{wl.path.name}": sha})
    assert pinned.describe()["pin"] == "verified" and wl.describe()["pin"] == "unpinned"
    assert L.build_frequency_resource(freq, "kk") is None  # no Kazakh list in wordfreq 3.1.1
    with pytest.raises(RuntimeError):
        L.WordfreqList("en", "best", "0.0")
    # the stage's own setting: an unpinned list stops it before the list is read, a pinned one passes
    assert STAGE_CFG["lexical"]["frequency"]["require_pin"] is True
    with pytest.raises(RuntimeError, match="no pin"):
        L.build_frequency_resource(STAGE_CFG["lexical"]["frequency"], "en", {})
    strict = L.build_frequency_resource(STAGE_CFG["lexical"]["frequency"], "en",
                                        {f"wordfreq-3.1.1/{wl.path.name}": sha})
    assert strict.describe()["pin"] == "verified"


def test_count_list_with_required_pin(tmp_path):
    p = tmp_path / "list.tsv"
    p.write_text("a\t3\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="no pin"):
        L.load_count_list(p, {}, require_pin=True)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    assert L.load_count_list(p, {"count_list/list.tsv": sha}, require_pin=True).pin == "verified"


# ---------------------------------------------------------------- names, tokens and word classes

TEXT = "Lily's well-known dog sleeps."
CONLLU = """# sent_id = T-0
# text = Lily's well-known dog sleeps.
1\tLily\tLily\tPROPN\t_\t_\t5\tnmod:poss\t_\t_
2\t's\t's\tPART\t_\t_\t1\tcase\t_\t_
3\twell\twell\tADV\t_\t_\t5\tadvmod\t_\t_
4\t-\t-\tPUNCT\t_\t_\t5\tpunct\t_\t_
5\tknown\tknow\tVERB\t_\t_\t6\tamod\t_\t_
6\tdog\tdog\tNOUN\t_\t_\t7\tnsubj\t_\t_
7\tsleeps\tsleep\tVERB\t_\t_\t0\troot\t_\t_
8\t.\t.\tPUNCT\t_\t_\t7\tpunct\t_\t_

"""
WORDS = [(0, 6), (7, 17), (18, 21), (22, 29)]  # Lily's | well-known | dog | sleeps.


def tokens_of(conllu, text, rules=RULES, inventory=None):
    """Tokens of a one-sentence parse whose sentence is the whole text, so its offsets are document offsets."""
    sents = list(G.parse_conllu(conllu.splitlines(keepends=True)))
    spans = [G.align_tokens(text, s["tokens"])[0] for s in sents]
    is_name = L.name_predicate(sents, rules, key("en"), inventory)
    return L.build_tokens(sents, spans, is_name, rules)


def test_build_tokens_decides_names_and_content():
    toks = tokens_of(CONLLU, TEXT)
    assert [t.span for t in toks] == [(0, 4), (4, 6), (7, 11), (11, 12), (12, 17), (18, 21), (22, 28), (28, 29)]
    assert [(w.form, w.name, w.content) for t in toks for w in t.words][:3] == [
        ("Lily", True, False), ("'s", False, False), ("well", False, True)]
    assert toks[4].words[0].lemma == "know"


def test_classify_words_by_any_and_all():
    toks = tokens_of(CONLLU, TEXT)
    assert L.classify_words(WORDS, toks, "any") == [(False, True, True), (True, False, True), (True, False, True),
                                                   (True, False, True)]
    assert L.classify_words(WORDS, toks, "all")[0] == (False, False, True)
    assert L.classify_words([(30, 33)], toks, "any") == [(False, False, False)]  # a word no token covers


def test_type_majority_and_inventory_name_rules():
    conllu = "".join(f"{i}\t{f}\t{f}\t{u}\t_\t_\t0\troot\t_\t_\n" for i, (f, u) in enumerate(
        [("Sparkle", "PROPN"), ("Sparkle", "NOUN"), ("Rex", "PROPN"), ("rex", "NOUN"), ("Rex", "NOUN"),
         ("Bo", "PROPN"), ("bo", "NOUN")], start=1))
    sents = list(G.parse_conllu(("# sent_id = N-0\n" + conllu + "\n").splitlines(keepends=True)))
    maj = dataclasses.replace(RULES, name_rule="type_majority_text")
    is_name = L.name_predicate(sents, maj, key("en"))
    words = sents[0]["words"]
    assert [is_name(w) for w in words] == [True, True, False, False, False, True, True]  # exactly half is a name
    tok = L.name_predicate(sents, RULES, key("en"))
    assert [tok(w) for w in words] == [True, False, True, False, False, True, False]
    inv = dataclasses.replace(RULES, name_rule="inventory")
    with pytest.raises(ValueError):
        L.name_predicate(sents, inv, key("en"))
    assert [L.name_predicate(sents, inv, key("en"), frozenset({"rex"}))(w) for w in words][2:5] == [True] * 3


def test_inventory_file(tmp_path):
    p = tmp_path / "names.txt"
    p.write_text("rex\n\nsparkle\n", encoding="utf-8")
    assert L.load_inventory(p) == frozenset({"rex", "sparkle"})


# ---------------------------------------------------------------- features

FREQ_TEXT = "Big kiteflew far"
FREQ_CONLLU = """# sent_id = F-0
# text = Big kiteflew far
1\tBig\tbig\tADJ\t_\t_\t3\tamod\t_\t_
2-3\tkiteflew\t_\t_\t_\t_\t_\t_\t_\t_
2\tkite\tkite\tNOUN\t_\t_\t3\tnsubj\t_\t_
3\tflew\tfly\tVERB\t_\t_\t0\troot\t_\t_
4\tfar\tfar\tADV\t_\t_\t3\tadvmod\t_\t_

"""
FREQ_LIST = L.CountList({"big": 99, "kite": 9, "flew": 999}, name="t", n_tokens=999_997, n_types=3)


def test_frequency_features_aggregate_to_the_orthographic_word():
    toks = tokens_of(FREQ_CONLLU, FREQ_TEXT)
    v, d = L.frequency_features(toks, FREQ_LIST, key("en"), RULES)
    # units: big 5 | kiteflew (4 + 6) / 2 = 5 | far absent, the floor 3, rare
    assert v["mean_zipf"] == pytest.approx(13 / 3) and v["rare_share"] == pytest.approx(1 / 3)
    assert v["mean_zipf_matched"] == pytest.approx(5.0) and v["rare_share_matched"] == 0
    assert v["rare_share_zipf3"] == pytest.approx(1 / 3)  # absent tokens count as rare at either threshold
    assert d == {"content_tokens": 3, "matched_tokens": 2, "rare_tokens": 1, "rare_tokens_zipf3": 1,
                 "content_syntactic_words": 4, "found_syntactic_words": 3, "defined": True}


def test_frequency_features_are_undefined_when_no_content_token_is_found():
    # qmd, Outcome-blind dimension reduction: "A text's value is defined when at least one of its non-name content
    # tokens is found in the feature's resource." Not the floor and a rare share of 1.
    toks = tokens_of(FREQ_CONLLU, FREQ_TEXT)
    v, d = L.frequency_features(toks, StubList({}), key("en"), RULES)
    assert all(math.isnan(v[k]) for k in ("mean_zipf", "rare_share", "rare_share_zipf3", "mean_zipf_matched"))
    assert d["defined"] is False and d["found_syntactic_words"] == 0 and d["content_tokens"] == 3


def test_frequency_features_on_syntactic_words():
    toks = tokens_of(FREQ_CONLLU, FREQ_TEXT)
    syn = dataclasses.replace(RULES, aggregation="syntactic_word")
    v, d = L.frequency_features(toks, FREQ_LIST, key("en"), syn)
    assert v["mean_zipf"] == pytest.approx(4.5) and d["content_tokens"] == 4
    assert v["mean_zipf_matched"] == pytest.approx(5.0)


class StubList:
    def __init__(self, values):
        self.values = values

    def lookup(self, k):
        return (self.values[k], False) if k in self.values else (0.5, True)


def test_rare_share_threshold_is_strict():
    toks = tokens_of(FREQ_CONLLU, FREQ_TEXT)
    syn = dataclasses.replace(RULES, aggregation="syntactic_word")
    v, _ = L.frequency_features(toks, StubList({"big": 4.0, "kite": 3.999, "flew": 4.0, "far": 7.0}), key("en"), syn)
    assert v["rare_share"] == pytest.approx(1 / 4) and v["rare_share_zipf3"] == 0


def test_frequency_features_without_a_resource_are_undefined():
    v, d = L.frequency_features([], None, key("en"), RULES)
    assert all(math.isnan(x) for x in v.values()) and d == {"resource": "unavailable"}


def test_word_length_in_both_units():
    toks = tokens_of(CONLLU, TEXT)
    letters = L.LetterCounter(LETTERS_CFG, "en")
    classes = L.classify_words(WORDS, toks, "any")
    v, d = L.word_length_features(toks, TEXT, WORDS, classes, letters, RULES)
    assert v == {"word_length": 18 / 4, "word_length_all_words": 19 / 5}  # well known dog sleeps | 's too
    word = dataclasses.replace(RULES, word_length_unit="word")
    v, _ = L.word_length_features(toks, TEXT, WORDS, classes, letters, word)
    assert v == {"word_length": 6.0, "word_length_all_words": 6.0}  # well-known 9, dog 3, sleeps 6
    v, _ = L.word_length_features(toks, TEXT, WORDS, L.classify_words(WORDS, toks, "all"), letters, word)
    assert v["word_length_all_words"] == 23 / 4  # Lily's (5 letters) is no longer a name word


def test_density_in_both_units():
    toks = tokens_of(CONLLU, TEXT)
    v, d = L.density_features(toks, L.classify_words(WORDS, toks, "any"), RULES)
    assert v == {"lexical_density": 1.0} and d["lexical_density_syntactic_word"] == pytest.approx(4 / 5)
    assert (d["density_words"], d["density_content_words"], d["words_without_token"]) == (3, 3, 0)
    v, _ = L.density_features(toks, L.classify_words(WORDS, toks, "all"), RULES)
    assert v["lexical_density"] == pytest.approx(3 / 4)
    syn = dataclasses.replace(RULES, density_unit="syntactic_word")
    v, d = L.density_features(toks, L.classify_words(WORDS, toks, "any"), syn)
    assert v["lexical_density"] == pytest.approx(4 / 5) and d["lexical_density_word"] == 1.0


@pytest.mark.parametrize("path, value", [(("names", "rule"), "guess"), (("names", "word_rule"), "some"),
                                         (("frequency", "aggregation"), "page"), (("word_length", "unit"), "page"),
                                         (("density", "unit"), "page")])
def test_unknown_switch_values_are_refused(path, value):
    cfg = copy.deepcopy(STAGE_CFG)
    cfg["lexical"][path[0]][path[1]] = value
    with pytest.raises(ValueError):
        L.LexicalRules.from_config(cfg, "en")


def test_arabic_takes_x_as_a_name_tag():
    assert L.LexicalRules.from_config(STAGE_CFG, "ar").name_upos == frozenset({"PROPN", "X"})
    assert RULES.name_upos == frozenset({"PROPN"})
