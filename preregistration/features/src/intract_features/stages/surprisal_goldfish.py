"""Stage surprisal_goldfish: corrected word surprisal under the Goldfish models on every document of a shard.

The 1 GB tier gives the LexicalDifficulty anchor (S3, Table 3: "Goldfish, one GPT-2 model per language
(`goldfish-models/<lang>_1000mb`, ...)") and the 100 MB tier the registered sensitivity refit (qmd Sensitivity
analyses: "Surprisal comes from the 100 MB tier of the same language models in another"). Both tiers score each group
of documents in turn, so a shard is read once and every record holds both. Goldfish always runs in fp32 (plan v3).

Reads ``documents`` (and, if [names] source is "artefact", the per-word name flags of another stage's artefact) and
writes ``surprisal_goldfish``: one record per document whose ``values`` hold ``mean_surprisal`` (the registered mean,
names excluded; None until a name mask is applied) and ``mean_surprisal_all_words``, with the same two for the
100 MB tier, and whose ``diagnostics`` hold, per tier, the counts S3 reports and the per-word corrected surprisals
(features/surprisal.py). The models are loaded from folders verified against config/models.lock.json, unless
``ctx.extra["scorers"]`` supplies a Scorer per tier, which is how the unit tests run the stage without torch.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from intract_features import config as config_mod
from intract_features.cli import Stage, StageContext
from intract_features.features import surprisal

STAGE = Stage(name="surprisal_goldfish", inputs=("documents",), outputs=("surprisal_goldfish",), device="gpu",
              env="core", description="corrected word surprisal, Goldfish 1 GB (anchor) and 100 MB tiers, fp32")


def openers_for(cfg: Mapping, lang_cfg: Mapping) -> frozenset[str]:
    """The opening quotation marks that attach a punctuation-only token to the following word ([text] openers)."""
    rule = cfg["text"]["attach_punctuation"]
    if rule != "word_extents":
        raise ValueError(f"text.attach_punctuation must be 'word_extents', not {rule!r}")
    openers = cfg["text"]["openers"]
    if openers == "quote_pairs":
        return surprisal.opening_marks(lang_cfg.get("quotes", ()))
    return frozenset(openers)


def name_source(ctx: StageContext, cfg: Mapping) -> tuple[Callable[[str], Sequence[bool] | None], str]:
    """A lookup of each document's per-word name flags, and a description of where they come from.

    qmd Materials: names are excluded "from the mean" of surprisal. The rule that decides them awaits P06 and P53, so
    with source "none" no mask is applied and the stored per-word values wait for it. With "artefact", the flags are
    read from ``diagnostics[field]`` of each record of the named artefact, as the indices of the registered words that
    are names.
    """
    ncfg = cfg["names"]
    source = ncfg["source"]
    if source == "none":
        return (lambda _sid: None), "none"
    if source != "artefact":
        raise ValueError(f"names.source must be 'none' or 'artefact', not {source!r}")
    field = ncfg["field"]
    flags: dict[str, list[int] | None] = {}
    words: dict[str, int] = {}
    for rec in ctx.read(ncfg["artefact"]):
        diag = rec.get("diagnostics") or {}
        flags[rec["story_id"]] = diag.get(field)
        words[rec["story_id"]] = diag.get("words")

    def lookup(story_id: str) -> Sequence[bool] | None:
        idx = flags.get(story_id)
        n = words.get(story_id)
        if idx is None or n is None:
            return None
        mask = [False] * int(n)
        for i in idx:
            mask[int(i)] = True
        return mask

    return lookup, f"artefact:{ncfg['artefact']}:{field}"


def run(ctx: StageContext) -> dict:
    """Score every document of the shard with both tiers and return the counts for the timing record."""
    cfg = ctx.stage_config()
    lang_cfg = config_mod.language(ctx.config, ctx.lang)
    out = surprisal.OutputSettings.from_config(cfg)
    settings = surprisal.ModelSettings.from_config(cfg)
    if settings.mode != "fp32":
        raise ValueError("Goldfish always runs in fp32 (plan v3); only XGLM-4.5B may move to bf16")
    tiers = list(cfg["models"]["tiers"])
    repos = {tier: lang_cfg["goldfish"][tier] for tier in tiers}
    models_lock = ctx.config.get("models", {})
    injected = ctx.extra.get("scorers")
    runtime_state: dict = {}
    if injected is None:
        runtime_state = surprisal.configure_torch({**cfg["precision"], **cfg["runtime"],
                                                   "seed": ctx.config.get("seeds", {}).get("base")})
        scorers = {tier: surprisal.load_scorers(repos[tier], settings, models_lock, ["fp32"])["fp32"]
                   for tier in tiers}
    else:
        scorers = {tier: injected[tier] for tier in tiers}
    names_for, names_desc = name_source(ctx, cfg)
    tally: dict = {}
    timers: dict = {}
    records_iter = surprisal.score_documents(
        ctx.documents(), scorers, value_names=cfg["models"]["value_names"],
        labels={tier: surprisal.pin_label(models_lock, repos[tier]) for tier in tiers},
        openers=openers_for(cfg, lang_cfg), out=out, names_for=names_for, tally=tally, timers=timers)
    written = ctx.write(STAGE.outputs[0], records_iter)
    counts = dict(tally)
    counts["documents"] = written
    counts["tokens"] = counts.get(f"tokens_{tiers[0]}", 0)
    counts.update({f"seconds_{k}": round(v, 3) for k, v in timers.items()})
    for tier, sc in scorers.items():
        for attr in ("forward_calls", "positions_computed"):
            if hasattr(sc.backend, attr):
                counts[f"{attr}_{tier}"] = getattr(sc.backend, attr)
        counts[f"active_replacements_{tier}"] = "".join(sorted(sc.active))
    counts["names"] = names_desc
    counts["models"] = {tier: surprisal.pin_label(models_lock, repos[tier]) for tier in tiers}
    if runtime_state:
        counts["runtime"] = runtime_state
    return counts
