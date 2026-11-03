"""The features_discourse stage end to end, on a synthetic two-story catalogue over two shards.

The name inventory has to be built across shards (Materials: "a frozen inventory"), so each shard's run reads every
parse shard. The phonemizer is a fake program that prints one phone per letter, and the MEmoLon table is a tiny
synthetic one pinned by its own SHA-256.
"""

import hashlib
import math
import statistics
import sys
import tomllib
from pathlib import Path

import pytest

from intract_features import records
from intract_features.features import names as nam

ROOT = Path(__file__).resolve().parents[2]

FAKE_PHONEMIZER = r'''
import os, sys
args = sys.argv[1:]
if "--version" in args:
    print("phonemizer-3.4.0\navailable backends: espeak-ng-1.52.0")
    sys.exit(0)
out, src = args[args.index("-o") + 1], args[-1]
lines = [" | ".join(" ".join(c for c in t if c.isalpha()) for t in line.split()) for line in open(src, encoding="utf8")]
open(out, "w", encoding="utf8").write(os.linesep.join(lines) + os.linesep)
'''

LEXICON = """word\tvalence\tarousal\tdominance\tjoy\tanger\tsadness\tfear\tdisgust
come\t5.0\t4.0\t5\t2\t1\t1\t1\t1
here\t5.5\t3.0\t5\t2\t1\t1\t1\t1
happy\t8.0\t6.0\t5\t2\t1\t1\t1\t1
sun\t7.0\t5.0\t5\t2\t1\t1\t1\t1
run\t6.0\t7.0\t5\t2\t1\t1\t1\t1
dog\t6.5\t4.5\t5\t2\t1\t1\t1\t1
kind\t7.5\t3.5\t5\t2\t1\t1\t1\t1
Tom\t1.0\t1.0\t5\t2\t1\t1\t1\t1
<UNK>\t4.8\t4.15\t5.03\t1.84\t1.6\t1.55\t1.64\t1.59
"""

PRS3 = "Number=Sing|Person=3|PronType=Prs"
# Story A: dialogue, a name the parser once tags NOUN, a pronoun subject and "because".
STORY_A = (["“Come here, Tom!” said Mia.", "Tom ran. He was happy because the sun was out."], [
    [("“", "“", "PUNCT", 2, "punct"), ("Come", "come", "VERB", 8, "ccomp"), ("here", "here", "ADV", 2, "advmod"),
     (",", ",", "PUNCT", 5, "punct"), ("Tom", "Tom", "PROPN", 2, "vocative"), ("!", "!", "PUNCT", 2, "punct"),
     ("”", "”", "PUNCT", 2, "punct"), ("said", "say", "VERB", 0, "root"), ("Mia", "Mia", "PROPN", 8, "nsubj"),
     (".", ".", "PUNCT", 8, "punct")],
    [("Tom", "Tom", "NOUN", 2, "nsubj"), ("ran", "run", "VERB", 0, "root"), (".", ".", "PUNCT", 2, "punct")],
    [("He", "he", "PRON", 3, "nsubj", PRS3), ("was", "be", "AUX", 3, "cop"), ("happy", "happy", "ADJ", 0, "root"),
     ("because", "because", "SCONJ", 8, "mark"), ("the", "the", "DET", 6, "det"), ("sun", "sun", "NOUN", 8, "nsubj"),
     ("was", "be", "AUX", 8, "cop"), ("out", "out", "ADV", 3, "advcl"), (".", ".", "PUNCT", 3, "punct")]])
# Story B: overlap in every pair, a contrastive "but" coordinating clauses and a clause-initial "So".
STORY_B = (["Mia saw a big dog. The dog was kind, but it was shy.", "So Mia gave the dog a bone."], [
    [("Mia", "Mia", "PROPN", 2, "nsubj"), ("saw", "see", "VERB", 0, "root"), ("a", "a", "DET", 5, "det"),
     ("big", "big", "ADJ", 5, "amod"), ("dog", "dog", "NOUN", 2, "obj"), (".", ".", "PUNCT", 2, "punct")],
    [("The", "the", "DET", 2, "det"), ("dog", "dog", "NOUN", 4, "nsubj"), ("was", "be", "AUX", 4, "cop"),
     ("kind", "kind", "ADJ", 0, "root"), (",", ",", "PUNCT", 9, "punct"), ("but", "but", "CCONJ", 9, "cc"),
     ("it", "it", "PRON", 9, "nsubj", PRS3), ("was", "be", "AUX", 9, "cop"), ("shy", "shy", "ADJ", 4, "conj"),
     (".", ".", "PUNCT", 4, "punct")],
    [("So", "so", "ADV", 3, "advmod"), ("Mia", "Mia", "PROPN", 3, "nsubj"), ("gave", "give", "VERB", 0, "root"),
     ("the", "the", "DET", 5, "det"), ("dog", "dog", "NOUN", 3, "iobj"), ("a", "a", "DET", 7, "det"),
     ("bone", "bone", "NOUN", 3, "obj"), (".", ".", "PUNCT", 3, "punct")]])
SENTENCE_TEXTS = {"A": ["“Come here, Tom!” said Mia.", "Tom ran.", "He was happy because the sun was out."],
                  "B": ["Mia saw a big dog.", "The dog was kind, but it was shy.", "So Mia gave the dog a bone."]}


def _story_ids():
    a = next(f"S{i}" for i in range(200) if records.shard_of(f"S{i}", 2) == 0)
    b = next(f"S{i}" for i in range(200) if records.shard_of(f"S{i}", 2) == 1)
    return {"A": a, "B": b}


def _write_catalogue(work: Path, ids: dict) -> dict:
    from intract_features.parse import ConlluShardWriter, Token, Word, align_tokens, document_units, format_document
    from intract_features.segment import SENTENCE_FIELDS, page_anchors

    docs = {}
    for role, (pages, parses) in (("A", STORY_A), ("B", STORY_B)):
        sid, shard = ids[role], records.shard_of(ids[role], 2)
        doc = records.Document(story_id=sid, lang="en-us", level="young", kind="generated", title="T",
                               pages=tuple(pages))
        text, spans, pos = doc.text, [], 0
        for s in SENTENCE_TEXTS[role]:
            start = text.index(s, pos)
            spans.append((start, start + len(s)))
            pos = start + len(s)
        anchors = page_anchors(doc.page_spans(), spans)
        records.write_jsonl(records.artefact_path(work, "en-us", "documents", shard, 2), [doc.to_json()])
        records.write_jsonl(records.artefact_path(work, "en-us", "segments", shard, 2), [{
            "story_id": sid, "lang": "en-us", "segmenter": "sat", "is_source": True,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "n_characters": len(text),
            "n_sentences": len(spans), "sentence_fields": list(SENTENCE_FIELDS),
            "sentences": [[a, b, p, q] for (a, b), (p, q) in zip(spans, anchors, strict=True)]}])
        units = document_units(doc, spans)
        token_lists = []
        for unit, rows in zip(units, parses, strict=True):
            tokens = [Token(form=r[0], words=[Word(id=i, form=r[0], lemma=r[1], upos=r[2], head=r[3], deprel=r[4],
                                                   feats=r[5] if len(r) > 5 else "_")])
                      for i, r in enumerate(rows, 1)]
            assert align_tokens(unit, tokens, max_skip=4) == 0
            token_lists.append(tokens)
        with ConlluShardWriter(records.artefact_path(work, "en-us", "parses_stanza", shard, 2, "conllu.gz")) as fh:
            fh.write(format_document(sid, units, token_lists, text))
        docs[role] = doc
    return docs


def _config(tmp_path: Path, lexicon: Path) -> dict:
    def toml(p):
        return tomllib.loads(p.read_text(encoding="utf-8"))

    stage = toml(ROOT / "config" / "stages" / "features_discourse.toml")
    script = tmp_path / "fake_phonemize.py"
    script.write_text(FAKE_PHONEMIZER, encoding="utf-8")
    stage["duration"]["command"] = [sys.executable, str(script)]
    pin = hashlib.sha256(lexicon.read_bytes()).hexdigest()
    return {"languages": toml(ROOT / "config" / "languages.toml"), "models": {},
            "resources": {"memolon_mtl_grouped_en": {"sha256": pin}},
            "stages": {"features_discourse": stage,
                       "features_gramlex": toml(ROOT / "config" / "stages" / "features_gramlex.toml")}}


def test_stage_end_to_end_over_two_shards(tmp_path, monkeypatch):
    from intract_features.cli import StageContext
    from intract_features.stages import features_discourse as fd

    res = tmp_path / "res"
    lexicon = res / "memolon" / "MTL_grouped" / "en.tsv"
    lexicon.parent.mkdir(parents=True)
    lexicon.write_text(LEXICON, encoding="utf-8", newline="\n")
    monkeypatch.setenv("INTRACT_RESOURCES", str(res))
    work = tmp_path / "work"
    ids = _story_ids()
    docs = _write_catalogue(work, ids)
    cfg = _config(tmp_path, lexicon)

    out, counts = {}, {}
    for shard in (0, 1):
        ctx = StageContext(stage=fd.STAGE, config=cfg, lang="en-us", work=work, shard=shard, nshards=2)
        counts[shard] = fd.run(ctx)
        for rec in records.read_jsonl(ctx.path("features_discourse")):
            out[rec["story_id"]] = rec
    a, b = out[ids["A"]]["values"], out[ids["B"]]["values"]

    # The catalogue inventory reads both shards: "tom" is a name at exactly half (PROPN once, NOUN once).
    for c in counts.values():
        assert c["parse_shards_read"] == 2 and c["name_inventory_types"] == 2 and c["documents"] == 1
        assert (c["phonemizer_version"], c["espeak_ng_version"], c["affect_pin"]) == ("3.4.0", "1.52.0", "verified")
        assert c["omitted"] == ["additive_density", "temporal_density"]
    inventory = work / "en-us" / "features_discourse" / "name_inventory.txt"
    assert nam.read_inventory(inventory) == {"tom", "mia"}

    # Story A: 15 words, three of them inside the quotation.
    assert a["dialogue_share"] == pytest.approx(3 / 15)
    assert a["referential_overlap"] == 0.5  # Tom links sentences 1 and 2; nothing links 2 and 3
    assert a["anaphoric_continuation"] == 1.0  # "He" opens sentence 3
    assert a["causal_density"] == pytest.approx(100 / 15) and a["contrastive_density"] == 0.0
    assert a["causal_density_without_so"] == pytest.approx(100 / 15)
    assert a["name_token_share"] == pytest.approx(3 / 15)
    assert a["name_token_share_elogit"] == pytest.approx(math.log(3.5 / 12.5))
    assert a["name_types_per_100_words"] == pytest.approx(200 / 15)
    assert a["name_tokens_per_type"] == 1.5
    val = [5.0, 5.5, 6.0, 8.0, 7.0]  # come, here, ran (as run), happy, sun; "Tom" (a name) excluded
    assert a["valence_mean"] == pytest.approx(statistics.fmean(val))
    assert a["valence_sd"] == pytest.approx(statistics.stdev(val))
    assert a["arousal_mean"] == pytest.approx(5.0)
    assert a["valence_mean_with_names"] == pytest.approx(statistics.fmean([*val, 1.0]))
    letters = sum(ch.isalpha() for ch in docs["A"].text)
    seconds = 0.08 * letters + 0.55 * 3 + 0.20 * 1  # three sentences, one comma
    assert a["duration_log_seconds_per_word"] == pytest.approx(math.log(seconds / 15))
    da = out[ids["A"]]["diagnostics"]
    assert (da["affect_content_tokens"], da["affect_matched_tokens"]) == (7, 5)
    assert (da["affect_content_tokens_with_names"], da["affect_matched_tokens_with_names"]) == (8, 6)
    assert (da["phones"], da["sentence_ends"], da["clause_marks"]) == (letters, 3, 1)

    # Story B: 20 words, a contrastive "but" between clauses and a clause-initial "So".
    assert b["dialogue_share"] == 0.0
    assert b["referential_overlap"] == 1.0 and b["anaphoric_continuation"] == 1.0
    assert b["causal_density"] == pytest.approx(5.0) and b["contrastive_density"] == pytest.approx(5.0)
    assert b["causal_density_without_so"] == 0.0
    assert b["name_token_share"] == pytest.approx(0.1) and b["name_tokens_per_type"] == 2.0
    assert b["name_types_per_100_words"] == pytest.approx(5.0)
    assert b["valence_mean"] == pytest.approx(6.75) and b["arousal_mean"] == pytest.approx(4.25)
    assert b["valence_mean"] == b["valence_mean_with_names"]
    assert out[ids["B"]]["diagnostics"]["sentences_contrastive"] == [1]


def test_stage_refuses_unsupported_languages():
    from intract_features.stages import features_discourse as fd

    stage = tomllib.loads((ROOT / "config" / "stages" / "features_discourse.toml").read_text(encoding="utf-8"))
    with pytest.raises(NotImplementedError):
        fd._check_language(stage, {"iso": "fr", "spaced": True})
    with pytest.raises(ValueError, match="G4"):
        fd._check_language({**stage, "connectives": {**stage["connectives"], "additive_temporal": True}},
                           {"iso": "en", "spaced": True})
