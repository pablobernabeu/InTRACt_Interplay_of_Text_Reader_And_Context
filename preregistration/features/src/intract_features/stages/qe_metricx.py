"""Stage qe_metricx: MetricX-24-Hybrid-XL reference-free quality estimates of page pairs (GPU, environment core).

Sensitivity analyses, ninth family (preregistration.qmd): "Translation quality is estimated for every translated page
against its English source by MetricX-24 in its reference-free mode [...]. A text's value is the word-weighted mean
over its pages." The scorer is the validated port in reference/metricx_qe.py, whose module docstring records why the
official code is not run here. The port runs in the core environment, whose torch and transformers releases it is
validated with; envs/metricx holds the official code's pins for the one-off validation run (tests/gpu).

The stage reads --input, a JSON Lines file (optionally gzipped) of pairs, because the English dry run has no
translations of the stand-in; the dry run times it on the translated benchmark's MADLAD-400 and NLLB-200 outputs:

    {"pair_id": "...", "src": "<English page>", "mt": "<its translation>",
     "story_id": "...", "page": 3, "words": 41, "lang": "de-de"}        <- optional fields

A pair without story_id is a text of one page. Pages of a story are grouped and scored, and the story falls in the
shard of its id, as every other artefact's stories do. Rows whose `lang` differs from --lang are skipped and counted.

The catalogue lock (lock.py) checks the input file, then every story's English and translated pages as delivered,
under each reading lock.check_text knows, before any page is normalised or reaches the model, so story texts cannot
be scored through this stage before in-principle acceptance. Each page is then normalised as every text is at load
time (S3), unless [input] normalise is false.

A page's weight in its text's mean follows [output] page_weight (PENDING the Feature Specification):
"translation_words", the registered word count of the translated page or the row's `words` when given (Chinese and
Thai need the segmenter's words, P81), or "source_words", the registered word count of the English page.

Writes `qe_metricx`, one record per text:

    {"story_id", "lang", "values": {"metricx_qe": <word-weighted mean or null>},
     "pages": [{"pair_id", "page", "words", "qe", "tokens", "at_limit"}, ...], "diagnostics": {...}}
"""

from __future__ import annotations

import importlib.metadata
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path

from intract_features import records
from intract_features.cli import Stage, StageContext
from intract_features.lock import DEFAULT_CONFIG_DIR, CatalogueLock
from intract_features.reference import (
    PinError,
    TorchRuntime,
    model_pin,
    pinned_folder,
    verify_pinned_files,
)
from intract_features.reference import metricx_qe as mq
from intract_features.text.keyed import key_settings
from intract_features.text.normalise import FORM, FORMAT_CHARACTER_RANGES, Normaliser
from intract_features.text.words import count_words

STAGE = Stage(name="qe_metricx", inputs=(), outputs=("qe_metricx",), device="gpu", env="core",
              description="MetricX-24-Hybrid-XL reference-free QE of --input page pairs, word-weighted per text")

PAGE_WEIGHTS = ("translation_words", "source_words")


@dataclass
class Pair:
    """One input row after validation; src and mt stay as delivered until the lock has seen them."""

    pair_id: str
    src: str
    mt: str
    story_id: str
    page: int | None
    words: float | None
    order: int


def _optional_number(row: dict, key: str, where: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    # json.loads accepts NaN and Infinity, and NaN passes a plain "< 0" test, so finiteness is checked first.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{where}: {key!r} must be a finite non-negative number, not {value!r}")
    return value


def read_pairs(path: Path, lang: str) -> tuple[list[Pair], int]:
    """Validate the input rows; return the pairs for `lang`, texts as delivered, and the rows skipped for another
    language."""
    pairs, seen, skipped = [], set(), 0
    for n, row in enumerate(records.read_jsonl(path), 1):
        where = f"{Path(path).name}, row {n}"
        if not isinstance(row, dict):
            raise ValueError(f"{where}: not a JSON object")
        if row.get("lang") not in (None, lang):
            skipped += 1
            continue
        for key in ("pair_id", "src", "mt"):
            if not isinstance(row.get(key), str):
                raise ValueError(f"{where}: {key!r} must be a string")
        pair_id = row["pair_id"]
        if not pair_id or pair_id in seen:
            raise ValueError(f"{where}: pair_id {pair_id!r} is empty or repeated")
        seen.add(pair_id)
        story_id = row.get("story_id", pair_id)
        if not isinstance(story_id, str) or not story_id:
            raise ValueError(f"{where}: story_id must be a non-empty string")
        page = row.get("page")
        if page is not None and (isinstance(page, bool) or not isinstance(page, int)):
            raise ValueError(f"{where}: page must be an integer")
        pairs.append(Pair(pair_id=pair_id, src=row["src"], mt=row["mt"], story_id=story_id, page=page,
                          words=_optional_number(row, "words", where), order=n))
    return pairs, skipped


def group_texts(pairs: list[Pair]) -> list[list[Pair]]:
    """Pages grouped by story, stories in order of first appearance, pages by page index (else input order)."""
    groups: dict[str, list[Pair]] = {}
    for p in pairs:
        groups.setdefault(p.story_id, []).append(p)
    out = []
    for story_id, pages in groups.items():
        indexed = [p.page for p in pages if p.page is not None]
        if len(set(indexed)) != len(indexed):
            raise ValueError(f"story {story_id!r} repeats a page index")
        if indexed and len(indexed) != len(pages):
            raise ValueError(f"story {story_id!r} gives a page index for some pages only")
        out.append(sorted(pages, key=lambda p: (p.page if p.page is not None else p.order, p.order)))
    return out


def page_weight(pair: Pair, rule: str) -> float:
    """A page's weight in its text's word-weighted mean under [output] page_weight (normalised texts)."""
    if rule == "source_words":
        return count_words(pair.src)
    return count_words(pair.mt) if pair.words is None else pair.words


def load_lock(ctx: StageContext) -> CatalogueLock:
    """The catalogue lock, evaluated from the documents stage's [lock] settings (lock.py)."""
    config_dir = Path(ctx.extra.get("config_dir", DEFAULT_CONFIG_DIR))
    return CatalogueLock.load(config_dir, ctx.config["stages"]["documents"]["lock"])


def check_versions(wanted: dict) -> dict:
    """The installed torch and transformers versions, each checked against the prefix the port was validated with."""
    have, bad = {}, []
    for package, prefix in wanted.items():
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            bad.append(f"{package} is not installed")
            continue
        have[package] = version
        if version != prefix and not version.split("+")[0].startswith(prefix + "."):
            bad.append(f"{package} {version} is installed, {prefix}.* validated")
    if bad:
        raise PinError("the environment differs from the one the port is validated in: " + "; ".join(bad))
    return have


def build_scorer(config: dict, scfg: dict, settings: mq.QESettings) -> mq.QEScorer:
    """Verify the checkpoint and the tokeniser against config/models.lock.json, then load both.

    Verification (hashing 15 GB of weights) and loading are timed apart from scoring, as setup that a shard pays once,
    so the dry run can project the scoring alone.
    """
    t0 = time.perf_counter()
    m = scfg["model"]
    model_entry = model_pin(config, m["metricx"])
    model_dir = pinned_folder(model_entry, env_name=m["model_dir_env"])
    tok_entry = model_pin(config, m["tokenizer"])
    tok_dir = pinned_folder(tok_entry, env_name=m["tokenizer_dir_env"])
    pins = {"model": {"repo": model_entry.get("repo"), "revision": model_entry.get("revision"),
                      "licence": model_entry.get("licence"),
                      "files": verify_pinned_files(model_dir, model_entry, what="the MetricX checkpoint")},
            "tokenizer": {"repo": tok_entry.get("repo"), "revision": tok_entry.get("revision"),
                          "files": verify_pinned_files(tok_dir, tok_entry, what="the mT5 tokeniser")}}
    versions = check_versions(dict(scfg["versions"]))
    t1 = time.perf_counter()
    runtime = TorchRuntime.from_config(scfg["runtime"])
    runtime_record = runtime.apply()
    tokenizer = mq.load_tokenizer(tok_dir)
    model, device, tied = mq.load_model(model_dir, runtime, settings)
    t2 = time.perf_counter()
    return mq.QEScorer(tokenizer=tokenizer, model=model, settings=settings, device=device, rescale=tied,
                       record={"pins_verified": pins, "versions": versions, "runtime": runtime_record,
                               "device": str(device), "mode": settings.mode, "checkpoint_ties_embeddings": tied,
                               "head_dtype": str(model.lm_head.weight.dtype),
                               "setup_seconds": {"verify_pins": t1 - t0, "load": t2 - t1}})


def run(ctx: StageContext) -> dict:
    """Score one shard of the input's texts and return the counts for the timing record."""
    if ctx.input is None:
        raise ValueError("qe_metricx needs --input: a JSON Lines file of {pair_id, src, mt} pairs")
    scfg = ctx.stage_config()
    settings = mq.QESettings.from_config(scfg)
    rule = str(scfg["output"]["page_weight"])
    if rule not in PAGE_WEIGHTS:
        raise ValueError(f"[output] page_weight must be one of {PAGE_WEIGHTS}, not {rule!r}")
    lock = load_lock(ctx)
    input_record = lock.check_input(ctx.input)
    pairs, other_lang = read_pairs(ctx.input, ctx.lang)
    keys = key_settings(ctx.config)  # pipeline.toml [keys], as the documents stage shards its stories
    texts = [g for g in group_texts(pairs) if records.shard_of(g[0].story_id, ctx.nshards, **keys) == ctx.shard]
    if ctx.limit is not None:
        texts = texts[:ctx.limit]
    for pages in texts:
        story_id = pages[0].story_id
        # The pages as delivered, with no title line, under every reading the lock fingerprints (lock.py).
        lock.check_text(f"{story_id} (English pages)", "", [p.src for p in pages])
        lock.check_text(f"{story_id} (translated pages)", "", [p.mt for p in pages])
    if scfg["input"]["normalise"]:
        norm_cfg = ctx.config.get("stages", {}).get("documents", {}).get("normalise", {})
        normaliser = Normaliser(norm_cfg.get("delete_ranges", FORMAT_CHARACTER_RANGES), norm_cfg.get("form", FORM))
        texts = [[replace(p, src=normaliser(p.src), mt=normaliser(p.mt)) for p in pages] for pages in texts]
    flat = [p for pages in texts for p in pages]
    scorer = build_scorer(ctx.config, scfg, settings) if flat else None
    t0 = time.perf_counter()
    results = scorer.score([(p.src, p.mt) for p in flat]) if scorer is not None else []
    scoring_seconds = time.perf_counter() - t0
    by_id = {p.pair_id: r for p, r in zip(flat, results, strict=True)}

    stats = dict(scorer.stats) if scorer is not None else {"batches": 0, "positions": 0, "positions_real": 0,
                                                           "filler_rows": 0}
    counts = {"documents": len(texts), "pairs": len(flat), "words": 0, "whitespace_tokens": 0, "characters": 0,
              "tokens": 0, "at_limit": 0, "non_finite_pages": 0, "texts_without_value": 0,
              "rows_other_language": other_lang, **stats}
    out = []
    for pages in texts:
        page_rows = []
        for p in pages:
            r = by_id[p.pair_id]
            qe = records.finite_or_none(r.score)
            weight = page_weight(p, rule)
            page_rows.append({"pair_id": p.pair_id, "page": p.page, "words": weight, "qe": qe, "tokens": r.tokens,
                              "at_limit": r.at_limit})
            counts["words"] += weight
            counts["whitespace_tokens"] += len(p.src.split()) + len(p.mt.split())
            counts["characters"] += len(p.src) + len(p.mt)
            counts["tokens"] += r.tokens
            counts["at_limit"] += r.at_limit
            counts["non_finite_pages"] += qe is None
        mean = mq.word_weighted_mean([(row["qe"], row["words"]) for row in page_rows])
        counts["texts_without_value"] += mean is None
        out.append({"story_id": pages[0].story_id, "lang": ctx.lang,
                    "values": {"metricx_qe": records.finite_or_none(mean)}, "pages": page_rows,
                    "diagnostics": {"pages": len(page_rows), "words": sum(row["words"] for row in page_rows),
                                    "tokens": sum(row["tokens"] for row in page_rows),
                                    "at_limit": sum(row["at_limit"] for row in page_rows),
                                    "non_finite_pages": sum(row["qe"] is None for row in page_rows)}})
    ctx.write("qe_metricx", out)
    setup = scorer.record.get("setup_seconds", {}) if scorer is not None else {}
    # seconds_score is the compute timer (aggregate_timing.toml [split.timers]); setup_seconds holds the verification
    # and loading paid once per process.
    return {**counts, "page_weight": rule, "input": input_record, "lock": lock.record, "mode": settings.mode,
            "setup_seconds": setup, "seconds_score": scoring_seconds,
            "scorer": scorer.record if scorer is not None else {}}
