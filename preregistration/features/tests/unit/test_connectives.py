"""English causal and contrastive anchors (features.connectives), with the registered list read from config."""

import tomllib
from pathlib import Path

import pytest

from intract_features.features import connectives as con

CONFIG = Path(__file__).resolve().parents[2] / "config" / "stages" / "features_discourse.toml"


@pytest.fixture(scope="module")
def cfg():
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))["connectives"]


@pytest.fixture(scope="module")
def counter(cfg):
    return con.ConnectiveCounter(con.AnchorSpec.from_config(cfg))


def flat(sentence):
    """Words with no tree (head 0, relation dep), for the anchors whose rules read forms only."""
    return [{"id": i, "form": f, "lemma": f.lower(), "upos": "X", "head": 0, "deprel": "dep", "feats": "_"}
            for i, f in enumerate(sentence.split(), 1)]


def counts(counter, sentence):
    c = counter.count(flat(sentence))
    return c.causal, c.contrastive, c.clause_initial


def test_the_registered_anchor_list(cfg):
    # S3: "The causal anchors are because, therefore, thus and clause-initial so, and the contrastive anchors are
    # but, however, although, though, even though, even if and whereas."
    assert cfg["causal"] == ["because", "therefore", "thus"]
    assert cfg["causal_clause_initial"] == ["so"]
    assert cfg["contrastive"] == ["but", "however", "although", "though", "even though", "even if", "whereas"]
    assert cfg["per_words"] == 100


def test_matcher_takes_the_longest_form_and_never_reuses_a_token():
    m = con.Matcher([("though",), ("even", "though"), ("even", "if")])
    assert m.match(["even", "though", "it", "rained"]) == [(("even", "though"), [0, 1])]
    assert m.match(["though", "even", "if"]) == [(("though",), [0]), (("even", "if"), [1, 2])]


def test_matcher_discontinuous_entries_use_the_tokens_left_over():
    m = con.Matcher([("either",), (("either",), ("or",))])
    # the contiguous "either" is taken first, so the discontinuous entry finds no free "either"
    assert m.match(["either", "tea", "or", "coffee"]) == [(("either",), [0])]
    m2 = con.Matcher([(("either",), ("or",))])
    assert m2.match(["either", "tea", "or", "coffee"]) == [((("either",), ("or",)), [0, 2])]


def test_causal_anchors(counter):
    assert counts(counter, "He ran because he was late .") == (1, 0, 0)
    assert counts(counter, "It rained ; therefore we stayed , and thus we read .") == (2, 0, 0)
    assert counts(counter, "BECAUSE it rained .") == (1, 0, 0)  # matching is on lower-cased forms


def test_clause_initial_so(counter):
    assert counts(counter, "So we went home .") == (1, 0, 1)
    assert counts(counter, "It was late , so we went home .") == (1, 0, 1)
    assert counts(counter, "It was late and so we went home .") == (1, 0, 1)
    assert counts(counter, "“ So what now ? ” he asked .") == (1, 0, 1)  # after a sentence-initial quotation mark
    assert counts(counter, "I was so happy .") == (0, 0, 0)  # not clause-initial
    assert counts(counter, "He hid , so that nobody saw him .") == (0, 0, 0)  # purpose
    assert counts(counter, "Apples , pears and so on .") == (0, 0, 0)  # S3 hygiene: "and so on"
    assert counts(counter, "So did I .") == (0, 0, 0)  # inversion with an auxiliary
    assert counts(counter, "So far we are fine .") == (0, 0, 0)  # degree


def test_contrastive_anchors_count_a_multiword_anchor_once(counter):
    assert counts(counter, "Even though it rained , we played .") == (0, 1, 0)
    assert counts(counter, "Even if it rains , we play .") == (0, 1, 0)
    assert counts(counter, "It was cold ; however , we swam , although the sea was rough .") == (0, 2, 0)
    assert counts(counter, "She ran , whereas he walked , but they met though .") == (0, 3, 0)


def test_the_typographic_apostrophe_is_folded():
    assert con.normalise_form("Don’t") == "don't"


def w(i, form, upos, head, deprel):
    return {"id": i, "form": form, "lemma": form.lower(), "upos": upos, "head": head, "deprel": deprel, "feats": "_"}


# "It was not a dog but a cat ."  (UD: copular root "dog", "not" an advmod of it, "cat" its conjunct)
NOT_X_BUT_Y = [w(1, "It", "PRON", 5, "nsubj"), w(2, "was", "AUX", 5, "cop"), w(3, "not", "PART", 5, "advmod"),
               w(4, "a", "DET", 5, "det"), w(5, "dog", "NOUN", 0, "root"), w(6, "but", "CCONJ", 8, "cc"),
               w(7, "a", "DET", 8, "det"), w(8, "cat", "NOUN", 5, "conj"), w(9, ".", "PUNCT", 5, "punct")]
# "I did not want to go , but I went ."  (the conjunct has its own subject: a coordinated clause)
CLAUSES = [w(1, "I", "PRON", 4, "nsubj"), w(2, "did", "AUX", 4, "aux"), w(3, "not", "PART", 4, "advmod"),
           w(4, "want", "VERB", 0, "root"), w(5, "to", "PART", 6, "mark"), w(6, "go", "VERB", 4, "xcomp"),
           w(7, ",", "PUNCT", 10, "punct"), w(8, "but", "CCONJ", 10, "cc"), w(9, "I", "PRON", 10, "nsubj"),
           w(10, "went", "VERB", 4, "conj"), w(11, ".", "PUNCT", 4, "punct")]
# "It is not only big but also heavy ."  ("not" under "only", an advmod of the first conjunct)
NOT_ONLY = [w(1, "It", "PRON", 5, "nsubj"), w(2, "is", "AUX", 5, "cop"), w(3, "not", "PART", 4, "advmod"),
            w(4, "only", "ADV", 5, "advmod"), w(5, "big", "ADJ", 0, "root"), w(6, "but", "CCONJ", 8, "cc"),
            w(7, "also", "ADV", 8, "advmod"), w(8, "heavy", "ADJ", 5, "conj"), w(9, ".", "PUNCT", 5, "punct")]


def test_not_x_but_y_is_blocked_and_a_coordinated_clause_is_not(counter):
    c = counter.count(NOT_X_BUT_Y)
    assert (c.contrastive, c.not_x_but_y_blocked) == (0, 1)
    c = counter.count(NOT_ONLY)
    assert (c.contrastive, c.not_x_but_y_blocked) == (0, 1)
    c = counter.count(CLAUSES)
    assert (c.contrastive, c.not_x_but_y_blocked) == (1, 0)


def test_the_not_x_but_y_switch(cfg):
    off = con.ConnectiveCounter(con.AnchorSpec.from_config({**cfg, "block_not_x_but_y": False}))
    assert off.count(NOT_X_BUT_Y).contrastive == 1


def test_densities_are_per_hundred_words_and_undefined_without_words():
    assert con.per_words(3, 150, 100) == 2.0
    assert con.per_words(0, 150, 100) == 0.0
    assert con.per_words(0, 0, 100) is None


def test_a_form_in_two_classes_is_refused(cfg):
    with pytest.raises(ValueError):
        con.AnchorSpec.from_config({**cfg, "causal": ["because", "but"]}).labels()
