"""The registered Serbian transliteration (supplementary.qmd S3, the fifth script rule): the rule table against the
CLDR 47 file, the hand-built cases, the offset map back to the served text and the round-trip collisions. Ported from
the translated benchmark's checks of 3 November 2026; the ICU comparison stays there, since it needs icu.dll."""

import hashlib
import re
import unicodedata
from pathlib import Path

import pytest

from intract_features.text import sr_translit as T

XML = Path(__file__).resolve().parents[2] / "config" / "cldr" / "cldr47_Serbian-Latin-BGN.xml"
ACUTE, C_ACUTE, c_ACUTE, e_ACUTE = chr(0x301), chr(0x106), chr(0x107), chr(0xE9)


def tl(s):
    return T.transliterate(s).text


def test_the_rule_table_is_the_cldr_47_file():
    raw = XML.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == T.CLDR["sha256"], "the kept rule file is not the release-47 file"
    body = raw.decode("utf-8").split("<![CDATA[")[1].split("]]>")[0]
    lines = [ln for ln in (x.split("#", 1)[0].strip() for x in body.splitlines()) if ln]
    var = {m.group(1): m.group(2) for m in (re.fullmatch(r"\$(\w+)\s*=\s*\[(.*)\]\s*;", ln) for ln in lines) if m}
    assert set(var["lowerConsonants"]) | set(var["lowerVowels"]) == T.LOWER
    filt = re.fullmatch(r"::\s*\[(.*)\]\s*;", lines[0]).group(1)
    assert set(filt) == T.FILTER and len(filt) == 60
    assert lines[1] == ":: NFD (NFC) ;"
    plain, ctx = {}, {}
    for ln in lines[2:]:
        if ln.startswith("$"):
            continue
        m = re.fullmatch(r"(\S)\s*(\}\s*\$lower)?\s*→\s*(\S+)\s*;", ln)
        assert m, ln
        (ctx if m.group(2) else plain)[m.group(1)] = m.group(3)
    assert plain == T.RULES and ctx == T.BEFORE_LOWER and set(plain) == T.FILTER
    assert T.RULES["ћ"] == "c" + ACUTE and T.RULES["Ћ"] == "C" + ACUTE, "the file writes Ć and ć decomposed"
    assert all(unicodedata.decomposition(c) == "" for c in T.FILTER), "NFD on the filtered letters changes nothing"


@pytest.mark.parametrize(("served", "latin"), [
    ("Љубав", "Ljubav"), ("ЉУБАВ", "LJUBAV"), ("Љ.", "LJ."), ("Љ", "LJ"), ("Љу", "Lju"), ("Њива", "Njiva"),
    ("ЊИВА", "NJIVA"), ("Џеп", "Džep"), ("ЏЕП", "DŽEP"), ("Ђорђе", "Đorđe"), ("Ћирилица", C_ACUTE + "irilica"),
    ("ћутала", c_ACUTE + "utala"), ("Шума, жаба и чаша.", "Šuma, žaba i čaša."), ("Југославија", "Jugoslavija"),
    ("Љa", "LJa"),          # a Latin a after Љ is not in $lower, so LJ, as ICU writes it
    ("мы й", "mы й"),       # Cyrillic letters outside Serbian stay Cyrillic
    ("TV 3D «Да»!", "TV 3D «Da»!"),
])
def test_hand_built_cases(served, latin):
    assert tl(served) == latin


def test_every_serbian_letter_leaves_cyrillic_and_c_acute_is_composed():
    assert T.cldr_raw("ћ")[0] == "c" + ACUTE and tl("ћ") == c_ACUTE
    assert all(ord(c) < 0x0400 for c in tl("".join(sorted(T.FILTER))))


def test_the_offset_map_leads_back_to_the_served_text():
    s = "Љубав је ћутала, а Џон «Њ» не."
    x = T.transliterate(s)
    assert len(x.starts) == len(x.ends) == len(x.text)
    assert all(a < b for a, b in zip(x.starts, x.ends, strict=True))
    assert all(x.starts[i] <= x.starts[i + 1] for i in range(len(x.text) - 1))
    assert x.text == "Ljubav je " + c_ACUTE + "utala, a Džon «NJ» ne."
    assert x.served_span(0, 6) == (0, 5) and s[0:5] == "Љубав"
    k = x.text.index("Džon")
    a, b = x.served_span(k, k + 4)
    assert s[a:b] == "Џон"
    toks = x.text.replace(",", " ,").replace("«", "« ").replace("»", " »").replace(".", " .").split()
    forms, found, exact = T.served_forms(s, x, toks)
    assert found == exact == len(toks)
    assert forms[0] == "Љубав" and forms[toks.index("NJ")] == "Њ" and forms[toks.index("Džon")] == "Џон"
    y = T.transliterate("се" + ACUTE)   # NFC composes é, mapped to both served characters
    assert y.text == "s" + e_ACUTE and (y.starts[1], y.ends[1]) == (1, 3)
    assert T.served_forms("не", T.transliterate("не"), ["xx"])[1] == 0   # a token the parser altered is reported


def test_collisions_and_the_round_trip():
    assert tl("конј") == tl("коњ") == "konj"
    assert tl("лј") == tl("љ") == "lj"
    assert tl("дж") == tl("џ") == "dž"
    for w in ("Љубав", "ЉУБАВ", "Њ", "Џеп", "ЏЕП", "Ђорђе", "Ћирилица", "шума", "чаша", "жаба"):
        assert T.to_cyrillic(tl(w)) == w
    r = T.roundtrip(["конјугација коњ", "TV програм", "мы", "надживети"])
    assert r["tokens"] == 6 and r["tokens_changed_by_round_trip"] == 3
    assert r["by_cause"]["cyrillic_digraph_lj_nj_dz"]["tokens"] == 2
    assert r["by_cause"]["latin_letters_in_served"]["tokens"] == 1
    assert r["tokens_with_non_serbian_cyrillic_left_in_cyrillic"]["tokens"] == 1
    assert r["sentences_changed_by_round_trip"] == 3
