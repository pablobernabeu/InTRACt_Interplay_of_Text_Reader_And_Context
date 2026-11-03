"""Tests of the documents stage on synthetic tables in the catalogue's published schema.

Every lock in these tests reads synthetic manifests in a temporary config folder, except the command-line
test at the end, which runs the stage under the repository's real lock configuration on a synthetic input.
"""

import copy
import csv
import gzip
import json
import lzma
import pkgutil
import shutil
from pathlib import Path

import pytest

from intract_features import cli, config, lock, lock_build, records, stages
from intract_features.io import catalogue
from intract_features.stages import documents
from intract_features.text import keyed
from intract_features.text.words import count_words

FEATURES = Path(__file__).resolve().parents[2]


def zip_text(title, pages):
    return "\n".join([title] + [p.replace("\n", "\\n") for p in pages]) + "\n"


def story(story_id, pages, *, title="A Title", age="young", lang="en-us", classic=False, text=None):
    folder = f"PD_Tale {age}" if classic else f"Hero-World-Theme-Prompt-Sidekick-{age}"
    return {"id": story_id, "folder": folder, "hero": "Public domain" if classic else "Hero", "world": "World",
            "theme": "Theme", "prompt": "Prompt", "sidekick": "Sidekick", "age": age, "lang": lang, "title": title,
            "pages": str(len(pages)), "words": str(len(" ".join(pages).split())), "build_error": "",
            "text": zip_text(title, pages) if text is None else text}


def write_table(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = lzma.open if path.name.endswith(".xz") else open
    with opener(path, "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(catalogue.STORY_COLS)
        for row in rows:
            w.writerow([row[c] for c in catalogue.STORY_COLS])
    return path


ROWS = [
    story("1", ["Once upon a time, a fox lived in a wood.", "Chapter Two\nThe fox ran\N{ZERO WIDTH SPACE} home.",
                "The End"], title="The Fox"),
    story("2", ["Long ago, a cafe\N{COMBINING ACUTE ACCENT} stood by the sea.", "It was quiet."], age="old",
          classic=True),
    story("3", ["Mia had a red kite.", "It flew high!"], age="mid"),
    story("4", ["A short tale.", "Done."], age=""),
] + [story(str(i), [f"Story {i} begins.", f"Story {i} ends."], age=("young", "mid", "old")[i % 3])
     for i in range(5, 31)]

CATALOGUE_PAGES = ["Once upon a time a small red fox lived at the edge of a very old wood.",
                   "Every morning the fox ran down to the river to drink and to watch the fish.",
                   "One day the river was gone, and the fox set out to find where it had gone."]
AUTH = ["--authorisation", "synthetic tables only"]


def make_config(tmp_path, *, protected_checksums=(), keyed_sample=None, **titles):
    """The repository's configuration, with the lock pointed at synthetic manifests in tmp_path/config."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "manifest.json").write_text(json.dumps(
        {"languages": {"en-us": {"sha256": "0" * 64, "uncompressed_sha256": "1" * 64}},
         "files": {f"f{i}": {"sha256": h} for i, h in enumerate(protected_checksums)}}), encoding="utf-8")
    (config_dir / "extraction_record.json").write_text(json.dumps({"files": [{"sha256": "2" * 64}]}),
                                                       encoding="utf-8")
    base = {"pipeline.toml", "languages.toml"}
    cfg_src = tmp_path / "cfg_src"
    if not cfg_src.exists():
        (cfg_src / "stages").mkdir(parents=True)
        for name in base:
            shutil.copy(FEATURES / "config" / name, cfg_src / name)
        shutil.copy(FEATURES / "config" / "stages" / "documents.toml", cfg_src / "stages" / "documents.toml")
    cfg = copy.deepcopy(config.load(cfg_src))
    d = cfg["stages"]["documents"]
    d["lock"] = {"manifests": ["manifest.json", "extraction_record.json"], "protected_dirs": ["../protected"],
                 "fingerprints": "catalogue_fingerprints_*.txt", "required_fingerprints": [],
                 "min_variant_tokens": 20, "ipa_checksum": "ipa_record.sha256", "ipa_record": "",
                 "ipa_commit_check": "git", "on_missing_manifest": "refuse"}
    d["titles"].update(titles)
    d["keyed_sample"].update(keyed_sample or {})
    return cfg, config_dir


def context(tmp_path, cfg, config_dir, input_path, *, lang="en-us", shard=0, nshards=1, limit=None, work="work"):
    return cli.StageContext(stage=documents.STAGE, config=cfg, lang=lang, work=tmp_path / work, shard=shard,
                            nshards=nshards, input=input_path, limit=limit, extra={"config_dir": config_dir})


def output(tmp_path, lang="en-us", shard=0, nshards=1, work="work"):
    return records.artefact_path(tmp_path / work, lang, "documents", shard, nshards)


def manifest_of(path):
    return json.loads(path.with_name(path.name.replace(".jsonl.gz", ".manifest.json")).read_text(encoding="utf-8"))


def read_docs(path):
    return [records.Document.from_json(o) for o in records.read_jsonl(path)]


def build_fingerprints(tmp_path, config_dir, rows):
    write_table(tmp_path / "tables" / "en-us" / "stories.csv.xz", rows)
    lock_build.main(["fingerprints", "--tables", str(tmp_path / "tables"), "--out", str(config_dir), *AUTH])


@pytest.fixture
def table(tmp_path):
    return write_table(tmp_path / "input" / "standin.csv.xz", ROWS)


def test_stage_module_is_discoverable():
    assert "documents" in {m.name for m in pkgutil.iter_modules(stages.__path__)}
    assert documents.STAGE.name == "documents" and documents.STAGE.outputs == ("documents",)
    assert documents.STAGE.inputs == () and documents.STAGE.env == "core"


def test_documents_are_normalised_titled_and_keyed(tmp_path, table):
    cfg, config_dir = make_config(tmp_path)
    counts = documents.run(context(tmp_path, cfg, config_dir, table))
    docs = {d.story_id: d for d in read_docs(output(tmp_path))}
    assert list(docs) == [r["id"] for r in ROWS]
    fox = docs["1"]
    assert fox.title == "The Fox"
    assert fox.pages == ("Once upon a time, a fox lived in a wood.", "The fox ran home.", "The End")
    assert fox.meta["page_titles"] == [{"page": 1, "text": "Chapter Two", "lines": 2}]
    assert fox.meta["page_titles_excluded"] is True
    assert (fox.level, fox.kind) == ("young", "generated")
    assert fox.meta["fingerprint"] == lock.fingerprint(catalogue.split_lines(ROWS[0]["text"])[1])
    assert docs["2"].pages[0] == "Long ago, a caf\xe9 stood by the sea."
    assert (docs["2"].kind, docs["2"].level, docs["4"].level) == ("classic", "old", "")
    # The keyed hash reads the story identifier alone; no rank, which would depend on the other rows.
    assert all(d.meta["keyed_hash"] == records.keyed_hash("keyed_sample", s) for s, d in docs.items())
    assert not any("keyed_rank" in d.meta for d in docs.values())
    assert counts["documents"] == len(ROWS) == counts["rows_read"]
    assert counts["pages"] == sum(len(d.pages) for d in docs.values())
    assert counts["words"] == sum(count_words(d.text) for d in docs.values())
    assert counts["characters"] == sum(len(d.text) for d in docs.values())
    assert counts["format_characters_deleted"] == 1 and counts["pages_changed_by_nfc"] == 1
    assert counts["page_titles"] == 1 and counts["page_title_words"] == 2 and counts["pages_with_line_breaks"] == 1
    assert counts["documents_without_level"] == 1
    assert counts["max_page_characters"] == max(len(p) for d in docs.values() for p in d.pages)
    assert counts["max_page_words"] == max(count_words(p) for d in docs.values() for p in d.pages)
    assert counts["keyed_sample_documents"] == len(ROWS)  # fewer stories than the sample of 2,000
    assert set(counts) == set(documents.COUNT_KEYS)
    sample = manifest_of(output(tmp_path))["keyed_sample"]
    assert sample["key"] == "intract|keyed_sample|v1|<story id>" and sample["stories_in_input"] == len(ROWS)
    assert [(c["size"], c["keyed_hash"], c["documents_written"]) for c in sample["cutoffs"]] == [
        (2000, None, len(ROWS)), (10000, None, len(ROWS))]


def test_smoke_rows_equal_the_full_runs_rows(tmp_path):
    # DESIGN.md, Determinism: "The 1 per cent smoke run's rows must equal the same rows of the full run".
    # The smoke table holds the first rows of the full table, as standin.build_standin --smoke writes it.
    rows = [story(f"SI{i}", [f"Story {i} begins.", f"Story {i} ends."]) for i in range(60)]
    cfg, config_dir = make_config(tmp_path)
    full = write_table(tmp_path / "full" / "stories.csv.xz", rows)
    smoke = write_table(tmp_path / "smoke" / "stories.csv.xz", rows[:10])
    for nshards in (1, 3):
        compared = 0
        for shard in range(nshards):
            documents.run(context(tmp_path, cfg, config_dir, full, shard=shard, nshards=nshards, work="full"))
            documents.run(context(tmp_path, cfg, config_dir, smoke, shard=shard, nshards=nshards, work="smoke"))
            whole = {o["story_id"]: o for o in records.read_jsonl(output(tmp_path, shard=shard, nshards=nshards,
                                                                         work="full"))}
            part = list(records.read_jsonl(output(tmp_path, shard=shard, nshards=nshards, work="smoke")))
            assert all(o == whole[o["story_id"]] for o in part)
            compared += len(part)
            assert manifest_of(output(tmp_path, shard=shard, nshards=nshards, work="smoke"))[
                "keyed_sample"]["stories_in_input"] == 10
        assert compared == 10


def test_keyed_sample_cutoffs_give_the_sample_over_the_input(tmp_path, table):
    cfg, config_dir = make_config(tmp_path, keyed_sample={"size": 5, "max_size": 12})
    want_small = set(keyed.keyed_sample([r["id"] for r in ROWS], 5, "keyed_sample"))
    want_large = set(keyed.keyed_sample([r["id"] for r in ROWS], 12, "keyed_sample"))
    in_small, in_large, counted = set(), set(), 0
    for shard in range(3):
        counts = documents.run(context(tmp_path, cfg, config_dir, table, shard=shard, nshards=3))
        path = output(tmp_path, shard=shard, nshards=3)
        small, large = manifest_of(path)["keyed_sample"]["cutoffs"]
        assert (small["size"], large["size"]) == (5, 12)
        for d in read_docs(path):
            h = d.meta["keyed_hash"]
            if keyed.in_keyed_sample(h, d.story_id, (small["keyed_hash"], small["story_id"])):
                in_small.add(d.story_id)
            if keyed.in_keyed_sample(h, d.story_id, (large["keyed_hash"], large["story_id"])):
                in_large.add(d.story_id)
        counted += counts["keyed_sample_documents"]
    assert in_small == want_small and in_large == want_large and counted == 5
    bad, _ = make_config(tmp_path, keyed_sample={"size": 20, "max_size": 10})
    with pytest.raises(ValueError, match="size"):
        documents.run(context(tmp_path, bad, config_dir, table))


def test_title_lines_and_page_shapes_are_counted(tmp_path):
    rows = [story("p", ["Once upon a time.", "The end."], text="Page 1: Once upon a time.\nPage 2: The end.\n"),
            story("e", ["Only a page."], title=""),
            story("v", ["“Wait,”\nsaid Tom.", "Twinkle, twinkle, little star,\nHow I wonder."])]
    rows[0]["pages"] = "1"  # the extraction's count for a text whose first page was read as the title
    rows[0]["words"] = "4"
    cfg, config_dir = make_config(tmp_path)
    counts = documents.run(context(tmp_path, cfg, config_dir, write_table(tmp_path / "t.csv", rows)))
    docs = {d.story_id: d for d in read_docs(output(tmp_path))}
    assert docs["p"].meta["title_line_issue"] == catalogue.PAGE_MARKER_TITLE
    assert docs["e"].meta["title_line_issue"] == catalogue.EMPTY_TITLE and "title_line_issue" not in docs["v"].meta
    assert (counts["title_lines_page_marker"], counts["title_lines_empty"]) == (1, 1)
    # S3's rule under the defaults takes short dialogue and verse lines for titles; their words are counted.
    assert docs["v"].pages == ("said Tom.", "How I wonder.")
    assert counts["page_titles"] == 2 and counts["page_title_words"] == 1 + 4 and counts["pages_with_line_breaks"] == 2


def test_title_action_mark_keeps_the_page(tmp_path, table):
    cfg, config_dir = make_config(tmp_path, action="mark")
    documents.run(context(tmp_path, cfg, config_dir, table))
    fox = read_docs(output(tmp_path))[0]
    assert fox.pages[1] == "Chapter Two\nThe fox ran home."
    assert fox.meta["page_titles_excluded"] is False
    cfg, config_dir = make_config(tmp_path, page_rule="every_page", action="exclude")
    documents.run(context(tmp_path, cfg, config_dir, table))
    fox = read_docs(output(tmp_path))[0]
    assert fox.pages == ("Once upon a time, a fox lived in a wood.", "The fox ran home.", "")


def test_shards_partition_the_input_and_keep_every_record(tmp_path, table):
    cfg, config_dir = make_config(tmp_path)
    documents.run(context(tmp_path, cfg, config_dir, table))
    full = {o["story_id"]: o for o in records.read_jsonl(output(tmp_path))}
    seen = []
    for shard in range(3):
        counts = documents.run(context(tmp_path, cfg, config_dir, table, shard=shard, nshards=3))
        objs = list(records.read_jsonl(output(tmp_path, shard=shard, nshards=3)))
        assert counts["documents"] == len(objs) and counts["rows_read"] == len(ROWS)
        for o in objs:
            assert records.shard_of(o["story_id"], 3) == shard
            assert o == full[o["story_id"]]
        seen += [o["story_id"] for o in objs]
    assert sorted(seen) == sorted(full) and len(seen) == len(set(seen))


def test_limit_keeps_the_first_documents_unchanged(tmp_path, table):
    cfg, config_dir = make_config(tmp_path)
    documents.run(context(tmp_path, cfg, config_dir, table))
    full = list(records.read_jsonl(output(tmp_path)))
    counts = documents.run(context(tmp_path, cfg, config_dir, table, limit=2))
    assert list(records.read_jsonl(output(tmp_path))) == full[:2]
    assert counts["rows_beyond_limit"] == len(ROWS) - 2 and counts["documents"] == 2


def test_rerun_is_byte_identical_and_records_its_run(tmp_path, table):
    cfg, config_dir = make_config(tmp_path)
    ctx = context(tmp_path, cfg, config_dir, table)
    rec = cli.run_stage(documents, ctx)
    first = output(tmp_path).read_bytes()
    cli.run_stage(documents, ctx)
    assert output(tmp_path).read_bytes() == first
    assert rec["counts"]["documents"] == len(ROWS)
    timing = tmp_path / "work" / "en-us" / "_timing" / "documents-shard-0-of-1.json"
    assert json.loads(timing.read_text(encoding="utf-8"))["counts"] == rec["counts"]
    manifest = manifest_of(output(tmp_path))
    assert manifest["input"]["name"] == "standin.csv.xz"
    assert manifest["input"]["sha256"] == records.sha256_file(table)
    assert manifest["lock"]["state"] == "locked" and manifest["counts"] == rec["counts"]
    assert manifest["config"]["titles"]["page_rule"] == "multiline"
    assert tmp_path.name not in json.dumps(manifest)  # no local path in a run record


def test_fingerprinted_rows_are_refused_and_nothing_is_written(tmp_path):
    cfg, config_dir = make_config(tmp_path)
    build_fingerprints(tmp_path, config_dir, [story("9001", ["A catalogue page.", "Another catalogue page."])])
    copied = story("77", ["A catalogue  page. Another", "catalogue page."])  # re-paged, re-spaced, renamed
    path = write_table(tmp_path / "input" / "mixed.csv", ROWS[:3] + [copied])
    with pytest.raises(lock.CatalogueLocked):
        documents.run(context(tmp_path, cfg, config_dir, path))
    assert not output(tmp_path).exists()
    assert not output(tmp_path).with_name("shard-0-of-1.manifest.json").exists()
    # Rows of other shards are checked too.
    with pytest.raises(lock.CatalogueLocked):
        for shard in range(4):
            documents.run(context(tmp_path, cfg, config_dir, path, shard=shard, nshards=4))


@pytest.mark.parametrize("text", [
    "\n".join(CATALOGUE_PAGES) + "\n",  # the title line dropped: the first page is read as the title
    "Copied from the catalogue\nThe Fox\n" + "\n".join(CATALOGUE_PAGES) + "\n",  # a header line added
    "Page 1: " + CATALOGUE_PAGES[0] + "\nPage 2: " + CATALOGUE_PAGES[1] + "\nPage 3: " + CATALOGUE_PAGES[2] + "\n",
])
def test_copies_whose_lines_moved_are_refused(tmp_path, text):
    cfg, config_dir = make_config(tmp_path)
    build_fingerprints(tmp_path, config_dir, [story("9001", CATALOGUE_PAGES, title="The Fox")])
    title_line, pages = catalogue.split_lines(text)
    copied = story("77", pages, title=title_line, text=text)
    with pytest.raises(lock.CatalogueLocked, match="reading"):
        documents.run(context(tmp_path, cfg, config_dir, write_table(tmp_path / "copy.csv", ROWS[:2] + [copied])))


def test_the_lock_sees_a_row_before_it_is_validated(tmp_path):
    cfg, config_dir = make_config(tmp_path)
    build_fingerprints(tmp_path, config_dir, [story("9001", ["A catalogue page."])])
    malformed = dict(story("9001", ["A catalogue page."]), age="teen", pages="7")
    path = write_table(tmp_path / "input" / "malformed.csv", [malformed])
    with pytest.raises(lock.CatalogueLocked):
        documents.run(context(tmp_path, cfg, config_dir, path))


def test_protected_checksum_is_refused_before_any_row_is_read(tmp_path):
    path = tmp_path / "input" / "broken.csv"
    path.parent.mkdir()
    path.write_text("not,the,schema\n", encoding="utf-8")
    cfg, config_dir = make_config(tmp_path, protected_checksums=[records.sha256_file(path)])
    with pytest.raises(lock.CatalogueLocked):
        documents.run(context(tmp_path, cfg, config_dir, path))


def test_protected_directory_missing_manifest_and_required_fingerprints(tmp_path):
    cfg, config_dir = make_config(tmp_path)
    inside = write_table(tmp_path / "protected" / "copy.csv", ROWS[:1])
    with pytest.raises(lock.CatalogueLocked):
        documents.run(context(tmp_path, cfg, config_dir, inside))
    ok = write_table(tmp_path / "ok.csv", ROWS[:1])
    cfg["stages"]["documents"]["lock"]["required_fingerprints"] = ["en-us"]
    with pytest.raises(lock.LockError, match="required"):
        documents.run(context(tmp_path, cfg, config_dir, ok))
    (config_dir / "manifest.json").unlink()
    with pytest.raises(lock.LockError, match="cannot read"):
        documents.run(context(tmp_path, cfg, config_dir, ok))


def test_the_ipa_record_unlocks(tmp_path):
    catalogue_rows = [story("9001", ["A catalogue page."])]
    cfg, config_dir = make_config(tmp_path)
    build_fingerprints(tmp_path, config_dir, catalogue_rows)
    letter = config_dir / "ipa_letter.txt"
    letter.write_text("Stage 1 in-principle acceptance", encoding="utf-8")
    (config_dir / "ipa_record.sha256").write_text(records.sha256_file(letter) + "\n", encoding="utf-8")
    cfg["stages"]["documents"]["lock"]["ipa_record"] = "ipa_letter.txt"
    path = write_table(tmp_path / "input" / "catalogue.csv", catalogue_rows)
    # Under ipa_commit_check = "git" an uncommitted checksum does not unlock (test_lock.py covers a commit).
    with pytest.raises(lock.CatalogueLocked):
        documents.run(context(tmp_path, cfg, config_dir, path))
    cfg["stages"]["documents"]["lock"]["ipa_commit_check"] = "none"
    counts = documents.run(context(tmp_path, cfg, config_dir, path))
    assert counts["documents"] == 1
    assert manifest_of(output(tmp_path))["lock"]["state"] == "unlocked"


def test_translations_carry_english_page_titles(tmp_path):
    english = [story("1", ["Intro.", "Chapter Two\nThe fox ran."]), story("2", ["Song\nLa la\nLa.", "End."]),
               story("4", ["Part One\nA.", "Bee sang.\nCee."])]
    german = [story("1", ["Einleitung.", "Kapitel Zwei\nDer Fuchs lief."], lang="de-de"),
              story("2", ["Lied\nLa la la.", "Ende."], lang="de-de"),  # one line fewer: not carried
              story("3", ["Neu.", "Mehr."], lang="de-de"),  # no English source
              story("4", ["Teil Eins\nA.", "Bie sang. Zeh."], lang="de-de")]  # the other page lost a line
    cfg, config_dir = make_config(tmp_path)
    de_table = write_table(tmp_path / "input" / "de.csv", german)
    with pytest.raises(FileNotFoundError, match="run the documents stage for en-us first"):
        documents.run(context(tmp_path, cfg, config_dir, de_table, lang="de-de"))
    documents.run(context(tmp_path, cfg, config_dir, write_table(tmp_path / "input" / "en.csv", english)))
    counts = documents.run(context(tmp_path, cfg, config_dir, de_table, lang="de-de"))
    docs = {d.story_id: d for d in read_docs(output(tmp_path, "de-de"))}
    assert docs["1"].pages[1] == "Der Fuchs lief."
    assert docs["1"].meta["page_titles"] == [{"page": 1, "text": "Kapitel Zwei", "lines": 2}]
    assert docs["2"].pages[0] == "Lied\nLa la la."
    assert docs["4"].pages[0] == "A."  # page_lines: the title's own page kept its two lines
    assert counts["page_titles"] == 2 and counts["page_titles_not_carried"] == 1
    assert counts["documents_without_english_source"] == 1
    strict, _ = make_config(tmp_path, carry_rule="text_lines")
    counts = documents.run(context(tmp_path, strict, config_dir, de_table, lang="de-de"))
    docs = {d.story_id: d for d in read_docs(output(tmp_path, "de-de"))}
    assert docs["4"].pages[0] == "Teil Eins\nA." and counts["page_titles_not_carried"] == 2
    cfg_off, _ = make_config(tmp_path, page_rule="off")
    shutil.rmtree(tmp_path / "work" / "en-us")
    assert documents.run(context(tmp_path, cfg_off, config_dir, de_table, lang="de-de"))["page_titles"] == 0


def test_input_and_configuration_errors(tmp_path, table):
    cfg, config_dir = make_config(tmp_path)
    with pytest.raises(ValueError, match="--input"):
        documents.run(context(tmp_path, cfg, config_dir, None))
    with pytest.raises(ValueError, match="negative"):
        documents.run(context(tmp_path, cfg, config_dir, table, limit=-1))
    wrong_lang = write_table(tmp_path / "w.csv", [story("1", ["x."], lang="fr-fr")])
    with pytest.raises(catalogue.CatalogueFormatError, match="the run is"):
        documents.run(context(tmp_path, cfg, config_dir, wrong_lang))
    duplicated = write_table(tmp_path / "d.csv", [story("1", ["x."]), story("1", ["y."])])
    with pytest.raises(catalogue.CatalogueFormatError, match="twice"):
        documents.run(context(tmp_path, cfg, config_dir, duplicated))
    for key, value in (("page_rule", "sometimes"), ("carry_rule", "by_luck")):
        bad, _ = make_config(tmp_path, **{key: value})
        with pytest.raises(ValueError, match=key):
            documents.run(context(tmp_path, bad, config_dir, table))
    missing = copy.deepcopy(cfg)
    del missing["stages"]["documents"]["keyed_sample"]["size"]
    with pytest.raises(KeyError, match="keyed_sample"):
        documents.run(context(tmp_path, missing, config_dir, table))


def test_unicode_version_switch(tmp_path, table, capsys):
    cfg, config_dir = make_config(tmp_path)
    cfg["stages"]["documents"]["normalise"]["unicode_version"] = "0.0.0"
    documents.run(context(tmp_path, cfg, config_dir, table))
    assert "Unicode Character Database" in capsys.readouterr().err
    cfg["stages"]["documents"]["normalise"]["on_unicode_mismatch"] = "refuse"
    with pytest.raises(RuntimeError, match="Unicode"):
        documents.run(context(tmp_path, cfg, config_dir, table))


def test_a_run_under_the_repository_lock(tmp_path, table):
    # As cli.main builds it: no config_dir in ctx.extra, so the lock resolves its [lock] paths against
    # the repository's config folder and reads the real manifests. cli.main itself is not called,
    # because its discovery imports every stage module, which other tests own.
    real = tmp_path / "real_config"
    (real / "stages").mkdir(parents=True)
    for name in ("pipeline.toml", "languages.toml"):
        shutil.copy(FEATURES / "config" / name, real / name)
    shutil.copy(FEATURES / "config" / "stages" / "documents.toml", real / "stages" / "documents.toml")
    cfg = config.load(real)
    manifests = [lock.DEFAULT_CONFIG_DIR / m for m in cfg["stages"]["documents"]["lock"]["manifests"]]
    if not all(m.is_file() for m in manifests):
        pytest.skip("the published story_texts manifests are not in this checkout")
    if (lock.DEFAULT_CONFIG_DIR / "ipa_record.sha256").exists():
        pytest.skip("an IPA checksum is committed; the lock may be open")
    work = tmp_path / "cli_work"
    ctx = cli.StageContext(stage=documents.STAGE, config=cfg, lang="en-us", work=work, shard=1, nshards=2,
                           input=table)
    assert cli.run_stage(documents, ctx)["counts"]["documents"] > 0
    out = records.artefact_path(work, "en-us", "documents", 1, 2)
    with gzip.open(out, "rt", encoding="utf-8") as fh:
        ids = [json.loads(line)["story_id"] for line in fh]
    assert ids and all(records.shard_of(s, 2) == 1 for s in ids)
    manifest = manifest_of(out)
    assert manifest["lock"]["state"] == "locked" and len(manifest["lock"]["manifests"]) == 4
