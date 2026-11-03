"""Parse tests with the real libraries and pinned models; they run on ARC and their results go to records/.

Marked `models` (Stanza on the CPU, needs the staged models) or `gpu` (UDPipe 2 on a GPU); the default pytest
options deselect both. Each test also skips itself when its environment is not set up, naming what is missing:

- Stanza: $STANZA_RESOURCES_DIR with the frozen resources.json and the registered packages, and the
  "stanza-1.15.0" entry in config/models.lock.json.
- UDPipe: $INTRACT_UDPIPE_SRC, $INTRACT_UDPIPE_MODELS and $HF_HUB_CACHE, an allocated GPU, and the "udpipe-2.17"
  entry.

Set $INTRACT_TEST_RECORDS to a directory to keep each test's measurements there as JSON. The texts are invented
here; no story text is read.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from intract_features import config as config_mod
from intract_features import parse as P
from intract_features import records
from intract_features.parse import stanza_wrap, udpipe_client, udpipe_server

CONFIG = Path(__file__).resolve().parents[2] / "config"
SENTENCES = ["Mia found a small blue key under the old oak tree.", "“What does it open?” she asked her dog.",
             "The dog wagged its tail and ran towards the shed.", "Inside, a dusty box waited for them!"]


def _cfg() -> dict:
    return config_mod.load(CONFIG)


def _max_skip(cfg: dict) -> int:
    return int(cfg["stages"]["parse_stanza"]["offset_max_skip"])


def _keep(name: str, payload: dict) -> None:
    out = os.environ.get("INTRACT_TEST_RECORDS")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / f"{name}.json").write_text(json.dumps(payload, indent=1, sort_keys=True, allow_nan=False),
                                                encoding="utf-8")


def _doc(sentences=SENTENCES, story_id="GPU1") -> tuple[records.Document, list[P.Unit]]:
    doc = records.Document(story_id=story_id, lang="en-us", level="young", kind="generated", title="T",
                           pages=(" ".join(sentences),))
    spans, pos = [], 0
    for s in sentences:
        start = doc.text.index(s, pos)
        spans.append((start, start + len(s)))
        pos = start + len(s)
    return doc, P.document_units(doc, spans)


def _stanza_or_skip(cfg: dict) -> None:
    if importlib.util.find_spec("stanza") is None:
        pytest.skip("stanza is not installed (environment core)")
    if not os.environ.get(cfg["stages"]["parse_stanza"]["model_dir_env"]):
        pytest.skip("$STANZA_RESOURCES_DIR is not set")
    if cfg["stages"]["parse_stanza"]["models_lock_key"] not in cfg["models"].get("models", cfg["models"]):
        pytest.skip("models.lock.json has no Stanza pin yet")


def _peak_rss_mb() -> float | None:
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except ImportError:
        return None


@pytest.mark.models
def test_stanza_english_real_parse_is_verified_and_reproducible():
    cfg = _cfg()
    _stanza_or_skip(cfg)
    parser = stanza_wrap.StanzaParser.from_config(cfg, "en-us")
    doc, units = _doc()
    first, stats = P.parse_document(doc, units, parser.parse, max_skip=_max_skip(cfg))
    again, _ = P.parse_document(doc, units, parser.parse, max_skip=_max_skip(cfg))
    assert first == again
    assert stats["empty_parses"] == 0 and stats["offset_misses"] == 0 and stats["offset_inexact"] == 0
    assert parser.lemma_missing_share() == 0.0 and parser.info["lemma_pretrain_workaround"] is None
    assert parser.info["model_files_sha256_pinned"] and all("sha256" in r for r in parser.info["model_files_verified"])
    assert isinstance(parser.info["effective_depparse"]["batch_size"], int)
    _keep("stanza_en_real", {"info": parser.info, "stats": parser.stats(), "doc": stats})


# Run in a fresh interpreter: DESIGN.md's rerun is a new process, which a second call in one process does not test.
FRESH_PROCESS = r"""
import json, sys
from pathlib import Path
from intract_features import config as config_mod
from intract_features import parse as P
from intract_features import records
from intract_features.parse import stanza_wrap
cfg = config_mod.load(Path(sys.argv[1]))
sentences = json.loads(sys.argv[2])
doc = records.Document(story_id="GPU1", lang="en-us", level="young", kind="generated", title="T",
                       pages=(" ".join(sentences),))
spans, pos = [], 0
for s in sentences:
    start = doc.text.index(s, pos)
    spans.append((start, start + len(s)))
    pos = start + len(s)
parser = stanza_wrap.StanzaParser.from_config(cfg, "en-us")
text, _ = P.parse_document(doc, P.document_units(doc, spans), parser.parse,
                           max_skip=int(cfg["stages"]["parse_stanza"]["offset_max_skip"]))
sys.stdout.write(text)
"""


@pytest.mark.models
def test_stanza_parse_is_identical_in_two_fresh_processes():
    cfg = _cfg()
    _stanza_or_skip(cfg)
    outs = [subprocess.run([sys.executable, "-I", "-X", "utf8", "-c", FRESH_PROCESS, str(CONFIG),
                            json.dumps(SENTENCES)], capture_output=True, text=True, encoding="utf-8", check=True,
                           env=dict(os.environ)).stdout for _ in range(2)]
    assert outs[0] and outs[0] == outs[1]
    _keep("stanza_fresh_process_rerun", {"identical": True, "characters": len(outs[0])})


@pytest.mark.models
def test_stanza_greek_lemmatiser_workaround_real():
    cfg = _cfg()
    _stanza_or_skip(cfg)
    model_dir = Path(os.environ[cfg["stages"]["parse_stanza"]["model_dir_env"]])
    if not (model_dir / "el" / "lemma" / "gdt_nocharlm.pt").exists():
        pytest.skip("the Greek gdt_nocharlm models are not staged")
    cfg["languages"]["el-gr"] = {"stanza_lang": "el", "spaced": True, "stanza_packages": {
        "tokenize": "gdt_nocharlm", "mwt": "gdt", "pos": "gdt_nocharlm", "lemma": "gdt_nocharlm",
        "depparse": "gdt_nocharlm"}}
    # The English entry pins English files by SHA-256 only; the Greek files are checked against resources.json's MD5s.
    entry = P.model_pin(cfg, cfg["stages"]["parse_stanza"]["models_lock_key"])
    greek_pin = {k: v for k, v in entry.items() if k != "files"}
    cfg["models"] = {cfg["stages"]["parse_stanza"]["models_lock_key"]: greek_pin}
    parser = stanza_wrap.StanzaParser.from_config(cfg, "el-gr")
    out = parser.parse(["Η Αθήνα είναι η πρωτεύουσα της Ελλάδας."])
    assert out[0] and parser.lemma_missing_share() == 0.0
    assert parser.info["lemma_pretrain_workaround"]["lemma_pretrain_path"] == "el/pretrain/conll17.pt"
    _keep("stanza_el_workaround", {"info": parser.info, "stats": parser.stats()})


@pytest.mark.models
def test_stanza_loop_sentence_memory_is_bounded_per_text():
    """A machine-translation loop below Stanza's separate-batch threshold pads only its own text's batch (TU-4s)."""
    cfg = _cfg()
    _stanza_or_skip(cfg)
    parser = stanza_wrap.StanzaParser.from_config(cfg, "en-us")
    loop = " ".join(["no"] * 139) + "."  # 140 syntactic words, 141 with ROOT: under 150, so it shares the batch
    sentences = [f"The fox jumped over fence number {i}." for i in range(60)] + [loop]
    doc, units = _doc(sentences, story_id="LOOP")
    pre = parser.preflight([[u.text for u in units]], spaced=True)
    _, stats = P.parse_document(doc, units, parser.parse, max_skip=_max_skip(cfg))
    batch = parser.stats()["max_padded_batch"]
    assert stats["empty_parses"] == 0 and batch["padded_length"] >= 141
    assert pre["padded_length"] >= batch["padded_length"]  # the pre-flight estimate errs high
    _keep("stanza_loop_memory", {"stats": parser.stats(), "preflight": pre, "doc": stats,
                                 "peak_rss_mb": _peak_rss_mb()})


def _udpipe_or_skip(cfg: dict) -> tuple[Path, Path, Path, dict]:
    scfg = cfg["stages"]["parse_udpipe"]
    if importlib.util.find_spec("tensorflow") is None:
        pytest.skip("tensorflow is not installed (environment udpipe)")
    if not udpipe_server.gpu_allocated(os.environ):
        pytest.skip("no GPU is allocated")
    src, models = os.environ.get(scfg["udpipe_src_env"]), os.environ.get(scfg["models_dir_env"])
    hub = os.environ.get(scfg["hf_hub_cache_env"])
    if not src or not models or not hub:
        pytest.skip("$INTRACT_UDPIPE_SRC, $INTRACT_UDPIPE_MODELS or $HF_HUB_CACHE is not set")
    try:
        pin = P.model_pin(cfg, scfg["models_lock_key"])
    except P.PinError:
        pytest.skip("models.lock.json has no UDPipe pin yet")
    return Path(src), Path(models), Path(hub), pin


def _server(cfg: dict, src: Path, models: Path, model: str, log: Path) -> udpipe_server.ServerProcess:
    scfg = cfg["stages"]["parse_udpipe"]
    port = udpipe_server.free_port()
    cmd = udpipe_server.server_command(python=sys.executable, src=src, models_dir=models, model=model, port=port,
                                       threads=int(scfg["threads"]), seed=int(cfg["seeds"]["base"]),
                                       batch_size=int(scfg["server_batch_size"]),
                                       max_request_size=int(scfg["max_request_bytes"]))
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    return udpipe_server.ServerProcess(cmd, f"http://127.0.0.1:{port}", log, env=env,
                                       startup_timeout=float(scfg["startup_timeout_s"]),
                                       poll_interval=float(scfg["poll_interval_s"]),
                                       stop_timeout=float(scfg["stop_timeout_s"]),
                                       probe_timeout=float(scfg["probe_timeout_s"]))


def _client(cfg: dict, url: str, model: str) -> udpipe_client.UDPipeClient:
    scfg = cfg["stages"]["parse_udpipe"]
    return udpipe_client.UDPipeClient(url, model, tokenizer=scfg["tokenizer"], timeout=float(scfg["request_timeout_s"]),
                                      retries=int(scfg["retries"]), retry_sleep=float(scfg["retry_sleep_s"]),
                                      max_request_bytes=int(scfg["max_request_bytes"]))


@pytest.mark.gpu
def test_udpipe_fresh_servers_give_identical_parses(tmp_path):
    """EM-2's determinism check at small scale: two fresh servers, the same text, byte-identical CoNLL-U."""
    cfg = _cfg()
    src, models, hub, pin = _udpipe_or_skip(cfg)
    model = cfg["languages"]["en-us"]["udpipe_model"]
    verified = udpipe_server.verify_server_files(src, models, model, pin, hub)
    doc, units = _doc()
    texts, runs = [], []
    for run in range(2):
        with _server(cfg, src, models, model, tmp_path / f"server{run}.log") as server:
            client = _client(cfg, server.base_url, model)
            text, stats = P.parse_document(doc, units, client.parse, max_skip=_max_skip(cfg))
            texts.append(text)
        runs.append({"versions": server.versions(), "resources": server.resources(), "process": server.usage,
                     "startup_seconds": server.startup_seconds, "stats": stats, "client": client.stats()})
    assert texts[0] == texts[1]
    assert runs[0]["versions"]["gpus"] and runs[0]["versions"]["op_determinism"] is True
    assert runs[0]["resources"] and runs[0]["resources"]["gpu_memory"]
    _keep("udpipe_fresh_server_rerun", {"verified": verified, "runs": runs})


@pytest.mark.gpu
def test_udpipe_real_server_refuses_a_sentence_over_1000_words(tmp_path):
    """The upstream TooLongError text the client relies on, and the per-sentence fallback, on the real server."""
    cfg = _cfg()
    src, models, hub, pin = _udpipe_or_skip(cfg)
    model = cfg["languages"]["en-us"]["udpipe_model"]
    udpipe_server.verify_server_files(src, models, model, pin, hub)
    long_line = " ".join(f"word{i}" for i in range(1050)) + "."
    with _server(cfg, src, models, model, tmp_path / "server.log") as server:
        client = _client(cfg, server.base_url, model)
        with pytest.raises(udpipe_client.SentenceTooLong):
            client.process([long_line])
        out = client.parse([SENTENCES[0], long_line, SENTENCES[1]])
    assert isinstance(out[1], P.Refused) and out[0] and out[2]
    assert client.too_long_fallbacks == 1 and client.refused_too_long == 1
    _keep("udpipe_too_long_refusal", {"client": client.stats()})
