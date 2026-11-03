"""Tests of the registered SaT call against wtpsplit itself.

``models``: wtpsplit 2.2.2's own code with a tiny randomly initialised SaT model built here, and the real
XLM-R tokeniser from INTRACT_XLMR_TOKENIZER_DIR (the snapshot folder of FacebookAI/xlm-roberta-base at
the pinned revision). It runs on a CPU in a few seconds and downloads nothing. It checks that the
offsets reproduce ``SaT.split`` with the colon rule on the same probabilities, that the fixed block width
makes a text's probabilities independent of its neighbours, that the chunk count matches wtpsplit's
forward passes, and that ``load_backend`` verifies pins.

``gpu``: the registered model from config/models.lock.json on a CUDA GPU (ARC). It checks determinism,
batch invariance and, when INTRACT_TU_DIR names the translated-union strand folder, that the GPU
boundaries equal those of the benchmark's cached CPU probabilities (the TU-2 identity check).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
from pathlib import Path

import pytest

from intract_features import config as config_mod
from intract_features.segment import sat as sat_mod

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CFG = config_mod.load(CONFIG_DIR)
SAT_CFG = CFG["stages"]["sat"]
SETTINGS = sat_mod.SatSettings.from_config(SAT_CFG)
RUNTIME = sat_mod.RuntimeSettings.from_config(SAT_CFG)

TEXTS = [
    "Once upon a time there was a small fox. It lived in a wood: deep, dark and old.",
    "A title line\nThe hen said: \"Who will help me?\" Nobody answered.\n\nShe baked the bread herself.",
    "",
    "Short.",
    " ".join(f"Sentence number {i} is here, and it goes on a little." for i in range(70)),  # several chunks
    "Mum called out:\n\"Come home now!\" We ran.   Then we ate.\n",
]


def colon_rule(segs):
    """seglib2.colon_rule, verbatim."""
    out = []
    for s in segs:
        if out and re.search(r"[:：]\s*$", out[-1]):
            out[-1] += s
        else:
            out.append(s)
    return out


def contents(text, spans):
    return [text[a:b].replace("\n", "") for a, b in spans]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    """A tiny random SaT model saved to disk, and the XLM-R tokeniser folder."""
    torch = pytest.importorskip("torch")
    pytest.importorskip("wtpsplit")
    tok_dir = os.environ.get("INTRACT_XLMR_TOKENIZER_DIR")
    if not tok_dir or not Path(tok_dir, "tokenizer.json").is_file():
        pytest.skip("set INTRACT_XLMR_TOKENIZER_DIR to a local FacebookAI/xlm-roberta-base snapshot")
    from wtpsplit.configs import SubwordXLMConfig
    from wtpsplit.models import SubwordXLMForTokenClassification

    torch.manual_seed(20261026)
    conf = SubwordXLMConfig(vocab_size=250002, hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
                            intermediate_size=32, max_position_embeddings=514, type_vocab_size=1, pad_token_id=1,
                            bos_token_id=0, eos_token_id=2, num_labels=1, lookahead=None, lookahead_split_layers=None,
                            layer_norm_eps=1e-5)
    model = SubwordXLMForTokenClassification(conf).eval()
    with torch.no_grad():
        # Centre the probabilities on the threshold and spread them, so that boundaries fall on both sides.
        model.classifier.weight.mul_(10.0)
        model.classifier.bias.fill_(math.log(0.25 / 0.75))
    out = tmp_path_factory.mktemp("tiny_sat")
    model.save_pretrained(out)
    return out, Path(tok_dir)


@pytest.fixture(scope="module")
def tiny_backend(tiny):
    from wtpsplit import SaT

    model_dir, tok_dir = tiny
    return SaT(str(model_dir), tokenizer_name_or_path=str(tok_dir))


@pytest.mark.models
def test_offsets_reproduce_wtpsplit_split_on_the_same_probabilities(tiny_backend):
    probs = sat_mod.predict(tiny_backend, TEXTS, SETTINGS, RUNTIME)
    live = [t for t in TEXTS if t.strip()]
    # The same call as predict makes, so the probabilities are identical and the comparison is exact.
    ref = tiny_backend.split([RUNTIME.sentinel, *live], threshold=SETTINGS.threshold, stride=SETTINGS.stride,
                             block_size=SETTINGS.block_size, batch_size=SETTINGS.batch_size,
                             pad_last_batch=SETTINGS.pad_last_batch, strip_whitespace=False,
                             split_on_input_newlines=True, outer_batch_size=len(live) + 1)
    ref = list(ref)[1:]
    n_bounds = 0
    for text, p, segs in zip(live, [p for t, p in zip(TEXTS, probs, strict=True) if t.strip()], ref, strict=True):
        seg = sat_mod.segment_text(text, p, SETTINGS)
        assert contents(text, seg.spans) == [s.strip() for s in colon_rule(segs) if s.strip()]
        n_bounds += len(seg.boundaries)
    assert n_bounds > 10  # the tiny model must put boundaries somewhere for the test to mean anything
    assert probs[2] == []


@pytest.mark.models
def test_fixed_block_width_makes_probabilities_independent_of_neighbours(tiny_backend):
    together = sat_mod.predict(tiny_backend, TEXTS, SETTINGS, RUNTIME)
    for text, p in zip(TEXTS, together, strict=True):
        assert sat_mod.predict(tiny_backend, [text], SETTINGS, RUNTIME)[0] == p
    # Without the sentinel the chunk geometry is the same, so any difference is floating-point noise.
    plain = sat_mod.RuntimeSettings(**{**RUNTIME.__dict__, "fixed_block_width": False})
    for text, p in zip(TEXTS, together, strict=True):
        q = sat_mod.predict(tiny_backend, [text], SETTINGS, plain)[0]
        assert len(q) == len(p) and max((abs(a - b) for a, b in zip(p, q, strict=True)), default=0.0) < 1e-2


@pytest.mark.models
def test_chunk_count_matches_wtpsplit_forward_passes(tiny_backend):
    class Counting:
        def __init__(self, inner):
            self.inner, self.rows = inner, 0

        def __call__(self, attention_mask, **kw):
            self.rows += int((attention_mask.sum(axis=1) > 0).sum())  # padded rows of the last batch are empty
            return self.inner(attention_mask=attention_mask, **kw)

        def __getattr__(self, name):
            return getattr(self.inner, name)

    inner = tiny_backend.model
    counter = Counting(inner)
    tiny_backend.model = counter
    try:
        sat_mod.predict(tiny_backend, TEXTS, SETTINGS, RUNTIME)
    finally:
        tiny_backend.model = inner
    sentinel = sat_mod.count_tokens(tiny_backend, [RUNTIME.sentinel])[0]
    assert sentinel >= 510
    expected = sat_mod.chunks_for(sentinel, SETTINGS) + sum(
        sat_mod.chunks_for(n, SETTINGS) for n in sat_mod.count_tokens(tiny_backend, TEXTS))
    assert counter.rows == expected
    assert max(sat_mod.count_tokens(tiny_backend, TEXTS)) > 510  # one text really has several chunks


@pytest.mark.models
def test_load_backend_verifies_pins_and_loads_on_cpu(tiny, monkeypatch):
    torch = pytest.importorskip("torch")
    model_dir, tok_dir = tiny
    for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "CUBLAS_WORKSPACE_CONFIG"):
        monkeypatch.setenv(var, os.environ.get(var, "1" if "OFFLINE" in var else ":4096:8"))
    model_files = {n: sha256(model_dir / n) for n in ("config.json", "model.safetensors")}
    tok_files = {n: sha256(tok_dir / n) for n in ("config.json", "sentencepiece.bpe.model", "tokenizer.json",
                                                  "tokenizer_config.json") if (tok_dir / n).is_file()}
    lock = {SAT_CFG["model"]["sat"]: {"revision": "test", "path": str(model_dir), "files": model_files},
            SAT_CFG["model"]["tokenizer"]: {"revision": "test", "path": str(tok_dir), "files": tok_files}}
    scfg = copy.deepcopy(SAT_CFG)
    scfg["runtime"]["device"] = "cpu"
    try:
        backend = sat_mod.load_backend(scfg, lock)
        direct = sat_mod.predict(backend, TEXTS[:2], SETTINGS, RUNTIME)
        assert next(backend.model.model.parameters()).dtype == torch.float32
        assert not backend.model.model.training
        bad = copy.deepcopy(lock)
        bad[SAT_CFG["model"]["sat"]]["files"]["model.safetensors"] = "0" * 64
        with pytest.raises(ValueError, match="does not match"):
            sat_mod.load_backend(scfg, bad)
        if not torch.cuda.is_available():
            with pytest.raises(RuntimeError, match="no GPU"):
                sat_mod.load_backend(SAT_CFG, lock)
    finally:
        torch.use_deterministic_algorithms(False)
    from wtpsplit import SaT

    again = sat_mod.predict(SaT(str(model_dir), tokenizer_name_or_path=str(tok_dir)), TEXTS[:2], SETTINGS, RUNTIME)
    assert direct == again


# ---------------------------------------------------------------- the registered model on a GPU


@pytest.fixture(scope="module")
def gpu_backend():
    torch = pytest.importorskip("torch")
    pytest.importorskip("wtpsplit")
    if not torch.cuda.is_available():
        pytest.skip("needs a CUDA GPU")
    return sat_mod.load_backend(SAT_CFG, CFG["models"])


@pytest.mark.gpu
def test_registered_model_is_deterministic_and_batch_invariant(gpu_backend):
    first = sat_mod.predict(gpu_backend, TEXTS, SETTINGS, RUNTIME)
    assert sat_mod.predict(gpu_backend, TEXTS, SETTINGS, RUNTIME) == first
    for text, p in zip(TEXTS, first, strict=True):
        assert sat_mod.predict(gpu_backend, [text], SETTINGS, RUNTIME)[0] == p


@pytest.mark.gpu
def test_registered_model_smoke_boundaries(gpu_backend):
    text = 'The cat sat on the mat. The dog ran away. Mum said: "Come home now." We went home.'
    (p,) = sat_mod.predict(gpu_backend, [text], SETTINGS, RUNTIME)
    seg = sat_mod.segment_text(text, p, SETTINGS)
    assert text.index("mat.") + 3 in seg.boundaries
    assert text.index(":") not in seg.boundaries  # the colon rule, whatever the model says


def _flores_texts(tu: Path):
    for path in (tu / "flores_texts.json", tu / "results" / "smoke" / "flores_texts.json"):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


@pytest.mark.gpu
def test_gpu_boundaries_equal_the_benchmark_cpu_cache(gpu_backend):
    np = pytest.importorskip("numpy")
    tu = os.environ.get("INTRACT_TU_DIR")
    flores = _flores_texts(Path(tu)) if tu else None
    if flores is None or not Path(tu, "earlier", "sat_probs_ags1.npz").is_file():
        pytest.skip("set INTRACT_TU_DIR to the translated-union strand folder")
    cache = {}
    for name in ("sat_probs_ags1.npz", "sat_probs_ags2.npz"):
        with np.load(Path(tu, "earlier", name)) as z:
            cache.update({k: z[k] for k in z.files})
    texts = [" ".join(flores["lines"]["eng_Latn"][i] for i in g) for g in flores["groups"][:30]]
    texts = [t for t in texts if hashlib.sha1(t.encode("utf-8")).hexdigest() in cache]
    assert texts
    probs = sat_mod.predict(gpu_backend, texts, SETTINGS, RUNTIME)
    worst = 0.0
    for text, p in zip(texts, probs, strict=True):
        old = cache[hashlib.sha1(text.encode("utf-8")).hexdigest()].tolist()
        worst = max(worst, max(abs(a - b) for a, b in zip(p, old, strict=True)))
        new_bounds = sat_mod.segment_text(text, p, SETTINGS).boundaries
        assert new_bounds == sat_mod.segment_text(text, old, SETTINGS).boundaries
    print(f"max |p_gpu - p_cpu_cache| = {worst}")
