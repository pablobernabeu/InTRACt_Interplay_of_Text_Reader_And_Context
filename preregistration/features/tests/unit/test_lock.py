"""Tests of the catalogue lock and its builder, on synthetic files and temporary git repositories only.

The tests that read the repository's own lock configuration load the checksums that the manifests
record, from the working tree and from the repository's history, and nothing else. No story table is
opened anywhere in this file.
"""

import csv
import hashlib
import json
import lzma
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from intract_features import lock, lock_build
from intract_features.io import catalogue

FEATURES = Path(__file__).resolve().parents[2]
GIT = shutil.which("git")
needs_git = pytest.mark.skipif(GIT is None, reason="git is not installed")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def settings(**over):
    s = {"manifests": ["manifest.json", "extraction_record.json"], "protected_dirs": ["../protected"],
         "fingerprints": "catalogue_fingerprints_*.txt", "required_fingerprints": [], "min_variant_tokens": 20,
         "ipa_checksum": "ipa_record.sha256", "ipa_record": "", "ipa_commit_check": "git",
         "on_missing_manifest": "refuse"}
    s.update(over)
    return s


def write_manifests(config_dir: Path, protected=(), uncompressed=()):
    """Manifests in the structure publish_story_texts.py and extract_story_texts.py write."""
    config_dir.mkdir(parents=True, exist_ok=True)
    languages = {f"l{i}": {"file": f"l{i}/stories.csv.xz", "stories": 1, "bytes": 1, "sha256": h,
                           "uncompressed_bytes": 1, "uncompressed_sha256": u}
                 for i, (h, u) in enumerate(zip(list(protected) or ["a" * 64], list(uncompressed) or ["b" * 64],
                                                strict=False))}
    manifest = {"languages": languages, "files": {"anomalies.csv": {"bytes": 1, "sha256": "c" * 64}}}
    record = {"stories": 1, "files": [{"file": "x.zip", "bytes": 1, "sha256": "d" * 64, "entries": 1}],
              "id_source": {"file": "id_map.json", "bytes": 1, "sha256": "e" * 64}}
    (config_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (config_dir / "extraction_record.json").write_text(json.dumps(record), encoding="utf-8")


def load(config_dir, environ=None, **over):
    return lock.CatalogueLock.load(config_dir, settings(**over), environ={} if environ is None else environ)


# ---- temporary git repositories (plumbing only, so no hook runs and no identity is needed beyond a label) ----
GIT_ENV = {"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture", "GIT_COMMITTER_NAME": "fixture",
           "GIT_COMMITTER_EMAIL": "fixture", "GIT_AUTHOR_DATE": "2026-10-18T12:00:00+00:00",
           "GIT_COMMITTER_DATE": "2026-10-18T12:00:00+00:00"}


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV})
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def new_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "core.autocrlf", "false")
    return path


def commit_all(repo: Path, message: str = "fixture") -> str:
    git(repo, "add", "-A")
    tree = git(repo, "write-tree")
    parent = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    commit = git(repo, "commit-tree", tree, "-m", message, *(["-p", parent] if parent else []))
    git(repo, "update-ref", "HEAD", commit)
    return commit


# ---- fingerprints and readings ----
def test_fingerprint_ignores_encoding_whitespace_and_paging():
    base = lock.fingerprint(["Once upon a time, a fox.", "It ran home."])
    assert base == lock.fingerprint(["Once upon  a time,\na fox. It", "ran home.  "])
    assert base == lock.fingerprint(["Once upon a time, a fox.", "", "It ran home."])
    assert base == lock.fingerprint(["Once\xa0upon a time, a fox.\N{ZERO WIDTH SPACE}", "It ran home."])
    assert base != lock.fingerprint(["Once upon a time, a fox.", "It ran away."])
    assert lock.fingerprint(["caf\xe9"]) == lock.fingerprint(["cafe\N{COMBINING ACUTE ACCENT}"])
    assert len(base) == 16 and int(base, 16) >= 0
    assert lock.EMPTY_FINGERPRINT == lock.fingerprint(["", "  "]) == sha(b"")[:16]


PAGES = ["Once upon a time a small red fox lived at the edge of a very old wood.",
         "Every morning the fox ran down to the river to drink and to watch the fish.",
         "One day the river was gone, and the fox set out to find where it had gone."]


def test_readings_catch_copies_whose_first_line_moved():
    listed = lock.fingerprint(PAGES)
    readings = lock.text_fingerprints("The Fox", PAGES, min_tokens=20)
    assert readings["pages"] == listed
    # A copy that lost its title line: its first page is read as the title line.
    assert lock.text_fingerprints(PAGES[0], PAGES[1:], min_tokens=20)["with_title_line"] == listed
    # A copy that gained a header line: its title line is read as the first page.
    assert lock.text_fingerprints("Header", ["The Fox", *PAGES], min_tokens=20)["without_first_page"] == listed
    assert not any(name.startswith(lock.UNMARKED) for name in readings)  # no page markers, no unmarked readings


def test_readings_bridge_the_viewer_and_zip_forms():
    viewer_text = "Page 1: " + PAGES[0] + "\nPage 2: " + PAGES[1] + "\nPage 3: " + PAGES[2]
    v_title, v_pages = catalogue.split_lines(viewer_text)
    readings = lock.text_fingerprints(v_title, v_pages, min_tokens=20)
    assert readings["unmarked_with_title_line"] == lock.fingerprint(PAGES)  # a viewer copy of a zip-form text
    # A viewer text with a preamble before its first marker.
    p_title, p_pages = catalogue.split_lines("The Fox\n" + viewer_text)
    assert lock.text_fingerprints(p_title, p_pages)["unmarked_pages"] == lock.fingerprint(PAGES)
    # A fingerprint file built from the viewer's table also lists the marker-free readings, so a zip-form
    # copy of a text published only in the viewer's form is refused.
    assert lock.listed_fingerprints(v_title, v_pages) == {lock.fingerprint(v_pages), readings["unmarked_pages"],
                                                          lock.fingerprint(PAGES)}
    assert lock.listed_fingerprints("The Fox", PAGES) == {lock.fingerprint(PAGES)}


def test_short_derived_readings_are_not_checked():
    readings = lock.text_fingerprints("The Fox", [PAGES[0], "The End."], min_tokens=20)
    assert "without_first_page" not in readings  # two tokens, below the minimum
    assert "pages" in readings and "with_title_line" in readings
    assert lock.text_fingerprints("", [], min_tokens=20) == {}
    assert lock.text_fingerprints("A", ["b"], min_tokens=1) == {
        "pages": lock.fingerprint(["b"]), "with_title_line": lock.fingerprint(["A b"])}


def test_check_text_refuses_any_listed_reading(tmp_path):
    config = tmp_path / "config"
    write_manifests(config)
    write_fp_file(config / "catalogue_fingerprints_en-us.txt", sorted({lock.fingerprint(PAGES), "0" * 16}))
    lk = load(config)
    assert lk.check_text("standin", "A Title", ["A different story entirely."]) == lock.fingerprint(
        ["A different story entirely."])
    for title_line, pages in (("The Fox", PAGES), (PAGES[0], PAGES[1:]), ("Header", ["The Fox", *PAGES])):
        with pytest.raises(lock.CatalogueLocked, match="reading"):
            lk.check_text("copy", title_line, pages)
    # A short catalogue text is not matched by a short remainder of a longer stand-in text.
    write_fp_file(config / "catalogue_fingerprints_en-us.txt", [lock.fingerprint(["The End."])])
    load(config).check_text("standin", "A Title", [PAGES[0], "The End."])


def test_recorded_checksums_reads_only_sha256_keys():
    obj = {"a": {"sha256": "A" * 64, "sha1": "1" * 40, "uncompressed_sha256": "b" * 64},
           "list": [{"file_sha256": "c" * 64}, {"sha256": "short"}], "sha256": 7, "other": "d" * 64}
    assert lock.recorded_checksums(obj) == {"a" * 64, "b" * 64, "c" * 64}
    assert lock.recorded_checksum_entries(obj) == [("a/sha256", "a" * 64), ("a/uncompressed_sha256", "b" * 64),
                                                  ("list/0/file_sha256", "c" * 64)]


# ---- refusing inputs ----
def test_protected_checksums_refuse_stored_and_decompressed_copies(tmp_path):
    table = b"id,text\n1,hello\n"
    plain = tmp_path / "copy.csv"
    plain.write_bytes(table)
    packed = tmp_path / "copy.csv.xz"
    packed.write_bytes(lzma.compress(table))
    config = tmp_path / "config"
    write_manifests(config, protected=["f" * 64], uncompressed=[sha(table)])
    lk = load(config)
    for path in (plain, packed):
        with pytest.raises(lock.CatalogueLocked):
            lk.check_input(path)
    write_manifests(config, protected=[sha(packed.read_bytes())])
    with pytest.raises(lock.CatalogueLocked):
        load(config).check_input(packed)


def test_unrelated_input_passes_with_its_checksums(tmp_path):
    write_manifests(tmp_path / "config")
    path = tmp_path / "standin.csv.xz"
    path.write_bytes(lzma.compress(b"x"))
    got = load(tmp_path / "config").check_input(path)
    assert got == {"name": "standin.csv.xz", "bytes": path.stat().st_size, "sha256": sha(path.read_bytes()),
                   "content_sha256": sha(b"x")}
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "config").check_input(tmp_path / "missing.csv")


def test_protected_directories_refuse_any_file(tmp_path):
    write_manifests(tmp_path / "config")
    inside = tmp_path / "protected" / "sub" / "anything.csv"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"id\n")
    with pytest.raises(lock.CatalogueLocked, match="protected directory"):
        load(tmp_path / "config").check_input(inside)


# ---- refusing documents ----
def write_fp_file(path: Path, lines):
    path.write_text("# header\n\n" + "\n".join(lines) + "\n", encoding="utf-8")


def test_fingerprint_files_are_read_strictly(tmp_path):
    good = tmp_path / "good.txt"
    write_fp_file(good, ["0000000000000001", "00000000000000ff", "ffffffffffffffff"])
    assert list(lock.read_fingerprints(good)) == [1, 255, 2**64 - 1]
    for lines, message in ((["00000000000000ff", "0000000000000001"], "sorted"), (["0000000000000001"] * 2, "sorted"),
                           (["XYZ"], "not a fingerprint"), (["00000000000000FF"], "not a fingerprint")):
        write_fp_file(tmp_path / "bad.txt", lines)
        with pytest.raises(lock.LockError, match=message):
            lock.read_fingerprints(tmp_path / "bad.txt")


def test_listed_documents_are_refused_in_every_language(tmp_path):
    config = tmp_path / "config"
    write_manifests(config)
    listed = lock.fingerprint(["A catalogue text."])
    write_fp_file(config / "catalogue_fingerprints_de-de.txt", [listed])
    lk = load(config)
    with pytest.raises(lock.CatalogueLocked):
        lk.check_document("1", listed)
    lk.check_document("2", lock.fingerprint(["A stand-in text."]))
    lk.check_document("3", lock.EMPTY_FINGERPRINT)
    assert lk.record["fingerprint_files"][0]["fingerprints"] == 1


def test_required_fingerprint_files_fail_closed(tmp_path):
    config = tmp_path / "config"
    write_manifests(config)
    with pytest.raises(lock.LockError, match="catalogue_fingerprints_en-us.txt is required"):
        load(config, required_fingerprints=["en-us"])
    write_fp_file(config / "catalogue_fingerprints_en-us.txt", ["0000000000000001"])
    lk = load(config, required_fingerprints=["en-us"])
    assert lk.record["required_fingerprints"] == ["en-us"] and len(lk.fingerprint_files) == 1
    with pytest.raises(lock.LockError, match="one '\\*'"):
        load(config, required_fingerprints=["en-us"], fingerprints="catalogue_fingerprints.txt")
    with pytest.raises(lock.LockError, match="min_variant_tokens"):
        load(config, min_variant_tokens=0)


# ---- unlocking ----
def write_checksum(config: Path, record: Path):
    (config / "ipa_record.sha256").write_text(f"# committed at acceptance\n{sha(record.read_bytes())}  "
                                              f"{record.name}\n", encoding="utf-8")


def test_ipa_record_unlocks_only_with_the_matching_checksum(tmp_path):
    config = tmp_path / "config"
    write_manifests(config)
    record = tmp_path / "ipa_letter.pdf"
    record.write_bytes(b"in-principle acceptance")
    assert load(config, ipa_commit_check="none").unlocked is False  # no checksum
    write_checksum(config, record)
    assert load(config, ipa_commit_check="none").unlocked is False  # a checksum, but no record given
    unlocked = load(config, environ={lock.ENV_IPA_RECORD: str(record)}, ipa_commit_check="none")
    assert unlocked.unlocked and unlocked.record["state"] == "unlocked"
    assert unlocked.record["ipa_commit_check"] == "none"
    assert load(config, ipa_record=str(record), ipa_commit_check="none").unlocked
    forged = tmp_path / "forged.pdf"
    forged.write_bytes(b"not the record")
    assert load(config, environ={lock.ENV_IPA_RECORD: str(forged)}, ipa_commit_check="none").unlocked is False
    # Once unlocked, nothing is refused.
    write_manifests(config, protected=[sha(record.read_bytes())])
    unlocked = load(config, environ={lock.ENV_IPA_RECORD: str(record)}, ipa_commit_check="none")
    unlocked.check_input(record)
    unlocked.check_document("1", lock.fingerprint(["x"]))
    assert unlocked.check_text("1", "T", ["x"]) == lock.fingerprint(["x"])
    with pytest.raises(lock.LockError):
        load(config, ipa_commit_check="sometimes")


def test_an_uncommitted_checksum_outside_a_repository_does_not_unlock(tmp_path, capsys):
    config = tmp_path / "config"
    write_manifests(config)
    record = tmp_path / "ipa_letter.pdf"
    record.write_bytes(b"in-principle acceptance")
    write_checksum(config, record)
    held = load(config, environ={lock.ENV_IPA_RECORD: str(record)})
    assert held.unlocked is False and held.record["ipa_checksum_git_commit"] is None
    assert "counts only once committed" in capsys.readouterr().err


@needs_git
def test_the_checksum_unlocks_only_while_committed_unchanged(tmp_path):
    repo = new_repo(tmp_path / "repo")
    config = repo / "config"
    write_manifests(config)
    first, second = tmp_path / "first.pdf", tmp_path / "second.pdf"
    first.write_bytes(b"in-principle acceptance")
    second.write_bytes(b"another letter")
    write_checksum(config, first)
    env = {lock.ENV_IPA_RECORD: str(first)}
    assert load(config, environ=env).unlocked is False  # untracked
    commit = commit_all(repo)
    opened = load(config, environ=env)
    assert opened.unlocked and opened.record["ipa_checksum_git_commit"] == commit
    write_checksum(config, second)  # edited after the commit, and matching the second record
    assert load(config, environ={lock.ENV_IPA_RECORD: str(second)}).unlocked is False
    assert load(config, environ={lock.ENV_IPA_RECORD: str(second)}, ipa_commit_check="none").unlocked


@pytest.mark.parametrize("content", ["not-a-checksum\n", "# only a comment\n", "abc\n"])
def test_a_malformed_committed_checksum_stops_the_run(tmp_path, content):
    config = tmp_path / "config"
    write_manifests(config)
    (config / "ipa_record.sha256").write_text(content, encoding="utf-8")
    with pytest.raises(lock.LockError):
        load(config)


# ---- failing closed ----
def test_missing_or_empty_manifests_fail_closed(tmp_path, capsys):
    config = tmp_path / "config"
    config.mkdir()
    with pytest.raises(lock.LockError, match="cannot read"):
        load(config)
    warned = load(config, on_missing_manifest="warn")
    assert warned.checksums == frozenset() and "WARNING" in capsys.readouterr().err
    with pytest.raises(lock.LockError, match="names no manifest"):
        load(config, manifests=[])
    (config / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(lock.LockError, match="records no SHA-256"):
        load(config, manifests=["manifest.json"])
    with pytest.raises(lock.LockError):
        load(config, on_missing_manifest="ignore")


# ---- the builder: fingerprints ----
def write_story_table(path: Path, texts):
    path.parent.mkdir(parents=True, exist_ok=True)
    with lzma.open(path, "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(catalogue.STORY_COLS)
        for i, text in enumerate(texts):
            w.writerow([str(i), "H-W-T-P-S-young", "H", "W", "T", "P", "S", "young", "en-us", "t", "1", "1", "", text])
    return path


TEXTS = ["Title\nPage one.\nPage two.", "Title\nPage one.\nPage two.", "Other\nA different\\ntext.", "Empty\n"]
AUTH = ["--authorisation", "synthetic tables only"]


def file_values(path: Path) -> list[str]:
    return [x for x in path.read_text(encoding="utf-8").splitlines() if x and not x.startswith("#")]


def test_lock_build_writes_sorted_unique_fingerprints(tmp_path, capsys):
    tables = tmp_path / "tables"
    write_story_table(tables / "en-us" / "stories.csv.xz", TEXTS)
    write_story_table(tables / "de-de" / "stories.csv.xz", ["Titel\nSeite eins."])
    out = tmp_path / "config"
    assert lock_build.main(["fingerprints", "--tables", str(tables), "--out", str(out), *AUTH]) == 0
    printed = capsys.readouterr().out
    assert "catalogue_fingerprints_en-us.txt: fingerprints written: 2" in printed
    assert '["de-de", "en-us"]' in printed  # the labels for [lock] required_fingerprints
    lines = (out / "catalogue_fingerprints_en-us.txt").read_text(encoding="utf-8").splitlines()
    header = [x for x in lines if x.startswith("#")]
    assert any("Source: en-us/stories.csv.xz, SHA-256" in x and "rows 4" in x for x in header)
    assert "# Authorised: synthetic tables only" in header
    expected = sorted({lock.fingerprint(catalogue.split_lines(t)[1]) for t in TEXTS[:3]})
    assert file_values(out / "catalogue_fingerprints_en-us.txt") == expected  # duplicates once, empty text left out
    assert (out / "catalogue_fingerprints_de-de.txt").is_file()

    write_manifests(out)
    lk = load(out, required_fingerprints=["de-de", "en-us"])
    with pytest.raises(lock.CatalogueLocked):
        lk.check_document("x", lock.fingerprint(["Page one. Page", "two."]))  # re-paged, still refused


def test_lock_build_lists_the_viewer_forms_marker_free_readings(tmp_path):
    viewer = "Page 1: " + PAGES[0] + "\nPage 2: " + PAGES[1] + "\nPage 3: " + PAGES[2]
    write_story_table(tmp_path / "tables" / "en-us-viewer" / "stories.csv.xz", [viewer])
    out = tmp_path / "config"
    lock_build.main(["fingerprints", "--tables", str(tmp_path / "tables"), "--out", str(out), *AUTH])
    values = file_values(out / "catalogue_fingerprints_en-us-viewer.txt")
    assert lock.fingerprint(PAGES) in values and len(values) == 3  # as split, and two marker-free readings
    write_manifests(out)
    with pytest.raises(lock.CatalogueLocked):
        load(out).check_text("zip-form copy", "The Fox", PAGES)


def test_lock_build_needs_its_arguments(tmp_path):
    with pytest.raises(SystemExit):
        lock_build.main([])
    with pytest.raises(SystemExit):
        lock_build.main(["fingerprints", "--tables", str(tmp_path), "--out", str(tmp_path / "o")])  # no authorisation
    with pytest.raises(SystemExit):
        lock_build.main(["fingerprints", "--tables", str(tmp_path), "--out", str(tmp_path / "o"), *AUTH])  # no table
    with pytest.raises(SystemExit):
        lock_build.main(["fingerprints", "--tables", str(tmp_path), "--out", str(tmp_path / "o"),
                         "--authorisation", "two\nlines"])
    with pytest.raises(SystemExit):
        lock_build.main(["fingerprints", "--tables", str(tmp_path), "--out", str(tmp_path / "o"), *AUTH,
                         "--suffix", "x"])  # a suffix needs --rev
    with pytest.raises(SystemExit):
        lock_build.main(["checksums", "--out", str(tmp_path / "x.json")])  # no revision


@needs_git
def test_lock_build_reads_tables_from_the_history_without_a_copy(tmp_path, capsys):
    repo = new_repo(tmp_path / "repo")
    table = write_story_table(repo / "data" / "en-us" / "stories.csv.xz", TEXTS)
    write_story_table(repo / "data" / "de-de" / "stories.csv.xz", ["Titel\nSeite eins."])
    original = table.read_bytes()
    commit = commit_all(repo)
    write_story_table(table, ["Changed\nA later text."])  # the working tree no longer holds the old table
    out = tmp_path / "config"
    lock_build.main(["fingerprints", "--repo", str(repo), "--rev", commit[:10], "--tables", "data", "--langs", "en-us",
                     "--suffix", "2026-10-18", "--out", str(out), *AUTH])
    written = out / "catalogue_fingerprints_en-us-2026-10-18.txt"
    expected = sorted({lock.fingerprint(catalogue.split_lines(t)[1]) for t in TEXTS[:3]})
    assert file_values(written) == expected
    text = written.read_text(encoding="utf-8")
    blob = git(repo, "rev-parse", f"{commit}:data/en-us/stories.csv.xz")
    assert f"git {commit[:12]}:data/en-us/stories.csv.xz (blob {blob}), SHA-256 {sha(original)}" in text
    assert sorted(p.name for p in out.iterdir()) == [written.name]  # nothing else written, no table copy
    capsys.readouterr()
    lock_build.main(["fingerprints", "--repo", str(repo), "--rev", "HEAD", "--tables", str(repo / "data"),
                     "--out", str(out), *AUTH])
    assert f'["de-de-{commit[:7]}", "en-us-{commit[:7]}"]' in capsys.readouterr().out


@needs_git
def test_lock_build_freezes_a_publications_checksums(tmp_path):
    repo = new_repo(tmp_path / "repo")
    write_manifests(repo / "data", protected=["f" * 64], uncompressed=["9" * 64])
    commit = commit_all(repo)
    out = tmp_path / "config" / "lock" / "published.json"
    assert lock_build.main(["checksums", "--repo", str(repo), "--rev", commit, "--folder", "data",
                            "--out", str(out)]) == 0
    frozen = json.loads(out.read_text(encoding="utf-8"))
    assert frozen["publication"] == {"commit": commit, "date": "2026-10-18", "folder": "data"}
    manifest_bytes = (repo / "data" / "manifest.json").read_bytes()
    assert frozen["sources"][0] == {"file": "manifest.json", "git_blob": git(repo, "rev-parse", f"{commit}:data/"
                                                                                          "manifest.json"),
                                    "bytes": len(manifest_bytes), "file_sha256": sha(manifest_bytes)}
    keys = {(c["source"], c["key"]): c["sha256"] for c in frozen["checksums"]}
    assert keys[("manifest.json", "languages/l0/sha256")] == "f" * 64
    assert keys[("extraction_record.json", "id_source/sha256")] == "e" * 64
    assert len(keys) == 5
    lk = lock.CatalogueLock.load(out.parent, settings(manifests=["published.json"]), environ={})
    assert {"f" * 64, "9" * 64, sha(manifest_bytes)} <= lk.checksums
    with pytest.raises(SystemExit):
        lock_build.main(["checksums", "--repo", str(repo), "--rev", "HEAD;x", "--out", str(out)])


# ---- the repository's configuration ----
def repository_lock_settings() -> dict:
    return tomllib.loads((FEATURES / "config" / "stages" / "documents.toml").read_text(encoding="utf-8"))["lock"]


def test_repository_lock_configuration_holds(tmp_path):
    cfg = repository_lock_settings()
    manifests = [lock.DEFAULT_CONFIG_DIR / m for m in cfg["manifests"]]
    if not all(m.is_file() for m in manifests):
        pytest.skip("the published story_texts manifests are not in this checkout")
    if (lock.DEFAULT_CONFIG_DIR / cfg["ipa_checksum"]).exists():
        pytest.skip("an IPA checksum is committed; the lock may be open")
    lk = lock.CatalogueLock.load(lock.DEFAULT_CONFIG_DIR, cfg, environ={})
    assert lk.unlocked is False
    assert all(m["checksums"] > 0 for m in lk.record["manifests"]) and len(lk.record["manifests"]) == 4
    standin = tmp_path / "standin.csv"
    standin.write_text("id\n", encoding="utf-8")
    lk.check_input(standin)
    for d in lk.protected_dirs:
        assert d.name in ("data", "Oxford-40k-stories")


def test_every_frozen_record_is_listed():
    frozen = {f"lock/{p.name}" for p in (FEATURES / "config" / "lock").glob("published_*.json")}
    assert frozen == {"lock/published_2026-10-18.json", "lock/published_2026-10-27.json"}
    assert frozen <= set(repository_lock_settings()["manifests"])


@needs_git
def test_frozen_records_match_the_repository_history():
    try:
        top = lock_build.git_toplevel(FEATURES)
    except lock_build.BuildError:
        pytest.skip("this checkout is not a git repository")
    for path in sorted((FEATURES / "config" / "lock").glob("published_*.json")):
        frozen = json.loads(path.read_text(encoding="utf-8"))
        commit = frozen["publication"]["commit"]
        if subprocess.run(["git", "-C", str(top), "cat-file", "-e", f"{commit}^{{commit}}"],
                          capture_output=True).returncode != 0:
            pytest.skip(f"commit {commit[:12]} is not in this clone")
        again = lock_build.published_checksums(top, commit, frozen["publication"]["folder"],
                                               [s["file"] for s in frozen["sources"]])
        assert again == frozen, path.name
