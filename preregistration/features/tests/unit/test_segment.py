"""Tests of segment/ and the sat and seg_check stages.

The promoted code must reproduce the benchmark exactly, so this file keeps reference copies of the
originals, verbatim apart from names, and compares the two on hand-built and random inputs:

- union_lib.py (SHA-256 d44fd665777e812e...): registered_bounds, the character helpers and the search;
- seglib2.py (60b1e485ad3430f9...): colon_rule;
- tu_common.py (aae704e68737f0d3...): the SEG-3 rule, internal_orth_ends, canon, prf and boot_prf;
- tu3_union.py (bea6befd057739c5...): summ;
- wtpsplit 2.2.2, wtpsplit/__init__.py (72b5daa2a8162333...) and wtpsplit/utils/__init__.py
  (2eca89e710ccfb67...): indices_to_sentences and the split_on_input_newlines step. wtpsplit is MIT
  licensed, copyright (c) 2024 Benjamin Minixhofer, Markus Frohmann and Igor Sterner; its permission
  notice, which applies to the copied lines, is reproduced in ../../LICENCES.md.

Tests that need NumPy skip without it. Two golden tests also need the translated-union strand's local
files (INTRACT_TU_DIR, the folder holding earlier/ and results/): they reproduce the port test's
registered F1 values and the English agreement with the rule on the benchmark's 382 boundaries.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import math
import os
import random
import re
import struct
import sys
import unicodedata
from pathlib import Path

import pytest

from intract_features import cli, records
from intract_features import config as config_mod
from intract_features.segment import (
    SENTENCE_FIELDS,
    boundaries_of,
    page_anchors,
    page_index,
    rules,
    sentences_from_record,
)
from intract_features.segment import diagnostics as diag
from intract_features.segment import sat as sat_mod
from intract_features.segment import union as union_mod
from intract_features.stages import sat as sat_stage
from intract_features.stages import seg_check as seg_check_stage

try:
    import numpy as np
except ImportError:  # the shared development environment has no NumPy; the tests that need it skip
    np = None

needs_numpy = pytest.mark.skipif(np is None, reason="needs NumPy")
CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CFG = config_mod.load(CONFIG_DIR)
SAT_CFG = CFG["stages"]["sat"]
CHECK_CFG = CFG["stages"]["seg_check"]
SETTINGS = sat_mod.SatSettings.from_config(SAT_CFG)
RUNTIME = sat_mod.RuntimeSettings.from_config(SAT_CFG)
USET = union_mod.UnionSettings.from_config(SAT_CFG)
RULE = rules.EnglishRule.from_config(CHECK_CFG["rule"])
ORTH = rules.OrthRule.from_config(CHECK_CFG["orth_rule"])
QUOTES = frozenset(CHECK_CFG["scorer"]["quotes"])


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


# ============================================================ reference copies of the originals

# ---- wtpsplit 2.2.2: utils.indices_to_sentences and SaT._split's newline step (MIT licence)
def ref_indices_to_sentences(text, indices, strip_whitespace=False):
    sentences = []
    offset = 0
    idx = 0
    for idx in indices:
        idx = idx + 1
        while idx < len(text) and text[idx].isspace():
            idx += 1
        sentence = text[offset:idx]
        if strip_whitespace:
            sentence = sentence.strip()
        if len(sentence) > 0:
            sentences.append(sentence)
        offset = idx
    if idx != len(text):
        last_sentence = text[idx:]
        if strip_whitespace:
            last_sentence = last_sentence.strip()
        if len(last_sentence) > 0:
            sentences.append(last_sentence)
    return sentences


def ref_wtpsplit_split(text, probs, threshold):
    """SaT.split(threshold=..., strip_whitespace=False, split_on_input_newlines=True) from probabilities."""
    thr = f32(threshold)  # np.where(probs > threshold) compares a float32 array in float32
    sentences = ref_indices_to_sentences(text, [i for i, v in enumerate(probs) if v > thr], strip_whitespace=False)
    new_sentences = []
    for i, sentence in enumerate(sentences):
        if i < len(sentences) - 1 and sentence.endswith("\n"):
            sentence = sentence[:-1]
        new_sentences.extend(sentence.split("\n"))
    return new_sentences


# ---- seglib2.colon_rule
def ref_colon_rule(segs):
    out = []
    for s in segs:
        if out and re.search(r"[:：]\s*$", out[-1]):
            out[-1] += s
        else:
            out.append(s)
    return out


# ---- union_lib (registered mode)
REF_FLOOR = 1e-5
REF_EPS = 1e-6
REF_TERMINAL_BASE = set(".!?…؟。！？．")
REF_CLOSERS = set("\"'”’»›」』)]）")
REF_QANCHOR = set("\"“”„‟«»「」『』")
REF_COLONS = (":", "：")


def ref_terminal_set(lang):
    greek = lang in ("el", "ell_Grek")
    return REF_TERMINAL_BASE | ({";"} if greek else set())


def ref_char_boundary_probs(text, p):
    n = len(text)
    out = np.zeros(n, dtype=float)
    c = 0
    while c < n:
        d = c + 1
        while d < n and text[d].isspace():
            d += 1
        out[c] = float(np.max(p[c:d]))
        c = d if d > c + 1 else c + 1
    return out


def ref_candidates(text, pprime, floor=REF_FLOOR):
    n = len(text)
    last = n - 1
    while last >= 0 and text[last].isspace():
        last -= 1
    pos = []
    for c in range(last):
        ch = text[c]
        if ch.isspace() or ch in REF_COLONS:
            continue
        tok_end = c + 1 < n and text[c + 1].isspace()
        punct = unicodedata.category(ch).startswith("P")
        if tok_end or punct or pprime[c] >= floor:
            pos.append(c)
    return np.array(pos, dtype=int)


def ref_nonspace_prefix(text):
    a = np.zeros(len(text) + 1, dtype=np.int64)
    a[1:] = np.cumsum([0 if ch.isspace() else 1 for ch in text])
    return a


def ref_quote_prefix(text):
    a = np.zeros(len(text) + 1, dtype=np.int64)
    a[1:] = np.cumsum([1 if ch in REF_QANCHOR else 0 for ch in text])
    return a


def ref_quote_counts(text, bounds):
    qp = ref_quote_prefix(text)
    cuts = [-1] + sorted(bounds) + [len(text) - 1]
    return [int(qp[b + 1] - qp[a + 1]) for a, b in zip(cuts[:-1], cuts[1:])]  # noqa: B905


def ref_spans_lens(text, bounds):
    nsp = ref_nonspace_prefix(text)
    cuts = [-1] + sorted(bounds) + [len(text) - 1]
    return [int(nsp[b + 1] - nsp[a + 1]) for a, b in zip(cuts[:-1], cuts[1:])]  # noqa: B905


def ref_project(text, p, eng_lens, s2, floor=REF_FLOOR, eng_quotes=None, w_q=0.0, pprime=None):
    m = len(eng_lens)
    if m <= 1:
        return [], {"K": 0}
    pp = ref_char_boundary_probs(text, p) if pprime is None else pprime
    pos = ref_candidates(text, pp, floor)
    K = len(pos)
    if K < m - 1:  # noqa: SIM300 (verbatim)
        return None, {"K": K, "infeasible": True}
    q = np.clip(pp[pos], REF_EPS, 1 - REF_EPS)
    s = np.log(q) - np.log1p(-q)
    nsp = ref_nonspace_prefix(text)
    tot = float(nsp[-1])
    cum = nsp[pos + 1].astype(float)
    L = np.asarray(eng_lens, dtype=float)
    c = tot / L.sum() if L.sum() > 0 else 1.0
    use_q = eng_quotes is not None and w_q > 0
    if use_q:
        qp = ref_quote_prefix(text)
        qcum = qp[pos + 1].astype(float)
        qtot = float(qp[-1])
        Q = np.asarray(eng_quotes, dtype=float)
        use_q = qtot == Q.sum() and qtot > 0

    def ll(lens, Li):
        mu, var = c * Li, max(s2 * Li, 1.0)
        return -(lens - mu) ** 2 / (2.0 * var)

    def qpen(qs, Qi):
        return -w_q * (qs != Qi) if use_q else 0.0

    NEG = -1e18
    dp = ll(cum, L[0]) + s + (qpen(qcum, Q[0]) if use_q else 0.0)
    tri = np.tril(np.ones((K, K), dtype=bool), k=-1)
    seglen = cum[:, None] - cum[None, :]
    segq = (qcum[:, None] - qcum[None, :]) if use_q else None
    backs = []
    for i in range(1, m - 1):
        M = dp[None, :] + ll(seglen, L[i])
        if use_q:
            M = M + qpen(segq, Q[i])
        M = np.where(tri, M, NEG)
        arg = M.argmax(axis=1)
        dp = M[np.arange(K), arg] + s
        dp[0] = NEG
        backs.append(arg)
    final = dp + ll(tot - cum, L[m - 1]) + (qpen(qtot - qcum, Q[m - 1]) if use_q else 0.0)
    k = int(final.argmax())
    chosen = [k]
    for arg in reversed(backs):
        k = int(arg[k])
        chosen.append(k)
    b = sorted(int(pos[j]) for j in chosen)
    return b, {"K": K, "used_quote_term": bool(use_q)}


def ref_project_pages(text, p, eng_text, eng_bounds, e_page_ends, t_page_ends, s2, floor=REF_FLOOR):
    nsp_e = ref_nonspace_prefix(eng_text)
    pb = set(t_page_ends)
    e_cuts = [-1] + list(e_page_ends) + [len(eng_text) - 1]
    t_cuts = [-1] + list(t_page_ends) + [len(text) - 1]
    infeasible = 0
    for (ea, eb2), (ta, tb) in zip(zip(e_cuts[:-1], e_cuts[1:]), zip(t_cuts[:-1], t_cuts[1:])):  # noqa: B905
        e_in = sorted(b for b in eng_bounds if ea < b < eb2)
        ecc = [ea] + e_in + [eb2]
        lens = [int(nsp_e[y + 1] - nsp_e[x + 1]) for x, y in zip(ecc[:-1], ecc[1:])]  # noqa: B905
        if len(lens) > 1:
            bb, _ = ref_project(text[ta + 1:tb + 1], p[ta + 1:tb + 1], lens, s2, floor)
            if bb is None:
                infeasible += 1
                continue
            pb |= {ta + 1 + x for x in bb}
    if infeasible:
        return None, {"infeasible_pages": infeasible}
    return sorted(pb), {}


def ref_terminal_additions(text, sat_bounds, lang):
    term = ref_terminal_set(lang)
    out = set()
    for b in sat_bounds:
        i = b
        while i > 0 and text[i] in REF_CLOSERS:
            i -= 1
        if text[i] in term:
            out.add(b)
    return out


def ref_union(text, p, eng_lens, s2, sat_bounds, lang, floor=REF_FLOOR, **kw):
    proj, diag_ = ref_project(text, p, eng_lens, s2, floor, **kw)
    if proj is None:
        return None, None, set(), diag_
    adds = ref_terminal_additions(text, sat_bounds, lang) - set(proj)
    return sorted(set(proj) | adds), proj, adds, diag_


def ref_registered_bounds(text, p, threshold=0.25):
    idx = np.where(p > threshold)[0]
    segs, off = [], 0
    for i in idx:
        j = i + 1
        while j < len(text) and text[j].isspace():
            j += 1
        if j > off:
            segs.append(text[off:j])
            off = j
    if off < len(text):
        segs.append(text[off:])
    merged = []
    for sg in segs:
        if merged and merged[-1].rstrip()[-1:] in REF_COLONS:
            merged[-1] += sg
        else:
            merged.append(sg)
    bounds, pos = set(), 0
    for sg in merged[:-1]:
        pos += len(sg)
        k = pos - 1
        while k >= 0 and text[k].isspace():
            k -= 1
        if k >= 0:
            bounds.add(k)
    return bounds, merged


def ref_at_space_or_terminal(text, b, lang=""):
    if b + 1 < len(text) and text[b + 1].isspace():
        return True
    i = b
    while i > 0 and text[i] in REF_CLOSERS:
        i -= 1
    return text[i] in ref_terminal_set(lang)


# ---- tu_common: SEG-3, the frozen gold rule and the scorer
REF_ABBR = ("Mr.", "Mrs.", "Ms.", "Dr.", "St.", "Mt.")
REF_CAND = re.compile(r"[.!?…]+[\"”’']*(?=\s)")
# The words verbatim; only the line breaks inside the string moved, which split() ignores.
REF_TAG_VERBS = set("""said says asked asks cried shouted replied exclaimed whispered yelled answered called screamed
giggled laughed sang added explained begged pleaded sighed squeaked barked roared chirped meowed quacked growled
shrieked gasped suggested warned insisted mumbled muttered sobbed cheered squealed hissed boomed howled wailed
announced declared continued repeated""".split())  # noqa: SIM905


def ref_speech_tag_follows(rest):
    if not rest:
        return False
    if rest[0].islower():
        return True
    m = re.search(r"[.!?…]|[\"“]", rest)
    clause = rest[: m.start()] if m else rest
    if m and m.group(0) in "\"“":
        return False
    words = re.findall(r"[A-Za-z']+", clause)
    if " and " in clause:
        return False
    return 0 < len(words) <= 7 and any(w.lower() in REF_TAG_VERBS for w in words[:4])


def ref_segment(text):
    sents, start = [], 0
    for m in REF_CAND.finditer(text):
        end = m.end()
        tok_start = text.rfind(" ", 0, m.start()) + 1
        if text[tok_start:end] in REF_ABBR:
            continue
        rest = text[end:].lstrip()
        if not rest:
            continue
        closes_quote = m.group(0)[-1] in "\"”’'"
        if closes_quote and ref_speech_tag_follows(rest):
            continue
        if not closes_quote and rest[0].islower():
            continue
        sents.append(text[start:end].strip())
        start = end
    tail = text[start:].strip()
    if tail:
        sents.append(tail)
    return sents


REF_TERMINAL_FROZEN = set(".!?…؟。！？;")
REF_CLOSERS_FROZEN = set("\"'”’»›」』)]）")
REF_OPENERS = set("\"'“‘«‹„「『(")
REF_CJK_TERM = set("。！？")


def ref_internal_orth_ends(text, spans, lang):
    TERMINAL = REF_TERMINAL_FROZEN
    out = set()
    for a, b in spans:
        k = a
        while k < b - 1:
            ch = text[k]
            if ch in TERMINAL or ch in REF_CJK_TERM:
                j = k + 1
                while j < b and text[j] in REF_CLOSERS_FROZEN:
                    j += 1
                end = j - 1
                if lang.startswith("zho"):
                    if ch in REF_CJK_TERM and j < b and not text[j].isspace():  # noqa: SIM114 (verbatim)
                        out.add(end)
                    elif ch in REF_CJK_TERM and j < b:
                        out.add(end)
                    k = j
                    continue
                if j < b and text[j].isspace():
                    jj = j
                    while jj < b and text[jj].isspace():
                        jj += 1
                    if jj < b:
                        c2 = text[jj]
                        ok = c2.isdigit() or c2 in REF_OPENERS or (
                            c2.isalpha() and (c2.isupper() or c2.upper() == c2.lower()))
                        if ok and ch == ".":
                            before = text[a:k].split()
                            w = before[-1] if before else ""
                            letters = sum(c.isalpha() for c in w)
                            if any(c.isdigit() for c in w) or "." in w or "/" in w or letters <= 2:
                                ok = False
                        if ok:
                            out.add(end)
                k = j
                continue
            k += 1
    return out


REF_QUOTES = set("\"'“”„‟«»‹›「」『』‘’‚")


def ref_canon(text, i):
    while i > 0 and (text[i] in REF_QUOTES or text[i].isspace()):
        i -= 1
    return i


def ref_prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def ref_boot_prf(rows, rng, n_boot=2000):
    a = np.asarray(rows, dtype=float).reshape(-1, 3)
    if len(a) == 0:
        return {"n_texts": 0}
    p, r, f = ref_prf(*a.sum(0))
    idx = rng.integers(0, len(a), (n_boot, len(a)))
    s = a[idx].sum(1)
    tp, fp, fn = s[:, 0], s[:, 1], s[:, 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        P = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
        R = np.where(tp + fn > 0, tp / (tp + fn), 0.0)
        F = np.where(P + R > 0, 2 * P * R / (P + R), 0.0)
    q = lambda v: [round(100 * float(np.percentile(v, 2.5)), 1), round(100 * float(np.percentile(v, 97.5)), 1)]  # noqa: E731
    return {"P": round(100 * p, 1), "R": round(100 * r, 1), "F1": round(100 * f, 1), "P_ci": q(P), "R_ci": q(R),
            "F1_ci": q(F), "n_texts": len(a), "tp": int(a[:, 0].sum()), "fp": int(a[:, 1].sum()),
            "fn": int(a[:, 2].sum()), "n_boot": n_boot}


# ---- tu3_union.summ
def ref_summ(v):
    v = np.asarray([x for x in v if x is not None and np.isfinite(x)], float)
    if not len(v):
        return None
    return {"median": round(float(np.median(v)), 3), "iqr": [round(float(np.percentile(v, 25)), 3),
                                                            round(float(np.percentile(v, 75)), 3)],
            "share_within_10pct": round(float(np.mean(np.abs(v - 1) <= 0.10)), 3), "n": int(len(v))}


# ============================================================ random inputs

ALPHABET = (list("abcdefghij") * 6 + list("ABCDE") * 2 + [" "] * 18 + ["\n"] * 3 + list(".!?") * 3
            + [":", "：", ";", ",", "\"", "“", "”", "’", "'", "…", "»", "«", "。", "）", "1", "\t", " "])


def rand_text(rng, n):
    return "".join(rng.choice(ALPHABET) for _ in range(n))


def rand_probs(rng, text):
    out = []
    for _ in text:
        u = rng.random()
        if u < 0.55:
            v = 0.0
        elif u < 0.70:
            v = 10 ** rng.uniform(-8, -3)
        elif u < 0.85:
            v = rng.uniform(0.05, 0.6)
        elif u < 0.92:
            v = rng.choice([0.25, 0.25 + 2 ** -25, 0.2499999, 1e-5, 0.9999])
        else:
            v = rng.uniform(0.6, 1.0)
        out.append(f32(v))
    return out


def ref_nonblank(text, segs):
    return [s.strip() for s in segs if s.strip()]


def my_contents(text, spans):
    # wtpsplit drops the newline characters it cuts at; a merged span still covers them
    return [text[a:b].replace("\n", "") for a, b in spans]


# ============================================================ configuration


def test_registered_constants_are_in_config():
    call = SAT_CFG["call"]
    assert call["threshold"] == 0.25
    assert (call["stride"], call["block_size"], call["batch_size"]) == (64, 512, 32)
    assert call["pad_last_batch"] is True and call["strip_whitespace"] is False
    assert call["split_on_input_newlines"] is True
    assert set(SAT_CFG["colon_rule"]["colons"]) == {":", "："}
    assert SAT_CFG["candidates"]["floor"] == 1e-5
    assert SAT_CFG["model"] == {"sat": "segment-any-text/sat-12l-sm", "tokenizer": "FacebookAI/xlm-roberta-base",
                                "wtpsplit_version": "2.2.2"}
    assert CFG["floor"]["min_english_sentences"] == 5
    assert SAT_CFG["floor"]["source_lang"] == "en-us"
    assert CHECK_CFG["criterion"]["min_f1"] == 0.95
    assert CHECK_CFG["bootstrap"]["replicates"] == 2000


def test_union_constants_equal_the_benchmark():
    assert USET.terminal_marks == REF_TERMINAL_BASE
    assert USET.closing_marks == REF_CLOSERS
    assert USET.quote_anchors == REF_QANCHOR
    assert USET.colons == set(REF_COLONS)
    assert USET.eps == REF_EPS and USET.floor == REF_FLOOR
    assert USET.terminal_set("el-gr") == ref_terminal_set("el") and USET.terminal_set("en-us") == ref_terminal_set("en")
    assert USET.quote_term is False
    assert math.isclose(USET.quote_term_weight, math.log(0.95 / 0.05), rel_tol=0, abs_tol=1e-15)


def test_rule_constants_equal_the_frozen_rule():
    assert RULE.abbreviations == set(REF_ABBR)
    assert RULE.tag_verbs == REF_TAG_VERBS
    assert QUOTES == REF_QUOTES
    assert ORTH.terminal == REF_TERMINAL_FROZEN and ORTH.closers == REF_CLOSERS_FROZEN
    assert ORTH.openers == REF_OPENERS and ORTH.cjk_terminal == REF_CJK_TERM
    assert ORTH.max_abbreviation_letters == 2
    probe = "".join(chr(c) for c in range(32, 0x3010)) + " x"
    assert [m.span() for m in RULE.cand.finditer(probe)] == [m.span() for m in REF_CAND.finditer(probe)]


def test_settings_refuse_strip_whitespace():
    bad = copy.deepcopy(SAT_CFG)
    bad["call"]["strip_whitespace"] = True
    with pytest.raises(ValueError):
        sat_mod.SatSettings.from_config(bad)


def test_sentinel_is_long_enough_in_words():
    assert len(RUNTIME.sentinel.split()) >= 510 and RUNTIME.fixed_block_width


# ============================================================ the registered call, from probabilities


def probs_at(text, marks):
    """Probability 0.9 at the given offsets, 0 elsewhere."""
    return [0.9 if i in marks else 0.0 for i in range(len(text))]


def test_threshold_boundaries_and_spans():
    text = "The cat sat. The dog ran! Then it slept."
    p = probs_at(text, {11, 24, 39})
    seg = sat_mod.segment_text(text, p, SETTINGS)
    assert seg.spans == [(0, 12), (13, 25), (26, 40)]
    assert seg.boundaries == [11, 24]
    assert seg.newline_forced == []


def test_threshold_is_strict_and_compared_in_float32():
    text = "Ab cd. Ef gh."
    at = [0.0] * len(text)
    at[5] = 0.25
    assert sat_mod.segment_text(text, at, SETTINGS).boundaries == []
    at[5] = 0.25 + 2 ** -25  # the next float32 above .25
    assert sat_mod.segment_text(text, at, SETTINGS).boundaries == [5]


def test_colon_rule_merges_across_the_colon():
    text = 'She said: "Run!" They ran.'
    p = probs_at(text, {8, 15, 25})  # the colon, the closing quote, the final stop
    seg = sat_mod.segment_text(text, p, SETTINGS)
    assert seg.boundaries == [15]
    assert [text[a:b] for a, b in seg.spans] == ['She said: "Run!"', "They ran."]
    full = "Note： see this. Next."
    seg = sat_mod.segment_text(full, probs_at(full, {4, 14}), SETTINGS)
    assert seg.boundaries == [14]


def test_newline_forces_a_boundary_and_is_counted():
    text = "A title line\nOnce there was a fox. It ran."
    p = probs_at(text, {33})
    seg = sat_mod.segment_text(text, p, SETTINGS)
    assert [text[a:b] for a, b in seg.spans] == ["A title line", "Once there was a fox.", "It ran."]
    assert seg.newline_forced == [11]
    off = sat_mod.segment_text(text, p, sat_mod.SatSettings(**{**SETTINGS.__dict__, "split_on_input_newlines": False}))
    assert off.boundaries == [33] and off.newline_forced == []


def test_colon_rule_applies_across_a_line_break():
    text = "He shouted:\nRun now. Go."
    seg = sat_mod.segment_text(text, probs_at(text, {19}), SETTINGS)
    assert seg.boundaries == [19]
    assert seg.newline_forced == []


def test_text_ending_in_a_line_break_keeps_its_last_sentence_last():
    text = "One. Two.\n"
    seg = sat_mod.segment_text(text, probs_at(text, {3, 8}), SETTINGS)
    assert seg.boundaries == [3]
    assert [text[a:b] for a, b in seg.spans] == ["One.", "Two."]


def test_blank_and_empty_texts():
    for text in ("", "   ", "\n\n"):
        seg = sat_mod.segment_text(text, [0.9] * len(text), SETTINGS)
        assert seg.spans == [] and seg.boundaries == []


def test_probability_count_must_match_the_text():
    with pytest.raises(ValueError):
        sat_mod.segment_text("abc", [0.0, 0.0], SETTINGS)


def test_offsets_match_wtpsplit_split_with_the_colon_rule():
    rng = random.Random(20261103)
    for _ in range(3000):
        text = rand_text(rng, rng.randint(0, 70))
        p = rand_probs(rng, text)
        ref = ref_nonblank(text, ref_colon_rule(ref_wtpsplit_split(text, p, 0.25)))
        seg = sat_mod.segment_text(text, p, SETTINGS)
        assert my_contents(text, seg.spans) == ref, (text, p)
        assert seg.boundaries == boundaries_of(seg.spans)
        for a, b in seg.spans:  # trimmed, ordered and disjoint
            assert not text[a].isspace() and not text[b - 1].isspace()
        assert all(seg.spans[i][1] <= seg.spans[i + 1][0] for i in range(len(seg.spans) - 1))
        nonspace = "".join(ch for ch in text if not ch.isspace())
        assert "".join(ch for a, b in seg.spans for ch in text[a:b] if not ch.isspace()) == nonspace


@needs_numpy
def test_boundaries_match_union_lib_registered_bounds_without_newlines():
    rng = random.Random(7)
    for _ in range(3000):
        text = rand_text(rng, rng.randint(0, 80)).replace("\n", " ")
        p = rand_probs(rng, text)
        ref, _ = ref_registered_bounds(text, np.asarray(p, dtype=np.float32))
        assert sat_mod.segment_text(text, p, SETTINGS).boundaries == sorted(ref), text


def test_boundaries_rebuild_from_stored_candidates():
    rng = random.Random(11)
    for _ in range(3000):
        text = rand_text(rng, rng.randint(0, 80))
        p = rand_probs(rng, text)
        seg = sat_mod.segment_text(text, p, SETTINGS)
        stored = json.loads(json.dumps({"pos": seg.candidate_pos, "p": seg.candidate_p}))
        assert sat_mod.boundaries_from_candidates(text, stored["pos"], stored["p"], SETTINGS) == seg.boundaries
        pp = union_mod.char_boundary_probs(text, p)
        assert [f32(v) for v in stored["p"]] == [pp[c] for c in stored["pos"]]


def test_f32_json_round_trips_exactly():
    rng = random.Random(3)
    for _ in range(20000):
        x = f32(10 ** rng.uniform(-12, 0))
        y = sat_mod.f32_json(x)
        assert f32(json.loads(json.dumps(y))) == x


def test_regex_whitespace_is_str_isspace():
    # union.py scans with \s where the benchmark's loops called str.isspace(); they must agree everywhere
    ws = re.compile(r"\s")
    assert all(bool(ws.match(chr(c))) == chr(c).isspace() for c in range(sys.maxunicode + 1))


def loop_char_boundary_probs(text, p):
    """The benchmark's loop, on lists (union_lib.char_boundary_probs without NumPy)."""
    n = len(text)
    out = [0.0] * n
    c = 0
    while c < n:
        d = c + 1
        while d < n and text[d].isspace():
            d += 1
        out[c] = max(p[c:d])
        c = d if d > c + 1 else c + 1
    return out


def loop_candidates(text, pprime, floor=REF_FLOOR):
    """The benchmark's loop, on lists (union_lib.candidates without NumPy)."""
    n = len(text)
    last = n - 1
    while last >= 0 and text[last].isspace():
        last -= 1
    pos = []
    for c in range(last):
        ch = text[c]
        if ch.isspace() or ch in REF_COLONS:
            continue
        tok_end = c + 1 < n and text[c + 1].isspace()
        punct = unicodedata.category(ch).startswith("P")
        if tok_end or punct or pprime[c] >= floor:
            pos.append(c)
    return pos


def test_char_helpers_match_the_benchmark_loops():
    rng = random.Random(23)
    for _ in range(4000):
        text = rand_text(rng, rng.randint(0, 90))
        if rng.random() < 0.2:
            text = rng.choice(["  ", "\n", " 　"]) + text  # a leading run keeps its maximum on position 0
        p = rand_probs(rng, text)
        mine = union_mod.char_boundary_probs(text, p)
        assert mine == loop_char_boundary_probs(text, p), text
        assert union_mod.candidates(text, mine, USET.floor, USET.colons) == loop_candidates(text, mine), text


@needs_numpy
def test_char_helpers_match_union_lib():
    rng = random.Random(5)
    for _ in range(2000):
        text = rand_text(rng, rng.randint(1, 80))
        p = np.asarray(rand_probs(rng, text), dtype=np.float32)
        mine = union_mod.char_boundary_probs(text, p)
        ref = ref_char_boundary_probs(text, p)
        assert mine == ref.tolist()
        assert union_mod.candidates(text, mine, USET.floor, USET.colons) == ref_candidates(text, ref).tolist()
        assert union_mod.nonspace_prefix(text) == ref_nonspace_prefix(text).tolist()
        bounds = sorted(rng.sample(range(len(text)), k=min(3, len(text) - 1))) if len(text) > 1 else []
        assert union_mod.spans_lens(text, bounds) == ref_spans_lens(text, bounds)
        assert union_mod.quote_counts(text, bounds, USET.quote_anchors) == ref_quote_counts(text, bounds)


# ============================================================ page anchors


def test_page_anchors_agree_with_document_page_of():
    doc = records.Document(story_id="S", lang="en-us", level="young", kind="generated", title="T",
                           pages=("One two.", "Three\nfour five.", "", "Six."))
    text = doc.text
    starts = [a for a, _ in doc.page_spans()]
    for off in range(len(text)):
        if not text[off].isspace():
            assert page_index(starts, off) == doc.page_of(off)
    spans = [(0, 8), (9, 25), (27, 31)]
    assert page_anchors(doc.page_spans(), spans) == [(0, 0), (1, 1), (3, 3)]
    assert page_anchors(doc.page_spans(), [(4, 14)]) == [(0, 1)]
    with pytest.raises(ValueError):
        page_anchors(doc.page_spans(), [(30, 99)])
    # a title-only row has no page and no sentence; it must not stop the shard
    assert page_anchors([], []) == []
    with pytest.raises(ValueError):
        page_anchors([], [(0, 1)])


def test_sentences_from_record_checks_its_fields():
    rec = {"sentence_fields": list(SENTENCE_FIELDS), "sentences": [[0, 4, 0, 0], [5, 9, 0, 1]]}
    assert [tuple(s) for s in sentences_from_record(rec)] == [(0, 4, 0, 0), (5, 9, 0, 1)]
    with pytest.raises(ValueError):
        sentences_from_record({"sentence_fields": ["end", "start"], "sentences": []})


# ============================================================ the model wrapper, with a fake


class FakeTokenizer:
    def __call__(self, texts, add_special_tokens=False, verbose=False):
        assert add_special_tokens is False
        return {"input_ids": [[0] * len(t.split()) for t in texts]}


class FakeSat:
    """Stands in for wtpsplit.SaT: a high probability at a sentence-final mark or closing quote before
    whitespace, 0.6 at a colon there, a tiny value at other token ends and 0 elsewhere."""

    def __init__(self):
        self.calls = []
        self.tokenizer = FakeTokenizer()

    @staticmethod
    def probs(t):
        out = []
        n = len(t)
        for i, ch in enumerate(t):
            before_space = i + 1 == n or t[i + 1].isspace()
            if before_space and (ch in ".!?" or (ch in "\"”" and i > 0 and t[i - 1] in ".!?")):
                out.append(0.9)
            elif before_space and ch == ":":
                out.append(0.6)
            elif before_space and not ch.isspace():
                out.append(1e-6)
            else:
                out.append(0.0)
        return out

    def predict_proba(self, texts, **kwargs):
        self.calls.append((list(texts), dict(kwargs)))
        for t in texts:  # a generator of arrays, as wtpsplit returns
            yield self.probs(t)


def test_predict_sends_the_registered_arguments_and_drops_the_sentinel():
    fake = FakeSat()
    texts = ["One. Two.", "", "Three!"]
    out = sat_mod.predict(fake, texts, SETTINGS, RUNTIME)
    assert out[1] == [] and out[0] == FakeSat.probs(texts[0]) and out[2] == FakeSat.probs(texts[2])
    (sent, kwargs), = fake.calls
    assert sent[0] == RUNTIME.sentinel and sent[1:] == ["One. Two.", "Three!"]
    assert kwargs == {"stride": 64, "block_size": 512, "batch_size": 32, "pad_last_batch": True,
                      "outer_batch_size": 3}
    plain = sat_mod.RuntimeSettings(**{**RUNTIME.__dict__, "fixed_block_width": False})
    fake2 = FakeSat()
    assert sat_mod.predict(fake2, texts, SETTINGS, plain) == out
    assert fake2.calls[0][0] == ["One. Two.", "Three!"]


def test_predict_refuses_a_length_mismatch():
    class Short(FakeSat):
        def predict_proba(self, texts, **kwargs):
            for t in texts:
                yield [0.0] * (len(t) - 1)

    with pytest.raises(RuntimeError):
        sat_mod.predict(Short(), ["One. Two."], SETTINGS, RUNTIME)


def test_chunks_follow_wtpsplit_extract():
    # extract(): ceil(max(L - block, 0) / stride) + 1 chunks, block 510 once CLS and SEP are counted
    assert [sat_mod.chunks_for(n, SETTINGS) for n in (1, 510, 511, 574, 575, 2000)] == [1, 1, 2, 2, 3, 25]


# ============================================================ pin verification


def test_resolve_pinned_snapshot_verifies_hashes(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    sha = hashlib.sha256(b"{}").hexdigest()
    lock = {"m": {"repo": "org/m", "revision": "abc", "path": str(tmp_path), "files": {"config.json": sha}}}
    assert sat_mod.resolve_pinned_snapshot(lock, "m") == tmp_path
    lock["m"]["files"] = [{"path": "config.json", "sha256": sha}]
    assert sat_mod.resolve_pinned_snapshot(lock, "m") == tmp_path
    assert sat_mod.resolve_pinned_snapshot({"models": lock}, "m") == tmp_path  # parse.model_pin's layout
    lock["m"]["files"] = {"config.json": "0" * 64}
    with pytest.raises(ValueError):
        sat_mod.resolve_pinned_snapshot(lock, "m")
    with pytest.raises(KeyError):
        sat_mod.resolve_pinned_snapshot({}, "m")
    with pytest.raises(ValueError):
        sat_mod.resolve_pinned_snapshot({"m": {"revision": "abc", "path": str(tmp_path)}}, "m")


def test_hf_snapshot_dir_follows_the_cache_layout(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    got = sat_mod.hf_snapshot_dir("segment-any-text/sat-12l-sm", "d70c72a9")
    assert got == tmp_path / "hub" / "models--segment-any-text--sat-12l-sm" / "snapshots" / "d70c72a9"


# ============================================================ the sat stage


KEYED_PURPOSE = CFG["stages"]["documents"]["keyed_sample"]["purpose"]


def keyed_hash_of(sid):
    """The keyed hash the documents stage stores in meta.keyed_hash (documents.toml [keyed_sample])."""
    from intract_features.text.keyed import key_settings

    return records.keyed_hash(KEYED_PURPOSE, sid, **key_settings(CFG))


def make_doc(sid, pages, lang="en-us"):
    return records.Document(story_id=sid, lang=lang, level="young", kind="generated", title="T", pages=tuple(pages),
                            meta={"keyed_hash": keyed_hash_of(sid)})


DOCS = [
    make_doc("A", ["The cat sat on the mat. It was warm.", "Then the dog came: it barked! Everyone ran away."]),
    make_doc("B", ["A title line\nOnce upon a time there was a fox. The fox was red.",
                   "It ran. It hid. It slept. The end."]),
    make_doc("C", ["She walked to the", "park. Birds sang. Dr. Smith waved. \"Hello!\" she said. They left."]),
    make_doc("D", ['"Run!" Tom shouted. They ran fast. Then they stopped. Then they rested. Then home.']),
]
KEYED_ORDER = sorted((d.story_id for d in DOCS), key=lambda s: (keyed_hash_of(s), s))


def write_documents(work, docs, lang="en-us", nshards=1):
    by_shard = {}
    for d in docs:
        by_shard.setdefault(records.shard_of(d.story_id, nshards), []).append(d)
    for shard in range(nshards):
        path = records.artefact_path(work, lang, "documents", shard, nshards)
        records.write_jsonl(path, [d.to_json() for d in by_shard.get(shard, [])])


def stage_ctx(stage, work, lang="en-us", shard=0, nshards=1, cfg=CFG, backend=None, limit=None):
    extra = {"sat_backend": backend or FakeSat()}
    return cli.StageContext(stage=stage.STAGE, config=cfg, lang=lang, work=work, shard=shard, nshards=nshards,
                            limit=limit, extra=extra)


def run_sat(work, docs, lang="en-us", nshards=1, cfg=CFG, limit=None):
    write_documents(work, docs, lang, nshards)
    counts = []
    for shard in range(nshards):
        counts.append(sat_stage.run(stage_ctx(sat_stage, work, lang, shard, nshards, cfg, limit=limit)))
    return counts


def read_segments(work, lang="en-us", nshards=1):
    out = {}
    for shard in range(nshards):
        for rec in records.read_jsonl(records.artefact_path(work, lang, "segments", shard, nshards)):
            out[rec["story_id"]] = rec
    return out


def test_sat_stage_writes_sentences_pages_candidates_and_the_floor(tmp_path):
    (counts,) = run_sat(tmp_path, DOCS)
    segs = read_segments(tmp_path)
    a = segs["A"]
    text = DOCS[0].text
    assert a["segmenter"] == "sat" and a["is_source"] is True and a["lang"] == "en-us"
    assert a["text_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert [text[s:e] for s, e, _, _ in a["sentences"]] == [
        "The cat sat on the mat.", "It was warm.", "Then the dog came: it barked!", "Everyone ran away."]
    assert [(ps, pe) for _, _, ps, pe in a["sentences"]] == [(0, 0), (0, 0), (1, 1), (1, 1)]
    assert a["n_sentences"] == 4 and a["floor"] == {"min_english_sentences": 5, "excluded": True}
    assert a["sentence_fields"] == list(SENTENCE_FIELDS)
    b = segs["B"]
    assert b["newline_forced"] == [DOCS[1].text.index("line") + 3]
    assert b["floor"]["excluded"] is False
    c = segs["C"]
    ctext = DOCS[2].text
    first = c["sentences"][0]
    assert ctext[first[0]:first[1]] == "She walked to the park." and (first[2], first[3]) == (0, 1)
    pos, pv = a["candidates"]["pos"], a["candidates"]["p"]
    assert len(pos) == len(pv) and pos == sorted(pos)
    assert sat_mod.boundaries_from_candidates(text, pos, pv, SETTINGS) == boundaries_of(a["sentences"])
    assert counts["documents"] == 4 and counts["characters"] == sum(len(d.text) for d in DOCS)
    assert counts["sentences"] == sum(r["n_sentences"] for r in segs.values())
    assert counts["words"] == sum(len(d.text.split()) for d in DOCS)
    assert counts["below_floor"] == 1 and counts["newline_forced"] == 1 and counts["cross_page_sentences"] == 1
    assert counts["tokens"] == counts["whitespace_tokens"] and counts["chunks"] == 4
    json.dumps(counts, allow_nan=False)


def test_sat_stage_is_byte_identical_on_rerun_and_honours_limit(tmp_path):
    run_sat(tmp_path, DOCS)
    path = records.artefact_path(tmp_path, "en-us", "segments", 0, 1)
    first = path.read_bytes()
    run_sat(tmp_path, DOCS)
    assert path.read_bytes() == first
    run_sat(tmp_path / "lim", DOCS, limit=2)
    assert list(read_segments(tmp_path / "lim")) == ["A", "B"]


def test_sat_stage_leaves_the_floor_to_the_english_source(tmp_path):
    fr = [make_doc("A", ["Le chat dort. Il fait chaud."], lang="fr-fr")]
    (counts,) = run_sat(tmp_path, fr, lang="fr-fr")
    rec = read_segments(tmp_path, "fr-fr")["A"]
    assert rec["is_source"] is False and "floor" not in rec and "below_floor" not in counts


def test_sat_stage_can_omit_candidates(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["stages"]["sat"]["candidates"]["store"] = False
    run_sat(tmp_path, DOCS[:1], cfg=cfg)
    assert "candidates" not in read_segments(tmp_path)["A"]


def test_sat_stage_timing_record_is_strict_json(tmp_path):
    write_documents(tmp_path, DOCS)
    rec = cli.run_stage(sat_stage, stage_ctx(sat_stage, tmp_path))
    assert rec["counts"]["documents"] == 4
    out = tmp_path / "en-us" / "_timing" / "sat-shard-0-of-1.json"
    assert json.loads(out.read_text(encoding="utf-8"))["stage"] == "sat"


def test_stage_modules_declare_their_contract():
    assert sat_stage.STAGE.name == "sat" and sat_stage.STAGE.device == "gpu" and sat_stage.STAGE.env == "core"
    assert sat_stage.STAGE.inputs == ("documents",) and sat_stage.STAGE.outputs == ("segments",)
    assert seg_check_stage.STAGE.name == "seg_check" and seg_check_stage.STAGE.device == "cpu"
    assert {"sat", "seg_check"} <= set(cli.discover())


# ============================================================ the frozen rules


STORY_BITS = ["The cat sat.", "Dr. Smith came home.", "Mrs. Lee waved!", "\"Run!\" she said.", "\"Stop,\" Tom cried.",
              "\"Hello!\" The dog barked.", "It was late... then it rained.", "He asked, \"Why?\" and left.",
              "\"Wait!\" Mom and Dad shouted.", "They ran to St. Paul's.", "Why? Nobody knew.", "she laughed.",
              "\"Yes.\" \"No.\"", "Mt. Fuji is tall.", "1. The first.", "It cost 3.50 dollars.", "Wow!\" said Ann.",
              "\"Look,\" whispered Sam, \"a fox.\"", "The end.", "Ms. Brown asked, \"Ready?\" Everyone nodded."]


def test_rule_spans_reproduce_seg3():
    rng = random.Random(42)
    texts = [" ".join(rng.choice(STORY_BITS) for _ in range(rng.randint(1, 12))) for _ in range(3000)]
    texts += [rand_text(rng, rng.randint(0, 60)) for _ in range(2000)]
    texts += ["", "   ", "Hi.", "Hi. ", " Hi.  Yo.", "A.\nB. c. D!\" e"]
    for text in texts:
        spans = rules.rule_spans(text, RULE)
        assert rules.rule_sentences(text, RULE) == ref_segment(text), text
        assert all(b > a and not text[a].isspace() and not text[b - 1].isspace() for a, b in spans)


def test_rule_keeps_a_quotation_with_its_speech_verb():
    text = '"Run!" she said. Then they ran. Dr. Smith smiled.'
    assert rules.rule_sentences(text, RULE) == ['"Run!" she said.', "Then they ran.", "Dr. Smith smiled."]


def test_internal_orth_ends_reproduces_the_frozen_rule():
    rng = random.Random(9)
    langs = ["eng_Latn", "zho_Hans", "zho_Hant", "ell_Grek"]
    for _ in range(4000):
        units = [rand_text(rng, rng.randint(1, 40)) for _ in range(rng.randint(1, 4))]
        text, spans = "", []
        for i, u in enumerate(units):
            if i:
                text += rng.choice(["", " "])
            spans.append((len(text), len(text) + len(u)))
            text += u
        for lang in langs:
            got = rules.internal_orth_ends(text, spans, ORTH, cjk=lang.startswith("zho"))
            assert got == ref_internal_orth_ends(text, spans, lang), (text, lang)


# ============================================================ the scorer and the summaries


def test_canon_counts_and_prf():
    text = 'He said "Go." Then'
    assert diag.canon(text, 12, QUOTES) == 11 == ref_canon(text, 12)
    assert diag.counts({1, 2, 3}, {2, 3, 4}) == (2, 1, 1)
    assert diag.prf(0, 0, 0) == (0.0, 0.0, 0.0) == ref_prf(0, 0, 0)
    assert diag.prf(3, 1, 2) == ref_prf(3, 1, 2)
    tol, exact = diag.score_text(text, [12], [11], QUOTES)
    assert tol == (1, 0, 0) and exact == (0, 1, 1)


@needs_numpy
def test_boot_prf_reproduces_the_benchmark():
    rng = random.Random(1)
    rows = [(rng.randint(0, 40), rng.randint(0, 3), rng.randint(0, 3)) for _ in range(150)]
    mine = diag.boot_prf(rows, diag.bootstrap_rng(20261026, 18), 2000)
    ref = ref_boot_prf(rows, np.random.default_rng(np.random.SeedSequence(20261026, spawn_key=(18,))), 2000)
    assert {k: v for k, v in mine.items() if not k.endswith("unrounded")} == ref
    assert round(100 * mine["F1_unrounded"], 1) == ref["F1"]
    assert diag.boot_prf([], diag.bootstrap_rng(1, 0), 10) == {"n_texts": 0}


@needs_numpy
def test_percentile_and_ratio_summary_match_numpy():
    rng = random.Random(2)
    for _ in range(500):
        v = [rng.uniform(0.5, 1.5) for _ in range(rng.randint(1, 60))]
        for q in (0, 1, 2.5, 25, 50, 75, 97.5, 99, 100):
            assert diag.percentile(v, q) == float(np.percentile(v, q))
        assert diag.ratio_summary(v + [None, float("nan")]) == ref_summ(v)
    assert diag.ratio_summary([None]) is None


def test_mean_sd_terminal_and_floor_helpers():
    assert diag.mean_sd([]) == (None, None) and diag.mean_sd([2.0]) == (2.0, None)
    m, s = diag.mean_sd([1, 2, 3, 4])
    assert m == 2.5 and math.isclose(s, math.sqrt(5 / 3))
    text = 'He ran." Then "Stop'
    assert diag.ends_with_terminal(text, 8, USET.terminal_marks, USET.closing_marks)
    assert not diag.ends_with_terminal(text, len(text), USET.terminal_marks, USET.closing_marks)
    assert diag.terminal_marks("A. B! C? D…", USET.terminal_marks) == 4
    assert diag.floor_excluded(4, 5) and not diag.floor_excluded(5, 5)
    assert diag.words_per_span([0, 3, 7, 12], [(0, 5), (6, 13)]) == [2, 2]
    assert diag.nonspace_length("a b  c", 0, 6) == 3


# ============================================================ the seg_check stage


def run_check(work, cfg=CFG, nshards=1, lang="en-us", limit=None):
    seg_check_stage.run(stage_ctx(seg_check_stage, work, lang, 0, nshards, cfg, limit=limit))
    return json.loads(seg_check_stage.report_path(work, lang).read_text(encoding="utf-8"))


def expected_rows(docs):
    rows = {}
    for d in docs:
        text = d.text
        seg = sat_mod.segment_text(text, FakeSat.probs(text), SETTINGS)
        rule_b = boundaries_of(rules.rule_spans(text, RULE))
        rows[d.story_id] = diag.score_text(text, seg.boundaries, rule_b, QUOTES)
    return rows


@needs_numpy
@pytest.mark.parametrize("nshards", [1, 3])
def test_seg_check_scores_the_keyed_sample_and_summarises_the_floor(tmp_path, nshards):
    run_sat(tmp_path, DOCS, nshards=nshards)
    rep = run_check(tmp_path, nshards=nshards)
    exp = expected_rows(DOCS)
    check = rep["check"]
    assert [r["story_id"] for r in check["per_text"]] == KEYED_ORDER
    assert {r["story_id"]: (tuple(r["tolerant"]), tuple(r["exact"])) for r in check["per_text"]} == exp
    tp, fp, fn = (sum(exp[s][0][i] for s in exp) for i in range(3))
    f1 = diag.prf(tp, fp, fn)[2]
    assert check["value"] == f1 and check["passed"] is (f1 >= 0.95)
    assert (check["tolerant"]["tp"], check["tolerant"]["fp"], check["tolerant"]["fn"]) == (tp, fp, fn)
    assert check["sample"]["rank_source"] == "documents" and check["sample"]["n_texts"] == 4
    assert fp > 0  # Dr. and a quotation before its speech tag: the fake SaT splits there, the rule does not
    floor = rep["floor"]
    assert floor["n_texts"] == 4 and floor["n_excluded"] == 1 and floor["min_english_sentences"] == 5
    assert floor["words_per_text"]["p0"] == min(len(d.text.split()) for d in DOCS)
    assert rep["diagnostics"]["newline_forced_boundaries"] == 1
    assert rep["diagnostics"]["sentences_across_a_page_break"] == 1


@needs_numpy
def test_seg_check_report_does_not_depend_on_sharding(tmp_path):
    run_sat(tmp_path / "one", DOCS, nshards=1)
    run_sat(tmp_path / "three", DOCS, nshards=3)
    one, three = run_check(tmp_path / "one"), run_check(tmp_path / "three", nshards=3)
    for rep in (one, three):
        rep.pop("nshards")
    assert one == three


@needs_numpy
def test_seg_check_sample_size_and_recomputed_ranks(tmp_path):
    from intract_features.text.keyed import key_settings, keyed_sample

    cfg = copy.deepcopy(CFG)
    cfg["stages"]["documents"]["keyed_sample"]["size"] = 2
    purpose = cfg["stages"]["documents"]["keyed_sample"]["purpose"]
    want = keyed_sample([d.story_id for d in DOCS], 2, purpose, **key_settings(cfg))
    run_sat(tmp_path, DOCS)
    rep = run_check(tmp_path, cfg=cfg)
    assert [r["story_id"] for r in rep["check"]["per_text"]] == want == KEYED_ORDER[:2]
    assert rep["check"]["sample"]["rank_source"] == "documents"
    unranked = [records.Document(**{**d.__dict__, "meta": {}}) for d in DOCS]
    run_sat(tmp_path / "u", unranked)
    rep = run_check(tmp_path / "u", cfg=cfg)
    assert rep["check"]["sample"]["rank_source"] == "recomputed"
    assert [r["story_id"] for r in rep["check"]["per_text"]] == want


def test_seg_check_refuses_a_keyed_hash_of_another_key(tmp_path):
    # A documents artefact written under another [keyed_sample] purpose or [keys] would sample other stories.
    stale = [records.Document(**{**d.__dict__, "meta": {"keyed_hash": "0" * 64}}) for d in DOCS[:1]]
    run_sat(tmp_path, stale)
    with pytest.raises(ValueError, match="keyed_hash"):
        seg_check_stage.run(stage_ctx(seg_check_stage, tmp_path))


def test_seg_check_writes_its_report_from_shard_0_only(tmp_path):
    run_sat(tmp_path, DOCS, nshards=2)
    counts = seg_check_stage.run(stage_ctx(seg_check_stage, tmp_path, shard=1, nshards=2))
    assert counts == dict.fromkeys(seg_check_stage.COUNT_KEYS, 0)
    assert not seg_check_stage.report_path(tmp_path, "en-us").exists()


@needs_numpy
def test_seg_check_criterion_switches(tmp_path):
    run_sat(tmp_path, DOCS)
    cfg = copy.deepcopy(CFG)
    cfg["stages"]["seg_check"]["criterion"]["min_f1"] = 0.0
    assert run_check(tmp_path, cfg=cfg)["check"]["passed"] is True
    cfg["stages"]["seg_check"]["criterion"]["statistic"] = "lower_95"
    rep = run_check(tmp_path, cfg=cfg)
    assert rep["check"]["value"] == rep["check"]["tolerant"]["F1_ci_unrounded"][0]
    cfg["stages"]["seg_check"]["criterion"]["min_f1"] = 1.01
    assert run_check(tmp_path, cfg=cfg)["check"]["passed"] is False
    cfg["stages"]["seg_check"]["criterion"]["statistic"] = "median"
    with pytest.raises(ValueError):
        run_check(tmp_path, cfg=cfg)


def test_seg_check_refuses_translations_and_stale_segments(tmp_path):
    with pytest.raises(ValueError, match="translation"):
        seg_check_stage.run(stage_ctx(seg_check_stage, tmp_path, lang="fr-fr"))
    run_sat(tmp_path, DOCS[:1])
    path = records.artefact_path(tmp_path, "en-us", "segments", 0, 1)
    rec = next(records.read_jsonl(path))
    rec["text_sha256"] = "0" * 64
    records.write_jsonl(path, [rec])
    with pytest.raises(ValueError, match="stale"):
        seg_check_stage.run(stage_ctx(seg_check_stage, tmp_path))


def test_segments_artefact_is_strict_gzip_json(tmp_path):
    run_sat(tmp_path, DOCS[:2])
    path = records.artefact_path(tmp_path, "en-us", "segments", 0, 1)
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            json.loads(line, parse_constant=lambda c: pytest.fail(f"non-finite {c}"))


# ============================================================ the union segmenter


@needs_numpy
def test_union_matches_union_lib_on_random_translations():
    rng = random.Random(13)
    words = ["la", "casa", "es", "roja", "y", "el", "gato", "duerme", "mucho", "hoy", "«No»", "dijo", "ella",
             "Ναι;", "fin", "mañana"]
    for trial in range(300):
        n_units = rng.randint(1, 6)
        units = [" ".join(rng.choice(words) for _ in range(rng.randint(1, 7))) + rng.choice([".", "!", "?", "", ";"])
                 for _ in range(n_units)]
        text = " ".join(units)
        p = np.asarray(rand_probs(rng, text), dtype=np.float32)
        eng_lens = [rng.randint(3, 40) for _ in range(rng.randint(1, 6))]
        s2 = rng.uniform(0.6, 3.5)
        lang = rng.choice(["es-es", "el-gr"])
        ref_lang = "el" if lang == "el-gr" else "es"
        sat_b = sorted(ref_registered_bounds(text, p)[0])
        got = union_mod.union(text, p, eng_lens, s2, sat_b, lang, USET)
        ref = ref_union(text, p, eng_lens, s2, sat_b, ref_lang)
        assert got[0] == ref[0] and got[1] == ref[1] and got[2] == ref[2], (trial, text)
        pp = union_mod.char_boundary_probs(text, p)
        assert union_mod.project(text, None, eng_lens, s2, USET, pprime=pp)[0] == ref[1]
        for b in sat_b:
            assert union_mod.at_space_or_terminal(text, b, USET.terminal_set(lang), USET.closing_marks) == \
                ref_at_space_or_terminal(text, b, ref_lang)


@needs_numpy
def test_project_pages_matches_union_lib_and_reads_stored_pprime():
    rng = random.Random(17)
    for _ in range(200):
        e_pages = [" ".join(["The", "cat", "sat."] * rng.randint(1, 3)) for _ in range(rng.randint(1, 4))]
        t_pages = [" ".join(["El", "gato", "duerme."] * rng.randint(1, 3)) for _ in e_pages]
        eng, tgt = " ".join(e_pages), " ".join(t_pages)
        ep = np.asarray([0.9 if ch == "." else 0.0 for ch in eng], dtype=np.float32)
        tp = np.asarray(rand_probs(rng, tgt), dtype=np.float32)
        eb = sorted(ref_registered_bounds(eng, ep)[0])

        def page_ends(pages):
            ends, pos = [], 0
            for pg in pages[:-1]:
                pos += len(pg)
                ends.append(pos - 1)
                pos += 1
            return ends

        e_ends, t_ends = page_ends(e_pages), page_ends(t_pages)
        ref = ref_project_pages(tgt, tp, eng, eb, e_ends, t_ends, 2.0)
        assert union_mod.project_pages(tgt, tp, eng, eb, e_ends, t_ends, 2.0, USET) == ref
        pp = union_mod.char_boundary_probs(tgt, tp)
        assert union_mod.project_pages(tgt, None, eng, eb, e_ends, t_ends, 2.0, USET, pprime=pp) == ref


@needs_numpy
def test_project_declares_infeasible_texts_missing():
    text = "abc"
    got, info = union_mod.project(text, [0.0, 0.0, 0.0], [1, 1, 1, 1, 1], 2.0, USET)
    assert got is None and info["infeasible"]
    assert union_mod.union(text, [0.0] * 3, [1] * 5, 2.0, [], "es-es", USET)[0] is None
    assert union_mod.project("abc def", [0.0] * 7, [5], 2.0, USET) == ([], {"K": 0})


def test_terminal_set_and_additions():
    assert ";" in USET.terminal_set("el-gr") and ";" not in USET.terminal_set("en-us")
    text = 'Hola.» Adiós; fin'
    assert union_mod.terminal_additions(text, [5, 12], USET.terminal_set("es-es"), USET.closing_marks) == {5}
    assert union_mod.terminal_additions(text, [5, 12], USET.terminal_set("el-gr"), USET.closing_marks) == {5, 12}


# ============================================================ golden: the benchmark's own outputs

TU_DIR = os.environ.get("INTRACT_TU_DIR")
needs_tu = pytest.mark.skipif(not TU_DIR or not Path(TU_DIR, "earlier", "sat_probs_ags1.npz").is_file(),
                              reason="set INTRACT_TU_DIR to the translated-union strand folder")
# port_check.py's s2 per FLORES code
PORT_S2 = {"arb_Arab": 1.922, "deu_Latn": 2.378, "ell_Grek": 3.014, "fra_Latn": 2.328, "ita_Latn": 2.764,
           "tha_Thai": 3.122, "zho_Hans": 1.078, "heb_Hebr": 1.131, "ind_Latn": 2.174, "kor_Hang": 0.892,
           "nld_Latn": 2.78, "pol_Latn": 3.031, "por_Latn": 1.88, "ron_Latn": 2.005, "rus_Cyrl": 3.403,
           "spa_Latn": 2.735, "tur_Latn": 2.399, "zho_Hant": 0.614}


def make_text(units, joiner=" "):
    text, spans = "", []
    for i, u in enumerate(units):
        if i:
            text += joiner
        a = len(text)
        text += u
        spans.append((a, len(text)))
    ends = []
    for _, b in spans:
        k = b - 1
        while k >= 0 and text[k].isspace():
            k -= 1
        ends.append(k)
    return text, spans, {e for e in ends[:-1] if e >= 0}


def load_tu():
    probs = {}
    for name in ("sat_probs_ags1.npz", "sat_probs_ags2.npz"):
        with np.load(Path(TU_DIR, "earlier", name)) as z:
            probs.update({k: z[k] for k in z.files})
    return probs


def sha1(t):
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


@needs_numpy
@needs_tu
def test_port_check_registered_figures_are_reproduced():
    from intract_features.text.normalise import normalise

    probs = load_tu()
    ref = json.loads(Path(TU_DIR, "results", "port_check.json").read_text(encoding="utf-8"))["results"]["registered"]
    flores = json.loads(Path(TU_DIR, "results", "smoke", "flores_texts.json").read_text(encoding="utf-8"))
    gold = json.loads(Path(TU_DIR, "earlier", "ts_gold.json").read_text(encoding="utf-8"))
    mt = {}
    for name in ("mt_ts10.json", "mt_ts20.json"):
        mt.update(json.loads(Path(TU_DIR, "earlier", name).read_text(encoding="utf-8")))

    def evaluate(lang, pairs):
        rows = {m: [] for m in ("sat25", "ags", "ags_tsat")}
        for et, _eg, tt, tsp, tg in pairs:
            if sha1(et) not in probs or sha1(tt) not in probs:
                continue
            ep, tp = probs[sha1(et)], probs[sha1(tt)]
            eb = sat_mod.segment_text(et, ep, SETTINGS).boundaries
            sb = sat_mod.segment_text(tt, tp, SETTINGS).boundaries
            un, proj, _, _ = union_mod.union(tt, tp, union_mod.spans_lens(et, eb), PORT_S2[lang], sb, lang, USET)
            inner = rules.internal_orth_ends(tt, tsp, ORTH, cjk=lang.startswith("zho"))
            g = {diag.canon(tt, b, QUOTES) for b in tg} | {diag.canon(tt, b, QUOTES) for b in inner}
            for m, b in (("sat25", sb), ("ags", proj or []), ("ags_tsat", un or [])):
                rows[m].append(diag.counts({diag.canon(tt, x, QUOTES) for x in b}, g))
        out = {}
        for m, r in rows.items():
            tot = [sum(x[i] for x in r) for i in range(3)]
            out[m] = (round(100 * diag.prf(*tot)[2], 1), len(r))
        return out

    checked = 0
    for lang, want in ref["FL"].items():
        j = "" if lang.startswith("zho") else " "
        pairs = []
        for g in flores["groups"][:30]:
            et, _, eg = make_text([flores["lines"]["eng_Latn"][i] for i in g], " ")
            tt, tsp, tg = make_text([flores["lines"][lang][i] for i in g], j)
            pairs.append((et, eg, tt, tsp, tg))
        got = evaluate(lang, pairs)
        for m in ("sat25", "ags", "ags_tsat"):
            assert got[m] == (want[m]["F1"], want[m]["n_texts"]), ("FL", lang, m)
            checked += 1
    for lang, want in ref["TS"].items():
        j = "" if lang.startswith("zho") else " "
        units = [[normalise(u.strip()) for u in st] for st in mt[lang]["units"]]
        pairs = []
        for k, u in enumerate(units):
            et, _, eg = make_text([normalise(s) for s in gold[k]["sents"]], " ")
            tt, tsp, tg = make_text(u, j)
            pairs.append((et, eg, tt, tsp, tg))
        got = evaluate(lang, pairs)
        for m in ("sat25", "ags", "ags_tsat"):
            assert got[m] == (want[m]["F1"], want[m]["n_texts"]), ("TS", lang, m)
            checked += 1
    assert checked == 3 * (len(ref["FL"]) + len(ref["TS"]))


@needs_numpy
@needs_tu
def test_english_sat_agrees_with_the_rule_on_the_benchmark_382_boundaries():
    from intract_features.text.normalise import normalise

    probs = load_tu()
    gold = json.loads(Path(TU_DIR, "earlier", "ts_gold.json").read_text(encoding="utf-8"))
    rows_t, rows_e = [], []
    for k in range(20):
        sents = [normalise(s) for s in gold[k]["sents"]]
        et, _, eg = make_text(sents, " ")
        assert rules.rule_sentences(et, RULE) == sents  # the frozen rule reproduces its own gold units
        rule_b = boundaries_of(rules.rule_spans(et, RULE))
        assert set(rule_b) == eg
        sat_b = sat_mod.segment_text(et, probs[sha1(et)], SETTINGS).boundaries
        tol, exact = diag.score_text(et, sat_b, rule_b, QUOTES)
        rows_t.append(tol)
        rows_e.append(exact)
    tol = [sum(r[i] for r in rows_t) for i in range(3)]
    assert tol == [382, 0, 0]  # S3: "Segment any Text agreed with the frozen rule on all 382 boundaries"
    rep = diag.boot_prf(rows_t, diag.bootstrap_rng(20261026, 18), 2000)
    assert rep["F1"] == 100.0 and rep["F1_ci"] == [100.0, 100.0]
