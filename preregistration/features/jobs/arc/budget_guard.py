"""Tally L40S GPU-hours from the job ledger and Slurm accounting, and refuse a submission past a cap.

    python -I budget_guard.py report [--ledger CSV ...] [--sacct-file FILE | --no-sacct]
    python -I budget_guard.py check --cap HOURS --add HOURS [--basis committed|requested] [--ledger CSV ...]

The ledger is the CSV that submit_chain.sh appends one row to per submitted job, with the pre-submission ledger's
columns (job_id, cluster, strand, purpose, gres, walltime, gpu_hours_requested, submitted_utc, outputs,
postprocess_command). A row counts when its gres requests an L40S by name ("gpu:l40s", as in "gpu:l40s:1"); a row that
mentions the L40S only in a comment, such as the pre-submission "gpu:1 (devel partition = RTX 8000, not L40S)", does
not. Jobs are told apart by cluster and job id, since htc and arc number their jobs independently.

* requested: the GPU-hours each job asked for (its gpu_hours_requested, else walltime x GPUs).
* used: what Slurm accounting reports, elapsed time x allocated GPUs, summed over every task of an array and every
  allocation of a requeued task (sacct --duplicates).
* committed: used for every finished task, plus the requested share of every task not yet finished, which is
  what the account could still be charged in the worst case.

`check` exits with status 3, and submit_chain.sh submits nothing, when the chosen basis plus --add would exceed
--cap, or when any number it needs is not finite: the guard fails closed. It only adds up a ledger against a cap.
The protocol's budget guard after acceptance (preregistration.qmd, Timeline) is a different rule: it projects the
GPU total from a pilot on 1 per cent of the catalogue and, if the projection exceeds 400 L40S GPU-hours, applies
three steps in order (bf16 for XGLM-4.5B, MetricX-24 and the coreference resolver if their text means agree with
full precision at r >= .995 on the public benchmark; a smaller coreference model; the projected-coreference anchor
on the keyed sample alone). The dry run's aggregate_timing stage makes the projection that rule needs. Standard
library only: this script runs on a login node with the module Python, before any environment exists.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

LEDGER_COLUMNS = ("job_id", "cluster", "strand", "purpose", "gres", "walltime", "gpu_hours_requested",
                  "submitted_utc", "outputs", "postprocess_command")
SACCT_FORMAT = "Cluster,JobID,JobIDRaw,State,ElapsedRaw,AllocTRES,ReqTRES,Submit"
# Slurm states after which a task is charged no more (sacct --helpformat; "CANCELLED by <uid>" is cut to its word).
# REQUEUED is not among them: the task runs again, in a new allocation that sacct --duplicates lists after it.
FINISHED = {"COMPLETED", "FAILED", "TIMEOUT", "CANCELLED", "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "BOOT_FAIL",
            "DEADLINE", "REVOKED"}
GPU_TRES = re.compile(r"gres/gpu(?::[^=,]+)?=(\d+)")
L40S_GRES = re.compile(r"(?<![A-Za-z0-9])gpu:l40s(?![A-Za-z0-9])", re.IGNORECASE)
WALLTIME = re.compile(r"^\s*(?:(\d+)-)?(\d+)(?::(\d+))?(?::(\d+))?(?!\d)")
# sacct with --duplicates can also return an older job that had the same id before the ids were reset; one whose
# submission precedes the ledger's row by more than this belongs to that older job.
SUBMIT_SLACK_SECONDS = 86400


class LedgerError(ValueError):
    """A ledger row, a time or an accounting line that the guard cannot read with certainty."""


@dataclass
class LedgerJob:
    """One ledger row that asked for an L40S."""

    job_id: str
    cluster: str
    purpose: str
    gres: str
    walltime: str
    requested: float
    submitted_utc: str = ""


@dataclass
class Tally:
    """Requested, used and committed L40S GPU-hours over a set of ledger jobs."""

    requested: float = 0.0
    used: float = 0.0
    committed: float = 0.0
    jobs: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        """The tally for printing and records."""
        return {"requested": round(self.requested, 3), "used": round(self.used, 3),
                "committed": round(self.committed, 3), "jobs": self.jobs}


def walltime_hours(text: str) -> float:
    """Hours in a Slurm time limit: "MM", "MM:SS", "HH:MM:SS", "D-HH", "D-HH:MM" or "D-HH:MM:SS".

    Text after the time is ignored, since the pre-submission ledger writes such notes as "04:00:00 per task".
    """
    m = WALLTIME.match(text or "")
    if not m:
        raise LedgerError(f"{text!r} is not a Slurm time limit")
    days, a, b, c = m.groups()
    fields = [int(x) for x in (a, b, c) if x is not None]
    if days is not None:
        while len(fields) < 3:
            fields.append(0)  # after a day count, the fields are hours, then minutes, then seconds
        h, mi, s = fields
    elif len(fields) == 1:
        h, mi, s = 0, fields[0], 0
    elif len(fields) == 2:
        h, mi, s = 0, fields[0], fields[1]
    else:
        h, mi, s = fields
    return int(days or 0) * 24 + h + mi / 60 + s / 3600


def gres_gpus(gres: str) -> int:
    """GPUs in a gres request such as "gpu:l40s:1" or "gpu:l40s:2" (one when no count is given)."""
    m = re.search(r"gpu(?::[A-Za-z0-9_]+)?:(\d+)\b", gres)
    return int(m.group(1)) if m else 1


def is_l40s(gres: str) -> bool:
    """Whether a ledger row's gres requests an L40S by name ("gpu:l40s"), not merely mentions one."""
    return bool(L40S_GRES.search(gres or ""))


def finite_hours(value: float, what: str) -> float:
    """A non-negative, finite number of hours; anything else stops the guard (it must fail closed)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise LedgerError(f"{what} is {value!r}, not a finite number of hours >= 0")
    return float(value)


def read_ledger(paths: Iterable[Path]) -> list[LedgerJob]:
    """The L40S rows of one or more ledgers; a (cluster, job id) that appears twice is counted once (the first)."""
    jobs, seen = [], set()
    for path in paths:
        path = Path(path)
        if not path.is_file():
            continue
        with open(path, newline="", encoding="utf-8") as fh:
            for n, row in enumerate(csv.DictReader(fh), start=2):
                missing = [c for c in LEDGER_COLUMNS if c not in row]
                if missing:
                    raise LedgerError(f"{path}: the ledger lacks columns {missing}")
                gres = row["gres"] or ""
                cluster = (row["cluster"] or "htc").strip()
                key = (cluster, (row["job_id"] or "").strip())
                if not is_l40s(gres) or key in seen:
                    continue
                seen.add(key)
                req = (row["gpu_hours_requested"] or "").strip()
                where = f"{path.name}, line {n} (job {key[1]})"
                if req:
                    try:
                        requested = float(req)
                    except ValueError as exc:
                        raise LedgerError(f"{where}: gpu_hours_requested {req!r} is not a number") from exc
                else:
                    requested = walltime_hours(row["walltime"]) * gres_gpus(gres)
                jobs.append(LedgerJob(job_id=key[1], cluster=cluster, purpose=row["purpose"], gres=gres,
                                      walltime=row["walltime"], requested=finite_hours(requested, where),
                                      submitted_utc=(row["submitted_utc"] or "").strip()))
    return jobs


def parse_sacct(text: str) -> dict[tuple[str | None, str], list[dict]]:
    """sacct -X -D -n -P --format=Cluster,JobID,JobIDRaw,State,ElapsedRaw,AllocTRES,ReqTRES,Submit, by ledger job.

    Lines are grouped by (cluster, job id). An array task's JobID is "<array id>_<task>", and the ledger records the
    array id, so tasks are grouped by the part before the underscore. A pending array shows as "<id>_[0-3]", one line
    for the tasks not yet started. A requeued task appears once per allocation. Saved output in the older six-field
    form (no Cluster, no Submit) is read with the cluster left open.
    """
    out: dict[tuple[str | None, str], list[dict]] = defaultdict(list)
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) >= 8:
            cluster, job_id, _raw, state, elapsed, alloc, req, submit = fields[:8]
        elif len(fields) >= 6:
            cluster, submit = None, ""
            job_id, _raw, state, elapsed, alloc, req = fields[:6]
        else:
            raise LedgerError(f"sacct line {line!r} has {len(fields)} fields")
        base, _, task = job_id.partition("_")
        pending_range = task.startswith("[")
        n_tasks = 1
        if pending_range:
            n_tasks = sum(_range_size(part) for part in task.strip("[]").split("%")[0].split(","))
        try:
            seconds = int(elapsed or 0)
        except ValueError as exc:
            raise LedgerError(f"sacct line {line!r}: ElapsedRaw {elapsed!r} is not a whole number") from exc
        gpus = _gpus(alloc) or _gpus(req)
        out[(cluster or None, base)].append({"task": job_id, "state": (state.split() or [""])[0],
                                             "elapsed": seconds, "gpus": gpus, "tasks": n_tasks,
                                             "submit": submit.strip()})
    return dict(out)


def _range_size(part: str) -> int:
    if "-" in part:
        a, b = part.split("-", 1)
        return int(b) - int(a) + 1
    return 1 if part else 0


def _gpus(tres: str) -> int:
    m = GPU_TRES.search(tres or "")
    return int(m.group(1)) if m else 0


def _epoch(stamp: str) -> float | None:
    """Seconds since the epoch of "2026-11-03T05:01:34", with or without a final Z, read as UTC; None otherwise.

    The ledger writes UTC and sacct the cluster's local time; job_rows allows a day of slack for the difference.
    """
    try:
        return float(calendar.timegm(time.strptime(stamp.strip().rstrip("Z"), "%Y-%m-%dT%H:%M:%S")))
    except ValueError:
        return None


def run_sacct(jobs: Sequence[LedgerJob]) -> str:
    """sacct's parsable output for the jobs, every allocation of a requeued task included (--duplicates)."""
    if not jobs:
        return ""
    clusters = sorted({j.cluster for j in jobs})
    cmd = ["sacct", f"--clusters={','.join(clusters)}", "-X", "-D", "-n", "-P", f"--format={SACCT_FORMAT}",
           "-j", ",".join(sorted({j.job_id for j in jobs}))]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def job_rows(job: LedgerJob, accounting: Mapping[tuple[str | None, str], list[dict]]) -> list[dict]:
    """The accounting lines of one ledger job: its cluster's, and none submitted long before its ledger row."""
    rows = list(accounting.get((job.cluster, job.job_id), [])) + list(accounting.get((None, job.job_id), []))
    since = _epoch(job.submitted_utc) if job.submitted_utc else None
    if since is None:
        return rows
    kept = []
    for r in rows:
        # sacct prints Submit in the cluster's local time without a zone, so the comparison allows a day either way
        when = _epoch(r["submit"]) if r.get("submit") else None
        if when is None or when >= since - SUBMIT_SLACK_SECONDS:
            kept.append(r)
    return kept


def tally(jobs: Sequence[LedgerJob], accounting: Mapping[tuple[str | None, str], list[dict]] | None) -> Tally:
    """Requested, used and committed GPU-hours; without accounting every job is committed at its request."""
    t = Tally()
    for job in jobs:
        rows = job_rows(job, accounting or {})
        latest: dict[str, dict] = {}
        for r in rows:  # sacct lists a requeued task's allocations in order, so the last one is current
            latest[r["task"]] = r
        n_tasks = sum(r["tasks"] for r in latest.values()) or 1
        per_task = job.requested / n_tasks
        default_gpus = gres_gpus(job.gres)
        used = sum(r["elapsed"] / 3600 * (r["gpus"] or default_gpus) for r in rows
                   if r["tasks"] == 1 and r["elapsed"] > 0)
        unfinished = sum(r["tasks"] for r in latest.values() if r["state"] not in FINISHED)
        running = sum(r["elapsed"] / 3600 * (r["gpus"] or default_gpus) for r in latest.values()
                      if r["state"] not in FINISHED and r["tasks"] == 1)
        if not rows:  # not yet in accounting: assume the whole request
            committed, unfinished = job.requested, 1
        else:
            # A running task is committed at its full request (it may run to its limit), so the elapsed time of
            # its current allocation, already in `used`, is not added twice.
            committed = used - running + unfinished * per_task
        for value, what in ((used, "used"), (committed, "committed")):
            finite_hours(value, f"job {job.cluster}/{job.job_id}: {what}")
        t.requested += job.requested
        t.used += used
        t.committed += committed
        t.jobs.append({"job_id": job.job_id, "cluster": job.cluster, "purpose": job.purpose,
                       "requested": round(job.requested, 3), "used": round(used, 3),
                       "committed": round(committed, 3), "tasks": n_tasks, "allocations": len(rows),
                       "unfinished_tasks": unfinished, "states": sorted({r["state"] for r in rows})})
    return t


def default_ledgers(environ: Mapping[str, str] | None = None) -> list[Path]:
    """$INTRACT_LEDGER (jobs/arc/env.sh) when set."""
    environ = os.environ if environ is None else environ
    return [Path(environ["INTRACT_LEDGER"])] if environ.get("INTRACT_LEDGER") else []


def main(argv: list[str] | None = None) -> int:
    """Command line; see the module docstring."""
    p = argparse.ArgumentParser(prog="budget_guard.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("report", "check"):
        s = sub.add_parser(name)
        s.add_argument("--ledger", type=Path, action="append", help="a ledger CSV (repeatable); $INTRACT_LEDGER")
        src = s.add_mutually_exclusive_group()
        src.add_argument("--sacct-file", type=Path, help="saved sacct -P output instead of calling sacct")
        src.add_argument("--no-sacct", action="store_true", help="commit every job at its request")
        if name == "check":
            s.add_argument("--cap", type=float, required=True, help="L40S GPU-hours that may not be exceeded")
            s.add_argument("--add", type=float, required=True, help="GPU-hours the new submission requests")
            s.add_argument("--basis", choices=("committed", "requested"), default="committed")
    args = p.parse_args(argv)

    ledgers = args.ledger or default_ledgers()
    if not ledgers:
        p.error("no ledger: pass --ledger or set INTRACT_LEDGER")
    try:
        if args.cmd == "check":
            finite_hours(args.cap, "--cap")
            finite_hours(args.add, "--add")
        jobs = read_ledger(ledgers)
        if args.no_sacct:
            accounting = None
        elif args.sacct_file:
            accounting = parse_sacct(args.sacct_file.read_text(encoding="utf-8"))
        else:
            accounting = parse_sacct(run_sacct(jobs))
        t = tally(jobs, accounting)
    except LedgerError as exc:
        # A number the guard cannot trust stops it with the refusal status, so nothing is submitted.
        print(f"budget_guard: refusing: {exc}", file=sys.stderr)
        return 3
    out = {"ledgers": [str(x) for x in ledgers], "l40s_gpu_hours": t.as_dict()}
    if args.cmd == "report":
        print(json.dumps(out, indent=1))
        return 0
    base = t.committed if args.basis == "committed" else t.requested
    proposed = base + args.add
    allowed = math.isfinite(proposed) and proposed <= args.cap
    out["check"] = {"basis": args.basis, "base": round(base, 3), "add": args.add, "proposed": round(proposed, 3),
                    "cap": args.cap, "allowed": allowed}
    print(json.dumps(out["check"] | {"requested": round(t.requested, 3), "used": round(t.used, 3),
                                     "committed": round(t.committed, 3)}, indent=1))
    if not allowed:
        print(f"budget_guard: refusing: {args.basis} {base:.2f} + {args.add:.2f} = {proposed:.2f} L40S GPU-hours "
              f"exceeds the cap of {args.cap:.2f}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
