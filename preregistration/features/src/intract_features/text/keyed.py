"""Registered keyed samples: story identifiers ranked by a keyed hash, so a sample depends on the ids alone.

Outcome-neutral quality checks (preregistration.qmd): "A registered sentence aligner pairs the two on
a fixed sample of 2,000 story versions per language, chosen from the story identifiers by a rule fixed in
advance, so that every run draws the same versions." That rule is the keyed hash computed here.
S3 runs the second Stanza package "on the fixed sample of 2,000 texts per language" and enlarges the
connective sample "by count alone to up to 10,000 versions".

A sample of n is the n identifiers with the smallest keyed hash. A larger sample therefore contains
every smaller one, which is what enlarging "by count alone" needs. The hash reads only the story
identifier, so every language samples the same stories, and neither file order nor sharding changes
a sample. The key string is records.keyed_hash's "<prefix>|<purpose>|<version>|<story id>" (gap G7;
the form awaits the Feature Specification), with the prefix and version from config/pipeline.toml
[keys] and the purpose from the calling stage's configuration.

A story's rank depends on which other stories are being ranked, its keyed hash does not. A record
that must be identical in a smoke run and a full run (DESIGN.md, Determinism) therefore stores the
hash, and membership of the sample of n over a given set of stories is read from that set's cut-off
(keyed_cutoffs, in_keyed_sample).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from intract_features.records import keyed_hash

DEFAULT_PREFIX = "intract"
DEFAULT_VERSION = "v1"


def key_settings(cfg: Mapping) -> dict[str, str]:
    """The keyed-hash prefix and version of config/pipeline.toml [keys], as keyword arguments."""
    keys = cfg.get("keys", {})
    return {"prefix": str(keys.get("prefix", DEFAULT_PREFIX)), "version": str(keys.get("version", DEFAULT_VERSION))}


def keyed_order(story_ids: Iterable[str], purpose: str, *, prefix: str = DEFAULT_PREFIX,
                version: str = DEFAULT_VERSION) -> list[str]:
    """Story identifiers in ascending order of their keyed hash (ties, never seen in SHA-256, by identifier)."""
    ids = list(story_ids)
    if len(set(ids)) != len(ids):
        raise ValueError("story identifiers must be unique to be ranked")
    if not purpose:
        raise ValueError("a keyed sample needs a purpose string")
    return sorted(ids, key=lambda s: (keyed_hash(purpose, s, prefix=prefix, version=version), s))


def keyed_ranks(story_ids: Iterable[str], purpose: str, *, prefix: str = DEFAULT_PREFIX,
                version: str = DEFAULT_VERSION) -> dict[str, int]:
    """Each identifier's 0-based rank in keyed order; a story is in the sample of n when its rank is below n."""
    return {s: i for i, s in enumerate(keyed_order(story_ids, purpose, prefix=prefix, version=version))}


def keyed_sample(story_ids: Iterable[str], n: int, purpose: str, *, prefix: str = DEFAULT_PREFIX,
                 version: str = DEFAULT_VERSION) -> list[str]:
    """The keyed sample of n: the n identifiers first in keyed order (all of them if there are fewer)."""
    if n < 0:
        raise ValueError("a sample size cannot be negative")
    return keyed_order(story_ids, purpose, prefix=prefix, version=version)[:n]


Cutoff = tuple[str, str]


def keyed_cutoffs(story_ids: Iterable[str], sizes: Iterable[int], purpose: str, *, prefix: str = DEFAULT_PREFIX,
                  version: str = DEFAULT_VERSION) -> dict[int, Cutoff | None]:
    """For each sample size n, the (keyed hash, story id) of the n-th story in keyed order.

    The value is None when there are fewer than n stories, all of which are then in the sample. A
    story is in the sample of n exactly when in_keyed_sample() says so, which needs only the story's
    own keyed hash and the cut-off, not the other stories.
    """
    order = keyed_order(story_ids, purpose, prefix=prefix, version=version)
    out: dict[int, Cutoff | None] = {}
    for n in sizes:
        if n < 1:
            raise ValueError("a keyed sample's size must be at least 1")
        last = order[n - 1] if len(order) >= n else None
        out[n] = None if last is None else (keyed_hash(purpose, last, prefix=prefix, version=version), last)
    return out


def in_keyed_sample(story_hash: str, story_id: str, cutoff: Cutoff | None) -> bool:
    """True if a story with this keyed hash is in the sample whose cut-off keyed_cutoffs() gave."""
    return cutoff is None or (story_hash, story_id) <= tuple(cutoff)
