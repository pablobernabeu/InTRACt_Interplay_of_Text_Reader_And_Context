"""Every malformed input that version 2026-08-05 could pass over in silence.

Each scenario writes a synthetic export with known ground truth into its own folder,
runs both versions of the script on it, and compares what each reported with the truth.
No real reading time is used anywhere: the generator in synth_export.py invents them.

    python test_malformed_inputs.py
    python test_malformed_inputs.py <v1 script> <v2 script> <real sample> <7 Aug output>

With no arguments it uses the two scripts in the folder above and skips the scenario
that needs the real 35-row sample, which is not in this repository.
"""
import csv
import gzip
import json
import os
import random
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
OUT_CSV = "lets_story_summary_data_for_oxford.csv"
OUT_HTML = "lets_story_manifest_for_oxford.html"


def _arg(i, default):
    return sys.argv[i] if len(sys.argv) > i else default


V1 = _arg(1, os.path.join(SCRIPTS, "lets_story_summary_2026-08-05.py"))
V2 = _arg(2, os.path.join(SCRIPTS, "lets_story_summary.py"))
SAMPLE = _arg(3, "")
EXAMPLE = _arg(4, "")
sys.path.insert(0, HERE)
from synth_export import synth, write_csv, HEADER

R = {}


def fresh(name):
    d = os.path.join(HERE, "v2_" + name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    return d


def run(script, folder, inputs):
    proc = subprocess.run([sys.executable, script] + inputs, cwd=folder,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    out, rows = {}, []
    p = os.path.join(folder, OUT_CSV)
    if os.path.exists(p):
        with open(p, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))[1:]
        for r in rows:
            out[(r[0], r[1], r[2], r[3])] = r[4]
    html = ""
    ph = os.path.join(folder, OUT_HTML)
    if os.path.exists(ph):
        html = open(ph, encoding="utf-8").read()
    return proc, out, rows, html


def ov(out, metric, scope=""):
    return out.get(((scope + ": " if scope else "") + "overview", "", "", metric))


def fr(out, metric):
    return out.get(("file record", "", "", metric))


def ident(out, metric):
    return out.get(("identifiers and integrity", "", "", metric))


def verdicts(html):
    return re.findall(r"(All [0-9,]+[^<]*usable number[^<]*|[0-9,]+ of [0-9,]+[^<]*"
                      r"usable number[^<]*|No session carries a usable number[^<]*|"
                      r"The reading-time column is not in this export\.)", html)


def excel_general(v):
    s = "%.5E" % v
    mant, exp = s.split("E")
    return f"{mant.rstrip('0').rstrip('.')}E+{int(exp):02d}"


# ---- 1. the real sample: v2 must not change any figure v1 reported -------------------
if SAMPLE and EXAMPLE and os.path.exists(SAMPLE):
 d1, d2 = fresh("sample_v1"), fresh("sample_v2")
 for d in (d1, d2):
    shutil.copy(SAMPLE, d)
 p1, o1, rows1, _ = run(V1, d1, [os.path.basename(SAMPLE)])
 p2, o2, rows2, _ = run(V2, d2, [os.path.basename(SAMPLE)])
 shared_changed = {k: (v, o2.get(k)) for k, v in o1.items()
                  if k in o2 and o2[k] != v and k[3] != "summary produced on"
                  and k[3] != "script version"}
 R["1. real 35-row sample"] = {
    "v1 exit": p1.returncode, "v2 exit": p2.returncode,
    "rows v1": len(rows1), "rows v2": len(rows2),
    "figures v1 reported that v2 changed": shared_changed,
    "v1 rows missing from v2": [k for k in o1 if k not in o2
                                and k[3] not in ("summary produced on",)],
    "new rows in v2": len([k for k in o2 if k not in o1]),
    "sessions / accounts / texts (v2)": [ov(o2, "sessions"), ov(o2, "distinct accounts"),
                                        ov(o2, "distinct texts")],
    "lines not accounted for (v2)": fr(o2, "lines not accounted for"),
    "v2 warnings": [l for l in p2.stdout.splitlines() if l.startswith(("Warning", "Note"))],
 }

else:
 R["1. real 35-row sample"] = "skipped: the real sample was not given"

# ---- 2. clean data: controls still exact ---------------------------------------------
rows_, truth = synth(20000, 3000, seed=1)
d = fresh("clean_single")
write_csv(os.path.join(d, "export.csv"), rows_)
p, o, _, html = run(V2, d, ["export.csv"])
R["2a. clean single file"] = {
    "exit": p.returncode, "truth": truth,
    "v2": [ov(o, "sessions"), ov(o, "distinct accounts"), ov(o, "distinct texts")],
    "lines not accounted for": fr(o, "lines not accounted for"),
    "verdict": verdicts(html)}

d = fresh("clean_parts")
third = len(rows_) // 3
write_csv(os.path.join(d, "part1.csv"), rows_[:third])
write_csv(os.path.join(d, "part2.csv"), rows_[third:2 * third])
write_csv(os.path.join(d, "part3.csv.gz"), rows_[2 * third:], gz=True)
p, o, _, _ = run(V2, d, ["part1.csv", "part2.csv", "part3.csv.gz"])
R["2b. clean three parts, one gzipped"] = {
    "exit": p.returncode, "truth": truth,
    "v2": [ov(o, "sessions"), ov(o, "distinct accounts"), ov(o, "distinct texts")],
    "lines not accounted for": fr(o, "lines not accounted for")}

rows_t, truth_t = synth(5000, 800, seed=2, title_trouble=True)
d = fresh("clean_messy_titles")
write_csv(os.path.join(d, "export.csv"), rows_t)
p, o, _, _ = run(V2, d, ["export.csv"])
R["2c. titles with commas, quotes and line breaks"] = {
    "exit": p.returncode, "truth": truth_t,
    "v2": [ov(o, "sessions"), ov(o, "distinct accounts"), ov(o, "distinct texts")],
    "misaligned": fr(o, "rows skipped because the field count did not match the header"),
    "rows set aside as over-long": fr(o, "rows set aside because one field was implausibly long, which is what an unclosed quote produces"),
    "lines not accounted for": fr(o, "lines not accounted for")}

# ---- 3. float identifiers (was CS-01) ------------------------------------------------
rows_f, truth_f = synth(50000, 3000, seed=3)
d1, d2 = fresh("float_ids_v1"), fresh("float_ids_v2")
for d in (d1, d2):
    write_csv(os.path.join(d, "export.csv"), rows_f, uid_format=excel_general)
p1, o1, _, _ = run(V1, d1, ["export.csv"])
p2, o2, _, html2 = run(V2, d2, ["export.csv"])
R["3. account ids as 1.23457E+18 (50,000 accounts)"] = {
    "true accounts": truth_f["accounts"],
    "v1 distinct accounts": ov(o1, "distinct accounts"),
    "v2 distinct accounts": ov(o2, "distinct accounts"),
    "v1 said anything?": any("scientific" in l for l in (p1.stdout + p1.stderr).splitlines()),
    "v2 rows flagged": ident(o2, "sessions whose account identifier is in scientific notation, which loses digits"),
    "v2 'account figures reliable'": ident(o2, "account figures reliable"),
    "v2 warning": [l for l in p2.stdout.splitlines() if "scientific notation" in l][:1]}

# ---- 4. a part with no header (was CS-02) -------------------------------------------
rows_h, truth_h = synth(2000, 400, seed=4)
half = len(rows_h) // 2
d1, d2 = fresh("headerless_v1"), fresh("headerless_v2")
for d in (d1, d2):
    write_csv(os.path.join(d, "part1.csv"), rows_h[:half])
    write_csv(os.path.join(d, "part2.csv"), rows_h[half:], with_header=False)
p1, o1, rows1, _ = run(V1, d1, ["part1.csv", "part2.csv"])
p2, o2, rows2, _ = run(V2, d2, ["part1.csv", "part2.csv"])
first = rows_h[half]
def leaked(rows):
    vals = {r[4] for r in rows}
    return sorted(v for v in (str(first["user_id"]), first["finished_reading_at"],
                              first["time_spent_reading"]) if v in vals)
R["4. second part has no header row"] = {
    "v1 exit": p1.returncode, "v2 exit": p2.returncode,
    "v1 wrote a deliverable": bool(rows1), "v2 wrote a deliverable": bool(rows2),
    "v1 leaked into the summary CSV": leaked(rows1),
    "v2 leaked into the summary CSV": leaked(rows2),
    "v2 message": p2.stdout.strip().splitlines()[-3:] + p2.stderr.strip().splitlines()[:4]}

# ---- 5. a part without the reading-time column (was CS-03) --------------------------
rows_m, truth_m = synth(2000, 400, seed=5)
half = len(rows_m) // 2
d1, d2 = fresh("no_time_col_v1"), fresh("no_time_col_v2")
for d in (d1, d2):
    write_csv(os.path.join(d, "part1.csv"), rows_m[:half])
    write_csv(os.path.join(d, "part2.csv"), rows_m[half:],
              header=[c for c in HEADER if c != "time_spent_reading"])
p1, o1, _, html1 = run(V1, d1, ["part1.csv", "part2.csv"])
p2, o2, _, html2 = run(V2, d2, ["part1.csv", "part2.csv"])
R["5. one part lacks time_spent_reading"] = {
    "total sessions": ov(o2, "sessions"), "rows with the column": half,
    "v1 verdict": verdicts(html1)[:1], "v2 verdict": verdicts(html2)[:1],
    "v2 uncovered count": ident(o2, "sessions in files without the reading-time column"),
    "v2 per-file column present": [o2.get(("files", f, "", "reading-time column present"))
                                   for f in ("part1.csv", "part2.csv")],
    "v2 warning": [l for l in p2.stdout.splitlines() if "reading-time check" in l][:1]}

# ---- 6. an unclosed quote (was CS-04) ------------------------------------------------
rows_q, truth_q = synth(2000, 400, seed=6)
d1, d2 = fresh("unclosed_quote_v1"), fresh("unclosed_quote_v2")
for d in (d1, d2):
    path = os.path.join(d, "export.csv")
    write_csv(path, rows_q)
    with open(path, encoding="utf-8", newline="") as fh:
        lines = fh.read().split("\r\n")
    parts = lines[200].split(",")
    parts[HEADER.index("story_title")] = '"' + parts[HEADER.index("story_title")]
    lines[200] = ",".join(parts)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\r\n".join(lines))
p1, o1, _, _ = run(V1, d1, ["export.csv"])
p2, o2, _, _ = run(V2, d2, ["export.csv"])
R["6. one unclosed quote at line 200"] = {
    "truth sessions": truth_q["sessions"],
    "v1 sessions reported": ov(o1, "sessions"),
    "v1 skipped": fr(o1, "rows skipped because the field count did not match the header"),
    "v1 exit": p1.returncode,
    "v2 exit": p2.returncode,
    "v2 wrote a deliverable": bool(o2),
    "v2 sessions reported": ov(o2, "sessions"),
    "v2 rows set aside as over-long": fr(o2, "rows set aside because one field was implausibly long, which is what an unclosed quote produces"),
    "v2 lines those rows had swallowed": fr(o2, "lines those rows had swallowed"),
    "v2 lines not accounted for": fr(o2, "lines not accounted for"),
    "v2 message": [l for l in (p2.stdout + p2.stderr).splitlines() if "quot" in l.lower()][:2]}

# ---- 7. blank story_id (was CS-06) ---------------------------------------------------
rows_b, _ = synth(5000, 800, seed=7)
rng = random.Random(8)
blanked = 0
for r in rows_b:
    if rng.random() < 0.05:
        r["story_id"] = ""
        blanked += 1
true_texts = len({r["story_id"] for r in rows_b if r["story_id"]})
d1, d2 = fresh("blank_story_id_v1"), fresh("blank_story_id_v2")
for d in (d1, d2):
    write_csv(os.path.join(d, "export.csv"), rows_b)
p1, o1, _, _ = run(V1, d1, ["export.csv"])
p2, o2, _, _ = run(V2, d2, ["export.csv"])
R["7. story_id blank on 5 per cent of rows"] = {
    "truth blank rows": blanked, "truth distinct story_ids": true_texts,
    "v1 'no story identifier'": ov(o1, "sessions with no story identifier"),
    "v1 distinct texts": ov(o1, "distinct texts"),
    "v2 'no story identifier'": ov(o2, "sessions with no story identifier"),
    "v2 distinct texts": ov(o2, "distinct texts"),
    "v2 blank-with-title count": ident(o2, "sessions with an empty story identifier but a story title present")}

# ---- 8. new behaviour: decimal commas, age-band variants, twins and a stray .txt -----
rows_d, truth_d = synth(3000, 500, seed=9)
d1, d2 = fresh("semicolon_decimal_v1"), fresh("semicolon_decimal_v2")
for d in (d1, d2):
    with open(os.path.join(d, "export.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(HEADER)
        for r in rows_d:
            row = []
            for c in HEADER:
                v = str(r[c])
                if c == "time_spent_reading":
                    v = v + ",5"          # a decimal comma
                row.append(v)
            w.writerow(row)
p1, o1, _, html1 = run(V1, d1, ["export.csv"])
p2, o2, _, html2 = run(V2, d2, ["export.csv"])
R["8a. semicolon-separated with decimal commas"] = {
    "v1 'not a number'": o1.get(("reading time, checked only for whether it can be used",
                                 "not a number", "cannot be used", "sessions")),
    "v2 'not a number'": o2.get(("reading time, checked only for whether it can be used",
                                 "not a number", "cannot be used", "sessions")),
    "v1 verdict": verdicts(html1)[:1], "v2 verdict": verdicts(html2)[:1],
    "v2 decimal mark recorded": o2.get(("files", "export.csv", "", "decimal mark"))}

rows_v, _ = synth(3000, 500, seed=10)
for r in rows_v:
    if r["user_age_group"] == "Age 7-8":
        r["user_age_group"] = "age 7 - 8"        # a spelling variant
want = sum(1 for r in rows_v if r["user_age_group"] in ("age 7 - 8", "Age 9+"))
d1, d2 = fresh("band_variant_v1"), fresh("band_variant_v2")
for d in (d1, d2):
    write_csv(os.path.join(d, "export.csv"), rows_v)
p1, o1, _, _ = run(V1, d1, ["export.csv"])
p2, o2, _, _ = run(V2, d2, ["export.csv"])
scope = "Age 7-8 and Age 9+ only"
R["8b. age band written 'age 7 - 8'"] = {
    "sessions that should reach Part 2": want,
    "v1 Part 2 sessions": ov(o1, "sessions", scope),
    "v2 Part 2 sessions": ov(o2, "sessions", scope),
    "v2 labels recorded": {k[1]: v for k, v in o2.items()
                           if k[0] == "identifiers and integrity" and "Part 2" in k[3]}}

d = fresh("twin_and_txt")
rows_w, truth_w = synth(2000, 400, seed=11)
write_csv(os.path.join(d, "export.csv"), rows_w)
shutil.copy(os.path.join(d, "export.csv"), os.path.join(d, "export_copy.csv"))
with open(os.path.join(d, "README.txt"), "w", encoding="utf-8") as fh:
    fh.write("This folder holds the export.\nPlease read the instructions.\n")
p1, o1, _, _ = run(V1, os.path.join(HERE, "twin_and_txt_v1") if False else d, [d])
R["8c. folder with a duplicate copy and a README.txt (v1)"] = {
    "truth sessions": truth_w["sessions"], "v1 sessions": ov(o1, "sessions"),
    "v1 duplicate rows reported": fr(o1, "rows identical to an earlier row in every column the script reads")}
p2, o2, _, _ = run(V2, d, [d])
R["8c. folder with a duplicate copy and a README.txt (v2)"] = {
    "truth sessions": truth_w["sessions"], "v2 sessions": ov(o2, "sessions"),
    "v2 notes": [v for k, v in o2.items() if k[3] == "note"]}

# ---- 9. --manifest-from, and the manifest matching the one written beside it ---------
d = fresh("manifest_from")
rows_x, _ = synth(1000, 200, seed=13)
write_csv(os.path.join(d, "export.csv"), rows_x)
p, o, _, html = run(V2, d, ["export.csv"])
p2b = subprocess.run([sys.executable, V2, "--manifest-from", OUT_CSV], cwd=d,
                     capture_output=True, text=True, encoding="utf-8", errors="replace")
rebuilt = os.path.join(d, os.path.splitext(OUT_CSV)[0] + "_manifest_rebuilt.html")
R["9. --manifest-from"] = {
    "exit": p2b.returncode,
    "wrote a separate file": os.path.exists(rebuilt),
    "original manifest untouched": open(os.path.join(d, OUT_HTML), encoding="utf-8").read() == html,
    "rebuilt page identical to the original": (open(rebuilt, encoding="utf-8").read() == html
                                               if os.path.exists(rebuilt) else None)}

print(json.dumps(R, indent=1, default=str))
