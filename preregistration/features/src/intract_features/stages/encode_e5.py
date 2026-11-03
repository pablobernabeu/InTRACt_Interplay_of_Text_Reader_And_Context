"""Stage encode_e5: adjacent-sentence similarity under multilingual-e5-large-instruct, the ReferentialContinuity anchor.

S3, Table 3: "multilingual-E5-large-instruct, identified by checkpoint, [...] and prompted with its developers'
instruction for semantic similarity on both sentences of a pair". qmd Outcome-blind dimension reduction: "For
ReferentialContinuity, they are adjacent-sentence similarity, referential overlap and the densities of causal and
contrastive connectives."

Reads ``documents`` and ``segments`` (the registered sentences of each text, checked against the text's hash) and
writes ``encode_e5``: one record per document whose ``values`` hold ``adjacent_similarity``, the mean cosine of its
adjacent sentences (None for a text with fewer than two), and whose ``diagnostics`` hold the per-pair cosines and
counts. Embeddings are not stored. The encoder is loaded from a folder verified against config/models.lock.json,
unless ``ctx.extra["encoder"]`` supplies an object with ``encode(texts)``, which is how the unit tests run the stage
without torch. encode_bgem3 runs the same loop with its own configuration.
"""

from __future__ import annotations

from intract_features.cli import Stage, StageContext
from intract_features.features import similarity, surprisal

STAGE = Stage(name="encode_e5", inputs=("documents", "segments"), outputs=("encode_e5",), device="gpu", env="core",
              description="adjacent-sentence similarity, multilingual-e5-large-instruct (anchor), fp32")


def run_encoder(ctx: StageContext, stage: Stage) -> dict:
    """The loop both encoder stages share: read, encode by groups of documents, write, and count."""
    cfg = ctx.stage_config()
    settings = similarity.EncoderSettings.from_config(cfg)
    rules = similarity.SegmentRules.from_config(cfg)
    models_lock = ctx.config.get("models", {})
    key = cfg["model"]["key"]
    encoder = ctx.extra.get("encoder")
    runtime_state: dict = {}
    if encoder is None:
        runtime_state = surprisal.configure_torch({**cfg["precision"], **cfg["runtime"],
                                                   "seed": ctx.config.get("seeds", {}).get("base")})
        encoder = similarity.load_encoder(key, settings, models_lock)
    # A shard's segmentation, without the candidate probabilities that only the union search reads.
    segs = {rec["story_id"]: similarity.segmentation_from_record(rec) for rec in ctx.read("segments")}
    tally: dict = {}
    timers: dict = {}
    label = surprisal.pin_label(models_lock, key)
    out = cfg["output"]
    records_iter = similarity.similarity_records(
        ctx.documents(), segs.get, encoder, value_name=cfg["model"]["value_name"], label=label, rules=rules,
        strict=bool(cfg["stage"]["strict"]), docs_per_group=int(cfg["stage"]["docs_per_group"]),
        decimals=int(out["decimals"]) if out.get("decimals") is not None else None, tally=tally, timers=timers)
    written = ctx.write(stage.outputs[0], records_iter)
    counts = dict(tally)
    counts["documents"] = written
    for attr in ("tokens", "padded_positions", "forward_calls", "truncated", "unique_texts"):
        if hasattr(encoder, attr):
            counts[attr] = getattr(encoder, attr)
    counts.update({f"seconds_{k}": round(v, 3) for k, v in timers.items()})
    counts["models"] = {stage.name: label}
    if runtime_state:
        counts["runtime"] = runtime_state
    return counts


def run(ctx: StageContext) -> dict:
    """Compute the anchor similarity of every document of the shard; return the counts for the timing record."""
    return run_encoder(ctx, STAGE)
