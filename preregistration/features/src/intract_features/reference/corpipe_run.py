"""CorPipe 26 on the English sources: its input, the official script, and chains mapped to Document.text offsets.

supplementary.qmd S3, referential overlap row: "CorPipe 26 [...], with its umT5-xl one-stage model, instead resolves
coreference on every English source as a validation reference." Materials (preregistration.qmd): "Its coreference
chains, resolved in English and projected onto the translation by word alignment, mask a sensitivity overlap anchor
computed on the served text (Sensitivity analyses)." S3: "Each language's κ between projected English chain
continuity and its own overlap is reported beside the English-internal ceiling."

How the official code runs, read from ufal/crac2026-corpipe at commit ec853c3b (corpipe26_onestage.py, MPL-2.0) and
the model card of ufal/corpipe26-onestage-corefud1.4-xl-260702:

- `corpipe26_onestage.py --load <model folder> --exp <out folder> --epochs 0 --test <file> ...` writes the prediction
  for each input to `<out folder>/<input stem>.00.conllu` (the README's `--epoch 0` is argparse's abbreviation of
  `--epochs`). The model is loaded once for all the files of a call.
- Input is CoNLL-U read by udapi. The words the model sees are the forms of the syntactic words
  (`tree.descendants`), a document begins at each `# newdoc` comment, and empty nodes on input are ignored (model
  card: "ignores all empty nodes present on input"). The dependency tree is used only after prediction, by udapi's
  corefud.MoveHead, to choose each mention's head word, so the parse decides no mention span.
- Each input file is one udapi Dataset with its own DataLoader, so batches never mix files. Writing one file per
  document therefore makes a document's batches, and so its output, independent of which documents share its shard
  (DESIGN.md, Determinism: "The 1 per cent smoke run's rows must equal the same rows of the full run").
- Output adds CorefUD's `Entity` attribute to MISC (`# global.Entity = eid-etype-head-other`), written by udapi's
  store_coref_to_misc; read_output() below parses it with udapi's own chunk grammar (udapi 0.5.2, core/coref.py).
- The script calls minnt.startup(), whose default turns TF32 on for matrix products (minnt 1.1.1, startup_impl.py:
  `allow_tf32: bool = True`), unless MINNT_ALLOW_TF32 is "0". The launcher sets it, as DESIGN.md requires fp32 with
  TF32 off, and records the flag after the run.

Two inputs stop the official script, and one bad document would stop its whole shard, since a shard is one call:

- A word the tokeniser encodes to no subword fails `assert len(subword) > 0` (Dataset.__init__). With umT5-xl's
  tokeniser that is a form made only of U+0020, U+00A0, U+3000 or U+2028 (checked on the pinned tokeniser files);
  input_conllu() writes such a form as [input] empty_form_placeholder instead and counts it.
- A sentence of more than segment - 4 subwords is cut to that length at prediction ("Truncating a long sentence
  during prediction"), but its word_indices keep pointing past the cut (Dataset.dataset), so the gather in
  Model.forward indexes beyond the segment and the run fails. input_conllu() leaves such a sentence out and records
  it; its adjacent pairs then have no continuity value.

The run keeps the official file byte for byte: its SHA-256 is verified, then it is executed in this process with
runpy, so the stage's timing record captures the GPU and its peak memory. No module is loaded from a path and
sys.path is untouched (runpy runs a plain file without adding its folder to sys.path).

bf16 (P08). The budget guard's first step runs the coreference resolver "with 16-bit (bf16) weights and 32-bit
log-probabilities" (preregistration.qmd, Timeline). torch.autocast cannot do that with the unchanged script:
Model.predict calls `.numpy(force=True)` on the antecedent scores, which fails on a bfloat16 tensor, and autocast would
also run the tag decoder's accumulator and the antecedent scores in bf16. The launcher therefore wraps minnt's
TrainableModule.load_weights for the duration of the run: once the script has loaded its weights, the encoder
(`Model._encoder`, the umT5 model, about nine tenths of the parameters) is cast to bf16 and a forward hook hands its
last hidden state to the heads in float32. The heads, the constrained tag decoding and the antecedent scores, which
decide every mention and link, then run in float32. The same wrapper timestamps the end of weight loading, which
separates the run's setup from its prediction in the timing record.

Gap G8 (which CoNLL-U and which tokenisation CorPipe reads) is open; the stage passes the Stanza English parse by
default (config/stages/coref_corpipe.toml, [input] parse), so CorPipe takes Stanza's syntactic words within the
registered sentences. Mentions come back as spans of syntactic words and are mapped to Document.text through the
parse artefact's TokenRange offsets; a word inside a multi-word token takes its token's offsets.
"""

from __future__ import annotations

import contextlib
import os
import pickle
import re
import runpy
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from intract_features.parse import ConlluDocument, ConlluSentence
from intract_features.reference import TorchRuntime

# udapi 0.5.2, core/coref.py, load_coref_from_misc: the split of an Entity value into chunks, and the subspan suffix
# of a discontinuous mention ("e2[1/2]").
ENTITY_CHUNK_RE = re.compile(r"(\([^()]+\)?|[^()]+\))")
DISCONTINUOUS_RE = re.compile(r"^([^[]+)\[(\d+)/(\d+)\]")
# udapi's default when a file carries no `# global.Entity` comment.
DEFAULT_ENTITY_FIELDS = ("eid", "etype", "head", "other")
# The per-document input files: d<index>.conllu, written in document order.
INPUT_PREFIX = "d"
OUTPUT_SUFFIX = ".00.conllu"  # "{epoch:02d}" with --epochs 0 (corpipe26_onestage.py, Model.process)
# Characters a CoNLL-U field cannot hold, or that udapi would read as a line break: tab, CR, LF, VT, FF, NEL, and
# the Unicode line and paragraph separators.
CELL_BREAKS_RE = re.compile("[\t\r\n\x0b\x0c\x85\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]")
# corpipe26_onestage.py, Dataset.dataset: "if 'proiel' in self._path: segment_size = min(512, args.segment)". No input
# path may contain it, or the segment would shrink without notice.
SEGMENT_OVERRIDE_MARK = "proiel"
# corpipe26_onestage.py, main(): the tokeniser it builds for an encoder ("using a hack to allow sharing tokenized data
# among models with the same tokenizers"), and the special tokens it adds (Dataset.TOKEN_EMPTY, Dataset.TOKEN_CLS).
SCRIPT_TOKENIZERS = (("t5gemma", "google/t5gemma-l-l-ul2"), ("umt5", "google/umt5-xl"), ("mt5", "google/mt5-xl"))
TOKEN_EMPTY, TOKEN_CLS = "[TOKEN_EMPTY]", "[TOKEN_CLS]"
# Dataset.dataset: a sentence fits when len(subwords) + 4 <= segment ([CLS], two separators and the closing one).
SEGMENT_RESERVED = 4


@dataclass(frozen=True)
class CorpipeSettings:
    """The call's settings from config/stages/coref_corpipe.toml ([input], [call] and [output])."""

    input_parse: str = "parses_stanza"
    segment: int = 2560
    batch_size: int = 0
    threads: int = 4
    zero_mentions_in_continuity: bool = False
    empty_form_placeholder: str = "_"

    PARSES = ("parses_stanza", "parses_udpipe")

    @classmethod
    def from_config(cls, stage_cfg: Mapping) -> CorpipeSettings:
        """Read the stage's tables; an unknown parse artefact stops the stage."""
        s = cls(input_parse=str(stage_cfg["input"]["parse"]), segment=int(stage_cfg["call"]["segment"]),
                batch_size=int(stage_cfg["call"]["batch_size"]), threads=int(stage_cfg["call"]["threads"]),
                zero_mentions_in_continuity=bool(stage_cfg["output"]["zero_mentions_in_continuity"]),
                empty_form_placeholder=str(stage_cfg["input"]["empty_form_placeholder"]))
        if s.input_parse not in cls.PARSES:
            raise ValueError(f"[input] parse must be one of {cls.PARSES}, not {s.input_parse!r}")
        if s.segment < 0 or s.batch_size < 0 or s.threads < 0:
            raise ValueError("segment, batch_size and threads must be zero or positive")
        if not s.empty_form_placeholder.strip() or CELL_BREAKS_RE.search(s.empty_form_placeholder):
            raise ValueError("[input] empty_form_placeholder must be visible and hold no line break or tab")
        return s


def script_tokenizer_name(encoder: str) -> str:
    """The tokeniser corpipe26_onestage.py loads for an encoder (main(), the first rule that matches)."""
    for mark, name in SCRIPT_TOKENIZERS:
        if mark in encoder:
            return name
    return encoder


# ------------------------------------------------------------------------------------------------------- input


def _cell(value: object) -> str:
    """A CoNLL-U field: empty becomes "_", and a tab or line break becomes a space (the parse artefact has none)."""
    text = "_" if value is None or value == "" else str(value)
    return CELL_BREAKS_RE.sub(" ", text)


@dataclass
class InputDoc:
    """CorPipe's input for one document and what is needed to read its output back.

    `written` lists the segmentation index k of each sentence written, `forms` the (word id, form) pairs written for
    each, `replaced` the (k, word id) of forms written as the placeholder, and `refused` the k of sentences left out
    because they exceed the segment.
    """

    text: str
    written: list[int]
    forms: dict[int, list[tuple[int, str]]] = field(default_factory=dict)
    replaced: list[tuple[int, int]] = field(default_factory=list)
    refused: list[int] = field(default_factory=list)
    subwords: int = 0


def input_conllu(doc: ConlluDocument, count: Callable[[str], int] | None = None, limit: int | None = None,
                 placeholder: str = "_") -> InputDoc:
    """CorPipe's input for one document.

    Sentences the parser returned nothing for are left out, since udapi needs a word in every tree. With `count`, the
    number of subwords the script's tokeniser gives a form, a form of no subword is written as `placeholder`, and a
    sentence of more than `limit` subwords is left out (module docstring), so neither stops the run. Sentence ids
    are the plain indices and the document id is a constant, so no story id, whatever its characters, passes through
    udapi (which reads a "/" in a sentence id as a zone separator). Token lines keep the parse's ids, forms, lemmas,
    tags and tree; DEPS and MISC are left empty.
    """
    lines: list[str] = []
    out = InputDoc(text="", written=[])
    for s in doc.sentences:
        if s.empty or not s.tokens:
            continue
        forms = [(w.id, _cell(w.form)) for w in s.words]
        n_subwords = 0
        if count is not None:
            fixed = []
            for wid, form in forms:
                if count(form) == 0:
                    out.replaced.append((s.k, wid))
                    form = placeholder
                fixed.append((wid, form))
                n_subwords += count(form)
            forms = fixed
            if limit is not None and n_subwords > limit:
                out.replaced = [r for r in out.replaced if r[0] != s.k]
                out.refused.append(s.k)
                continue
        form_of = dict(forms)
        if not out.written:
            lines.append("# newdoc id = doc")
        lines.append(f"# sent_id = {s.k}")
        lines.append(f"# text = {_cell(s.text) if s.text else '_'}")
        for tok in s.tokens:
            if len(tok.words) > 1:
                lines.append(f"{tok.words[0].id}-{tok.words[-1].id}\t{_cell(tok.form)}" + "\t_" * 8)
            for w in tok.words:
                lines.append("\t".join([str(w.id), form_of[w.id], _cell(w.lemma), _cell(w.upos), _cell(w.xpos),
                                        _cell(w.feats), str(w.head), _cell(w.deprel), "_", "_"]))
        lines.append("")
        out.written.append(s.k)
        out.forms[s.k] = forms
        out.subwords += n_subwords
    out.text = "\n".join(lines) + "\n" if lines else ""
    return out


@dataclass
class InputFile:
    """One document's input file and what is needed to read its output back."""

    index: int
    story_id: str
    path: Path
    written: list[int]
    forms: dict[int, list[tuple[int, str]]] = field(default_factory=dict)
    replaced: list[tuple[int, int]] = field(default_factory=list)
    refused: list[int] = field(default_factory=list)

    @property
    def output_name(self) -> str:
        """The name CorPipe gives the prediction for this input."""
        return self.path.stem + OUTPUT_SUFFIX


@dataclass
class InputReport:
    """What write_inputs() left out or changed, by document index."""

    skipped: int = 0
    refused: dict[int, list[int]] = field(default_factory=dict)
    replaced: dict[int, list[tuple[int, int]]] = field(default_factory=dict)


def write_inputs(docs: Iterable[tuple[str, ConlluDocument | None]], folder: Path,
                 count: Callable[[str], int] | None = None, limit: int | None = None,
                 placeholder: str = "_") -> tuple[list[InputFile], InputReport]:
    """Write one input file per document that has a sendable sentence; return the files and what was left out."""
    folder = Path(folder)
    if SEGMENT_OVERRIDE_MARK in str(folder.resolve()).lower():
        raise ValueError(f"the input folder {folder} contains {SEGMENT_OVERRIDE_MARK!r}, which makes the official "
                         f"script cap the segment at 512 subwords")
    folder.mkdir(parents=True, exist_ok=True)
    files, report = [], InputReport()
    for i, (story_id, doc) in enumerate(docs):
        made = input_conllu(doc, count, limit, placeholder) if doc is not None else InputDoc(text="", written=[])
        if made.refused:
            report.refused[i] = made.refused
        if made.replaced:
            report.replaced[i] = made.replaced
        if not made.written:
            report.skipped += 1
            continue
        path = folder / f"{INPUT_PREFIX}{i:07d}.conllu"
        path.write_text(made.text, encoding="utf-8", newline="\n")
        files.append(InputFile(index=i, story_id=story_id, path=path, written=made.written, forms=made.forms,
                               replaced=made.replaced, refused=made.refused))
    return files, report


class SubwordCounter:
    """Subwords per form under the script's own tokeniser, as Dataset.__init__ counts them, memoised.

    corpipe26_onestage.py: `subword = tokenizer.encode(word, add_special_tokens=False)` for each word, after main()
    has built the tokeniser with `legacy=False` and added its special tokens. load() repeats those two steps.
    """

    def __init__(self, tokenizer) -> None:
        self._tokenizer = tokenizer
        self._cache: dict[str, int] = {}

    @classmethod
    def load(cls, encoder: str) -> SubwordCounter:
        """The tokeniser of an encoder as the script builds it, from the Hugging Face cache (offline)."""
        import transformers  # lazy: present in the corpipe environment

        tokenizer = transformers.AutoTokenizer.from_pretrained(script_tokenizer_name(encoder), legacy=False)
        tokenizer.add_special_tokens({"additional_special_tokens": [TOKEN_EMPTY] + (
            [TOKEN_CLS] if tokenizer.cls_token_id is None else [])})
        return cls(tokenizer)

    def __call__(self, form: str) -> int:
        """The number of subwords of one form."""
        n = self._cache.get(form)
        if n is None:
            n = self._cache[form] = len(self._tokenizer.encode(form, add_special_tokens=False))
        return n


def corpipe_args(model_dir: Path, out_dir: Path, inputs: Sequence[Path], settings: CorpipeSettings) -> list[str]:
    """The official script's arguments for one call (README, "Predicting with a CorPipe 26 Model")."""
    args = ["--load", str(model_dir), "--exp", str(out_dir), "--epochs", "0"]
    if settings.segment:
        args += ["--segment", str(settings.segment)]
    if settings.batch_size:
        args += ["--batch_size", str(settings.batch_size)]
    if settings.threads:
        args += ["--threads", str(settings.threads)]
    return args + ["--test", *map(str, inputs)]


# ------------------------------------------------------------------------------------------------------ launch


def corpipe_environment(runtime: TorchRuntime) -> dict[str, str]:
    """Environment for the official script: the runtime's own variables plus minnt's TF32 and device switches.

    minnt.startup() sets torch.backends.cuda.matmul.allow_tf32 from MINNT_ALLOW_TF32 when that is "0" or "1", and
    minnt's device choice reads MINNT_DEVICE (minnt 1.1.1, startup_impl.py and utils.get_auto_device).
    """
    env = runtime.environment()
    env["MINNT_ALLOW_TF32"] = "1" if runtime.allow_tf32 else "0"
    if runtime.device != "auto":
        env["MINNT_DEVICE"] = runtime.device
    return env


@contextlib.contextmanager
def patched_environ(values: Mapping[str, str]) -> Iterator[None]:
    """Set environment variables for the duration of a block and restore them after."""
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run_script(script: Path, args: Sequence[str]) -> None:
    """Execute a script file as __main__ with the given arguments, restoring sys.argv after.

    runpy.run_path executes a plain file directly, without adding its folder to sys.path. A non-zero exit, such as
    an argparse error, becomes a RuntimeError naming the script.
    """
    saved = sys.argv[:]
    sys.argv = [str(script), *map(str, args)]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as e:
        if e.code not in (None, 0):
            raise RuntimeError(f"{Path(script).name} exited with status {e.code}") from e
    finally:
        sys.argv = saved


def _float32_hidden_states(module, args, output):
    """Forward hook: the encoder's last hidden state goes on to the heads in float32 (bf16 runs)."""
    output.last_hidden_state = output.last_hidden_state.float()
    return output


@contextlib.contextmanager
def weights_hook(record: dict, *, bf16: bool) -> Iterator[None]:
    """Wrap minnt.TrainableModule.load_weights for one run of the script, restoring it after.

    After the script's own load (main(): `model.load_weights(os.path.join(args.load[0], "model.pt"))`), the wrapper
    records when loading finished and, when `bf16`, casts the model's `_encoder` to bfloat16 and hooks its output
    back to float32 (module docstring). A model without an `_encoder` module stops the run, since the pinned script
    always has one.
    """
    import minnt  # lazy: present in the corpipe environment
    import torch

    original = minnt.TrainableModule.load_weights

    def load_weights(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        record["weights_loaded_at"] = time.perf_counter()
        record["weight_loads"] = record.get("weight_loads", 0) + 1
        if bf16:
            encoder = getattr(self, "_encoder", None)
            if not isinstance(encoder, torch.nn.Module):
                raise RuntimeError("the CorPipe model has no _encoder module to run in bf16")
            encoder.to(torch.bfloat16)
            encoder.register_forward_hook(_float32_hidden_states)
            params = list(self.parameters())
            record["bf16_parameters"] = sum(p.numel() for p in params if p.dtype == torch.bfloat16)
            record["float32_parameters"] = sum(p.numel() for p in params if p.dtype == torch.float32)
        return result

    minnt.TrainableModule.load_weights = load_weights
    try:
        yield
    finally:
        minnt.TrainableModule.load_weights = original


def launch(script: Path, args: Sequence[str], runtime: TorchRuntime) -> dict:
    """Run the official CorPipe script under the registered runtime and return the runtime record.

    The environment is set first (cuBLAS reads its workspace setting when CUDA starts), then torch's flags. A
    bfloat16 runtime casts the encoder after loading (weights_hook); otherwise everything runs in fp32. A run that
    ends with TF32 on breaks DESIGN.md's determinism rule, so it stops the stage, as does a bf16 run whose encoder
    was not cast exactly once.
    """
    bf16 = runtime.dtype == "bfloat16"
    with patched_environ(corpipe_environment(runtime)):
        record = runtime.apply()
        import torch  # lazy: present in the corpipe environment, absent from the unit tests

        started = time.perf_counter()
        with weights_hook(record, bf16=bf16):
            run_script(script, args)
        finished = time.perf_counter()
        record["allow_tf32_after_run"] = torch.backends.cuda.matmul.allow_tf32
        record["minnt_allow_tf32"] = os.environ.get("MINNT_ALLOW_TF32")
    loaded = record.pop("weights_loaded_at", None)
    if loaded is not None:
        # Setup: reading and tokenising the inputs, building the model and loading its weights; then prediction.
        record["setup_seconds"] = loaded - started
        record["predict_seconds"] = finished - loaded
    if record["allow_tf32_after_run"] and not runtime.allow_tf32:
        raise RuntimeError("TF32 was on after the CorPipe run although the runtime forbids it")
    if bf16 and record.get("weight_loads") != 1:
        raise RuntimeError(f"the bf16 run loaded weights {record.get('weight_loads', 0)} times, not once")
    return record


def read_cache(input_path: Path) -> list | None:
    """The tokenised documents the script caches beside an input, or None if there is no single cache file.

    corpipe26_onestage.py, Dataset.__init__, pickles each document as a list of sentences whose first item is the
    sentence's subword ids, to `<input>.mentions1.<tokeniser name>`. The file is written by the official script in
    this run's private scratch folder, so it is trusted.
    """
    caches = sorted(Path(input_path).parent.glob(Path(input_path).name + ".mentions1.*"))
    if len(caches) != 1:
        return None
    with open(caches[0], "rb") as fh:
        return pickle.load(fh)  # written by the official script in this run's private scratch folder


def encoder_cost(docs: Sequence, segment: int, right: int | None, batch_size: int) -> dict:
    """What the encoder computed for one input, rebuilt from the script's cache as Dataset.dataset builds it.

    Each sentence is encoded with up to `segment` subwords: [CLS], left context, a separator, the sentence, a
    separator, right context and a closing separator (corpipe26_onestage.py, Dataset.dataset, prediction). Batches of
    `batch_size` consecutive sentences are padded to their longest (Dataset.padded_batch). Returns the sentence
    subwords, the encoder positions, the padded positions and the sentences the script would truncate.
    """
    tokens = positions = padded = truncated = 0
    lengths: list[int] = []
    for doc in docs:
        p_len = 0
        for i, sentence in enumerate(doc):
            n = len(sentence[0])
            tokens += n
            if n + SEGMENT_RESERVED > segment:
                truncated += 1
                n = segment - SEGMENT_RESERVED
            right_reserve = min((segment - SEGMENT_RESERVED - n) // 2, right or 0)
            context = min(segment - SEGMENT_RESERVED - n - right_reserve, p_len)
            e_len = 3 + context + n
            if right is not None:
                j = i + 1
                while j < len(doc) and e_len + 1 < segment:
                    e_len += min(len(doc[j][0]), segment - e_len - 1)
                    j += 1
            e_len += 1
            lengths.append(e_len)
            p_len += n
    positions = sum(lengths)
    step = max(batch_size, 1)
    padded = sum(len(chunk) * max(chunk) for chunk in (lengths[k:k + step] for k in range(0, len(lengths), step)))
    return {"tokens": tokens, "encoder_positions": positions, "padded_positions": padded,
            "truncated_sentences": truncated}


# ------------------------------------------------------------------------------------------------------ output


@dataclass(frozen=True)
class OutNode:
    """A word or empty-node line of CorPipe's output.

    `word` is the syntactic word id for a word line and None for an empty node; `ord` orders both as udapi's
    descendants_and_empty does (an empty node n.k follows word n); `deps` is the DEPS column, where CorPipe writes
    "<parent>:<deprel>" for each empty node it predicts.
    """

    ord: tuple[int, int]
    word: int | None
    form: str
    entity: str
    deps: str


@dataclass
class OutSentence:
    """One sentence of CorPipe's output."""

    sent_id: str | None
    nodes: list[OutNode] = field(default_factory=list)


def _misc_value(misc: str, key: str) -> str:
    if misc in ("", "_"):
        return ""
    for part in misc.split("|"):
        name, sep, value = part.partition("=")
        if sep and name == key:
            return value
    return ""


def _ord(token_id: str, where: str) -> tuple[tuple[int, int], int | None]:
    if token_id.isdigit():
        return (int(token_id), 0), int(token_id)
    head, sep, tail = token_id.partition(".")
    if sep and head.isdigit() and tail.isdigit():
        return (int(head), int(tail)), None
    raise ValueError(f"{where}: unexpected token id {token_id!r}")


def read_output(lines: Iterable[str], where: str = "CorPipe output") -> tuple[list[OutSentence], tuple[str, ...]]:
    """Parse CorPipe's output CoNLL-U into sentences of nodes, with the global.Entity field order it declares."""
    sentences: list[OutSentence] = []
    fields = DEFAULT_ENTITY_FIELDS
    current: OutSentence | None = None
    for n, raw in enumerate(lines, 1):
        line = raw.rstrip("\r\n")
        if not line:
            if current is not None:
                sentences.append(current)
                current = None
            continue
        if line.startswith("#"):
            key, sep, value = line[1:].strip().partition("=")
            if sep and key.strip() == "global.Entity":
                fields = tuple(value.strip().split("-"))
            elif sep and key.strip() == "sent_id":
                current = current or OutSentence(sent_id=None)
                current.sent_id = value.strip()
            continue
        cols = line.split("\t")
        if len(cols) != 10:
            raise ValueError(f"{where}, line {n}: {len(cols)} columns, not 10")
        if "-" in cols[0]:
            continue  # a multi-word token's range line; Entity sits on its words
        current = current or OutSentence(sent_id=None)
        ord_, word = _ord(cols[0], f"{where}, line {n}")
        if current.nodes and ord_ <= current.nodes[-1].ord:
            raise ValueError(f"{where}, line {n}: token ids out of order")
        current.nodes.append(OutNode(ord=ord_, word=word, form=cols[1], entity=_misc_value(cols[9], "Entity"),
                                     deps=cols[8]))
    if current is not None:
        sentences.append(current)
    return sentences, fields


@dataclass(frozen=True)
class RawMention:
    """A mention as CorPipe wrote it: its entity id, its first and last node (indices into the sentence's nodes),
    the 1-based head index udapi wrote (counting empty nodes inside the span) and whether it is one subspan of a
    discontinuous mention."""

    eid: str
    first: int
    last: int
    head: int | None
    subspan: bool = False


def entity_chunks(value: str) -> list[str]:
    """The chunks of an Entity value, split as udapi splits them ("(e1-person(e2-place)" -> two chunks)."""
    return [c for c in ENTITY_CHUNK_RE.split(value) if c]


def sentence_mentions(sentence: OutSentence, fields: Sequence[str], where: str = "") -> tuple[list[RawMention], int]:
    """The mentions of one output sentence, following udapi's load_coref_from_misc; returns them and the number of
    mentions opened but never closed.

    A closing chunk closes the latest open mention of its entity; an opening chunk opens one; a chunk with both
    brackets is a one-node mention. A mention spans every node from its opening to its closing node, empty nodes
    included, as in udapi. CorPipe writes no mention across sentences, so one still open at the end of its sentence
    is counted and dropped (udapi deletes a mention never closed).
    """
    open_: dict[str, list[tuple[int, int | None, bool]]] = {}
    mentions: list[RawMention] = []
    for i, node in enumerate(sentence.nodes):
        if not node.entity:
            continue
        for chunk in entity_chunks(node.entity):
            opening, closing = chunk[0] == "(", chunk[-1] == ")"
            body = chunk.strip("()")
            if not opening and not closing:
                raise ValueError(f"{where}: Entity chunk {chunk!r} has no bracket")
            if not opening:
                eid, subspan = body, False
                if eid not in open_ or not open_[eid]:
                    m = DISCONTINUOUS_RE.match(body)
                    if not m:
                        raise ValueError(f"{where}: mention {body!r} closed but not opened")
                    eid, subspan = m.group(1), True
                if not open_.get(eid):
                    raise ValueError(f"{where}: mention {body!r} closed but not opened")
                first, head, was_subspan = open_[eid].pop()
                mentions.append(RawMention(eid, first, i, head, subspan or was_subspan))
                continue
            values = dict(zip(fields, body.split("-"), strict=False))
            eid = values.get("eid") or values.get("GRP")
            if not eid:
                raise ValueError(f"{where}: no entity id in Entity chunk {chunk!r}")
            head = int(values["head"]) if values.get("head", "").isdigit() else None
            subspan = False
            m = DISCONTINUOUS_RE.match(eid)
            if m:
                eid, subspan = m.group(1), True
            if closing:
                mentions.append(RawMention(eid, i, i, head, subspan))
            else:
                open_.setdefault(eid, []).append((i, head, subspan))
    unclosed = sum(len(v) for v in open_.values())
    return mentions, unclosed


# ----------------------------------------------------------------------------------------------------- mapping


def word_offsets(sentence: ConlluSentence) -> dict[int, tuple[int, int] | None]:
    """Each syntactic word id of a parsed sentence mapped to its token's [start, end) offsets in Document.text.

    Every word of a multi-word token takes the token's offsets; a token the parse could not place maps to None.
    """
    out: dict[int, tuple[int, int] | None] = {}
    for tok in sentence.tokens:
        span = (tok.start, tok.end) if tok.start is not None and tok.end is not None else None
        for w in tok.words:
            out[w.id] = span
    return out


@dataclass
class _Mention:
    entity: str
    k: int
    order: tuple[int, int]
    payload: dict
    zero: bool


def _mention_payload(raw: RawMention, nodes: Sequence[OutNode], k: int, offsets: Mapping[int, tuple[int, int] | None]
                     ) -> tuple[dict, bool, bool]:
    """The record of one mention, whether it is a zero mention, and whether its offsets are unknown."""
    span_nodes = nodes[raw.first:raw.last + 1]
    words = [n.word for n in span_nodes if n.word is not None]
    head_node = span_nodes[raw.head - 1] if raw.head and 0 < raw.head <= len(span_nodes) else None
    if not words:  # a zero mention: an empty node CorPipe predicted, anchored to its parent word
        parent, _, deprel = span_nodes[0].deps.partition(":")
        parent_id = int(parent) if parent.isdigit() else None
        span = offsets.get(parent_id) if parent_id else None
        return ({"k": k, "parent": parent_id, "deprel": deprel or None, "start": span[0] if span else None,
                 "end": span[1] if span else None}, True, span is None)
    first, last = offsets.get(words[0]), offsets.get(words[-1])
    unknown = first is None or last is None
    payload = {"k": k, "start": None if unknown else first[0], "end": None if unknown else last[1],
               "words": [words[0], words[-1]], "head": head_node.word if head_node is not None else None}
    if len(words) != len(span_nodes):
        payload["empty_nodes"] = len(span_nodes) - len(words)
    return payload, False, unknown


def document_chains(story_id: str, parse_doc: ConlluDocument | None, written: Sequence[int],
                    output: Sequence[OutSentence], fields: Sequence[str], *, zero_in_continuity: bool,
                    forms: Mapping[int, Sequence[tuple[int, str]]] | None = None) -> dict:
    """Chains, zero mentions and adjacent-pair continuity of one document, in Document.text offsets.

    `written` lists the segmentation index k of each sentence sent to CorPipe, in order; `output` is CorPipe's
    prediction for that input, sentence by sentence; `forms` holds the (word id, form) pairs written for each k
    (input_conllu), which the output's words must repeat exactly. Entities are renumbered 1, 2, ... by their first
    mention, and mentions are ordered by sentence, start and length, so the record does not depend on CorPipe's
    internal ids.

    `pair_continuity` has one value per adjacent sentence pair (k, k + 1) of the segmentation: 1 if some entity has
    a mention in both sentences, 0 if not, and None if either sentence was not sent to CorPipe (no parse, or longer
    than the segment), because then nothing is known about the pair. It is the English chain continuity whose
    agreement with referential overlap S3 reports as the English-internal ceiling; zero mentions count only if
    `zero_in_continuity` is set.
    """
    if len(output) != len(written):
        raise ValueError(f"{story_id}: CorPipe returned {len(output)} sentences for {len(written)}")
    by_k = {s.k: s for s in parse_doc.sentences} if parse_doc is not None else {}
    n_sentences = len(parse_doc.sentences) if parse_doc is not None else 0
    mentions: list[_Mention] = []
    diag = {"sentences": n_sentences, "sentences_sent": len(written), "mentions": 0, "zero_mentions": 0,
            "unmapped_mentions": 0, "unclosed_mentions": 0, "discontinuous_subspans": 0,
            "mentions_with_empty_nodes": 0}
    for k, out in zip(written, output, strict=True):
        parsed = by_k.get(k)
        if parsed is None:
            raise ValueError(f"{story_id}: no parsed sentence {k}")
        # Ids and forms must both match what was sent, so a mixed-up output file cannot be mapped.
        out_words = [(n.word, n.form) for n in out.nodes if n.word is not None]
        sent_words = list(forms[k]) if forms is not None and k in forms else [(w.id, _cell(w.form))
                                                                              for w in parsed.words]
        if out_words != sent_words:
            raise ValueError(f"{story_id}, sentence {k}: CorPipe's words {out_words[:6]} differ from those sent "
                             f"{sent_words[:6]}")
        if out.sent_id is not None and out.sent_id != str(k):
            raise ValueError(f"{story_id}: output sentence {out.sent_id!r} where sentence {k} was expected")
        raws, unclosed = sentence_mentions(out, fields, f"{story_id}, sentence {k}")
        diag["unclosed_mentions"] += unclosed
        offsets = word_offsets(parsed)
        for raw in raws:
            payload, zero, unknown = _mention_payload(raw, out.nodes, k, offsets)
            diag["zero_mentions" if zero else "mentions"] += 1
            diag["unmapped_mentions"] += unknown
            diag["discontinuous_subspans"] += raw.subspan
            diag["mentions_with_empty_nodes"] += "empty_nodes" in payload
            mentions.append(_Mention(raw.eid, k, (raw.first, -raw.last), payload, zero))
    mentions.sort(key=lambda m: (m.k, m.order, m.zero))
    number: dict[str, int] = {}
    for m in mentions:
        number.setdefault(m.entity, len(number) + 1)
    chains = [{"entity": n, "mentions": [], "zero": []} for n in range(1, len(number) + 1)]
    for m in mentions:
        chains[number[m.entity] - 1]["zero" if m.zero else "mentions"].append(m.payload)
    sentences_of = [{p["k"] for p in c["mentions"]} | ({p["k"] for p in c["zero"]} if zero_in_continuity else set())
                    for c in chains]
    sent = set(written)
    pairs = [int(any(k in ks and k + 1 in ks for ks in sentences_of)) if k in sent and k + 1 in sent else None
             for k in range(max(n_sentences - 1, 0))]
    known = [p for p in pairs if p is not None]
    diag.update(chains=len(chains), singletons=sum(1 for c in chains if len(c["mentions"]) + len(c["zero"]) == 1),
                adjacent_pairs=len(pairs), pairs_with_data=len(known), pairs_sharing_chain=sum(known),
                pair_continuity_share=sum(known) / len(known) if known else None,
                syntactic_words_sent=sum(len(by_k[k].words) for k in written),
                characters_sent=sum(len(by_k[k].text) for k in written))
    return {"chains": chains, "pair_continuity": pairs, "diagnostics": diag}


def read_output_file(path: Path) -> tuple[list[OutSentence], tuple[str, ...]]:
    """read_output() on a file."""
    with open(path, encoding="utf-8", newline="\n") as fh:
        return read_output(fh, where=Path(path).name)
