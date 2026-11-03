"""Reference tests with the real libraries and pinned files; they run on ARC and their results go to records/.

Marked `models` (CPU, needs staged files) or `gpu` (a GPU and the pinned weights); the default pytest options deselect
both. Each test skips itself when its environment is not set up, naming what is missing:

- CorPipe, tiny model (models): the corpipe environment, $INTRACT_CORPIPE_SRC (the official repository at the pinned
  commit, checked out with LF line endings so that its SHA-256 is the pinned one), $INTRACT_TEST_UMT5_FILES
  (config.json, special_tokens_map.json, spiece.model, tokenizer.json and tokenizer_config.json of google/umt5-xl)
  and $INTRACT_TEST_CORPIPE_LABELS (a folder with the released model's tags.txt and zdeprels.txt; the model folder
  itself will do). A randomly initialised umT5 encoder is built from the official script's own classes, so the
  official script runs end to end, in fp32 and in bf16, without the 7.5 GB weights.
- CorPipe xl (gpu): the corpipe environment, $INTRACT_CORPIPE_SRC, $INTRACT_CORPIPE_MODEL, the umT5-xl snapshot in
  the Hugging Face cache, and the CorPipe entries in config/models.lock.json. The bf16 check (P08) also needs
  $INTRACT_TEST_COREF_WORK, a work folder holding the English `documents` and `parses_stanza` artefacts of public
  texts (the dry run's stand-in), and reads at most $INTRACT_TEST_COREF_LIMIT documents (default 300).
- MetricX tokeniser (models): $INTRACT_MT5_TOKENIZER, the google/mt5-xl tokeniser files, and the core environment.
- MetricX port (gpu): the core environment, the two MetricX entries in models.lock.json, and the official code's
  scores on public pairs, either ready in $INTRACT_METRICX_OFFICIAL_OUTPUT or computed by the test itself when
  $INTRACT_METRICX_PYTHON (the interpreter of envs/metricx) and $INTRACT_METRICX_PAIRS (public pairs, JSON Lines with
  "src" and "mt", or "source" and "hypothesis") are set. The test then writes metricx_qe.validation_pairs() of them,
  which adds candidates ending in a space or a line break and empty ones, and runs

      python -m metricx24.predict --tokenizer <mt5-xl> --model_name_or_path <metricx-24-hybrid-xl-v2p6> \
          --max_input_length 1536 --batch_size 1 --input_file pairs.jsonl --output_file official.jsonl --qe

  from google-research/metricx at commit fc4978eb ($INTRACT_METRICX_SRC). envs/metricx must hold the official
  requirements.txt (transformers[torch]==4.30.2, sentencepiece==0.1.99, datasets==2.13.1) plus protobuf 3.20.x and
  fsspec 2023.6.0: transformers 4.30.2 needs protobuf to convert mt5-xl's spiece.model, and its generated module
  fails under protobuf 4 and later ("Descriptors cannot be created directly"); datasets 2.13.1 fails under fsspec
  2024.10.0 ("Loading a dataset cached in a LocalFileSystem is not supported"). Both were reproduced under Python
  3.11.5 on 3 November 2026. A ready output file must also hold those candidates, or the test fails.
- Aligner (models): $INTRACT_MBERT and the google-bert/bert-base-multilingual-cased entry in models.lock.json.

Set $INTRACT_TEST_RECORDS to a directory to keep each test's measurements there as JSON. The texts are public or
invented here; no story text is read.
"""

import hashlib
import importlib.util
import json
import os
import re
import runpy
import shutil
import statistics
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from intract_features import cli, records
from intract_features import config as config_mod
from intract_features.parse import ConlluDocument, ConlluSentence, Token, Word
from intract_features.reference import PinError, TorchRuntime, model_pin, pinned_folder, verify_pinned_files
from intract_features.reference import align as AL
from intract_features.reference import corpipe_run as cr
from intract_features.reference import metricx_qe as mq
from intract_features.stages import coref_corpipe as coref_stage
from intract_features.stages import qe_metricx as qe_stage
from intract_features.text.words import count_words

CONFIG = Path(__file__).resolve().parents[2] / "config"
# The CorPipe README's example: two sentences.
README_SENTENCES = [["Susan", "came", "home", "and", "Martin", "greeted", "her", "there", "."],
                    ["Then", "Martin", "and", "Paul", "left", "for", "a", "trip", "and", "Susan", "waved", "them",
                     "off", "."]]
UMT5_REVISION = "e02ba7fcf3d6286215043111ee2fc83a9d1f18e2"
UMT5_FILES = ("config.json", "special_tokens_map.json", "spiece.model", "tokenizer.json", "tokenizer_config.json")

# The official tokeniser's ids for "source: The fox found a red kite in the garden. candidate: " + each candidate,
# from transformers 4.30.2, tokenizers 0.13.3, sentencepiece 0.1.99 and protobuf 3.20.3 under Python 3.11.5, on the
# pinned google/mt5-xl files (3 November 2026). The same port matched those releases on 44,439 public inputs.
OFFICIAL_SOURCE = "The fox found a red kite in the garden."
_HEAD = [10219, 267, 486, 259, 63142, 5897, 259, 262, 5656, 57066, 281, 287, 23838, 260, 259, 53939, 267]
_DE = [1683, 259, 140076, 35366, 259, 2448, 259, 133623, 2051, 59415, 859, 28252, 260]
_ZH = [259, 82791, 220520, 1083, 147188, 5811, 236653, 179906, 116778, 223616, 239009, 306]
OFFICIAL_IDS = {
    "plain": ("Der Fuchs fand einen roten Drachen im Garten.", _HEAD + _DE + [1]),
    "trailing_space": ("Der Fuchs fand einen roten Drachen im Garten. ", _HEAD + _DE + [259, 1]),
    "trailing_newline": ("Der Fuchs fand einen roten Drachen im Garten.\n", _HEAD + _DE + [259, 1]),
    "trailing_tab": ("Der Fuchs fand einen roten Drachen im Garten.\t", _HEAD + _DE + [259, 1]),
    "trailing_ideographic_space": ("狐狸在花园里找到了一只红色的风筝。\N{IDEOGRAPHIC SPACE}", _HEAD + _ZH + [259, 1]),
    "trailing_nbsp": ("Le renard a trouvé un cerf-volant rouge\xa0!\xa0",
                      _HEAD + [764, 584, 100652, 259, 262, 13417, 361, 335, 12331, 367, 264, 83569, 48720, 259, 309,
                               259, 1]),
    "empty": ("", _HEAD + [259, 1]),
    "space_only": (" ", _HEAD + [259, 1]),
    "leading_space": (" Der Fuchs fand einen roten Drachen.",
                      _HEAD + [1683, 259, 140076, 35366, 259, 2448, 259, 133623, 2051, 59415, 260, 1]),
    "inner_spaces": ("Der  Fuchs\n\nfand   einen Drachen.",
                     _HEAD + [1683, 259, 140076, 35366, 259, 2448, 2051, 59415, 260, 1]),
    "zh": ("狐狸在花园里找到了一只红色的风筝。", _HEAD + _ZH + [1]),
    "th": ("สุนัขจิ้งจอกพบว่าวสีแดงในสวน",
           _HEAD + [259, 156392, 16344, 159716, 98664, 5405, 121406, 9074, 141232, 2361, 66191, 1]),
    "ar": ("وجد الثعلب طائرة ورقية حمراء في الحديقة.",
           _HEAD + [259, 38421, 16163, 1923, 20466, 259, 61520, 4651, 20339, 35251, 21809, 9626, 575, 124455, 13790,
                    260, 1]),
    "ko": ("여우가 정원에서 빨간 연을 찾았다.",
           _HEAD + [5741, 3216, 929, 6104, 151727, 259, 74274, 7477, 7275, 611, 40757, 22793, 260, 1]),
    "el": ("Η αλεπού βρήκε έναν κόκκινο χαρταετό στον κήπο.",
           _HEAD + [2083, 259, 174382, 60520, 5849, 762, 36680, 259, 2217, 1449, 2760, 94634, 589, 137902, 209822,
                    56508, 259, 4541, 259, 83230, 26458, 260, 1]),
    "fullwidth": ("ＡＢＣ ﬁ x² Ⅻ …", _HEAD + [37116, 1090, 259, 329, 338, 50504, 480, 1]),
    "literal_eos": ("Der Fuchs</s> fand <pad> einen <unk>.",
                    _HEAD + [1683, 259, 140076, 1, 35366, 259, 0, 259, 2448, 259, 2, 259, 260, 1]),
    "extra_id": ("<extra_id_10>", _HEAD + [250089, 1]),
    "rare_char": ("Der 𠀀 Fuchs 🙂.", _HEAD + [1683, 259, 2, 259, 140076, 259, 8691, 260, 1]),
}
# Where SentencePiece itself differs from the official ids: white space at the end, empty candidates, special-token
# strings (matched as special tokens by the fast tokeniser) and characters outside the vocabulary (<unk> in the fast
# tokeniser, bytes in SentencePiece).
DIFFER_FROM_SENTENCEPIECE = {"empty", "literal_eos", "rare_char", "space_only", "trailing_ideographic_space",
                             "trailing_nbsp", "trailing_newline", "trailing_space", "trailing_tab"}


def _cfg() -> dict:
    return config_mod.load(CONFIG)


def _keep(name: str, payload: dict) -> None:
    out = os.environ.get("INTRACT_TEST_RECORDS")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / f"{name}.json").write_text(json.dumps(payload, indent=1, sort_keys=True, allow_nan=False),
                                                encoding="utf-8")


def _need_env(*names: str) -> list[Path]:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        pytest.skip("not set: " + ", ".join(f"${n}" for n in missing))
    return [Path(os.environ[n]) for n in names]


def _need_modules(*names: str) -> None:
    missing = [n for n in names if importlib.util.find_spec(n) is None]
    if missing:
        pytest.skip("not installed: " + ", ".join(missing))


def _parse(sentences: list[list[str]], story_id: str = "R") -> tuple[str, ConlluDocument]:
    """Document.text and a flat parse of sentences of forms, joined by single spaces (offsets from the text)."""
    text, parsed = "", []
    for k, forms in enumerate(sentences):
        if text:
            text += " "
        start, toks = len(text), []
        for form in forms:
            if text and not text.endswith(" "):
                text += " "
            toks.append(Token(form=form, words=[Word(id=len(toks) + 1, form=form, head=0, deprel="dep")],
                              start=len(text), end=len(text) + len(form)))
            text += form
        parsed.append(ConlluSentence(sent_id=f"{story_id}-{k}", k=k, text=text[start:], span=(start, len(text)),
                                     tokens=toks))
    return text, ConlluDocument(story_id=story_id, sentences=parsed)


def _run_corpipe(script: Path, model_dir: Path, work: Path, runtime: TorchRuntime, segment: int, encoder: str,
                 sentences: list[list[str]], guard: bool = True) -> dict:
    text, doc = _parse(sentences)
    counter = cr.SubwordCounter.load(encoder) if guard else None
    limit = segment - cr.SEGMENT_RESERVED if guard else None
    files, report = cr.write_inputs([("R", doc)], work / "in", counter, limit)
    settings = cr.CorpipeSettings(segment=segment, batch_size=0, threads=1)
    record = cr.launch(script, cr.corpipe_args(model_dir, work / "out", [f.path for f in files], settings), runtime)
    out, fields = cr.read_output_file(work / "out" / files[0].output_name)
    result = cr.document_chains("R", doc, files[0].written, out, fields, zero_in_continuity=False,
                                forms=files[0].forms)
    for chain in result["chains"]:
        for m in chain["mentions"]:
            assert m["start"] is not None and 0 <= m["start"] < m["end"] <= len(text)
    call = coref_stage.call_options(settings, json.loads((model_dir / "options.json").read_text(encoding="utf-8")))
    cost = cr.encoder_cost(cr.read_cache(files[0].path), call["segment"], call["right"], call["batch_size"])
    return {"result": result, "runtime": record, "report": report, "text": text, "cost": cost}


@pytest.mark.models
def test_corpipe_official_script_with_a_tiny_model(tmp_path, monkeypatch):
    _need_modules("torch", "transformers", "minnt", "udapi")
    src, umt5, labels = _need_env("INTRACT_CORPIPE_SRC", "INTRACT_TEST_UMT5_FILES", "INTRACT_TEST_CORPIPE_LABELS")
    script = src / "corpipe26_onestage.py"
    hub = tmp_path / "hf" / "hub" / "models--google--umt5-xl"
    (hub / "snapshots" / UMT5_REVISION).mkdir(parents=True)
    (hub / "refs").mkdir()
    (hub / "refs" / "main").write_text(UMT5_REVISION)
    for name in UMT5_FILES:
        shutil.copy(umt5 / name, hub / "snapshots" / UMT5_REVISION / name)
    for key, value in {"HF_HOME": str(tmp_path / "hf"), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                       "CUBLAS_WORKSPACE_CONFIG": ":4096:8"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    import minnt
    import torch
    import transformers

    tiny = tmp_path / "tiny-umt5"  # "umt5" in the name selects UMT5EncoderModel and the umT5 tokeniser in the script
    transformers.UMT5Config(vocab_size=256384, d_model=16, d_kv=4, d_ff=32, num_layers=2, num_decoder_layers=2,
                            num_heads=4, relative_attention_num_buckets=8, relative_attention_max_distance=16,
                            feed_forward_proj="gated-gelu").save_pretrained(tiny)
    lib = runpy.run_path(str(script), run_name="corpipe_lib")  # its classes, without main()
    tok = transformers.AutoTokenizer.from_pretrained("google/umt5-xl", legacy=False)
    tok.add_special_tokens({"additional_special_tokens": [lib["Dataset"].TOKEN_EMPTY]
                            + ([lib["Dataset"].TOKEN_CLS] if tok.cls_token_id is None else [])})
    tags = (labels / "tags.txt").read_text(encoding="utf-8").splitlines()
    zdeprels = (labels / "zdeprels.txt").read_text(encoding="utf-8").splitlines()
    torch.manual_seed(7)
    model = lib["Model"](tok, tags, zdeprels, Namespace(depth=5, zeros_per_parent=2, encoder=str(tiny), load=["x"]))
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    model.save_weights(str(model_dir / "model.pt"))
    for name in ("tags.txt", "zdeprels.txt"):
        shutil.copy(labels / name, model_dir / name)
    (model_dir / "options.json").write_text(json.dumps({"batch_size": 6, "depth": 5, "encoder": str(tiny),
                                                         "right": 50, "segment": 512, "treebanks": []}))
    del model, lib
    original_load = minnt.TrainableModule.load_weights
    long = ["Then", "Martin", "and", "Paul", "left", "for", "a", "very", "long", "trip", "across", "the", "wide",
            "and", "windy", "northern", "hills", "while", "Susan", "waved", "them", "off", "."]
    guarded = [README_SENTENCES[0], ["Then", "\xa0", "Martin", "left", "."], long]
    fp32, bf16 = TorchRuntime(device="cpu", threads=1), TorchRuntime(device="cpu", threads=1, dtype="bfloat16")
    try:
        first = _run_corpipe(script, model_dir, tmp_path / "run1", fp32, 512, str(tiny), README_SENTENCES)
        second = _run_corpipe(script, model_dir, tmp_path / "run2", fp32, 512, str(tiny), README_SENTENCES)
        half = _run_corpipe(script, model_dir, tmp_path / "run3", bf16, 512, str(tiny), README_SENTENCES)
        # A segment of 24 holds the first two sentences and not the third; the guard leaves it out and writes the
        # no-break space, which umT5 encodes to no subword, as the placeholder.
        kept = _run_corpipe(script, model_dir, tmp_path / "run4", fp32, 24, str(tiny), guarded)
        # Unguarded, the official script fails on the long sentence: torch.gather indexes past the segment.
        with pytest.raises((RuntimeError, IndexError)):
            _run_corpipe(script, model_dir, tmp_path / "run5", fp32, 24, str(tiny), [README_SENTENCES[0], long],
                         guard=False)
    finally:
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.use_deterministic_algorithms(False)
    assert minnt.TrainableModule.load_weights is original_load
    assert first["result"] == second["result"]  # a rerun gives the same chains
    assert first["runtime"]["allow_tf32_after_run"] is False and first["runtime"]["minnt_allow_tf32"] == "0"
    assert first["runtime"]["weight_loads"] == 1 and first["runtime"]["setup_seconds"] > 0
    assert first["cost"]["tokens"] > 0 and first["cost"]["truncated_sentences"] == 0
    assert half["runtime"]["bf16_parameters"] > 0 and half["runtime"]["float32_parameters"] > 0
    assert kept["report"].refused == {0: [2]} and kept["report"].replaced == {0: [(1, 2)]}
    assert kept["result"]["pair_continuity"][1] is None and kept["result"]["diagnostics"]["sentences_sent"] == 2
    _keep("corpipe_tiny", {"script_sha256": records.sha256_file(script), "diagnostics": first["result"]["diagnostics"],
                           "runtime": first["runtime"], "cost": first["cost"], "bf16_runtime": half["runtime"],
                           "bf16_same_chains_as_fp32": half["result"]["chains"] == first["result"]["chains"],
                           "guard": {"refused": kept["report"].refused, "replaced": len(kept["report"].replaced)}})


def _need_pins(cfg: dict, keys: list[str]) -> None:
    """Skip unless every key has a models.lock.json entry (at the top level or under "models", as model_pin reads)."""
    for key in keys:
        try:
            model_pin(cfg, key)
        except PinError:
            pytest.skip(f"config/models.lock.json has no entry {key!r}")


def _gpu_or_skip(cfg: dict, keys: list[str]):
    _need_pins(cfg, keys)
    import torch

    if not torch.cuda.is_available():
        pytest.skip("no GPU is visible")
    return torch


@pytest.mark.gpu
def test_corpipe_xl_on_the_readme_example(tmp_path):
    _need_modules("torch", "transformers", "minnt", "udapi")
    cfg = _cfg()
    scfg = cfg["stages"]["coref_corpipe"]
    variant = coref_stage.model_variant(scfg)
    torch = _gpu_or_skip(cfg, [variant["corpipe"], scfg["model"]["code"], variant["encoder"]])
    versions = coref_stage.check_versions(dict(scfg["versions"]))
    pinned = coref_stage.verify_pins(cfg, scfg)
    runtime = TorchRuntime.from_config(scfg["runtime"])
    segment = int(scfg["call"]["segment"])
    with cr.patched_environ(runtime.environment()):
        first = _run_corpipe(pinned.script, pinned.model_dir, tmp_path / "run1", runtime, segment, pinned.encoder,
                             README_SENTENCES)
        second = _run_corpipe(pinned.script, pinned.model_dir, tmp_path / "run2", runtime, segment, pinned.encoder,
                              README_SENTENCES)
    assert first["result"] == second["result"]  # DESIGN.md: a rerun on the same GPU gives identical outputs
    chains = [[first["text"][m["start"]:m["end"]] for m in c["mentions"]] for c in first["result"]["chains"]]
    assert any(len(c) >= 2 for c in chains)
    _keep("corpipe_xl_readme", {"chains": chains, "pair_continuity": first["result"]["pair_continuity"],
                                "diagnostics": first["result"]["diagnostics"], "runtime": first["runtime"],
                                "cost": first["cost"], "versions": versions, "pins": pinned.record,
                                "gpu": torch.cuda.get_device_name(0)})


def _shard_of_work(work: Path, artefact: str) -> tuple[int, int, Path]:
    found = sorted((work / "en-us" / artefact).glob("shard-*-of-*.*"))
    if not found:
        pytest.skip(f"no {artefact} artefact under {work}")
    m = re.match(r"shard-(\d+)-of-(\d+)\.", found[0].name)
    return int(m.group(1)), int(m.group(2)), found[0]


def _text_shares(rows: list[dict]) -> dict[str, float]:
    """The resolver's text mean (coref_corpipe.toml [bf16_check] quantity): the share of continuous pairs."""
    return {r["story_id"]: r["diagnostics"]["pair_continuity_share"] for r in rows
            if r["diagnostics"].get("pair_continuity_share") is not None}


@pytest.mark.gpu
def test_corpipe_bf16_text_means(tmp_path):
    """P08: "The bf16 step is taken only if text means agree with those at full precision at r >= .995"."""
    _need_modules("torch", "transformers", "minnt", "udapi")
    (work,) = _need_env("INTRACT_TEST_COREF_WORK")
    cfg = _cfg()
    scfg = json.loads(json.dumps(cfg["stages"]["coref_corpipe"]))
    variant = coref_stage.model_variant(scfg)
    _gpu_or_skip(cfg, [variant["corpipe"], scfg["model"]["code"], variant["encoder"]])
    shard, nshards, _ = _shard_of_work(work, "documents")
    limit = int(os.environ.get("INTRACT_TEST_COREF_LIMIT", "300"))
    texts = {}
    for dtype in ("float32", "bfloat16"):
        run_work = tmp_path / dtype
        for artefact, ext in (("documents", "jsonl.gz"), (scfg["input"]["parse"], "conllu.gz")):
            target = records.artefact_path(run_work, "en-us", artefact, shard, nshards, ext)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(records.artefact_path(work, "en-us", artefact, shard, nshards, ext), target)
        scfg["runtime"]["dtype"] = dtype
        config = {**cfg, "stages": {**cfg["stages"], "coref_corpipe": scfg}}
        ctx = cli.StageContext(stage=coref_stage.STAGE, config=config, lang="en-us", work=run_work, shard=shard,
                               nshards=nshards, limit=limit)
        rec = cli.run_stage(coref_stage, ctx)
        texts[dtype] = {"shares": _text_shares(list(records.read_jsonl(ctx.path("coref_corpipe")))),
                        "wall_seconds": rec["wall_seconds"], "counts": rec["counts"]}
    both = sorted(set(texts["float32"]["shares"]) & set(texts["bfloat16"]["shares"]))
    a = [texts["float32"]["shares"][s] for s in both]
    b = [texts["bfloat16"]["shares"][s] for s in both]
    r = statistics.correlation(a, b)
    _keep("corpipe_bf16", {"texts": len(both), "pearson": r, "max_abs_difference": max(abs(x - y) for x, y in
                                                                                      zip(a, b, strict=True)),
                           "wall_seconds": {k: v["wall_seconds"] for k, v in texts.items()},
                           "runtime": {k: v["counts"]["runtime"] for k, v in texts.items()}})
    assert len(both) >= 30 and r >= float(scfg["bf16_check"]["min_pearson"])


@pytest.mark.models
def test_metricx_tokenizer_matches_the_official_ids():
    _need_modules("tokenizers", "sentencepiece", "google.protobuf")
    (folder,) = _need_env("INTRACT_MT5_TOKENIZER")
    import sentencepiece

    tok = mq.load_tokenizer(folder)
    sp = sentencepiece.SentencePieceProcessor(model_file=str(folder / "spiece.model"))
    settings = mq.QESettings()
    texts = {name: mq.qe_input(OFFICIAL_SOURCE, mt, settings) for name, (mt, _) in OFFICIAL_IDS.items()}
    got = dict(zip(texts, tok(list(texts.values()), max_length=1536, truncation=True, padding=False)["input_ids"],
                   strict=True))
    mismatches = sorted(name for name, (_, ids) in OFFICIAL_IDS.items() if got[name] != ids)
    differ = {name for name, text in texts.items() if sp.encode(text) + [1] != OFFICIAL_IDS[name][1]}
    long = mq.encode(tok, [" ".join(["word"] * 3000)], settings)[0]
    _keep("metricx_tokenizer", {"cases": len(texts), "mismatches": mismatches, "differ_from_sentencepiece":
                                sorted(differ), "long_input_tokens": len(long.ids)})
    assert not mismatches
    assert differ == DIFFER_FROM_SENTENCEPIECE  # the fixture still exercises every case where the two part
    assert long.at_limit and len(long.ids) == settings.max_input_length - 1


def _read_pairs(path: Path) -> list[tuple[str, str]]:
    out = []
    for row in records.read_jsonl(path):
        src, mt = (row["src"], row["mt"]) if "src" in row else (row["source"], row["hypothesis"])
        out.append((src, mt))
    return out


def _run_official(tmp_path: Path, cfg: dict, min_edge: int) -> Path:
    """Score metricx_qe.validation_pairs() of $INTRACT_METRICX_PAIRS with the official predict.py in envs/metricx."""
    python, pairs_path = _need_env("INTRACT_METRICX_PYTHON", "INTRACT_METRICX_PAIRS")
    scfg = cfg["stages"]["qe_metricx"]
    code = model_pin(cfg, scfg["model"]["official_code"])
    repo = Path(os.environ.get("INTRACT_METRICX_SRC") or "")
    if not repo.is_dir():
        pytest.skip("not set: $INTRACT_METRICX_SRC, the official code at the pinned commit")
    verify_pinned_files(repo, code, what="the official MetricX code")
    model_dir = pinned_folder(model_pin(cfg, scfg["model"]["metricx"]), env_name=scfg["model"]["model_dir_env"])
    tok_dir = pinned_folder(model_pin(cfg, scfg["model"]["tokenizer"]), env_name=scfg["model"]["tokenizer_dir_env"])
    rows = mq.validation_pairs(_read_pairs(pairs_path), min_edge)
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    out = tmp_path / "official" / "official.jsonl"
    launcher = ("import runpy, sys; sys.path.insert(0, sys.argv[1]); sys.argv = ['metricx24.predict'] + sys.argv[2:]; "
                "runpy.run_module('metricx24.predict', run_name='__main__', alter_sys=True)")
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
           "HF_DATASETS_CACHE": str(tmp_path / "datasets")}
    subprocess.run([str(python), "-I", "-c", launcher, str(repo), "--tokenizer", str(tok_dir), "--model_name_or_path",
                    str(model_dir), "--max_input_length", str(scfg["input"]["max_input_length"]), "--batch_size", "1",
                    "--input_file", str(pairs), "--output_file", str(out), "--qe"], check=True, env=env)
    return out


def _official_rows(tmp_path: Path) -> list[dict]:
    cfg = _cfg()
    min_edge = int(cfg["stages"]["qe_metricx"]["validation"]["min_edge_pairs"])
    ready = os.environ.get("INTRACT_METRICX_OFFICIAL_OUTPUT")
    path = Path(ready) if ready else _run_official(tmp_path, cfg, min_edge)
    rows = list(records.read_jsonl(path))
    if not rows or any("prediction" not in r for r in rows):
        pytest.fail(f"{path} holds no official predictions")
    edges = mq.count_edge_kinds([r["hypothesis"] for r in rows])
    if min(edges.values()) < min_edge:
        pytest.fail(f"the official output lacks white-space and empty candidates ({edges}); build its input with "
                    f"metricx_qe.validation_pairs")
    return rows


def _metricx_scorer(mode: str, dtype: str = "float32") -> mq.QEScorer:
    _need_modules("torch", "transformers", "tokenizers")
    cfg = _cfg()
    scfg = json.loads(json.dumps(cfg["stages"]["qe_metricx"]))
    _gpu_or_skip(cfg, [scfg["model"]["metricx"], scfg["model"]["tokenizer"]])
    scfg["batching"]["mode"] = mode
    scfg["runtime"]["dtype"] = dtype
    return qe_stage.build_scorer(cfg, scfg, mq.QESettings.from_config(scfg))


@pytest.mark.gpu
def test_metricx_port_reproduces_the_official_code(tmp_path):
    rows = _official_rows(tmp_path)
    tol = _cfg()["stages"]["qe_metricx"]["validation"]
    want = [float(r["prediction"]) for r in rows]
    kinds = [mq.edge_kind(r["hypothesis"]) or "other" for r in rows]
    report = {"pairs": len(rows), "tolerance": tol, "edge_kinds": mq.count_edge_kinds([r["hypothesis"] for r in rows])}
    for mode in ("single", "buckets"):
        scorer = _metricx_scorer(mode)
        got = [r.score for r in scorer.score([(r["source"], r["hypothesis"]) for r in rows])]
        diffs = [abs(a - b) for a, b in zip(got, want, strict=True)]
        report[mode] = {"max_abs_difference": max(diffs), "mean_abs_difference": statistics.fmean(diffs),
                        "pearson": statistics.correlation(got, want), "stats": dict(scorer.stats),
                        "max_abs_difference_by_kind": {k: max(d for d, kk in zip(diffs, kinds, strict=True) if kk == k)
                                                       for k in set(kinds)},
                        "record": scorer.record}
        del scorer
    _keep("metricx_port_vs_official", report)
    for mode in ("single", "buckets"):
        assert report[mode]["max_abs_difference"] <= tol["max_abs_difference"], mode
        assert report[mode]["pearson"] >= tol["min_pearson"], mode


@pytest.mark.gpu
def test_metricx_buckets_are_independent_of_batch_neighbours(tmp_path):
    rows = _official_rows(tmp_path)[:64]
    scorer = _metricx_scorer("buckets")
    pairs = [(r["source"], r["hypothesis"]) for r in rows]
    together = [r.score for r in scorer.score(pairs)]
    alone = [scorer.score([p])[0].score for p in pairs[:8]]
    _keep("metricx_batch_invariance", {"pairs": len(pairs), "identical": together[:8] == alone})
    assert together[:8] == alone


def _text_means(rows: list[dict], scores: list[float]) -> dict[str, float]:
    """Word-weighted text means as the stage computes them ([output] page_weight = "translation_words"); rows with a
    story_id are pages of that story, others are texts of one page."""
    pages: dict[str, list[tuple[float, float]]] = {}
    for i, (row, score) in enumerate(zip(rows, scores, strict=True)):
        pages.setdefault(str(row.get("story_id", i)), []).append((score, count_words(row["hypothesis"])))
    means = {k: mq.word_weighted_mean(v) for k, v in pages.items()}
    return {k: v for k, v in means.items() if v is not None}


@pytest.mark.gpu
def test_metricx_bf16_agreement(tmp_path):
    """P08: "The bf16 step is taken only if text means agree with those at full precision at r >= .995"."""
    rows = _official_rows(tmp_path)
    pairs = [(r["source"], r["hypothesis"]) for r in rows]
    fp32 = _text_means(rows, [r.score for r in _metricx_scorer("buckets", "float32").score(pairs)])
    bf16 = _text_means(rows, [r.score for r in _metricx_scorer("buckets", "bfloat16").score(pairs)])
    keys = sorted(set(fp32) & set(bf16))
    r = statistics.correlation([fp32[k] for k in keys], [bf16[k] for k in keys])
    _keep("metricx_bf16", {"texts": len(keys), "pearson": r,
                           "max_abs_difference": max(abs(fp32[k] - bf16[k]) for k in keys)})
    assert r >= float(_cfg()["stages"]["qe_metricx"]["bf16_check"]["min_pearson"])


@pytest.mark.models
def test_aligner_on_a_public_sentence_pair():
    _need_modules("torch", "transformers", "numpy")
    cfg = _cfg()
    settings = AL.AlignerSettings.from_config(cfg["stages"]["coref_corpipe"]["aligner"])
    _need_pins(cfg, [settings.model])
    _need_env(settings.model_dir_env)
    import torch

    try:
        aligner, verified = AL.Aligner.from_pinned(cfg, settings)
        src = ["The", "cat", "sat", "on", "the", "mat", "."]
        tgt = ["Die", "Katze", "saß", "auf", "der", "Matte", "."]
        (pairs,) = aligner.align([src], [tgt])
    finally:
        torch.use_deterministic_algorithms(False)
    _keep("aligner_public_pair", {"pairs": pairs, "verified": verified,
                                  "src_sha256": hashlib.sha256(" ".join(src).encode()).hexdigest()})
    assert (1, 1) in pairs and (5, 5) in pairs
