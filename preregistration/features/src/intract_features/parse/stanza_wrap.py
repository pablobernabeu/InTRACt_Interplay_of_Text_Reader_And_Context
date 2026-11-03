"""One Stanza 1.15.0 wrapper for every language: explicit packages, the registered sentences, verified files.

Merged from presub/translated_union/scripts/tu4s_stanza.py (the translated benchmark, TU-4s) and
presub/error_model/scripts/parse_stanza2.py (the error model's gold parses, EM-1). The two built the same pipeline
except that only parse_stanza2.py carried the Greek lemmatiser workaround, and TU-4s failed on Greek for want of it.
Supplementary S3 registers "Stanza 1.15.0 in its `nocharlm` tier", run "on every sentence of every text ... with
the registered treebank for the language and its own tokeniser".

Packages. Each processor's package comes from languages.toml (stanza_packages) and is resolved against the frozen
resources.json before Stanza sees it, then passed to Stanza by its exact name. Stanza itself only warns and drops a
processor whose package it cannot find (resources/common.py, maintain_processor_list), adds an mwt model it was not
asked for when the tokeniser has one (add_mwt), and resolves a bundle name such as "gum" through the language's
package table, where pos and depparse map to charlm models. So an unknown package, an mwt model that languages.toml
does not name, or a tiered processor outside the registered `nocharlm` tier stops the stage here.

Sentences. Each registered sentence is one paragraph, paragraphs are joined by a blank line and
tokenize_no_ssplit=True, so Stanza tokenises, tags and parses but cannot move a sentence boundary (as in TU-4s and
EM-1). Stanza splits paragraphs at a newline, optional whitespace and a newline (models/tokenization/data.py), which
is why parse.document_units() flattens line breaks inside a sentence first.

CPU only, offline. use_gpu=False, as in every presub Stanza run (583 syntactic words per CPU-second on htc, one
thread). download_method=None, so Stanza neither fetches resources.json nor downloads a model; it then builds the
pipeline from the files on disk without checking any MD5 (pipeline/core.py). The wrapper therefore checks
resources.json against its SHA-256 pin, every model file the pipeline loads (dependencies included) against the
MD5 the frozen resources.json lists, and, where models.lock.json pins files by SHA-256 ("files"), against that pin
too, before the pipeline is built (DESIGN.md: code verifies a pin before it loads the file).

Greek. Stanza 1.15.0's Greek gdt_nocharlm lemmatiser carries a contextual classifier whose saved word-vector path
is its training machine's (/nlp/scr/...), and resources.json declares no lemma dependency, so building the pipeline
fails with "Pretrained file ... does not exist". Only on that error, the lemmatiser is given the language's own POS
pretrain (the vectors the tagger and parser load) through lemma_pretrain_path, which the lemma processor hands to
the classifier as its wordvec_pretrain_file (pipeline/lemma_processor.py, models/lemma_classifier/base_model.py).
Diagnosed in EM job 9150648 and tested on the whole el_gdt test set in job 9150820, with no missing lemma. Every
other language builds exactly as before; the run record names the path whenever the workaround applies.

Parser batch and memory. Stanza's depparse counts a sentence's length with the ROOT node it prepends
(models/depparse/data.py, Dataset.lengths), sorts a call's sentences longest first, gives every sentence longer than
150 by that count (so of 150 words or more) a batch of its own (DEFAULT_SEPARATE_BATCH, pipeline/
depparse_processor.py) and packs the rest while a batch's summed lengths stay within `batch_size`, the value saved
in the model file unless depparse_batch_size overrides it (pipeline/processor.py, _set_up_final_config; 5,000 in
the English GUM model). Every sentence in a batch is padded to the batch's longest. The label scorer
(models/common/biaffine.py, PairwiseBilinear) then holds an intermediate of n x L x (D + 1) x R floats and, while
it adds its bias, two score tensors of n x L x L x R, for n sentences padded to L (ROOT included), hidden size D and
R relation labels; the squared term dominates once L passes D + 1, which is the case of a machine-translation loop.
In TU-4s, 400-sentence chunks that held a one-word loop of 78 to 131 words stayed under the separate-batch
threshold, so the whole chunk was padded to the loop's length, and seven tasks were killed at 8 GB; 24 GB was
estimated to cover the worst such chunk (an extrapolation from the boundary between surviving and killed chunks,
not a measured peak). By default the stage calls the parser once per text, so a batch never holds more than one
story's sentences. The wrapper estimates the largest batch before parsing, from the units' lengths, and reports the
largest batch it met with its estimated label-scorer size, so the dry run measures the bound instead of assuming
it. A capped batch is a switch in config/stages/parse_stanza.toml, off by default: it changes batch composition,
and whether Stanza's CPU parse is identical under another batch size is unverified until the TU-4s identity test
(task 37 reparsed with the cap and compared byte for byte) has run.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from intract_features import config as config_mod
from intract_features.parse import PinError, Token, Word, file_digests, model_pin, sha256_file

IDENTITY = "identity"
# The processors whose packages carry a tier suffix (<treebank>_nocharlm, _charlm, ...); mwt packages carry none.
TIERED = ("tokenize", "pos", "lemma", "depparse")
REQUIRED = ("tokenize", "pos", "lemma", "depparse")
# Stanza's message when a pretrain file it was told to load is missing (models/common/pretrain.py).
_MISSING_PRETRAIN = "Pretrained file"
# Stanza 1.15.0's separate-batch threshold when neither the model nor the caller sets one
# (pipeline/depparse_processor.py, DEFAULT_SEPARATE_BATCH).
STANZA_DEFAULT_SEPARATE_BATCH = 150
# Pieces of a spaced text that a tokeniser keeps apart (word characters, or one other non-space character), which
# overestimate its syntactic words slightly; the pre-flight memory estimate uses them before any parse exists.
_PIECES = re.compile(r"\w+|[^\w\s]")


@dataclass(frozen=True)
class ModelFile:
    """One file the pipeline loads, with the MD5 the frozen resources.json lists for it."""

    processor: str
    package: str
    path: Path
    md5: str


def load_resources(path: Path, expected_sha256: str) -> dict:
    """Read Stanza's resources.json after checking it against its SHA-256 pin."""
    path = Path(path)
    if not path.is_file():
        raise PinError(f"Stanza resources file {path} is missing")
    got = sha256_file(path)
    if got != expected_sha256.lower():
        raise PinError(f"{path} has SHA-256 {got}, pinned {expected_sha256}")
    return json.loads(path.read_text(encoding="utf-8"))


def _mwt_stanza_would_add(lres: dict, tokenize_pkg: str) -> str | None:
    """The mwt package Stanza 1.15.0 adds by itself for this tokeniser package (resources/common.py, add_mwt)."""
    mwt = lres.get("mwt", {})
    bundle = lres.get("packages", {}).get(tokenize_pkg, {})
    if "mwt" in bundle:
        return bundle["mwt"]
    if tokenize_pkg in mwt:
        return tokenize_pkg
    if tokenize_pkg.endswith(("_nocharlm", "_charlm")):
        base = tokenize_pkg.rsplit("_", maxsplit=1)[0]
        if base in mwt:
            return base
    return None


def resolve_processors(resources: dict, lang: str, packages: dict[str, str], required_tier: str | None) -> dict:
    """Resolve each configured package to the exact package Stanza will load, and check the registered tier.

    A name is taken as a package of its processor, or else as a bundle in the language's package table (Stanza's own
    order of lookup). The lemma processor may be "identity" (Stanza's identity lemmatiser, used for Thai in the
    benchmarks). Every processor in REQUIRED must be named, and mwt must be named whenever Stanza would add it.
    """
    if lang not in resources or not isinstance(resources[lang], dict):
        raise ValueError(f"Stanza's resources.json has no language {lang!r}")
    lres = resources[lang]
    if "alias" in lres:
        raise ValueError(f"{lang!r} is an alias of {lres['alias']!r} in resources.json; name the language itself")
    bundles = lres.get("packages", {})
    out: dict[str, str] = {}
    for proc, name in packages.items():
        name = name.strip().lower()  # Stanza lower-cases package names (process_pipeline_parameters)
        if proc == "lemma" and name == IDENTITY:
            out[proc] = IDENTITY
        elif name in lres.get(proc, {}):
            out[proc] = name
        elif proc in bundles.get(name, {}):
            out[proc] = bundles[name][proc]
        else:
            raise ValueError(f"Stanza has no {proc} package {name!r} for {lang!r} in the frozen resources.json")
    missing = [p for p in REQUIRED if p not in out]
    if missing:
        raise ValueError(f"languages.toml names no Stanza package for {missing} in {lang!r}")
    if "mwt" not in out:
        added = _mwt_stanza_would_add(lres, out["tokenize"])
        if added is not None:
            raise ValueError(f"Stanza would add mwt package {added!r} for {lang!r} by itself; name it in "
                             "languages.toml")
    if required_tier:
        wrong = {p: out[p] for p in TIERED if out[p] != IDENTITY and not out[p].endswith("_" + required_tier)}
        if wrong:
            raise ValueError(f"packages outside the registered {required_tier!r} tier for {lang!r}: {wrong}")
    return out


def model_files(resources: dict, lang: str, processors: dict, model_dir: Path) -> list[ModelFile]:
    """Every file the pipeline loads for these processors, dependencies (pretrain, charlm) included.

    Paths follow Stanza's layout, <dir>/<lang>/<processor>/<package>.pt (pipeline/core.py, build_default_config).
    """
    lres = resources[lang]
    todo = [(p, pkg) for p, pkg in processors.items() if pkg != IDENTITY]
    seen, out = set(), []
    while todo:
        proc, pkg = todo.pop(0)
        if (proc, pkg) in seen:
            continue
        seen.add((proc, pkg))
        meta = lres.get(proc, {}).get(pkg)
        if not isinstance(meta, dict) or "md5" not in meta:
            raise PinError(f"resources.json lists no MD5 for {lang}/{proc}/{pkg}")
        out.append(ModelFile(proc, pkg, Path(model_dir) / lang / proc / f"{pkg}.pt", meta["md5"]))
        todo.extend((dep["model"], dep["package"]) for dep in meta.get("dependencies", []))
    return sorted(out, key=lambda f: (f.processor, f.package))


def verify_model_files(files: list[ModelFile], root: Path, sha256_pins: Mapping | None = None) -> list[dict]:
    """Check every file against its MD5 and, if `sha256_pins` is given, its SHA-256; raise PinError naming each
    missing or differing file.

    `sha256_pins` is models.lock.json's "files" table, {path relative to the model directory: {"sha256": ...}};
    once it is given, a file the pipeline loads that it does not pin is an error too. The record gives each file's
    path relative to the model directory, so run records carry no local paths.
    """
    rows, bad = [], []
    for f in files:
        rel = f.path.relative_to(root).as_posix()
        if not f.path.is_file():
            bad.append(f"{rel} is missing")
            continue
        md5, sha = file_digests(f.path)
        if md5 != f.md5:
            bad.append(f"{rel} has MD5 {md5}, expected {f.md5}")
        row = {"processor": f.processor, "package": f.package, "file": rel, "md5": md5, "bytes": f.path.stat().st_size}
        if sha256_pins is not None:
            pin = sha256_pins.get(rel)
            want = pin.get("sha256") if isinstance(pin, Mapping) else None
            if not want:
                bad.append(f"{rel} has no SHA-256 pin in models.lock.json")
            elif sha != str(want).lower():
                bad.append(f"{rel} has SHA-256 {sha}, pinned {want}")
            row["sha256"] = sha
        rows.append(row)
    if bad:
        raise PinError("Stanza model files fail their pins: " + "; ".join(bad))
    return rows


def pipeline_kwargs(lang: str, processors: dict, model_dir: Path, resources_path: Path, scfg: dict) -> dict:
    """The keyword arguments of stanza.Pipeline for the registered parse.

    package=None and explicit processors, so no default or combined model loads; use_gpu=False; no download. The
    parser batch keeps Stanza's own values unless parse_stanza.toml sets them (0 means Stanza's own).
    """
    kw = {"lang": lang, "dir": str(model_dir), "processors": dict(processors), "package": None,
          "tokenize_no_ssplit": bool(scfg["tokenize_no_ssplit"]), "use_gpu": False, "download_method": None,
          "logging_level": "WARN", "resources_filepath": str(resources_path)}
    if processors.get("lemma") == IDENTITY:
        kw["lemma_use_identity"] = True
    for key in ("depparse_batch_size", "depparse_min_length_to_batch_separately"):
        value = int(scfg["batch"][key])
        if value > 0:
            kw[key] = value
    return kw


def pos_pretrain_path(resources: dict, lang: str, processors: dict, model_dir: Path) -> Path | None:
    """The POS tagger's own pretrain file, which the Greek workaround hands to the lemmatiser; None if it has none."""
    deps = resources[lang]["pos"][processors["pos"]].get("dependencies") or []
    pretrains = [d["package"] for d in deps if d.get("model") == "pretrain"]
    return Path(model_dir) / lang / "pretrain" / f"{pretrains[0]}.pt" if pretrains else None


def build_pipeline(pipeline_cls, kwargs: dict, resources: dict, lang: str, processors: dict,
                   model_dir: Path) -> tuple[object, dict | None]:
    """Build the pipeline, applying the Greek lemmatiser workaround only when the pipeline cannot be built otherwise.

    The workaround applies only to Stanza's missing-pretrain error with a lemma model to hand a pretrain to, and only
    when the POS package declares a pretrain; any other error is raised as it is (presub stanza_compat.py). Every
    other argument is passed through unchanged. Returns the pipeline and, when the workaround applied, the path it
    used and the error that called for it.
    """
    try:
        return pipeline_cls(**kwargs), None
    except FileNotFoundError as e:
        if (_MISSING_PRETRAIN not in str(e) or processors.get("lemma") in (None, IDENTITY)
                or "lemma_pretrain_path" in kwargs):
            raise
        path = pos_pretrain_path(resources, lang, processors, model_dir)
        if path is None:
            raise
        if not path.is_file():
            raise FileNotFoundError(f"POS pretrain {path} for the lemmatiser workaround is missing") from e
        workaround = {"lemma_pretrain_path": path.relative_to(model_dir).as_posix(), "error": str(e)}
        return pipeline_cls(**{**kwargs, "lemma_pretrain_path": str(path)}), workaround


def padded_batches(word_counts: Iterable[int], batch_size: int, separate: int | None) -> list[tuple[int, int]]:
    """(sentences, padded length) of each depparse batch Stanza 1.15.0 forms from these sentences' word counts.

    Mirrors models/depparse/data.py (data_to_batches) in evaluation mode: a sentence's length counts the ROOT node
    Stanza prepends (Dataset.lengths, len(x[0])), sentences are sorted longest first, each one longer than
    `separate` by that count gets a batch of its own, and the rest are packed while a batch's summed lengths stay
    within `batch_size`. The padded length is the batch's longest length, ROOT included. Used only to report the
    padded size that drives the parser's memory.
    """
    batches: list[list[int]] = []
    current: list[int] = []
    used = 0
    for n in sorted((w + 1 for w in word_counts), reverse=True):
        if separate is not None and n > separate:
            if current:
                batches.append(current)
                current, used = [], 0
            batches.append([n])
            continue
        if current and n + used > batch_size:
            batches.append(current)
            current, used = [], 0
        current.append(n)
        used += n
    if current:
        batches.append(current)
    return [(len(b), max(b)) for b in batches]


def label_scorer_floats(sentences: int, padded: int, hidden: int, relations: int) -> int:
    """Floats the label scorer holds at its peak for one batch: n L (D + 1) R + 2 n L^2 R.

    models/common/biaffine.py, PairwiseBilinear.forward: the intermediate einsum gives n x L x (D + 1) x R, the
    second einsum n x L x L x R, and adding the bias makes another tensor of that size while both exist. L is the
    padded length with ROOT, D the hidden size of the scorer (deep_biaff_hidden_dim) and R the relation labels. A
    lower bound on the parser's peak: einsum's own temporaries and the rest of the model come on top.
    """
    return sentences * padded * (hidden + 1) * relations + 2 * sentences * padded * padded * relations


def word_proxy(text: str, spaced: bool) -> int:
    """An overestimate of a unit's syntactic words before it is parsed, for the pre-flight memory estimate.

    Spaced scripts: word-character runs and single other characters; unspaced scripts: non-space characters.
    """
    return len(_PIECES.findall(text)) if spaced else sum(1 for c in text if not c.isspace())


def _field(value: object) -> str:
    return "_" if value is None or value == "" else str(value)


def to_tokens(sentence) -> list[Token]:
    """Tokens and words of one Stanza sentence, with the fields TU-4s wrote (None becomes "_", a missing head 0)."""
    tokens = []
    for t in sentence.tokens:
        words = [Word(id=int(w.id), form=w.text, lemma=_field(w.lemma), upos=_field(w.upos), xpos=_field(w.xpos),
                      feats=_field(w.feats), head=int(w.head) if w.head is not None else 0, deprel=_field(w.deprel))
                 for w in t.words]
        tokens.append(Token(form=t.text, words=words))
    return tokens


def _env_dir(name: str) -> Path:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"${name} is not set; it must name the directory that holds the Stanza models")
    return Path(value)


class StanzaParser:
    """A verified Stanza pipeline and the statistics of what it parsed.

    parse() takes the registered sentences of one parser call and returns one token list per sentence, or None
    where Stanza returned no sentence for it.
    """

    def __init__(self, nlp, info: dict, *, lemma_identity: bool = False):
        self.nlp = nlp
        self.info = info
        self.lemma_identity = lemma_identity
        self.calls = self.fallback_calls = self.sentences = self.words = self.lemma_missing = 0
        self.max_batch: dict = {"sentences": 0, "padded_length": 0, "estimated_label_scorer_mb": None}
        self._max_rank = -1
        dep = info.get("effective_depparse") or {}
        self._batch_size = dep.get("batch_size")
        self._separate = dep.get("min_length_to_batch_separately")
        self._hidden = dep.get("deep_biaff_hidden_dim")
        self._relations = dep.get("relations")

    @classmethod
    def from_config(cls, cfg: dict, lang: str, *, stage: str = "parse_stanza",
                    model_dir: Path | None = None) -> StanzaParser:
        """Verify the pins and build the pipeline for one served language from the merged configuration."""
        scfg = cfg["stages"][stage]
        lcfg = config_mod.language(cfg, lang)
        pin = model_pin(cfg, scfg["models_lock_key"])
        import stanza  # lazy: unit tests run without it

        version = scfg["stanza_version"]
        if stanza.__version__ != version or pin.get("version", version) != version:
            raise PinError(f"Stanza {stanza.__version__} is installed and {pin.get('version')} pinned; S3 registers "
                           f"Stanza {version}")
        model_dir = Path(model_dir) if model_dir else _env_dir(scfg["model_dir_env"])
        resources_path = model_dir / "resources.json"
        resources = load_resources(resources_path, pin["resources_json_sha256"])
        slang = lcfg["stanza_lang"]
        processors = resolve_processors(resources, slang, lcfg["stanza_packages"], scfg["required_tier"])
        sha_pins = pin.get("files")
        verified = verify_model_files(model_files(resources, slang, processors, model_dir), model_dir,
                                      sha_pins if isinstance(sha_pins, Mapping) else None)
        threads = _set_torch_threads(int(scfg["torch_threads"]))
        kwargs = pipeline_kwargs(slang, processors, model_dir, resources_path, scfg)
        nlp, workaround = build_pipeline(stanza.Pipeline, kwargs, resources, slang, processors, model_dir)
        info = {
            "stanza": stanza.__version__, "lang": slang, "requested_packages": dict(lcfg["stanza_packages"]),
            "processors": processors, "resources_json_sha256": pin["resources_json_sha256"],
            "model_files_verified": verified, "model_files_sha256_pinned": isinstance(sha_pins, Mapping),
            "lemma_pretrain_workaround": workaround,
            "pipeline_kwargs": {k: v for k, v in kwargs.items() if k not in ("dir", "resources_filepath")},
            "effective_depparse": effective_depparse(nlp), **threads,
        }
        return cls(nlp, info, lemma_identity=processors["lemma"] == IDENTITY)

    def parse(self, texts: list[str]) -> list[list[Token] | None]:
        """Parse the sentences of one call at once, falling back to one call per sentence on a count mismatch.

        A paragraph can yield no sentence (TU-4s met symbol-only lines), which would shift every later sentence; the
        fallback keeps None for it, as TU-4s kept an empty parse. A sentence split in two is an error.
        """
        self.calls += 1
        sents = list(self.nlp("\n\n".join(texts)).sentences)
        calls = [sents]
        if len(sents) != len(texts):
            self.fallback_calls += 1
            sents, calls = [], []
            for text in texts:
                one = list(self.nlp(text).sentences)
                if len(one) > 1:
                    raise RuntimeError(f"Stanza split one registered sentence into {len(one)}: {text[:80]!r}")
                sents.append(one[0] if one else None)
                calls.append(one)
        out = [to_tokens(s) if s is not None else None for s in sents]
        self._tally(out, calls)
        return out

    def _batch_rank(self, n: int, padded: int) -> tuple[int, float | None]:
        """A batch's rank by its estimated label-scorer floats (n L^2 when the sizes are unknown), and its MB."""
        if self._hidden and self._relations:
            floats = label_scorer_floats(n, padded, int(self._hidden), int(self._relations))
            return floats, floats * 4 / 2**20
        return n * padded * padded, None

    def _largest(self, word_counts_per_call: Iterable[list[int]]) -> tuple[int, dict]:
        best, out = -1, {"sentences": 0, "padded_length": 0, "estimated_label_scorer_mb": None}
        for counts in word_counts_per_call:
            for n, padded in padded_batches(counts, int(self._batch_size), self._separate):
                rank, mb = self._batch_rank(n, padded)
                if rank > best:
                    best, out = rank, {"sentences": n, "padded_length": padded, "estimated_label_scorer_mb": mb}
        return best, out

    def _tally(self, parses: list[list[Token] | None], calls: list[list]) -> None:
        for toks in parses:
            if not toks:
                continue
            self.sentences += 1
            for w in (w for t in toks for w in t.words):
                self.words += 1
                self.lemma_missing += (w.lemma != w.form) if self.lemma_identity else w.lemma == "_"
        if self._batch_size:
            rank, batch = self._largest([len(s.words) for s in call] for call in calls)
            if rank > self._max_rank:
                self._max_rank, self.max_batch = rank, batch

    def preflight(self, calls: Iterable[list[str]], *, spaced: bool) -> dict:
        """The largest parser batch these calls should form, estimated from their sentences before any parse.

        Lengths are word_proxy() overestimates, so the estimate errs high. The stage prints it before parsing, so a
        job that runs out of memory on one long unit leaves its estimate in the log.
        """
        if not self._batch_size:
            return {"estimated": False, "reason": "the parser's batch size is unknown"}
        _, batch = self._largest([word_proxy(t, spaced) for t in texts] for texts in calls)
        return {"estimated": True, "word_proxy": "pieces" if spaced else "characters", **batch}

    def lemma_missing_share(self) -> float:
        """Share of syntactic words without a lemma (identity lemmatiser: whose lemma differs from the form)."""
        return self.lemma_missing / max(self.words, 1)

    def stats(self) -> dict:
        """Parse statistics for the run record, with the largest padded parser batch and its estimated size."""
        return {"calls": self.calls, "fallback_calls": self.fallback_calls, "sentences": self.sentences,
                "words": self.words, "lemma_missing": self.lemma_missing,
                "lemma_missing_share": self.lemma_missing_share(), "max_padded_batch": dict(self.max_batch)}


def effective_depparse(nlp) -> dict:
    """The parser batch settings the built pipeline actually uses, read from its depparse processor.

    The batch size comes from the model file unless overridden, so the run record states the value instead of the
    5,000-word training default the presub report assumed.
    """
    proc = (getattr(nlp, "processors", None) or {}).get("depparse")
    conf = getattr(proc, "config", None) or {}
    relations = None
    if hasattr(proc, "get_known_relations"):
        try:
            relations = len(proc.get_known_relations())
        except Exception:  # a diagnostic must not stop the parse
            relations = None
    separate = conf.get("min_length_to_batch_separately")
    if separate is None and proc is not None:
        separate = STANZA_DEFAULT_SEPARATE_BATCH
    return {"batch_size": conf.get("batch_size"), "min_length_to_batch_separately": separate,
            "relations": relations, "deep_biaff_hidden_dim": conf.get("deep_biaff_hidden_dim")}


def _set_torch_threads(threads: int) -> dict:
    """Fix torch's intra-op threads (one in every presub Stanza run) and report the versions for the run record."""
    import torch  # lazy

    torch.set_num_threads(threads)
    return {"torch": getattr(torch, "__version__", None), "threads": torch.get_num_threads()}
