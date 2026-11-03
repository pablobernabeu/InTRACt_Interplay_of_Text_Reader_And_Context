"""Adjacent-sentence similarity from a multilingual sentence encoder: the anchor encoder and the sensitivity encoder.

The registered rules, quoted:

- qmd Materials: "*Discourse* features are mean semantic similarity between adjacent sentences from a multilingual
  sentence encoder, referential overlap, and causal and contrastive connectives per hundred words."
- S3, Table 3, adjacent-sentence similarity row: "multilingual-E5-large-instruct, identified by checkpoint, since no
  DOI is registered, and prompted with its developers' instruction for semantic similarity on both sentences of a
  pair" as the primary resource, and "BGE-M3 [...], retained as the sensitivity encoder", with "the per-language
  correlation between the two estimates [...] reported with the feature-pipeline validation".
- qmd Outcome-blind dimension reduction: "Quantities undefined by construction are listed and omitted, never entered
  as constants." A text with fewer than two sentences has no adjacent pair, so it has no value.

Promoted from presub/translated_union/scripts/seglib2.E5 and tu5_e5.py: the developers' instruction ("Instruct:
Retrieve semantically similar text." then "Query: ", the task text the developers' evaluation code gives semantic
textual similarity), mean pooling over the attention mask, L2 normalisation, a maximum of 512 tokens, fp32, and a
text's value as the mean cosine of its adjacent sentences. From verify-discourse/scripts/enc_compare.py: BGE-M3's
dense vector, the hidden state of its first token, with no instruction, L2-normalised, at most 512 tokens. What
changed: each sentence is padded to the bucket its own length falls in, with a fixed number of rows per call, so that
its embedding never depends on the sentences that share the call (DESIGN.md, Determinism); TF32 is off through
PyTorch's fp32_precision API (features.surprisal.configure_torch); and weights are read only from safetensors files
verified against their pin. Everything outside the model runs in plain Python, so the unit tests need no torch.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import batched
from pathlib import Path

from intract_features import records
from intract_features.features import surprisal
from intract_features.text.words import count_words

# ------------------------------------------------------------------------------------------------ settings


@dataclass(frozen=True)
class EncoderSettings:
    """How one sentence encoder is run (the [encoding], [runtime] and [loading] tables of its stage configuration)."""

    prefix: str
    pooling: str
    normalise: bool
    max_length: int
    padding: str
    buckets: tuple[int, ...]
    tokens_per_batch: int
    device: str
    attn_implementation: str
    allowed_missing: tuple[str, ...]
    allowed_unexpected: tuple[str, ...]

    @classmethod
    def from_config(cls, cfg: Mapping) -> EncoderSettings:
        """Read the settings and refuse an inconsistent geometry."""
        enc, rt, ld = cfg["encoding"], cfg["runtime"], cfg["loading"]
        s = cls(prefix=str(enc["prefix"]), pooling=str(enc["pooling"]), normalise=bool(enc["normalise"]),
                max_length=int(enc["max_length"]), padding=str(enc["padding_token"]),
                buckets=tuple(int(b) for b in rt["buckets"]), tokens_per_batch=int(rt["tokens_per_batch"]),
                device=str(rt["device"]), attn_implementation=str(rt["attn_implementation"]),
                allowed_missing=tuple(ld["allowed_missing"]), allowed_unexpected=tuple(ld["allowed_unexpected"]))
        if s.pooling not in ("mean", "cls"):
            raise ValueError(f"encoding.pooling must be 'mean' or 'cls', not {s.pooling!r}")
        if list(s.buckets) != sorted(set(s.buckets)) or not s.buckets:
            raise ValueError("runtime.buckets must be strictly increasing")
        if s.buckets[-1] < s.max_length:
            raise ValueError("the largest bucket must hold the maximum length")
        return s


@dataclass(frozen=True)
class SegmentRules:
    """Which segmentation a document's sentences must come from ([segments] table)."""

    source_segmenter: str
    translation_segmenter: str
    allow_sat_alone: bool

    @classmethod
    def from_config(cls, cfg: Mapping) -> SegmentRules:
        """Read the rules."""
        seg = cfg["segments"]
        return cls(source_segmenter=str(seg["source_segmenter"]),
                   translation_segmenter=str(seg["translation_segmenter"]),
                   allow_sat_alone=bool(seg["allow_sat_alone"]))

    def refusal(self, segmenter: str | None, is_source: bool) -> str | None:
        """Why a record's segmentation is not the registered one for its language, or None if it is.

        qmd Materials: "In English, a sentence ends where the registered Segment any Text (SaT) model places a
        boundary"; "In each translation, the union segmenter keeps every sentence end the translation marks itself and
        takes the others from its English source". SaT alone is a translation's sentences only in the registered
        sensitivity analysis ("by SaT alone in another").
        """
        if is_source:
            ok = segmenter == self.source_segmenter
        else:
            ok = segmenter == self.translation_segmenter or (self.allow_sat_alone and segmenter == "sat")
        return None if ok else f"segmenter {segmenter!r} is not the registered one for this language"


# ------------------------------------------------------------------------------------------------ batching


def bucket_length(n: int, buckets: Sequence[int]) -> int:
    """The smallest bucket that holds ``n`` tokens."""
    for b in buckets:
        if n <= b:
            return b
    raise ValueError(f"{n} tokens exceed the largest bucket, {buckets[-1]}")


def plan_batches(lengths: Sequence[int], buckets: Sequence[int],
                 tokens_per_batch: int) -> list[tuple[int, int, list[int]]]:
    """Calls of fixed shape: (bucket length, rows per call, sentence indices), in ascending bucket order.

    A sentence's padded length depends only on its own token count, and every call of a bucket has the same number of
    rows, so its embedding is the same whichever sentences share the call.
    """
    by: dict[int, list[int]] = {}
    for i, n in enumerate(lengths):
        by.setdefault(bucket_length(n, buckets), []).append(i)
    plan = []
    for b in sorted(by):
        rows = max(1, tokens_per_batch // b)
        plan.extend((b, rows, list(chunk)) for chunk in batched(by[b], rows))
    return plan


# ------------------------------------------------------------------------------------------------ similarity


def adjacent_cosines(vectors) -> list[float]:
    """Cosine of each pair of adjacent sentence vectors (unit vectors, so their dot product).

    tu5_e5.py took ``vec[a] @ vec[b]`` of the L2-normalised embeddings. Accumulation is in float64: by NumPy for an
    array, row by row, so each value is independent of the other rows, and by math.fsum otherwise.
    """
    try:
        import numpy as np
    except ImportError:  # the unit tests run without numpy
        np = None
    if np is not None and isinstance(vectors, np.ndarray):
        if len(vectors) < 2:
            return []
        v = vectors.astype(np.float64)
        return [float(x) for x in (v[:-1] * v[1:]).sum(axis=1)]
    vs = [list(map(float, v)) for v in vectors]
    return [math.fsum(a * b for a, b in zip(u, w, strict=True)) for u, w in zip(vs, vs[1:], strict=False)]


def mean_similarity(cosines: Sequence[float]) -> float | None:
    """A text's value: the mean cosine of its adjacent sentences, None without a pair (undefined by construction)."""
    return math.fsum(cosines) / len(cosines) if cosines else None


# ------------------------------------------------------------------------------------------------ the encoder


class SentenceEncoder:
    """A sentence encoder under fixed call shapes: prefix, tokenisation with truncation, pooling, L2 normalisation.

    ``encode`` returns one float32 vector per text (a NumPy array of shape (texts, dimension)). Identical texts are
    encoded once. The counters feed the timing record.
    """

    def __init__(self, model, tokeniser, settings: EncoderSettings, pad_id: int, device: str):
        import torch

        self.torch = torch
        self.model = model
        self.tokeniser = tokeniser
        self.settings = settings
        self.pad_id = pad_id
        self.device = device
        self.forward_calls = 0
        self.tokens = 0
        self.padded_positions = 0
        self.truncated = 0
        self.unique_texts = 0

    def token_ids(self, texts: Sequence[str]) -> tuple[list[list[int]], int]:
        """Token ids of the prefixed texts with the model's special tokens, truncated to the maximum length, and the
        number of texts truncated (the tokeniser reserves room for the special tokens, as transformers does)."""
        encs = self.tokeniser.encode_batch([self.settings.prefix + t for t in texts], add_special_tokens=True)
        return [list(e.ids) for e in encs], sum(1 for e in encs if e.overflowing)

    def encode(self, texts: Sequence[str]):
        """One unit vector per text, in order."""
        import numpy as np

        torch = self.torch
        unique = list(dict.fromkeys(texts))
        if not unique:
            return np.zeros((0, 0), dtype=np.float32)
        ids, truncated = self.token_ids(unique)
        self.unique_texts += len(unique)
        self.truncated += truncated
        out = [None] * len(unique)
        for width, rows, idx in plan_batches([len(x) for x in ids], self.settings.buckets,
                                             self.settings.tokens_per_batch):
            fill = list(idx) + [idx[0]] * (rows - len(idx))  # copies of the first sentence keep the shape fixed
            x = torch.full((rows, width), self.pad_id, dtype=torch.long)
            m = torch.zeros((rows, width), dtype=torch.long)
            for j, i in enumerate(fill):
                x[j, :len(ids[i])] = torch.tensor(ids[i], dtype=torch.long)
                m[j, :len(ids[i])] = 1
            x, m = x.to(self.device), m.to(self.device)
            with torch.inference_mode():
                h = self.model(input_ids=x, attention_mask=m).last_hidden_state
                if self.settings.pooling == "mean":
                    w = m.unsqueeze(-1).to(h.dtype)
                    v = (h * w).sum(1) / w.sum(1)
                else:
                    v = h[:, 0]
                if self.settings.normalise:
                    v = torch.nn.functional.normalize(v, p=2, dim=-1)
                v = v.float().cpu().numpy()
            self.forward_calls += 1
            self.padded_positions += rows * width
            self.tokens += sum(len(ids[i]) for i in idx)
            for j, i in enumerate(idx):
                out[i] = v[j]
        table = {t: out[k] for k, t in enumerate(unique)}
        return np.stack([table[t] for t in texts]).astype(np.float32)


def load_encoder(key: str, settings: EncoderSettings, models_lock: Mapping) -> SentenceEncoder:
    """Verify a pinned encoder folder and load the model in fp32 from its safetensors weights only.

    The model is built without its pooling layer, which neither pooling rule reads.
    """
    import torch
    from tokenizers import Tokenizer
    from transformers import AutoModel

    from intract_features.segment.sat import resolve_pinned_snapshot

    folder = Path(resolve_pinned_snapshot(models_lock, key))
    tokeniser = Tokenizer.from_file(str(folder / "tokenizer.json"))
    tokeniser.enable_truncation(max_length=settings.max_length)
    tokeniser.no_padding()
    pad_id = tokeniser.token_to_id(settings.padding)
    if pad_id is None:
        raise ValueError(f"{key}: the tokeniser has no {settings.padding!r} piece")
    device = surprisal.resolve_device(settings.device)
    model, info = AutoModel.from_pretrained(str(folder), dtype=torch.float32,
                                            attn_implementation=settings.attn_implementation, use_safetensors=True,
                                            local_files_only=True, output_loading_info=True, add_pooling_layer=False)
    surprisal.check_loading(info, settings.allowed_missing, settings.allowed_unexpected)
    model.to(device)
    model.eval()  # dropout off
    return SentenceEncoder(model, tokeniser, settings, pad_id, device)


# ------------------------------------------------------------------------------------------------ documents


@dataclass(frozen=True)
class Segmentation:
    """What the similarity stages read from a segments record."""

    text_sha256: str | None
    spans: tuple[tuple[int, int], ...]
    segmenter: str | None
    is_source: bool


def segmentation_from_record(rec: Mapping) -> Segmentation:
    """The sentence spans and provenance of one segments record (segment.sentences_from_record checks the fields)."""
    from intract_features.segment import sentences_from_record

    return Segmentation(text_sha256=rec.get("text_sha256"),
                        spans=tuple((s.start, s.end) for s in sentences_from_record(rec)),
                        segmenter=rec.get("segmenter"), is_source=bool(rec.get("is_source")))


def similarity_records(documents: Iterable[records.Document], segmentation: Callable[[str], Segmentation | None],
                       encoder, *, value_name: str, label: str, rules: SegmentRules, strict: bool,
                       docs_per_group: int, decimals: int | None, tally: dict, timers: dict) -> Iterable[dict]:
    """Yield one record per document with its adjacent-sentence similarity under ``encoder``.

    Sentences are the spans of the document's segments record over Document.text. A record cut from another text, a
    missing record or a segmentation that is not the registered one for the language leaves the value undefined, or
    stops the stage when ``strict``.
    """
    def add(key: str, v: int = 1) -> None:
        tally[key] = tally.get(key, 0) + v

    for group in batched(documents, docs_per_group):
        plans, texts = [], []
        for doc in group:
            seg = segmentation(doc.story_id)
            digest = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
            problem = None
            if seg is None:
                problem = "no segments record"
            elif seg.text_sha256 is not None and seg.text_sha256 != digest:
                problem = "segments record cut from another text (stale artefact)"
            else:
                problem = rules.refusal(seg.segmenter, seg.is_source)
            if problem is not None:
                if strict:
                    raise ValueError(f"{doc.story_id}: {problem}")
                plans.append((doc, digest, None, problem))
                continue
            sents = [doc.text[a:b] for a, b in seg.spans]
            plans.append((doc, digest, (len(texts), len(sents), seg.segmenter), None))
            texts.extend(sents)
        t0 = time.perf_counter()
        vectors = encoder.encode(texts) if texts else []
        timers["encode"] = timers.get("encode", 0.0) + time.perf_counter() - t0
        for doc, digest, where, problem in plans:
            add("documents")
            add("words", count_words(doc.text))
            add("characters", len(doc.text))
            diag: dict = {"model": label, "text_sha256": digest}
            value = None
            if problem is not None:
                diag["error"] = problem
                add("documents_refused")
            else:
                start, n, segmenter = where
                cos = adjacent_cosines(vectors[start:start + n]) if n >= 2 else []
                value = mean_similarity(cos)
                diag.update({"segmenter": segmenter, "sentences": n, "pairs": len(cos),
                             "pair_cosines": [round(c, decimals) if decimals is not None else c for c in cos]})
                add("sentences", n)
                add("pairs", len(cos))
                if value is None:
                    add("documents_without_pair")
            yield {"story_id": doc.story_id, "lang": doc.lang, "values": {value_name: records.finite_or_none(value)},
                   "diagnostics": diag}
