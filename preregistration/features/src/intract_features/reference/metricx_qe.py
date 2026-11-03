"""MetricX-24-Hybrid-XL in its reference-free mode: a port of the developers' inference code, validated against it.

Sensitivity analyses, ninth family (preregistration.qmd): "Translation quality is estimated for every translated page
against its English source by MetricX-24 in its reference-free mode [@juraskaMetricX24GoogleSubmission2024] [...]. A
text's value is the word-weighted mean over its pages." supplementary.qmd S3: "Every translated page is scored against
its English source by MetricX-24-Hybrid-XL in its reference-free quality-estimation mode".

What the developers' code computes (google-research/metricx at commit fc4978eb, metricx24/predict.py and models.py):

- input, with --qe: "source: " + source + " candidate: " + hypothesis; the reference field does not enter it;
- tokens: AutoTokenizer("google/mt5-xl") under transformers 4.30.2, max_length 1536 with truncation, then
  `_remove_eos` drops the final token;
- model: MT5ForRegression, an mT5 encoder and one decoder step whose input is token 0, then the language-model head;
  the score is `lm_logits[:, 0, 250089]` ("250089 = <extra_id_10>"), clamped to [0, 25] (lower is better). The
  checkpoint's config sets tie_word_embeddings to false, so the output is not rescaled;
- the checkpoint (google/metricx-24-hybrid-xl-v2p6) stores float32 weights under the names of transformers'
  MT5ForConditionalGeneration (shared, encoder.*, decoder.*, lm_head; 560 tensors, 14,970,478,592 bytes), and
  predict.py loads it with torch_dtype="auto", so it runs in fp32.

Decision: the stage runs this port in the core environment, and the official code runs once, in the metricx
environment, to validate it. The trade-offs:

1. Throughput. predict.py batches with the Trainer's default collator, which cannot pad, so it scores one page per
   forward pass. After acceptance that is about 13.2 million page pairs (733,441 English pages, the structure-only
   count in config/stages/aggregate_timing.toml, times 18 translations). The port pads to fixed-shape length buckets
   (below), which keep each page's score independent of its batch.
2. Environments. The official pins (transformers 4.30.2 with tokenizers 0.13.3, sentencepiece 0.1.99) publish
   binary wheels for CPython 3.11 at most (PyPI file lists, checked 3 November 2026), and this package requires
   Python 3.12 or later (pyproject.toml). Running the official code as the stage would need a subprocess bridge from
   the stage into a second interpreter, which is what the one-off validation run does instead.
3. The official models.py cannot import under transformers 5: it reads modeling_mt5.__HEAD_MASK_WARNING_MSG, which
   v5.2.0 no longer defines, and calls MT5Stack(config, embed_tokens), whereas v5.2.0's MT5Stack takes the config
   alone. A port onto the official file is therefore not possible either.
4. The computation is small and fully specified by the two files, so it is ported step for step onto the modules of
   transformers' MT5ForConditionalGeneration (encoder, decoder, lm_head) with eager attention, the only attention
   4.30.2's mT5 has, and checked on load to leave no checkpoint tensor unused and none missing. transformers 5.2.0 and
   5.19.0 force MT5Config.tie_word_embeddings to True, yet both keep a checkpoint's own lm_head on load (checked on a
   tiny untied checkpoint, tests/unit/test_reference.py), so the port reads the flag from the checkpoint's
   config.json, checks that the loaded head is separate exactly when the checkpoint's is, and applies the head itself.

Tokens. The port rebuilds the fast tokeniser that 4.30.2 makes for predict.py, instead of loading transformers 5's,
because the two differ. google/mt5-xl ships no tokenizer.json, so 4.30.2 converts spiece.model with its SpmConverter
and T5Converter (convert_slow_tokenizer.py in v4.30.2): a Unigram model of the pieces without byte fallback, the
normaliser Precompiled(charsmap) then Replace(" {2,}", " "), the pre-tokeniser Metaspace("▁", add_prefix_space=True)
and the template "$A </s>". Nothing strips the text, so a candidate ending in white space, or an empty candidate,
keeps a final "▁" piece (id 259) before "</s>", which `_remove_eos` leaves in the input. transformers 5.2.0 and
5.19.0, and SentencePiece itself, drop that piece. Run under transformers 4.30.2, tokenizers 0.13.3 and protobuf
3.20.3, the official tokeniser gives the same ids as build_tokenizer() on 44,439 public inputs (FLORES-200 dev pairs
in 27 languages, SimpleStories stories past max_length, and white-space, empty and special-token edge cases), under
tokenizers 0.22.2 and 0.23.3; the models test in tests/gpu checks it again wherever the files are staged. Pages are
scored as delivered after the registered normalisation, so the port matches the official code on them as they are.

The port is admitted only after a GPU test (tests/gpu/test_reference_gpu.py) shows that it reproduces the official
code, run once in a Python 3.11 environment with the official pins, on public pairs within the tolerance set in
config/stages/qe_metricx.toml [validation]. Until that test has passed on ARC, its scores are provisional.

Batching. "single" mode scores one pair per forward pass without padding, as predict.py does. "buckets" mode pads
each pair to the smallest bucket edge that holds it and fills each batch to a fixed number of rows for that edge, so
every pair is computed in a tensor of the same shape whatever else is in its batch (DESIGN.md: "Batches have fixed
shapes wherever padding could change a result"). Padding is masked in attention, so the two modes differ only in the
order of floating-point operations; the GPU test measures that difference.

bf16 (P08). The budget guard's first step runs MetricX-24 "with 16-bit (bf16) weights and 32-bit log-probabilities"
(preregistration.qmd, Timeline). The encoder and decoder then run in bf16, while the language-model head keeps its
float32 weights and is applied to the decoder output cast to float32, so the logit that becomes the score is
computed in 32 bits.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from intract_features.reference import TorchRuntime

# mt5-xl's special_tokens_map.json, in the order 4.30.2's fast tokeniser lists them as added tokens.
SPECIAL_TOKENS = ("<pad>", "</s>", "<unk>")
EOS_TOKEN, PAD_TOKEN, UNK_TOKEN = "</s>", "<pad>", "<unk>"
# 4.30.2's SpmConverter.converted(): replacement = "▁", add_prefix_space = True.
METASPACE = "▁"
# sentencepiece_model.proto, TrainerSpec.ModelType: UNIGRAM = 1, the only type T5Converter turns into Unigram.
UNIGRAM = 1


@dataclass(frozen=True)
class QESettings:
    """MetricX's input, output and batching settings from config/stages/qe_metricx.toml."""

    source_prefix: str = "source: "
    candidate_prefix: str = " candidate: "
    max_input_length: int = 1536
    drop_final_token: bool = True
    logit_index: int = 250089
    clip: tuple[float, float] = (0.0, 25.0)
    attn_implementation: str = "eager"
    mode: str = "buckets"
    bucket_edges: tuple[int, ...] = (64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536)
    tokens_per_batch: int = 16384
    chunk_pairs: int = 50000

    MODES = ("single", "buckets")

    @classmethod
    def from_config(cls, stage_cfg: Mapping) -> QESettings:
        """Read [input], [output], [batching] and [runtime]; inconsistent buckets stop the stage."""
        inp, out, bat = stage_cfg["input"], stage_cfg["output"], stage_cfg["batching"]
        s = cls(source_prefix=str(inp["source_prefix"]), candidate_prefix=str(inp["candidate_prefix"]),
                max_input_length=int(inp["max_input_length"]), drop_final_token=bool(inp["drop_final_token"]),
                logit_index=int(out["logit_index"]), clip=(float(out["clip"][0]), float(out["clip"][1])),
                attn_implementation=str(stage_cfg["runtime"].get("attn_implementation", "eager")),
                mode=str(bat["mode"]), bucket_edges=tuple(int(e) for e in bat["bucket_edges"]),
                tokens_per_batch=int(bat["tokens_per_batch"]), chunk_pairs=int(bat["chunk_pairs"]))
        s.check()
        return s

    def check(self) -> None:
        """Refuse settings under which some pair would have no bucket or a batch no row."""
        if self.mode not in self.MODES:
            raise ValueError(f"[batching] mode must be one of {self.MODES}, not {self.mode!r}")
        edges = self.bucket_edges
        if not edges or any(b <= a for a, b in zip(edges, edges[1:], strict=False)) or edges[0] < 1:
            raise ValueError(f"bucket edges must be positive and strictly increasing: {edges}")
        if edges[-1] < self.max_input_length:
            raise ValueError(f"the last bucket edge {edges[-1]} is below max_input_length {self.max_input_length}")
        if self.tokens_per_batch < edges[-1]:
            raise ValueError("tokens_per_batch must hold at least one pair of the longest bucket")
        if self.chunk_pairs < 1:
            raise ValueError("chunk_pairs must be at least 1")
        if not self.clip[0] < self.clip[1]:
            raise ValueError(f"clip must be [low, high] with low < high, not {self.clip}")


def qe_input(src: str, mt: str, settings: QESettings) -> str:
    """The reference-free input string, as metricx24/predict.py builds it with --qe."""
    return settings.source_prefix + src + settings.candidate_prefix + mt


# The candidates on which transformers 5's tokeniser parts from 4.30.2's in the common case (module docstring).
EDGE_KINDS = ("trailing_space", "trailing_newline", "empty")


def edge_kind(hypothesis: str) -> str | None:
    """Which of EDGE_KINDS a candidate is, if any."""
    if hypothesis == "":
        return "empty"
    if hypothesis.endswith("\n"):
        return "trailing_newline"
    if hypothesis.endswith(" "):
        return "trailing_space"
    return None


def count_edge_kinds(hypotheses: Sequence[str]) -> dict[str, int]:
    """How many candidates of each of EDGE_KINDS a validation set holds."""
    counts = dict.fromkeys(EDGE_KINDS, 0)
    for h in hypotheses:
        kind = edge_kind(h)
        if kind is not None:
            counts[kind] += 1
    return counts


def validation_pairs(pairs: Sequence[tuple[str, str]], per_kind: int) -> list[dict]:
    """Rows for the official predict.py (`{"source", "hypothesis"}`): the public pairs, then per_kind pairs of each
    of EDGE_KINDS made from them.

    Machine translations usually come stripped, so a validation on them alone would never meet the inputs where the
    tokenisers differ; FLORES-200 itself has lines ending in a space (224 of the 997 Greek dev lines). The added
    candidates are the first per_kind non-blank candidates with a space or a line break appended, and empty ones.
    """
    rows = [{"source": s, "hypothesis": h} for s, h in pairs]
    usable = [(s, h) for s, h in pairs if h.strip()][:per_kind]
    if len(usable) < per_kind:
        raise ValueError(f"{len(usable)} non-blank candidates cannot make {per_kind} pairs of each edge kind")
    for s, h in usable:
        rows += [{"source": s, "hypothesis": h.rstrip() + " "}, {"source": s, "hypothesis": h.rstrip() + "\n"},
                 {"source": s, "hypothesis": ""}]
    return rows


# --------------------------------------------------------------------------------------------------- tokeniser


@dataclass
class OfficialTokenizer:
    """The fast mT5 tokeniser of predict.py under transformers 4.30.2, rebuilt on the installed tokenizers library.

    Called as predict.py calls its tokeniser (max_length, truncation, no padding); it returns the input ids only.
    Truncation keeps room for "</s>", as the tokenizers library does for a template's special tokens in both 0.13.3
    and the current releases.
    """

    backend: object
    eos_token_id: int
    pad_token_id: int
    unk_token_id: int

    def __call__(self, texts: Sequence[str], max_length: int, truncation: bool, padding: bool) -> dict:
        """Token ids of each text, with "</s>" appended and truncation at max_length when asked."""
        if padding:
            raise ValueError("predict.py tokenises without padding; the port pads in its own batches")
        if truncation:
            # transformers' fast tokenisers pass these values for truncation=True (longest_first, from the right).
            self.backend.enable_truncation(max_length, stride=0, strategy="longest_first", direction="right")
        else:
            self.backend.no_truncation()
        encodings = self.backend.encode_batch([str(t) for t in texts], add_special_tokens=True)
        return {"input_ids": [list(e.ids) for e in encodings]}


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).is_file() else {}


def check_tokenizer_files(folder: Path) -> dict:
    """The special tokens of mt5-xl's tokeniser files, refusing any setting the port does not reproduce.

    T5TokenizerFast adds `extra_ids` sentinel tokens (100 when unset) and any additional special tokens; the pinned
    mt5-xl files set extra_ids to 0 and add none, so the port builds only that case.
    """
    cfg = _read_json(Path(folder) / "tokenizer_config.json")
    special = {**cfg, **_read_json(Path(folder) / "special_tokens_map.json")}
    if cfg.get("extra_ids") != 0 or cfg.get("additional_special_tokens") or special.get("additional_special_tokens"):
        raise ValueError(f"the tokeniser under {folder} sets extra_ids {cfg.get('extra_ids')!r} or additional special "
                         "tokens; the port reproduces only google/mt5-xl's files (extra_ids 0, none added)")
    wanted = {"eos_token": EOS_TOKEN, "unk_token": UNK_TOKEN, "pad_token": PAD_TOKEN}
    got = {k: special.get(k) for k in wanted}
    if got != wanted:
        raise ValueError(f"the tokeniser under {folder} names the special tokens {got}, not {wanted}")
    return got


def build_tokenizer(folder: Path) -> OfficialTokenizer:
    """Rebuild 4.30.2's fast tokeniser for google/mt5-xl from its spiece.model.

    Step for step as SpmConverter and T5Converter in transformers 4.30.2 (convert_slow_tokenizer.py), with the
    tokenizers API of today: `prepend_scheme="always"` is the old `add_prefix_space=True`, and byte_fallback stays
    off, because 4.30.2's converter ignored the model's byte-fallback flag ("byte fallback option which is not
    implemented in the fast tokenizers"). The model file is parsed with SentencePiece's generated protobuf module,
    as the converter parses it with its own copy.
    """
    from sentencepiece import sentencepiece_model_pb2  # lazy: needs protobuf, present in the core environment
    from tokenizers import AddedToken, Regex, Tokenizer, normalizers, pre_tokenizers, processors
    from tokenizers.models import Unigram

    folder = Path(folder)
    check_tokenizer_files(folder)
    proto = sentencepiece_model_pb2.ModelProto()
    proto.ParseFromString((folder / "spiece.model").read_bytes())
    if proto.trainer_spec.model_type != UNIGRAM:
        raise ValueError(f"{folder / 'spiece.model'} is not a Unigram model; T5Converter builds Unigram only")
    vocab = [(p.piece, p.score) for p in proto.pieces]
    backend = Tokenizer(Unigram(vocab, proto.trainer_spec.unk_id, False))
    charsmap = proto.normalizer_spec.precompiled_charsmap
    steps = [normalizers.Precompiled(charsmap)] if charsmap else []
    backend.normalizer = normalizers.Sequence([*steps, normalizers.Replace(Regex(" {2,}"), " ")])
    backend.pre_tokenizer = pre_tokenizers.Metaspace(replacement=METASPACE, prepend_scheme="always", split=True)
    ids = {t: backend.token_to_id(t) for t in SPECIAL_TOKENS}
    if any(v is None for v in ids.values()):
        raise ValueError(f"spiece.model lacks a special token: {ids}")
    backend.post_processor = processors.TemplateProcessing(single=["$A", EOS_TOKEN],
                                                           pair=["$A", EOS_TOKEN, "$B", EOS_TOKEN],
                                                           special_tokens=[(EOS_TOKEN, ids[EOS_TOKEN])])
    # The added tokens of 4.30.2's tokeniser: special, matched in raw text, never normalised or stripped.
    backend.add_special_tokens([AddedToken(t, single_word=False, lstrip=False, rstrip=False, normalized=False,
                                           special=True) for t in SPECIAL_TOKENS])
    return OfficialTokenizer(backend=backend, eos_token_id=ids[EOS_TOKEN], pad_token_id=ids[PAD_TOKEN],
                             unk_token_id=ids[UNK_TOKEN])


def load_tokenizer(folder: Path) -> OfficialTokenizer:
    """The tokeniser the port scores with: 4.30.2's fast mT5 tokeniser, rebuilt (build_tokenizer)."""
    return build_tokenizer(folder)


# ---------------------------------------------------------------------------------------------------- encoding


@dataclass(frozen=True)
class Encoded:
    """One pair's model input: token ids after the final token is dropped, and whether it reached max_length."""

    ids: tuple[int, ...]
    at_limit: bool


def encode(tokenizer, texts: Sequence[str], settings: QESettings) -> list[Encoded]:
    """Tokenise as predict.py does: max_length with truncation, padding off, then drop the final token.

    The final token must be the tokeniser's end-of-sequence mark, which predict.py's `_remove_eos` assumes; any other
    final token means the tokeniser behaves differently from the official one, so it stops the stage. An input whose
    ids reach max_length may have been truncated; `at_limit` records it.
    """
    enc = tokenizer(list(texts), max_length=settings.max_input_length, truncation=True, padding=False)
    eos = getattr(tokenizer, "eos_token_id", None)
    out = []
    for ids in enc["input_ids"]:
        ids = list(ids)
        at_limit = len(ids) >= settings.max_input_length
        if settings.drop_final_token:
            if not ids or ids[-1] != eos:
                raise RuntimeError(f"the tokeniser's final token is {ids[-1:]!r}, not end-of-sequence {eos!r}")
            ids = ids[:-1]
        out.append(Encoded(ids=tuple(ids), at_limit=at_limit))
    return out


@dataclass(frozen=True)
class Batch:
    """One forward pass: its padded width, its fixed number of rows, and the items (indices) it scores."""

    width: int
    rows: int
    items: tuple[int, ...]


def bucket_width(n: int, settings: QESettings) -> int:
    """The padded width of a pair of n tokens: its own length in "single" mode, else the smallest edge holding it."""
    if settings.mode == "single":
        return n
    for edge in settings.bucket_edges:
        if edge >= n:
            return edge
    raise ValueError(f"a pair of {n} tokens exceeds the largest bucket ({settings.bucket_edges[-1]})")


def plan_batches(lengths: Sequence[int], settings: QESettings) -> list[Batch]:
    """Group pairs into fixed-shape batches.

    A pair's batch shape depends only on its own length (its bucket's width and that bucket's row count), never on
    the other pairs of the shard, so the 1 per cent smoke run's rows equal the full run's (DESIGN.md, Determinism).
    Within a bucket, pairs keep their input order.
    """
    if settings.mode == "single":
        return [Batch(width=n, rows=1, items=(i,)) for i, n in enumerate(lengths)]
    groups: dict[int, list[int]] = {}
    for i, n in enumerate(lengths):
        groups.setdefault(bucket_width(n, settings), []).append(i)
    batches = []
    for width in sorted(groups):
        rows = max(1, settings.tokens_per_batch // width)
        items = groups[width]
        batches.extend(Batch(width=width, rows=rows, items=tuple(items[j:j + rows]))
                       for j in range(0, len(items), rows))
    return batches


def batch_tensors(encoded: Sequence[Encoded], batch: Batch, pad_id: int):
    """Padded input ids and attention mask of one batch, as torch tensors on the CPU.

    Rows beyond the batch's items are filler: one attended pad token each, so no row is fully masked. The scores of
    real rows do not depend on them, since every row of a fixed-shape batch is computed independently.
    """
    import torch  # lazy: unit tests of the planning run without it

    ids = torch.full((batch.rows, batch.width), pad_id, dtype=torch.long)
    mask = torch.zeros((batch.rows, batch.width), dtype=torch.long)
    for r, i in enumerate(batch.items):
        seq = encoded[i].ids
        if len(seq) > batch.width:
            raise ValueError(f"item {i} has {len(seq)} tokens, more than its batch width {batch.width}")
        ids[r, :len(seq)] = torch.tensor(seq, dtype=torch.long)
        mask[r, :len(seq)] = 1
    mask[len(batch.items):, 0] = 1
    return ids, mask


def forward_scores(model, input_ids, attention_mask, settings: QESettings, *, rescale: bool = False):
    """MT5ForRegression.forward of metricx24/models.py, step by step on the modules of MT5ForConditionalGeneration.

    The encoder reads the input; the decoder takes one step from token 0 ("Create 1 step of dummy input for the
    decoder") with the encoder's mask over its states; the decoder output is rescaled by d_model ** -0.5 only when
    the checkpoint ties its embeddings (models.py: "if self.config.tie_word_embeddings"), which MetricX-24's does
    not; the head projects onto the vocabulary; and the score is the logit at `logit_index`, clamped as the official
    model clamps it, returned as float32. The decoder output is cast to the head's dtype before the head, which
    changes nothing in fp32 and, under bf16, computes the score's logit in 32 bits (load_model keeps the head in
    float32). The modules are called directly, so the result does not depend on how a transformers release wires
    MT5ForConditionalGeneration.forward.
    """
    import torch

    decoder_input_ids = torch.zeros((input_ids.shape[0], 1), dtype=torch.long, device=input_ids.device)
    hidden = model.encoder(input_ids=input_ids, attention_mask=attention_mask, return_dict=True).last_hidden_state
    out = model.decoder(input_ids=decoder_input_ids, encoder_hidden_states=hidden,
                        encoder_attention_mask=attention_mask, use_cache=False, return_dict=True).last_hidden_state
    out = out.to(model.lm_head.weight.dtype)
    if rescale:
        out = out * (model.config.d_model ** -0.5)
    logits = model.lm_head(out)
    return logits[:, 0, settings.logit_index].clamp(settings.clip[0], settings.clip[1]).float()


@dataclass
class QEResult:
    """One pair's score and how it was computed."""

    score: float
    tokens: int
    width: int
    at_limit: bool


@dataclass
class QEScorer:
    """A tokeniser and a loaded model, scoring (source, translation) pairs."""

    tokenizer: object
    model: object
    settings: QESettings
    device: object = None
    # Whether the checkpoint ties its embeddings, read from its own config.json (False for MetricX-24).
    rescale: bool = False
    record: dict = field(default_factory=dict)
    # The cost the dry run measures: forward passes, token positions computed (padding and filler rows included),
    # the real tokens among them, and filler rows, which only small shards need many of.
    stats: dict = field(default_factory=lambda: {"batches": 0, "positions": 0, "positions_real": 0, "filler_rows": 0})

    def score(self, pairs: Sequence[tuple[str, str]]) -> list[QEResult]:
        """Score pairs in input order, `chunk_pairs` at a time so that a large shard's token ids are never all held.

        Chunking changes which pairs share a batch, never a pair's batch shape, so it changes no score.
        """
        out: list[QEResult] = []
        step = self.settings.chunk_pairs
        for start in range(0, len(pairs), step):
            out.extend(self._score_chunk(pairs[start:start + step]))
        return out

    def _score_chunk(self, pairs: Sequence[tuple[str, str]]) -> list[QEResult]:
        import torch

        texts = [qe_input(src, mt, self.settings) for src, mt in pairs]
        encoded = encode(self.tokenizer, texts, self.settings)
        pad_id = getattr(self.tokenizer, "pad_token_id", None)
        pad_id = 0 if pad_id is None else int(pad_id)
        scores: list[float | None] = [None] * len(encoded)
        widths = [0] * len(encoded)
        for batch in plan_batches([len(e.ids) for e in encoded], self.settings):
            ids, mask = batch_tensors(encoded, batch, pad_id)
            if self.device is not None:
                ids, mask = ids.to(self.device), mask.to(self.device)
            with torch.inference_mode():
                got = forward_scores(self.model, ids, mask, self.settings, rescale=self.rescale).cpu().tolist()
            self.stats["batches"] += 1
            self.stats["positions"] += batch.rows * batch.width
            self.stats["positions_real"] += sum(len(encoded[i].ids) for i in batch.items)
            self.stats["filler_rows"] += batch.rows - len(batch.items)
            for r, i in enumerate(batch.items):
                scores[i], widths[i] = got[r], batch.width
        return [QEResult(score=s, tokens=len(e.ids), width=w, at_limit=e.at_limit)
                for s, e, w in zip(scores, encoded, widths, strict=True)]


def checkpoint_ties_embeddings(folder: Path) -> bool:
    """The tie_word_embeddings flag of a checkpoint's own config.json (MetricX-24-Hybrid-XL: false).

    It is read from the file because transformers 5 forces MT5Config.tie_word_embeddings to True on load
    (configuration_mt5.py in 5.2.0: "Force because official weights have False serialized, but we have to tie
    always"; 5.19.0 does the same), so the loaded config no longer says what the checkpoint holds. A file without
    the key gets the default of MT5Config in transformers 4.30.2, the official pin, which is False
    (configuration_mt5.py in v4.30.2: "tie_word_embeddings=False").
    """
    raw = json.loads((Path(folder) / "config.json").read_text(encoding="utf-8"))
    return bool(raw.get("tie_word_embeddings", False))


def load_model(folder: Path, runtime: TorchRuntime, settings: QESettings):
    """Load the verified checkpoint into MT5ForConditionalGeneration; return the model, its device and whether the
    checkpoint ties its embeddings.

    No checkpoint tensor may be left unused and none missing. The loaded head must be tied to the input embeddings
    exactly when the checkpoint's config.json says so: a checkpoint with its own lm_head keeps it on load in
    transformers 5.2.0 and 5.19.0, despite the forced flag, and this check stops a release that would tie it. The
    weights load in float32, as predict.py's torch_dtype="auto" loads this checkpoint. A bfloat16 runtime (P08) then
    casts the encoder and decoder to bf16 and keeps an untied head in float32, so the score's logit stays 32-bit.
    transformers reads pickled shards with weights_only.
    """
    import torch
    from transformers import MT5ForConditionalGeneration  # lazy: only the GPU environment has it

    tied = checkpoint_ties_embeddings(folder)
    model, info = MT5ForConditionalGeneration.from_pretrained(
        str(folder), dtype=torch.float32, attn_implementation=settings.attn_implementation, output_loading_info=True)
    checked = ("missing_keys", "unexpected_keys", "mismatched_keys")
    problems = {k: list(v) for k, v in info.items() if k in checked and v}
    if problems:
        raise RuntimeError(f"the MetricX checkpoint does not fit MT5ForConditionalGeneration: {problems}")
    head_is_shared = model.lm_head.weight.data_ptr() == model.shared.weight.data_ptr()
    if head_is_shared != tied:
        raise RuntimeError(f"the loaded head is {'tied to' if head_is_shared else 'separate from'} the input "
                           f"embeddings, but the checkpoint's config.json sets tie_word_embeddings to {tied}")
    if runtime.dtype != "float32":
        if tied:
            raise RuntimeError("bf16 keeps the head in float32, which a tied checkpoint cannot do without also "
                               "keeping its input embeddings in float32")
        model = model.to(runtime.torch_dtype())
        model.lm_head.to(torch.float32)
    device = runtime.torch_device()
    model.to(device).eval()
    return model, device, tied


def word_weighted_mean(pages: Sequence[tuple[float | None, float]]) -> float | None:
    """A text's value from (score, words) per page: the word-weighted mean.

    Ninth family: "A text's value is the word-weighted mean over its pages." A page without words carries no weight.
    The value is None when no page has a word, and when a page with words has no finite score, because dropping that
    page would quietly change the text's weights.
    """
    weighted = [(s, w) for s, w in pages if w > 0]
    total = sum(w for _, w in weighted)
    if total <= 0 or any(s is None or not math.isfinite(s) for s, _ in weighted):
        return None
    return sum(s * w for s, w in weighted) / total
