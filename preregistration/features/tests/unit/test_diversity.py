"""Tests of features.diversity: MATTR, mattr_batch, MTLD and the unit sequences.

The mattr_batch test is part 1 of error_model/scripts/test_em_core.py, ported. MATTR and MTLD are also checked
against lexical_diversity 0.1.1 (Kyle), an independent implementation, where it is installed; its MTLD closes a
factor only when the ratio falls below .72, needs ten tokens per factor and always ends on a partial factor, so the
comparison sets those switches and keeps to sequences whose last token closes no factor.
"""

import copy
import math
import random
from pathlib import Path

import pytest

from intract_features import config as config_mod
from intract_features.features import diversity as D
from intract_features.features.lexical import SynWord, Token

FEATURES = Path(__file__).resolve().parents[2]
STAGE_CFG = config_mod.load(FEATURES / "config")["stages"]["features_gramlex"]
EN = D.DiversityRules.from_config(STAGE_CFG, "en")


# ---------------------------------------------------------------- MATTR


def test_mattr_by_hand():
    assert D.mattr(list("abac"), 3, "ttr") == pytest.approx(5 / 6)  # windows aba (2 types) and bac (3)
    assert D.mattr(list("aab"), 3, "ttr") == pytest.approx(2 / 3)  # no longer than the window: its type-token ratio
    assert math.isnan(D.mattr(list("aab"), 3, "missing"))
    assert math.isnan(D.mattr([], 50, "ttr"))


def test_mattr_matches_lexical_diversity():
    ld = pytest.importorskip("lexical_diversity.lex_div")
    rng = random.Random(3)
    for _ in range(200):
        seq = [rng.randrange(rng.randint(2, 40)) for _ in range(rng.randint(1, 160))]
        for w in (25, 50, 100):
            assert D.mattr(seq, w, "ttr") == pytest.approx(ld.mattr(seq, w), rel=1e-12, abs=1e-12)


def test_mattr_batch_equals_the_reference_loop():
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(1)
    n_units = 300
    lens = rng.integers(0, 25, n_units)
    off = np.concatenate([[0], np.cumsum(lens)])
    vocab = 40
    tok = rng.integers(0, vocab, off[-1]).astype(np.int32)
    n_texts = 200
    rows, cols = [], []
    for t in range(n_texts):
        k = rng.integers(1, 12)
        rows += [t] * k
        cols += list(rng.integers(0, n_units, k))
    rows, cols = np.array(rows), np.array(cols)
    got = D.mattr_batch(tok, off[:-1], off[1:], rows, cols, n_texts, vocab, 50)
    ref = np.array([D.mattr(np.concatenate([tok[off[c]:off[c + 1]] for c in cols[rows == t]]).tolist(), 50, "ttr")
                    for t in range(n_texts)], float)
    assert np.allclose(np.nan_to_num(got, nan=-1), np.nan_to_num(ref, nan=-1), atol=1e-12)


# ---------------------------------------------------------------- MTLD


def test_mtld_by_hand():
    seq = list("abacadefgh")
    # forward: a b a closes a factor at TTR 2/3; c a d e f g h leaves 7 types in 7 tokens, a partial factor of 0,
    # so 10 / 1. Reverse: no factor closes; 8 types in 10 tokens leave (1 - .8) / .28 = 5/7, so 10 / (5/7) = 14.
    assert D.mtld_factors(seq, 0.72, True, 0) == (1, 7, 7)
    assert D.mtld_pass(seq, 0.72, True, 0) == pytest.approx(10.0)
    assert D.mtld_pass(seq[::-1], 0.72, True, 0) == pytest.approx(14.0)
    assert D.mtld(seq, 0.72, True, 0) == pytest.approx(12.0)


def test_mtld_threshold_inclusion_and_minimum_factor_length():
    at = [str(i) for i in range(18)] + ["0"] * 7  # 18 types in 25 tokens: the ratio is exactly .72
    assert D.mtld_factors(at, 0.72, True, 0) == (1, 0, 0)
    assert D.mtld_factors(at, 0.72, False, 0) == (0, 25, 18)
    assert D.mtld_factors(["a", "a"], 0.72, True, 0) == (1, 0, 0)
    assert D.mtld_factors(["a", "a"], 0.72, True, 10) == (0, 2, 1)


def test_mtld_is_undefined_without_factors():
    assert math.isnan(D.mtld([], 0.72, True, 0))
    assert math.isnan(D.mtld(list("abcdef"), 0.72, True, 0))  # every token a new type: no factor accrues


def test_mtld_matches_lexical_diversity():
    ld = pytest.importorskip("lexical_diversity.lex_div")
    rng = random.Random(7)
    compared = 0
    for _ in range(400):
        seq = [str(rng.randrange(rng.randint(5, 60))) for _ in range(rng.randint(20, 200))]
        if D.mtld_factors(seq, 0.72, False, 10)[1] == 0 or D.mtld_factors(seq[::-1], 0.72, False, 10)[1] == 0:
            continue  # the last token closes a factor, where lexical_diversity counts a partial one instead
        ref = ld.mtld(seq)
        if ref == 0:
            continue  # lexical_diversity returns 0 where no factor accrues; mtld leaves it undefined
        assert D.mtld(seq, 0.72, inclusive=False, min_factor=10) == pytest.approx(ref, rel=1e-12)
        compared += 1
    assert compared > 100


# ---------------------------------------------------------------- sequences and features


def word(form, lemma, upos, name=False, content=None, deprel="dep"):
    return SynWord(form=form, lemma=lemma, upos=upos, deprel=deprel, name=name,
                   content=upos in {"NOUN", "VERB", "ADJ", "ADV"} and not name if content is None else content)


TOKENS = [Token((0, 4), (word("Cats", "Cat", "NOUN"),)), Token((5, 8), (word("Ran", "run", "VERB"),)),
          Token((9, 11), (word("Bo", "Bo", "PROPN", name=True),)),
          Token((11, 12), (word(".", ".", "PUNCT", deprel="punct"),)),
          Token((13, 17), (word("Isik", "I\u015F\u0131k", "NOUN"),))]


def test_sequences_follow_the_benchmark_keys():
    s = D.diversity_sequences(TOKENS, EN)
    assert s == {"content_lemma": ["cat", "run", "i\u015F\u0131k"], "content_form": ["cats", "ran", "isik"],
                 "all_word": ["cats", "ran", "bo", "isik"]}
    zh = D.diversity_sequences(TOKENS, D.DiversityRules.from_config(STAGE_CFG, "zh"))
    assert zh["content_lemma"] == ["Cats", "Ran", "Isik"] and zh["content_form"] == ["cats", "ran", "isik"]
    ko = D.diversity_sequences(TOKENS, D.DiversityRules.from_config(STAGE_CFG, "ko"))
    assert ko["content_lemma"] == ["Cat", "run", "I\u015F\u0131k"]
    tr = D.diversity_sequences(TOKENS, D.DiversityRules.from_config(STAGE_CFG, "tr"))
    assert tr["content_lemma"][2] == "\u0131\u015F\u0131k" and tr["content_form"][2] == "\u0131sik"


def test_diversity_features_names_and_units():
    seqs = {"content_lemma": list("abacadefgh"), "content_form": list("abcdefghij"), "all_word": list("aabb")}
    v, d = D.diversity_features(seqs, EN)
    assert set(v) == {"mattr", "mattr_window25", "mattr_window100", "mattr_content_forms", "mattr_all_words", "mtld"}
    assert v["mattr"] == pytest.approx(8 / 10) and v["mattr_content_forms"] == 1.0
    assert v["mtld"] == pytest.approx(12.0)
    assert d["content_lemmas"] == 10 and d["mtld_all_word"] == pytest.approx(D.mtld(list("aabb"), 0.72, True, 0))
    cfg = copy.deepcopy(STAGE_CFG)
    cfg["diversity"]["mtld_unit"] = "all_word"
    v, d = D.diversity_features(seqs, D.DiversityRules.from_config(cfg, "en"))
    assert v["mtld"] == pytest.approx(D.mtld(list("aabb"), 0.72, True, 0)) and "mtld_content_lemma" in d


@pytest.mark.parametrize("field, value", [("short_text", "zero"), ("mtld_unit", "page")])
def test_unknown_switch_values_are_refused(field, value):
    cfg = copy.deepcopy(STAGE_CFG)
    cfg["diversity"][field] = value
    with pytest.raises(ValueError):
        D.DiversityRules.from_config(cfg, "en")


def test_registered_settings():
    assert (EN.window, EN.variant_windows, EN.mtld_threshold) == (50, (25, 100), 0.72)
