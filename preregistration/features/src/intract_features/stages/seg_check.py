"""Stage seg_check: English SaT against the frozen rule segmenter, and the five-sentence floor.

Outcome-neutral quality checks: "The second requires English SaT to reach an F1 of .95 against a frozen
rule segmenter on the served English texts. If either of these two checks fails, every language falls
back to SaT alone, with its noise measured." The three segmentation checks run "on the keyed sample"
(S3: "After acceptance, the three segmentation checks [...] run on the keyed sample"). The score is the
benchmark's: quote-tolerant boundary F1 with exact matching beside it, and 2,000 cluster-bootstrap
replicates over texts.

The stage also summarises the floor over every English text (Outcome-blind dimension reduction: "We
will report, per language, the distribution of sentences and of words per text and the number of texts
the minimum removes") and the S3 segmentation diagnostics, which decide nothing.

The check is defined over the whole language, so the stage reads every shard of ``documents`` and
``segments`` (``--nshards`` must match the sat run) and writes one report,
``<work>/<lang>/_checks/seg_check.json``. Only the run with ``--shard 0`` computes and writes it; any
other shard returns at once with zero counts, so an array job or the combined GPU job's loop over the
shards neither repeats the work nor races for the report, and the timing records sum to one pass. A
first pass summarises every text and collects the story identifiers, which fix the keyed sample; a
second pass scores the sampled texts, so memory holds only the sample's texts. It runs on CPU.

The keyed sample has one definition, ``config/stages/documents.toml`` [keyed_sample] with the key of
``config/pipeline.toml`` [keys]: a story is in the sample of n when it is among the n stories present
with the smallest (keyed hash, story id) (text/keyed.py). The documents stage stores each story's keyed
hash in ``meta["keyed_hash"]``; the hash is recomputed here and must agree, so a documents artefact
written under another key or purpose stops the check instead of scoring another sample.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from intract_features import records
from intract_features.cli import Stage, StageContext
from intract_features.segment import boundaries_of, rules, sentences_from_record
from intract_features.segment import diagnostics as diag
from intract_features.segment.sat import text_sha256
from intract_features.segment.union import UnionSettings

STAGE = Stage(name="seg_check", inputs=("documents", "segments"), outputs=(), device="cpu", env="core",
              description="English SaT against the frozen rule segmenter (F1 >= .95) and the five-sentence floor")

QUANTILES = (0, 1, 5, 25, 50, 75, 95, 99, 100)


def report_path(work: Path, lang: str) -> Path:
    """Where the stage writes its report."""
    return Path(work) / lang / "_checks" / "seg_check.json"


def _write_json(path: Path, obj: dict) -> None:
    # Atomic, like every artefact: a job killed mid-write leaves no report that looks complete. The temporary
    # name carries the process id, so two processes writing the report at once cannot remove each other's file.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
                       encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _pairs(ctx: StageContext):
    """(Document, segments record) pairs over every shard, each shard in document order, candidates dropped.

    ``--limit`` keeps the first K documents of each shard, as ``StageContext.documents`` does for the sat
    stage, so a smoke run of both stages covers the same texts.
    """
    for shard in range(ctx.nshards):
        segs = {}
        for rec in records.read_jsonl(records.artefact_path(ctx.work, ctx.lang, "segments", shard, ctx.nshards)):
            rec.pop("candidates", None)  # p' values are not needed here and dominate the record's size
            if rec["story_id"] in segs:
                raise ValueError(f"two segments records for {rec['story_id']!r}")
            segs[rec["story_id"]] = rec
        doc_path = records.artefact_path(ctx.work, ctx.lang, "documents", shard, ctx.nshards)
        for i, obj in enumerate(records.read_jsonl(doc_path)):
            if ctx.limit is not None and i >= ctx.limit:
                break
            doc = records.Document.from_json(obj)
            rec = segs.get(doc.story_id)
            if rec is None:
                raise ValueError(f"{doc.story_id}: no segments record in shard {shard}; rerun the sat stage")
            text = doc.text
            if rec.get("text_sha256") != text_sha256(text):
                raise ValueError(f"{doc.story_id}: the segments record was cut from another text (stale artefact)")
            if rec.get("segmenter") != "sat":
                raise ValueError(f"{doc.story_id}: the check scores SaT, not {rec.get('segmenter')!r}")
            yield doc, text, rec


COUNT_KEYS = ("documents", "characters", "words", "whitespace_tokens", "sampled_documents", "sentences",
              "report_written")


def run(ctx: StageContext) -> dict:
    """Score the keyed sample, summarise the floor and the diagnostics, and write the report (shard 0 only)."""
    from intract_features.records import keyed_hash
    from intract_features.text.keyed import key_settings
    from intract_features.text.words import words

    scfg = ctx.stage_config()
    sat_cfg = ctx.config["stages"]["sat"]
    source_lang = sat_cfg["floor"]["source_lang"]
    if ctx.lang != source_lang:
        raise ValueError(f"seg_check scores the English source ({source_lang}); {ctx.lang} is a translation")
    if ctx.shard != 0:
        # The report covers every shard (see the module docstring), so the other shards' runs have nothing to do.
        return dict.fromkeys(COUNT_KEYS, 0)
    crit = scfg["criterion"]
    if crit["score"] not in ("tolerant", "exact") or crit["statistic"] not in ("point", "lower_95"):
        raise ValueError(f"unknown criterion {crit!r}")
    scope = scfg["sample"]["scope"]
    if scope not in ("keyed_sample", "all"):
        raise ValueError(f"unknown sample scope {scope!r}")
    keyed_cfg = ctx.config["stages"]["documents"]["keyed_sample"]
    keys = key_settings(ctx.config)
    rule = rules.EnglishRule.from_config(scfg["rule"])
    quotes = frozenset(scfg["scorer"]["quotes"])
    usettings = UnionSettings.from_config(sat_cfg)
    terminal, closing = usettings.terminal_set(ctx.lang), usettings.closing_marks
    floor_min = int(ctx.config["floor"]["min_english_sentences"])

    # Pass 1: every text, for the floor and the diagnostics.
    ids, hashes, n_sent, n_words, len_words, len_chars = [], {}, [], [], [], []
    excluded = no_terminal = forced = forced_texts = cross_page = characters = stored = whitespace_tokens = 0
    for doc, text, rec in _pairs(ctx):
        sentences = sentences_from_record(rec)
        spans = [(s.start, s.end) for s in sentences]
        if doc.story_id in hashes:
            raise ValueError(f"{doc.story_id}: the story appears twice in the documents artefact")
        ids.append(doc.story_id)
        hashes[doc.story_id] = keyed_hash(keyed_cfg["purpose"], doc.story_id, **keys)
        if "keyed_hash" in doc.meta:
            if doc.meta["keyed_hash"] != hashes[doc.story_id]:
                raise ValueError(f"{doc.story_id}: meta.keyed_hash differs from the keyed hash of documents.toml "
                                 "[keyed_sample] and pipeline.toml [keys]; rerun the documents stage under this "
                                 "configuration")
            stored += 1
        characters += len(text)
        whitespace_tokens += len(text.split())  # the catalogue's unit, for the cost projection (aggregate_timing)
        n_sent.append(len(spans))
        excluded += diag.floor_excluded(len(spans), floor_min)
        anchors = [w.anchor for w in words(text)]
        n_words.append(len(anchors))
        len_words.extend(diag.words_per_span(anchors, spans))
        for a, b in spans:
            len_chars.append(diag.nonspace_length(text, a, b))
            no_terminal += not diag.ends_with_terminal(text, b, terminal, closing)
        nf = len(rec.get("newline_forced", []))
        forced += nf
        forced_texts += nf > 0
        cross_page += sum(s.page_start != s.page_end for s in sentences)

    # The keyed sample over the stories present: keyed order is (keyed hash, story id), text/keyed.py's order.
    # rank_source records whether every document carried the hash the documents stage stores (checked above).
    rank_source = "documents" if ids and stored == len(ids) else ("recomputed" if not stored else "mixed")
    ordered = sorted(ids, key=lambda sid: (hashes[sid], sid))
    size = int(keyed_cfg["size"]) if scope == "keyed_sample" else None
    chosen_ids = ordered if size is None else ordered[:size]
    wanted = set(chosen_ids)

    # Pass 2: the sampled texts only, scored in keyed order so that the bootstrap rows never depend on sharding.
    kept = {}
    for doc, text, rec in _pairs(ctx):
        if doc.story_id in wanted:
            kept[doc.story_id] = (text, boundaries_of([(s.start, s.end) for s in sentences_from_record(rec)]))
    rows_t, rows_e, per_text = [], [], []
    for sid in chosen_ids:
        text, sat_bounds = kept.pop(sid)
        rule_bounds = boundaries_of(rules.rule_spans(text, rule))
        tol, exact = diag.score_text(text, sat_bounds, rule_bounds, quotes)
        rows_t.append(tol)
        rows_e.append(exact)
        per_text.append({"story_id": sid, "tolerant": list(tol), "exact": list(exact)})

    boot = scfg["bootstrap"]
    seed, spawn = int(ctx.config["seeds"]["base"]), int(boot["spawn_key"])
    rng = diag.bootstrap_rng(seed, spawn)
    # Tolerant before exact from one stream, the order in which TU-3 drew them.
    tolerant = diag.boot_prf(rows_t, rng, int(boot["replicates"]))
    exact = diag.boot_prf(rows_e, rng, int(boot["replicates"]))
    scored = tolerant if crit["score"] == "tolerant" else exact
    value = passed = None
    if scored.get("n_texts"):
        value = scored["F1_unrounded"] if crit["statistic"] == "point" else scored["F1_ci_unrounded"][0]
        passed = value >= float(crit["min_f1"])

    wl_mean, wl_sd = diag.mean_sd(len_words)
    cl_mean, cl_sd = diag.mean_sd(len_chars)
    n_texts = len(ids)
    report = {
        "stage": "seg_check", "lang": ctx.lang, "nshards": ctx.nshards, "limit_per_shard": ctx.limit,
        "check": {
            "anchor": "preregistration.qmd, Outcome-neutral quality checks: English SaT against a frozen rule "
                      "segmenter, F1 of at least .95",
            "criterion": {"min_f1": float(crit["min_f1"]), "score": crit["score"], "statistic": crit["statistic"]},
            "value": value, "passed": passed,
            "consequence_if_failed": "every language falls back to SaT alone, with its noise measured",
            "sample": {"scope": scope, "purpose": keyed_cfg["purpose"], "size": size, "rank_source": rank_source,
                       "n_texts": len(chosen_ids)},
            "tolerant": tolerant, "exact": exact,
            "n_rule_boundaries": int(sum(r[0] + r[2] for r in rows_e)),
            "bootstrap": {"replicates": int(boot["replicates"]), "seed": f"SeedSequence({seed}, spawn_key=({spawn},))"},
            "per_text": per_text,
        },
        "floor": {
            "anchor": "Outcome-blind dimension reduction: an English source with fewer than five sentences "
                      "enters no family's solution in any language",
            "min_english_sentences": floor_min, "n_texts": n_texts, "n_excluded": excluded,
            "share_excluded": excluded / n_texts if n_texts else None,
            "sentences_per_text": ({**diag.quantiles(n_sent, QUANTILES), "mean": sum(n_sent) / n_texts}
                                   if n_texts else None),
            "words_per_text": ({**diag.quantiles(n_words, QUANTILES), "mean": sum(n_words) / n_texts}
                               if n_texts else None),
        },
        "diagnostics": {
            "anchor": "supplementary.qmd S3: per-language segmentation diagnostics, reported and deciding nothing",
            "n_sentences": len(len_words),
            "sentence_length_words": {"mean": wl_mean, "sd": wl_sd},
            "sentence_length_nonspace_characters": {"mean": cl_mean, "sd": cl_sd},
            "share_without_terminal_mark": no_terminal / len(len_chars) if len_chars else None,
            "newline_forced_boundaries": forced, "texts_with_newline_forced_boundaries": forced_texts,
            "sentences_across_a_page_break": cross_page,
        },
    }
    _write_json(report_path(ctx.work, ctx.lang), report)
    return {"documents": n_texts, "characters": characters, "words": sum(n_words),
            "whitespace_tokens": whitespace_tokens, "sampled_documents": len(chosen_ids), "sentences": len(len_words),
            "report_written": 1}
