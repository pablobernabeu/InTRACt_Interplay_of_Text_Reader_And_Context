"""Targeted checks of version 2026-09-17: the new options and the new refusals.

    python test_revised_version.py
    python test_revised_version.py <v1 script> <v2 script> <7 Aug output>

With no arguments it uses the two scripts in the folder above and skips the scenario
that redraws the manifest from the 7 August output, which is not in this repository.
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
OUT_CSV = "lets_story_summary_data_for_oxford.csv"
OUT_HTML = "lets_story_manifest_for_oxford.html"


def _arg(i, default):
    return sys.argv[i] if len(sys.argv) > i else default


V1 = _arg(1, os.path.join(SCRIPTS, "lets_story_summary_2026-08-05.py"))
V2 = _arg(2, os.path.join(SCRIPTS, "lets_story_summary.py"))
EXAMPLE = _arg(3, "")
sys.path.insert(0, HERE)
from synth_export import synth, write_csv, HEADER

R = {}


def fresh(name):
    d = os.path.join(HERE, "v3_" + name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    return d


def run(script, folder, inputs):
    p = subprocess.run([sys.executable, script] + inputs, cwd=folder,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    rows, out = [], {}
    f = os.path.join(folder, OUT_CSV)
    if os.path.exists(f):
        with open(f, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))[1:]
        for r in rows:
            out[(r[0], r[1], r[2], r[3])] = r[4]
    html = ""
    if os.path.exists(os.path.join(folder, OUT_HTML)):
        html = open(os.path.join(folder, OUT_HTML), encoding="utf-8").read()
    return p, out, rows, html


# ---- a single file with no header at all --------------------------------------------
rows_h, _ = synth(500, 100, seed=22)
d = fresh("headerless_single")
write_csv(os.path.join(d, "export.csv"), rows_h, with_header=False)
p, o, rows, _ = run(V2, d, ["export.csv"])
R["single file with no header row"] = {
    "exit": p.returncode, "wrote anything": bool(rows),
    "message": (p.stdout + p.stderr).strip().splitlines()[-3:]}

# ---- no file has the reading-time column --------------------------------------------
d = fresh("no_time_anywhere")
write_csv(os.path.join(d, "export.csv"), rows_h,
          header=[c for c in HEADER if c != "time_spent_reading"])
p, o, rows, html = run(V2, d, ["export.csv"])
R["reading-time column absent everywhere"] = {
    "exit": p.returncode,
    "verdict in the manifest": "The reading-time column is not in this export." in html,
    "uncovered count": o.get(("identifiers and integrity", "", "",
                              "sessions in files without the reading-time column")),
    "sessions": o.get(("overview", "", "", "sessions"))}

# ---- NA / NULL tokens in the reading-time column ------------------------------------
rows_na, _ = synth(300, 60, seed=23)
for i, r in enumerate(rows_na):
    if i % 3 == 0:
        r["time_spent_reading"] = ["NA", "NULL", "N/A"][i % 3 if i % 3 else 0]
d1, d2 = fresh("na_tokens_v1"), fresh("na_tokens_v2")
for d in (d1, d2):
    write_csv(os.path.join(d, "export.csv"), rows_na)
p1, o1, _, _ = run(V1, d1, ["export.csv"])
p2, o2, _, _ = run(V2, d2, ["export.csv"])
sec = "reading time, checked only for whether it can be used"
R["NA in the reading-time column"] = {
    "rows written NA": sum(1 for r in rows_na if r["time_spent_reading"] == "NA"),
    "v1 counted as 'not a number'": o1.get((sec, "not a number", "cannot be used", "sessions")),
    "v1 counted as 'empty'": o1.get((sec, "empty", "cannot be used", "sessions")),
    "v2 counted as 'not a number'": o2.get((sec, "not a number", "cannot be used", "sessions")),
    "v2 counted as 'empty'": o2.get((sec, "empty", "cannot be used", "sessions"))}

# ---- the old summary file still redraws (backward compatibility) ---------------------
if EXAMPLE and os.path.exists(EXAMPLE):
 d = fresh("manifest_from_v1_output")
 shutil.copy(EXAMPLE, os.path.join(d, "old_summary.csv"))
 p = subprocess.run([sys.executable, V2, "--manifest-from", "old_summary.csv"], cwd=d,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
 rebuilt = os.path.join(d, "old_summary_manifest_rebuilt.html")
 R["--manifest-from on the 7 August output"] = {
    "exit": p.returncode, "page written": os.path.exists(rebuilt),
    "page size": os.path.getsize(rebuilt) if os.path.exists(rebuilt) else 0,
    "verdict drawn": ("usable number" in open(rebuilt, encoding="utf-8").read()
                      if os.path.exists(rebuilt) else None)}

else:
 R["--manifest-from on the 7 August output"] = "skipped: the 7 August output was not given"

# ---- a run over a folder twice, which now must not read its own output ---------------
d = fresh("run_twice")
rows_t, truth_t = synth(800, 200, seed=24)
write_csv(os.path.join(d, "export.csv"), rows_t)
p1, o1, _, _ = run(V2, d, [d])
p2, o2, _, _ = run(V2, d, [d])
R["folder run twice"] = {
    "truth sessions": truth_t["sessions"],
    "first run": o1.get(("overview", "", "", "sessions")),
    "second run": o2.get(("overview", "", "", "sessions"))}

# ---- timing: how long the new checks cost on a large export -------------------------
import time
rows_big, truth_big = synth(120000, 8000, seed=25)
d1, d2 = fresh("big_v1"), fresh("big_v2")
for d in (d1, d2):
    write_csv(os.path.join(d, "export.csv"), rows_big)
t0 = time.time()
p1, o1, _, _ = run(V1, d1, ["export.csv"])
t1 = time.time()
p2, o2, _, _ = run(V2, d2, ["export.csv"])
t2 = time.time()
R["large export (%d rows)" % truth_big["sessions"]] = {
    "v1 seconds": round(t1 - t0, 1), "v2 seconds": round(t2 - t1, 1),
    "v1 sessions/accounts/texts": [o1.get(("overview", "", "", m)) for m in
                                   ("sessions", "distinct accounts", "distinct texts")],
    "v2 sessions/accounts/texts": [o2.get(("overview", "", "", m)) for m in
                                   ("sessions", "distinct accounts", "distinct texts")],
    "truth": truth_big,
    "figures v1 reported that v2 changed": {str(k): (v, o2.get(k)) for k, v in o1.items()
                                            if k in o2 and o2[k] != v
                                            and k[3] not in ("summary produced on", "script version")}}

print(json.dumps(R, indent=1, default=str))
