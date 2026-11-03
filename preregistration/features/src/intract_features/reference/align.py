"""SimAlign-style word alignment: multilingual BERT layer 8, word vectors as subword means, mutual ArgMax.

Two registered roles use it after acceptance. Materials (preregistration.qmd), names: "A type is also a name if word
alignment projects it from a name in the English source, where the alignment covers at least half of that source's
names." Materials, the English-source rule: "Its coreference chains, resolved in English and projected onto the
translation by word alignment, mask a sensitivity overlap anchor computed on the served text". supplementary.qmd S3:
"The second route projects the English source's names through word alignment with multilingual BERT
[@jalilisabetSimAlignHighQuality2020]". The rules built on the alignment are chosen before submission (P06, P53).

Promoted from the names benchmark, nonnative/names-dialogue-freq/scripts/align.py (identical to
nonnative/verify-names-dialogue-sweep/scripts/align.py), which bench_names_mt.py and bench_names_pud.py ran: "contextual
embeddings from layer 8 of multilingual BERT, word vectors as the mean of their subword vectors, cosine similarity,
and the 'ArgMax' method (a pair is aligned when each word is the other's most similar word). Deterministic on CPU in
fp32." Kept as it was: the encoder and its pin (google-bert/bert-base-multilingual-cased at 3f076fdb, the cased
model), truncation of the encoder to its first eight layers so that the last hidden state is exactly
hidden_states[8], the 512-token limit with words lost to truncation keeping a zero vector, L2-normalised word
vectors, the mutual-argmax rule, compact() and fp32 with deterministic algorithms. Changed: the constants come from
config/stages/coref_corpipe.toml [aligner], the snapshot is verified against its pin before it loads, torch and
numpy are imported lazily, and a fixed-shape mode (the default) pads every sentence to a width that depends on its
own length only, with batches filled to a fixed number of rows, so a sentence's vectors never depend on the other
sentences of its batch (DESIGN.md, Determinism). fixed_shapes = false reproduces the benchmark's batching.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from intract_features.reference import TorchRuntime, model_pin, pinned_folder, verify_pinned_files

# A filler row of a fixed-shape batch; its content never reaches a real row's vectors.
FILLER_WORDS = (".",)


@dataclass(frozen=True)
class AlignerSettings:
    """The aligner's settings, from config/stages/coref_corpipe.toml [aligner]."""

    model: str = "google-bert/bert-base-multilingual-cased"
    model_dir_env: str = "INTRACT_MBERT"
    layer: int = 8
    method: str = "argmax"
    max_length: int = 512
    batch_size: int = 16
    fixed_shapes: bool = True
    pad_multiple: int = 32
    threads: int = 4
    device: str = "cpu"
    compact: bool = False

    @classmethod
    def from_config(cls, table: Mapping) -> AlignerSettings:
        """Read the [aligner] table; a method other than the benchmark's mutual argmax stops the run."""
        s = cls(model=str(table["model"]), model_dir_env=str(table["model_dir_env"]), layer=int(table["layer"]),
                method=str(table["method"]), max_length=int(table["max_length"]),
                batch_size=int(table["batch_size"]), fixed_shapes=bool(table["fixed_shapes"]),
                pad_multiple=int(table["pad_multiple"]), threads=int(table["threads"]), device=str(table["device"]),
                compact=bool(table.get("compact", False)))
        if s.method != "argmax":
            raise ValueError(f"only the benchmark's 'argmax' method is implemented, not {s.method!r}")
        if s.layer < 1 or s.max_length < 2 or s.batch_size < 1 or s.pad_multiple < 1:
            raise ValueError("layer, max_length, batch_size and pad_multiple must be positive")
        return s


def padded_width(n_tokens: int, settings: AlignerSettings) -> int:
    """The fixed-shape width of a sentence of n subword tokens: the next multiple of pad_multiple, capped at
    max_length (a longer sentence is truncated there, as in the benchmark)."""
    return min(settings.max_length, -(-n_tokens // settings.pad_multiple) * settings.pad_multiple)


def plan_embedding_batches(lengths: Sequence[int], settings: AlignerSettings) -> list[tuple[list[int], int | None]]:
    """Batches of sentence indices with their fixed width, or with None (the benchmark's dynamic padding).

    Fixed-shape batches hold sentences of one width, in input order, and are filled to batch_size rows.
    """
    n = len(lengths)
    if not settings.fixed_shapes:
        return [(list(range(k, min(k + settings.batch_size, n))), None) for k in range(0, n, settings.batch_size)]
    groups: dict[int, list[int]] = {}
    for i, length in enumerate(lengths):
        groups.setdefault(padded_width(length, settings), []).append(i)
    out = []
    for width in sorted(groups):
        idx = groups[width]
        out.extend((idx[k:k + settings.batch_size], width) for k in range(0, len(idx), settings.batch_size))
    return out


class Aligner:
    """A truncated multilingual BERT and its tokeniser, embedding pre-tokenised sentences and aligning their words."""

    def __init__(self, tokenizer, model, settings: AlignerSettings, device=None):
        self.tok = tokenizer
        self.model = model
        self.settings = settings
        self.device = device
        self.remap = None

    @classmethod
    def from_pretrained(cls, folder: Path, settings: AlignerSettings) -> Aligner:
        """Load the tokeniser and the encoder in fp32 and keep the encoder's first `layer` layers (align.py)."""
        runtime = TorchRuntime(device=settings.device, threads=settings.threads, deterministic_warn_only=False)
        runtime.apply()
        import torch
        from transformers import AutoModel, AutoTokenizer  # lazy: unit tests run without them

        tok = AutoTokenizer.from_pretrained(str(folder))
        model = AutoModel.from_pretrained(str(folder), dtype=torch.float32).eval()
        # Keep only the first `layer` encoder layers: the last hidden state is then exactly hidden_states[layer].
        model.encoder.layer = model.encoder.layer[:settings.layer]
        model.config.num_hidden_layers = settings.layer
        device = runtime.torch_device()
        return cls(tok, model.to(device), settings, device)

    @classmethod
    def from_pinned(cls, config: dict, settings: AlignerSettings, environ: Mapping[str, str] | None = None
                    ) -> tuple[Aligner, list[dict]]:
        """Verify the encoder's snapshot against config/models.lock.json, then load it; returns the files verified."""
        entry = model_pin(config, settings.model)
        folder = pinned_folder(entry, env_name=settings.model_dir_env, environ=environ)
        verified = verify_pinned_files(folder, entry, what="the multilingual BERT snapshot")
        return cls.from_pretrained(folder, settings), verified

    def compact(self, all_sents: Sequence[Sequence[str]]) -> int:
        """Keep only the embedding rows of subwords that occur in all_sents (align.py: "a memory saving on a shared
        laptop; the arithmetic is unchanged because every used row is copied exactly"); returns the rows kept."""
        import gc

        import torch

        ids = set()
        for k in range(0, len(all_sents), 256):
            batch = [list(s) for s in all_sents[k:k + 256]]
            for x in self.tok(batch, is_split_into_words=True, truncation=True,
                              max_length=self.settings.max_length)["input_ids"]:
                ids.update(x)
        ids.add(self.tok.pad_token_id)
        ids.update(self.tok(list(FILLER_WORDS), is_split_into_words=True)["input_ids"])
        keep = torch.tensor(sorted(ids))
        old = self.model.embeddings.word_embeddings
        new = torch.nn.Embedding(len(keep), old.weight.shape[1], device=old.weight.device)
        new.weight.data.copy_(old.weight.data[keep])
        self.model.embeddings.word_embeddings = new
        self.remap = torch.full((old.weight.shape[0],), -1, dtype=torch.long)
        self.remap[keep] = torch.arange(len(keep))
        del old
        gc.collect()
        return len(keep)

    def _encode(self, batch: list[list[str]], width: int | None):
        if width is None:
            return self.tok(batch, is_split_into_words=True, return_tensors="pt", padding=True, truncation=True,
                            max_length=self.settings.max_length)
        filler = [list(FILLER_WORDS)] * (self.settings.batch_size - len(batch))
        return self.tok(batch + filler, is_split_into_words=True, return_tensors="pt", padding="max_length",
                        truncation=True, max_length=width)

    def embed(self, sents: Sequence[Sequence[str]]) -> list:
        """sents: lists of words. Returns one (n_words x hidden) float32 array per sentence, rows L2-normalised.

        A word's vector is the mean of its subword vectors at the kept layer; a word lost to truncation keeps a zero
        vector and so never aligns (align.py).
        """
        import numpy as np
        import torch

        sents = [list(s) for s in sents]
        if self.settings.fixed_shapes and sents:
            lengths = [len(x) for x in self.tok(sents, is_split_into_words=True, truncation=True,
                                                 max_length=self.settings.max_length)["input_ids"]]
        else:  # the benchmark's dynamic padding needs no lengths
            lengths = [0] * len(sents)
        out: list = [None] * len(sents)
        for idx, width in plan_embedding_batches(lengths, self.settings):
            batch = [sents[i] for i in idx]
            enc = self._encode(batch, width)
            ii = enc["input_ids"] if self.remap is None else self.remap[enc["input_ids"]]
            if int(ii.min()) < 0:
                raise ValueError("a subword lies outside the compacted vocabulary")
            kwargs = {"attention_mask": enc["attention_mask"]}
            if "token_type_ids" in enc:
                kwargs["token_type_ids"] = enc["token_type_ids"]
            if self.device is not None:
                ii = ii.to(self.device)
                kwargs = {k: v.to(self.device) for k, v in kwargs.items()}
            with torch.inference_mode():
                hs = self.model(input_ids=ii, **kwargs).last_hidden_state
            for r, words in enumerate(batch):
                wid = enc.word_ids(r)
                h = hs[r].float().cpu().numpy()
                vec = np.zeros((len(words), h.shape[1]), dtype=np.float32)
                cnt = np.zeros(len(words), dtype=np.float32)
                for t, w in enumerate(wid):
                    if w is not None:
                        vec[w] += h[t]
                        cnt[w] += 1
                cnt[cnt == 0] = 1  # words lost to truncation keep a zero vector and never align
                vec /= cnt[:, None]
                norm = np.linalg.norm(vec, axis=1, keepdims=True)
                norm[norm == 0] = 1
                out[idx[r]] = vec / norm
        return out

    @staticmethod
    def argmax_align(a, b) -> list[tuple[int, int]]:
        """Mutual-argmax alignment between word-vector arrays a (source) and b (target): list of (i, j)."""
        if len(a) == 0 or len(b) == 0:
            return []
        s = a @ b.T
        f = s.argmax(axis=1)
        g = s.argmax(axis=0)
        return [(i, int(f[i])) for i in range(len(a)) if g[f[i]] == i]

    def align(self, sources: Sequence[Sequence[str]], targets: Sequence[Sequence[str]]) -> list[list[tuple[int, int]]]:
        """Align each source sentence with its target sentence; returns (source word, target word) index pairs."""
        if len(sources) != len(targets):
            raise ValueError(f"{len(sources)} source sentences for {len(targets)} targets")
        a, b = self.embed(sources), self.embed(targets)
        return [self.argmax_align(x, y) for x, y in zip(a, b, strict=True)]
