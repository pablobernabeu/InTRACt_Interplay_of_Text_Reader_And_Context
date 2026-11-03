"""Tests of the aggregate_timing stage on hand-built timing records (no text, no models)."""

import json
import math
from pathlib import Path

import pytest

from intract_features import cli
from intract_features import config as config_mod
from intract_features.stages import aggregate_timing as agg

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CAT_WS, CAT_CHARS = 17_309_915, 101_672_026


@pytest.fixture(scope="module")
def cfg():
    return config_mod.load(CONFIG_DIR)


@pytest.fixture
def stage_cfg(cfg):
    return cfg["stages"]["aggregate_timing"]


@pytest.fixture
def ratio(stage_cfg):
    return agg.level_char_ratio(stage_cfg["catalogue"]["levels"])


def write_record(work, lang, stage, shard, nshards, *, device="cpu", env="core", wall=10.0, cpu=9.0, counts=None,
                 **extra):
    rec = {"stage": stage, "lang": lang, "shard": shard, "nshards": nshards, "device": device, "env": env,
           "wall_seconds": wall, "cpu_seconds": cpu, "peak_rss_mb": 100.0 + shard, "code_commit": "tree-sha256:ab",
           "slurm_job_id": "123", "counts": counts or {}, **extra}
    path = Path(work) / lang / "_timing" / f"{stage}-shard-{shard}-of-{nshards}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec), encoding="utf-8")
    return path


def write_side(work, lang, stage, shard, nshards, **fields):
    rec = {"stage": stage, "lang": lang, "shard": shard, "nshards": nshards, **fields}
    path = Path(work) / "_runs" / lang / f"{stage}-shard-{shard}-of-{nshards}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec), encoding="utf-8")
    return path


def write_probe(work, kind, stage, lang, nshards, wall, documents=1, **counts):
    return write_record(Path(work) / "_probe" / kind / stage, lang, stage, 0, nshards, wall=wall,
                        counts={"documents": documents, **counts})


def rows_for(work, cfg, target=4):
    scfg = cfg["stages"]["aggregate_timing"]
    recs, _ = agg.read_timing_records(work, "all", ["aggregate_timing"])
    side, _ = agg.read_side_records(work)
    probes, _ = agg.read_probe_records(work, scfg["probe"]["dir"])
    return {r["stage"]: r for r in (agg.project(r, scfg, target, probes) for r in agg.summarise(recs, scfg, side))}


# ------------------------------------------------------------------------------------------------- factors


def test_level_char_ratio_is_the_token_weighted_mean(stage_cfg):
    levels = stage_cfg["catalogue"]["levels"]
    young, mid, old = 13500 * 357.2, 13500 * 409.2, 13500 * 513.5
    expected = (young * 1.045 + mid * 1.072 + old * 1.088) / (young + mid + old)
    # the classics take that same mean, so the overall ratio equals it
    assert agg.level_char_ratio(levels) == pytest.approx(expected, rel=1e-12)
    assert 1.07 < expected < 1.072


def test_level_char_ratio_needs_a_rated_level():
    with pytest.raises(ValueError):
        agg.level_char_ratio({"classic": {"texts": 1, "mean_tokens": 10}})


def test_projection_factors_set_each_unit_against_the_same_unit(stage_cfg, ratio):
    cat = stage_cfg["catalogue"]
    amounts = {"whitespace_tokens": 1_000_000, "characters": 5_500_000, "documents": 2000}
    assert agg.projection_factor(amounts, "whitespace_tokens", cat, ratio) == pytest.approx(CAT_WS / 1_000_000)
    assert agg.projection_factor(amounts, "characters", cat, ratio) == pytest.approx(CAT_CHARS / 5_500_000)
    assert agg.projection_factor(amounts, "documents", cat, ratio) == pytest.approx(40559 / 2000)
    assert agg.projection_factor(amounts, "level_ratios", cat, ratio) == pytest.approx(17.309915 * ratio)
    assert agg.projection_factor({"whitespace_tokens": None}, "whitespace_tokens", cat, ratio) is None
    with pytest.raises(ValueError):
        agg.projection_factor(amounts, "words", cat, ratio)


def test_shard_amount_borrows_only_for_the_same_documents():
    refs = agg.reference_index([{"stage": "sat", "lang": "en-us", "shard": 0, "nshards": 4,
                                 "counts": {"documents": 100, "whitespace_tokens": 40_000, "characters": 230_000}}],
                               ["sat"])
    gram = {"stage": "features_gramlex", "lang": "en-us", "shard": 0, "nshards": 4, "counts": {"documents": 100}}
    assert agg.shard_amount(gram, "whitespace_tokens", refs) == (40_000.0, "reference:sat")
    other = {**gram, "counts": {"documents": 99}}  # a --limit run: not the same texts
    assert agg.shard_amount(other, "whitespace_tokens", refs) == (None, "no whitespace_tokens count")
    coref = {"stage": "coref_corpipe", "lang": "en-us", "shard": 0, "nshards": 4,
             "counts": {"documents": 100, "characters": 226_000, "words": 52_000}}
    assert agg.shard_amount(coref, "characters", refs) == (226_000.0, "own")
    assert agg.shard_amount(coref, "characters", refs, prefer="reference") == (230_000.0, "reference:sat")
    alone = {**coref, "lang": "fr-fr"}
    assert agg.shard_amount(alone, "whitespace_tokens", refs) == (None, "no whitespace_tokens count")
    amount, source = agg.shard_amount(alone, "whitespace_tokens", refs, words_fallback=True)
    assert amount == 52_000.0 and "approximate" in source


# --------------------------------------------------------------------------------------------- units


def test_parser_words_are_never_set_against_whitespace_tokens(tmp_path, cfg):
    # 5,830 syntactic words over 5,000 whitespace tokens: the projection divides by the 5,000
    write_record(tmp_path, "en-us", "parse_stanza", 0, 1, wall=100.0, cpu=90.0,
                 counts={"documents": 10, "words": 5830, "whitespace_tokens": 5000, "characters": 30_000})
    stanza = rows_for(tmp_path, cfg, target=1)["parse_stanza"]
    assert (stanza["unit"], stanza["method"]) == ("whitespace_tokens", "whitespace_tokens")
    assert stanza["unit_source"] == "own"
    assert stanza["factor"] == pytest.approx(CAT_WS / 5000)
    assert stanza["words_per_whitespace_token"] == pytest.approx(1.166)
    assert stanza["words_per_cpu_second"] == pytest.approx(5830 / 90)
    # no split source applies to Stanza here, so the projection is the unsplit upper bound, and it is flagged
    assert stanza["split"] == "none" and stanza["projected_wall_hours"] == pytest.approx(100 * CAT_WS / 5000 / 3600)
    assert stanza["projected_core_hours"] == pytest.approx(stanza["projected_wall_hours"] * 1)


def test_stages_without_a_count_borrow_it_from_the_reference_stage(tmp_path, cfg, ratio):
    for s in range(2):
        write_record(tmp_path, "en-us", "sat", s, 2, device="gpu", wall=50.0,
                     counts={"documents": 200, "words": 79_000, "whitespace_tokens": 80_000, "characters": 440_000})
        write_record(tmp_path, "en-us", "features_gramlex", s, 2, wall=30.0, counts={"documents": 200, "sentences": 9})
        write_record(tmp_path, "en-us", "coref_corpipe", s, 2, device="gpu", env="corpipe", wall=80.0,
                     counts={"documents": 200, "words": 95_000, "characters": 430_000, "tokens": 120_000})
    rows = rows_for(tmp_path, cfg, target=2)
    gram, coref = rows["features_gramlex"], rows["coref_corpipe"]
    assert gram["unit_source"] == "reference:sat" and gram["factor"] == pytest.approx(CAT_WS / 160_000)
    # CorPipe's syntactic words (95,000 a shard) are not used; its characters come from sat for the same texts
    assert coref["method"] == "level_ratios" and coref["unit_source"] == "reference:sat"
    assert coref["factor"] == pytest.approx(CAT_WS / 160_000 * ratio)
    assert coref["alternative_method"] == "characters"
    assert coref["amounts"]["characters"] == 880_000


def test_shards_without_documents_add_nothing(tmp_path, cfg, ratio):
    # seg_check computes its report in the run with --shard 0 and the other shards' runs return zero counts; those
    # must neither stop the stage's projection nor borrow an amount from another stage.
    write_record(tmp_path, "en-us", "seg_check", 0, 2, wall=40.0,
                 counts={"documents": 300, "words": 99_000, "whitespace_tokens": 100_000, "characters": 550_000})
    write_record(tmp_path, "en-us", "seg_check", 1, 2, wall=0.5,
                 counts={"documents": 0, "words": 0, "whitespace_tokens": 0, "characters": 0})
    row = rows_for(tmp_path, cfg, target=2)["seg_check"]
    assert row["amounts"]["whitespace_tokens"] == 100_000 and row["complete"]
    assert row["method"] == "level_ratios" and row["factor"] == pytest.approx(CAT_WS / 100_000 * ratio)
    assert row["projected_wall_hours"] is not None


def test_qe_metricx_scales_by_characters_over_every_translation(tmp_path, cfg):
    for s in range(4):
        write_record(tmp_path, "de-de", "qe_metricx", s, 4, device="gpu", wall=1000.0,
                     counts={"documents": 100, "words": 1000, "characters": 15_000, "tokens": 3000})
    qe = rows_for(tmp_path, cfg, target=4)["qe_metricx"]
    assert qe["method"] == "characters" and qe["alternative_method"] is None
    assert qe["factor"] == pytest.approx(2 * 18 * CAT_CHARS / 60_000)
    assert qe["target_processes"] == 4 * 18


def test_unknown_stage_takes_the_default_unit(tmp_path, cfg, stage_cfg):
    write_record(tmp_path, "en-us", "new_stage", 0, 1, counts={"documents": 1, "whitespace_tokens": 10})
    assert rows_for(tmp_path, cfg)["new_stage"]["unit"] == stage_cfg["projection"]["default_unit"]


# --------------------------------------------------------------------------------------------- fixed costs


def load_dominated_run(work, *, cold_probe=True, side=True):
    """A smoke-sized GPU stage: each process loads for 300 s, then computes 1 s per document."""
    for s in range(4):
        write_record(work, "en-us", "sat", s, 4, device="gpu", wall=400.0,
                     counts={"documents": 100, "words": 39_000, "whitespace_tokens": 40_000, "characters": 230_000})
        if side:
            write_side(work, "en-us", "sat", s, 4, cold=False, env_active="core", cpus=16,
                       process_tree={"user_seconds": 380.0, "sys_seconds": 10.0})
    write_probe(work, "warm", "sat", "en-us", 4, wall=301.0)
    if cold_probe:
        write_probe(work, "cold", "sat", "en-us", 4, wall=541.0)  # the job's 240 s cold start, plus the load


def test_load_dominated_records_scale_only_their_compute(tmp_path, cfg, ratio):
    load_dominated_run(tmp_path)
    sat = rows_for(tmp_path, cfg)["sat"]
    factor = CAT_WS / 160_000 * ratio
    assert sat["split"] == "probe" and sat["factor"] == pytest.approx(factor)
    assert sat["fixed_seconds"] == pytest.approx(1200.0, rel=1e-6)
    assert sat["compute_seconds"] == pytest.approx(400.0, rel=1e-5)
    # four warm processes and the one cold start of the job, carried once; 400 s of compute scaled
    assert sat["projected_fixed_hours"] == pytest.approx((4 * 300 + 240) / 3600, rel=1e-5)
    assert sat["projected_compute_hours"] == pytest.approx(400 * factor / 3600, rel=1e-5)
    assert sat["unsplit_projected_wall_hours"] == pytest.approx(1600 * factor / 3600)
    assert sat["projected_wall_hours"] < sat["unsplit_projected_wall_hours"] / 3.5
    assert sat["cold_starts"] == 1 and sat["env_active"] == "core"
    assert sat["process_cpu_seconds"] == pytest.approx(4 * 390.0)


def test_cold_shards_pay_the_cold_start_again(tmp_path, cfg):
    load_dominated_run(tmp_path)
    for s in (1, 2, 3):  # array tasks: each starts cold in its own job
        write_record(tmp_path, "en-us", "sat", s, 4, device="gpu", wall=640.0,
                     counts={"documents": 100, "words": 39_000, "whitespace_tokens": 40_000, "characters": 230_000})
        write_side(tmp_path, "en-us", "sat", s, 4, cold=True)
    sat = rows_for(tmp_path, cfg)["sat"]
    assert sat["fixed_seconds"] == pytest.approx(300 + 3 * 540, rel=1e-5)
    assert sat["compute_seconds"] == pytest.approx(400.0, rel=1e-4)
    assert sat["cold_starts"] == 4
    assert sat["projected_fixed_hours"] == pytest.approx((4 * 300 + 4 * 240) / 3600, rel=1e-5)


def test_without_a_cold_probe_the_split_says_so(tmp_path, cfg):
    load_dominated_run(tmp_path, cold_probe=False, side=False)
    sat = rows_for(tmp_path, cfg)["sat"]
    assert sat["split"] == "probe" and sat["compute_seconds"] == pytest.approx(400.0, rel=1e-5)
    assert "no cold probe" in sat["notes"] and "without a side record" in sat["notes"]


def test_a_probe_as_large_as_a_shard_is_not_used(tmp_path, cfg):
    for s in range(2):
        write_record(tmp_path, "en-us", "sat", s, 2, device="gpu", wall=10.0,
                     counts={"documents": 1, "whitespace_tokens": 400, "characters": 2300})
    write_probe(tmp_path, "warm", "sat", "en-us", 2, wall=10.0)
    assert rows_for(tmp_path, cfg, target=2)["sat"]["split"] == "none"


def test_timers_split_the_encoders(tmp_path, cfg):
    for s in range(4):
        write_record(tmp_path, "en-us", "encode_e5", s, 4, device="gpu", wall=100.0,
                     counts={"documents": 100, "words": 39_000, "characters": 230_000, "seconds_encode": 60.0})
        write_record(tmp_path, "en-us", "sat", s, 4, device="gpu", wall=1.0,
                     counts={"documents": 100, "whitespace_tokens": 40_000, "characters": 230_000})
    e5 = rows_for(tmp_path, cfg)["encode_e5"]
    assert e5["split"] == "timers" and e5["unit_source"] == "reference:sat"
    assert (e5["fixed_seconds"], e5["compute_seconds"]) == (pytest.approx(160.0), pytest.approx(240.0))
    assert e5["projected_fixed_hours"] == pytest.approx(160 / 3600)
    assert e5["projected_compute_hours"] == pytest.approx(240 * e5["factor"] / 3600)


def test_reported_fixed_costs_split_udpipe(tmp_path, cfg):
    for s in range(4):
        write_record(tmp_path, "en-us", "parse_udpipe", s, 4, device="gpu", env="udpipe", wall=300.0,
                     counts={"documents": 100, "words": 46_000, "whitespace_tokens": 40_000,
                             "udpipe": {"server": {"startup_seconds": 185.0}}})
    ud = rows_for(tmp_path, cfg)["parse_udpipe"]
    assert ud["split"] == "fixed_keys"
    assert (ud["fixed_seconds"], ud["compute_seconds"]) == (pytest.approx(740.0), pytest.approx(460.0))
    assert ud["projected_wall_hours"] == pytest.approx((740 + 460 * CAT_WS / 160_000) / 3600)


def test_split_order_is_validated(tmp_path, cfg):
    write_record(tmp_path, "en-us", "sat", 0, 1, device="gpu", counts={"documents": 1, "whitespace_tokens": 5})
    scfg = {**cfg["stages"]["aggregate_timing"], "split": {"order": ["guess"]}}
    recs, _ = agg.read_timing_records(tmp_path, "all", [])
    with pytest.raises(ValueError):
        agg.project(agg.summarise(recs, scfg)[0], scfg, 1)


def test_probe_split_solves_rate_and_costs_together():
    shards = [{"wall": 400.0, "documents": 100.0, "cold": False} for _ in range(4)]
    p = agg.probe_split(shards, {"wall_seconds": 301.0, "counts": {"documents": 1}},
                        {"wall_seconds": 541.0, "counts": {"documents": 1}})
    assert p["process_fixed"] == pytest.approx(300.0) and p["cold_excess"] == pytest.approx(240.0)
    assert p["rate_per_document"] == pytest.approx(1.0)


# ------------------------------------------------------------------------------------------ reading and run


def test_read_and_summarise_flag_incomplete_and_stray_files(tmp_path, cfg):
    for s in range(4):
        write_record(tmp_path, "en-us", "sat", s, 4, device="gpu", wall=100.0,
                     counts={"documents": 100, "words": 40_000, "characters": 230_000, "tokens": 60_000},
                     gpu_name="NVIDIA L40S", gpu_peak_allocated_mb=2000.0 + s)
    for s in range(3):  # shard 3 missing
        write_record(tmp_path, "en-us", "parse_stanza", s, 4, counts={"documents": 100, "words": 45_000})
    write_record(tmp_path, "en-us", "aggregate_timing", 0, 1)  # its own record is left out
    bad = tmp_path / "en-us" / "_timing" / "documents-shard-0-of-4.json"
    bad.write_text("{not json", encoding="utf-8")
    renamed = write_record(tmp_path, "en-us", "encode_e5", 0, 4)
    renamed.rename(renamed.with_name("encode_bgem3-shard-0-of-4.json"))  # its stage disagrees with its name
    nan = tmp_path / "en-us" / "_timing" / "seg_check-shard-0-of-4.json"
    nan.write_text('{"stage": "seg_check", "lang": "en-us", "shard": 0, "nshards": 4, "wall_seconds": NaN}',
                   encoding="utf-8")
    (tmp_path / "en-us" / "_timing" / "summary.tsv").write_text("ignored", encoding="utf-8")
    write_probe(tmp_path, "warm", "sat", "en-us", 4, wall=5.0)  # a probe folder is not a language
    recs, notes = agg.read_timing_records(tmp_path, "all", ["aggregate_timing"])
    assert len(recs) == 7 and len(notes) == 3
    rows = {r["stage"]: r for r in agg.summarise(recs, cfg["stages"]["aggregate_timing"])}
    assert set(rows) == {"sat", "parse_stanza"}
    sat, stanza = rows["sat"], rows["parse_stanza"]
    assert sat["complete"] and sat["shards_found"] == 4 and sat["words"] == 160_000 and sat["tokens"] == 240_000
    assert sat["gpu_names"] == "NVIDIA L40S" and sat["gpu_peak_allocated_mb"] == 2003.0
    assert not stanza["complete"] and stanza["shards_found"] == 3 and stanza["tokens"] is None
    assert stanza["peak_rss_mb"] == 102.0


def test_mixed_shard_counts_are_incomplete(tmp_path, cfg):
    write_record(tmp_path, "en-us", "sat", 0, 1, counts={"words": 10})
    write_record(tmp_path, "en-us", "sat", 0, 4, counts={"words": 10})
    (row,) = agg.summarise(agg.read_timing_records(tmp_path, "all", [])[0], cfg["stages"]["aggregate_timing"])
    assert row["nshards"] == "1/4" and not row["complete"]


def test_langs_can_be_listed(tmp_path):
    write_record(tmp_path, "en-us", "sat", 0, 1, counts={"words": 10})
    write_record(tmp_path, "de-de", "qe_metricx", 0, 1, counts={"words": 10})
    recs, notes = agg.read_timing_records(tmp_path, ["de-de", "fr-fr"], [])
    assert [r["lang"] for r in recs] == ["de-de"] and notes == ["fr-fr: no _timing folder"]


def test_side_and_probe_records_are_checked_against_their_names(tmp_path):
    write_side(tmp_path, "en-us", "sat", 0, 4, cold=True)
    path = write_side(tmp_path, "en-us", "sat", 1, 4, cold=False)
    path.rename(path.with_name("sat-shard-2-of-4.json"))
    side, notes = agg.read_side_records(tmp_path)
    assert list(side) == [("en-us", "sat", 0, 4)] and len(notes) == 1
    write_probe(tmp_path, "cold", "sat", "en-us", 4, wall=9.0)
    stray = write_probe(tmp_path, "warm", "encode_e5", "en-us", 4, wall=3.0)
    stray.rename(stray.with_name("sat-shard-0-of-4.json"))  # a sat record in encode_e5's probe folder
    probes, _ = agg.read_probe_records(tmp_path, "_probe")
    assert set(probes) == {("en-us", "sat")} and set(probes[("en-us", "sat")]) == {"cold"}


def test_run_writes_a_strict_table_and_a_stable_tsv(tmp_path, cfg, ratio):
    for s in range(2):
        write_record(tmp_path, "en-us", "sat", s, 2, device="gpu", wall=50.0, cpu=40.0,
                     counts={"documents": 200, "words": 79_000, "whitespace_tokens": 80_000, "characters": 440_000})
        write_record(tmp_path, "en-us", "parse_stanza", s, 2, wall=150.0, cpu=140.0,
                     counts={"documents": 200, "words": 90_000, "whitespace_tokens": 80_000, "characters": 440_000})
    write_record(tmp_path, "de-de", "qe_metricx", 0, 1, device="gpu", env="metricx", wall=600.0,
                 counts={"documents": 400, "pairs": 400, "words": 5000, "characters": 60_000, "tokens": 20_000,
                         "input": {"sha256": "x"}})
    write_side(tmp_path, "de-de", "qe_metricx", 0, 1, env_active="core", cold=True)
    ctx = cli.StageContext(stage=agg.STAGE, config=cfg, lang="en-us", work=tmp_path)
    counts = agg.run(ctx)
    assert counts["records"] == 5 and counts["stages"] == 3 and counts["files_left_out"] == 0
    tsv = (tmp_path / "_summary" / "timing.tsv").read_text(encoding="utf-8")
    header, *lines = tsv.rstrip("\n").split("\n")
    assert header.split("\t") == list(agg.COLUMNS)
    assert len(lines) == 3 and all(len(line.split("\t")) == len(agg.COLUMNS) for line in lines)
    summary = json.loads((tmp_path / "_summary" / "timing.json").read_text(encoding="utf-8"))
    t = summary["totals"]
    assert t["incomplete_stages"] == [] and t["stages_without_projection"] == []
    assert sorted(t["stages_projected_unsplit"]) == ["de-de/qe_metricx", "en-us/parse_stanza", "en-us/sat"]
    target = cfg["shards"]["default"]
    assert summary["target_shards"] == target
    sat_hours = 100.0 * CAT_WS / 160_000 * ratio / 3600
    qe_hours = 600.0 * 36 * CAT_CHARS / 60_000 / 3600
    assert t["projected_gpu_hours"] == pytest.approx(sat_hours + qe_hours)
    assert t["projected_core_hours"] == pytest.approx(300.0 * CAT_WS / 160_000 / 3600)
    assert t["measured_gpu_hours"] == pytest.approx(700 / 3600)
    qe = next(r for r in summary["stages"] if r["stage"] == "qe_metricx")
    assert (qe["env"], qe["env_active"]) == ("metricx", "core") and "_shards" not in qe
    agg.run(ctx)
    assert (tmp_path / "_summary" / "timing.tsv").read_text(encoding="utf-8") == tsv


def test_run_on_an_empty_work_folder(tmp_path, cfg):
    ctx = cli.StageContext(stage=agg.STAGE, config=cfg, lang="en-us", work=tmp_path / "missing")
    assert agg.run(ctx)["stages"] == 0
    assert (tmp_path / "missing" / "_summary" / "timing.tsv").read_text(encoding="utf-8").startswith("lang\tstage")


def test_cli_discovers_and_runs_the_stage(tmp_path):
    assert "aggregate_timing" in cli.discover()
    write_record(tmp_path, "en-us", "sat", 0, 1, device="gpu",
                 counts={"documents": 1, "whitespace_tokens": 100, "characters": 550})
    assert cli.main(["run", "aggregate_timing", "--config", str(CONFIG_DIR), "--work", str(tmp_path)]) == 0
    own = tmp_path / "en-us" / "_timing" / "aggregate_timing-shard-0-of-1.json"
    assert json.loads(own.read_text(encoding="utf-8"))["counts"]["stages"] == 1
    # a second run leaves its own earlier record out of the table
    assert cli.main(["run", "aggregate_timing", "--config", str(CONFIG_DIR), "--work", str(tmp_path)]) == 0
    summary = json.loads((tmp_path / "_summary" / "timing.json").read_text(encoding="utf-8"))
    assert [r["stage"] for r in summary["stages"]] == ["sat"]


def test_target_shards_default_to_the_pipeline(stage_cfg):
    assert agg.target_shard_count(stage_cfg, {"shards": {"default": 4}}) == 4
    assert agg.target_shard_count({"projection": {"target_shards": 8}}, {"shards": {"default": 4}}) == 8


def test_cells_are_formatted_for_the_tsv():
    assert agg._cell(None, 2) == "" and agg._cell(True, 2) == "true" and agg._cell(1.23456, 2) == "1.23"
    assert agg._cell(math.inf, 2) == "" and agg._cell("a\tb", 2) == "a b" and agg._cell(7, 2) == "7"
    assert agg.dotted({"a": {"b": 2}}, "a.b") == 2 and agg.dotted({"a": 1}, "a.b") is None
    assert agg.timer_seconds({"seconds_x": 1.5, "seconds_y": 2, "other": 9}, ["seconds_*"]) == 3.5
    assert agg.timer_seconds({"other": 9}, ["seconds_*"]) is None
