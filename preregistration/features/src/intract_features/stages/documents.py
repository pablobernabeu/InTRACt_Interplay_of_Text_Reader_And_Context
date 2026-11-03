"""Stage `documents`: rows in the catalogue's published schema to normalised documents, behind the lock.

    python -m intract_features run documents --work WORK --lang en-us --input TABLE.csv.xz
                                             [--shard I --nshards N] [--limit K]

The stage reads the --input table (io.catalogue) and applies the catalogue lock to the file and then
to every row of every shard, straight after the delivery's own split into title line and pages and
before anything else is computed on it (lock.py). It normalises each title and page once (S3,
text/normalise.py), keeps the stories of this shard (records.shard_of) and the first K of them under
--limit, finds page titles under S3's rule (text/titles.py) and writes
<work>/<lang>/documents/shard-<i>-of-<n>.jsonl.gz. It returns the counts for the timing record
(COUNT_KEYS): documents, pages, words (the registered word function), characters (of the page join),
and what was read, skipped, changed and found. max_page_characters and max_page_words are maxima over
this shard's pages, not sums.

A document's record depends only on its own row and the configuration, never on which other stories
the input holds, so a story's record is the same in a sharded, limited, smoke or full run (DESIGN.md,
Determinism: "The 1 per cent smoke run's rows must equal the same rows of the full run"). For the
keyed sample it therefore stores the story's keyed hash (meta.keyed_hash, text/keyed.py), not a rank,
which would depend on the other stories. Beside the artefact, shard-<i>-of-<n>.manifest.json records
the input's name and checksums, the lock's state, the Unicode version, the stage's configuration, the
counts, and the keyed sample's cut-offs over every story of the input, from which membership of the
samples of [keyed_sample] size and max_size follows (text.keyed.in_keyed_sample). The manifest is a
run record, so it may differ between runs; the rows may not.

For a language other than the English source, page titles are carried from the English documents of
the same shard (S3), which must exist unless [titles] page_rule is "off".
"""

from __future__ import annotations

import json
import platform
import sys
from collections import Counter
from collections.abc import Iterator, Mapping
from pathlib import Path

from intract_features import records
from intract_features.cli import Stage, StageContext
from intract_features.io import catalogue
from intract_features.lock import DEFAULT_CONFIG_DIR, CatalogueLock
from intract_features.text import keyed, titles
from intract_features.text.normalise import UNICODE_VERSION, Normaliser
from intract_features.text.words import LINE_BREAK, count_words

STAGE = Stage(name="documents", inputs=(), outputs=("documents",), device="cpu", env="core",
              description="catalogue-schema rows to normalised documents, behind the catalogue lock")

# Every key is reported, zero or not, so that timing records from different runs share one schema.
COUNT_KEYS = ("documents", "pages", "words", "characters", "rows_read", "rows_other_shards", "rows_beyond_limit",
              "format_characters_deleted", "pages_changed_by_nfc", "page_titles", "page_title_words",
              "page_titles_not_carried", "pages_with_line_breaks", "title_lines_empty", "title_lines_page_marker",
              "documents_without_english_source", "documents_without_level", "catalogue_word_count_mismatches",
              "empty_pages", "keyed_sample_documents", "max_page_characters", "max_page_words")

REQUIRED = {
    "normalise": ("form", "delete_ranges", "unicode_version", "on_unicode_mismatch"),
    "catalogue": ("levels",),
    "titles": ("max_words", "terminal_marks", "page_rule", "action", "final_mark_test", "carry_rule", "english_lang"),
    "keyed_sample": ("purpose", "size", "max_size"),
    "lock": ("manifests", "protected_dirs", "fingerprints", "required_fingerprints", "min_variant_tokens",
             "ipa_checksum", "ipa_record", "ipa_commit_check", "on_missing_manifest"),
}


def settings(ctx: StageContext) -> dict:
    """The stage's configuration (config/stages/documents.toml), checked for every key and value it needs."""
    cfg = ctx.stage_config()
    for table, keys in REQUIRED.items():
        missing = [k for k in keys if k not in cfg.get(table, {})]
        if missing:
            raise KeyError(f"config/stages/documents.toml [{table}] lacks {missing}")
    t = cfg["titles"]
    for key, allowed in (("page_rule", titles.PAGE_RULES), ("action", titles.ACTIONS),
                         ("final_mark_test", titles.FINAL_MARK_TESTS), ("carry_rule", titles.CARRY_RULES)):
        if t[key] not in allowed:
            raise ValueError(f"[titles] {key} must be one of {allowed}, not {t[key]!r}")
    if cfg["normalise"]["on_unicode_mismatch"] not in ("warn", "refuse"):
        raise ValueError("[normalise] on_unicode_mismatch must be 'warn' or 'refuse'")
    k = cfg["keyed_sample"]
    if not 1 <= int(k["size"]) <= int(k["max_size"]):
        raise ValueError("[keyed_sample] needs 1 <= size <= max_size")
    return cfg


def terminal_marks(ctx: StageContext, cfg: Mapping) -> frozenset[str]:
    """S3's terminal marks plus the language's own (languages.toml), for the title rule."""
    own = ctx.config.get("languages", {}).get(ctx.lang, {}).get("terminal_marks", [])
    return frozenset(cfg["titles"]["terminal_marks"]) | frozenset(own)


def english_titles(ctx: StageContext, english_lang: str) -> dict[str, tuple[int, list[titles.PageTitle], list[int]]]:
    """Per story of this shard, the English source's page count, page titles and line counts as served.

    S3: titles "are identified on the English source and carried to each translation".
    """
    path = records.artefact_path(ctx.work, english_lang, "documents", ctx.shard, ctx.nshards)
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing. Page titles are identified on the English source and carried "
                                f"to each translation (S3), so run the documents stage for {english_lang} first, "
                                f"or set [titles] page_rule = 'off'")
    out = {}
    for obj in records.read_jsonl(path):
        found = [titles.PageTitle.from_json(t) for t in obj.get("meta", {}).get("page_titles", [])]
        out[obj["story_id"]] = (len(obj["pages"]), found, titles.served_line_counts(obj["pages"], found))
    return out


def write_json(path: Path, obj: dict) -> None:
    """Write strict JSON atomically, as records.write_jsonl writes its files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
                       encoding="utf-8")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)


def _check_unicode(cfg: Mapping) -> None:
    expected = cfg["normalise"]["unicode_version"]
    if expected == UNICODE_VERSION:
        return
    message = (f"documents: this Python's Unicode Character Database is {UNICODE_VERSION}, the configuration "
               f"names {expected}")
    if cfg["normalise"]["on_unicode_mismatch"] == "refuse":
        raise RuntimeError(message)
    print(f"WARNING {message}; recorded in the run manifest", file=sys.stderr)


def run(ctx: StageContext) -> dict:
    """Read --input, apply the lock, normalise, keep this shard's stories and write the documents artefact."""
    cfg = settings(ctx)
    if ctx.input is None:
        raise ValueError("the documents stage needs --input, a table in the catalogue's published schema")
    if ctx.limit is not None and ctx.limit < 0:
        raise ValueError("--limit cannot be negative")
    config_dir = Path(ctx.extra.get("config_dir", DEFAULT_CONFIG_DIR))
    lock = CatalogueLock.load(config_dir, cfg["lock"])
    input_record = lock.check_input(ctx.input)
    _check_unicode(cfg)

    normaliser = Normaliser(cfg["normalise"]["delete_ranges"], cfg["normalise"]["form"])
    t = cfg["titles"]
    marks = terminal_marks(ctx, cfg)
    english = ctx.lang == t["english_lang"]
    carried_from = None if english or t["page_rule"] == "off" else english_titles(ctx, t["english_lang"])
    levels = frozenset(cfg["catalogue"]["levels"])
    sample = cfg["keyed_sample"]
    keys = keyed.key_settings(ctx.config)

    counts: Counter = Counter(dict.fromkeys(COUNT_KEYS, 0))
    story_ids: list[str] = []
    seen: set[str] = set()
    kept_keys: list[tuple[str, str]] = []  # (keyed hash, story id) of each document written

    def documents() -> Iterator[dict]:
        # A generator, so that rows stream to the artefact; records.write_jsonl writes a temporary file
        # and renames it only at the end, so a row the lock refuses leaves no artefact behind.
        n_kept = 0
        for row in catalogue.read_rows(ctx.input):
            counts["rows_read"] += 1
            # The lock sees every row of every shard straight after the delivery's own split into
            # title line and pages, before anything else is computed on it.
            title_line, raw_pages = catalogue.split_lines(row["text"])
            keep = records.shard_of(row["id"], ctx.nshards, **keys) == ctx.shard
            fp = lock.check_text(row["id"], title_line, raw_pages) if keep or not lock.unlocked else None
            crow = catalogue.parse_row(row, levels=levels, split=(title_line, raw_pages))
            if crow.lang != ctx.lang:
                raise catalogue.CatalogueFormatError(f"story {crow.story_id!r} is in {crow.lang!r}, "
                                                     f"the run is {ctx.lang!r}")
            if crow.story_id in seen:
                raise catalogue.CatalogueFormatError(f"story {crow.story_id!r} appears twice in {ctx.input.name}")
            seen.add(crow.story_id)
            story_ids.append(crow.story_id)
            if not keep:
                counts["rows_other_shards"] += 1
                continue
            if ctx.limit is not None and n_kept >= ctx.limit:
                counts["rows_beyond_limit"] += 1
                continue
            n_kept += 1
            yield document(crow, fp).to_json()

    def document(crow: catalogue.CatalogueRow, fp: str) -> records.Document:
        issue = catalogue.title_line_issue(crow.title_line)
        counts["title_lines_empty"] += issue == catalogue.EMPTY_TITLE
        counts["title_lines_page_marker"] += issue == catalogue.PAGE_MARKER_TITLE
        title, deleted, _ = normaliser.with_stats(crow.title_line)
        counts["format_characters_deleted"] += deleted
        pages = []
        for raw in crow.pages:
            page, deleted, nfc_changed = normaliser.with_stats(raw)
            counts["format_characters_deleted"] += deleted
            counts["pages_changed_by_nfc"] += nfc_changed
            counts["pages_with_line_breaks"] += LINE_BREAK in page
            pages.append(page)

        if english:
            found = titles.find_page_titles(pages, page_rule=t["page_rule"], max_words=t["max_words"],
                                            terminal_marks=marks, final_mark_test=t["final_mark_test"])
        elif carried_from is None:
            found = []
        elif crow.story_id in carried_from:
            english_pages, english_found, english_lines = carried_from[crow.story_id]
            found, lost = titles.carry_page_titles(english_found, english_pages, pages, rule=t["carry_rule"],
                                                   english_lines=english_lines)
            counts["page_titles_not_carried"] += lost
        else:
            found = []
            counts["documents_without_english_source"] += 1
        story_hash = records.keyed_hash(sample["purpose"], crow.story_id, **keys)
        kept_keys.append((story_hash, crow.story_id))
        meta = dict(crow.meta, fingerprint=fp, keyed_hash=story_hash)
        if issue:
            meta["title_line_issue"] = issue
        if found:
            counts["page_titles"] += len(found)
            counts["page_title_words"] += sum(count_words(p.text) for p in found)
            meta["page_titles"] = [p.to_json() for p in found]
            meta["page_titles_excluded"] = t["action"] == "exclude"
            if t["action"] == "exclude":
                pages = list(titles.exclude_page_titles(pages, found))
        doc = records.Document(story_id=crow.story_id, lang=crow.lang, level=crow.level, kind=crow.kind,
                               title=title, pages=tuple(pages), meta=meta)
        page_words = [count_words(p) for p in pages]
        counts["pages"] += len(pages)
        counts["words"] += sum(page_words)  # the join is a space, so no word spans two pages
        counts["characters"] += len(doc.text)
        counts["max_page_characters"] = max(counts["max_page_characters"], *(len(p) for p in pages), 0)
        counts["max_page_words"] = max(counts["max_page_words"], *page_words, 0)
        counts["documents_without_level"] += not crow.level
        counts["catalogue_word_count_mismatches"] += not crow.words_consistent
        counts["empty_pages"] += sum(1 for p in pages if not p.strip())
        return doc

    written = ctx.write("documents", documents())
    sizes = (int(sample["size"]), int(sample["max_size"]))
    cutoffs = keyed.keyed_cutoffs(story_ids, sizes, sample["purpose"], **keys)
    counts["documents"] = written
    counts["keyed_sample_documents"] = sum(keyed.in_keyed_sample(h, s, cutoffs[sizes[0]]) for h, s in kept_keys)
    result = {k: int(v) for k, v in sorted(counts.items())}
    keyed_record = {
        "key": f"{keys['prefix']}|{sample['purpose']}|{keys['version']}|<story id>",
        "stories_in_input": len(story_ids),
        "rule": ("a document is in the input's keyed sample of size n when (meta.keyed_hash, story_id) <= "
                 "(keyed_hash, story_id) of that size's cut-off; a null cut-off means the input holds fewer "
                 "than n stories, all of them in the sample"),
        "cutoffs": [{"size": n, "keyed_hash": c[0] if c else None, "story_id": c[1] if c else None,
                     "documents_written": sum(keyed.in_keyed_sample(h, s, c) for h, s in kept_keys)}
                    for n, c in cutoffs.items()],
    }
    manifest = {"stage": STAGE.name, "lang": ctx.lang, "shard": ctx.shard, "nshards": ctx.nshards, "limit": ctx.limit,
                "input": input_record, "lock": lock.record, "unicode_version": UNICODE_VERSION,
                "python": platform.python_version(), "config": cfg, "counts": result, "keyed_sample": keyed_record}
    write_json(ctx.path("documents", ext="manifest.json"), manifest)
    return result
