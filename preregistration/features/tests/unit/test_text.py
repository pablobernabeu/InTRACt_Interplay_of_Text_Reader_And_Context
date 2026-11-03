"""Tests of the text layer: normalisation, the registered word function, titles and keyed samples.

The references are verbatim copies of the benchmark functions the modules were promoted from:
lexrules.registered_words and is_reg_word (presub/error_model/scripts/lexrules.py) and seglib2.normalise
(presub/translated_union/scripts/seglib2.py, SHA-256 60b1e485ad3430f951f66f69df49083b76dd621218f960e9f4b92cbcea0d8e9c).
Two copies of lexrules.py and of tu_common.py exist, and the promoted functions are the same in both:
the copies kept in presub/_pre_20261103 (lexrules.py SHA-256
2dc7fac3c2806948d81bcaa744ceb91dc5c8e595355acb8122ecc678800c133c, tu_common.py SHA-256
5ef80254e3d883dd3ac324fe43aa0df3fcf2e8bf76b6352f7aa61b6904904bed) and the presub/ copies edited on
3 November 2026 (lexrules.py SHA-256 fed2de71bc29c668b03af7d1b657cfbeb7669dd411c6bdec36258c2f1be7f9e1,
tu_common.py SHA-256 aae704e68737f0d3470a21858077fe2c53ce3bd1429dfcdd7cef9138e6ce3e07). The benchmark
files are not in this repository. When the environment variable INTRACT_BENCH_ROOT names the folder
that holds presub/, every copy present is loaded from its source and compared.
"""

import ast
import hashlib
import os
import random
import re
import tomllib
import unicodedata
import unicodedata as ud
from pathlib import Path

import pytest

from intract_features.text import keyed, titles
from intract_features.text.normalise import (
    DELETED,
    FORMAT_CHARACTER_RANGES,
    Normaliser,
    characters,
    normalise,
)
from intract_features.text.words import (
    LINE_BREAK,
    WHITE_SPACE,
    count_words,
    is_word_token,
    whitespace_tokens,
    word_extents,
    word_spans,
    words,
)

FEATURES = Path(__file__).resolve().parents[2]

# ---- verbatim references (the whitespace string is written with escapes for the same 25 code points) ----
REF_WS = ("\x09\x0a\x0b\x0c\x0d \x85\xa0\U00001680\U00002000\U00002001\U00002002\U00002003\U00002004\U00002005"
          "\U00002006\U00002007\U00002008\U00002009\U0000200a\U00002028\U00002029\U0000202f\U0000205f\U00003000")
REF_WS_RE = re.compile("[" + REF_WS + "]+")


def ref_is_reg_word(tok):
    """At least one letter (other than a modifier letter) or digit."""
    for ch in tok:
        c = ud.category(ch)
        if c[0] == "N" or (c[0] == "L" and c != "Lm"):
            return True
    return False


def ref_registered_words(text):
    return sum(1 for t in REF_WS_RE.split(text or "") if t and ref_is_reg_word(t))


REF_DELETE = "".join(chr(c) for c in list(range(0x200B, 0x2010)) + list(range(0x202A, 0x202F))
                     + list(range(0x2060, 0x206A)) + [0x061C, 0xFEFF])
REF_DEL_RE = re.compile("[" + re.escape(REF_DELETE) + "]")


def ref_normalise(s):
    return REF_DEL_RE.sub("", unicodedata.normalize("NFC", s))


# ---- fixtures ----
POOL = (
    list(REF_WS) + ["\x1c", "\x1d", "\x1e", "\x1f"]  # White_Space, and the four separators str.split adds
    + list("abcXYZ019.,;:!?'\"-()[]")
    + list("ʰʼˈーๆ々ゝ")  # modifier letters (Lm)
    + ["\N{COMBINING ACUTE ACCENT}", "\N{THAI CHARACTER MAI EK}", "\N{HEBREW POINT HIRIQ}",
       "\N{COMBINING DIAERESIS}"]
    + list("½Ⅻ²٣๓")  # numbers of categories No, Nl and Nd
    + list("éßαжאع中ก한")
    + list("🙂€©«»“”—–…¿¡「」")
    + ["\N{ZERO WIDTH JOINER}", "\N{ZERO WIDTH NON-JOINER}", "\N{ZERO WIDTH NO-BREAK SPACE}",
       "\N{LEFT-TO-RIGHT MARK}", "\N{LEFT-TO-RIGHT ISOLATE}", "\N{SOFT HYPHEN}", "\N{MONGOLIAN VOWEL SEPARATOR}",
       "e\N{COMBINING ACUTE ACCENT}", "A\N{COMBINING RING ABOVE}"]
)


def random_strings(n=5000, seed=20261103, max_len=40):
    rng = random.Random(seed)
    return ["".join(rng.choice(POOL) for _ in range(rng.randint(0, max_len))) for _ in range(n)]


FIXED = [
    "", " ", "one", "one two", "  one   two  ", "one, two.", "— one —", "« Bonjour » dit-il",
    "ดี ๆ นะ", "ʰ", "aʰ", "ʰa", "ʰ ʼ", "3", "½", "Ⅻ", "x²", "...", "!!! ???", "🙂", "🙂 ok",
    "a\xa0b", "a\N{NARROW NO-BREAK SPACE}b", "a\N{IDEOGRAPHIC SPACE}b", "a\x1cb", "a\x1fb", "line\nbreak",
    "tab\tbed", "a\N{LINE SEPARATOR}b", "e\N{COMBINING ACUTE ACCENT}", "\N{COMBINING ACUTE ACCENT}", "don't",
    "co-op", "U.S.A.", "1,000", "中文", "한국어 문장", "שלום עולם", "مرحبا بالعالم", "a\N{ZERO WIDTH JOINER}b",
    "a \N{ZERO WIDTH JOINER} b",
]


# ---- the word function ----
def test_white_space_is_the_unicode_property():
    isspace = {chr(c) for c in range(0x110000) if chr(c).isspace()}
    assert isspace - set("\x1c\x1d\x1e\x1f") == WHITE_SPACE
    assert set(REF_WS) == WHITE_SPACE
    assert len(WHITE_SPACE) == 25


@pytest.mark.parametrize("text", FIXED)
def test_count_equals_lexrules_on_fixed_strings(text):
    assert count_words(text) == ref_registered_words(text)
    assert len(word_spans(text)) == ref_registered_words(text)


def test_count_equals_lexrules_on_random_strings():
    for text in random_strings():
        assert count_words(text) == ref_registered_words(text), repr(text)


def test_none_counts_as_empty_as_in_lexrules():
    assert count_words(None) == ref_registered_words(None) == 0


def test_every_white_space_character_splits_and_the_separators_do_not():
    for ch in WHITE_SPACE:
        assert count_words(f"a{ch}b") == 2, f"U+{ord(ch):04X}"
    for ch in "\x1c\x1d\x1e\x1f":
        assert count_words(f"a{ch}b") == 1  # str.split() would give 2
        assert len(f"a{ch}b".split()) == 2


def test_modifier_letters_alone_are_not_a_word():
    assert count_words("ดี ๆ") == 1
    assert count_words("ʰ ʼ ˈ") == 0
    assert count_words("aʰ") == count_words("ʰa") == 1
    assert not is_word_token("ーー") and is_word_token("ー2")


def test_spans_are_word_tokens_with_their_anchor():
    for text in random_strings(n=2000, seed=7):
        ws = words(text)
        tokens = whitespace_tokens(text)
        assert [(w.start, w.end) for w in ws] == [t for t in tokens if is_word_token(text[t[0]:t[1]])]
        previous_end = -1
        for w in ws:
            assert previous_end <= w.start < w.end <= len(text)
            assert not set(text[w.start:w.end]) & WHITE_SPACE
            assert w.start <= w.anchor < w.end
            cat = ud.category(text[w.anchor])
            assert cat[0] == "N" or (cat[0] == "L" and cat != "Lm")
            assert not any(ref_is_reg_word(ch) for ch in text[w.start:w.anchor])
            previous_end = w.end


def test_spans_on_an_example():
    text = "“Run!” said Tom — and ran."
    assert [text[a:b] for a, b in word_spans(text)] == ["“Run!”", "said", "Tom", "and", "ran."]
    assert [text[w.anchor] for w in words(text)] == ["R", "s", "T", "a", "r"]


# ---- attachment (feature plan v3, PENDING the Feature Specification) ----
def extents(text, **kw):
    return [text[a:b] for a, b in word_extents(text, **kw)]


def test_punctuation_joins_the_preceding_word():
    assert extents("Tom , said Ann .") == ["Tom ,", "said", "Ann ."]
    assert extents("Hola — dijo") == ["Hola —", "dijo"]


def test_text_initial_tokens_join_the_following_word():
    assert extents("... and then") == ["... and", "then"]
    assert extents("ʰ ok") == ["ʰ ok"]


def test_opening_marks_join_the_following_word():
    text = "Il dit « Bonjour » ."
    assert extents(text, openers={"«"}) == ["Il", "dit", "« Bonjour » ."]
    assert extents(text) == ["Il", "dit «", "Bonjour » ."]


def test_modifier_letter_tokens_join_the_preceding_word():
    assert extents("ดี ๆ นะ") == ["ดี ๆ", "นะ"]


def test_turn_initial_dash_joins_the_following_word():
    assert extents("Hola.\n— ¿Qué tal?") == ["Hola.", "— ¿Qué", "tal?"]
    assert extents("Hola.\n  — Bien") == ["Hola.", "— Bien"]
    assert extents("Hola. — Bien") == ["Hola. —", "Bien"]
    assert extents("Hola. — Bien", breaks={6}) == ["Hola.", "— Bien"]


def test_one_line_break_for_every_rule():
    # Gap G9: the line feed decoded from the delivery's escape is the only line break, for turn-initial
    # dashes as for page titles; other characters str.splitlines() honours are whitespace inside a line.
    assert LINE_BREAK == "\n" and titles.LINE_BREAK is LINE_BREAK
    for other in ("\r", "\x0b", "\x0c", "\x85", "\N{LINE SEPARATOR}", "\N{PARAGRAPH SEPARATOR}"):
        assert extents(f"Hola.{other}— Bien") == [f"Hola.{other}—", "Bien"], repr(other)
        assert find([f"Chapter Two{other}The fox ran away."]) == [], repr(other)
        assert titles.line_count(f"a{other}b") == 1
    assert titles.line_count("a\nb\nc") == 3


def test_extents_partition_the_words_in_order():
    assert word_extents("— ...") == []
    for text in random_strings(n=2000, seed=11):
        ext = word_extents(text, openers={"«", "“", "「"}, breaks={5})
        spans = word_spans(text)
        assert len(ext) == len(spans) == count_words(text)
        previous_end = -1
        for (a, b), (s, e) in zip(ext, spans, strict=True):
            assert previous_end <= a <= s < e <= b
            previous_end = b


# ---- normalisation ----
def test_deleted_set_is_the_benchmarks():
    assert DELETED == set(REF_DELETE) == characters(FORMAT_CHARACTER_RANGES)
    assert len(DELETED) == 22


def test_normalise_equals_the_benchmark_on_random_strings():
    for text in random_strings(n=3000, seed=3) + FIXED:
        assert normalise(text) == ref_normalise(text), repr(text)


def test_normaliser_built_from_the_configuration_equals_normalise():
    cfg = tomllib.loads((FEATURES / "config" / "stages" / "documents.toml").read_text(encoding="utf-8"))
    ranges = cfg["normalise"]["delete_ranges"]
    assert [tuple(r) for r in ranges] == list(FORMAT_CHARACTER_RANGES)
    assert cfg["normalise"]["form"] == "NFC"
    norm = Normaliser(ranges, cfg["normalise"]["form"])
    for text in random_strings(n=500, seed=5):
        assert norm(text) == normalise(text)


def test_with_stats_counts_deletions_and_nfc_changes():
    norm = Normaliser()
    assert norm.with_stats("a\N{ZERO WIDTH SPACE}b\N{ZERO WIDTH NO-BREAK SPACE}") == ("ab", 2, False)
    assert norm.with_stats("e\N{COMBINING ACUTE ACCENT}") == ("\xe9", 0, True)
    assert norm.with_stats("plain") == ("plain", 0, False)


def test_nfc_runs_before_deletion_as_in_the_benchmark():
    # A deleted joiner leaves the base and the mark uncomposed; a second call would compose them,
    # which is why every text is normalised exactly once.
    once = normalise("e\N{ZERO WIDTH JOINER}\N{COMBINING ACUTE ACCENT}")
    assert once == "e\N{COMBINING ACUTE ACCENT}" != unicodedata.normalize("NFC", once)
    assert normalise(once) == "\xe9"


def test_kept_format_characters():
    assert normalise("co\N{SOFT HYPHEN}op") == "co\N{SOFT HYPHEN}op"  # not in the registered set
    assert normalise("a\N{ZERO WIDTH SPACE}b") == "ab"


def test_only_nfc_is_accepted():
    with pytest.raises(ValueError):
        Normaliser(FORMAT_CHARACTER_RANGES, "NFKC")
    with pytest.raises(ValueError):
        characters([(0x2010, 0x200F)])


# ---- titles (S3) ----
MARKS = frozenset(".!?…．！？؟")


def is_title(line, test="anywhere"):
    return titles.is_title_line(line, max_words=8, terminal_marks=MARKS, final_mark_test=test)


def test_title_line_rule():
    assert is_title("Chapter One")
    assert is_title("One two three four five six seven eight")
    assert not is_title("One two three four five six seven eight nine")
    assert not is_title("The End.")
    assert not is_title("")
    assert not is_title("— …")  # a title needs a word


def test_final_mark_switch():
    assert not is_title("Dr. Fox and the Moon")
    assert is_title("Dr. Fox and the Moon", "line_end")
    assert not is_title("“Run!”", "line_end")  # closing quotation marks are skipped
    assert is_title("“Run, Tom”", "line_end")
    with pytest.raises(ValueError):
        is_title("x", "somewhere")


def find(pages, rule="multiline", test="anywhere"):
    return titles.find_page_titles(pages, page_rule=rule, max_words=8, terminal_marks=MARKS, final_mark_test=test)


def test_page_rules():
    pages = ["Chapter Two\nThe fox ran away.", "The End", "Once upon a time.\nMore text.", "Two lines\nhere"]
    assert [(t.page, t.text, t.lines) for t in find(pages)] == [(0, "Chapter Two", 2), (3, "Two lines", 2)]
    assert [t.page for t in find(pages, "every_page")] == [0, 1, 3]
    assert find(pages, "off") == []
    with pytest.raises(ValueError):
        find(pages, "sometimes")


def test_exclude_page_titles_keeps_page_indices():
    pages = ("Chapter Two\nThe fox ran away.", "The End", "A plain page.")
    found = find(pages, "every_page")
    assert titles.exclude_page_titles(pages, found) == ("The fox ran away.", "", "A plain page.")
    # Under every_page, any short single-line page without a terminal mark is a title, such as a
    # sentence continued across a page break; the default, multiline, never takes one.
    assert [t.page for t in find(("Once upon a time, in a land", "far away."), "every_page")] == [0]
    assert find(("Once upon a time, in a land", "far away.")) == []
    assert titles.PageTitle.from_json(found[0].to_json()) == found[0]
    with pytest.raises(ValueError):
        titles.exclude_page_titles(("Other\ntext",), found[:1])


def test_titles_are_carried_by_line_index_where_line_structure_survives():
    english = [titles.PageTitle(page=0, text="Chapter Two", lines=2), titles.PageTitle(page=1, text="Song", lines=3)]
    pages = ["Capítulo dos\nEl zorro huyó.", "Canción\nuna línea"]
    carried, lost = titles.carry_page_titles(english, 2, pages)
    assert [(t.page, t.text) for t in carried] == [(0, "Capítulo dos")]
    assert lost == 1
    assert titles.carry_page_titles(english, 3, pages) == ([], 2)


def test_carry_rule_text_lines_needs_every_page_to_keep_its_lines():
    english = [titles.PageTitle(page=0, text="Chapter Two", lines=2)]
    pages = ["Capítulo dos\nEl zorro huyó.", "Una línea."]
    assert titles.carry_page_titles(english, 2, pages, rule="text_lines", english_lines=[2, 1])[1] == 0
    assert titles.carry_page_titles(english, 2, pages, rule="text_lines", english_lines=[2, 2]) == ([], 1)
    assert len(titles.carry_page_titles(english, 2, pages, rule="page_lines", english_lines=[2, 2])[0]) == 1
    with pytest.raises(ValueError, match="line counts"):
        titles.carry_page_titles(english, 2, pages, rule="text_lines")
    with pytest.raises(ValueError, match="carry_rule"):
        titles.carry_page_titles(english, 2, pages, rule="by_luck")


def test_served_line_counts_restore_excluded_titles():
    served = ("Chapter Two\nThe fox ran away.", "The End", "Song\nLa\nLa.")
    found = find(served, "every_page")
    stored = titles.exclude_page_titles(served, found)
    assert stored == ("The fox ran away.", "", "La\nLa.")
    assert titles.served_line_counts(stored, found) == [titles.line_count(p) for p in served] == [2, 1, 3]


# ---- keyed samples ----
def test_keyed_order_reads_only_the_ids():
    ids = [f"S{i}" for i in range(500)]
    order = keyed.keyed_order(ids, "keyed_sample")
    assert order == keyed.keyed_order(list(reversed(ids)), "keyed_sample")
    assert sorted(order) == sorted(ids)
    assert order != keyed.keyed_order(ids, "another_purpose")
    digest = [hashlib.sha256(f"intract|keyed_sample|v1|{s}".encode()).hexdigest() for s in order]
    assert digest == sorted(digest)


def test_a_larger_sample_contains_a_smaller_one():
    ids = [str(i) for i in range(1000)]
    small, large = keyed.keyed_sample(ids, 20, "keyed_sample"), keyed.keyed_sample(ids, 200, "keyed_sample")
    assert large[:20] == small
    assert keyed.keyed_sample(ids[:10], 2000, "keyed_sample") == keyed.keyed_order(ids[:10], "keyed_sample")
    ranks = keyed.keyed_ranks(ids, "keyed_sample")
    assert {s for s, r in ranks.items() if r < 20} == set(small)


def test_keyed_cutoffs_decide_membership_from_a_storys_own_hash():
    ids = [f"S{i}" for i in range(300)]
    cutoffs = keyed.keyed_cutoffs(ids, (20, 200, 500), "keyed_sample")
    assert cutoffs[500] is None  # fewer stories than the sample, so all of them are in it
    for n in (20, 200):
        h, last = cutoffs[n]
        assert last == keyed.keyed_order(ids, "keyed_sample")[n - 1]
        assert h == hashlib.sha256(f"intract|keyed_sample|v1|{last}".encode()).hexdigest()
        members = {s for s in ids if keyed.in_keyed_sample(keyed.keyed_hash("keyed_sample", s), s, cutoffs[n])}
        assert members == set(keyed.keyed_sample(ids, n, "keyed_sample"))
    assert keyed.in_keyed_sample("f" * 64, "x", None)
    with pytest.raises(ValueError):
        keyed.keyed_cutoffs(ids, (0,), "keyed_sample")


def test_keyed_settings_and_errors():
    assert keyed.key_settings({"keys": {"prefix": "p", "version": "v9"}}) == {"prefix": "p", "version": "v9"}
    assert keyed.key_settings({}) == {"prefix": "intract", "version": "v1"}
    ids = [str(i) for i in range(50)]
    expected = sorted(ids, key=lambda s: hashlib.sha256(f"p|x|v9|{s}".encode()).hexdigest())
    assert keyed.keyed_order(ids, "x", prefix="p", version="v9") == expected
    with pytest.raises(ValueError):
        keyed.keyed_order(["a", "a"], "keyed_sample")
    with pytest.raises(ValueError):
        keyed.keyed_sample(["a"], -1, "keyed_sample")
    with pytest.raises(ValueError):
        keyed.keyed_order(["a"], "")


# ---- the originals, when the benchmark folder is available locally ----
def _load(path: Path, names: set[str], namespace: dict) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
             or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) in names for t in n.targets))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


BENCH = os.environ.get("INTRACT_BENCH_ROOT")


@pytest.mark.skipif(not BENCH, reason="INTRACT_BENCH_ROOT is not set")
@pytest.mark.parametrize("copy", ["presub", "presub/_pre_20261103"])
def test_against_the_benchmark_originals(copy):
    root = Path(BENCH) / copy
    lexrules = root / "error_model" / "scripts" / "lexrules.py"
    if not lexrules.is_file():
        pytest.skip(f"{copy} is not in the benchmark folder")
    lex = _load(lexrules, {"WS", "WS_RE", "is_reg_word", "registered_words"}, {"re": re, "ud": ud})
    tuc = _load(root / "translated_union" / "scripts" / "tu_common.py", {"DELETE", "DEL_RE", "normalise"},
                {"re": re, "unicodedata": unicodedata})
    # seglib2.py has one copy, in presub/.
    seglib2 = Path(BENCH) / "presub" / "translated_union" / "scripts" / "seglib2.py"
    seg = _load(seglib2, {"DELETE", "DEL_RE", "normalise"}, {"re": re, "unicodedata": unicodedata})
    assert set(lex["WS"]) == WHITE_SPACE
    assert set(seg["DELETE"]) == set(tuc["DELETE"]) == DELETED
    for text in random_strings(n=3000, seed=13) + FIXED:
        assert count_words(text) == lex["registered_words"](text), repr(text)
        assert normalise(text) == seg["normalise"](text) == tuc["normalise"](text), repr(text)
