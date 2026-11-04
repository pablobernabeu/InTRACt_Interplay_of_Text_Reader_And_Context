"""Stage aggregate_timing: every timing record of a run in one table, with throughput and a catalogue projection.

DESIGN.md: "Every run writes a timing record to <work>/<lang>/_timing/, with wall and CPU seconds, peak memory, the
GPU and its peak allocation, and the counts the stage returns. A stage should return at least documents, words and
characters, and tokens where it runs a subword model, so that costs can be projected per unit." This stage reads
those records (cli.run_stage names them <stage>-shard-<i>-of-<n>.json), sums them per language and stage, and writes
<work>/_summary/timing.tsv and timing.json. Two rules keep the projection to the English catalogue sound
(config/stages/aggregate_timing.toml):

* Units. A stage's time is scaled by the catalogue's total in the unit its cost follows over the amount of that same
  unit the stage processed. The catalogue's structure table counts whitespace tokens, characters and texts, so every
  stage is scaled by one of these. The amount comes from the stage's own counts or, for a stage that does not count
  that unit, from a reference stage that processed the same documents of the same shard. A stage's `words` are never
  set against whitespace tokens unless no other count exists, and then the row says so: the parse stages and CorPipe
  count syntactic words, 1.14 to 1.27 per whitespace token (planning review, section 3).
* Fixed costs. Only the time that grows with the text is scaled. Imports, pin verification, weight loading and server
  starts are paid once per process, so they are carried to the catalogue run once per process of that run. The split
  comes, in the configured order, from one-document probes that jobs/arc/run_stage.sh runs before and after a stage's
  shards, from the compute timers a stage reports, or from fixed costs it reports. A stage with none of these is
  projected unsplit, which also scales its fixed costs, and is listed as such.

jobs/arc/run_stage.sh also leaves a side record per shard (<work>/_runs/<lang>/<stage>-shard-<i>-of-<n>.json) with
the environment that actually ran, the CPUs allocated, the CPU time of the whole process tree and whether the process
started cold; the table uses them where present. It measures cost only: no feature is computed and no text is read.
"""

from __future__ import annotations

import fnmatch
import json
import math
import re
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

from intract_features import records
from intract_features.cli import Stage, StageContext

STAGE = Stage(name="aggregate_timing", inputs=(), outputs=(), device="cpu", env="core",
              description="timing records of a run in one table: throughput and a projection to the catalogue")

TIMING_NAME = re.compile(r"^(?P<stage>[a-z0-9_]+)-shard-(?P<shard>\d+)-of-(?P<nshards>\d+)\.json$")
# Projection units and the [catalogue] total each is set against.
CATALOGUE_TOTAL = {"whitespace_tokens": "whitespace_tokens", "characters": "characters", "documents": "texts"}
METHODS = ("whitespace_tokens", "characters", "documents", "level_ratios")
SPLIT_SOURCES = ("probe", "timers", "fixed_keys")
SUMMED = ("documents", "words", "whitespace_tokens", "characters", "tokens")
COLUMNS = ("lang", "stage", "device", "env", "env_active", "shards_found", "nshards", "complete", "documents", "words",
           "whitespace_tokens", "characters", "tokens", "words_per_whitespace_token", "wall_seconds", "cpu_seconds",
           "process_cpu_seconds", "cpus", "peak_rss_mb", "gpu_names", "gpu_peak_allocated_mb", "documents_per_second",
           "whitespace_tokens_per_second", "characters_per_second", "tokens_per_second", "words_per_cpu_second",
           "split", "fixed_seconds", "compute_seconds", "cold_starts", "unit", "unit_source", "method", "factor",
           "target_processes", "projected_fixed_hours", "projected_compute_hours", "projected_wall_hours",
           "unsplit_projected_wall_hours", "batch_fill", "projected_wall_hours_as_measured", "alternative_method",
           "alternative_projected_wall_hours", "projected_core_hours", "notes")


# ------------------------------------------------------------------------------------------------- reading


def _refuse_constant(name: str):
    raise ValueError(f"non-finite number {name}")


def _load_record(path: Path, expected: Mapping) -> tuple[dict | None, str | None]:
    """A strict-JSON object whose fields agree with `expected`, or None and the reason it was left out."""
    try:
        rec = json.loads(path.read_text(encoding="utf-8"), parse_constant=_refuse_constant)
    except (ValueError, OSError) as e:
        return None, f"unreadable ({e})"
    if not isinstance(rec, dict):
        return None, "not a JSON object"
    wrong = [k for k, v in expected.items() if rec.get(k) != v]
    if wrong:
        return None, f"{', '.join(wrong)} disagree with the file name"
    return rec, None


def _timing_files(folder: Path) -> Iterable[tuple[Path, re.Match]]:
    if not folder.is_dir():
        return
    for path in sorted(folder.iterdir()):
        m = TIMING_NAME.match(path.name)
        if m and path.is_file():
            yield path, m


def read_timing_records(work: Path, langs: str | Iterable[str], exclude: Iterable[str]) -> tuple[list[dict], list[str]]:
    """Every timing record under <work>/<lang>/_timing/, and a note for each file left out.

    A file is left out when its name is not a timing record's, when it is not strict JSON, or when its stage,
    shard or language disagrees with its name, so a stray or half-copied file cannot enter the table. Folders whose
    name starts with "_" (_probe, _runs, _summary, _input) are not languages.
    """
    work = Path(work)
    excluded = set(exclude)
    if langs == "all":
        folders = sorted(p for p in work.iterdir() if p.is_dir() and not p.name.startswith("_")
                         and (p / "_timing").is_dir()) if work.is_dir() else []
    else:
        folders = [work / lang for lang in langs]
    found, notes = [], []
    for folder in folders:
        timing = folder / "_timing"
        if not timing.is_dir():
            notes.append(f"{folder.name}: no _timing folder")
            continue
        for path, m in _timing_files(timing):
            if m["stage"] in excluded:
                continue
            expected = {"stage": m["stage"], "shard": int(m["shard"]), "nshards": int(m["nshards"]),
                        "lang": folder.name}
            rec, why = _load_record(path, expected)
            if rec is None:
                notes.append(f"{folder.name}/{path.name}: {why}")
            else:
                found.append(rec)
    return found, notes


def read_side_records(work: Path) -> tuple[dict[tuple, dict], list[str]]:
    """run_stage.sh's side records, keyed (lang, stage, shard, nshards), and a note for each file left out."""
    out, notes = {}, []
    runs = Path(work) / "_runs"
    if not runs.is_dir():
        return out, notes
    for folder in sorted(p for p in runs.iterdir() if p.is_dir()):
        for path, m in _timing_files(folder):
            expected = {"stage": m["stage"], "shard": int(m["shard"]), "nshards": int(m["nshards"]),
                        "lang": folder.name}
            rec, why = _load_record(path, expected)
            if rec is None:
                notes.append(f"_runs/{folder.name}/{path.name}: {why}")
            else:
                out[(folder.name, m["stage"], int(m["shard"]), int(m["nshards"]))] = rec
    return out, notes


def read_probe_records(work: Path, probe_dir: str) -> tuple[dict[tuple[str, str], dict], list[str]]:
    """The probes' timing records, {(lang, stage): {"cold": record, "warm": record}}, and notes.

    run_stage.sh runs each probe in its own work folder, <work>/<probe_dir>/<cold|warm>/<stage>/, so a probe's
    one-document outputs never mix with the run's.
    """
    out: dict[tuple[str, str], dict] = defaultdict(dict)
    notes = []
    root = Path(work) / probe_dir
    for kind in ("cold", "warm"):
        base = root / kind
        if not base.is_dir():
            continue
        for stage_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            for lang_dir in sorted(p for p in stage_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
                for path, m in _timing_files(lang_dir / "_timing"):
                    if m["stage"] != stage_dir.name:
                        continue
                    expected = {"stage": m["stage"], "shard": int(m["shard"]), "nshards": int(m["nshards"]),
                                "lang": lang_dir.name}
                    rec, why = _load_record(path, expected)
                    if rec is None:
                        notes.append(f"{probe_dir}/{kind}/{stage_dir.name}/{lang_dir.name}/{path.name}: {why}")
                    else:
                        out[(lang_dir.name, m["stage"])][kind] = rec
    return dict(out), notes


# ---------------------------------------------------------------------------------------------- numbers


def _number(value) -> float:
    """A count or a time as a float; anything else (a nested record, None, a non-finite value) counts as zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value) if math.isfinite(value) else 0.0


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _whole(x: float) -> int | float:
    """A count that is a whole number as an int, so the table shows 400, not 400.0000."""
    return int(x) if float(x).is_integer() else x


def dotted(mapping: Mapping, path: str):
    """The value at a dotted path ("udpipe.server.startup_seconds") of nested mappings, or None."""
    node = mapping
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def timer_seconds(counts: Mapping, patterns: Iterable[str]) -> float | None:
    """The sum of the top-level counts whose key matches a pattern (fnmatch), or None when none matches."""
    found = [float(v) for k, v in counts.items()
             if _is_number(v) and any(fnmatch.fnmatchcase(k, p) for p in patterns)]
    return sum(found) if found else None


# ------------------------------------------------------------------------------------------------- amounts


def reference_index(recs: Iterable[Mapping], stages: Iterable[str]) -> dict[tuple, list[tuple[str, Mapping]]]:
    """Reference stages' counts by (lang, shard, nshards), in the configured order of preference."""
    order = list(stages)
    index: dict[tuple, list[tuple[str, Mapping]]] = defaultdict(list)
    for r in sorted((r for r in recs if r["stage"] in order), key=lambda r: order.index(r["stage"])):
        index[(r["lang"], int(r["shard"]), int(r["nshards"]))].append((r["stage"], r.get("counts") or {}))
    return index


def shard_amount(rec: Mapping, unit: str, refs: Mapping[tuple, list], prefer: str = "own",
                 words_fallback: bool = False) -> tuple[float | None, str]:
    """A shard's amount of `unit` and where it comes from.

    "own" is the stage's own count. "reference:<stage>" borrows a reference stage's count for the same shard, used
    only when both recorded the same number of documents, since then they processed the same texts. With
    `words_fallback`, a stage with neither falls back to its `words` for whitespace tokens, marked approximate.
    """
    counts = rec.get("counts") or {}
    if _is_number(counts.get("documents")) and counts["documents"] == 0:
        # A shard that processed no document adds nothing: an empty shard, or a seg_check run other than shard 0,
        # which computes the whole report (stages/seg_check.py). Without this, one such shard would leave the
        # stage with no amount at all.
        return 0.0, "own (no documents)"
    own = counts.get(unit)
    own_ok = _is_number(own) and own > 0
    borrowed, source = None, None
    if unit != "documents":
        docs = counts.get("documents")
        for stage, rc in refs.get((rec["lang"], int(rec["shard"]), int(rec["nshards"])), ()):
            if stage != rec["stage"] and _is_number(docs) and rc.get("documents") == docs and \
                    _is_number(rc.get(unit)) and rc[unit] > 0:
                borrowed, source = float(rc[unit]), f"reference:{stage}"
                break
    if prefer == "reference" and borrowed is not None:
        return borrowed, source
    if own_ok:
        return float(own), "own"
    if borrowed is not None:
        return borrowed, source
    words = counts.get("words")
    if unit == "whitespace_tokens" and words_fallback and _is_number(words) and words > 0:
        return float(words), "words (approximate: not whitespace tokens)"
    return None, f"no {unit} count"


# ------------------------------------------------------------------------------------------------- summary


def summarise(recs: Iterable[Mapping], cfg: Mapping, side: Mapping[tuple, Mapping] | None = None) -> list[dict]:
    """One row per (language, stage): summed counts and times, maxima of memory, the GPUs used, and the shards.

    Shards of one stage may have run with different shard counts after a rerun; the row then reports every count
    seen and is marked incomplete, since its shards do not partition one run.
    """
    recs = list(recs)
    side = side or {}
    pcfg = cfg["projection"]
    refs = reference_index(recs, pcfg.get("reference_stages", []))
    words_fallback = bool(pcfg.get("allow_words_fallback", False))
    groups: dict[tuple[str, str], list[Mapping]] = defaultdict(list)
    for r in recs:
        groups[(r["lang"], r["stage"])].append(r)
    rows = []
    for (lang, stage), items in sorted(groups.items()):
        items = sorted(items, key=lambda r: (int(r["nshards"]), int(r["shard"])))
        nshards = sorted({int(r["nshards"]) for r in items})
        shards = {int(r["shard"]) for r in items}
        complete = len(nshards) == 1 and shards == set(range(nshards[0]))
        counts = {u: _whole(sum(_number((r.get("counts") or {}).get(u)) for r in items)) for u in SUMMED}
        present = {u: any(u in (r.get("counts") or {}) for r in items) for u in SUMMED}
        sides = [side.get((lang, stage, int(r["shard"]), int(r["nshards"]))) for r in items]
        spec = pcfg.get("units", {}).get(stage, {})
        prefer = spec.get("source", "own") if isinstance(spec, Mapping) else "own"
        amounts, sources = {}, {}
        for unit in CATALOGUE_TOTAL:
            got = [shard_amount(r, unit, refs, prefer, words_fallback) for r in items]
            amounts[unit] = None if any(a is None for a, _ in got) else sum(a for a, _ in got)
            sources[unit] = "/".join(sorted({s for _, s in got}))
        rss = [_number(r.get("peak_rss_mb")) for r in items if r.get("peak_rss_mb") is not None]
        gpu_mb = [_number(r.get("gpu_peak_allocated_mb")) for r in items if r.get("gpu_peak_allocated_mb") is not None]
        tree = [t for t in (s.get("process_tree") for s in sides if s) if isinstance(t, Mapping)
                and _is_number(t.get("user_seconds")) and _is_number(t.get("sys_seconds"))]
        cpus = [_number(s.get("cpus")) for s in sides if s and _is_number(s.get("cpus")) and s["cpus"] > 0]
        rows.append({
            "lang": lang, "stage": stage, "device": _one(r.get("device") for r in items),
            "env": _one(r.get("env") for r in items), "env_active": _one(s.get("env_active") for s in sides if s),
            "shards_found": len(shards),
            "nshards": nshards[0] if len(nshards) == 1 else "/".join(map(str, nshards)), "complete": complete,
            **{u: (counts[u] if present[u] else None) for u in SUMMED},
            "words_per_whitespace_token": (counts["words"] / counts["whitespace_tokens"]
                                           if present["words"] and present["whitespace_tokens"]
                                           and counts["whitespace_tokens"] else None),
            "wall_seconds": sum(_number(r.get("wall_seconds")) for r in items),
            "cpu_seconds": sum(_number(r.get("cpu_seconds")) for r in items),
            "process_cpu_seconds": (sum(_number(t.get("user_seconds")) + _number(t.get("sys_seconds")) for t in tree)
                                    if len(tree) == len(items) else None),
            "cpus": (sum(cpus) / len(cpus)) if len(cpus) == len(items) else None,
            "peak_rss_mb": max(rss) if rss else None,
            "gpu_names": ";".join(sorted({str(r["gpu_name"]) for r in items if r.get("gpu_name")})) or None,
            "gpu_peak_allocated_mb": max(gpu_mb) if gpu_mb else None,
            "code_commits": sorted({str(r.get("code_commit")) for r in items}),
            "slurm_job_ids": sorted({str(r["slurm_job_id"]) for r in items if r.get("slurm_job_id")}),
            "amounts": amounts, "amount_sources": sources,
            "_shards": [{"wall": _number(r.get("wall_seconds")),
                         "documents": _number((r.get("counts") or {}).get("documents")),
                         "counts": r.get("counts") or {},
                         "cold": (s or {}).get("cold") if isinstance((s or {}).get("cold"), bool) else None}
                        for r, s in zip(items, sides, strict=True)],
        })
    return rows


def _one(values: Iterable) -> str | None:
    seen = sorted({str(v) for v in values if v is not None})
    return "/".join(seen) if seen else None


def _rate(amount: float | None, seconds: float) -> float | None:
    if amount is None or seconds <= 0:
        return None
    return amount / seconds


# ---------------------------------------------------------------------------------------------- the split


def probe_usable(shards: list[Mapping], warm: Mapping) -> bool:
    """Whether a probe is small beside the shards (at most a tenth of a mean shard's documents).

    The split solves for a fixed cost and a per-document rate, which a probe as large as a shard cannot tell apart.
    """
    d_warm = _number((warm.get("counts") or {}).get("documents")) or 1.0
    n_docs = sum(s["documents"] for s in shards)
    return n_docs > 0 and 10 * d_warm * len(shards) <= n_docs


def probe_split(shards: list[Mapping], warm: Mapping, cold: Mapping | None, iterations: int = 25) -> dict:
    """Fixed and compute seconds of each shard from a warm probe and, if it ran, a cold one.

    A probe is the stage run on one document, so its wall time is the fixed cost of a process plus one document's
    compute. The warm probe runs after the shards, with the job's files in the page cache; the cold probe runs
    first, so it also pays the job's cold start, the 3-7 minute imports from the network file system that the
    pre-submission jobs met (planning review, section 3). A shard that started cold pays that excess too. The
    per-document compute rate and the fixed costs are solved together by fixed-point iteration, which converges
    because one document is a small share of a shard.
    """
    w_warm, d_warm = _number(warm.get("wall_seconds")), _number((warm.get("counts") or {}).get("documents")) or 1.0
    w_cold = _number(cold.get("wall_seconds")) if cold else None
    d_cold = (_number((cold.get("counts") or {}).get("documents")) or 1.0) if cold else 0.0
    cold_flags = [bool(s.get("cold")) for s in shards]
    fixed, excess, rate = w_warm, 0.0, 0.0
    n_docs = sum(s["documents"] for s in shards)
    for _ in range(iterations):
        compute = [max(0.0, s["wall"] - fixed - (excess if c else 0.0))
                   for s, c in zip(shards, cold_flags, strict=True)]
        rate = sum(compute) / n_docs if n_docs > 0 else 0.0
        fixed = max(0.0, w_warm - rate * d_warm)
        if w_cold is not None:
            excess = max(0.0, w_cold - rate * d_cold - fixed)
    per_fixed = [min(s["wall"], fixed + (excess if c else 0.0)) for s, c in zip(shards, cold_flags, strict=True)]
    return {"fixed": per_fixed, "process_fixed": fixed, "cold_excess": excess if w_cold is not None else None,
            "rate_per_document": rate, "cold_shards": sum(cold_flags), "cold_probe": cold is not None}


def split_row(row: Mapping, probes: Mapping[str, Mapping] | None, scfg: Mapping) -> dict:
    """How a row's wall time divides into fixed and compute seconds, from the first source in [split] order.

    Returns the source, per-shard fixed seconds and the sums. "none" means that no source applied, so every
    second counts as compute; such a projection also scales the fixed costs and is an upper bound.
    """
    stage, shards = row["stage"], row["_shards"]
    walls = [s["wall"] for s in shards]
    notes = []
    for source in scfg.get("order", SPLIT_SOURCES):
        if source not in SPLIT_SOURCES:
            raise ValueError(f"[split] order names {source!r}; known: {SPLIT_SOURCES}")
        if source == "probe" and probes and probes.get("warm"):
            if not probe_usable(shards, probes["warm"]):
                notes.append("the probe is too large beside the shards to separate fixed from compute time")
                continue
            p = probe_split(shards, probes["warm"], probes.get("cold"))
            if p["rate_per_document"] <= 0:
                # A stage that pads every batch to a fixed size (qe_metricx) costs as much on one document as on a
                # shard, so the probe finds no per-document cost and would put every second into fixed time
                # (ISSUES.md FP-13, smoke run of 4 November 2026).
                notes.append("the probe finds no per-document cost, as in a stage that pads every batch to a fixed "
                             "size; the next source is used")
                continue
            unknown = sum(1 for s in shards if s.get("cold") is None)
            if not p["cold_probe"]:
                notes.append("no cold probe: a cold start stays in the compute time")
            if unknown:
                notes.append(f"{unknown} shard(s) without a side record are taken as warm")
            return {"split": "probe", "fixed": p["fixed"], "process_fixed": p["process_fixed"],
                    "cold_excess": p["cold_excess"], "cold_shards": p["cold_shards"],
                    "cold_probes": int(p["cold_probe"]), "notes": notes}
        if source == "timers":
            patterns = scfg.get("timers", {}).get(stage)
            if not patterns:
                continue
            compute = [timer_seconds(s["counts"], patterns) for s in shards]
            if any(c is None for c in compute):
                continue
            notes.append("compute from the stage's timers; work outside them (reading, writing, tokenising) is "
                         "carried as fixed")
            return {"split": "timers", "fixed": [max(0.0, w - min(w, c)) for w, c in zip(walls, compute, strict=True)],
                    "notes": notes}
        if source == "fixed_keys":
            paths = scfg.get("fixed_keys", {}).get(stage)
            if not paths:
                continue
            found = [[dotted(s["counts"], p) for p in paths] for s in shards]
            if not any(_is_number(v) for vals in found for v in vals):
                continue
            notes.append("fixed costs are those the stage reports (" + ", ".join(paths) + "); the rest of its start "
                         "is scaled with the compute")
            return {"split": "fixed_keys", "notes": notes,
                    "fixed": [min(w, sum(_number(v) for v in vals)) for w, vals in zip(walls, found, strict=True)]}
    return {"split": "none", "fixed": [0.0] * len(shards),
            "notes": notes + ["no split: fixed costs are scaled with the compute (upper bound)"]}


# ------------------------------------------------------------------------------------------- projection


def level_char_ratio(levels: Mapping[str, Mapping]) -> float:
    """The catalogue's token-weighted character ratio over its reading levels.

    A level without a char_ratio (the classics) takes the token-weighted mean of the levels that have one.
    """
    tokens = {name: float(v["texts"]) * float(v["mean_tokens"]) for name, v in levels.items()}
    rated = {name: float(v["char_ratio"]) for name, v in levels.items() if "char_ratio" in v}
    if not rated:
        raise ValueError("no reading level has a char_ratio")
    known = sum(tokens[n] for n in rated)
    mean_rated = sum(tokens[n] * r for n, r in rated.items()) / known
    total = sum(tokens.values())
    return sum(tokens[n] * rated.get(n, mean_rated) for n in tokens) / total


def projection_factor(amounts: Mapping[str, float | None], method: str, catalogue: Mapping, ratio: float,
                      multiplier: float = 1.0) -> float | None:
    """The factor that scales measured compute to the catalogue under one rule; None if the amount is missing.

    "whitespace_tokens", "characters" and "documents" divide the catalogue's total by the same unit's measured
    amount. "level_ratios" is the whitespace-token factor times the catalogue-to-stand-in character ratio (planning
    review, section 5, step 8), for stages whose cost follows characters on a stand-in matched in tokens.
    """
    if method not in METHODS:
        raise ValueError(f"unknown projection method {method!r}; one of {METHODS}")
    unit = "whitespace_tokens" if method == "level_ratios" else method
    measured = amounts.get(unit)
    if measured is None or measured <= 0:
        return None
    factor = multiplier * float(catalogue[CATALOGUE_TOTAL[unit]]) / measured
    return factor * ratio if method == "level_ratios" else factor


def project(row: dict, cfg: Mapping, target_shards: int, probes: Mapping[tuple[str, str], Mapping] | None = None
            ) -> dict:
    """Add throughput, the fixed/compute split and the projection columns to a summary row."""
    wall, cpu = row["wall_seconds"], row["cpu_seconds"]
    for u in ("documents", "whitespace_tokens", "characters", "tokens"):
        row[f"{u}_per_second"] = _rate(row[u], wall)
    row["words_per_cpu_second"] = _rate(row["words"], cpu)
    pcfg, catalogue = cfg["projection"], cfg["catalogue"]
    spec = pcfg.get("units", {}).get(row["stage"]) or {}
    unit = spec.get("unit", pcfg["default_unit"]) if isinstance(spec, Mapping) else str(spec)
    if unit not in CATALOGUE_TOTAL:
        raise ValueError(f"{row['stage']}: unit {unit!r} must be one of {tuple(CATALOGUE_TOTAL)}")
    override = pcfg.get("overrides", {}).get(row["stage"], {})
    repeat = 1
    if "per_translation" in override:
        # A stage that scores every translation with its English source (qe_metricx): each of the translations is
        # its own run on the catalogue, with its own processes.
        repeat = int(catalogue["translations"])
        multiplier = float(override["per_translation"]) * repeat
    else:
        multiplier = float(override.get("multiplier", 1.0))
    if unit == "characters":
        method = override.get("method", pcfg["character_method"])
        alternative = None if "method" in override else ("characters" if method == "level_ratios" else "level_ratios")
    else:
        method, alternative = unit, None
    notes = []
    ratio = level_char_ratio(catalogue["levels"])
    amounts = row["amounts"]
    factor = projection_factor(amounts, method, catalogue, ratio, multiplier)
    if factor is None and alternative is not None:
        alt = projection_factor(amounts, alternative, catalogue, ratio, multiplier)
        if alt is not None:
            notes.append(f"{method} has no amount; {alternative} is used")
            method, alternative, factor = alternative, method, alt
    unit_used = "whitespace_tokens" if method == "level_ratios" else method
    source = row["amount_sources"].get(unit_used)
    if source and "approximate" in source:
        notes.append("words stand in for whitespace tokens")

    split = split_row(row, (probes or {}).get((row["lang"], row["stage"])), cfg.get("split", {}))
    notes += split["notes"]
    fixed = sum(split["fixed"])
    compute = wall - fixed
    n = len(row["_shards"])
    target = target_shards * repeat
    if split["split"] == "probe":
        # Each target process pays the warm fixed cost; cold starts recur as often per process as they did here,
        # counting the cold probe, which took the cold start of its job.
        cold_events = split["cold_shards"] + split["cold_probes"]
        excess = split["cold_excess"] or 0.0
        projected_fixed = split["process_fixed"] * target + excess * cold_events * target / n
        cold_starts = cold_events
    else:
        projected_fixed = fixed / n * target if n else 0.0
        cold_starts = None
    # A stage that pads its batches ([projection.overrides] fill = [real, padded] count keys) spends its compute on
    # padded positions. A smoke run fills its batches mostly with padding, while the catalogue fills them, so the
    # compute is scaled by the measured fill before it is projected; the projection with batches as measured is
    # kept beside it as an upper bound.
    fill, fill_keys = None, override.get("fill")
    if fill_keys:
        real = sum(_number(dotted(s["counts"], fill_keys[0])) for s in row["_shards"])
        padded = sum(_number(dotted(s["counts"], fill_keys[1])) for s in row["_shards"])
        if real > 0 and padded > 0:
            fill = min(1.0, real / padded)
            notes.append(f"compute scaled to full batches: {real:.0f} of {padded:.0f} positions held text "
                         f"(fill {fill:.3f}); projected_wall_hours_as_measured keeps the padding")
        else:
            notes.append(f"no {fill_keys[0]} and {fill_keys[1]} counts: compute not scaled to full batches")
    compute_projected = compute * fill if fill is not None else compute
    row.update({"split": split["split"], "fixed_seconds": fixed, "compute_seconds": compute,
                "cold_starts": cold_starts, "unit": unit, "unit_source": source, "method": method, "factor": factor,
                "target_processes": target,
                "projected_fixed_hours": projected_fixed / 3600 if factor is not None else None,
                "projected_compute_hours": compute_projected * factor / 3600 if factor is not None else None,
                "unsplit_projected_wall_hours": wall * factor / 3600 if factor is not None else None,
                "batch_fill": fill,
                "projected_wall_hours_as_measured": ((projected_fixed + compute * factor) / 3600
                                                     if fill is not None and factor is not None else None),
                "alternative_method": alternative, "alternative_projected_wall_hours": None})
    row["projected_wall_hours"] = (row["projected_fixed_hours"] + row["projected_compute_hours"]
                                   if factor is not None else None)
    if alternative:
        alt = projection_factor(amounts, alternative, catalogue, ratio, multiplier)
        row["alternative_projected_wall_hours"] = (projected_fixed + compute * alt) / 3600 if alt is not None else None
    cores = row["cpus"]
    if cores is None:
        cores = pcfg.get("cores", {}).get(row["stage"])
        if cores is not None:
            notes.append("CPUs allocated taken from [projection.cores]")
    row["cpus"] = cores
    # ARC bills a CPU job for its allocated cores over its elapsed time, so the core-hours follow the wall time.
    row["projected_core_hours"] = (row["projected_wall_hours"] * float(cores)
                                   if row["device"] != "gpu" and cores and row["projected_wall_hours"] is not None
                                   else None)
    row["notes"] = "; ".join(notes) or None
    return row


def totals(rows: Iterable[Mapping]) -> dict:
    """Measured and projected GPU-hours (one GPU per GPU stage) and the core-hours of the CPU stages."""
    out = {"measured_gpu_hours": 0.0, "projected_gpu_hours": 0.0, "projected_gpu_fixed_hours": 0.0,
           "projected_gpu_compute_hours": 0.0, "unsplit_projected_gpu_hours": 0.0, "measured_core_hours": 0.0,
           "projected_core_hours": 0.0, "measured_cpu_hours_main_process": 0.0, "stages_without_projection": [],
           "stages_projected_unsplit": [], "stages_without_core_count": [], "incomplete_stages": [],
           "approximate_units": [],
           "note": "GPU-hours are the sums of GPU stages' wall times; an allocation is billed for its whole elapsed "
                   "time (jobs/arc/budget_guard.py report)."}
    for r in rows:
        name = f"{r['lang']}/{r['stage']}"
        if not r["complete"]:
            out["incomplete_stages"].append(name)
        if r["projected_wall_hours"] is None:
            out["stages_without_projection"].append(name)
        if r["split"] == "none":
            out["stages_projected_unsplit"].append(name)
        if r["unit_source"] and "approximate" in r["unit_source"]:
            out["approximate_units"].append(name)
        if r["device"] == "gpu":
            out["measured_gpu_hours"] += r["wall_seconds"] / 3600
            out["projected_gpu_hours"] += r["projected_wall_hours"] or 0.0
            out["projected_gpu_fixed_hours"] += r["projected_fixed_hours"] or 0.0
            out["projected_gpu_compute_hours"] += r["projected_compute_hours"] or 0.0
            out["unsplit_projected_gpu_hours"] += r["unsplit_projected_wall_hours"] or 0.0
        else:
            out["measured_cpu_hours_main_process"] += r["cpu_seconds"] / 3600
            if r["cpus"]:
                out["measured_core_hours"] += r["wall_seconds"] * float(r["cpus"]) / 3600
                out["projected_core_hours"] += r["projected_core_hours"] or 0.0
            else:
                out["stages_without_core_count"].append(name)
    return out


# ------------------------------------------------------------------------------------------------- output


def _cell(value, decimals: int) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{decimals}f}" if math.isfinite(value) else ""
    return str(value).replace("\t", " ").replace("\n", " ")


def _write_text(path: Path, text: str) -> None:
    """Write a file atomically (temporary file, then rename), as every artefact is written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _strict(obj):
    """Replace non-finite floats with None, so the JSON is strict (DESIGN.md: non-finite numbers become null)."""
    if isinstance(obj, float):
        return records.finite_or_none(obj)
    if isinstance(obj, dict):
        return {k: _strict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strict(v) for v in obj]
    return obj


def target_shard_count(cfg: Mapping, pipeline_cfg: Mapping) -> int:
    """Processes per stage in the catalogue run: [projection] target_shards, or the pipeline's [shards] default."""
    n = int(cfg["projection"].get("target_shards", 0) or 0)
    if n <= 0:
        n = int(pipeline_cfg.get("shards", {}).get("default", 1))
    if n < 1:
        raise ValueError("the target run needs at least one shard")
    return n


def run(ctx: StageContext) -> dict:
    """Collect the run's timing records and write the summary table; return counts for this stage's own record."""
    cfg = ctx.stage_config()
    scope = cfg["scope"]
    work = Path(ctx.work)
    recs, notes = read_timing_records(work, scope["langs"], scope["exclude_stages"])
    side, side_notes = read_side_records(work)
    probes, probe_notes = read_probe_records(work, cfg["probe"]["dir"])
    notes += side_notes + probe_notes
    target = target_shard_count(cfg, ctx.config)
    rows = [project(r, cfg, target, probes) for r in summarise(recs, cfg, side)]
    out_dir = work / cfg["output"]["dir"]
    decimals = int(cfg["output"]["decimals"])
    lines = ["\t".join(COLUMNS)] + ["\t".join(_cell(r.get(c), decimals) for c in COLUMNS) for r in rows]
    _write_text(out_dir / "timing.tsv", "\n".join(lines) + "\n")
    for r in rows:
        r.pop("_shards", None)
    summary = {"work": str(ctx.work), "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "records": len(recs), "side_records": len(side), "probes": sorted("/".join(k) for k in probes),
               "notes": notes, "catalogue": cfg["catalogue"],
               "char_ratio": level_char_ratio(cfg["catalogue"]["levels"]), "target_shards": target,
               "projection": dict(cfg["projection"]), "split": dict(cfg.get("split", {})),
               "totals": totals(rows), "stages": rows}
    _write_text(out_dir / "timing.json",
                json.dumps(_strict(summary), indent=1, sort_keys=True, allow_nan=False) + "\n")
    return {"documents": 0, "words": 0, "characters": 0, "records": len(recs), "stages": len(rows),
            "files_left_out": len(notes)}
