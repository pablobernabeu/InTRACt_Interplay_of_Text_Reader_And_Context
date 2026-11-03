"""Language-model and encoder tests with the real pinned models; they run on ARC and their results go to records/.

Marked ``models`` (needs the pinned weights; runs on a CPU if no GPU is visible) or ``gpu`` (needs an allocated GPU as
well); the default pytest options deselect both. Each test also skips itself when its environment is not set up,
naming what is missing: torch and transformers (environment core), and the entries of models.lock.json for
goldfish-models/eng_latn_1000mb, goldfish-models/eng_latn_100mb, facebook/xglm-4.5B,
intfloat/multilingual-e5-large-instruct and BAAI/bge-m3. A file whose SHA-256 is still null awaits the build job's
conversion, so its test skips; otherwise the files must be present and must match their pins.

Set $INTRACT_TEST_CONFIG to a run's configuration directory (the one the ARC staging writes, with the converted
weights' hashes and folders) instead of the repository's config/, and $INTRACT_TEST_RECORDS to a directory to keep
each test's measurements there as JSON. The texts are invented here; no story text is read.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import os
import time
from pathlib import Path

import pytest

from intract_features import config as config_mod
from intract_features.features import similarity as SIM
from intract_features.features import surprisal as S

CONFIG = Path(os.environ.get("INTRACT_TEST_CONFIG") or Path(__file__).resolve().parents[2] / "config")
STORY = ["Mia found a small blue key under the old oak tree.", "“What does it open?” she asked her dog.",
         "The dog wagged its tail and ran towards the shed.", "Inside, a dusty box waited for them!",
         "Mia turned the key, and the lid creaked open.", "A map lay folded at the bottom of the box.",
         "It showed the garden, the pond and a cross beside the wall.", "They dug there until the sun went down."]
OTHER = ["The train left the station at noon.", "Prices rose again in the spring.",
         "A storm closed the mountain road.", "The choir sang in the old church.",
         "Engineers tested the new bridge.", "The library opened a reading room.",
         "Farmers planted barley in the north.", "The museum lent two paintings abroad."]


def _cfg() -> dict:
    return config_mod.load(CONFIG)


def _keep(name: str, payload: dict) -> None:
    out = os.environ.get("INTRACT_TEST_RECORDS")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / f"{name}.json").write_text(json.dumps(payload, indent=1, sort_keys=True, allow_nan=False),
                                                encoding="utf-8")


def _need(cfg: dict, key: str, gpu: bool) -> None:
    for mod in ("torch", "transformers", "tokenizers", "safetensors"):
        if importlib.util.find_spec(mod) is None:
            pytest.skip(f"{mod} is not installed (environment core)")
    import torch

    if gpu and not torch.cuda.is_available():
        pytest.skip("no GPU is visible")
    models = cfg.get("models") or {}
    entry = models.get(key) or (models.get("models") or {}).get(key)
    if not entry:
        pytest.skip(f"models.lock.json has no entry {key!r}")
    pending = [name for name, pin in (entry.get("files") or {}).items()
               if (pin.get("sha256") if isinstance(pin, dict) else pin) is None]
    if pending:
        pytest.skip(f"{key}: {pending} await the build job's conversion (SHA-256 null); set $INTRACT_TEST_CONFIG")


def _scorers(cfg: dict, stage: str, key: str, modes=("fp32",), device="auto"):
    scfg = copy.deepcopy(cfg["stages"][stage])
    scfg["runtime"]["device"] = device
    S.configure_torch({**scfg["precision"], **scfg["runtime"]})
    return S.load_scorers(key, S.ModelSettings.from_config(scfg), cfg["models"], list(modes))


def _long_text(n_sentences: int = 120) -> str:
    return " ".join(STORY[i % len(STORY)] for i in range(n_sentences))


@pytest.mark.models
def test_goldfish_reproduces_the_developers_reference_value():
    """example_score_text.py: log p("test!" | "This is a") = -14.735662460327148 with [CLS] (eng_latn_1000mb)."""
    cfg = _cfg()
    key = cfg["languages"]["en-us"]["goldfish"]["tier_1gb"]
    _need(cfg, key, gpu=False)
    sc = _scorers(cfg, "surprisal_goldfish", key)["fp32"]
    inp, _ = sc.tokeniser.encode("This is a")
    tgt, _ = sc.tokeniser.encode("test!")
    res = sc.backend.score([[sc.start_id, *inp, *tgt]])[0]
    value = math.fsum(res.target_logp[len(inp):])
    _keep("goldfish_reference", {"value": value, "reference": -14.735662460327148})
    assert value == pytest.approx(-14.735662460327148, abs=1e-4)


@pytest.mark.gpu
def test_goldfish_identity_windows_and_determinism_on_gpu():
    cfg = _cfg()
    key = cfg["languages"]["en-us"]["goldfish"]["tier_1gb"]
    _need(cfg, key, gpu=True)
    sc = _scorers(cfg, "surprisal_goldfish", key, device="cuda")["fp32"]
    long_p = S.prepare_text("L", _long_text())
    short_p = S.prepare_text("S", " ".join(STORY[:3]))
    t0 = time.perf_counter()
    first = sc.score([long_p, short_p])
    seconds = time.perf_counter() - t0
    # A rerun alone, and with the long text's windows moved to other rows of the call: a fixed-shape GEMM on cuBLAS
    # can still depend on a row's position, which keeping the text first in every call would never show.
    again = sc.score([long_p])
    moved = sc.score([short_p, S.prepare_text("S2", " ".join(STORY[3:6])), long_p])[2]
    for other in (again[0], moved):
        assert first[0].tokens.surprisal == other.tokens.surprisal
        assert first[0].words.corrected == other.words.corrected
    res = first[0]
    assert res.n_windows > 2 and res.tokens.min_context_after_first_window() >= 255
    assert abs(res.words.identity_residual) < 1e-6 and min(res.words.corrected) >= -1e-5
    _keep("goldfish_gpu", {"tokens": res.n_tokens + first[1].n_tokens, "windows": res.n_windows + first[1].n_windows,
                           "seconds": seconds, "identity_residual": res.words.identity_residual,
                           "forward_calls": sc.backend.forward_calls})


@pytest.mark.models
def test_goldfish_tiers_share_one_tokeniser():
    """S3: the 100 MB tier is "trained with the same tokeniser on the same stream with a tenth of the data"."""
    cfg = _cfg()
    tiers = cfg["languages"]["en-us"]["goldfish"]
    for key in tiers.values():
        _need(cfg, key, gpu=False)
    from intract_features.segment.sat import resolve_pinned_snapshot

    toks = [S.HFTokeniser(resolve_pinned_snapshot(cfg["models"], key) / "tokenizer.json") for key in tiers.values()]
    assert all(toks[0].id_to_token(i) == toks[1].id_to_token(i) for i in range(51200))


@pytest.mark.gpu
def test_xglm_bf16_agrees_with_fp32_on_invented_texts():
    """A sanity check of the bf16 mode; the registered check (r >= .995) runs on the public benchmark (P08)."""
    cfg = _cfg()
    key = cfg["stages"]["surprisal_xglm"]["model"]["key"]
    _need(cfg, key, gpu=True)
    scorers = _scorers(cfg, "surprisal_xglm", key, modes=("bf16", "fp32"), device="cuda")
    texts = [S.prepare_text(f"T{i}", " ".join(STORY[i:i + 3] + OTHER[i:i + 2])) for i in range(6)]
    t0 = time.perf_counter()
    lo = scorers["bf16"].score(texts)
    t_bf16 = time.perf_counter() - t0
    t0 = time.perf_counter()
    hi = scorers["fp32"].score(texts)
    t_fp32 = time.perf_counter() - t0
    pairs = [(S.summarise(h, p, None)[0]["mean_all_words"], S.summarise(lw, p, None)[0]["mean_all_words"])
             for p, lw, h in zip(texts, lo, hi, strict=True)]
    out = S.precision_agreement(pairs, cfg["stages"]["surprisal_xglm"]["precision"]["agreement_threshold"])
    _keep("xglm_bf16", {**out, "seconds_bf16": t_bf16, "seconds_fp32": t_fp32,
                        "tokens": sum(r.n_tokens for r in hi)})
    assert out["r"] is not None and out["r"] > 0.99
    assert all(abs(h.words.identity_residual) < 1e-6 for h in hi)


@pytest.mark.gpu
@pytest.mark.parametrize("stage", ["encode_e5", "encode_bgem3"])
def test_encoders_are_deterministic_and_separate_adjacent_from_unrelated_pairs(stage):
    cfg = _cfg()
    key = cfg["stages"][stage]["model"]["key"]
    _need(cfg, key, gpu=True)
    scfg = copy.deepcopy(cfg["stages"][stage])
    S.configure_torch({**scfg["precision"], **scfg["runtime"]})
    enc = SIM.load_encoder(key, SIM.EncoderSettings.from_config(scfg), cfg["models"])
    t0 = time.perf_counter()
    a = enc.encode(STORY + OTHER)
    seconds = time.perf_counter() - t0
    b = enc.encode(list(reversed(STORY + OTHER)))[::-1]
    assert (a == b).all()  # identical bits whatever the order and company
    adjacent = SIM.mean_similarity(SIM.adjacent_cosines(a[:len(STORY)]))
    unrelated = SIM.mean_similarity([float(a[i] @ a[len(STORY) + i]) for i in range(len(OTHER))])
    _keep(f"{stage}_gpu", {"adjacent": adjacent, "unrelated": unrelated, "seconds": seconds,
                           "sentences": len(STORY) + len(OTHER), "tokens": enc.tokens})
    assert adjacent > unrelated
