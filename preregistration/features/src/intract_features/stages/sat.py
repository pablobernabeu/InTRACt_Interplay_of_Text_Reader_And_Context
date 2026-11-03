"""Stage sat: the registered Segment any Text call on every document of a shard.

Reads ``documents`` and writes ``segments`` (schema in ``intract_features.segment``). In English the
sentences are the registered segmentation (Materials, the segmentation paragraph). In a translation
they are SaT alone, the union segmenter's input and the fallback that the segmentation checks can
impose (Outcome-neutral quality checks), and the stored p' values feed the union search.

The model is loaded from verified snapshots unless ``ctx.extra["sat_backend"]`` supplies an object with
wtpsplit's ``predict_proba``, which is how the unit tests run the stage without torch.

The stage reads ``Document.text`` as the documents stage normalised it and does not normalise again:
S3 normalises "once", and a second pass could change a text whose deleted joiner left a base letter
and a combining mark uncomposed (text/normalise.py).
"""

from __future__ import annotations

from itertools import batched

from intract_features.cli import Stage, StageContext
from intract_features.segment import SENTENCE_FIELDS, page_anchors
from intract_features.segment import diagnostics as diag
from intract_features.segment import sat as sat_mod

STAGE = Stage(name="sat", inputs=("documents",), outputs=("segments",), device="gpu", env="core",
              description="registered SaT sentence boundaries (sat-12l-sm, wtpsplit 2.2.2) and p' at candidates")


def _record(doc, text: str, seg: sat_mod.SegmentedText, settings: sat_mod.SatSettings, is_source: bool,
            floor_min: int) -> dict:
    anchors = page_anchors(doc.page_spans(), seg.spans)
    rec = {
        "story_id": doc.story_id,
        "lang": doc.lang,
        "segmenter": "sat",
        "is_source": is_source,
        "text_sha256": sat_mod.text_sha256(text),
        "n_characters": len(text),
        "n_sentences": len(seg.spans),
        "sentence_fields": list(SENTENCE_FIELDS),
        "sentences": [[a, b, ps, pe] for (a, b), (ps, pe) in zip(seg.spans, anchors, strict=True)],
        "newline_forced": seg.newline_forced,
    }
    if settings.store_candidates:
        rec["candidates"] = {"pos": seg.candidate_pos, "p": seg.candidate_p}
    if is_source:
        # Outcome-blind dimension reduction: the English source's count decides the floor in every language.
        rec["floor"] = {"min_english_sentences": floor_min,
                        "excluded": diag.floor_excluded(len(seg.spans), floor_min)}
    return rec


def run(ctx: StageContext) -> dict:
    """Segment every document of the shard and return the counts for the timing record."""
    from intract_features.text.words import count_words  # the registered word function, for the cost per word

    scfg = ctx.stage_config()
    settings = sat_mod.SatSettings.from_config(scfg)
    runtime = sat_mod.RuntimeSettings.from_config(scfg)
    floor_min = int(ctx.config["floor"]["min_english_sentences"])
    is_source = ctx.lang == scfg["floor"]["source_lang"]
    backend = ctx.extra.get("sat_backend") or sat_mod.load_backend(scfg, ctx.config.get("models", {}))
    tally = {"documents": 0, "characters": 0, "words": 0, "whitespace_tokens": 0, "sentences": 0, "candidates": 0,
             "newline_forced": 0, "cross_page_sentences": 0, "model_calls": 0}
    if is_source:
        tally["below_floor"] = 0
    count_tokens = runtime.count_tokens and hasattr(backend, "tokenizer")
    if count_tokens:
        tally["tokens"] = 0
        tally["chunks"] = 0

    def produce():
        for group in batched(ctx.documents(), runtime.texts_per_call):
            texts = [d.text for d in group]
            probs = sat_mod.predict(backend, texts, settings, runtime)
            tally["model_calls"] += 1
            if count_tokens:
                for n in sat_mod.count_tokens(backend, texts):
                    tally["tokens"] += n
                    tally["chunks"] += sat_mod.chunks_for(n, settings)
            for d, t, p in zip(group, texts, probs, strict=True):
                seg = sat_mod.segment_text(t, p, settings)
                rec = _record(d, t, seg, settings, is_source, floor_min)
                tally["documents"] += 1
                tally["characters"] += len(t)
                tally["words"] += count_words(t)
                tally["whitespace_tokens"] += len(t.split())
                tally["sentences"] += rec["n_sentences"]
                tally["candidates"] += len(seg.candidate_pos)
                tally["newline_forced"] += len(seg.newline_forced)
                tally["cross_page_sentences"] += sum(row[2] != row[3] for row in rec["sentences"])
                if is_source:
                    tally["below_floor"] += rec["floor"]["excluded"]
                yield rec

    ctx.write("segments", produce())
    return tally
