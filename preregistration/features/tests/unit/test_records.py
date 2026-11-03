import gzip
import json

import pytest

from intract_features import records


def doc(pages=("One two.", "Three four!")):
    return records.Document(story_id="S1", lang="en-us", level="young", kind="generated", title="T", pages=pages)


def test_text_joins_pages_with_one_space():
    assert doc().text == "One two. Three four!"


def test_page_spans_and_page_of():
    d = doc()
    assert d.page_spans() == [(0, 8), (9, 20)]
    assert d.page_of(0) == 0
    assert d.page_of(8) == 0  # the joining space belongs to the page before it
    assert d.page_of(9) == 1
    with pytest.raises(ValueError):
        d.page_of(21)


def test_document_json_round_trip():
    d = doc()
    assert records.Document.from_json(d.to_json()) == d


def test_keyed_hash_is_stable_and_purpose_specific():
    a = records.keyed_hash("shard", "S1")
    assert a == records.keyed_hash("shard", "S1")
    assert a != records.keyed_hash("sample", "S1")
    # the documented key string: "intract|shard|v1|S1"
    import hashlib

    assert a == hashlib.sha256(b"intract|shard|v1|S1").hexdigest()


def test_shard_of_reads_only_the_story_id():
    assert records.shard_of("S1", 4) == records.shard_of("S1", 4)
    assert {records.shard_of(f"S{i}", 4) for i in range(200)} == {0, 1, 2, 3}
    with pytest.raises(ValueError):
        records.shard_of("S1", 0)


def test_write_jsonl_gz_is_byte_identical_on_rerun(tmp_path):
    recs = [{"b": 1, "a": "é"}, {"x": None}]
    p = tmp_path / "x" / "shard-0-of-1.jsonl.gz"
    assert records.write_jsonl(p, recs) == 2
    first = p.read_bytes()
    records.write_jsonl(p, recs)
    assert p.read_bytes() == first
    assert list(records.read_jsonl(p)) == recs
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        assert json.loads(fh.readline()) == {"a": "é", "b": 1}  # keys sorted


def test_write_jsonl_refuses_non_finite(tmp_path):
    with pytest.raises(ValueError):
        records.write_jsonl(tmp_path / "bad.jsonl", [{"v": float("nan")}])
    assert not (tmp_path / "bad.jsonl").exists()


def test_finite_or_none():
    assert records.finite_or_none(1.5) == 1.5
    assert records.finite_or_none(float("inf")) is None
    assert records.finite_or_none(None) is None
