"""MEmoLon reading and text affect (features.affect) on a tiny lexicon in the release's layout."""

import statistics

import pytest

from intract_features.features import affect as aff

HEADER = "word\tvalence\tarousal\tdominance\tjoy\tanger\tsadness\tfear\tdisgust\n"
DEFAULT = "5.66\t4.16\t5.41\t2.57\t1.38\t1.35\t1.44\t1.33"  # MEmoLon en's unknown-word tuple


def lexicon_file(tmp_path, rows, last=f"<UNK>\t{DEFAULT}", newline="\n"):
    path = tmp_path / "en.tsv"
    body = HEADER + "".join(r + "\n" for r in rows) + last + newline
    path.write_bytes(body.replace("\n", "\r\n" if newline == "\r\n" else "\n").encode("utf-8"))
    return path


ROWS = [
    "happy\t8.00\t6.00\t6.1\t3.0\t1.1\t1.1\t1.1\t1.1",
    "Happy\t2.00\t2.00\t6.1\t3.0\t1.1\t1.1\t1.1\t1.1",
    "dog\t6.5\t4.5\t5.0\t2.0\t1.2\t1.2\t1.2\t1.2",
    "run\t6.0\t7.0\t5.0\t2.0\t1.2\t1.2\t1.2\t1.2",
    f"zzdefault\t{DEFAULT}",  # equal to the unknown-word default: no word-specific value
    "ice cream\t7.0\t5.0\t5.0\t2.0\t1.2\t1.2\t1.2\t1.2",  # multi-word: never matches a syntactic word
    "Tom\t1.0\t1.0\t5.0\t2.0\t1.2\t1.2\t1.2\t1.2",
]


def test_load_drops_default_rows_unknown_and_multiword(tmp_path):
    lex = aff.load_memolon(lexicon_file(tmp_path, ROWS))
    assert set(lex.values) == {"happy", "Happy", "dog", "run", "Tom"}
    assert lex.values["dog"] == (6.5, 4.5)
    assert lex.default == tuple(float(x) for x in DEFAULT.split("\t"))
    # rows and default rows include <UNK>, as verify-affect lexicon_profile.py counts them (4 default rows in en)
    assert (lex.rows, lex.default_rows, lex.multiword_rows) == (8, 2, 1)


def test_load_keeps_only_requested_keys(tmp_path):
    lex = aff.load_memolon(lexicon_file(tmp_path, ROWS), keys={"dog", "absent"})
    assert set(lex.values) == {"dog"}


def test_load_reads_crlf_files(tmp_path):
    lex = aff.load_memolon(lexicon_file(tmp_path, ROWS, newline="\r\n"))
    assert lex.values["run"] == (6.0, 7.0)


def test_load_refuses_a_file_without_the_final_unknown_row(tmp_path):
    with pytest.raises(ValueError, match="UNK"):
        aff.load_memolon(lexicon_file(tmp_path, ROWS[:2], last=ROWS[2]))


def test_load_refuses_an_unexpected_header(tmp_path):
    path = tmp_path / "bad.tsv"
    path.write_text("word\tvalence\n" + f"<UNK>\t{DEFAULT}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        aff.load_memolon(path)


def test_read_last_line(tmp_path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"a\nbb\nlast line\n\n")
    assert aff.read_last_line(p) == "last line"
    p.write_bytes(b"only")
    assert aff.read_last_line(p) == "only"
    p.write_bytes(("x" * 10000 + "\nend\r\n").encode())
    assert aff.read_last_line(p, chunk=7) == "end"
    p.write_bytes(b"a\nlast line\n \n\t\n")  # whitespace-only lines after the last row are not rows
    assert aff.read_last_line(p) == "last line"


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_load_refuses_non_finite_values(tmp_path, value):
    # float() reads them, and a non-finite value would stop the stage later, inside the standard deviation.
    rows = [*ROWS, f"odd\t{value}\t4.0\t5.0\t2.0\t1.2\t1.2\t1.2\t1.2"]
    with pytest.raises(ValueError, match="non-finite"):
        aff.load_memolon(lexicon_file(tmp_path, rows))


def word(form, lemma, upos):
    return {"id": 1, "form": form, "lemma": lemma, "upos": upos, "head": 0, "deprel": "root", "feats": "_"}


def test_candidate_keys_follow_the_registered_order():
    # S3: "Lookups try the language-aware lower case, the surface form and the lemma"
    order = ["lower", "surface", "lemma"]
    assert aff.candidate_keys(word("Happy", "happy", "ADJ"), str.lower, order) == ["happy", "Happy"]
    assert aff.candidate_keys(word("ran", "run", "VERB"), str.lower, order) == ["ran", "run"]
    assert aff.candidate_keys(word("ran", "_", "VERB"), str.lower, order) == ["ran"]
    with pytest.raises(ValueError):
        aff.candidate_keys(word("ran", "run", "VERB"), str.lower, ["fallback"])


def test_the_lower_case_key_wins_over_the_surface_form(tmp_path):
    lex = aff.load_memolon(lexicon_file(tmp_path, ROWS))
    v = aff.lookup(lex.values, aff.candidate_keys(word("Happy", "happy", "ADJ"), str.lower,
                                                   ["lower", "surface", "lemma"]))
    assert v == (8.0, 6.0)  # "happy", not the surface "Happy"
    v = aff.lookup(lex.values, aff.candidate_keys(word("ran", "run", "VERB"), str.lower,
                                                   ["lower", "surface", "lemma"]))
    assert v == (6.0, 7.0)  # through the lemma


def test_text_affect_with_and_without_the_name_exclusion(tmp_path):
    lex = aff.load_memolon(lexicon_file(tmp_path, ROWS))
    words = [word("Tom", "Tom", "NOUN"),  # a name type the parser tagged NOUN here
             word("ran", "run", "VERB"), word("the", "the", "DET"), word("happy", "happy", "ADJ"),
             word("dogs", "dog", "NOUN"), word("quickly", "quickly", "ADV"), word("Mia", "Mia", "PROPN")]
    names = [True, False, False, False, False, False, True]
    with_ex, without = aff.text_affect(words, names, lex.values, str.lower, ["lower", "surface", "lemma"],
                                       {"NOUN", "VERB", "ADJ", "ADV"}, ddof=1)
    # content tokens: Tom (name), ran, happy, dogs, quickly; PROPN and DET are never content
    assert (with_ex.content_tokens, with_ex.matched_tokens) == (4, 3)
    assert with_ex.valence_mean == pytest.approx((6.0 + 8.0 + 6.5) / 3)
    assert with_ex.arousal_mean == pytest.approx((7.0 + 6.0 + 4.5) / 3)
    assert with_ex.valence_sd == pytest.approx(statistics.stdev([6.0, 8.0, 6.5]))
    assert with_ex.coverage() == 0.75
    assert (without.content_tokens, without.matched_tokens) == (5, 4)  # "Tom" matches through its surface form
    assert without.valence_mean == pytest.approx((1.0 + 6.0 + 8.0 + 6.5) / 4)


def test_summaries_of_short_texts():
    s = aff.summarise([(5.0, 4.0)], 3, ddof=1)
    assert s.valence_mean == 5.0 and s.valence_sd is None  # a sample SD needs two tokens
    s0 = aff.summarise([(5.0, 4.0)], 3, ddof=0)
    assert s0.valence_sd == 0.0
    empty = aff.summarise([], 0, ddof=1)
    assert empty.valence_mean is None and empty.coverage() is None
    with pytest.raises(ValueError):
        aff.summarise([], 0, ddof=2)
