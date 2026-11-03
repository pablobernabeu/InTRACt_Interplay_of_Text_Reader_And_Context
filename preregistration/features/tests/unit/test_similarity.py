"""Tests of features/similarity.py and the encoder stages.

The first part runs anywhere, with a fake encoder whose vectors are a fixed function of the text. The second part,
skipped without torch, transformers and tokenizers, builds a tiny randomly initialised XLM-RoBERTa from a config and
checks the encoder: mean and first-token pooling against the model's own outputs, L2 normalisation, truncation, and
that a sentence's vector does not depend on the sentences that share its call.
"""

from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path

import pytest

from intract_features import cli, records
from intract_features import config as config_mod
from intract_features.features import similarity as SIM
from intract_features.stages import encode_bgem3, encode_e5

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def unit(v):
    n = math.sqrt(math.fsum(x * x for x in v))
    return [x / n for x in v]


class FakeEncoder:
    """Unit vectors from a hash of the text, so equal texts get equal vectors."""

    def __init__(self, dim=8):
        self.dim = dim
        self.calls = []
        self.tokens = 0
        self.forward_calls = 0

    def encode(self, texts):
        self.calls.append(list(texts))
        self.forward_calls += 1
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            out.append(unit([h[i] - 127.5 for i in range(self.dim)]))
            self.tokens += len(t.split())
        return out


# ------------------------------------------------------------------------------------------------ pure parts


def test_buckets_and_fixed_call_shapes():
    buckets = (16, 32, 64)
    assert SIM.bucket_length(1, buckets) == 16 and SIM.bucket_length(17, buckets) == 32
    with pytest.raises(ValueError):
        SIM.bucket_length(65, buckets)
    plan = SIM.plan_batches([5, 20, 3, 40, 18, 16], buckets, tokens_per_batch=64)
    assert plan == [(16, 4, [0, 2, 5]), (32, 2, [1, 4]), (64, 1, [3])]
    # a sentence's bucket and call shape depend on its own length only
    alone = SIM.plan_batches([20], buckets, 64)
    assert alone == [(32, 2, [0])]


def test_adjacent_cosines_and_mean():
    vs = [unit([1, 0, 0]), unit([1, 1, 0]), unit([0, 1, 0])]
    cos = SIM.adjacent_cosines(vs)
    assert cos == pytest.approx([1 / math.sqrt(2), 1 / math.sqrt(2)])
    assert SIM.mean_similarity(cos) == pytest.approx(1 / math.sqrt(2))
    assert SIM.adjacent_cosines(vs[:1]) == [] and SIM.mean_similarity([]) is None


def test_adjacent_cosines_of_an_array_match_the_plain_path():
    np = pytest.importorskip("numpy")
    vs = [unit([1, 0, 0]), unit([1, 1, 0]), unit([0, 1, 0])]
    assert SIM.adjacent_cosines(np.array(vs, dtype=np.float32)) == pytest.approx(SIM.adjacent_cosines(vs), abs=1e-7)
    assert SIM.adjacent_cosines(np.zeros((1, 3), dtype=np.float32)) == []


def test_segment_rules():
    rules = SIM.SegmentRules(source_segmenter="sat", translation_segmenter="union", allow_sat_alone=False)
    assert rules.refusal("sat", True) is None
    assert rules.refusal("union", False) is None
    assert rules.refusal("sat", False) is not None  # SaT alone is not a translation's registered segmentation
    assert SIM.SegmentRules("sat", "union", True).refusal("sat", False) is None


def _doc(i=0, pages=("One cat sat. It purred.", "Then it slept! The end.")):
    return records.Document(story_id=f"S{i}", lang="en-us", level="young", kind="generated", title="T",
                            pages=pages)


def _segments_record(doc, segmenter="sat", is_source=True):
    """A segments record as the sat stage writes it, with sentences cut at terminal marks."""
    text = doc.text
    spans, start = [], 0
    for i, ch in enumerate(text):
        if ch in ".!?":
            spans.append((start, i + 1))
            start = i + 2
    return {"story_id": doc.story_id, "lang": doc.lang, "segmenter": segmenter, "is_source": is_source,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "n_sentences": len(spans),
            "sentence_fields": ["start", "end", "page_start", "page_end"],
            "sentences": [[a, b, doc.page_of(a), doc.page_of(b - 1)] for a, b in spans]}


def _run(docs, segs, encoder, strict=True, rules=None):
    tally, timers = {}, {}
    rules = rules or SIM.SegmentRules("sat", "union", False)
    lookup = {r["story_id"]: SIM.segmentation_from_record(r) for r in segs}.get
    out = list(SIM.similarity_records(docs, lookup, encoder, value_name="adjacent_similarity", label="m@r",
                                      rules=rules, strict=strict, docs_per_group=2, decimals=6, tally=tally,
                                      timers=timers))
    return out, tally


def test_similarity_records():
    docs = [_doc(0), _doc(1, ("Only one sentence here.",)), _doc(2, ("A b. C d. E f.", "G h."))]
    enc = FakeEncoder()
    out, tally = _run(docs, [_segments_record(d) for d in docs], enc)
    sents = [docs[0].text[a:b] for a, b, *_ in _segments_record(docs[0])["sentences"]]
    assert sents == ["One cat sat.", "It purred.", "Then it slept!", "The end."]
    expected = SIM.mean_similarity(SIM.adjacent_cosines(enc.encode(sents)))
    assert out[0]["values"]["adjacent_similarity"] == pytest.approx(expected, abs=1e-12)
    assert out[0]["diagnostics"]["pairs"] == 3 and len(out[0]["diagnostics"]["pair_cosines"]) == 3
    assert out[1]["values"]["adjacent_similarity"] is None  # one sentence: undefined by construction
    assert tally["documents"] == 3 and tally["documents_without_pair"] == 1 and tally["sentences"] == 9
    assert len(enc.calls[0]) == 5  # the first group's two documents went to the encoder together


def test_stale_missing_and_refused_segmentations():
    doc = _doc(0)
    stale = _segments_record(doc)
    stale["text_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        _run([doc], [stale], FakeEncoder())
    out, tally = _run([doc], [stale], FakeEncoder(), strict=False)
    assert out[0]["values"]["adjacent_similarity"] is None and "stale" in out[0]["diagnostics"]["error"]
    out, _ = _run([doc], [], FakeEncoder(), strict=False)
    assert out[0]["diagnostics"]["error"] == "no segments record"
    out, _ = _run([doc], [_segments_record(doc, is_source=False)], FakeEncoder(), strict=False)
    assert "segmenter" in out[0]["diagnostics"]["error"]


def _ctx(tmp_path, stage, extra, docs, cfg=None):
    cfg = cfg or config_mod.load(CONFIG_DIR)
    ctx = cli.StageContext(stage=stage, config=cfg, lang="en-us", work=tmp_path, extra=extra)
    records.write_jsonl(ctx.path("documents"), [d.to_json() for d in docs])
    records.write_jsonl(ctx.path("segments"), [_segments_record(d) for d in docs])
    return ctx


@pytest.mark.parametrize("mod,value", [(encode_e5, "adjacent_similarity"), (encode_bgem3, "adjacent_similarity_bgem3")])
def test_encoder_stages_with_an_injected_encoder(tmp_path, mod, value):
    docs = [_doc(i) for i in range(3)]
    cfg = config_mod.load(CONFIG_DIR)
    cfg["stages"][mod.STAGE.name]["stage"]["strict"] = True
    ctx = _ctx(tmp_path, mod.STAGE, {"encoder": FakeEncoder()}, docs, cfg)
    rec = cli.run_stage(mod, ctx)
    out = list(records.read_jsonl(ctx.path(mod.STAGE.outputs[0])))
    assert [r["story_id"] for r in out] == ["S0", "S1", "S2"]
    assert all(r["values"][value] is not None for r in out)
    for key in ("documents", "words", "characters", "tokens", "sentences", "pairs"):
        assert rec["counts"][key] > 0


def test_encoder_configurations_hold_the_registered_values():
    cfg = config_mod.load(CONFIG_DIR)["stages"]
    e5, bge = cfg["encode_e5"], cfg["encode_bgem3"]
    assert e5["encoding"]["prefix"] == "Instruct: Retrieve semantically similar text.\nQuery: "
    assert (e5["encoding"]["pooling"], e5["encoding"]["normalise"], e5["encoding"]["max_length"]) == ("mean", True, 512)
    assert (bge["encoding"]["prefix"], bge["encoding"]["pooling"], bge["encoding"]["normalise"]) == ("", "cls", True)
    assert e5["model"]["key"] == "intfloat/multilingual-e5-large-instruct" and bge["model"]["key"] == "BAAI/bge-m3"
    SIM.EncoderSettings.from_config(e5)
    SIM.EncoderSettings.from_config(bge)


# ------------------------------------------------------------------------------------------------ PyTorch encoder


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    """A tiny random XLM-RoBERTa and a Unigram tokenizer.json with XLM-R's special tokens, pinned in a lock."""
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    tokenizers = pytest.importorskip("tokenizers")
    pytest.importorskip("safetensors")
    pytest.importorskip("numpy")
    root = tmp_path_factory.mktemp("tiny_enc")
    mark = "▁"
    chars = "abcdefghijklmnopqrstuvwxyz.,!?:"
    pieces = [("<s>", 0.0), ("<pad>", 0.0), ("</s>", 0.0), ("<unk>", 0.0)] + [(mark, -6.0)] + [
        (mark + c, -1.0) for c in chars] + [(c, -2.0) for c in chars]
    tok = tokenizers.Tokenizer(tokenizers.models.Unigram(pieces, unk_id=3, byte_fallback=False))
    tok.pre_tokenizer = tokenizers.pre_tokenizers.Metaspace(replacement=mark, prepend_scheme="always")
    tok.add_special_tokens(["<s>", "<pad>", "</s>", "<unk>"])
    tok.post_processor = tokenizers.processors.TemplateProcessing(single="<s> $A </s>",
                                                                   special_tokens=[("<s>", 0), ("</s>", 2)])
    torch.manual_seed(1)
    model = transformers.XLMRobertaModel(transformers.XLMRobertaConfig(
        vocab_size=len(pieces), hidden_size=32, num_hidden_layers=2, num_attention_heads=2, intermediate_size=64,
        max_position_embeddings=600, pad_token_id=1, bos_token_id=0, eos_token_id=2, type_vocab_size=1),
        add_pooling_layer=True)
    folder = root / "xlmr"
    model.save_pretrained(folder, safe_serialization=True)
    tok.save(str(folder / "tokenizer.json"))
    files = {f: records.sha256_file(folder / f) for f in ("config.json", "model.safetensors", "tokenizer.json")}
    lock = {"tiny/xlmr": {"repo": "tiny/xlmr", "revision": "test", "path": str(folder), "files": files}}
    return {"lock": lock, "model": model.eval(), "torch": torch, "tok": tok}


def _settings(stage, **changes):
    cfg = copy.deepcopy(config_mod.load(CONFIG_DIR)["stages"][stage])
    cfg["runtime"].update(device="cpu", attn_implementation="eager", tokens_per_batch=96)
    for k, v in changes.items():
        cfg["encoding" if k in cfg["encoding"] else "runtime"][k] = v
    return SIM.EncoderSettings.from_config(cfg)


TEXTS = ["the cat sat.", "a dog ran far away!", "owls hoot.", "the cat sat."]


def test_mean_pooling_matches_the_model_and_is_normalised(tiny):
    torch = tiny["torch"]
    enc = SIM.load_encoder("tiny/xlmr", _settings("encode_e5"), tiny["lock"])
    vecs = enc.encode(TEXTS)
    assert vecs.shape == (4, 32)
    assert enc.unique_texts == 3 and (vecs[0] == vecs[3]).all()
    ids = tiny["tok"].encode(enc.settings.prefix + TEXTS[1]).ids
    with torch.inference_mode():
        h = tiny["model"](input_ids=torch.tensor([ids])).last_hidden_state[0]
    ref = torch.nn.functional.normalize(h.mean(0), dim=-1).numpy()
    assert vecs[1] == pytest.approx(ref, abs=1e-5)
    assert float((vecs ** 2).sum(1).max()) == pytest.approx(1.0, abs=1e-5)


def test_cls_pooling_matches_the_first_hidden_state(tiny):
    torch = tiny["torch"]
    enc = SIM.load_encoder("tiny/xlmr", _settings("encode_bgem3"), tiny["lock"])
    vecs = enc.encode(TEXTS[:2])
    ids = tiny["tok"].encode(TEXTS[0]).ids
    with torch.inference_mode():
        h = tiny["model"](input_ids=torch.tensor([ids])).last_hidden_state[0, 0]
    assert vecs[0] == pytest.approx(torch.nn.functional.normalize(h, dim=-1).numpy(), abs=1e-5)


def test_vectors_do_not_depend_on_call_companions(tiny):
    enc = SIM.load_encoder("tiny/xlmr", _settings("encode_e5"), tiny["lock"])
    alone = enc.encode(["a dog ran far away!"])[0]
    mixed = enc.encode(["the cat sat.", "a dog ran far away!", "x" * 40])[1]
    assert (alone == mixed).all()  # identical bits, not merely close


def test_truncation_is_counted(tiny):
    # BGE-M3's settings carry no instruction, so only the long sentence passes 16 tokens
    enc = SIM.load_encoder("tiny/xlmr", _settings("encode_bgem3", max_length=16, buckets=[8, 16]), tiny["lock"])
    vecs = enc.encode(["short.", "a very long sentence that goes on and on and on."])
    assert enc.truncated == 1 and vecs.shape == (2, 32)


def test_encoder_stage_loads_a_pinned_tiny_model(tiny, tmp_path):
    cfg = config_mod.load(CONFIG_DIR)
    cfg["models"] = tiny["lock"]
    scfg = cfg["stages"]["encode_e5"]
    scfg["model"]["key"] = "tiny/xlmr"
    scfg["runtime"].update(device="cpu", attn_implementation="eager", tokens_per_batch=96)
    scfg["stage"]["strict"] = True
    docs = [_doc(i) for i in range(2)]
    ctx = _ctx(tmp_path, encode_e5.STAGE, {}, docs, cfg)
    rec = cli.run_stage(encode_e5, ctx)
    assert rec["counts"]["models"]["encode_e5"] == "tiny/xlmr@test" and rec["counts"]["forward_calls"] > 0
    out = list(records.read_jsonl(ctx.path("encode_e5")))
    assert -1.0 <= out[0]["values"]["adjacent_similarity"] <= 1.0
