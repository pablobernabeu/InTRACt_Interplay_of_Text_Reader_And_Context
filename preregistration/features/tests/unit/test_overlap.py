"""Referential overlap and anaphoric continuation (features.overlap) on hand-built parses."""

import pytest

from intract_features.features import overlap as ovl

NOMINAL = {"NOUN", "PROPN"}
SUBJ = ("nsubj", "nsubj:pass")
HANDOVER_UPOS = ("CCONJ", "PART")
HANDOVER_REL = ("parataxis", "conj", "advcl")
PRED_DEPS = ("nsubj", "csubj", "cop", "aux", "expl")
PRS3 = "Number=Sing|Person=3|PronType=Prs"


def w(i, form, lemma, upos, head, deprel, feats="_"):
    return {"id": i, "form": form, "lemma": lemma, "upos": upos, "head": head, "deprel": deprel, "feats": feats}


def key(word):
    return ovl.lemma_or_form(word).lower()


def pron3(words):
    return ovl.has_third_person_pronoun_subject(words, SUBJ, HANDOVER_UPOS, HANDOVER_REL, PRED_DEPS)


# "The dogs ran." / "A dog barked." / "Birds sing." / "Tom smiled."
S_DOGS = [w(1, "The", "the", "DET", 2, "det"), w(2, "dogs", "dog", "NOUN", 3, "nsubj"),
          w(3, "ran", "run", "VERB", 0, "root"), w(4, ".", ".", "PUNCT", 3, "punct")]
S_DOG = [w(1, "A", "a", "DET", 2, "det"), w(2, "dog", "dog", "NOUN", 3, "nsubj"),
         w(3, "barked", "bark", "VERB", 0, "root"), w(4, ".", ".", "PUNCT", 3, "punct")]
S_BIRDS = [w(1, "Birds", "bird", "NOUN", 2, "nsubj"), w(2, "sing", "sing", "VERB", 0, "root")]


def test_nominal_keys_take_lemmas_of_nouns_and_proper_nouns_only():
    words = [w(1, "Tom", "Tom", "PROPN", 2, "nsubj"), w(2, "saw", "see", "VERB", 0, "root"),
             w(3, "them", "they", "PRON", 2, "obj"), w(4, "Dogs", "dog", "NOUN", 2, "obj"),
             w(5, "x", "x", "X", 2, "dep")]
    assert ovl.nominal_keys(words, NOMINAL, key) == {"tom", "dog"}
    # X is nominal only where configured, as in Arabic (S3: "or X in Arabic")
    assert ovl.nominal_keys(words, NOMINAL | {"X"}, key) == {"tom", "dog", "x"}


def test_lemma_or_form_falls_back_to_the_form():
    assert ovl.lemma_or_form(w(1, "Dogs", "dog", "NOUN", 0, "root")) == "dog"
    assert ovl.lemma_or_form(w(1, "Dogs", "_", "NOUN", 0, "root")) == "Dogs"
    assert ovl.lemma_or_form(w(1, "Dogs", "dog", "NOUN", 0, "root"), use_form=True) == "Dogs"


def test_overlap_is_the_share_of_adjacent_pairs_sharing_a_nominal_lemma():
    keysets = [ovl.nominal_keys(s, NOMINAL, key) for s in (S_DOGS, S_DOG, S_BIRDS)]
    flags = ovl.overlap_flags(keysets)
    assert flags == [True, False]  # "dogs"/"dog" share the lemma dog; dog and bird share nothing
    assert ovl.share(flags) == 0.5


def test_a_text_without_a_pair_has_no_overlap_value():
    assert ovl.overlap_flags([{"dog"}]) == []
    assert ovl.share([]) is None


def test_pairs_with_an_unparsed_sentence_are_left_out():
    assert ovl.adjacent_pairs([True, True, True]) == [(0, 1), (1, 2)]
    assert ovl.adjacent_pairs([True, False, True]) == []
    pairs = ovl.adjacent_pairs([True, True, False, True])
    assert pairs == [(0, 1)]
    keysets = [{"dog"}, {"dog"}, set(), {"dog"}]
    assert ovl.overlap_flags(keysets, pairs) == [True]


def test_third_person_personal_pronoun_subject():
    he = [w(1, "He", "he", "PRON", 2, "nsubj", "Case=Nom|" + PRS3), w(2, "left", "leave", "VERB", 0, "root")]
    i_ = [w(1, "I", "I", "PRON", 2, "nsubj", "Case=Nom|Number=Sing|Person=1|PronType=Prs"),
          w(2, "left", "leave", "VERB", 0, "root")]
    this = [w(1, "This", "this", "PRON", 3, "nsubj", "Number=Sing|PronType=Dem"), w(2, "is", "be", "AUX", 3, "cop"),
            w(3, "good", "good", "ADJ", 0, "root")]
    passive = [w(1, "It", "it", "PRON", 3, "nsubj:pass", PRS3), w(2, "was", "be", "AUX", 3, "aux:pass"),
               w(3, "found", "find", "VERB", 0, "root")]
    no_feats = [w(1, "She", "she", "PRON", 2, "nsubj"), w(2, "sang", "sing", "VERB", 0, "root")]
    assert pron3(he) and pron3(passive)
    assert not pron3(i_) and not pron3(this)
    # rc_features.py reads missing PronType and Person as personal and third person
    assert pron3(no_feats)
    # only the main clause's subject counts: a pronoun subject of a subordinate clause does not
    sub = [w(1, "Tom", "Tom", "PROPN", 2, "nsubj"), w(2, "smiled", "smile", "VERB", 0, "root"),
           w(3, "because", "because", "SCONJ", 5, "mark"), w(4, "he", "he", "PRON", 5, "nsubj", PRS3),
           w(5, "won", "win", "VERB", 2, "advcl")]
    assert not pron3(sub)


def test_subject_relation_is_matched_in_full():
    outer = [w(1, "It", "it", "PRON", 2, "nsubj:outer", PRS3), w(2, "is", "be", "AUX", 0, "root")]
    assert not pron3(outer)


def test_a_conjunction_root_hands_the_main_clause_to_its_predicate():
    # "And then he left.": the fragment's CCONJ root hands over to its first predicate conj dependent
    words = [w(1, "And", "and", "CCONJ", 0, "root"), w(2, "then", "then", "ADV", 4, "advmod"),
             w(3, "he", "he", "PRON", 4, "nsubj", PRS3), w(4, "left", "leave", "VERB", 1, "conj"),
             w(5, ".", ".", "PUNCT", 1, "punct")]
    assert pron3(words)
    head = ovl.main_clause_head(words, HANDOVER_UPOS, HANDOVER_REL, PRED_DEPS)
    assert head["form"] == "left"


def test_continuation_adds_pronoun_subjects_of_the_second_sentence():
    he = [w(1, "He", "he", "PRON", 2, "nsubj", PRS3), w(2, "barked", "bark", "VERB", 0, "root")]
    sents = [S_BIRDS, he, S_DOGS]
    keysets = [ovl.nominal_keys(s, NOMINAL, key) for s in sents]
    ov = ovl.overlap_flags(keysets)
    assert ov == [False, False]
    flags = ovl.continuation_flags(ov, [pron3(s) for s in sents])
    # pair (birds, he): continuous through the pronoun; pair (he, dogs): the pronoun sits in the first sentence
    assert flags == [True, False]
    assert ovl.share(flags) == 0.5


def test_continuation_checks_its_lengths():
    with pytest.raises(ValueError):
        ovl.continuation_flags([True], [True, False], pairs=[(0, 1), (1, 2)])


def test_parse_feats():
    assert ovl.parse_feats("_") == {}
    assert ovl.parse_feats(None) == {}
    assert ovl.parse_feats("Person=3|PronType=Prs") == {"Person": "3", "PronType": "Prs"}
    assert ovl.base_relation("nsubj:pass") == "nsubj"
