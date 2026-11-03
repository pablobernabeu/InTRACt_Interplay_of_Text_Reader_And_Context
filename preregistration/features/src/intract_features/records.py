"""Shared records: the document model, keyed hashes, sharding and JSON Lines storage.

Every stage reads and writes through these helpers so that artefacts have one
layout: <work>/<lang>/<artefact>/shard-<i>-of-<n>.<ext>. A document's character
offsets always refer to its pages joined with a single space (Materials: "Pages are
joined with a single space"), after the registered normalisation.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

PAGE_JOINER = " "


@dataclass(frozen=True)
class Document:
    """One text of one language version, normalised once at load time.

    `pages` are the page texts after the registered normalisation (NFC, invisible
    format characters removed); `title` is the first line, which the extraction's
    word count already excludes and which no feature reads (gap G1a, pending the
    Feature Specification).
    """

    story_id: str
    lang: str
    level: str
    kind: str  # "generated" or "classic"
    title: str
    pages: tuple[str, ...]
    meta: dict = field(default_factory=dict, compare=False)

    @property
    def text(self) -> str:
        """The pages joined with one space, the string every character offset in every artefact refers to."""
        return PAGE_JOINER.join(self.pages)

    def page_spans(self) -> list[tuple[int, int]]:
        """[start, end) character offsets of each page in `text`."""
        spans, pos = [], 0
        for page in self.pages:
            spans.append((pos, pos + len(page)))
            pos += len(page) + len(PAGE_JOINER)
        return spans

    def page_of(self, offset: int) -> int:
        """Index of the page that holds character `offset` of `text` (a joiner belongs to the page before it)."""
        for i, (_, end) in enumerate(self.page_spans()):
            if offset <= end:
                return i
        raise ValueError(f"offset {offset} lies beyond the text of {self.story_id}")

    def to_json(self) -> dict:
        """The record the documents artefact stores."""
        return {"story_id": self.story_id, "lang": self.lang, "level": self.level, "kind": self.kind,
                "title": self.title, "pages": list(self.pages), "meta": self.meta}

    @classmethod
    def from_json(cls, obj: dict) -> Document:
        """A document read back from its documents-artefact record."""
        return cls(story_id=obj["story_id"], lang=obj["lang"], level=obj["level"], kind=obj["kind"],
                   title=obj["title"], pages=tuple(obj["pages"]), meta=obj.get("meta", {}))


def keyed_hash(purpose: str, *parts: str, prefix: str = "intract", version: str = "v1") -> str:
    """SHA-256 hex of "<prefix>|<purpose>|<version>|" + parts joined by "|".

    One key string per purpose keeps every registered sample and shard independent of
    file order and reproducible from the story ids alone (gap G7; the default form
    awaits the Feature Specification).
    """
    key = "|".join([prefix, purpose, version, *parts])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def shard_of(story_id: str, nshards: int, purpose: str = "shard", *, prefix: str = "intract",
             version: str = "v1") -> int:
    """Shard index of a story: keyed hash modulo the number of shards.

    All language versions of a story share a shard, because the hash reads only the
    story id, so cross-language stages find a story's versions in the same shard. The
    stages that assign shards (documents, qe_metricx) pass pipeline.toml [keys] as
    `prefix` and `version` (text.keyed.key_settings), so that table governs sharding
    as it governs every keyed sample; the defaults are its committed values.
    """
    if nshards < 1:
        raise ValueError("nshards must be at least 1")
    return int(keyed_hash(purpose, story_id, prefix=prefix, version=version)[:16], 16) % nshards


def artefact_path(work: Path, lang: str, artefact: str, shard: int, nshards: int, ext: str = "jsonl.gz") -> Path:
    """<work>/<lang>/<artefact>/shard-<i>-of-<n>.<ext>, the one layout of every artefact (DESIGN.md)."""
    return Path(work) / lang / artefact / f"shard-{shard}-of-{nshards}.{ext}"


def write_jsonl(path: Path, records: Iterable[dict]) -> int:
    """Write records atomically (temporary file, then rename) and return how many were written.

    A rename keeps a half-written file from ever being read as complete when a job is
    killed at its time limit.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    n = 0
    try:
        if path.suffix == ".gz":
            # mtime=0 and no file name in the header keep gzip output byte-identical across reruns,
            # so run records can compare output hashes.
            with open(tmp, "wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as fh:
                for rec in records:
                    line = json.dumps(rec, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
                    fh.write(line.encode("utf-8"))
                    n += 1
        else:
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                for rec in records:
                    fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
                    n += 1
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)
    return n


def read_jsonl(path: Path) -> Iterator[dict]:
    """The records of a JSON Lines file, gzipped when its name ends in .gz; blank lines are skipped."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def finite_or_none(x: float | None) -> float | None:
    """Map NaN and infinities to None so that every output is strict JSON."""
    if x is None:
        return None
    return x if math.isfinite(x) else None


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """SHA-256 hex digest of a file, read in chunks so that a multi-gigabyte weight file is never held in memory."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()
