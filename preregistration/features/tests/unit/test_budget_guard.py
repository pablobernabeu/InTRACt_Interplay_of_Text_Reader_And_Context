"""Tests of the ARC job layer in jobs/arc/ and envs/: the budget guard, the staging helper, the run comparison, the
committed locks and the job templates. jobs/arc/ holds scripts, not package modules, so its Python scripts are
loaded from their files here, and their command lines are run as subprocesses. No network, GPU or model is used."""

import csv
import gzip
import importlib.util
import io
import json
import os
import re
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from intract_features import cli
from intract_features import config as config_mod

ROOT = Path(__file__).resolve().parents[2]
JOBS = ROOT / "jobs" / "arc"
CONFIG_DIR = ROOT / "config"


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve their annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


bg = load_script("arc_budget_guard", JOBS / "budget_guard.py")
st = load_script("arc_staging", JOBS / "staging.py")
cr = load_script("arc_compare_runs", JOBS / "compare_runs.py")

HEADER = list(bg.LEDGER_COLUMNS)


def write_ledger(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        for r in rows:
            w.writerow([r.get(c, "") for c in HEADER])
    return path


# ---------------------------------------------------------------------------------------------- budget guard


@pytest.mark.parametrize("text,hours", [("01:30:00", 1.5), ("45:00", 0.75), ("90", 1.5), ("2-00:00:00", 48.0),
                                        ("1-12", 36.0), ("0-01:15", 1.25), ("12:00:00", 12.0),
                                        ("04:00:00 per task", 4.0)])
def test_walltime_hours(text, hours):
    assert bg.walltime_hours(text) == pytest.approx(hours)


def test_walltime_hours_refuses_what_is_not_a_time():
    with pytest.raises(bg.LedgerError):
        bg.walltime_hours("unknown")


def test_gres_parsing():
    assert bg.gres_gpus("gpu:l40s:1") == 1 and bg.gres_gpus("gpu:l40s:2") == 2 and bg.gres_gpus("gpu:l40s") == 1
    assert bg.is_l40s("gpu:l40s:1") and not bg.is_l40s("none (cpu 2)") and not bg.is_l40s("gpu:a100:1")
    # rows of the pre-submission ledger: an L40S request with notes counts, a note naming the L40S does not
    assert bg.is_l40s("gpu:l40s:1 (cpu 8, 48G)") and bg.is_l40s("gpu:l40s:1 per task (-c 8, 64G), array 0-1")
    assert not bg.is_l40s("gpu:1 (devel partition = RTX 8000, not L40S)") and not bg.is_l40s("gpu:1")
    assert not bg.is_l40s("gpu:l40sx:1")


def test_read_ledger_keys_jobs_by_cluster(tmp_path):
    path = write_ledger(tmp_path / "jobs.csv", [
        {"job_id": "70", "cluster": "htc", "gres": "gpu:l40s:1", "walltime": "01:00:00", "gpu_hours_requested": "1"},
        {"job_id": "70", "cluster": "arc", "gres": "gpu:l40s:1", "walltime": "02:00:00", "gpu_hours_requested": "2"},
        {"job_id": "9149711", "cluster": "htc", "gres": "gpu:1 (devel partition = RTX 8000, not L40S)",
         "walltime": "00:10:00", "gpu_hours_requested": "0.17"},
    ])
    assert [(j.cluster, j.job_id, j.requested) for j in bg.read_ledger([path])] == [("htc", "70", 1.0),
                                                                                    ("arc", "70", 2.0)]


@pytest.mark.parametrize("bad", ["nan", "inf", "-1", "lots"])
def test_read_ledger_refuses_a_request_it_cannot_trust(tmp_path, bad):
    path = write_ledger(tmp_path / "jobs.csv", [
        {"job_id": "1", "cluster": "htc", "gres": "gpu:l40s:1", "walltime": "01:00:00", "gpu_hours_requested": bad}])
    with pytest.raises(bg.LedgerError):
        bg.read_ledger([path])


def test_read_ledger_keeps_l40s_rows_once(tmp_path):
    path = write_ledger(tmp_path / "jobs.csv", [
        {"job_id": "11", "cluster": "htc", "gres": "gpu:l40s:1", "walltime": "03:00:00", "gpu_hours_requested": "3"},
        {"job_id": "12", "cluster": "htc", "gres": "gpu:l40s:1", "walltime": "01:30:00", "gpu_hours_requested": ""},
        {"job_id": "13", "cluster": "htc", "gres": "none", "walltime": "06:00:00", "gpu_hours_requested": "0"},
        {"job_id": "11", "cluster": "htc", "gres": "gpu:l40s:1", "walltime": "09:00:00", "gpu_hours_requested": "9"},
    ])
    jobs = bg.read_ledger([path, tmp_path / "absent.csv"])
    assert [(j.job_id, j.requested) for j in jobs] == [("11", 3.0), ("12", 1.5)]


def test_read_ledger_refuses_other_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("job_id,gres\n1,gpu:l40s:1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        bg.read_ledger([path])


SACCT = "\n".join([
    # array 21: two tasks done (one each of 1 h and 0.5 h), one running for 0.25 h, one pending
    "21_0|21|COMPLETED|3600|billing=8,cpu=8,gres/gpu=1,mem=64G,node=1|billing=8,cpu=8,gres/gpu=1",
    "21_1|22|FAILED|1800|cpu=8,gres/gpu:l40s=1|cpu=8,gres/gpu=1",
    "21_2|23|RUNNING|900|cpu=8,gres/gpu=1|cpu=8,gres/gpu=1",
    "21_[3]|21|PENDING|0||cpu=8,gres/gpu=1",
    # job 30 finished in 2 h; job 31 was cancelled before it started
    "30|30|COMPLETED|7200|cpu=16,gres/gpu=1|cpu=16,gres/gpu=1",
    "31|31|CANCELLED by 1234|0||cpu=8,gres/gpu=1",
    "",
])


def test_parse_sacct_groups_array_tasks():
    acc = bg.parse_sacct(SACCT)
    assert sorted(acc) == [(None, "21"), (None, "30"), (None, "31")]
    assert [r["tasks"] for r in acc[(None, "21")]] == [1, 1, 1, 1] and acc[(None, "21")][3]["state"] == "PENDING"
    assert acc[(None, "31")][0]["state"] == "CANCELLED" and acc[(None, "30")][0]["gpus"] == 1
    assert bg.parse_sacct("40_[0-3%2]|40|PENDING|0||gres/gpu=1")[(None, "40")][0]["tasks"] == 4
    full = bg.parse_sacct("htc|50|50|COMPLETED|60|gres/gpu=1|gres/gpu=1|2026-11-04T10:00:00")
    assert list(full) == [("htc", "50")] and full[("htc", "50")][0]["submit"] == "2026-11-04T10:00:00"
    with pytest.raises(bg.LedgerError):
        bg.parse_sacct("htc|50|50|COMPLETED|soon|gres/gpu=1|gres/gpu=1|2026-11-04T10:00:00")


def test_requeued_allocations_are_all_counted():
    sacct = "\n".join(["htc|60|60|REQUEUED|1800|gres/gpu=1|gres/gpu=1|2026-11-04T10:00:00",
                       "htc|60|60|RUNNING|600|gres/gpu=1|gres/gpu=1|2026-11-04T10:31:00",
                       "arc|60|60|COMPLETED|7200|gres/gpu=1|gres/gpu=1|2026-11-04T10:00:00"])
    job = bg.LedgerJob("60", "htc", "requeued", "gpu:l40s:1", "02:00:00", 2.0, "2026-11-04T09:59:58Z")
    t = bg.tally([job], bg.parse_sacct(sacct))
    # the requeued allocation's half hour was charged; the running one may still use its whole request; the arc
    # job with the same number is another job
    assert t.used == pytest.approx(0.5 + 600 / 3600)
    assert t.committed == pytest.approx(0.5 + 2.0)
    assert t.jobs[0]["tasks"] == 1 and t.jobs[0]["allocations"] == 2


def test_an_older_job_with_the_same_number_is_left_out():
    sacct = "\n".join(["htc|61|61|COMPLETED|36000|gres/gpu=1|gres/gpu=1|2024-01-02T03:04:05",
                       "htc|61|61|COMPLETED|3600|gres/gpu=1|gres/gpu=1|2026-11-04T12:00:00"])
    job = bg.LedgerJob("61", "htc", "", "gpu:l40s:1", "02:00:00", 2.0, "2026-11-04T11:59:59Z")
    assert bg.tally([job], bg.parse_sacct(sacct)).used == pytest.approx(1.0)


def test_tally_commits_unfinished_tasks_at_their_request():
    jobs = [bg.LedgerJob("21", "htc", "array", "gpu:l40s:1", "02:00:00", 8.0),
            bg.LedgerJob("30", "htc", "one", "gpu:l40s:1", "03:00:00", 3.0),
            bg.LedgerJob("31", "htc", "cancelled", "gpu:l40s:1", "01:00:00", 1.0),
            bg.LedgerJob("32", "htc", "not yet in accounting", "gpu:l40s:1", "04:00:00", 4.0)]
    t = bg.tally(jobs, bg.parse_sacct(SACCT))
    assert t.requested == pytest.approx(16.0)
    assert t.used == pytest.approx(1.0 + 0.5 + 0.25 + 2.0)
    # array 21: 1.5 h finished, then the running and the pending task at 8/4 h each; 30 used 2 h; 31 nothing;
    # 32 its whole request
    assert t.committed == pytest.approx(1.5 + 2 * 2.0 + 2.0 + 0.0 + 4.0)
    by_id = {j["job_id"]: j for j in t.jobs}
    assert by_id["21"]["unfinished_tasks"] == 2 and by_id["31"]["committed"] == 0


def test_tally_without_accounting_commits_every_request():
    jobs = [bg.LedgerJob("1", "htc", "", "gpu:l40s:1", "01:00:00", 1.5)]
    t = bg.tally(jobs, None)
    assert (t.requested, t.used, t.committed) == (1.5, 0.0, 1.5)


def run_guard(*args):
    return subprocess.run([sys.executable, "-I", str(JOBS / "budget_guard.py"), *args], capture_output=True,
                          text=True)


def test_check_refuses_past_the_cap_and_allows_within(tmp_path):
    ledger = write_ledger(tmp_path / "jobs.csv", [
        {"job_id": "30", "cluster": "htc", "gres": "gpu:l40s:1", "walltime": "03:00:00", "gpu_hours_requested": "3"},
        {"job_id": "21", "cluster": "htc", "gres": "gpu:l40s:1", "walltime": "02:00:00", "gpu_hours_requested": "8"},
    ])
    sacct = tmp_path / "sacct.txt"
    sacct.write_text(SACCT, encoding="utf-8")
    ok = run_guard("check", "--cap", "10", "--add", "2", "--ledger", str(ledger), "--sacct-file", str(sacct))
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["proposed"] == pytest.approx(2.0 + 5.5 + 2.0)  # committed 30: 2, 21: 5.5
    over = run_guard("check", "--cap", "10", "--add", "2", "--basis", "requested", "--ledger", str(ledger),
                     "--sacct-file", str(sacct))
    assert over.returncode == 3 and "refusing" in over.stderr
    rep = run_guard("report", "--ledger", str(ledger), "--no-sacct")
    assert rep.returncode == 0 and json.loads(rep.stdout)["l40s_gpu_hours"]["committed"] == pytest.approx(11.0)


def test_check_needs_a_ledger(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "INTRACT_LEDGER"}
    r = subprocess.run([sys.executable, "-I", str(JOBS / "budget_guard.py"), "report", "--no-sacct"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2 and "no ledger" in r.stderr


@pytest.mark.parametrize("cap,add,asked", [("nan", "1", "1"), ("10", "inf", "1"), ("10", "1", "nan"),
                                           ("-5", "1", "1")])
def test_check_fails_closed_on_numbers_it_cannot_trust(tmp_path, cap, add, asked):
    ledger = write_ledger(tmp_path / "jobs.csv", [
        {"job_id": "1", "cluster": "htc", "gres": "gpu:l40s:1", "walltime": "01:00:00",
         "gpu_hours_requested": asked}])
    r = run_guard("check", "--cap", cap, "--add", add, "--ledger", str(ledger), "--no-sacct")
    assert r.returncode == 3 and "refusing" in r.stderr


def test_the_presub_rtx8000_row_is_not_an_l40s(tmp_path):
    ledger = write_ledger(tmp_path / "jobs.csv", [
        {"job_id": "9149711", "cluster": "htc", "gres": "gpu:1 (devel partition = RTX 8000, not L40S)",
         "walltime": "00:10:00", "gpu_hours_requested": "0.17"},
        {"job_id": "9151086", "cluster": "htc", "gres": "gpu:l40s:1 per task (-c 8, 64G), array 0-1",
         "walltime": "04:00:00 per task", "gpu_hours_requested": "8.0"}])
    rep = run_guard("report", "--ledger", str(ledger), "--no-sacct")
    assert rep.returncode == 0 and json.loads(rep.stdout)["l40s_gpu_hours"]["requested"] == pytest.approx(8.0)


# ------------------------------------------------------------------------------------------- committed locks


def lock(name, table):
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))[table]


def test_committed_locks_are_well_formed():
    assert st.validate_models_lock(lock("models.lock.json", "models")) == []
    assert st.validate_resources_lock(lock("resources.lock.json", "resources")) == []


def test_validate_models_lock_finds_short_revisions_and_bad_hashes():
    entries = {"a/b": {"repo": "a/b", "revision": "1467d280", "files": {"x": {"sha256": "abc"}, "y": None}},
               "c/d": {"repo": "c/d", "revision": "0" * 40, "files": {"m.safetensors": {"sha256": None}},
                       "hub_files": {"m.bin": {"sha256": "1" * 64}},
                       "conversion": {"dir": "c", "map": {"m.bin": "m.safetensors"}}}}
    problems = st.validate_models_lock(entries)
    assert any("not a full commit" in p for p in problems)
    assert any("x SHA-256 'abc' is malformed" in p for p in problems)
    assert any("y has no SHA-256" in p for p in problems)
    assert not any(p.startswith("c/d") for p in problems)  # a converted file may be pending


def test_every_lock_key_a_stage_config_names_is_pinned():
    cfg = config_mod.load(CONFIG_DIR)
    models, stages = cfg["models"]["models"], cfg["stages"]
    keys = {stages["sat"]["model"]["sat"], stages["sat"]["model"]["tokenizer"],
            stages["parse_stanza"]["models_lock_key"], stages["parse_udpipe"]["models_lock_key"],
            stages["coref_corpipe"]["model"]["code"], stages["coref_corpipe"]["aligner"]["model"],
            stages["qe_metricx"]["model"]["metricx"], stages["qe_metricx"]["model"]["tokenizer"],
            stages["encode_e5"]["model"]["key"], stages["encode_bgem3"]["model"]["key"],
            stages["surprisal_xglm"]["model"]["key"]}
    variants = stages["coref_corpipe"]["model"]["variants"]
    for v in variants.values():
        keys |= {v["corpipe"], v["encoder"], v["tokenizer"]}
    for lang in cfg["languages"].values():
        keys |= set(lang["goldfish"].values())
    assert sorted(k for k in keys if k not in models) == []
    # CorPipe's script loads its encoder's configuration and tokeniser by hub name, so J0 writes their refs/main
    for v in variants.values():
        assert models[v["encoder"]].get("hub_ref_main") and models[v["tokenizer"]].get("hub_ref_main")
    resources = cfg["resources"]["resources"]
    affect = stages["features_discourse"]["affect"]["resource_pin"]
    for lang in cfg["languages"].values():
        assert affect.format(code=lang["memolon"]) in resources


def test_converted_entries_name_their_conversion_parameters():
    models = lock("models.lock.json", "models")
    for key in ("goldfish-models/eng_latn_1000mb", "goldfish-models/eng_latn_100mb"):
        drop, tied = st.conversion_parameters(models[key], CONFIG_DIR)
        assert tied == {"lm_head.weight": "transformer.wte.weight"} and drop
    drop, tied = st.conversion_parameters(models["BAAI/bge-m3"], CONFIG_DIR)
    assert (drop, tied) == ([], {})


def requirement_blocks(text):
    """(name==version, hashes) for each requirement of a uv hash lock."""
    blocks, current = [], None
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*==\S+)", line)
        if m:
            current = [m.group(1), 0]
            blocks.append(current)
        elif current is not None:
            current[1] += len(re.findall(r"--hash=sha256:[0-9a-f]{64}", line))
    return blocks


@pytest.mark.parametrize("env", ["core", "udpipe", "corpipe", "metricx"])
def test_every_locked_requirement_is_hash_pinned_and_matches_its_in_file(env):
    text = (ROOT / "envs" / f"{env}.lock").read_text(encoding="utf-8")
    blocks = requirement_blocks(text)
    assert blocks and all(n > 0 for _, n in blocks)
    locked = {b[0].split("==")[0].lower().replace("_", "-").replace(".", "-"): b[0].split("==")[1] for b in blocks}
    for line in (ROOT / "envs" / f"{env}.in").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]+\])?==(\S+)", line.strip())
        if m:
            name = m.group(1).lower().replace("_", "-").replace(".", "-")
            assert locked.get(name) == m.group(3), f"{env}: {m.group(1)}"


def test_every_stage_environment_has_a_lock():
    for name, mod in cli.discover().items():
        assert (ROOT / "envs" / f"{mod.STAGE.env}.lock").is_file(), name


# --------------------------------------------------------------------------------------------- job templates


def test_every_stage_has_a_template_with_the_right_resources():
    for name, mod in cli.discover().items():
        text = (JOBS / f"{name}.sbatch").read_text(encoding="utf-8")
        for directive in ("--clusters=htc", "--account=educ-intract", "--partition=short", "--export=NONE"):
            assert f"#SBATCH {directive}" in text, (name, directive)
        assert ("#SBATCH --gres=gpu:l40s:1" in text) == (mod.STAGE.device == "gpu"), name
        assert re.search(rf"run_stage\.sh {name} ", text), name


ARRAY_TEMPLATES = {"documents", "parse_stanza", "features_gramlex", "features_discourse"}


def test_log_names_suit_the_job_kind():
    # %a is only meaningful in an array job; elsewhere it prints 4294967294
    for path in JOBS.glob("*.sbatch"):
        text = path.read_text(encoding="utf-8")
        pattern = "%x_%A_%a.out" if path.stem in ARRAY_TEMPLATES else "%x_%j.out"
        assert pattern in text, path.name
        for directive in ("--clusters=htc", "--account=educ-intract", "--export=NONE"):
            assert f"#SBATCH {directive}" in text, (path.name, directive)
        assert "set -eo pipefail" in text, path.name


def test_the_metricx_build_gates_nothing():
    j0 = (JOBS / "j0_build.sbatch").read_text(encoding="utf-8")
    step1 = j0.split("== 1.")[1].split("== 2.")[0]
    assert re.search(r'build_envs\.sh"? core udpipe corpipe\n', step1) and "metricx" not in step1
    chain = (JOBS / "submit_chain.sh").read_text(encoding="utf-8")
    assert 'plan j0_metricx - j0_metricx.sbatch 0 0 "j0"' in chain
    assert not re.search(r'plan [^\n]*"[^"\n]*j0_metricx', chain)  # no job lists it as a dependency


def test_submit_chain_checks_both_lock_files():
    chain = (JOBS / "submit_chain.sh").read_text(encoding="utf-8")
    assert "for f in manifest.json extraction_record.json" in chain
    lock_cfg = config_mod.load(CONFIG_DIR)["stages"]["documents"]["lock"]
    assert lock_cfg.get("on_missing_manifest") == "refuse"


def test_combined_job_covers_every_gpu_stage():
    text = (JOBS / "gpu_combined.sbatch").read_text(encoding="utf-8")
    gpu = [n for n, m in cli.discover().items() if m.STAGE.device == "gpu"]
    for name in gpu:
        assert re.search(rf"gpu_stage {name}\b", text), name
    assert "#SBATCH --gres=gpu:l40s:1" in text and "--time=12:00:00" in text


EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")


def test_no_job_file_carries_an_email_address():
    for path in list(JOBS.iterdir()) + list((ROOT / "envs").iterdir()):
        if path.is_file() and path.suffix != ".pyc":
            text = path.read_text(encoding="utf-8")
            assert "mailto" not in text and "--mail-" not in text and not EMAIL.search(text), path.name


# ------------------------------------------------------------------------------------------- staging helpers


def test_overlay_fills_pending_hashes_and_sets_the_folder(tmp_path):
    lockd = {"models": {"m": {"repo": "o/m", "revision": "0" * 40,
                              "files": {"config.json": {"sha256": "a" * 64}, "model.safetensors": {"sha256": None}},
                              "conversion": {"dir": "o--m", "map": {"model.bin": "model.safetensors"}}},
                        "plain": {"repo": "o/p", "revision": "1" * 40, "files": {"x": "b" * 64}}}}
    (tmp_path / "o--m").mkdir()
    conversions = {"m": {"files": {"config.json": "a" * 64, "model.safetensors": "c" * 64}}}
    new, changes = st.overlay_models_lock(lockd, conversions, tmp_path)
    m = new["models"]["m"]
    assert m["path"] == str(tmp_path / "o--m") and m["files"]["model.safetensors"]["sha256"] == "c" * 64
    assert lockd["models"]["m"]["files"]["model.safetensors"]["sha256"] is None  # the input is untouched
    assert new["models"]["plain"] == lockd["models"]["plain"] and len(changes) == 2
    bad = {"m": {"files": {"config.json": "f" * 64, "model.safetensors": "c" * 64}}}
    with pytest.raises(st.StagingError):
        st.overlay_models_lock(lockd, bad, tmp_path)
    _, notes = st.overlay_models_lock(lockd, {}, tmp_path)
    assert "no recorded conversion" in notes[0]


def test_write_run_config_copies_the_config_and_records_the_overlay(tmp_path):
    src = tmp_path / "config"
    (src / "stages").mkdir(parents=True)
    (src / "stages" / "x.toml").write_text("a = 1\n", encoding="utf-8")
    (src / "models.lock.json").write_text(json.dumps({"models": {}}), encoding="utf-8")
    rec = st.write_run_config(tmp_path / "run" / "config", src, tmp_path / "models")
    out = tmp_path / "run" / "config"
    assert (out / "stages" / "x.toml").read_text(encoding="utf-8") == "a = 1\n"
    assert json.loads((out / "OVERLAY.json").read_text(encoding="utf-8"))["changes"] == rec["changes"] == []
    assert config_mod.load(out)["models"] == {"models": {}}


def make_zip(member_bytes):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("other.tsv", b"x" * 1000)
        z.writestr("en.tsv", member_bytes)
    data = buf.getvalue()
    return data, (lambda a, b: data[a:b + 1])


def test_zip_member_is_streamed_and_checked():
    content = ("word\tvalence\n" + "".join(f"w{i}\t{i % 9}\n" for i in range(20000))).encode("utf-8")
    data, get = make_zip(content)
    entries = st.zip_entries(get, len(data))
    assert [e["name"] for e in entries] == ["other.tsv", "en.tsv"]
    entry = entries[1]
    assert b"".join(st.zip_member_stream(get, entry, step=4096)) == content
    with pytest.raises(st.StagingError):
        list(st.zip_member_stream(get, {**entry, "crc32": entry["crc32"] ^ 1}))


def test_write_verified_refuses_a_wrong_hash(tmp_path):
    import hashlib

    good = hashlib.sha256(b"abc").hexdigest()
    assert st.write_verified(tmp_path / "f", [b"a", b"bc"], good).read_bytes() == b"abc"
    with pytest.raises(st.StagingError):
        st.write_verified(tmp_path / "g", [b"abd"], good)
    assert not (tmp_path / "g").exists() and not (tmp_path / "g.part").exists()


def test_verify_files_and_exact_folders(tmp_path):
    import hashlib

    (tmp_path / "a").write_bytes(b"1")
    (tmp_path / "extra").write_bytes(b"2")
    pins = {"a": {"sha256": hashlib.sha256(b"1").hexdigest()}, "b": "0" * 64}
    assert st.verify_files(tmp_path, pins) == ["b is missing"]
    assert st.verify_files(tmp_path, pins, exact=True) == ["b is missing", "extra is not pinned"]


def test_qe_pairs_from_the_translated_benchmark():
    rows = [{"src": "He", "out": "Er"}, {"src": "Ben!", "out": "- Ben!"}, {"src": "x", "out": "y"}]
    pairs = list(st.qe_pairs(rows, "madlad_de", "de-de", limit=2))
    assert pairs == [{"pair_id": "madlad_de-000000", "src": "He", "mt": "Er", "lang": "de-de"},
                     {"pair_id": "madlad_de-000001", "src": "Ben!", "mt": "- Ben!", "lang": "de-de"}]
    with pytest.raises(st.StagingError):
        list(st.qe_pairs([{"src": "a"}], "t", "de-de"))


def test_safetensors_index_is_sorted_and_refuses_duplicates():
    idx = st.safetensors_index({"b.safetensors": ["z", "a"], "a.safetensors": ["m"]}, 12)
    assert list(idx["weight_map"]) == ["a", "m", "z"] and idx["metadata"]["total_size"] == 12
    with pytest.raises(st.StagingError):
        st.safetensors_index({"a": ["k"], "b": ["k"]}, 0)


def test_ref_main_is_written_once_and_never_moved(tmp_path):
    env = {"HF_HUB_CACHE": str(tmp_path)}
    with pytest.raises(st.StagingError):
        st.ensure_ref_main("google/umt5-xl", "a" * 40, env, write=False)
    assert st.ensure_ref_main("google/umt5-xl", "a" * 40, env) == "written"
    assert st.ensure_ref_main("google/umt5-xl", "a" * 40, env) == "present"
    with pytest.raises(st.StagingError):
        st.ensure_ref_main("google/umt5-xl", "b" * 40, env)
    assert (tmp_path / "models--google--umt5-xl" / "refs" / "main").read_text(encoding="utf-8") == "a" * 40


def test_espeak_plan_comes_from_the_lock(tmp_path):
    entry = lock("resources.lock.json", "resources")["espeak-ng-1.52.0"]
    plan = st.espeak_plan(entry, {"INTRACT_SRC": str(tmp_path / "src"), "INTRACT_OPT": str(tmp_path / "opt")})
    assert plan["ESPEAK_COMMIT"] == "4870adfa25b1a32b4361592f1be8a40337c58d6c" and plan["ESPEAK_TAG"] == "1.52.0"
    assert plan["ESPEAK_PREFIX"] == str(tmp_path / "opt" / "espeak-ng-1.52.0")
    assert "--without-pcaudiolib" in plan["ESPEAK_CONFIGURE"]


def test_env_dir_has_no_default():
    with pytest.raises(st.StagingError):
        st.env_dir("INTRACT_MODELS", {})


def fake_snapshot(tmp_path, monkeypatch, shards):
    """A hub snapshot holding pickled state dicts, and the lock entry that converts them.

    Like BAAI/bge-m3's entry, it copies a file from a subfolder (1_Pooling/config.json), which the converted
    folder has to create.
    """
    torch = pytest.importorskip("torch")
    pytest.importorskip("safetensors")
    import hashlib

    hub, models = tmp_path / "hub", tmp_path / "models"
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.setenv("INTRACT_MODELS", str(models))
    snap = hub / "models--org--tiny" / "snapshots" / ("e" * 40)
    (snap / "1_Pooling").mkdir(parents=True)
    (snap / "config.json").write_text('{"model_type": "gpt2"}', encoding="utf-8")
    (snap / "1_Pooling" / "config.json").write_text('{"pooling_mode_cls_token": true}', encoding="utf-8")
    hub_files, mapping = {}, {}
    for i, state in enumerate(shards):
        name = "pytorch_model.bin" if len(shards) == 1 else f"pytorch_model-{i + 1:05d}-of-{len(shards):05d}.bin"
        torch.save(state, snap / name)
        hub_files[name] = {"sha256": hashlib.sha256((snap / name).read_bytes()).hexdigest()}
        mapping[name] = name.replace("pytorch_model", "model").replace(".bin", ".safetensors")
    files = {}
    for copied in ("config.json", "1_Pooling/config.json"):
        sha = hashlib.sha256((snap / copied).read_bytes()).hexdigest()
        hub_files[copied] = files[copied] = {"sha256": sha}
    files.update({t: {"sha256": None} for t in mapping.values()})
    conv = {"dir": "org--tiny", "copy": ["1_Pooling/config.json", "config.json"], "map": mapping,
            "drop": [r"\.attn\.bias$"], "tied": {"lm_head.weight": "transformer.wte.weight"}}
    if len(shards) > 1:
        conv["index"] = "model.safetensors.index.json"
        files["model.safetensors.index.json"] = {"sha256": None}
    return {"repo": "org/tiny", "revision": "e" * 40, "files": files, "hub_files": hub_files, "conversion": conv}


def test_convert_entry_builds_a_verified_folder_and_resumes(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    wte = torch.arange(12.0).reshape(4, 3)
    state = {"transformer.wte.weight": wte, "lm_head.weight": wte, "transformer.h.0.attn.bias": torch.ones(2, 2),
             "transformer.h.0.mlp.c_fc.weight": torch.full((3, 3), 0.5)}
    entry = fake_snapshot(tmp_path, monkeypatch, [state])
    assert st.validate_models_lock({"org/tiny": entry}) == []
    conversions, log = {}, []
    rec = st.convert_entry("org/tiny", entry, CONFIG_DIR, conversions, log.append)
    folder = tmp_path / "models" / "org--tiny"
    assert sorted(rec["files"]) == ["1_Pooling/config.json", "config.json", "model.safetensors"]
    assert conversions["org/tiny"] is rec
    assert rec["checks"]["model.safetensors"]["dropped"] == ["transformer.h.0.attn.bias"]
    assert rec["checks"]["model.safetensors"]["tied_omitted"] == ["lm_head.weight"]
    assert st.verify_files(folder, rec["files"], exact=True) == []
    from safetensors.torch import load_file

    assert torch.equal(load_file(str(folder / "model.safetensors"))["transformer.wte.weight"], wte)
    new, _ = st.overlay_models_lock({"models": {"org/tiny": entry}}, conversions, tmp_path / "models")
    assert st.verify_files(new["models"]["org/tiny"]["path"], new["models"]["org/tiny"]["files"]) == []
    log.clear()
    assert st.convert_entry("org/tiny", entry, CONFIG_DIR, conversions, log.append) is rec
    assert "already matches" in log[0]


def test_convert_entry_writes_a_sorted_index_for_shards(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    shared = torch.ones(2, 2)
    shard1 = {"shared.weight": shared, "encoder.embed_tokens.weight": shared, "encoder.block.0.w": torch.zeros(3)}
    shard2 = {"lm_head.weight": torch.full((2, 2), 2.0)}
    entry = fake_snapshot(tmp_path, monkeypatch, [shard1, shard2])
    entry["conversion"]["tied"] = {"encoder.embed_tokens.weight": "shared.weight"}
    rec = st.convert_entry("org/tiny", entry, CONFIG_DIR, {}, lambda _: None)
    index = json.loads((tmp_path / "models" / "org--tiny" / "model.safetensors.index.json").read_text(encoding="utf-8"))
    assert index["weight_map"] == {"encoder.block.0.w": "model-00001-of-00002.safetensors",
                                   "lm_head.weight": "model-00002-of-00002.safetensors",
                                   "shared.weight": "model-00001-of-00002.safetensors"}
    assert index["metadata"]["total_size"] == (4 + 3 + 4) * 4
    assert rec["checks"]["model-00001-of-00002.safetensors"]["tied_omitted"] == ["encoder.embed_tokens.weight"]


def test_convert_entry_refuses_a_committed_hash_that_differs(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    entry = fake_snapshot(tmp_path, monkeypatch, [{"a": torch.zeros(2)}])
    entry["files"]["model.safetensors"] = {"sha256": "0" * 64}
    with pytest.raises(st.StagingError):
        st.convert_entry("org/tiny", entry, CONFIG_DIR, {}, lambda _: None)
    assert not (tmp_path / "models" / "org--tiny").exists()
    assert not (tmp_path / "models" / "org--tiny.tmp").exists()


def test_check_conversion_explains_every_missing_tensor():
    torch = pytest.importorskip("torch")
    w = torch.arange(6.0).reshape(2, 3)
    original = {"wte": w, "lm_head": w, "h.0.attn.bias": torch.ones(1), "h.0.mlp": torch.zeros(2)}
    converted = {"wte": w.clone(), "h.0.mlp": torch.zeros(2)}
    rec = st.check_conversion(original, converted, [r"\.attn\.bias$"], {"lm_head": "wte"})
    assert rec == {"tensors": 2, "dropped": ["h.0.attn.bias"], "tied_omitted": ["lm_head"]}
    with pytest.raises(st.StagingError):
        st.check_conversion(original, {"wte": w, "h.0.mlp": torch.ones(2)}, [r"\.attn\.bias$"], {"lm_head": "wte"})


def test_copied_files_keep_their_subfolders(tmp_path):
    # the committed BGE-M3 entry copies a file from a subfolder, which once stopped J0 (FileNotFoundError)
    copies = lock("models.lock.json", "models")["BAAI/bge-m3"]["conversion"]["copy"]
    assert any("/" in name for name in copies)
    src = tmp_path / "snap"
    for name in copies:
        (src / name).parent.mkdir(parents=True, exist_ok=True)
        (src / name).write_text(name, encoding="utf-8")
    st.copy_files(src, tmp_path / "out", copies)
    assert all((tmp_path / "out" / name).read_text(encoding="utf-8") == name for name in copies)


# ----------------------------------------------------------------------------------------- archives


def test_a_zip64_marker_without_its_locator_is_refused():
    data, get = make_zip(b"x" * 100)
    eocd = data.rfind(b"PK\x05\x06")
    # mark the central directory's offset as a ZIP64 field without adding the ZIP64 records
    forged = data[:eocd + 16] + struct.pack("<I", 0xFFFFFFFF) + data[eocd + 20:]
    with pytest.raises(st.StagingError):
        st.zip_entries(lambda a, b: forged[a:b + 1], len(forged))


# ----------------------------------------------------------------------------------------- run configs


def test_overrides_change_one_value_in_the_run_copy(tmp_path):
    src = tmp_path / "config"
    (src / "stages").mkdir(parents=True)
    (src / "models.lock.json").write_text(json.dumps({"models": {}}), encoding="utf-8")
    original = ('[precision]\n# the registered default\nmode = "fp32"\ncheck_fraction = 1.0\n\n[runtime]\n'
                'dtype = "float32"\ntied = [\n  "a",\n]\n')
    (src / "stages" / "x.toml").write_text(original, encoding="utf-8")
    rec = st.write_run_config(tmp_path / "run", src, tmp_path / "models",
                              ['x.precision.mode="bf16"', "x.runtime.dtype = 'bfloat16'"])
    cfg = config_mod.load(tmp_path / "run")["stages"]["x"]
    assert cfg["precision"] == {"mode": "bf16", "check_fraction": 1.0} and cfg["runtime"]["dtype"] == "bfloat16"
    assert (src / "stages" / "x.toml").read_text(encoding="utf-8") == original  # the committed file is untouched
    assert [o["value"] for o in rec["overrides"]] == ["bf16", "bfloat16"]
    for bad in ('x.precision.absent="y"', 'y.precision.mode="bf16"', "x.precision.mode=bf16", "x.mode=1",
                'x.runtime.tied="b"'):
        with pytest.raises(st.StagingError):
            st.write_run_config(tmp_path / "bad", src, tmp_path / "models", [bad])
        assert not (tmp_path / "bad").exists() and not (tmp_path / "bad.tmp").exists()


def test_the_bf16_job_sets_keys_the_stage_configs_have(tmp_path):
    text = (JOBS / "gpu_bf16.sbatch").read_text(encoding="utf-8")
    sets = re.findall(r"--set '([^']+)'", text)
    assert len(sets) == 3
    for override in sets:
        stage, table, key, literal, value = st.parse_override(override)
        path = CONFIG_DIR / "stages" / f"{stage}.toml"
        st.apply_override(path.read_text(encoding="utf-8"), table, key, literal, value)


# ------------------------------------------------------------------------------------------- resuming


def finished_shard(work, stage="encode_e5", commit="c1", inputs=("documents", "segments"), outputs=("encode_e5",)):
    for art in inputs:
        p = work / "en-us" / art / "shard-0-of-4.jsonl.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        os.utime(p, (1_000_000, 1_000_000))
    for art in outputs:
        p = work / "en-us" / art / "shard-0-of-4.jsonl.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"y")
    record = work / "en-us" / "_timing" / f"{stage}-shard-0-of-4.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"stage": stage, "code_commit": commit}), encoding="utf-8")
    os.utime(record, (2_000_000, 2_000_000))
    return record


def test_a_record_is_trusted_only_for_the_same_code_and_older_inputs(tmp_path):
    record = finished_shard(tmp_path)
    files = st.shard_files(tmp_path, "en-us", ("documents", "segments"), 0, 4)
    outs = st.shard_files(tmp_path, "en-us", ("encode_e5",), 0, 4)
    assert st.resume_reason(record, "c1", files, outs) is None
    assert "code" in st.resume_reason(record, "c2", files, outs)
    assert "cannot identify" in st.resume_reason(record, "c1-dirty", files, outs)
    assert "cannot identify" in st.resume_reason(record, "unknown", files, outs)
    newer = tmp_path / "en-us" / "segments" / "shard-0-of-4.jsonl.gz"
    os.utime(newer, (3_000_000, 3_000_000))
    assert "newer" in st.resume_reason(record, "c1", files, outs)
    os.utime(newer, (1_000_000, 1_000_000))
    (tmp_path / "en-us" / "encode_e5" / "shard-0-of-4.jsonl.gz").unlink()
    outs = st.shard_files(tmp_path, "en-us", ("encode_e5",), 0, 4)
    assert "output" in st.resume_reason(record, "c1", files, outs)
    assert st.resume_reason(tmp_path / "absent.json", "c1", files, outs) == "no timing record"


def test_resume_plan_lists_the_shards_to_run(tmp_path):
    finished_shard(tmp_path)
    stage = cli.discover()["encode_e5"].STAGE
    assert set(stage.inputs) <= {"documents", "segments"}
    assert st.resume_plan(stage, tmp_path, "en-us", 4, [0, 1], "c1", log=lambda m: None) == [1]
    assert st.resume_plan(stage, tmp_path, "en-us", 4, [0], "c2", log=lambda m: None) == [0]


# --------------------------------------------------------------------------------------- optional pins


def test_optional_entries_are_staged_only_on_request():
    models = lock("models.lock.json", "models")
    optional = [k for k, e in models.items() if e.get("optional")]
    assert optional == ["google/metricx-24-hybrid-xl-v2p6@safetensors"]
    key, e = optional[0], models[optional[0]]
    assert not st.selected(key, e, None, False)
    assert st.selected(key, e, None, True) and st.selected(key, e, [key], False)
    assert st.selected("BAAI/bge-m3", models["BAAI/bge-m3"], None, False)


def test_disk_plan_counts_what_is_missing_once(tmp_path):
    models = lock("models.lock.json", "models")
    env = {"HF_HUB_CACHE": str(tmp_path / "hub"), "INTRACT_MODELS": str(tmp_path / "models")}
    plan = st.disk_plan(models, environ=env)
    with_optional = st.disk_plan(models, include_optional=True, environ=env)
    xglm = models["facebook/xglm-4.5B"]["files"]["model.safetensors"]["bytes"]
    assert plan["download_bytes"] > xglm
    # the optional entry shares its pickles with the main MetricX entry, so only its conversion adds bytes
    assert with_optional["download_bytes"] == plan["download_bytes"]
    assert with_optional["conversion_bytes"] > plan["conversion_bytes"] + 14_000_000_000
    snap = tmp_path / "hub" / "models--facebook--xglm-4.5B" / "snapshots" / models["facebook/xglm-4.5B"]["revision"]
    snap.mkdir(parents=True)
    (snap / "model.safetensors").write_bytes(b"")
    assert st.disk_plan(models, environ=env)["download_bytes"] == plan["download_bytes"] - xglm


# ------------------------------------------------------------------------------------------ comparisons


def write_shard(work, lang, art, shard, rows, ext="jsonl.gz"):
    path = Path(work) / lang / art / f"shard-{shard}-of-2.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        if ext == "jsonl.gz":
            fh.writelines(json.dumps(r) + "\n" for r in rows)
        else:
            fh.writelines(f"# newdoc id = {sid}\n# sent_id = {sid}-1\n1\t{word}\n\n" for sid, word in rows)
    return path


def test_smoke_rows_are_compared_with_the_full_run(tmp_path):
    full, smoke = tmp_path / "full", tmp_path / "smoke"
    write_shard(full, "en-us", "segments", 0, [{"story_id": "a", "n": 1}, {"story_id": "b", "n": 2}])
    write_shard(full, "en-us", "segments", 1, [{"story_id": "c", "n": 3}])
    write_shard(smoke, "en-us", "segments", 0, [{"n": 2, "story_id": "b"}])  # key order does not matter
    write_shard(full, "en-us", "parses_stanza", 0, [("a", "x"), ("b", "y")], ext="conllu.gz")
    write_shard(smoke, "en-us", "parses_stanza", 0, [("b", "z")], ext="conllu.gz")
    (smoke / "_probe").mkdir()  # not a language
    report = cr.compare_rows(full, smoke, ["en-us"])
    seg, parse = report["artefacts"]["en-us/segments"], report["artefacts"]["en-us/parses_stanza"]
    assert seg["equal"] and seg["rows_compared"] == 1 and seg["sha256_base"] == seg["sha256_other"]
    assert not parse["equal"] and parse["differ"] == ["b"] and not report["all_equal"]
    out = tmp_path / "rows.json"
    code = cr.main(["rows", "--base", str(full), "--other", str(smoke), "--out", str(out)])
    assert code == 1 and json.loads(out.read_text(encoding="utf-8"))["artefacts"]["en-us/segments"]["equal"]


def test_the_bf16_check_pairs_text_values(tmp_path):
    fp32, bf16 = tmp_path / "smoke", tmp_path / "smoke_bf16"
    xs = [3.1, 4.2, 5.0, 6.3]
    write_shard(fp32, "en-us", "surprisal_xglm", 0,
                [{"story_id": s, "values": {"mean_surprisal_xglm": None, "mean_surprisal_xglm_all_words": x}}
                 for s, x in zip("abcd", xs, strict=True)])
    write_shard(bf16, "en-us", "surprisal_xglm", 0,
                [{"story_id": s, "values": {"mean_surprisal_xglm": None, "mean_surprisal_xglm_all_words": x + 0.01}}
                 for s, x in zip("abcd", xs, strict=True)])
    write_shard(fp32, "en-us", "coref_corpipe", 0,
                [{"story_id": s, "values": {}, "pair_continuity": p} for s, p in
                 [("a", [1, 0]), ("b", [1, 1]), ("c", [0, 0]), ("d", [0, 1, 1])]])
    write_shard(bf16, "en-us", "coref_corpipe", 0,
                [{"story_id": s, "values": {}, "pair_continuity": p} for s, p in
                 [("a", [0, 0]), ("b", [1, 1]), ("c", [1, 1]), ("d", [0, 1, 1])]])
    rep = cr.compare_bf16(fp32, bf16, 0.995, {"surprisal_xglm": "en-us", "coref_corpipe": "en-us",
                                               "qe_metricx": "de-de"})
    xglm, coref = rep["models"]["surprisal_xglm"], rep["models"]["coref_corpipe"]
    assert xglm["primary"] == "mean_surprisal_xglm_all_words" and xglm["passes"]
    assert xglm["values"]["mean_surprisal_xglm_all_words"]["r"] == pytest.approx(1.0)
    assert coref["passes"] is False and "PENDING" in coref["definition"]
    assert rep["models"]["qe_metricx"]["status"].startswith("not compared") and rep["all_pass"] is False
    assert cr.pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None and cr.pearson([1.0, 2.0], [1.0, 2.0]) is None


def test_the_bf16_check_reads_corpipe_shares_with_unsent_pairs(tmp_path):
    # coref_corpipe writes null for a pair whose sentences were not both sent, and the share over the pairs with data
    # as diagnostics.pair_continuity_share; neither may break the check or count as a pair without a shared entity.
    path = write_shard(tmp_path, "en-us", "coref_corpipe", 0, [
        {"story_id": "a", "values": {}, "pair_continuity": [1, None, 0], "diagnostics": {}},
        {"story_id": "b", "values": {}, "pair_continuity": [None, None], "diagnostics": {}},
        {"story_id": "c", "values": {}, "pair_continuity": [0, 0],
         "diagnostics": {"pair_continuity_share": 0.25}},
    ])
    got = cr.read_values(path, "pair_continuity", ("pair_continuity_mean",))
    assert got == {"a": {"pair_continuity_mean": 0.5}, "b": {}, "c": {"pair_continuity_mean": 0.25}}
