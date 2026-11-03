"""Stage surprisal_xglm: corrected word surprisal under XGLM-4.5B, the single-multilingual-model contrast.

S3, Table 3: "XGLM-4.5B (`facebook/xglm-4.5B`, 4.5 billion parameters, MIT licence) [...] is the
single-multilingual-model contrast in all 19 languages"; qmd Sensitivity analyses: surprisal comes "from the
multilingual XGLM-4.5B model in a third" refit. Plan v3: "each whole text scored after the model's start token in
fp32, using its 2,048-token context with a stride fallback for longer texts. The word, name, unknown-character and
Traditional Chinese rules are the same, and the boundary set is the pieces beginning with U+2581 plus the
end-of-sequence token."

The model runs in fp32. Under the budget guard (qmd Timeline) it may run "with 16-bit (bf16) weights and 32-bit
log-probabilities", which is accepted "only if their text means agree with those at full precision at r >= .995 on
the public benchmark scored before submission". With [precision] mode "bf16", documents whose keyed fraction lies
below check_fraction are scored at both precisions, each record holds the fp32 means beside the bf16 ones, and the
timing record carries the agreement on this shard (features.surprisal.precision_agreement). The public-benchmark
check runs with check_fraction = 1.

Reads ``documents`` and writes ``surprisal_xglm``, with ``mean_surprisal_xglm`` and ``mean_surprisal_xglm_all_words``
as values; everything else follows surprisal_goldfish. ``ctx.extra["scorers"]`` may supply {"xglm": Scorer} and, for
the check, ``ctx.extra["check_scorers"]`` {"xglm": Scorer}, which is how the unit tests run the stage without torch.
"""

from __future__ import annotations

from intract_features import config as config_mod
from intract_features.cli import Stage, StageContext
from intract_features.features import surprisal
from intract_features.stages.surprisal_goldfish import name_source, openers_for

STAGE = Stage(name="surprisal_xglm", inputs=("documents",), outputs=("surprisal_xglm",), device="gpu", env="core",
              description="corrected word surprisal, XGLM-4.5B contrast (fp32; bf16 only with its fp32 check)")

MODEL = "xglm"


def run(ctx: StageContext) -> dict:
    """Score every document of the shard and return the counts for the timing record."""
    cfg = ctx.stage_config()
    lang_cfg = config_mod.language(ctx.config, ctx.lang)
    out = surprisal.OutputSettings.from_config(cfg)
    settings = surprisal.ModelSettings.from_config(cfg)
    key = cfg["model"]["key"]
    models_lock = ctx.config.get("models", {})
    fraction = float(cfg["precision"]["check_fraction"]) if settings.mode != "fp32" else 0.0
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("precision.check_fraction must lie in [0, 1]")
    modes = [settings.mode] + (["fp32"] if fraction > 0 else [])
    injected = ctx.extra.get("scorers")
    runtime_state: dict = {}
    if injected is None:
        runtime_state = surprisal.configure_torch({**cfg["precision"], **cfg["runtime"],
                                                   "seed": ctx.config.get("seeds", {}).get("base")})
        loaded = surprisal.load_scorers(key, settings, models_lock, modes)
        scorers = {MODEL: loaded[settings.mode]}
        checks = {MODEL: loaded["fp32"]} if fraction > 0 else None
    else:
        scorers = {MODEL: injected[MODEL]}
        checks = ctx.extra.get("check_scorers") if fraction > 0 else None
    keys = ctx.config.get("keys", {})
    purpose = cfg["precision"]["check_key_purpose"]

    def selected(story_id: str) -> bool:
        return surprisal.keyed_fraction(story_id, purpose, keys) < fraction

    names_for, names_desc = name_source(ctx, cfg)
    tally: dict = {}
    timers: dict = {}
    pairs: dict[str, list] = {}
    label = surprisal.pin_label(models_lock, key) + ("" if settings.mode == "fp32" else f" ({settings.mode})")
    records_iter = surprisal.score_documents(
        ctx.documents(), scorers, value_names={MODEL: cfg["model"]["value_name"]}, labels={MODEL: label},
        openers=openers_for(cfg, lang_cfg), out=out, names_for=names_for, tally=tally, timers=timers,
        checks=checks, check_selected=selected if checks else None, check_pairs=pairs)
    written = ctx.write(STAGE.outputs[0], records_iter)
    counts = dict(tally)
    counts["documents"] = written
    counts["tokens"] = counts.get(f"tokens_{MODEL}", 0)
    counts.update({f"seconds_{k}": round(v, 3) for k, v in timers.items()})
    backend = scorers[MODEL].backend
    for attr in ("forward_calls", "positions_computed"):
        if hasattr(backend, attr):
            counts[f"{attr}_{MODEL}"] = getattr(backend, attr)
    counts[f"active_replacements_{MODEL}"] = "".join(sorted(scorers[MODEL].active))
    counts["precision"] = settings.mode
    if checks:
        counts["precision_check"] = surprisal.precision_agreement(pairs.get(MODEL, []),
                                                                  float(cfg["precision"]["agreement_threshold"]))
    counts["names"] = names_desc
    counts["models"] = {MODEL: label}
    if runtime_state:
        counts["runtime"] = runtime_state
    return counts
