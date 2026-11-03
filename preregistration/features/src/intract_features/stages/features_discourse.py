"""Stage features_discourse: discourse anchors, connective densities, dialogue share, names, affect and duration.

For every text it writes one record of the `features_discourse` artefact, with these registered quantities in
`values` (each defined in the module named, with its anchor):

- referential_overlap, anaphoric_continuation (features.overlap)
- causal_density, contrastive_density, causal_density_without_so (features.connectives)
- dialogue_share (features.dialogue)
- name_token_share, name_token_share_elogit, name_types_per_100_words, name_tokens_per_type (features.names)
- valence_mean, valence_sd, arousal_mean, arousal_sd, and the same four without the name exclusion, suffixed
  _with_names (features.affect)
- duration_log_seconds_per_word (features.duration)

Inputs: documents, segments (the registered sentences and their count) and parses_stanza. ReferentialContinuity
and every lexical lookup take Stanza's parse alone (config/stages/features_discourse.toml, [parse]). The name
inventory is built over the whole catalogue of the language, so by default the stage reads every shard of the parse
before it scores its own shard (Materials: "a frozen inventory"). English only in this version: the translations
use connective inventories induced after acceptance, and several lookup and word rules of other scripts are not
implemented yet.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from intract_features import config as config_mod
from intract_features import records
from intract_features.cli import Stage, StageContext
from intract_features.features import affect as aff
from intract_features.features import connectives as con
from intract_features.features import dialogue as dia
from intract_features.features import duration as dur
from intract_features.features import names as nam
from intract_features.features import overlap as ovl

STAGE = Stage(name="features_discourse", inputs=("documents", "segments", "parses_stanza"),
              outputs=("features_discourse",), device="cpu", env="core",
              description="overlap, continuation, connectives, dialogue share, names, affect and spoken duration")

INVENTORY_SCOPES = ("catalogue", "shard", "file")


def _as_dict(w: Any) -> dict:
    """A parse.Word as the mapping the feature modules read."""
    return {"id": w.id, "form": w.form, "lemma": w.lemma, "upos": w.upos, "feats": w.feats, "head": w.head,
            "deprel": w.deprel}


def _upos_set(table: Mapping, key: str, iso: str) -> frozenset[str]:
    return frozenset(table[key]) | frozenset(table.get(f"{key}_extra", {}).get(iso, ()))


def _check_language(cfg: Mapping, lang_cfg: Mapping) -> None:
    iso = lang_cfg["iso"]
    if iso not in cfg["stage"]["languages"]:
        raise NotImplementedError(f"features_discourse supports {cfg['stage']['languages']} in this version, not "
                                  f"{iso!r}; see [stage] in config/stages/features_discourse.toml")
    if not lang_cfg.get("spaced", True):
        raise NotImplementedError(f"{iso!r} has no whitespace words; its registered words come from the parse")
    if cfg["connectives"]["additive_temporal"] and not (cfg["connectives"]["additive"]
                                                        and cfg["connectives"]["temporal"]):
        raise ValueError("connectives.additive_temporal is on, but no English additive and temporal anchors are "
                         "registered (gap G4)")
    if cfg["names"]["inventory_scope"] not in INVENTORY_SCOPES:
        raise ValueError(f"names.inventory_scope must be one of {INVENTORY_SCOPES}, "
                         f"not {cfg['names']['inventory_scope']!r}")


def _lookup_normaliser(ctx: StageContext, cfg: Mapping, iso: str) -> Callable[[str], str]:
    """The shared lookup normalisation (S3: "Lists and texts share one normalisation function")."""
    from intract_features.features.lexical import LookupNormaliser

    lex_cfg = ctx.config["stages"][cfg["lookup"]["config_stage"]]["lexical"]
    return LookupNormaliser(lex_cfg["normalisation"], iso, lex_cfg["casing"]["dotted_i_languages"])


def _dotted_i(ctx: StageContext, cfg: Mapping, iso: str) -> bool:
    lex_cfg = ctx.config["stages"][cfg["lookup"]["config_stage"]]["lexical"]
    return iso in set(lex_cfg["casing"]["dotted_i_languages"])


def _segments(ctx: StageContext, docs: list[records.Document]) -> dict[str, list]:
    """The registered sentences of each selected document, checked against the document they were cut from."""
    from intract_features.segment import sentences_from_record

    wanted = {d.story_id: d for d in docs}
    out: dict[str, list] = {}
    for rec in ctx.read("segments"):
        sid = rec["story_id"]
        if sid not in wanted:
            continue
        if sid in out:
            raise ValueError(f"two segments records for {sid!r}")
        if rec.get("lang", ctx.lang) != ctx.lang:
            raise ValueError(f"segments record {sid!r} is for {rec.get('lang')!r}, not {ctx.lang!r}")
        digest = rec.get("text_sha256")
        if digest is not None and digest != hashlib.sha256(wanted[sid].text.encode("utf-8")).hexdigest():
            raise ValueError(f"segments record {sid!r} was cut from another text (stale artefact)")
        out[sid] = sentences_from_record(rec)
    missing = [sid for sid in wanted if sid not in out]
    if missing:
        raise ValueError(f"no segments record for {len(missing)} documents, e.g. {missing[:3]}")
    return out


def _parse_paths(ctx: StageContext, cfg: Mapping, scope: str) -> list[Path]:
    art, ext = cfg["parse"]["artefact"], cfg["parse"]["ext"]
    shards = range(ctx.nshards) if scope == "catalogue" else [ctx.shard]
    paths = [records.artefact_path(ctx.work, ctx.lang, art, i, ctx.nshards, ext) for i in shards]
    absent = [p for p in paths if not p.exists()]
    if absent:
        raise FileNotFoundError(f"parse shards missing for the name inventory ({scope} scope): {absent[:3]}")
    return paths


def _iter_parses(path: Path) -> Iterator:
    from intract_features.parse import read_conllu

    yield from read_conllu(path)


def _scan(ctx: StageContext, cfg: Mapping, iso: str, selected: set[str], name_key: Callable[[Mapping], str],
          norm: Callable[[str], str]) -> tuple[nam.NameCounts | None, set[str], int]:
    """First pass: name counts over the inventory's scope, and the affect keys the selected documents can ask for.

    Returns (counts, or None when the inventory is read from a file; candidate lexicon keys; parse shards read).
    """
    scope = cfg["names"]["inventory_scope"]
    build = scope in ("catalogue", "shard")
    name_upos = _upos_set(cfg["names"], "name_upos", iso)
    content = frozenset(cfg["affect"]["content_upos"])
    order = cfg["affect"]["lookup_order"]
    counts = nam.NameCounts() if build else None
    keys: set[str] = set()
    own = records.artefact_path(ctx.work, ctx.lang, cfg["parse"]["artefact"], ctx.shard, ctx.nshards,
                                cfg["parse"]["ext"])
    paths = _parse_paths(ctx, cfg, scope if build else "shard")
    for path in paths:
        is_own = path == own
        for pdoc in _iter_parses(path):
            want_keys = is_own and pdoc.story_id in selected
            for sent in pdoc.sentences:
                words = [_as_dict(w) for w in sent.words]
                if counts is not None:
                    counts.add(words, name_key, name_upos)
                if want_keys:
                    for w in words:
                        if w["upos"] in content:
                            keys.update(aff.candidate_keys(w, norm, order))
    return counts, keys, len(paths)


def _inventory(ctx: StageContext, cfg: Mapping, counts: nam.NameCounts | None) -> tuple[frozenset[str], str]:
    """The frozen name inventory of the language, and where it came from."""
    ncfg = cfg["names"]
    scope = ncfg["inventory_scope"]
    if scope == "file":
        if not ncfg["inventory_path"]:
            raise ValueError("names.inventory_scope is 'file' but names.inventory_path is empty")
        return nam.read_inventory(ncfg["inventory_path"]), str(ncfg["inventory_path"])
    inventory = counts.inventory(float(ncfg["min_share"]))
    if ncfg["write_inventory"]:
        suffix = "" if scope == "catalogue" else f"-shard-{ctx.shard}-of-{ctx.nshards}"
        path = Path(ctx.work) / ctx.lang / STAGE.outputs[0] / f"name_inventory{suffix}.txt"
        nam.write_inventory(path, inventory)
        return inventory, str(path)
    return inventory, f"built ({scope})"


def _affect_lexicon(ctx: StageContext, cfg: Mapping, lang_cfg: Mapping, keys: set[str]) -> tuple[aff.AffectLexicon,
                                                                                                str]:
    """MEmoLon for the language, its pin verified before it is read (DESIGN.md, Configuration)."""
    from intract_features.features.lexical import verify_pin

    acfg = cfg["affect"]
    code = lang_cfg["memolon"]
    resources = os.environ.get("INTRACT_RESOURCES", "")
    if "{resources}" in acfg["lexicon"] and not resources:
        raise ValueError("set INTRACT_RESOURCES to the directory that holds memolon/MTL_grouped/")
    path = Path(acfg["lexicon"].format(resources=resources, code=code))
    key = acfg["resource_pin"].format(code=code)
    pins = ctx.config.get("resources") or {}
    if key not in pins and isinstance(pins.get("resources"), dict):
        pins = pins["resources"]  # the lock's entries may sit at the top level or under "resources"
    status = verify_pin(path, pins, key)
    if status != "verified" and acfg["require_pin"]:
        raise RuntimeError(f"{path} has no pin {key!r} in resources.lock.json")
    return aff.load_memolon(path, keys=keys, drop_multiword=acfg["drop_multiword"]), status


def _phones(cfg: Mapping, lang_cfg: Mapping, docs: list[records.Document]) -> tuple[dict[str, tuple[int, int]],
                                                                                  tuple[str, str]]:
    """Phones and phonemized words of every document, from one call of the external phonemizer program."""
    ph = dur.Phonemizer(cfg["duration"], lang_cfg["espeak_voice"])
    versions = ph.check_pins()
    lines = ph.phonemize([d.text for d in docs])
    sep = cfg["duration"]["word_separator"]
    return {d.story_id: dur.count_phones(line, sep) for d, line in zip(docs, lines, strict=True)}, versions


def _finite(values: Mapping[str, float | None]) -> dict[str, float | None]:
    return {k: records.finite_or_none(v) for k, v in values.items()}


def run(ctx: StageContext) -> dict:
    """Score the shard's documents and write the features_discourse artefact; return counts for the timing record."""
    from intract_features.features.lexical import lower
    from intract_features.text.words import words as registered_words

    cfg = ctx.stage_config()
    lang_cfg = config_mod.language(ctx.config, ctx.lang)
    iso = lang_cfg["iso"]
    _check_language(cfg, lang_cfg)

    docs = list(ctx.documents())
    selected = {d.story_id for d in docs}
    segs = _segments(ctx, docs)
    norm = _lookup_normaliser(ctx, cfg, iso)
    dotted = _dotted_i(ctx, cfg, iso)

    def name_key(w: Mapping) -> str:
        return norm(w["form"])

    form_lemma = iso in set(cfg["overlap"]["form_as_lemma"])

    def overlap_key(w: Mapping) -> str:
        # The benchmark keys (lexrules.overlap_key) lower-cased with lower(); the shared casing rule adds the
        # dotted-I languages (critique item 19).
        return lower(ovl.lemma_or_form(w, use_form=form_lemma), dotted)

    counts, keys, shards_read = _scan(ctx, cfg, iso, selected, name_key, norm)
    inventory, inventory_source = _inventory(ctx, cfg, counts)
    lexicon, pin_status = _affect_lexicon(ctx, cfg, lang_cfg, keys)
    phones, (ph_version, es_version) = _phones(cfg, lang_cfg, docs)

    nominal = _upos_set(cfg["overlap"], "nominal_upos", iso)
    ccfg = cfg["continuation"]
    counter = con.ConnectiveCounter(con.AnchorSpec.from_config(cfg["connectives"]))
    inv = dia.QuoteInventory.from_config(lang_cfg["quotes"], cfg["dialogue"], iso)
    acfg, ncfg, dcfg = cfg["affect"], cfg["names"], cfg["duration"]
    content = frozenset(acfg["content_upos"])
    pauses = dur.PauseRules.from_config(dcfg)
    consts = dur.DurationConstants(float(dcfg["seconds_per_unit"]), float(dcfg["seconds_per_sentence_end"]),
                                   float(dcfg["seconds_per_clause_mark"]))
    if dcfg["sentence_ends"] not in ("segments", "terminal_marks"):
        raise ValueError(f"duration.sentence_ends is 'segments' or 'terminal_marks', not {dcfg['sentence_ends']!r}")
    per_conn, per_names = float(cfg["connectives"]["per_words"]), float(ncfg["per_words"])

    parsed_docs: dict[str, Any] = {}
    own = records.artefact_path(ctx.work, ctx.lang, cfg["parse"]["artefact"], ctx.shard, ctx.nshards,
                                cfg["parse"]["ext"])
    for pdoc in _iter_parses(own):
        if pdoc.story_id in selected:
            parsed_docs[pdoc.story_id] = pdoc

    totals = {"words": 0, "characters": 0, "sentences": 0, "sentences_parsed": 0, "syntactic_words": 0, "phones": 0,
              "name_tokens_unaligned": 0}
    out = []
    for doc in docs:
        sid, text = doc.story_id, doc.text
        wl = registered_words(text)
        n_words = len(wl)
        spans = [(w.start, w.end) for w in wl]
        sentences = segs[sid]
        pdoc = parsed_docs.get(sid)
        psents = pdoc.sentences if pdoc is not None else []
        # The parse writes one block per registered sentence (parse/__init__.py), so a shortfall is a stale or
        # partial artefact. Scoring it would turn missing counts into zero densities and shares.
        if len(psents) != len(sentences):
            raise ValueError(f"{sid}: the parse has {len(psents)} sentences, the segmentation {len(sentences)}")
        sent_words = [[_as_dict(w) for w in s.words] for s in psents]
        parsed = [bool(ws) and not s.empty for s, ws in zip(psents, sent_words, strict=True)]

        # Referential overlap and anaphoric continuation over adjacent pairs that both have a parse.
        pairs = ovl.adjacent_pairs(parsed)
        keysets = [ovl.nominal_keys(ws, nominal, overlap_key) for ws in sent_words]
        ov = ovl.overlap_flags(keysets, pairs)
        pron = [ovl.has_third_person_pronoun_subject(ws, ccfg["subject_relations"], ccfg["root_handover_upos"],
                                                     ccfg["root_handover_relations"], ccfg["predicate_dependents"])
                for ws in sent_words]
        cont = ovl.continuation_flags(ov, pron, pairs)

        # Connectives, counted on the parse's syntactic words of each sentence.
        hits = [counter.count(ws) for ws in sent_words]
        causal = sum(h.causal for h in hits)
        contrastive = sum(h.contrastive for h in hits)
        so = sum(h.clause_initial for h in hits)

        # Dialogue share over the registered words, by each word's first letter or digit.
        mask = dia.speech_mask(doc.pages, inv)
        inside, total = dia.speech_words(mask, [w.anchor for w in wl])

        # Names: the frozen inventory masks syntactic words; a word of the outcome's unit is a name when a token
        # holding a name overlaps it.
        flags = [nam.name_flags(ws, inventory, name_key) for ws in sent_words]
        name_spans, name_lemmas, name_tokens = [], set(), 0
        for s, ws, fl in zip(psents, sent_words, flags, strict=True):
            by_id = {w["id"]: f for w, f in zip(ws, fl, strict=True)}
            for tok in s.tokens:
                if any(by_id.get(w.id, False) for w in tok.words):
                    if tok.start is None:
                        totals["name_tokens_unaligned"] += 1
                    else:
                        name_spans.append((tok.start, tok.end))
            for w, f in zip(ws, fl, strict=True):
                if f:
                    name_tokens += 1
                    name_lemmas.add(norm(ovl.lemma_or_form(w)))
        nm = nam.NameMeasures(n_words=n_words, name_words=nam.words_overlapping(spans, name_spans),
                              name_tokens=name_tokens, name_types=len(name_lemmas))

        # Valence and arousal over content syntactic words, with and without the name exclusion.
        all_words = [w for ws in sent_words for w in ws]
        all_flags = [f for fl in flags for f in fl]
        with_ex, without = aff.text_affect(all_words, all_flags, lexicon.values, norm, acfg["lookup_order"], content,
                                           int(acfg["sd_ddof"]))

        # Predicted spoken duration per word.
        n_phones, n_ph_words = phones[sid]
        ends = len(sentences) if dcfg["sentence_ends"] == "segments" else pauses.terminal_run_count(text)
        marks = pauses.clause_mark_count(text)
        seconds = consts.seconds(n_phones, ends, marks)

        values = {
            "referential_overlap": ovl.share(ov),
            "anaphoric_continuation": ovl.share(cont),
            "causal_density": con.per_words(causal, n_words, per_conn),
            "contrastive_density": con.per_words(contrastive, n_words, per_conn),
            "causal_density_without_so": con.per_words(causal - so, n_words, per_conn),
            "dialogue_share": dia.share(inside, total),
            "name_token_share": nm.share(),
            "name_token_share_elogit": nm.share_elogit(float(ncfg["elogit_offset"])),
            "name_types_per_100_words": nm.types_per(per_names),
            "name_tokens_per_type": nm.tokens_per_type(),
            "valence_mean": with_ex.valence_mean, "valence_sd": with_ex.valence_sd,
            "arousal_mean": with_ex.arousal_mean, "arousal_sd": with_ex.arousal_sd,
            "valence_mean_with_names": without.valence_mean, "valence_sd_with_names": without.valence_sd,
            "arousal_mean_with_names": without.arousal_mean, "arousal_sd_with_names": without.arousal_sd,
            "duration_log_seconds_per_word": dur.log_seconds_per_word(seconds, n_words),
        }
        diagnostics = {
            "n_words": n_words, "n_sentences": len(sentences), "n_sentences_parsed": sum(parsed),
            "pairs": len(pairs), "pairs_left_out": max(len(sentences) - 1, 0) - len(pairs),
            "overlap_pairs": sum(ov), "continuation_pairs": sum(cont),
            "causal": causal, "contrastive": contrastive, "causal_clause_initial_so": so,
            "not_x_but_y_blocked": sum(h.not_x_but_y_blocked for h in hits),
            "sentences_causal": [k for k, h in enumerate(hits) if h.causal],
            "sentences_contrastive": [k for k, h in enumerate(hits) if h.contrastive],
            "speech_words": inside,
            "name_words": nm.name_words, "name_tokens": nm.name_tokens, "name_types": nm.name_types,
            "affect_content_tokens": with_ex.content_tokens, "affect_matched_tokens": with_ex.matched_tokens,
            "affect_coverage": with_ex.coverage(),
            "affect_content_tokens_with_names": without.content_tokens,
            "affect_matched_tokens_with_names": without.matched_tokens,
            "phones": n_phones, "phonemized_words": n_ph_words, "sentence_ends": ends, "clause_marks": marks,
            "duration_seconds": seconds,
        }
        out.append({"story_id": sid, "lang": ctx.lang, "values": _finite(values),
                    "diagnostics": _finite_tree(diagnostics)})
        totals["words"] += n_words
        totals["characters"] += len(text)
        totals["sentences"] += len(sentences)
        totals["sentences_parsed"] += sum(parsed)
        totals["syntactic_words"] += len(all_words)
        totals["phones"] += n_phones

    ctx.write(STAGE.outputs[0], out)
    omitted = [] if cfg["connectives"]["additive_temporal"] else ["additive_density", "temporal_density"]
    return {"documents": len(docs), **totals, "parse_shards_read": shards_read,
            "name_inventory_types": len(inventory), "name_inventory_sha256": nam.inventory_digest(inventory),
            "name_inventory_source": inventory_source, "affect_lexicon_rows": lexicon.rows,
            "affect_lexicon_default_rows": lexicon.default_rows, "affect_lexicon_kept": len(lexicon.values),
            "affect_pin": pin_status, "phonemizer_version": ph_version, "espeak_ng_version": es_version,
            "omitted": omitted}


def _finite_tree(obj: Any) -> Any:
    """Diagnostics with every non-finite float mapped to None, so the record is strict JSON."""
    if isinstance(obj, float):
        return records.finite_or_none(obj)
    if isinstance(obj, dict):
        return {k: _finite_tree(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite_tree(v) for v in obj]
    return obj
