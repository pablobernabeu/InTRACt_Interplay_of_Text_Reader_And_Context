"""Tests of features.pages: word count, page count, pages per hundred words and page-break alignment."""

import math

import pytest

from intract_features import records
from intract_features.features import pages as P


def doc(*pages):
    return records.Document(story_id="S", lang="en-us", level="young", kind="generated", title="T", pages=pages)


def test_page_features():
    assert P.page_features(2, 17, 100) == {"word_count": 17, "page_count": 2,
                                           "pages_per_100_words": pytest.approx(200 / 17)}
    assert math.isnan(P.page_features(1, 0, 100)["pages_per_100_words"])


@pytest.mark.parametrize("sentences, inside", [
    ([(0, 8), (9, 20)], 0),  # each page ends a sentence
    ([(0, 9), (9, 20)], 0),  # a sentence that keeps the joining space still ends with its page
    ([(0, 14), (15, 20)], 1),  # "One two. Three" runs across the break
    ([], 0),
])
def test_page_breaks_inside_sentences(sentences, inside):
    d = doc("One two.", "Three four!")
    assert d.page_spans() == [(0, 8), (9, 20)]
    expected = {"page_breaks": 1, "page_breaks_inside_sentence": inside}
    assert P.page_break_alignment(d.page_spans(), sentences) == expected


def test_one_sentence_over_three_pages_and_a_single_page():
    d = doc("A", "b", "c.")
    assert P.page_break_alignment(d.page_spans(), [(0, len(d.text))]) == {"page_breaks": 2,
                                                                         "page_breaks_inside_sentence": 2}
    assert P.page_break_alignment(doc("Only page.").page_spans(), [(0, 10)]) == {"page_breaks": 0,
                                                                                "page_breaks_inside_sentence": 0}
