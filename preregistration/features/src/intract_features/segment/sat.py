"""The registered Segment any Text (SaT) call.

Materials, the segmentation paragraph: "Pages are joined with a single space. In English, a sentence
ends where the registered Segment any Text (SaT) model places a boundary [...], never after a colon."
Supplementary.qmd S3: "English is segmented by Segment any Text, the `sat-12l-sm` model run through
`wtpsplit` 2.2.2 at a threshold of .25, with no boundary after a colon." Feature plan v3 fixes the
remaining arguments: stride 64, block 512, batch 32, ``strip_whitespace=False``,
``pad_last_batch=True`` and ``split_on_input_newlines=True``, in fp32 with TF32 off, and stores the
probabilities at candidate positions for the union search. Every value is read from
``config/stages/sat.toml``.

The model gives one boundary probability per character of the joined text (wtpsplit puts a
token's probability on its last character and 0 elsewhere). Everything after that is pure Python
here, and reproduces the benchmark exactly:

- ``threshold_segments`` and ``split_newlines`` are wtpsplit 2.2.2's ``SaT.split`` with
  ``strip_whitespace=False`` and ``split_on_input_newlines=True`` (``indices_to_sentences`` and the
  newline step in ``wtpsplit/__init__.py``), on character offsets instead of strings;
- ``apply_colon_rule`` is the colon rule of ``union_lib.registered_bounds`` and
  ``seglib2.colon_rule`` in the benchmark.

The benchmark texts held no line break, so its SaT stage never met wtpsplit's newline step. The
delivered texts do hold line breaks inside pages (preregistration/README.md), and wtpsplit cuts at
each of them and drops the newline character, so ``"".join(segments)`` no longer rebuilds the text.
Working on offsets keeps every sentence a span of ``Document.text``.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from intract_features import records
from intract_features.segment import union


def float32(x: float) -> float:
    """The float32 nearest to ``x``, as a Python float."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def f32_json(x: float) -> float:
    """A float32 value written with nine significant digits, which always read back to the same float32."""
    return float(f"{float32(x):.9g}")


@dataclass(frozen=True)
class SatSettings:
    """Arguments of the registered call and of the post-rules (config/stages/sat.toml, [call] and after)."""

    threshold: float
    stride: int
    block_size: int
    batch_size: int
    pad_last_batch: bool
    strip_whitespace: bool
    split_on_input_newlines: bool
    colons: frozenset[str]
    candidate_floor: float
    store_candidates: bool

    @classmethod
    def from_config(cls, stage_cfg: dict) -> SatSettings:
        """Build the settings from the sat stage's configuration table."""
        call = stage_cfg["call"]
        s = cls(threshold=float(call["threshold"]), stride=int(call["stride"]), block_size=int(call["block_size"]),
                batch_size=int(call["batch_size"]), pad_last_batch=bool(call["pad_last_batch"]),
                strip_whitespace=bool(call["strip_whitespace"]),
                split_on_input_newlines=bool(call["split_on_input_newlines"]),
                colons=frozenset(stage_cfg["colon_rule"]["colons"]),
                candidate_floor=float(stage_cfg["candidates"]["floor"]),
                store_candidates=bool(stage_cfg["candidates"]["store"]))
        if s.strip_whitespace:
            # Spans are trimmed here whatever wtpsplit returns, so stripping would change nothing; refusing
            # it keeps the configuration identical to the registered call.
            raise ValueError("the registered call uses strip_whitespace=False")
        return s


@dataclass(frozen=True)
class RuntimeSettings:
    """How the model runs (config/stages/sat.toml, [runtime]); none of these changes a boundary."""

    device: str
    dtype: str
    allow_tf32: bool
    deterministic_algorithms: bool
    cublas_workspace_config: str
    fixed_block_width: bool
    sentinel: str
    texts_per_call: int
    offline: bool
    count_tokens: bool

    @classmethod
    def from_config(cls, stage_cfg: dict) -> RuntimeSettings:
        """Build the runtime settings from the sat stage's configuration table."""
        r = stage_cfg["runtime"]
        return cls(device=str(r["device"]), dtype=str(r["dtype"]), allow_tf32=bool(r["allow_tf32"]),
                   deterministic_algorithms=bool(r["deterministic_algorithms"]),
                   cublas_workspace_config=str(r["cublas_workspace_config"]),
                   fixed_block_width=bool(r["fixed_block_width"]),
                   sentinel=" ".join([str(r["sentinel_word"])] * int(r["sentinel_words"])),
                   texts_per_call=int(r["texts_per_call"]), offline=bool(r["offline"]),
                   count_tokens=bool(r["count_tokens"]))


# ---------------------------------------------------------------- probabilities to sentences

def threshold_segments(text: str, probs: Sequence[float], threshold: float) -> list[tuple[int, int]]:
    """wtpsplit's ``indices_to_sentences(text, where(probs > threshold), strip_whitespace=False)`` as offsets.

    A segment ends after the character whose probability exceeds the threshold and after the whitespace
    run that follows it. NumPy compares a float32 array with a Python float in float32 (NEP 50, and
    value-based casting before it), so the threshold is rounded to float32 first; .25 is exact anyway.
    """
    probs = union._floats(probs)
    n = len(text)
    if len(probs) != n:
        raise ValueError(f"{len(probs)} probabilities for {n} characters")
    thr = float32(threshold)
    segs, off = [], 0
    for i in [i for i, v in enumerate(probs) if v > thr]:
        j = i + 1
        while j < n and text[j].isspace():
            j += 1
        if j > off:
            segs.append((off, j))
            off = j
    if off < n:
        segs.append((off, n))
    return segs


def split_newlines(text: str, segs: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """wtpsplit 2.2.2's ``split_on_input_newlines=True`` step on offsets.

    Every segment but the last loses one trailing newline, then each segment is cut at every newline,
    and the newline characters themselves belong to no piece. Pieces may be empty or blank, exactly as
    ``sentence.split("\\n")`` makes them.
    """
    out = []
    last = len(segs) - 1
    for k, (a, b) in enumerate(segs):
        if k < last and b > a and text[b - 1] == "\n":
            b -= 1
        start = a
        i = text.find("\n", start, b)
        while i != -1:
            out.append((start, i))
            start = i + 1
            i = text.find("\n", start, b)
        out.append((start, b))
    return out


def _last_nonspace_char(text: str, a: int, b: int) -> str:
    k = b - 1
    while k >= a and text[k].isspace():
        k -= 1
    return text[k] if k >= a else ""


def apply_colon_rule(text: str, segs: Sequence[tuple[int, int]], colons: Iterable[str]) -> list[tuple[int, int]]:
    """Merge a segment into the next while it ends, before trailing whitespace, in a colon.

    Materials: "never after a colon". S3: "A colon that introduces speech is the model's one systematic
    error, and that rule removes it at no cost." A merged segment spans the newline characters that
    ``split_newlines`` left between its pieces, so it stays one span of the text.
    """
    colons = frozenset(colons)
    merged: list[tuple[int, int]] = []
    for a, b in segs:
        if merged and _last_nonspace_char(text, *merged[-1]) in colons:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def registered_segments(text: str, probs: Sequence[float], settings: SatSettings,
                        split_on_input_newlines: bool | None = None) -> list[tuple[int, int]]:
    """Segments of the registered call (threshold, newline step, colon rule), untrimmed and possibly blank."""
    segs = threshold_segments(text, probs, settings.threshold)
    newlines = settings.split_on_input_newlines if split_on_input_newlines is None else split_on_input_newlines
    if newlines:
        segs = split_newlines(text, segs)
    return apply_colon_rule(text, segs, settings.colons)


def trimmed_spans(text: str, segs: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sentence spans: each segment with surrounding whitespace removed, blank segments dropped.

    Dropping blank segments matters only after the newline step: a text ending in a line break gives
    wtpsplit an empty last segment, and the sentence before it must stay the last sentence.
    """
    out = []
    for a, b in segs:
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if b > a:
            out.append((a, b))
    return out


@dataclass(frozen=True)
class SegmentedText:
    """The registered segmentation of one text, with what the segments artefact stores beside it."""

    spans: list[tuple[int, int]]
    boundaries: list[int]
    newline_forced: list[int]
    candidate_pos: list[int]
    candidate_p: list[float]


def segment_text(text: str, probs: Sequence[float], settings: SatSettings) -> SegmentedText:
    """Sentences of the registered call from per-character probabilities, plus p' at candidate positions."""
    probs = union._floats(probs)
    spans = trimmed_spans(text, registered_segments(text, probs, settings))
    bounds = [b - 1 for _, b in spans[:-1]]
    forced: list[int] = []
    if settings.split_on_input_newlines and "\n" in text:
        plain = trimmed_spans(text, registered_segments(text, probs, settings, split_on_input_newlines=False))
        forced = sorted(set(bounds) - {b - 1 for _, b in plain[:-1]})
    pos: list[int] = []
    pvals: list[float] = []
    if settings.store_candidates and text:
        pprime = union.char_boundary_probs(text, probs)
        pos = union.candidates(text, pprime, settings.candidate_floor, settings.colons)
        pvals = [f32_json(pprime[c]) for c in pos]
    return SegmentedText(spans=spans, boundaries=bounds, newline_forced=forced, candidate_pos=pos, candidate_p=pvals)


def boundaries_from_candidates(text: str, pos: Sequence[int], pvals: Sequence[float],
                               settings: SatSettings) -> list[int]:
    """Rebuild the registered boundaries from a stored record (text plus p' at candidates).

    A boundary of the registered call is a non-space, non-colon character before the text's last one
    whose p' exceeds the threshold, or that a newline follows in its whitespace run when the newline
    step is on. Every such character with p' above the threshold is a candidate, because the threshold
    exceeds the candidate floor, so the stored values suffice. Used to audit an artefact.
    """
    if settings.threshold < settings.candidate_floor:
        raise ValueError("the threshold must not lie below the candidate floor")
    thr = float32(settings.threshold)
    out = {c for c, v in zip(pos, pvals, strict=True) if float32(v) > thr}
    last = union.last_nonspace(text)
    if settings.split_on_input_newlines:
        prev = -1  # last non-space character seen so far
        for i, ch in enumerate(text):
            if ch == "\n":
                if 0 <= prev < last:
                    out.add(prev)
            elif not ch.isspace():
                prev = i
    return sorted(c for c in out if text[c] not in settings.colons)


# ---------------------------------------------------------------- the model

def predict(backend, texts: Sequence[str], settings: SatSettings, runtime: RuntimeSettings) -> list[list[float]]:
    """Per-character boundary probabilities of the registered call, one list per text, in input order.

    ``backend`` is a ``wtpsplit.SaT`` or any object with the same ``predict_proba``. Blank texts are not
    sent (wtpsplit returns one value for them) and get zeros. With ``fixed_block_width`` a sentinel text
    of at least 510 subword tokens opens every call: wtpsplit sets the block width to the longest text in
    its batch, so without it a text's padding, and in principle its last float16 digit, would depend on
    its neighbours. The chunk geometry that the registered stride and block fix is the same either way.
    """
    texts = list(texts)
    out: list[list[float]] = [[0.0] * len(t) for t in texts]
    todo = [i for i, t in enumerate(texts) if t.strip()]
    if not todo:
        return out
    call = [texts[i] for i in todo]
    if runtime.fixed_block_width:
        call = [runtime.sentinel, *call]
    got = backend.predict_proba(call, stride=settings.stride, block_size=settings.block_size,
                                batch_size=settings.batch_size, pad_last_batch=settings.pad_last_batch,
                                outer_batch_size=len(call))
    got = [union._floats(p) for p in got]
    if runtime.fixed_block_width:
        got = got[1:]
    if len(got) != len(todo):
        raise RuntimeError(f"the model returned {len(got)} probability arrays for {len(todo)} texts")
    for i, p in zip(todo, got, strict=True):
        if p and isinstance(p[0], list):  # a (characters, labels) array: sat-12l-sm has one label
            p = [row[0] for row in p]
        if len(p) != len(texts[i]):
            raise RuntimeError(f"{len(p)} probabilities for a text of {len(texts[i])} characters")
        out[i] = p
    return out


def count_tokens(backend, texts: Sequence[str]) -> list[int]:
    """Subword tokens per text, without special tokens, as wtpsplit's chunking counts them."""
    texts = [t for t in texts if t.strip()]
    if not texts:
        return []
    enc = backend.tokenizer(texts, add_special_tokens=False, verbose=False)
    return [len(ids) for ids in enc["input_ids"]]


def chunks_for(n_tokens: int, settings: SatSettings) -> int:
    """Forward chunks wtpsplit runs for a text of ``n_tokens`` subwords at full block width (``extract``)."""
    width = min(settings.block_size, 510)  # wtpsplit leaves two positions for the CLS and SEP tokens
    return -(-max(n_tokens - width, 0) // settings.stride) + 1


def hf_snapshot_dir(repo: str, revision: str) -> Path:
    """The Hugging Face cache's snapshot folder for a pinned revision (HF_HUB_CACHE, else HF_HOME/hub)."""
    hub = os.environ.get("HF_HUB_CACHE")
    if not hub:
        home = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
        hub = str(Path(home) / "hub")
    return Path(hub) / f"models--{repo.replace('/', '--')}" / "snapshots" / revision


def _pin_files(entry: dict) -> list[tuple[str, str]]:
    files = entry.get("files")
    if isinstance(files, dict):
        return [(name, v["sha256"] if isinstance(v, dict) else v) for name, v in files.items()]
    if isinstance(files, list):
        return [(f.get("path") or f.get("name"), f["sha256"]) for f in files]
    return []


def resolve_pinned_snapshot(models_lock: dict, key: str) -> Path:
    """Verify a pinned snapshot's files against config/models.lock.json and return its folder.

    DESIGN.md: "Code verifies a pin before it loads the file." The entry for ``key`` sits at the lock's
    top level or under a "models" table (as parse.model_pin reads it), and must name its revision and the
    SHA-256 of every file that is loaded, as ``files`` mapping a file name to its hash (or to a table with
    a "sha256" field) or listing tables with "path" and "sha256". Its folder is ``path`` when given,
    otherwise the Hugging Face cache's snapshot of that revision.
    """
    entry = models_lock.get(key)
    if entry is None and isinstance(models_lock.get("models"), dict):
        entry = models_lock["models"].get(key)
    if not entry:
        raise KeyError(f"config/models.lock.json has no pin for {key!r}")
    repo = entry.get("repo") or entry.get("repository") or entry.get("repo_id") or key
    revision = entry.get("revision") or entry.get("commit")
    if not revision:
        raise ValueError(f"the pin for {key!r} names no revision")
    folder = Path(entry["path"]) if entry.get("path") else hf_snapshot_dir(repo, revision)
    files = _pin_files(entry)
    if not files:
        raise ValueError(f"the pin for {key!r} lists no file hashes to verify")
    for name, sha in files:
        target = folder / name
        if not target.is_file():
            raise FileNotFoundError(f"pinned file {target} is missing")
        got = records.sha256_file(target)
        if got.lower() != str(sha).lower():
            raise ValueError(f"{target}: SHA-256 {got} does not match the pin {sha}")
    return folder


def load_backend(stage_cfg: dict, models_lock: dict):
    """Load the registered model through wtpsplit from verified local snapshots, in fp32 with TF32 off.

    Heavy imports happen here so that the rest of the package runs without torch. The environment
    variables are set before torch starts CUDA, which is when cuBLAS reads its workspace setting.
    """
    runtime = RuntimeSettings.from_config(stage_cfg)
    model = stage_cfg["model"]
    if runtime.offline:
        # Nothing is fetched at run time: every file comes from the verified snapshot.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    if runtime.deterministic_algorithms:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", runtime.cublas_workspace_config)
    have = importlib.metadata.version("wtpsplit")
    if have != model["wtpsplit_version"]:
        raise RuntimeError(f"wtpsplit {have} is installed; the registered call needs {model['wtpsplit_version']}")
    sat_dir = resolve_pinned_snapshot(models_lock, model["sat"])
    tok_dir = resolve_pinned_snapshot(models_lock, model["tokenizer"])

    import torch

    torch.backends.cuda.matmul.allow_tf32 = runtime.allow_tf32
    torch.backends.cudnn.allow_tf32 = runtime.allow_tf32
    if runtime.deterministic_algorithms:
        torch.use_deterministic_algorithms(True, warn_only=True)
    from wtpsplit import SaT

    sat = SaT(str(sat_dir), tokenizer_name_or_path=str(tok_dir))
    if runtime.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = runtime.device
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("the sat stage is configured for CUDA, but no GPU is visible")
    net = sat.model.model  # the transformers module inside wtpsplit's PyTorchWrapper
    net.to(device)
    want = getattr(torch, runtime.dtype)
    if next(net.parameters()).dtype != want:
        net.to(want)
    net.eval()
    if runtime.fixed_block_width:
        width = len(sat.tokenizer(runtime.sentinel, add_special_tokens=False, verbose=False)["input_ids"])
        if width < 510:
            raise ValueError(f"the sentinel has {width} tokens; it needs at least 510 to fix the block width")
    return sat


def text_sha256(text: str) -> str:
    """SHA-256 of a text's UTF-8 bytes, which ties a segments record to its document."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
