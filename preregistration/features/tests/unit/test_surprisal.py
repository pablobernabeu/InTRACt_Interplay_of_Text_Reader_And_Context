"""Tests of features/surprisal.py and the surprisal stages.

The first part runs anywhere: a character-level tokeniser with SentencePiece's word-start marker and a deterministic
toy language model stand in for Goldfish. It carries the checks of the benchmark's verify-surprisal/scripts/t_pm.py:
(i) the telescoping identity, (ii) S >= 0 and (iii) a brute-force word probability from fresh model calls on
truncated inputs. The second part, skipped without torch, transformers and tokenizers, builds tiny randomly
initialised GPT-2 and XGLM models from configs and checks the PyTorch backend: fixed batch shapes, the chunked output
layer, pinned loading from safetensors, the pickle conversion and the bf16 mode.
"""

from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

import pytest

from intract_features import cli, records
from intract_features import config as config_mod
from intract_features.features import surprisal as S
from intract_features.stages import surprisal_goldfish, surprisal_xglm

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
MARK = "▁"
ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.,!?'\"-–:;"
SPECIALS = ["<unk>", "<s>", "</s>", "[CLS]", "[SEP]", "<pad>", MARK]
VOCAB = SPECIALS + [MARK + c for c in ALPHABET] + list(ALPHABET)


# ------------------------------------------------------------------------------------------------ toy tokeniser and LM


class CharTokeniser:
    """Characters as pieces, a word's first one carrying the word-start marker, as SentencePiece does.

    A first character with no marked piece becomes a bare marker plus the character, and characters outside the
    alphabet are <unk>, as in the Goldfish tokenisers. Offsets mimic the tokenizers library: a marked piece covers the
    space before it, and a bare marker at the text's start covers nothing.
    """

    def __init__(self, vocab=VOCAB):
        self.vocab = {p: i for i, p in enumerate(vocab)}
        self.pieces = list(vocab)

    def encode(self, text):
        ids, offs = [], []
        unk = self.vocab["<unk>"]
        for m in re.finditer(r"[^ ]+", text):
            a, b = m.span()
            sp = a - 1 if a > 0 else a
            word = m.group()
            if MARK + word[0] in self.vocab:
                ids.append(self.vocab[MARK + word[0]])
                offs.append((sp, a + 1))
            else:
                ids.append(self.vocab[MARK])
                offs.append((sp, a) if a > 0 else (0, 0))
                ids.append(self.vocab.get(word[0], unk))
                offs.append((a, a + 1))
            for k in range(1, len(word)):
                ids.append(self.vocab.get(word[k], unk))
                offs.append((a + k, a + k + 1))
        return ids, offs

    def token_to_id(self, token):
        return self.vocab.get(token)

    def id_to_token(self, i):
        return self.pieces[i] if 0 <= i < len(self.pieces) else None


def _logsumexp(xs):
    xs = list(xs)
    if not xs:
        return float("-inf")
    m = max(xs)
    return m + math.log(math.fsum(math.exp(x - m) for x in xs))


class ToyLM:
    """A deterministic language model whose next-token distribution depends on the last two inputs and the position.

    Because the position in the window enters it, a token's value differs between windows, which makes the
    first-window rule observable.
    """

    def __init__(self, mask, positions=512):
        self.mask = list(mask)
        self.size = len(mask)
        self.positions = positions
        self.calls = 0

    def dist(self, prefix):
        k = len(prefix) - 1
        last, prev = prefix[-1], (prefix[-2] if len(prefix) > 1 else 0)
        logits = [2.0 * math.sin(0.7 * v + 1.3 * last + 0.4 * prev + 0.05 * k) for v in range(self.size)]
        z = _logsumexp(logits)
        return [x - z for x in logits]

    def score(self, windows):
        out = []
        for w in windows:
            self.calls += 1
            assert len(w) <= self.positions
            tl, bl, en = [], [], []
            for k in range(len(w)):
                lp = self.dist(w[:k + 1])
                if k + 1 < len(w):
                    tl.append(lp[w[k + 1]])
                bl.append(_logsumexp(lp[v] for v in range(self.size) if self.mask[v]))
                en.append(-math.fsum(math.exp(x) * x for x in lp))
            out.append(S.WindowScores(target_logp=tl, boundary_logmass=bl, entropy=en))
        return out


TABLE = {"—": "–", "«": '"', "»": '"', "’": "'"}


def toy_scorer(positions=512, stride=256, table=TABLE):
    tok = CharTokeniser()
    mask = S.boundary_mask(tok, len(VOCAB), MARK, tok.token_to_id("[SEP]"))
    lm = ToyLM(mask, positions=max(positions, 8))
    return S.Scorer(tokeniser=tok, backend=lm, start_id=tok.token_to_id("[CLS]"), unknown_id=tok.token_to_id("<unk>"),
                    positions=positions, stride=stride, table=table)


def prepared(text, story_id="S1", openers=("“",)):
    return S.prepare_text(story_id, text, openers=openers)


# ------------------------------------------------------------------------------------------------ windows


def _gf_scorer_starts(T, W, stride):
    """The window starts of the benchmark engine (predictability/scripts/gf_scorer.py, token_stats)."""
    starts = [0]
    if T > W:
        a = 0
        while a + W < T:
            a = min(a + stride, T - W) if stride < W else a + W
            starts.append(a)
    return starts


@pytest.mark.parametrize("n", [1, 5, 510, 511, 512, 600, 767, 1022, 1023, 2036, 2500])
def test_windows_follow_the_registered_rule(n):
    plan = S.plan_windows(n, 512, 256)
    assert [w.start for w in plan] == _gf_scorer_starts(n, 511, 256)
    assert plan[-1].end == n  # "the last one ends at the text's final token"
    covered = [i for w in plan for i in range(w.keep_from, w.end)]
    assert covered == list(range(n))  # each token from exactly one window, the first that contains it
    for w in plan:
        assert w.end - w.start == min(511, n)  # every window of a long text is full: [CLS] plus 511 tokens
    first_end = plan[0].end
    ctx = [i - w.start for w in plan for i in range(w.keep_from, w.end)]
    assert all(c >= 255 for c in ctx[first_end:])  # "at least 255 tokens of preceding context"


def test_window_geometry_is_validated():
    with pytest.raises(ValueError):
        S.plan_windows(10, 512, 0)
    with pytest.raises(ValueError):
        S.plan_windows(10, 512, 512)
    with pytest.raises(ValueError):
        S.plan_windows(10, 1, 1)
    assert S.plan_windows(0, 512, 256) == []
    assert S.window_inputs([5, 6, 7], S.plan_windows(3, 512, 256), 9) == [[9, 5, 6, 7]]


# ------------------------------------------------------------------------------------------------ text preparation


def test_whitespace_is_collapsed_and_words_keep_their_punctuation():
    text = "  Hello ,   world\n “ Hi — there.  "
    p = prepared(text)
    assert p.text == "Hello , world “ Hi — there."
    words = [p.text[a:b] for a, b in p.word_spans]
    # a punctuation-only token joins the preceding word, an opening quotation mark the following one (plan v3)
    assert words == ["Hello ,", "world", "“ Hi —", "there."]
    from intract_features.text.words import count_words

    assert p.n_words == count_words(text)


def test_replacement_table_is_one_to_one_and_applies_only_to_unknown_characters():
    with pytest.raises(ValueError):
        S.check_table({"…": "..."})
    unknown = {"«", "»", "§"}
    active = S.active_replacements({"«": '"', "—": "–", "»": "§"}, lambda c: c in unknown)
    assert active == {"«": '"'}  # the em dash is known; the target § is itself unknown
    out, counts = S.apply_replacements("«Hi« —", active)
    assert out == '"Hi" —' and counts == {"«": 2}
    assert S.apply_replacements("plain", active) == ("plain", {})


def test_opening_marks_skip_symmetric_quotes():
    assert S.opening_marks([["“", "”"], ["‘", "’"], ['"', '"']]) == {"“", "‘"}


# ------------------------------------------------------------------------------------------------ alignment


def test_tokens_are_assigned_by_their_first_non_space_character():
    tok = CharTokeniser()
    text = "§ab cd"  # a bare marker at the start, then <unk>
    ids, offs = tok.encode(text)
    p = S.prepare_text("S", text)
    assert S.assign_tokens(p.text, offs, p.word_spans) == [0, 0, 0, 0, 1, 1]


def test_misplaced_tokens_are_refused():
    with pytest.raises(S.AlignmentError):
        S.assign_tokens("ab cd", [(3, 4), (0, 1)], [(0, 2), (3, 5)])  # not contiguous
    with pytest.raises(S.AlignmentError):
        S.assign_tokens("ab", [(0, 1)], [])


# ------------------------------------------------------------------------------------------------ the correction


TEXT = ("The little fox ran to the old oak. “Wait!” said the owl, and the fox stopped. "
        "They talked until the moon rose — then both went home.")


def _score(text, **kw):
    sc = toy_scorer(**kw)
    p = prepared(text)
    return sc, p, sc.score([p])[0]


def test_telescoping_identity_and_non_negative_word_surprisal():
    sc, p, res = _score(TEXT)
    ws, ts = res.words, res.tokens
    # (i) sum of corrected word surprisals - sum of token surprisals = lambda(first token) - lambda(end)
    lhs = math.fsum(ws.corrected) - math.fsum(ts.surprisal)
    rhs = ts.boundary_before[0] - ts.boundary_end
    assert abs(lhs - rhs) < 1e-9
    assert abs(ws.identity_residual) < 1e-9
    # (ii) every corrected word surprisal is a proper surprisal
    assert min(ws.corrected) >= -1e-12
    assert len(ws.corrected) == p.n_words


def _model_ids(sc, p):
    """The ids the scorer gave the model: the text after its active replacements."""
    model_text, _ = S.apply_replacements(p.text, sc.active)
    ids, offs = sc.tokeniser.encode(model_text)
    return model_text, ids, offs


def test_corrected_word_probability_matches_brute_force():
    """(iii) of t_pm.py: p(word | ctx) recomputed from fresh calls on truncated inputs, outside the windows."""
    sc, p, res = _score(TEXT)
    tok, lm = sc.tokeniser, sc.backend
    model_text, ids, offs = _model_ids(sc, p)
    t2w = S.assign_tokens(model_text, offs, p.word_spans)
    cls = tok.token_to_id("[CLS]")
    mask = lm.mask
    for wi in (1, p.n_words // 2, p.n_words - 1):
        idx = [i for i, w in enumerate(t2w) if w == wi]
        f, last = idx[0], idx[-1]
        lp_ctx = lm.dist([cls] + ids[:f])
        lp_tokens = math.fsum(lm.dist([cls] + ids[:f + k])[ids[f + k]] for k in range(len(idx)))
        lp_after = lm.dist([cls] + ids[:last + 1])
        lp_end = _logsumexp(lp_after[v] for v in range(len(mask)) if mask[v])
        lp_start = _logsumexp(lp_ctx[v] for v in range(len(mask)) if mask[v])
        brute = -(lp_tokens + lp_end - lp_start)
        assert res.words.corrected[wi] == pytest.approx(brute, abs=1e-9)


def test_each_token_takes_the_values_of_the_first_window_that_contains_it():
    sc, p, res = _score(TEXT, positions=12, stride=5)
    tok, lm = sc.tokeniser, sc.backend
    _, ids, _ = _model_ids(sc, p)
    cls = tok.token_to_id("[CLS]")
    plan = S.plan_windows(len(ids), 12, 5)
    assert len(plan) > 3 and res.n_windows == len(plan)
    for w in plan:
        for i in range(w.keep_from, w.end):
            lp = lm.dist([cls] + ids[w.start:i])  # the window's own context, after [CLS]
            assert res.tokens.surprisal[i] == pytest.approx(-lp[ids[i]], abs=1e-12)
    assert res.tokens.min_context_after_first_window() >= 11 - 5
    lhs = math.fsum(res.words.corrected) - math.fsum(res.tokens.surprisal)
    assert lhs == pytest.approx(res.tokens.boundary_before[0] - res.tokens.boundary_end, abs=1e-9)


def test_unknown_words_names_and_replacements():
    text = "Ann saw «dogs» and a § sign."
    sc, p, res = _score(text)
    # the toy alphabet lacks the four sources and holds the targets; Goldfish's English tokeniser knows the em dash
    assert sc.active == {"—": "–", "«": '"', "»": '"', "’": "'"}
    assert res.replacements == {"«": 1, "»": 1}
    unknown_words = [i for i, u in enumerate(res.word_unknown) if u]
    assert unknown_words == [4]  # the section sign is not in the table
    names = [i == 0 for i in range(p.n_words)]
    values, diag = S.summarise(res, p, names)
    kept = [res.words.corrected[i] for i in range(p.n_words) if i not in (0, 4)]
    assert values["mean"] == pytest.approx(math.fsum(kept) / len(kept))
    all_words = [res.words.corrected[i] for i in range(p.n_words) if i != 4]
    assert values["mean_all_words"] == pytest.approx(math.fsum(all_words) / len(all_words))
    assert diag["words_unknown"] == [4] and diag["names_excluded"] == 1 and diag["counted_words"] == p.n_words - 2
    assert S.text_mean(diag["word_surprisal"], [i in (0, 4) for i in range(p.n_words)]) == pytest.approx(
        values["mean"], abs=1e-5)
    unmasked, _ = S.summarise(res, p, None)
    assert unmasked["mean"] is None and unmasked["mean_all_words"] == values["mean_all_words"]
    json.dumps(diag, allow_nan=False)


def test_descriptive_measures():
    sc, p, res = _score(TEXT)
    _, diag = S.summarise(res, p, None, sd_ddof=0)
    d = diag["descriptive"]
    usable = [i for i in range(p.n_words) if not res.word_unknown[i]]  # the curly quotes are unknown here
    assert diag["words_unknown"] and len(usable) == diag["counted_words"]
    vals = [res.words.corrected[i] for i in usable]
    mean = math.fsum(vals) / len(vals)
    assert d["sd"] == pytest.approx(math.sqrt(math.fsum((v - mean) ** 2 for v in vals) / len(vals)))
    assert d["surprisal_per_character"] == pytest.approx(math.fsum(res.tokens.surprisal) / len(p.text))
    ent = [res.tokens.entropy_before[res.words.first_token[i]] for i in usable]
    assert d["mean_next_token_entropy"] == pytest.approx(math.fsum(ent) / len(ent))


def test_alignment_failure_is_recorded_when_not_strict():
    class Broken(CharTokeniser):
        def encode(self, text):
            ids, offs = super().encode(text)
            return ids, list(reversed(offs))

    sc = toy_scorer()
    sc.tokeniser = Broken()
    p = prepared("one two three")
    with pytest.raises(S.AlignmentError):
        sc.score([p], strict=True)
    res = sc.score([p], strict=False)[0]
    values, diag = S.summarise(res, p, None)
    assert values == {"mean": None, "mean_all_words": None} and "error" in diag


def test_texts_without_words_are_undefined_not_errors():
    sc = toy_scorer()
    for text in ("", "... !! —"):
        p = prepared(text)
        res = sc.score([p], strict=True)[0]  # no alignment error, even when strict
        values, diag = S.summarise(res, p, None)
        assert res.n_tokens == 0 and values == {"mean": None, "mean_all_words": None}
        assert diag["error"] == "no registered words"


# ------------------------------------------------------------------------------------------------ agreement and keys


def test_pearson_and_precision_agreement():
    assert S.pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert S.pearson([1, 1, 1], [1, 2, 3]) is None
    assert S.pearson([1, 2], [1, 2]) is None
    a = [(4.0, 4.001), (5.0, 5.0), (6.0, 6.002), (4.5, 4.5)]
    out = S.precision_agreement(a, 0.995)
    assert out["texts"] == 4 and out["passes"] and out["max_abs_difference"] == pytest.approx(0.002)
    assert not S.precision_agreement([(1.0, 3.0), (2.0, 1.0), (3.0, 2.0)], 0.995)["passes"]


def test_pin_label_reads_the_lock_format():
    lock = {"models": {"org/m": {"repo": "org/m", "revision": "abc"}}}
    assert S.pin_label(lock, "org/m") == "org/m@abc"
    assert S.pin_label({}, "org/m") == "org/m@unpinned"


def test_keyed_fraction_is_stable():
    keys = {"prefix": "intract", "version": "v1"}
    f = S.keyed_fraction("S1", "bf16_check", keys)
    assert 0.0 <= f < 1.0 and f == S.keyed_fraction("S1", "bf16_check", keys)
    assert f != S.keyed_fraction("S1", "other", keys)


# ------------------------------------------------------------------------------------------------ the stages


ANIMALS = ["cat", "dog", "owl", "fox", "hen"]


def _docs():
    return [records.Document(story_id=f"S{i}", lang="en-us", level="young", kind="generated", title="T",
                             pages=(f"Page one of a story. The {a} sat.", "“Hello,” said Tom — twice.",
                                    f"The {a} slept."))
            for i, a in enumerate(ANIMALS)]


def _ctx(tmp_path, stage, extra, cfg=None):
    cfg = cfg or config_mod.load(CONFIG_DIR)
    ctx = cli.StageContext(stage=stage, config=cfg, lang="en-us", work=tmp_path, extra=extra)
    records.write_jsonl(ctx.path("documents"), [d.to_json() for d in _docs()])
    return ctx


def test_goldfish_stage_with_injected_scorers(tmp_path):
    cfg = config_mod.load(CONFIG_DIR)
    cfg["stages"]["surprisal_goldfish"]["stage"]["strict"] = True
    ctx = _ctx(tmp_path, surprisal_goldfish.STAGE, {"scorers": {"tier_1gb": toy_scorer(), "tier_100mb": toy_scorer(
        stride=128)}}, cfg)
    rec = cli.run_stage(surprisal_goldfish, ctx)
    out = list(records.read_jsonl(ctx.path("surprisal_goldfish")))
    assert len(out) == 5 and rec["counts"]["documents"] == 5
    for key in ("documents", "words", "characters", "tokens"):
        assert rec["counts"][key] > 0
    v = out[0]["values"]
    assert set(v) == {"mean_surprisal", "mean_surprisal_all_words", "mean_surprisal_100mb",
                      "mean_surprisal_100mb_all_words"}
    assert v["mean_surprisal"] is None and v["mean_surprisal_all_words"] > 0  # no name mask until P06
    d = out[0]["diagnostics"]["models"]["tier_1gb"]
    assert len(d["word_surprisal"]) == out[0]["diagnostics"]["words"]
    assert d["model"] == S.pin_label(cfg["models"], cfg["languages"]["en-us"]["goldfish"]["tier_1gb"])
    timing = json.loads((tmp_path / "en-us" / "_timing" / "surprisal_goldfish-shard-0-of-1.json").read_text())
    assert timing["counts"]["tokens"] == rec["counts"]["tokens_tier_1gb"]


def test_goldfish_stage_applies_a_name_mask_from_an_artefact(tmp_path):
    cfg = config_mod.load(CONFIG_DIR)
    scfg = cfg["stages"]["surprisal_goldfish"]
    scfg["names"]["source"] = "artefact"
    scfg["names"]["artefact"] = "names_fixture"
    ctx = _ctx(tmp_path, surprisal_goldfish.STAGE, {"scorers": {"tier_1gb": toy_scorer(),
                                                                "tier_100mb": toy_scorer()}}, cfg)
    from intract_features.text.words import count_words

    # word 10 is "Tom" with the attached dash, which the replacement table makes encodable
    rows = [{"story_id": d.story_id, "diagnostics": {"words": count_words(d.text), "name_word_indices": [10]}}
            for d in _docs()]
    records.write_jsonl(ctx.path("names_fixture"), rows)
    cli.run_stage(surprisal_goldfish, ctx)
    out = list(records.read_jsonl(ctx.path("surprisal_goldfish")))
    rec = out[0]
    diag = rec["diagnostics"]["models"]["tier_1gb"]
    words = diag["word_surprisal"]
    excluded = {10, *diag["words_unknown"]}  # the name, and the words the toy tokeniser cannot encode
    expected = S.text_mean(words, [i in excluded for i in range(len(words))])
    assert rec["values"]["mean_surprisal"] == pytest.approx(expected, abs=1e-5)
    assert rec["diagnostics"]["names_applied"] is True and diag["names_excluded"] == 1


def test_goldfish_stage_refuses_bf16(tmp_path):
    cfg = config_mod.load(CONFIG_DIR)
    scfg = cfg["stages"]["surprisal_goldfish"]
    scfg["precision"]["mode"] = "bf16"
    with pytest.raises(ValueError):
        surprisal_goldfish.run(_ctx(tmp_path, surprisal_goldfish.STAGE, {"scorers": {}}, cfg))


def test_xglm_stage_records_the_bf16_check(tmp_path):
    cfg = config_mod.load(CONFIG_DIR)
    scfg = cfg["stages"]["surprisal_xglm"]
    scfg["precision"]["mode"] = "bf16"
    scfg["precision"]["check_fraction"] = 1.0
    ctx = _ctx(tmp_path, surprisal_xglm.STAGE, {"scorers": {"xglm": toy_scorer(positions=2048, stride=1024)},
                                                "check_scorers": {"xglm": toy_scorer(positions=2048, stride=1024)}},
               cfg)
    rec = cli.run_stage(surprisal_xglm, ctx)
    check = rec["counts"]["precision_check"]
    assert check["texts"] == 5 and check["passes"] and check["r"] == pytest.approx(1.0)
    out = list(records.read_jsonl(ctx.path("surprisal_xglm")))
    assert "fp32_check" in out[0]["diagnostics"]["models"]["xglm"]
    assert set(out[0]["values"]) == {"mean_surprisal_xglm", "mean_surprisal_xglm_all_words"}


def test_xglm_stage_in_fp32_runs_no_check(tmp_path):
    ctx = _ctx(tmp_path, surprisal_xglm.STAGE, {"scorers": {"xglm": toy_scorer(positions=2048, stride=1024)}})
    rec = cli.run_stage(surprisal_xglm, ctx)
    assert "precision_check" not in rec["counts"] and rec["counts"]["precision"] == "fp32"


def test_stage_configurations_hold_the_registered_values():
    cfg = config_mod.load(CONFIG_DIR)["stages"]
    g, x = cfg["surprisal_goldfish"], cfg["surprisal_xglm"]
    assert (g["windows"]["positions"], g["windows"]["stride"]) == (512, 256)
    assert g["tokens"]["start"] == "[CLS]" and g["tokens"]["end_of_sequence"] == "[SEP]"
    assert g["precision"]["allowed_modes"] == ["fp32"] and g["precision"]["logprob_dtype"] == "float32"
    assert x["precision"]["agreement_threshold"] == 0.995 and x["precision"]["mode"] == "fp32"
    assert x["tokens"]["start"] == "</s>" and x["windows"]["positions"] == 2048
    table = S.table_from_code_points(g["replacements"]["code_points"])
    assert table == S.table_from_code_points(x["replacements"]["code_points"])
    # plan v3: "The table maps U+2014 to U+2013; ‘ ’ ‚ ‹ › to '; “ ” „ « » to "; U+2010 and U+2011 to -."
    expected = {0x2014: 0x2013, **dict.fromkeys((0x2018, 0x2019, 0x201A, 0x2039, 0x203A), 0x27),
                **dict.fromkeys((0x201C, 0x201D, 0x201E, 0x00AB, 0x00BB), 0x22), 0x2010: 0x2D, 0x2011: 0x2D}
    assert table == {chr(a): chr(b) for a, b in expected.items()}
    assert S.ModelSettings.from_config(g).table == table
    S.ModelSettings.from_config(x)
    with pytest.raises(ValueError):
        S.table_from_code_points([[0x2014, 0x2013], [0x2014, 0x2D]])


# ------------------------------------------------------------------------------------------------ PyTorch backend


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    """A tokenizer.json with the toy vocabulary and tiny random GPT-2 and XGLM checkpoints, pinned in a lock."""
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    tokenizers = pytest.importorskip("tokenizers")
    pytest.importorskip("safetensors")
    root = tmp_path_factory.mktemp("tiny_lm")
    scores = [(p, 0.0) for p in SPECIALS[:-1]] + [(MARK, -6.0)] + [(MARK + c, -1.0) for c in ALPHABET] + [
        (c, -2.0) for c in ALPHABET]
    tok = tokenizers.Tokenizer(tokenizers.models.Unigram(scores, unk_id=0, byte_fallback=False))
    tok.pre_tokenizer = tokenizers.pre_tokenizers.Metaspace(replacement=MARK, prepend_scheme="always")
    tok.add_special_tokens(SPECIALS[:-1])
    lock = {}
    torch.manual_seed(0)
    gpt2 = transformers.GPT2LMHeadModel(transformers.GPT2Config(
        vocab_size=len(VOCAB), n_positions=16, n_embd=32, n_layer=2, n_head=2, bos_token_id=3, eos_token_id=4))
    xglm = transformers.XGLMForCausalLM(transformers.XGLMConfig(
        vocab_size=len(VOCAB), d_model=32, num_layers=2, attention_heads=2, ffn_dim=64, max_position_embeddings=32,
        pad_token_id=5, bos_token_id=1, eos_token_id=2, dropout=0.0, attention_dropout=0.0))
    for name, model in (("tiny/gpt2", gpt2), ("tiny/xglm", xglm)):
        folder = root / name.replace("/", "__")
        model.save_pretrained(folder, safe_serialization=True)
        tok.save(str(folder / "tokenizer.json"))
        files = {f: records.sha256_file(folder / f) for f in ("config.json", "model.safetensors", "tokenizer.json")}
        lock[name] = {"repo": name, "revision": "test", "path": str(folder), "files": files}
    return {"root": root, "lock": lock, "gpt2": gpt2.eval(), "xglm": xglm.eval(), "torch": torch}


def _settings(stage, **runtime):
    cfg = copy.deepcopy(config_mod.load(CONFIG_DIR)["stages"][stage])
    cfg["windows"].update(positions=16, stride=8)
    cfg["runtime"].update(device="cpu", windows_per_batch=4, pad_to_window=True, positions_per_chunk=5)
    cfg["runtime"].update(runtime)
    return cfg


def test_torch_backend_matches_the_full_forward_pass(tiny):
    torch = tiny["torch"]
    cfg = _settings("surprisal_goldfish")
    settings = S.ModelSettings.from_config(cfg)
    sc = S.load_scorers("tiny/gpt2", settings, tiny["lock"], ["fp32"])["fp32"]
    window = [3, 10, 20, 30, 40, 7, 8]
    got = sc.backend.score([window])[0]
    with torch.inference_mode():
        lp = torch.log_softmax(tiny["gpt2"](input_ids=torch.tensor([window])).logits[0].float(), -1).double()
    mask = torch.tensor(sc.backend.mask.tolist())
    # The stage pads to the window and runs eager attention; the reference runs unpadded with the default attention,
    # so the two agree to fp32 round-off, not bit for bit.
    assert got.target_logp == pytest.approx([lp[k, window[k + 1]].item() for k in range(len(window) - 1)], abs=1e-5)
    assert got.boundary_logmass == pytest.approx(torch.logsumexp(lp[:, mask], -1).tolist(), abs=1e-5)
    assert got.entropy == pytest.approx((-(lp.exp() * lp).sum(-1)).tolist(), abs=1e-5)


def test_torch_scores_do_not_depend_on_batch_companions(tiny):
    settings = S.ModelSettings.from_config(_settings("surprisal_goldfish"))
    sc = S.load_scorers("tiny/gpt2", settings, tiny["lock"], ["fp32"])["fp32"]
    a = prepared("The fox ran to the old oak and the owl said hi.", "A")
    b = prepared("Short one.", "B")
    c = prepared("Another, quite different, text with words.", "C")
    alone = sc.score([a])[0]
    mixed = sc.score([b, a, c])[1]
    assert alone.tokens.surprisal == mixed.tokens.surprisal  # identical floats, not merely close
    assert alone.words.corrected == mixed.words.corrected
    assert alone.n_windows > 1


def test_torch_scorer_matches_direct_computation_and_identity(tiny):
    torch = tiny["torch"]
    settings = S.ModelSettings.from_config(_settings("surprisal_goldfish", pad_to_window=False, windows_per_batch=1))
    sc = S.load_scorers("tiny/gpt2", settings, tiny["lock"], ["fp32"])["fp32"]
    p = prepared("The fox ran far.", "A")
    res = sc.score([p])[0]
    ids, _ = sc.tokeniser.encode(p.text)
    assert len(ids) < 15
    with torch.inference_mode():
        lp = torch.log_softmax(tiny["gpt2"](input_ids=torch.tensor([[3] + ids])).logits[0], -1)
    direct = [-lp[k, ids[k]].item() for k in range(len(ids))]
    assert res.tokens.surprisal == pytest.approx(direct, abs=1e-5)
    assert abs(res.words.identity_residual) < 1e-9 and min(res.words.corrected) >= -1e-9


def test_torch_bf16_mode_and_agreement(tiny):
    settings = S.ModelSettings.from_config(_settings("surprisal_xglm", windows_per_batch=1, pad_to_window=False))
    scorers = S.load_scorers("tiny/xglm", settings, tiny["lock"], ["bf16", "fp32"])
    torch = tiny["torch"]
    assert next(scorers["bf16"].backend.model.parameters()).dtype == torch.bfloat16
    assert next(scorers["fp32"].backend.model.parameters()).dtype == torch.float32
    texts = [prepared(t, f"S{i}") for i, t in enumerate(["The fox ran.", "A cat sat on a mat today.",
                                                          "Owls hoot at night, they say!", "Big red dogs bark."])]
    pairs = []
    for p, lo, hi in zip(texts, scorers["bf16"].score(texts), scorers["fp32"].score(texts), strict=True):
        pairs.append((S.summarise(hi, p, None)[0]["mean_all_words"], S.summarise(lo, p, None)[0]["mean_all_words"]))
    out = S.precision_agreement(pairs, 0.995)
    assert out["texts"] == 4 and out["r"] is not None


def test_stage_loads_pinned_tiny_models(tiny, tmp_path):
    cfg = config_mod.load(CONFIG_DIR)
    cfg["models"] = tiny["lock"]
    cfg["languages"]["en-us"]["goldfish"] = {"tier_1gb": "tiny/gpt2", "tier_100mb": "tiny/gpt2"}
    scfg = cfg["stages"]["surprisal_goldfish"]
    scfg["windows"].update(positions=16, stride=8)
    scfg["runtime"].update(device="cpu", windows_per_batch=4)
    scfg["stage"]["strict"] = True
    ctx = _ctx(tmp_path, surprisal_goldfish.STAGE, {}, cfg)
    rec = cli.run_stage(surprisal_goldfish, ctx)
    assert rec["counts"]["models"]["tier_1gb"] == "tiny/gpt2@test"
    assert rec["counts"]["runtime"]["fp32_precision"]["generic"] == "ieee"
    assert rec["counts"]["forward_calls_tier_1gb"] > 0
    out = list(records.read_jsonl(ctx.path("surprisal_goldfish")))
    assert out[0]["values"]["mean_surprisal_all_words"] == out[0]["values"]["mean_surprisal_100mb_all_words"]


def test_tampered_weights_are_refused(tiny, tmp_path):
    lock = copy.deepcopy(tiny["lock"])
    lock["tiny/gpt2"]["files"]["model.safetensors"] = "0" * 64
    settings = S.ModelSettings.from_config(_settings("surprisal_goldfish"))
    with pytest.raises(ValueError):
        S.load_scorers("tiny/gpt2", settings, lock, ["fp32"])


def test_pickled_checkpoint_conversion(tiny, tmp_path):
    """The build job's conversion: a GPT-2 pickle with tied output layer and old buffers becomes a loadable,
    pinnable safetensors file that gives the same scores."""
    torch = tiny["torch"]
    model = tiny["gpt2"]
    state = dict(model.state_dict())
    state["lm_head.weight"] = state["transformer.wte.weight"]
    for i in range(2):
        state[f"transformer.h.{i}.attn.bias"] = torch.ones(1, 1, 16, 16)
        state[f"transformer.h.{i}.attn.masked_bias"] = torch.tensor(-1e4)
    src = tmp_path / "pytorch_model.bin"
    torch.save(state, src)
    folder = tmp_path / "converted"
    gcfg = config_mod.load(CONFIG_DIR)["stages"]["surprisal_goldfish"]["loading"]
    info = S.convert_pickled_checkpoint(src, folder / "model.safetensors", drop=gcfg["conversion_drop"],
                                        tied=gcfg["conversion_tied"])
    assert "lm_head.weight" in info["dropped"] and "transformer.h.0.attn.bias" in info["dropped"]
    for f in ("config.json", "tokenizer.json"):
        (folder / f).write_bytes((Path(tiny["lock"]["tiny/gpt2"]["path"]) / f).read_bytes())
    files = {f: records.sha256_file(folder / f) for f in ("config.json", "model.safetensors", "tokenizer.json")}
    assert files["model.safetensors"] == info["sha256"]
    lock = {"tiny/converted": {"repo": "tiny/converted", "revision": "test", "path": str(folder), "files": files}}
    settings = S.ModelSettings.from_config(_settings("surprisal_goldfish"))
    sc = S.load_scorers("tiny/converted", settings, lock, ["fp32"])["fp32"]
    ref = S.load_scorers("tiny/gpt2", settings, tiny["lock"], ["fp32"])["fp32"]
    p = prepared("The fox ran to the old oak and back.", "A")
    assert sc.score([p])[0].words.corrected == ref.score([p])[0].words.corrected


def test_configure_torch_turns_tf32_off(tiny):
    state = S.configure_torch({"fp32_precision": "ieee", "deterministic_algorithms": True, "offline": True})
    torch = tiny["torch"]
    if hasattr(torch.backends, "fp32_precision"):
        assert state["fp32_precision"] == {"generic": "ieee", "cuda_matmul": "ieee", "cudnn_conv": "ieee",
                                           "cudnn_rnn": "ieee"}
    assert state["deterministic_algorithms"] is True
