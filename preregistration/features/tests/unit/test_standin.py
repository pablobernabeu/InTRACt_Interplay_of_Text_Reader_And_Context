"""Tests of the stand-in builder in standin/: pins, candidates, selection, paging, the published
schema, the smoke property, typography and the structure table.

Every fixture is synthetic, apart from the public SimpleStories test split, which the last
tests read when pyarrow and the pinned file are present. No catalogue text is read.
"""

import csv
import dataclasses
import hashlib
import io
import json
import lzma
import os
import random
import re
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

FEATURES = Path(__file__).resolve().parents[2]
CONFIG = FEATURES / "config"
REVISION = "e63b8adc3b1a1bdc7cac5b500d150b71346b0628"


@pytest.fixture(scope="module")
def si():
    """The stand-in modules. standin/ sits beside the installed package, not inside it; pyproject.toml's
    [tool.pytest.ini_options] pythonpath puts the features folder on the import path for the tests."""
    from standin import build_standin, catalogue_structure, typography

    return SimpleNamespace(bs=build_standin, cs=catalogue_structure, ty=typography)


@pytest.fixture(scope="module")
def settings(si):
    return si.bs.Settings.load(CONFIG)


# --- Fixtures ------------------------------------------------------------------------------

WORDS = ["the", "a", "cat", "dog", "ran", "sat", "bird", "tree", "small", "big", "happy", "sad", "found", "looked",
         "went", "home", "friend", "river", "light", "stone", "path", "door"]


def make_story(rng: random.Random, n_tokens: int) -> str:
    """An ASCII story of exactly n_tokens whitespace tokens: sentences with terminal marks, some
    dialogue, an ellipsis now and then, paragraphs with stray spaces, as SimpleStories writes."""
    tokens: list[str] = []
    while len(tokens) < n_tokens:
        sentence = [rng.choice(WORDS) for _ in range(rng.randint(4, 12))]
        sentence[0] = sentence[0].capitalize()
        end = rng.choice([".", ".", ".", "!", "?", "..."])
        if rng.random() < 0.3:
            sentence[0], sentence[-1] = '"' + sentence[0], sentence[-1] + end + '"'
        else:
            sentence[-1] += end
        tokens.extend(sentence)
    tokens = tokens[:n_tokens]
    lines, i = [], 0
    while i < len(tokens):
        j = min(len(tokens), i + rng.randint(15, 40))
        lines.append(("  " if rng.random() < 0.2 else "") + " ".join(tokens[i:j]) + (" " if rng.random() < 0.2 else ""))
        i = j
    return "\n\n".join(lines)


def candidate_rows(seed: int = 1, count: int = 1500, low: int = 30, high: int = 700) -> list[tuple[str, str, str]]:
    rng = random.Random(seed)
    return [(f"{i:032x}-{i % 7}", make_story(rng, rng.randint(low, high)), f"topic {i % 13}") for i in range(count)]


def make_targets(si, seed: int = 2) -> list:
    """Young, mid and old versions of 12 combinations, plus three classics, one without a level."""
    rng = random.Random(seed)
    targets, sid = [], 0
    for _ in range(12):
        first = sid + 1
        for level, pages, mean in (("young", 17, 21), ("mid", 17, 24), ("old", 20, 27)):
            sid += 1
            tpp = tuple(max(1, round(rng.gauss(mean, 5))) for _ in range(pages))
            targets.append(si.cs.Target(str(sid), "generated", level, tpp, sum(tpp) * 6, str(first)))
    for level, pages, mean in (("young", 25, 48), ("old", 40, 42), ("", 12, 30)):
        sid += 1
        tpp = tuple(max(1, round(rng.gauss(mean, 10))) for _ in range(pages))
        targets.append(si.cs.Target(str(sid), "classic", level, tpp, sum(tpp) * 6, str(sid)))
    return targets


def write_structure_tsv(si, targets, path: Path) -> Path:
    cols = si.cs.STRUCTURE_COLS + [si.cs.COMBINATION_COL]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(cols) + "\n")
        for t in targets:
            fh.write("\t".join(map(str, [t.story_id, t.kind, t.level or si.cs.BLANK_LEVEL, t.pages, t.tokens,
                                         t.chars_joined, " ".join(map(str, t.tokens_per_page)),
                                         " ".join(str(6 * x) for x in t.tokens_per_page), t.combination])) + "\n")
    return path


def read_table(path: Path) -> tuple[str, list[dict]]:
    with lzma.open(path, "rt", encoding="utf-8", newline="") as fh:
        raw = fh.read()
    return raw, list(csv.DictReader(io.StringIO(raw, newline="")))


def quiet(_message: str) -> None:
    pass


# --- Configuration and pins ----------------------------------------------------------------


def test_config_pins_the_revision_and_seven_train_shards(si, settings):
    assert settings.repo == "SimpleStories/SimpleStories"
    assert settings.revision == REVISION
    train = settings.splits["train"]
    assert [p.name for p in train] == [f"train-{i:05d}-of-00007.parquet" for i in range(7)]
    assert len({p.sha256 for p in train}) == 7
    assert all(re.fullmatch(r"[0-9a-f]{64}", p.sha256) and p.size > 200_000_000 for p in train)
    assert settings.splits["test"][0].sha256.startswith("24a513732fd6")
    assert settings.expected_rows == {"train": 2115696, "test": 21371}
    assert settings.licence == "MIT" and "MIT License" in settings.notice and REVISION in settings.notice


def test_config_constants_follow_the_scout_design(si, settings):
    assert settings.candidate_key == "intract-standin|v1|cand|"
    assert settings.target_key == "intract-standin|v1|target|"
    assert settings.min_tokens == 50
    assert settings.tolerance == Fraction(3, 100)
    assert settings.join_unit == 500
    assert settings.snap_window == 6
    assert settings.terminal_marks == (".", "!", "?", "…")
    assert settings.id_prefix == "SI" and settings.lang == "en-us"
    assert si.bs.smoke_size(40559, settings.smoke_fraction) == 406


def test_config_merges_with_the_pipeline_loader():
    from intract_features import config

    cfg = config.load(CONFIG)
    assert cfg["stages"]["standin"]["source"]["revision"] == REVISION


def test_settings_refuse_unknown_switch_values(si, settings):
    with pytest.raises(si.bs.StandinError):
        dataclasses.replace(settings, line_breaks="newline").check()
    with pytest.raises(si.bs.StandinError):
        dataclasses.replace(settings, duplicate_ids="ignore").check()


def test_verify_file_checks_size_and_sha256(si, tmp_path):
    f = tmp_path / "x.parquet"
    f.write_bytes(b"public bytes")
    pin = si.bs.Pin("data/x.parquet", 12, hashlib.sha256(b"public bytes").hexdigest())
    si.bs.verify_file(f, pin)
    with pytest.raises(si.bs.PinError, match="bytes"):
        si.bs.verify_file(f, dataclasses.replace(pin, size=13))
    with pytest.raises(si.bs.PinError, match="SHA-256"):
        si.bs.verify_file(f, dataclasses.replace(pin, sha256="0" * 64))
    with pytest.raises(si.bs.PinError, match="missing"):
        si.bs.verify_file(tmp_path / "absent.parquet", pin)


def test_download_verifies_before_keeping(si, settings, tmp_path):
    payload = b"a pinned public file"
    remote = tmp_path / "remote" / "datasets" / Path(settings.repo) / "resolve" / settings.revision / "data"
    remote.mkdir(parents=True)
    (remote / "x.parquet").write_bytes(payload)
    local = dataclasses.replace(settings, base_url=(tmp_path / "remote").as_uri())
    pin = si.bs.Pin("data/x.parquet", len(payload), hashlib.sha256(payload).hexdigest())
    dest = tmp_path / "dest"
    assert si.bs.download([pin], dest, local, log=quiet) == [dest / "x.parquet"]
    assert (dest / "x.parquet").read_bytes() == payload
    si.bs.download([pin], dest, local, log=quiet)  # present: verified, not fetched again
    bad = dataclasses.replace(pin, path="data/x.parquet", sha256="f" * 64)
    with pytest.raises(si.bs.PinError):
        si.bs.download([bad], tmp_path / "dest2", local, log=quiet)
    assert not list((tmp_path / "dest2").iterdir())  # no partial or unverified file is left


# --- Candidates and keys -------------------------------------------------------------------


def test_candidate_lines_and_key(si, settings):
    assert si.bs.candidate_lines("  One two. \n\n Three four!\n   \n") == ["One two.", "Three four!"]
    assert si.bs.candidate_key("abc-1", settings.candidate_key) == hashlib.sha256(
        b"intract-standin|v1|cand|abc-1").digest()


def test_target_key_and_ascending_order(si, settings):
    t = si.cs.Target("12", "generated", "mid", (3, 4))
    assert si.bs.target_key(t, settings) == hashlib.sha256(b"intract-standin|v1|target|12|mid").digest()
    blank = si.cs.Target("7", "classic", "", (5,))
    assert si.bs.target_key(blank, settings) == hashlib.sha256(b"intract-standin|v1|target|7|").digest()
    targets = make_targets(si)
    ranked = si.bs.rank_targets(targets, settings)
    keys = [si.bs.target_key(t, settings) for t in ranked]
    assert keys == sorted(keys) and len(ranked) == len(targets)


def test_story_keys_are_shared_by_the_versions_of_a_story(si, settings):
    ranked = si.bs.rank_targets(make_targets(si), settings)
    keys = si.bs.story_keys(ranked, "SK")
    assert len(keys) == 12 + 3
    assert keys[ranked[0].combination] == "SK1"


# --- The candidate pool and selection ------------------------------------------------------


def pool_of(si, entries):
    """A frozen pool from (key byte, n) pairs; keys are 32 bytes of the given value."""
    pool = si.bs.CandidatePool()
    for row, (kb, n) in enumerate(entries):
        pool.add(bytes([kb]) * 32, n, 0, row)
    pool.freeze()
    return pool


def test_tolerance_is_inclusive_and_exact(si):
    tol = Fraction(3, 100)
    assert si.bs.within_tolerance(103, 100, tol) and not si.bs.within_tolerance(104, 100, tol)
    assert pool_of(si, [(1, 103)]).select(Fraction(100), tol).n == 103  # |3| <= 0.03 * 100
    assert pool_of(si, [(1, 104)]).select(Fraction(100), tol) is None
    aim = Fraction(1001, 3)  # 333.67; the window is 10.01 tokens
    assert pool_of(si, [(1, 344)]).select(aim, tol) is None
    assert pool_of(si, [(1, 343)]).select(aim, tol).n == 343


def test_nearest_length_first_then_smallest_key(si):
    pool = pool_of(si, [(9, 100), (5, 100), (1, 99), (2, 101)])
    first = pool.select(Fraction(100), Fraction(3, 100))
    assert (first.n, first.key[0]) == (100, 5)  # exact length wins, and the smaller key within it
    assert pool.select(Fraction(100), Fraction(3, 100)).key[0] == 9
    tie = pool.select(Fraction(100), Fraction(3, 100))
    assert (tie.n, tie.key[0]) == (99, 1)  # 99 and 101 are equally near; the smaller key wins
    assert pool.select(Fraction(100), Fraction(3, 100)).n == 101
    assert pool.select(Fraction(100), Fraction(3, 100)) is None


def test_nearest_fallback_reaches_any_length(si):
    pool = pool_of(si, [(1, 60), (2, 900)])
    assert pool.select(Fraction(10), None).n == 60  # below every length
    assert pool.select(Fraction(5000), None).n == 900  # above every length
    assert pool.select(Fraction(100), None) is None  # empty


def test_repeated_generation_ids_keep_the_first(si):
    pool = si.bs.CandidatePool()
    key = b"\x07" * 32
    pool.add(key, 80, 0, 5)
    pool.add(key, 90, 1, 2)
    pool.add(b"\x08" * 32, 70, 0, 1)
    assert pool.freeze("keep_first") == 1
    pick = pool.select(Fraction(85), None)
    assert (pick.shard, pick.row, pick.n) == (0, 5, 80)
    fail = si.bs.CandidatePool()
    fail.add(key, 80, 0, 5)
    fail.add(key, 90, 1, 2)
    with pytest.raises(si.bs.StandinError):
        fail.freeze("fail")


def test_join_aims_at_t_over_m_then_the_remainder(si, settings):
    # Nothing near 900, so m = ceil(900/500) = 2: one piece near 450, the other near the remainder.
    pool = pool_of(si, [(4, 452), (3, 440), (9, 445), (1, 60)])
    sel = si.bs.select_for(pool, 900, settings)
    assert sel.m == 2 and sel.pieces_in_tolerance == (True, True)
    assert sorted(p.n for p in sel.pieces) == [445, 452]  # 452 first (nearest 450), then nearest to 448
    assert [p.key for p in sel.pieces] == sorted(p.key for p in sel.pieces)  # text order is ascending key


def test_short_target_without_a_match_takes_the_nearest_story(si, settings):
    pool = pool_of(si, [(1, 250), (2, 380)])
    sel = si.bs.select_for(pool, 300, settings)
    assert sel.m == 1 and sel.pieces_in_tolerance == (False,) and sel.pieces[0].n == 250


def test_pool_exhaustion_is_reported(si, settings):
    with pytest.raises(si.bs.PoolExhausted):
        si.bs.select_for(pool_of(si, []), 300, settings)


# --- Paging --------------------------------------------------------------------------------


def test_sentence_final_skips_closers(si, settings):
    final = lambda t: si.bs.is_sentence_final(t, settings.terminal_marks, settings.closers)  # noqa: E731
    assert final("end.") and final('end."') and final("end!)") and final("wait…") and final("so.’")
    assert not final('end"') and not final('"') and not final("and,") and not final("---")


def test_cuts_snap_to_the_nearest_sentence_end_ties_earlier(si):
    flags = [False] * 20
    flags[7] = flags[11] = True  # tokens 8 and 12 end sentences, both 2 from the ideal cut at 10
    assert si.bs.page_cuts(20, (10, 10), flags, 6) == [8]
    assert si.bs.page_cuts(20, (10, 10), [False] * 20, 6) == [10]  # nothing to snap to
    flags[7] = False
    flags[2] = True  # token 3 lies 7 from the ideal, outside the window
    assert si.bs.page_cuts(20, (10, 10), flags, 6) == [12]


def test_cuts_keep_pages_non_empty_and_increasing(si):
    assert si.bs.page_cuts(3, (1, 1, 1), [True] * 3, 6) == [1, 2]
    cuts = si.bs.page_cuts(40, (1,) * 40, [True] * 40, 6)
    assert cuts == list(range(1, 40))
    with pytest.raises(ValueError):
        si.bs.page_cuts(2, (1, 1, 1), [True] * 2, 6)


def test_cut_rounding_switch(si):
    # N * S / T = 5 * 1 / 2 = 2.5 exactly.
    assert si.bs.page_cuts(5, (1, 1), [False] * 5, 0, "half_up") == [3]
    assert si.bs.page_cuts(5, (1, 1), [False] * 5, 0, "half_even") == [2]


def test_render_pages_space_and_escape(si):
    tokens, ends = ["a", "b.", "c", "d."], [False, True, False, True]
    assert si.bs.render_pages(tokens, ends, [3], "space") == ["a b. c", "d."]
    assert si.bs.render_pages(tokens, ends, [3], "escape") == ["a b.\\nc", "d."]


# --- Building ------------------------------------------------------------------------------


def build_in_memory(si, settings, out, limit=None, rows=None, targets=None):
    source = si.bs.InMemorySource(rows if rows is not None else candidate_rows())
    targets = targets if targets is not None else make_targets(si)
    return si.bs.build(targets, source, out, settings, limit=limit, log=quiet)


def test_build_writes_the_published_schema(si, settings, tmp_path):
    manifest = build_in_memory(si, settings, tmp_path)
    raw, rows = read_table(tmp_path / "en-us" / "stories.csv.xz")
    assert raw.splitlines()[0].split(",") == si.cs.STORY_COLS
    targets = {(t.story_id, t.level): t for t in make_targets(si)}
    ranked = si.bs.rank_targets(list(targets.values()), settings)
    assert [r["id"] for r in rows] == [f"SI{i}" for i in range(1, len(ranked) + 1)]
    for row, target in zip(rows, ranked, strict=True):
        title, pages = si.cs.split_lines(row["text"])
        assert title == row["title"] and len(pages) == target.pages == int(row["pages"])
        assert int(row["words"]) == len(" ".join(pages).split())
        assert row["age"] == target.level and row["lang"] == "en-us" and row["build_error"] == ""
        if target.kind == "classic":
            assert row["hero"] == "Public domain" and row["folder"].startswith("PD_SK")
        else:
            assert row["folder"] == f"{row['hero']}-{target.level}"
    heroes = {}
    for row, target in zip(rows, ranked, strict=True):
        if target.kind == "generated":
            heroes.setdefault(target.combination, set()).add(row["hero"])
    assert all(len(h) == 1 for h in heroes.values()) and len(heroes) == 12
    assert manifest["sizes"] == {"targets": 39, "built": 39, "limit": None, "smoke_size": 1, "smoke": False}
    assert manifest["acceptance"]["pages_per_text_identical"] is True
    assert manifest["outputs"]["table"]["rows"] == 39
    notice = (tmp_path / "NOTICE-SimpleStories.txt").read_text(encoding="utf-8")
    assert "MIT License" in notice and "Permission is hereby granted" in notice
    selection = (tmp_path / "selection.tsv").read_text(encoding="utf-8").splitlines()
    assert selection[0].split("\t") == si.bs.SELECTION_COLS and len(selection) == 40
    on_disk = json.loads((tmp_path / "standin_manifest.json").read_text(encoding="utf-8"))
    assert on_disk["outputs"]["table"]["rows_sha256"] == manifest["outputs"]["table"]["rows_sha256"]


def test_joins_and_tolerance_are_recorded(si, settings, tmp_path):
    manifest = build_in_memory(si, settings, tmp_path)
    classic = manifest["selection"]["classic"]
    assert classic["joins"] >= 2  # the two long classics cannot be matched by one story of at most 700 tokens
    assert manifest["acceptance"]["groups"]["all"]["tokens_per_text"]["passed"] is True
    assert manifest["selection"]["all"]["outside_tolerance"] == 0


def test_smoke_rows_are_the_first_rows_of_the_full_build(si, settings, tmp_path):
    targets = make_targets(si)
    local = dataclasses.replace(settings, smoke_fraction=Fraction(1, 4))  # 10 of 39 targets
    n_smoke = si.bs.smoke_size(len(targets), local.smoke_fraction)
    full = build_in_memory(si, local, tmp_path / "full", targets=targets)
    smoke = build_in_memory(si, local, tmp_path / "smoke", limit=n_smoke, targets=targets)
    full_raw, full_rows = read_table(tmp_path / "full" / "en-us" / "stories.csv.xz")
    smoke_raw, smoke_rows = read_table(tmp_path / "smoke" / "en-us" / "stories.csv.xz")
    assert len(smoke_rows) == n_smoke == 10
    assert full_raw.startswith(smoke_raw) and smoke_rows == full_rows[:n_smoke]
    assert smoke["sizes"]["smoke"] is True
    assert smoke["outputs"]["table"]["rows_sha256"] == full["outputs"]["table"]["rows_sha256_first"]["sha256"]


def test_rebuild_is_byte_identical(si, settings, tmp_path):
    build_in_memory(si, settings, tmp_path / "a")
    build_in_memory(si, settings, tmp_path / "b")
    a = (tmp_path / "a" / "en-us" / "stories.csv.xz").read_bytes()
    assert a == (tmp_path / "b" / "en-us" / "stories.csv.xz").read_bytes()
    assert (tmp_path / "a" / "selection.tsv").read_bytes() == (tmp_path / "b" / "selection.tsv").read_bytes()


def test_typography_switch_moves_no_page_break(si, settings, tmp_path):
    on = build_in_memory(si, settings, tmp_path / "on")
    off = build_in_memory(si, dataclasses.replace(settings, typography=False), tmp_path / "off")
    _, rows_on = read_table(tmp_path / "on" / "en-us" / "stories.csv.xz")
    raw_off, rows_off = read_table(tmp_path / "off" / "en-us" / "stories.csv.xz")
    for a, b in zip(rows_on, rows_off, strict=True):
        pa, pb = si.cs.split_lines(a["text"])[1], si.cs.split_lines(b["text"])[1]
        assert [len(p.split()) for p in pa] == [len(p.split()) for p in pb]
    assert all(ord(c) < 128 for c in raw_off)
    assert on["typography"]["replacements"]["double_open"] > 0 and off["typography"]["replacements"] == {}
    assert on["outputs"]["table"]["rows_sha256"] != off["outputs"]["table"]["rows_sha256"]


def test_escaped_line_breaks_read_back_as_the_same_tokens(si, settings, tmp_path):
    build_in_memory(si, dataclasses.replace(settings, line_breaks="escape"), tmp_path / "esc")
    build_in_memory(si, settings, tmp_path / "sp")
    raw, rows = read_table(tmp_path / "esc" / "en-us" / "stories.csv.xz")
    _, rows_sp = read_table(tmp_path / "sp" / "en-us" / "stories.csv.xz")
    assert "\\n" in raw
    for a, b in zip(rows, rows_sp, strict=True):
        pa, pb = si.cs.split_lines(a["text"])[1], si.cs.split_lines(b["text"])[1]
        assert [p.split() for p in pa] == [p.split() for p in pb] and a["words"] == b["words"]


def test_build_refuses_a_limit_outside_the_targets(si, settings, tmp_path):
    with pytest.raises(si.bs.StandinError):
        build_in_memory(si, settings, tmp_path, limit=0)


def test_quantile_and_acceptance_checks(si, settings):
    assert si.bs.quantile([1, 2, 3, 4], 50) == 2.5
    assert si.bs.quantile([10], 99) == 10
    ok = si.bs._compare([100, 200, 300], [101, 199, 309], [50], Fraction(3, 100))
    assert ok["passed"] and ok["quantiles"][0]["standin"] == 199
    bad = si.bs._compare([100, 200, 300], [100, 190, 300], [50], Fraction(3, 100))
    assert not bad["passed"]


# --- Typography ----------------------------------------------------------------------------

CASES = [
    ('"Hello," she said.', "“Hello,” she said."),
    ("Kim's friends' toys", "Kim’s friends’ toys"),
    ("'Trust yourself,' they sang.", "‘Trust yourself,’ they sang."),
    ('"I think the answer is \'holiday\'!" she said', "“I think the answer is ‘holiday’!” she said"),
    ("I... I sold it", "I… I sold it"),
    ("precious - the gift", "precious — the gift"),
    ("end.\n\n---\n\nStart", "end.\n\n—\n\nStart"),
    ('him-"teapot."', "him—“teapot.”"),
    ('gadget"-a', "gadget”—a"),
    ("word--word", "word—word"),
    ("rock 'n' roll 'em 'tis '90s", "rock ’n’ roll ’em ’tis ’90s"),
    ('" Hello "', "“ Hello ”"),
    ("well-known (\"aside\")", "well-known (“aside”)"),
    ("a big 'X' marked", "a big ‘X’ marked"),
]


@pytest.mark.parametrize(("ascii_text", "typeset"), CASES)
def test_typography_rules(si, ascii_text, typeset):
    out, _ = si.ty.transform_text(ascii_text)
    assert out == typeset
    assert si.ty.transform_text(out)[0] == out  # idempotent


def test_typography_counts_and_switches(si):
    out, counts = si.ty.transform_text('"Wait..." - he said, "it\'s here."')
    assert out == "“Wait…” — he said, “it’s here.”"
    assert counts == {"ellipsis": 1, "em_dash": 1, "double_open": 2, "double_close": 2,
                      "single_close_or_apostrophe": 1}
    plain, none = si.ty.transform_text('"Wait..." - it\'s', quotes=False, apostrophes=False, ellipsis=False,
                                       dashes=False)
    assert plain == '"Wait..." - it\'s' and not none


def test_typography_never_changes_whitespace_or_token_count(si):
    rng = random.Random(3)
    alphabet = "ab'\".-!?,()  \n\t"
    for _ in range(2000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        out, _ = si.ty.transform_text(s)
        assert re.findall(r"\s+", out) == re.findall(r"\s+", s)
        assert len(out.split()) == len(s.split())
        assert si.ty.transform_text(out)[0] == out


# --- The structure table -------------------------------------------------------------------


def write_story_table(si, path: Path, rows: list[dict]) -> Path:
    """A synthetic table in the published schema, compressed as the extraction compresses it."""
    with lzma.open(path, "wt", encoding="utf-8", newline="", preset=6) as fh:
        w = csv.writer(fh)
        w.writerow(si.cs.STORY_COLS)
        for r in rows:
            w.writerow([r.get(c, "") for c in si.cs.STORY_COLS])
    return path


def synthetic_story_rows():
    return [
        {"id": "1", "folder": "Ana-Moon Base-Hope-Quest-Owl-young", "hero": "Ana", "world": "Moon Base",
         "theme": "Hope", "prompt": "Quest", "sidekick": "Owl", "age": "young", "lang": "en-us",
         "title": "A Title", "pages": "3", "words": "6", "text": "A Title\nOne two.\nThree\\nfour five.\nSix\n"},
        {"id": "2", "folder": "Ana-Moon Base-Hope-Quest-Owl-mid", "hero": "Ana", "world": "Moon Base",
         "theme": "Hope", "prompt": "Quest", "sidekick": "Owl", "age": "mid", "lang": "en-us",
         "title": "B", "pages": "2", "words": "9", "text": "B\nSeven eight nine.\nTen."},
        {"id": "3", "folder": "PD_The Fox young", "hero": "Public domain", "age": "young", "lang": "en-us",
         "title": "Fox", "pages": "2", "words": "4", "text": "Fox\r\nA b.\r\nC d.\r\n"},
        {"id": "4", "folder": "PD_The Fox_old current", "hero": "Public domain", "age": "old", "lang": "en-us",
         "title": "Fox", "pages": "1", "words": "1", "text": "Fox\nE."},
        {"id": "5", "folder": "PD_Odd", "hero": "Public domain", "age": "", "lang": "en-us",
         "title": "Odd", "pages": "1", "words": "2", "text": "Odd\nG h."},
    ]


def test_structure_table_matches_the_scout_format(si, tmp_path):
    stories = write_story_table(si, tmp_path / "stories.csv.xz", synthetic_story_rows())
    checks = si.cs.write_structure(stories, tmp_path / "s.tsv")
    expected = (
        "id\tkind\tlevel\tpages\ttokens\tchars_joined\ttokens_per_page\tchars_per_page\n"
        "1\tgenerated\tyoung\t3\t6\t29\t2 3 1\t8 16 3\n"
        "2\tgenerated\tmid\t2\t4\t22\t3 1\t17 4\n"
        "3\tclassic\tyoung\t2\t4\t9\t2 2\t4 4\n"
        "4\tclassic\told\t1\t1\t2\t1\t2\n"
        "5\tclassic\t(blank)\t1\t2\t4\t2\t4\n"
    )
    assert (tmp_path / "s.tsv").read_bytes() == expected.encode("utf-8")
    assert checks["texts"] == 5 and checks["words_column_mismatches"] == 1  # row 2 claims 9 words
    assert checks["pages_column_mismatches"] == 0 and checks["max_tokens_per_page"] == 3
    assert checks["max_chars_per_page"] == 17 and checks["empty_pages"] == 0


def test_structure_combination_groups_the_versions_of_a_story(si, tmp_path):
    stories = write_story_table(si, tmp_path / "stories.csv.xz", synthetic_story_rows())
    si.cs.write_structure(stories, tmp_path / "s.tsv", with_combination=True)
    lines = (tmp_path / "s.tsv").read_text(encoding="utf-8").splitlines()
    assert lines[0].endswith("\tcombination")
    assert [line.split("\t")[-1] for line in lines[1:]] == ["1", "1", "3", "3", "5"]
    targets = si.cs.read_structure(tmp_path / "s.tsv")
    assert [(t.story_id, t.level, t.combination) for t in targets] == [
        ("1", "young", "1"), ("2", "mid", "1"), ("3", "young", "3"), ("4", "old", "3"), ("5", "", "5")]
    assert targets[0].tokens_per_page == (2, 3, 1) and targets[0].chars_joined == 29


def test_structure_command_requires_an_authorisation(si, tmp_path, capsys):
    stories = write_story_table(si, tmp_path / "stories.csv.xz", synthetic_story_rows())
    out = tmp_path / "s.tsv"
    with pytest.raises(SystemExit) as stopped:  # argparse refuses a missing required flag
        si.cs.main([str(stories), str(out)])
    assert stopped.value.code != 0 and not out.exists()
    assert si.cs.main([str(stories), str(out), "--authorisation", "two\nlines"]) == 1
    assert si.cs.main([str(stories), str(out), "--authorisation", "   "]) == 1
    assert not out.exists()
    assert si.cs.main([str(stories), str(out), "--authorisation", "lab log 2026-11-03, entry 1"]) == 0
    assert "Authorised: lab log 2026-11-03, entry 1" in capsys.readouterr().out
    record = json.loads((tmp_path / "s.tsv.authorisation.json").read_text(encoding="utf-8"))
    assert record["authorisation"] == "lab log 2026-11-03, entry 1"
    assert record["checks"]["texts"] == 5 and len(record["source_sha256"]) == 64
    assert record["table_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()


def test_read_structure_refuses_story_tables_and_bad_rows(si, tmp_path):
    with pytest.raises(si.cs.StructureError, match="tsv"):
        si.cs.read_structure(tmp_path / "stories.csv.xz")  # refused by name, before it is opened
    with_text = tmp_path / "t.tsv"
    with_text.write_text("id\ttext\n1\tOnce upon a time\n", encoding="utf-8")
    with pytest.raises(si.cs.StructureError, match="text column"):
        si.cs.read_structure(with_text)
    head = "\t".join(si.cs.STRUCTURE_COLS) + "\n"
    bad = tmp_path / "bad.tsv"
    bad.write_text(head + "1\tgenerated\tyoung\t2\t5\t20\t2 2\t9 9\n", encoding="utf-8")
    with pytest.raises(si.cs.StructureError, match="disagree"):
        si.cs.read_structure(bad)
    dup = tmp_path / "dup.tsv"
    dup.write_text(head + "1\tgenerated\tyoung\t1\t2\t5\t2\t5\n" * 2, encoding="utf-8")
    with pytest.raises(si.cs.StructureError, match="twice"):
        si.cs.read_structure(dup)


def test_read_structure_reads_xz_and_the_scout_columns(si, tmp_path):
    path = tmp_path / "s.tsv.xz"
    body = "\t".join(si.cs.STRUCTURE_COLS) + "\n" + "9\tclassic\t(blank)\t2\t3\t12\t1 2\t4 7\n"
    with lzma.open(path, "wt", encoding="utf-8", newline="") as fh:
        fh.write(body)
    (t,) = si.cs.read_structure(path)
    assert (t.story_id, t.kind, t.level, t.pages, t.tokens, t.combination) == ("9", "classic", "", 2, 3, "9")


def test_split_lines_matches_the_extraction(si):
    assert si.cs.split_lines("T\nOne\\ntwo\nThree\n") == ("T", ["One\ntwo", "Three"])
    assert si.cs.split_lines("T\r\nA\r\n") == ("T", ["A"])


# --- The public SimpleStories test split ---------------------------------------------------


def local_split_dir() -> Path | None:
    """The folder holding the pinned test split, as INTRACT_SIMPLESTORIES_DIR names it (None when unset)."""
    env = os.environ.get("INTRACT_SIMPLESTORIES_DIR")
    return Path(env) if env else None


@pytest.fixture(scope="module")
def test_split(si, settings):
    pytest.importorskip("pyarrow")
    folder = local_split_dir()
    pin = settings.splits["test"][0]
    if folder is None or not (folder / pin.name).is_file():
        pytest.skip("the pinned SimpleStories test split is not present locally")
    return si.bs.verify_shards(folder, settings.splits["test"], log=quiet)  # a wrong file fails here


def split_targets(si):
    """140 synthetic targets with catalogue-like page structures, classics long enough to need joins."""
    rng = random.Random(11)
    targets, sid = [], 0
    for _ in range(45):
        first = sid + 1
        for level, pages, mean in (("young", 17, 21), ("mid", 17, 24), ("old", 20, 26)):
            sid += 1
            tpp = tuple(max(1, round(rng.gauss(mean, 6))) for _ in range(pages))
            targets.append(si.cs.Target(str(sid), "generated", level, tpp, sum(tpp) * 6, str(first)))
    for level, pages in (("young", 25), ("old", 40), ("old", 30), ("young", 20), ("", 12)):
        sid += 1
        tpp = tuple(max(1, round(rng.gauss(48, 15))) for _ in range(pages))
        targets.append(si.cs.Target(str(sid), "classic", level, tpp, sum(tpp) * 6, str(sid)))
    return targets


def test_smoke_identity_on_the_public_test_split(si, settings, test_split, tmp_path):
    targets = split_targets(si)
    local = dataclasses.replace(settings, smoke_fraction=Fraction(1, 10))
    n_smoke = si.bs.smoke_size(len(targets), local.smoke_fraction)

    def run(out, limit):
        source = si.bs.ParquetSource(test_split, local.batch_size, {"split": "test"}, local.expected_rows["test"])
        return si.bs.build(targets, source, out, local, limit=limit, log=quiet)

    full = run(tmp_path / "full", None)
    smoke = run(tmp_path / "smoke", n_smoke)
    full_raw, full_rows = read_table(tmp_path / "full" / "en-us" / "stories.csv.xz")
    smoke_raw, smoke_rows = read_table(tmp_path / "smoke" / "en-us" / "stories.csv.xz")
    assert n_smoke == 14 and smoke_rows == full_rows[:n_smoke] and full_raw.startswith(smoke_raw)
    assert smoke["outputs"]["table"]["rows_sha256"] == full["outputs"]["table"]["rows_sha256_first"]["sha256"]
    assert full["source"]["rows_read"] == 21371 and full["source"]["dropped_duplicate_id"] == 0
    assert full["selection"]["classic"]["joins"] >= 1
    assert full["acceptance"]["pages_per_text_identical"] is True
    assert full["acceptance"]["groups"]["all"]["tokens_per_text"]["passed"] is True
    assert full["typography"]["replacements"]["double_open"] > 0


def test_command_line_build_on_the_public_test_split(si, test_split, tmp_path):
    structure = write_structure_tsv(si, split_targets(si), tmp_path / "structure.tsv")
    folder = test_split[0].parent
    assert si.bs.main(["verify", "--shards", str(folder), "--split", "test"]) == 0
    code = si.bs.main(["build", "--structure", str(structure), "--shards", str(folder), "--split", "test",
                       "--out", str(tmp_path / "out"), "--limit", "20", "--typography", "off"])
    manifest = json.loads((tmp_path / "out" / "standin_manifest.json").read_text(encoding="utf-8"))
    # [acceptance] enforce = false (the committed default): a failed check is recorded, never an exit status.
    assert code == 0 and manifest["acceptance"]["enforced"] is False
    assert manifest["sizes"]["built"] == 20 and manifest["typography"]["enabled"] is False
    assert manifest["source"]["files"][0]["verified"] is True and manifest["source"]["revision"] == REVISION
    assert manifest["structure"]["combination_column"] is True and manifest["structure"]["rows"] == 140
    notice = (tmp_path / "out" / "NOTICE-SimpleStories.txt").read_text(encoding="utf-8")
    assert "typographic" not in notice and "MIT License" in notice


def test_acceptance_enforcement_sets_the_exit_status(si, settings, tmp_path, monkeypatch):
    # A build whose check fails exits 3 only when [acceptance] enforce is true; outputs are written either way.
    failing = {"acceptance": {"passed": False, "enforced": None, "groups": {
        "young": {"tokens_per_text": {"passed": True}, "tokens_per_page": {"passed": False}}}}}
    monkeypatch.setattr(si.bs, "read_structure", lambda path: [])
    monkeypatch.setattr(si.bs, "verify_shards", lambda folder, pins, **kw: [])
    monkeypatch.setattr(si.bs, "ParquetSource", lambda *a, **kw: None)
    monkeypatch.setattr(si.bs, "_structure_record", lambda path, targets: {})
    monkeypatch.setattr(si.bs, "build", lambda *a, **kw: failing)
    args = ["build", "--structure", str(tmp_path / "s.tsv"), "--shards", str(tmp_path), "--out", str(tmp_path / "o")]
    for enforce, expected in ((False, 0), (True, 3)):
        loaded = dataclasses.replace(settings, enforce_acceptance=enforce)
        monkeypatch.setattr(si.bs.Settings, "load", classmethod(lambda cls, config_dir, s=loaded: s))
        assert si.bs.main(args) == expected


def test_the_notice_follows_the_typography_switch(si, settings):
    assert si.bs.TYPOGRAPHY_CLAUSE in settings.notice  # else the replacement below would silently do nothing
    off = si.bs.notice_text(dataclasses.replace(settings, typography=False))
    assert si.bs.TYPOGRAPHY_CLAUSE not in off and "and divided into pages by the InTRACt" in off
    assert si.bs.notice_text(settings) == settings.notice


@pytest.mark.parametrize("change", [{"acceptance_quantiles": ()}, {"acceptance_quantiles": (1, 101)},
                                    {"page_tolerance": Fraction(0)}, {"terminal_marks": ()}])
def test_settings_refuse_unusable_acceptance_and_paging_values(si, settings, change):
    with pytest.raises(si.bs.StandinError):
        dataclasses.replace(settings, **change).check()
