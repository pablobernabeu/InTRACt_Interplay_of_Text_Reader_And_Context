"""The name inventory and covariates (features.names).

The features_discourse stage end to end, which builds the inventory across shards, is tested in
test_features_discourse.py.
"""

import math

import pytest

from intract_features.features import names as nam


def w(form, upos, i=1, lemma=None):
    return {"id": i, "form": form, "lemma": lemma or form, "upos": upos, "head": 0, "deprel": "dep", "feats": "_"}


def key(word):
    return word["form"].lower()


def test_a_type_is_a_name_if_at_least_half_its_occurrences_are_proper_nouns():
    counts = nam.NameCounts()
    counts.add([w("Tom", "PROPN"), w("ran", "VERB"), w(".", "PUNCT")], key, {"PROPN"})
    counts.add([w("Tom", "PROPN"), w("Rose", "PROPN"), w("rose", "VERB")], key, {"PROPN"})
    counts.add([w("May", "PROPN"), w("may", "AUX"), w("rose", "NOUN"), w("Tom", "PROPN")], key, {"PROPN"})
    inv = counts.inventory(0.5)
    # tom 3/3; may 1/2 is exactly half, so a name; rose 1/3 is not
    assert inv == {"tom", "may"}
    assert "." not in counts.total  # punctuation is not an occurrence (bench_names_tagonly.is_punct)


def test_x_counts_as_a_name_tag_only_where_configured():
    counts = nam.NameCounts()
    counts.add([w("Zaid", "X")], key, {"PROPN"})
    assert counts.inventory(0.5) == frozenset()
    counts2 = nam.NameCounts()
    counts2.add([w("Zaid", "X")], key, {"PROPN", "X"})  # Arabic: "or as X in Arabic"
    assert counts2.inventory(0.5) == {"zaid"}


def test_the_inventory_is_decided_over_every_shard():
    a, b = nam.NameCounts(), nam.NameCounts()
    a.add([w("Dragon", "PROPN")], key, {"PROPN"})
    b.add([w("dragon", "NOUN"), w("dragon", "NOUN")], key, {"PROPN"})
    assert a.inventory(0.5) == {"dragon"}  # one shard alone would call it a name
    a.merge(b)
    assert a.inventory(0.5) == frozenset()  # 1 of 3 over the catalogue
    assert nam.NameCounts.from_json(a.to_json()).inventory(0.5) == frozenset()


def test_the_mask_flags_every_occurrence_of_a_name_type_whatever_its_tag():
    flags = nam.name_flags([w("Tom", "NOUN"), w("ran", "VERB"), w("!", "PUNCT")], {"tom"}, key)
    assert flags == [True, False, False]


def test_words_overlapping_counts_each_word_once():
    # "Tom's dog met Ann-Lee." with tokens Tom ('s) ... Ann - Lee
    word_spans = [(0, 5), (6, 9), (10, 13), (14, 22)]
    name_spans = [(0, 3), (14, 17), (18, 21)]
    assert nam.words_overlapping(word_spans, name_spans) == 2
    assert nam.words_overlapping(word_spans, []) == 0


def test_name_measures():
    m = nam.NameMeasures(n_words=10, name_words=2, name_tokens=3, name_types=2)
    assert m.share() == 0.2
    assert m.share_elogit(0.5) == pytest.approx(math.log(2.5 / 8.5))
    assert m.types_per(100) == 20.0
    assert m.tokens_per_type() == 1.5
    empty = nam.NameMeasures(n_words=0, name_words=0, name_tokens=0, name_types=0)
    assert empty.share() is None and empty.share_elogit(0.5) is None and empty.tokens_per_type() is None
    none = nam.NameMeasures(n_words=10, name_words=0, name_tokens=0, name_types=0)
    assert none.share() == 0.0 and none.share_elogit(0.5) == pytest.approx(math.log(0.5 / 10.5))


def test_inventory_file_round_trip_and_digest(tmp_path):
    p = tmp_path / "inv" / "name_inventory.txt"
    nam.write_inventory(p, {"tom", "mia", "o'brien"})
    assert p.read_text(encoding="utf-8") == "mia\no'brien\ntom\n"
    assert nam.read_inventory(p) == {"tom", "mia", "o'brien"}
    assert nam.inventory_digest({"b", "a"}) == nam.inventory_digest(["a", "b"])
    with pytest.raises(ValueError):
        nam.write_inventory(p, {"bad\ntype"})
    # A checkout that converts line ends gives CRLF; the types are read the same, as lexical.load_inventory reads them.
    crlf = tmp_path / "crlf.txt"
    crlf.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    assert nam.read_inventory(crlf) == {"tom", "mia", "o'brien"}
