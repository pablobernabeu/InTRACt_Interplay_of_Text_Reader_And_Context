"""Compare two runs of the feature pipeline: row by row (determinism) or value by value (the bf16 check).

    python -I compare_runs.py rows --base WORK --other WORK --out FILE [--lang L ...]
    python -I compare_runs.py bf16 --base WORK --other WORK --out FILE [--config DIR]

rows: DESIGN.md, Determinism: "The 1 per cent smoke run's rows must equal the same rows of the full run, and the run
records compare their hashes." Every artefact the two runs share is read shard by shard (both runs shard by the same
keyed hash of the story id, so a story sits in the same shard of each). Every record of --other (the smoke run) is
matched by story id to the record of --base (the full run), and the two are compared in canonical JSON, or as the
document's block for CoNLL-U. The record gives, per artefact, the rows compared and equal, a SHA-256 over the
compared rows of each run in story order, and the first stories that differ. Exit status 1 if any row differs.
Because every stage process runs with randomised string hashing (jobs/arc/env.sh), equal rows also show that no
output depends on hash order.

bf16: preregistration.qmd, Timeline, budget guard: XGLM-4.5B, MetricX-24 and the coreference resolver may run in
bf16 "only if their text means agree with those at full precision at r >= .995 on the public benchmark scored before
submission" (P08). --base is the fp32 run and --other the bf16 run of gpu_bf16.sbatch. For each model, the text
values are paired by story id and Pearson's r computed; the threshold is surprisal_xglm.toml's agreement_threshold,
the registered value's one home in config/. CorPipe gives no registered value, so its text mean is the share of
adjacent sentence pairs its chains link (pair_continuity), PENDING the Feature Specification. The XGLM stage also
compares the precisions itself (check_fraction); its own result, from the bf16 run's timing records, is reported
beside. Exit status 1 if a model with pairs falls below the threshold.

Standard library only (tomllib for the threshold); no text is printed, only story ids and numbers.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
import tomllib
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

SHARD_FILE = re.compile(r"^shard-(?P<shard>\d+)-of-(?P<nshards>\d+)\.(?P<ext>jsonl\.gz|conllu\.gz)$")
NEWDOC = "# newdoc id = "
# The text values compared in the bf16 check (the stages' registered values), and how CorPipe's is derived.
BF16_VALUES = {
    "surprisal_xglm": ("values", ("mean_surprisal_xglm", "mean_surprisal_xglm_all_words")),
    "qe_metricx": ("values", ("metricx_qe",)),
    "coref_corpipe": ("pair_continuity", ("pair_continuity_mean",)),
}
SHOWN_DIFFERENCES = 10


# -------------------------------------------------------------------------------------------- reading


def artefact_files(work: Path, lang: str) -> dict[str, dict[tuple[int, int], Path]]:
    """{artefact: {(shard, nshards): path}} for the row artefacts of one language of a run."""
    out: dict[str, dict[tuple[int, int], Path]] = {}
    folder = Path(work) / lang
    if not folder.is_dir():
        return out
    for art in sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for path in sorted(art.iterdir()):
            m = SHARD_FILE.match(path.name)
            if m:
                out.setdefault(art.name, {})[(int(m["shard"]), int(m["nshards"]))] = path
    return out


def read_rows(path: Path) -> Iterator[tuple[str, str]]:
    """(story id, canonical text) for each document of a JSON Lines or CoNLL-U shard."""
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        if path.name.endswith(".jsonl.gz"):
            for line in fh:
                if line.strip():
                    rec = json.loads(line)
                    yield str(rec.get("story_id")), json.dumps(rec, sort_keys=True, ensure_ascii=False)
            return
        sid, block = None, []
        for line in fh:
            if line.startswith(NEWDOC):
                if sid is not None:
                    yield sid, "".join(block)
                sid, block = line[len(NEWDOC):].strip(), []
            block.append(line)
        if sid is not None:
            yield sid, "".join(block)


def read_values(path: Path, how: str, names: Iterable[str]) -> dict[str, dict[str, float]]:
    """{story id: {value name: number}} from a JSON Lines shard, finite numbers only."""
    out: dict[str, dict[str, float]] = {}
    for sid, text in read_rows(path):
        rec = json.loads(text)
        vals = {}
        if how == "values":
            for name in names:
                v = (rec.get("values") or {}).get(name)
                if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                    vals[name] = float(v)
        elif how == "pair_continuity":
            # coref_corpipe writes null for a pair either of whose sentences was not sent, and the text's share over
            # the pairs with data as diagnostics.pair_continuity_share (null when no pair has data).
            share = (rec.get("diagnostics") or {}).get("pair_continuity_share")
            if share is None:
                known = [float(p) for p in rec.get("pair_continuity") or [] if p is not None]
                share = sum(known) / len(known) if known else None
            if isinstance(share, (int, float)) and not isinstance(share, bool) and math.isfinite(share):
                vals["pair_continuity_mean"] = float(share)
        out[sid] = vals
    return out


# -------------------------------------------------------------------------------------------- rows


def compare_rows(base: Path, other: Path, langs: Iterable[str]) -> dict:
    """Row equality of every artefact the two runs share, per language; see the module docstring."""
    report: dict = {"base": str(base), "other": str(other), "artefacts": {}, "all_equal": True}
    for lang in langs:
        b_files, o_files = artefact_files(base, lang), artefact_files(other, lang)
        for art in sorted(set(b_files) & set(o_files)):
            shards = sorted(set(b_files[art]) & set(o_files[art]))
            rec = {"shards": len(shards), "rows_other": 0, "rows_compared": 0, "rows_equal": 0,
                   "missing_in_base": 0, "differ": []}
            h_base, h_other = hashlib.sha256(), hashlib.sha256()
            for key in shards:
                small = dict(read_rows(o_files[art][key]))
                rec["rows_other"] += len(small)
                found = {sid: text for sid, text in read_rows(b_files[art][key]) if sid in small}
                for sid in sorted(small):
                    if sid not in found:
                        rec["missing_in_base"] += 1
                        continue
                    rec["rows_compared"] += 1
                    h_other.update(small[sid].encode("utf-8") + b"\n")
                    h_base.update(found[sid].encode("utf-8") + b"\n")
                    if small[sid] == found[sid]:
                        rec["rows_equal"] += 1
                    elif len(rec["differ"]) < SHOWN_DIFFERENCES:
                        rec["differ"].append(sid)
            rec["sha256_base"], rec["sha256_other"] = h_base.hexdigest(), h_other.hexdigest()
            rec["equal"] = rec["rows_equal"] == rec["rows_compared"] == rec["rows_other"] and rec["rows_other"] > 0
            report["artefacts"][f"{lang}/{art}"] = rec
            report["all_equal"] = report["all_equal"] and rec["equal"]
    if not report["artefacts"]:
        report["all_equal"] = False
        report["note"] = "the runs share no artefact"
    return report


# -------------------------------------------------------------------------------------------- bf16


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson's r, or None when it is undefined (fewer than three pairs, or a constant series)."""
    if len(xs) < 3:
        return None
    try:
        return statistics.correlation(xs, ys)
    except statistics.StatisticsError:
        return None


def stage_check(stage: str, base: Path, other: Path, lang: str, threshold: float) -> dict | None:
    """The bf16 agreement of one stage's text values, or None when either run lacks the artefact."""
    how, names = BF16_VALUES[stage]
    b_files, o_files = artefact_files(base, lang).get(stage), artefact_files(other, lang).get(stage)
    if not b_files or not o_files:
        return None
    full, half = {}, {}
    for key in sorted(set(b_files) & set(o_files)):
        full.update(read_values(b_files[key], how, names))
        half.update(read_values(o_files[key], how, names))
    out: dict = {"lang": lang, "texts_fp32": len(full), "texts_bf16": len(half), "values": {}}
    for name in names:
        common = sorted(s for s in half if name in half[s] and name in full.get(s, {}))
        xs, ys = [full[s][name] for s in common], [half[s][name] for s in common]
        r = pearson(xs, ys)
        out["values"][name] = {"pairs": len(common), "r": r,
                               "max_abs_difference": max((abs(a - b) for a, b in zip(xs, ys, strict=True)),
                                                         default=None),
                               "passes": None if r is None else r >= threshold}
    # The verdict reads the first value with pairs: the registered mean, else its all-words form (names unset).
    primary = next((n for n in names if out["values"][n]["pairs"]), None)
    out["primary"] = primary
    out["passes"] = out["values"][primary]["passes"] if primary else None
    return out


def own_precision_checks(work: Path, lang: str, stage: str) -> list:
    """The precision_check the stage itself recorded in each shard's timing record (surprisal_xglm)."""
    found = []
    timing = Path(work) / lang / "_timing"
    for path in sorted(timing.glob(f"{stage}-shard-*-of-*.json")) if timing.is_dir() else []:
        rec = json.loads(path.read_text(encoding="utf-8"))
        check = (rec.get("counts") or {}).get("precision_check")
        if check is not None:
            found.append({"shard": rec.get("shard"), "check": check})
    return found


def compare_bf16(base: Path, other: Path, threshold: float, langs: Mapping[str, str]) -> dict:
    """The P08 check for each model; see the module docstring."""
    report: dict = {"base_fp32": str(base), "other_bf16": str(other), "threshold": threshold, "models": {}}
    verdicts = []
    for stage, lang in langs.items():
        rec = stage_check(stage, base, other, lang, threshold)
        if rec is None:
            report["models"][stage] = {"lang": lang, "status": "not compared: an artefact is missing"}
            continue
        if stage == "surprisal_xglm":
            rec["stage_own_checks"] = own_precision_checks(other, lang, stage)
        if stage == "coref_corpipe":
            rec["definition"] = "share of adjacent sentence pairs linked by a chain (PENDING the Feature Specification)"
        report["models"][stage] = rec
        verdicts.append(rec["passes"])
    report["all_pass"] = bool(verdicts) and all(v is True for v in verdicts)
    return report


# -------------------------------------------------------------------------------------------- main


def _write(path: Path, rec: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {**rec, "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "code_commit": os.environ.get("INTRACT_CODE_COMMIT", "unknown")}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    """Command line; see the module docstring."""
    p = argparse.ArgumentParser(prog="compare_runs.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("rows", "bf16"):
        s = sub.add_parser(name)
        s.add_argument("--base", type=Path, required=True)
        s.add_argument("--other", type=Path, required=True)
        s.add_argument("--out", type=Path, required=True)
    sub.choices["rows"].add_argument("--lang", action="append", default=None)
    default_config = Path(os.environ["INTRACT_CODE"]) / "config" if os.environ.get("INTRACT_CODE") else None
    sub.choices["bf16"].add_argument("--config", type=Path, default=default_config)
    args = p.parse_args(argv)
    if args.cmd == "rows":
        if args.lang:
            langs = args.lang
        elif args.other.is_dir():
            langs = sorted(d.name for d in args.other.iterdir() if d.is_dir() and not d.name.startswith("_"))
        else:
            langs = []
        report = compare_rows(args.base, args.other, langs)
        _write(args.out, report)
        bad = [k for k, v in report["artefacts"].items() if not v["equal"]]
        if report["all_equal"]:
            verdict = "all equal"
        else:
            verdict = "differ: " + ", ".join(bad) if bad else report.get("note", "nothing compared")
        print(f"compare_runs rows: {len(report['artefacts'])} artefacts, {verdict}")
        return 0 if report["all_equal"] else 1
    if args.config is None:
        p.error("--config is required when INTRACT_CODE is not set")
    with open(args.config / "stages" / "surprisal_xglm.toml", "rb") as fh:
        threshold = float(tomllib.load(fh)["precision"]["agreement_threshold"])
    report = compare_bf16(args.base, args.other, threshold,
                          {"surprisal_xglm": "en-us", "coref_corpipe": "en-us", "qe_metricx": "de-de"})
    _write(args.out, report)
    for stage, rec in report["models"].items():
        print(f"compare_runs bf16: {stage}: {rec.get('status') or ('passes' if rec['passes'] else 'fails')}")
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
