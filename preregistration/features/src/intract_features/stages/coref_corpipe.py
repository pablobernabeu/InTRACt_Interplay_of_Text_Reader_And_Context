"""Stage coref_corpipe: CorPipe 26 coreference chains on every English source (GPU, environment corpipe).

supplementary.qmd S3, referential overlap row: "CorPipe 26 [...], with its umT5-xl one-stage model, instead resolves
coreference on every English source as a validation reference." The chains mask a sensitivity overlap anchor after
projection by word alignment (Materials) and give the English-internal ceiling of the κ that S3 reports.

Reads `documents` and the parse named by [input] parse in config/stages/coref_corpipe.toml (the Stanza parse by
default, pending gap G8; STAGE.inputs names that default, and [input] parse = "parses_udpipe" reads the other parse),
and writes `coref_corpipe`, one record per document:

    {"story_id", "lang", "values": {},
     "chains": [{"entity": 1, "mentions": [{"k", "start", "end", "words": [first, last], "head"}, ...],
                 "zero": [{"k", "parent", "deprel", "start", "end"}, ...]}, ...],
     "pair_continuity": [1, 0 or null for each adjacent sentence pair (k, k + 1)],
     "diagnostics": {...}}

`k` is the sentence's index in the segmentation, `start` and `end` are offsets in Document.text, `words` and `head`
are syntactic word ids of the parse, and a zero mention is an empty node CorPipe predicted, anchored to its parent
word. A pair is null when either sentence was not sent to CorPipe. No quantity here is a registered feature, so
`values` is empty.

[model] variant chooses the model: "xl", the registered umT5-xl model, or "large", the mT5-large model the budget
guard falls back to (preregistration.qmd, Timeline: "Second, the coreference resolver falls back to a smaller model";
S3: "against 75.1 for its mT5-large fallback"). The pinned official script runs unchanged (reference/corpipe_run.py).
Every pinned file is verified first: the script, the model's files, and the encoder configuration and tokeniser that
the script loads by name from the Hugging Face cache, whose refs/main must name the pinned revisions.

The timing record's `words` and `characters` count the registered words and the characters of every document of the
shard (DESIGN.md: Words are the registered word function), so aggregate_timing projects this stage on the same units
as the others; the parser's words sent to CorPipe are `syntactic_words`.
"""

from __future__ import annotations

import importlib.metadata
import json
import tempfile
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from intract_features.cli import Stage, StageContext
from intract_features.parse import ConlluDocument, read_conllu
from intract_features.records import Document
from intract_features.reference import (
    PinError,
    TorchRuntime,
    hf_cache_ref,
    hf_snapshot_dir,
    model_pin,
    pinned_folder,
    verify_pinned_files,
)
from intract_features.reference import corpipe_run as cr
from intract_features.text.words import count_words

STAGE = Stage(name="coref_corpipe", inputs=("documents", "parses_stanza"), outputs=("coref_corpipe",), device="gpu",
              env="corpipe", description="CorPipe 26 one-stage coreference on every English source (S3; umT5-xl, "
                                         "mT5-large as the budget guard's fallback)")

# corpipe26_onestage.py's argparse defaults for the options the stage reads back: "--segment" 512, "--batch_size" 8,
# "--right" 50. options.json and the command line override them, in that order (main(): "load configuration from a
# trained model", then parse_args with that namespace).
SCRIPT_DEFAULTS = {"segment": 512, "batch_size": 8, "right": 50}


@dataclass(frozen=True)
class Pinned:
    """The verified files of one run."""

    script: Path
    model_dir: Path
    options: dict
    record: dict
    encoder: str = ""


def check_versions(wanted: dict) -> dict:
    """The installed versions of the corpipe environment's packages, each checked against its pinned prefix."""
    have, bad = {}, []
    for package, prefix in wanted.items():
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            bad.append(f"{package} is not installed")
            continue
        have[package] = version
        if version != prefix and not version.split("+")[0].startswith(prefix + "."):
            bad.append(f"{package} {version} is installed, {prefix}.* pinned")
    if bad:
        raise PinError("the corpipe environment does not match the pinned code's requirements: " + "; ".join(bad))
    return have


def model_variant(scfg: Mapping) -> dict:
    """The [model.variants] table [model] variant names, checked for its keys."""
    m = scfg["model"]
    name = str(m["variant"])
    variants = m.get("variants", {})
    if name not in variants:
        raise ValueError(f"[model] variant {name!r} is not one of {sorted(variants)}")
    v = dict(variants[name])
    for key in ("corpipe", "encoder", "tokenizer"):
        if not v.get(key):
            raise ValueError(f"[model.variants.{name}] lacks {key!r}")
    if cr.script_tokenizer_name(v["encoder"]) != v["tokenizer"]:
        raise ValueError(f"[model.variants.{name}]: the official script loads the tokeniser "
                         f"{cr.script_tokenizer_name(v['encoder'])!r} for {v['encoder']!r}, not {v['tokenizer']!r}")
    return {"name": name, **v}


def _hub_snapshot(config: dict, repo: str, environ: Mapping[str, str] | None) -> dict:
    """Verify a snapshot the script loads by hub name: refs/main must name the pinned revision."""
    entry = model_pin(config, repo)
    revision = str(entry.get("revision") or "")
    ref = hf_cache_ref(repo, "main", environ)
    if ref != revision:
        raise PinError(f"the Hugging Face cache's refs/main for {repo} names {ref!r}, not the pinned {revision!r}; "
                       f"the script loads that snapshot by name")
    return {"repo": repo, "revision": revision,
            "files": verify_pinned_files(hf_snapshot_dir(repo, revision, environ), entry, what=f"the {repo} snapshot")}


def verify_pins(config: dict, scfg: dict, environ: dict | None = None) -> Pinned:
    """Verify the script, the model and the hub snapshots it loads against config/models.lock.json before loading.

    The script loads its encoder's configuration, and the tokeniser it chooses for that encoder, by hub name in
    offline mode, which reads the cache snapshot that refs/main names; for the large model these are two
    repositories (google/mt5-large and google/mt5-xl).
    """
    m = scfg["model"]
    variant = model_variant(scfg)
    code = model_pin(config, m["code"])
    code_dir = pinned_folder(code, env_name=m["code_dir_env"], environ=environ)
    record = {"variant": variant["name"],
              "code": {"repo": code.get("repo"), "revision": code.get("revision"),
                       "files": verify_pinned_files(code_dir, code, what="the CorPipe code")}}
    script = code_dir / m["script"]
    if m["script"] not in {f["file"] for f in record["code"]["files"]}:
        raise PinError(f"the pin {m['code']!r} does not cover {m['script']}")
    model = model_pin(config, variant["corpipe"])
    model_dir = pinned_folder(model, env_name=m["model_dir_env"], environ=environ)
    record["model"] = {"repo": model.get("repo"), "revision": model.get("revision"), "licence": model.get("licence"),
                       "files": verify_pinned_files(model_dir, model, what="the CorPipe model")}
    options = json.loads((model_dir / "options.json").read_text(encoding="utf-8"))
    if options.get("encoder") != variant["encoder"]:
        raise PinError(f"options.json names the encoder {options.get('encoder')!r}; the {variant['name']} variant is "
                       f"the {variant['encoder']} model")
    record["encoder"] = _hub_snapshot(config, variant["encoder"], environ)
    if variant["tokenizer"] != variant["encoder"]:
        record["tokenizer"] = _hub_snapshot(config, variant["tokenizer"], environ)
    return Pinned(script=script, model_dir=model_dir, options=options, record=record, encoder=variant["encoder"])


def joined(documents: Iterator[Document], parses: Iterator[ConlluDocument], *,
           strict: bool = True) -> Iterator[tuple[Document, ConlluDocument | None]]:
    """Pair each document with its parse, both in documents order; a document the parse skipped gets None.

    The parse stages write documents in documents order and skip a document with no sentence, so a parse whose
    story is not the current document must belong to a later one. A parse left over at the end matched no document
    in order, which stops the stage when `strict`; with --limit the parse legitimately holds later stories.
    """
    pending = next(parses, None)
    for doc in documents:
        if pending is not None and pending.story_id == doc.story_id:
            yield doc, pending
            pending = next(parses, None)
        else:
            yield doc, None
    if strict and pending is not None:
        raise ValueError(f"the parse of {pending.story_id!r} matches no document in documents order")


def call_options(settings: cr.CorpipeSettings, options: Mapping) -> dict:
    """The segment, batch size and right context the script will use: command line, else options.json, else its
    defaults."""
    return {"segment": settings.segment or int(options.get("segment", SCRIPT_DEFAULTS["segment"])),
            "batch_size": settings.batch_size or int(options.get("batch_size", SCRIPT_DEFAULTS["batch_size"])),
            "right": options.get("right", SCRIPT_DEFAULTS["right"])}


def load_counter(encoder: str, runtime: TorchRuntime) -> cr.SubwordCounter:
    """The script's tokeniser for `encoder`, loaded offline from the verified cache snapshot."""
    with cr.patched_environ(runtime.environment()):
        return cr.SubwordCounter.load(encoder)


def run(ctx: StageContext) -> dict:
    """Resolve coreference on one shard of the English sources and return the counts for the timing record."""
    scfg = ctx.stage_config()
    if ctx.lang != scfg["source_lang"]:
        raise ValueError(f"coref_corpipe runs on the English sources ({scfg['source_lang']}) only; S3: coreference "
                         f"is resolved in no translation, so {ctx.lang!r} is refused")
    settings = cr.CorpipeSettings.from_config(scfg)
    runtime = TorchRuntime.from_config(scfg["runtime"])
    parse_path = ctx.path(settings.input_parse, ext="conllu.gz")
    if not parse_path.is_file():
        raise FileNotFoundError(f"the input parse {parse_path} is missing ([input] parse = {settings.input_parse!r})")
    t0 = time.perf_counter()
    versions = check_versions(dict(scfg["versions"]))
    pinned = verify_pins(ctx.config, scfg)
    call = call_options(settings, pinned.options)
    limit = call["segment"] - cr.SEGMENT_RESERVED
    counter = load_counter(pinned.encoder, runtime)
    if counter(settings.empty_form_placeholder) < 1:
        raise ValueError(f"the placeholder {settings.empty_form_placeholder!r} encodes to no subword either")
    verify_seconds = time.perf_counter() - t0

    counts = {"documents": 0, "documents_without_sentences": 0, "words": 0, "whitespace_tokens": 0, "characters": 0,
              "syntactic_words": 0, "characters_sent": 0, "sentences": 0, "sentences_sent": 0, "sentences_refused": 0,
              "forms_replaced": 0,
              "tokens": 0, "encoder_positions": 0, "padded_positions": 0, "truncated_sentences": 0, "mentions": 0,
              "zero_mentions": 0, "chains": 0, "singletons": 0, "unmapped_mentions": 0, "unclosed_mentions": 0,
              "pairs_with_data": 0, "pairs_sharing_chain": 0}
    strict = ctx.limit is None
    with tempfile.TemporaryDirectory(prefix="corpipe-") as tmp:
        in_dir, out_dir = Path(tmp) / "in", Path(tmp) / "out"
        pairs = joined(ctx.documents(), read_conllu(parse_path), strict=strict)
        files, report = cr.write_inputs(((d.story_id, p) for d, p in pairs), in_dir, counter, limit,
                                        settings.empty_form_placeholder)
        runtime_record = {}
        if files:
            args = cr.corpipe_args(pinned.model_dir, out_dir, [f.path for f in files], settings)
            runtime_record = cr.launch(pinned.script, args, runtime)
        by_index = {f.index: f for f in files}
        out = []
        for i, (doc, parse_doc) in enumerate(joined(ctx.documents(), read_conllu(parse_path), strict=strict)):
            f = by_index.get(i)
            if f is not None and f.story_id != doc.story_id:
                raise RuntimeError(f"document {i} is {doc.story_id!r} now and was {f.story_id!r} before the run")
            if f is None:
                result = cr.document_chains(doc.story_id, parse_doc, [], [], cr.DEFAULT_ENTITY_FIELDS,
                                            zero_in_continuity=settings.zero_mentions_in_continuity)
                counts["documents_without_sentences"] += 1
            else:
                output, fields = cr.read_output_file(out_dir / f.output_name)
                result = cr.document_chains(doc.story_id, parse_doc, f.written, output, fields,
                                            zero_in_continuity=settings.zero_mentions_in_continuity, forms=f.forms)
                cache = cr.read_cache(f.path)
                cost = (cr.encoder_cost(cache, call["segment"], call["right"], call["batch_size"])
                        if cache is not None else {})
                result["diagnostics"].update(subword_tokens=cost.get("tokens"),
                                             encoder_positions=cost.get("encoder_positions"))
                for key in ("tokens", "encoder_positions", "padded_positions", "truncated_sentences"):
                    counts[key] += cost.get(key) or 0
            d = result["diagnostics"]
            d["sentences_refused"] = report.refused.get(i, [])
            d["forms_replaced"] = len(report.replaced.get(i, []))
            counts["documents"] += 1
            counts["words"] += count_words(doc.text)
            # str.split, the rule behind the catalogue's own token count (aggregate_timing.toml, reference_stages).
            counts["whitespace_tokens"] += len(doc.text.split())
            counts["characters"] += len(doc.text)
            counts["syntactic_words"] += d["syntactic_words_sent"]
            counts["sentences_refused"] += len(d["sentences_refused"])
            counts["forms_replaced"] += d["forms_replaced"]
            for key in ("characters_sent", "sentences", "sentences_sent", "mentions", "zero_mentions", "chains",
                        "singletons", "unmapped_mentions", "unclosed_mentions", "pairs_with_data",
                        "pairs_sharing_chain"):
                counts[key] += d[key]
            out.append({"story_id": doc.story_id, "lang": ctx.lang, "values": {}, "chains": result["chains"],
                        "pair_continuity": result["pair_continuity"], "diagnostics": d})
    # Checked before anything is written, so a shard whose inputs changed under the run leaves no artefact.
    if counts["documents_without_sentences"] != report.skipped:
        raise RuntimeError(f"{report.skipped} documents had no sendable sentence before the run and "
                           f"{counts['documents_without_sentences']} after it")
    if counts["truncated_sentences"]:
        raise RuntimeError(f"{counts['truncated_sentences']} sentences exceeded the segment although the input guard "
                           f"should have left them out")
    ctx.write("coref_corpipe", out)
    setup = {"verify_pins_and_tokenizer": verify_seconds, "script_setup": runtime_record.get("setup_seconds")}
    # seconds_predict is the compute timer (aggregate_timing.toml [split.timers]): the script's prediction, after its
    # weights have loaded; setup_seconds holds the fixed costs paid once per process.
    return {**counts, "segment": call["segment"], "batch_size": call["batch_size"], "right": call["right"],
            "input_parse": settings.input_parse, "variant": pinned.record["variant"], "versions": versions,
            "setup_seconds": setup, "seconds_predict": runtime_record.get("predict_seconds") or 0.0,
            "runtime": runtime_record, "pins_verified": pinned.record}
