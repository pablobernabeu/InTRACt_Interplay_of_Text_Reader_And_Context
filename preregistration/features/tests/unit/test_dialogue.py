"""The registered direct-speech detector and dialogue share (features.dialogue)."""

import tomllib
from pathlib import Path

import pytest

from intract_features.features import dialogue as dia

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def stage_cfg():
    return tomllib.loads((ROOT / "config" / "stages" / "features_discourse.toml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def en(stage_cfg):
    quotes = tomllib.loads((ROOT / "config" / "languages.toml").read_text(encoding="utf-8"))["en-us"]["quotes"]
    return dia.QuoteInventory.from_config(quotes, stage_cfg["dialogue"], "en")


def words_of(text):
    """(start, end, anchor) of each whitespace token with a letter or digit, as text.words gives them."""
    out, i = [], 0
    for tok in text.split(" "):
        anchor = next((i + k for k, ch in enumerate(tok) if ch.isalnum()), None)
        if anchor is not None:
            out.append(anchor)
        i += len(tok) + 1
    return out


def inside_words(pages, inv):
    """The whitespace tokens whose anchor lies inside speech, and speech_words' counts."""
    text = " ".join(pages)
    mask = dia.speech_mask(pages, inv)
    assert len(mask) == len(text)
    anchors = words_of(text)
    tokens = [text[text.rfind(" ", 0, a) + 1:].split(" ")[0] for a in anchors if mask[a]]
    return tokens, dia.speech_words(mask, anchors)


def test_english_inventory_is_cldr_47_plus_the_straight_double_quote(en):
    # CLDR 47 en: quotationStart/End U+201C/U+201D, alternate U+2018/U+2019; the straight quote is an admitted mark
    assert en.asymmetric() == {"“": {"”"}, "‘": {"’"}}
    assert en.symmetric() == {'"'}


def test_typographic_double_quotes(en):
    found, (inside, total) = inside_words(["“Come here, Tom!” said Mia."], en)
    assert found == ["“Come", "here,", "Tom!”"]
    assert (inside, total) == (3, 5)
    assert dia.share(inside, total) == 0.6


def test_apostrophes_never_close_a_quotation(en):
    found, _ = inside_words(["“Don’t go,” said Ann’s mum."], en)
    assert found == ["“Don’t", "go,”"]


def test_the_alternate_pair_with_its_apostrophe_guard(en):
    found, _ = inside_words(["‘Run, Tom’s dog!’ she cried. It’s late."], en)
    assert found == ["‘Run,", "Tom’s", "dog!’"]


def test_straight_double_quotes_take_their_direction_from_spacing(en):
    found, _ = inside_words(['He said "go home" and "stay there" to Tom.'], en)
    assert found == ['"go', 'home"', '"stay', 'there"']


def test_unspaced_straight_quotes_toggle(en):
    # neither side is a space, so the first mark opens and the second closes (safeguard_decomposition.dir_only)
    mask = dia.speech_mask(['a"bc"d'], en)
    assert mask == [False, False, True, True, False, False]


def test_an_opener_unmatched_at_the_end_of_its_page_closes_there(en):
    found, (inside, total) = inside_words(["“Wait for", "me.” Tom ran."], en)
    # page 1 closes the quotation; page 2's closing mark has no opener, so "me." is outside
    assert found == ["“Wait", "for"]  # whole tokens, though each word counts by its anchor
    assert (inside, total) == (2, 5)


def test_a_straight_opener_also_closes_at_its_page_end(en):
    found, _ = inside_words(['"Hi there', 'Tom said."'], en)
    assert found == ['"Hi', "there"]


def test_the_joining_space_is_never_inside(en):
    mask = dia.speech_mask(["“Open", "still”"], en)
    assert mask[len("“Open")] is False


def test_a_line_initial_dash_opens_a_turn_to_the_end_of_the_line(en):
    page = "— Come here!\nShe came."
    mask = dia.speech_mask([page], en)
    assert [page[k] for k in range(len(page)) if mask[k]] == list(" Come here!")
    # a dash inside a line is not a turn
    assert not any(dia.speech_mask(["She came — slowly."], en))


def test_dash_turns_can_be_switched_off(stage_cfg):
    cfg = {**stage_cfg["dialogue"], "dash_turns": False}
    inv = dia.QuoteInventory.from_config([["“", "”"]], cfg, "en")
    assert not any(dia.speech_mask(["— Come here!"], inv))


def test_hebrew_marks_between_letters_are_gershayim(stage_cfg):
    inv = dia.QuoteInventory.from_config([['"', '"']], stage_cfg["dialogue"], "he")
    # U+05E6 U+05D4 " U+05DC: letters on both sides, so not a delimiter
    assert not any(dia.speech_mask(['צה"ל אמר'], inv))
    found = dia.speech_mask(['אמר "שלום" לו'], inv)
    assert any(found)


def test_text_without_words_has_no_share():
    assert dia.speech_words([], []) == (0, 0)
    assert dia.share(0, 0) is None


def test_sentence_level_speech_status(en):
    text = "“Hi,” said Tom. Then he left."
    mask = dia.speech_mask([text], en)
    anchors = words_of(text)
    assert dia.spans_with_speech(mask, anchors, [(0, 15), (16, len(text))]) == [True, False]
