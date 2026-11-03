"""Tests of the English-source references: CorPipe's input and output, the MetricX port, the aligner and their stages.

Everything runs on hand-built fixtures, the public example of the CorPipe README and public FLORES-200 sentences; no
story text is read. Tests that need torch, transformers, tokenizers, minnt or numpy skip where those are missing (the
shared development environment has none of them); with them, tiny models built here stand in for the pinned ones.

The MetricX port is checked against the official code without circularity: TINY_CASES holds token ids from
transformers 4.30.2's tokeniser and scores from the official `python -m metricx24.predict ... --qe` (google-research/
metricx at fc4978eb, Python 3.11.5, torch 2.5.1), run on a tiny checkpoint built by the official MT5ForRegression with
the integer-valued weights of tiny_weights() below, which every torch release builds bit for bit alike.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pickle
import re
import sys
import tomllib
import zlib
from pathlib import Path

import pytest

from intract_features import cli, records
from intract_features import parse as P
from intract_features.lock import CatalogueLocked, fingerprint
from intract_features.reference import (
    PinError,
    TorchRuntime,
    hf_cache_ref,
    hf_snapshot_dir,
    pin_files,
    pinned_folder,
    verify_pinned_files,
)
from intract_features.reference import align as AL
from intract_features.reference import corpipe_run as cr
from intract_features.reference import metricx_qe as mq
from intract_features.stages import coref_corpipe as coref_stage
from intract_features.stages import qe_metricx as qe_stage

STAGES = Path(__file__).resolve().parents[2] / "config" / "stages"
COREF_CFG = tomllib.loads((STAGES / "coref_corpipe.toml").read_text(encoding="utf-8"))
QE_CFG = tomllib.loads((STAGES / "qe_metricx.toml").read_text(encoding="utf-8"))

# The CorPipe README's example, with its two sentences at [0, 45) and [46, 108).
README_TEXT = ("Susan came home and Martin greeted her there. "
               "Then Martin and Paul left for a trip and Susan waved them off.")
README_SPANS = [(0, 45), (46, len(README_TEXT))]
TOKEN_RE = re.compile(r"[\w']+|[^\w\s]")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tokens_of(text: str, start: int = 0, mwt: dict | None = None) -> list[P.Token]:
    """Tokens with offsets; `mwt` maps a token's form to the forms of its syntactic words."""
    toks, wid = [], 1
    for m in TOKEN_RE.finditer(text):
        forms = (mwt or {}).get(m.group(), [m.group()])
        words = [P.Word(id=wid + j, form=f, head=0, deprel="dep") for j, f in enumerate(forms)]
        wid += len(forms)
        toks.append(P.Token(form=m.group(), words=words, start=start + m.start(), end=start + m.end()))
    return toks


def parsed(story_id: str, text: str, spans, mwt: dict | None = None, empty=()) -> P.ConlluDocument:
    sents = []
    for k, (a, b) in enumerate(spans):
        toks = [] if k in empty else tokens_of(text[a:b], a, mwt)
        sents.append(P.ConlluSentence(sent_id=f"{story_id}-{k}", k=k, text=text[a:b], span=(a, b), tokens=toks,
                                      empty=k in empty))
    return P.ConlluDocument(story_id=story_id, sentences=sents)


def out_lines(sentences, header: bool = True) -> list[str]:
    """CorPipe output lines: each sentence is (k, rows), each row (id, form, misc, deps)."""
    lines = ["# newdoc id = doc"] + (["# global.Entity = eid-etype-head-other"] if header else [])
    for k, rows in sentences:
        lines.append(f"# sent_id = {k}")
        for tid, form, misc, deps in rows:
            empty = "." in tid
            lines.append("\t".join([tid, form, "_", "_", "_", "_", "_" if empty else "0", "_" if empty else "dep",
                                    deps, misc]))
        lines.append("")
    return [line + "\n" for line in lines]


def word_rows(text: str, misc: dict) -> list[tuple[str, str, str, str]]:
    return [(str(i), f, misc.get(i, "_"), "_") for i, f in enumerate(TOKEN_RE.findall(text), 1)]


# The README's predicted entities (corpipe26-onestage-corefud1.4-large), sentence ids replaced by our indices.
README_OUTPUT = out_lines([
    (0, word_rows(README_TEXT[0:45], {1: "Entity=(c1--1)", 3: "Entity=(c2--1)", 5: "Entity=(c3--1)",
                                      7: "Entity=(c1--1)", 8: "Entity=(c2--1)|SpaceAfter=No"})),
    (1, word_rows(README_TEXT[46:], {2: "Entity=(c4--1(c3--1)", 4: "Entity=(c5--1)c4)", 10: "Entity=(c1--1)",
                                     12: "Entity=(c4--1)", 13: "SpaceAfter=No"})),
])


def fake_count(form: str) -> int:
    """A stand-in for the script's tokeniser: no subword for white space only, else one per four characters."""
    return 0 if not form.strip() else 1 + len(form) // 4


# ------------------------------------------------------------------------------------------- shared helpers


def test_pin_files_accepts_the_lock_shapes():
    assert pin_files({"files": {"a": "1"}}) == [("a", "1")]
    assert pin_files({"files": {"a": {"sha256": "2"}}}) == [("a", "2")]
    assert pin_files({"files": [{"path": "b", "sha256": "3"}]}) == [("b", "3")]
    with pytest.raises(PinError):
        pin_files({"repo": "x"})


def test_verify_pinned_files_names_every_bad_file(tmp_path):
    (tmp_path / "good.txt").write_bytes(b"good")
    (tmp_path / "bad.txt").write_bytes(b"bad")
    entry = {"files": {"good.txt": sha(b"good"), "bad.txt": sha(b"other"), "gone.txt": sha(b"x")}}
    with pytest.raises(PinError) as e:
        verify_pinned_files(tmp_path, entry, what="the test files")
    assert "bad.txt has SHA-256" in str(e.value) and "gone.txt is missing" in str(e.value)
    ok = verify_pinned_files(tmp_path, {"files": {"good.txt": sha(b"good")}}, what="x")
    assert ok == [{"file": "good.txt", "sha256": sha(b"good"), "bytes": 4}]


def test_hub_cache_layout_and_refs(tmp_path):
    env = {"HF_HUB_CACHE": str(tmp_path / "hub")}
    assert hf_snapshot_dir("org/m", "abc", env) == tmp_path / "hub" / "models--org--m" / "snapshots" / "abc"
    assert hf_snapshot_dir("org/m", "abc", {"HF_HOME": str(tmp_path)}) == hf_snapshot_dir("org/m", "abc", env)
    assert hf_cache_ref("org/m", "main", env) is None
    ref = tmp_path / "hub" / "models--org--m" / "refs" / "main"
    ref.parent.mkdir(parents=True)
    ref.write_text("abc\n")
    assert hf_cache_ref("org/m", "main", env) == "abc"


def test_pinned_folder_prefers_path_then_environment_then_cache(tmp_path):
    entry = {"repo": "org/m", "revision": "r1"}
    env = {"HF_HUB_CACHE": str(tmp_path), "MODEL_DIR": str(tmp_path / "env")}
    assert pinned_folder({**entry, "path": "/explicit"}, env_name="MODEL_DIR", environ=env) == Path("/explicit")
    assert pinned_folder(entry, env_name="MODEL_DIR", environ=env) == tmp_path / "env"
    assert pinned_folder(entry, env_name="UNSET", environ=env) == hf_snapshot_dir("org/m", "r1", env)
    with pytest.raises(PinError):
        pinned_folder({"repo": "org/m"}, env_name="UNSET", environ=env)


def test_torch_runtime_reads_and_checks_its_table():
    rt = TorchRuntime.from_config(COREF_CFG["runtime"])
    assert rt.dtype == "float32" and rt.allow_tf32 is False and rt.deterministic_algorithms
    env = rt.environment()
    assert env["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8" and env["HF_HUB_OFFLINE"] == "1"
    with pytest.raises(ValueError):
        TorchRuntime.from_config({"dtype": "float16"})
    with pytest.raises(ValueError):
        TorchRuntime.from_config({"device": "tpu"})


# ------------------------------------------------------------------------------------------ CorPipe: input


def test_input_conllu_keeps_ids_and_mwt_and_skips_empty_parses():
    text = "Tom ran. Nothing. Sam don't stop."
    doc = parsed("S1", text, [(0, 8), (9, 17), (18, 33)], mwt={"don't": ["do", "n't"]}, empty={1})
    made = cr.input_conllu(doc)
    assert made.written == [0, 2] and made.refused == [] and made.replaced == []
    lines = made.text.splitlines()
    assert lines[:3] == ["# newdoc id = doc", "# sent_id = 0", "# text = Tom ran."]
    assert "1\tTom\t_\t_\t_\t_\t0\tdep\t_\t_" in lines
    assert "2-3\tdon't\t_\t_\t_\t_\t_\t_\t_\t_" in lines and "3\tn't\t_\t_\t_\t_\t0\tdep\t_\t_" in lines
    assert "# sent_id = 1" not in lines and made.text.endswith("\n\n")
    assert all(len(line.split("\t")) == 10 for line in lines if line and not line.startswith("#"))
    assert made.forms[2] == [(1, "Sam"), (2, "do"), (3, "n't"), (4, "stop"), (5, ".")]


def _odd_doc() -> P.ConlluDocument:
    """Sentence 0 holds a no-break space as a word, sentence 1 is long, sentence 2 is ordinary."""
    toks = [P.Token(form=f, words=[P.Word(id=i, form=f, head=0, deprel="dep")], start=None, end=None)
            for i, f in enumerate(["Then", "\xa0", "Tom", "ran", "."], 1)]
    long = [P.Token(form="w" * 40, words=[P.Word(id=i, form="w" * 40, head=0, deprel="dep")]) for i in range(1, 6)]
    short = [P.Token(form="Ok", words=[P.Word(id=1, form="Ok", head=0, deprel="dep")])]
    return P.ConlluDocument(story_id="S", sentences=[
        P.ConlluSentence(sent_id="S-0", k=0, text="Then \xa0 Tom ran.", span=None, tokens=toks),
        P.ConlluSentence(sent_id="S-1", k=1, text="long", span=None, tokens=long),
        P.ConlluSentence(sent_id="S-2", k=2, text="Ok", span=None, tokens=short)])


def test_input_guard_replaces_forms_of_no_subword_and_refuses_long_sentences():
    made = cr.input_conllu(_odd_doc(), fake_count, limit=20, placeholder="_")
    assert made.written == [0, 2] and made.refused == [1] and made.replaced == [(0, 2)]
    assert "2\t_\t_\t_\t_\t_\t0\tdep\t_\t_" in made.text.splitlines()
    assert made.forms[0][1] == (2, "_") and made.subwords == sum(fake_count(f) for _, f in made.forms[0]) + 1
    unguarded = cr.input_conllu(_odd_doc())
    assert unguarded.written == [0, 1, 2] and "\xa0" in unguarded.text


def test_cell_breaks_lines_and_tabs_with_escaped_separators():
    assert cr._cell("a\N{LINE SEPARATOR}b\N{PARAGRAPH SEPARATOR}c\td\re\nf\x85g") == "a b c d e f g"
    assert cr._cell("") == "_" and cr._cell(None) == "_"
    assert "\N{LINE SEPARATOR}" not in Path(cr.__file__).read_text(encoding="utf-8")


def test_write_inputs_writes_one_file_per_document_with_a_sentence(tmp_path):
    doc = parsed("S1", README_TEXT, README_SPANS)
    empty = parsed("S2", "Oops.", [(0, 5)], empty={0})
    # fake_count gives the README's sentences 15 and 22 subwords, and _odd_doc's long sentence 55.
    files, report = cr.write_inputs([("S1", doc), ("S2", empty), ("S3", None), ("S4", _odd_doc())], tmp_path,
                                    fake_count, limit=30)
    assert report.skipped == 2 and [f.story_id for f in files] == ["S1", "S4"]
    assert files[0].path.name == "d0000000.conllu" and files[0].output_name == "d0000000.00.conllu"
    assert files[0].written == [0, 1] and files[1].index == 3 and files[1].written == [0, 2]
    assert report.refused == {3: [1]} and report.replaced == {3: [(0, 2)]}


def test_write_inputs_refuses_a_folder_that_shrinks_the_segment(tmp_path):
    with pytest.raises(ValueError, match="proiel"):
        cr.write_inputs([], tmp_path / "my-PROIEL-run")


def test_corpipe_args_follow_the_readme(tmp_path):
    s = cr.CorpipeSettings(segment=2560, batch_size=0, threads=4)
    args = cr.corpipe_args(Path("m"), Path("o"), [Path("a.conllu"), Path("b.conllu")], s)
    assert args == ["--load", "m", "--exp", "o", "--epochs", "0", "--segment", "2560", "--threads", "4",
                    "--test", "a.conllu", "b.conllu"]
    assert "--segment" not in cr.corpipe_args(Path("m"), Path("o"), [], cr.CorpipeSettings(segment=0))


def test_corpipe_settings_from_the_config_file():
    s = cr.CorpipeSettings.from_config(COREF_CFG)
    assert s.input_parse == "parses_stanza" and s.segment == 2560 and not s.zero_mentions_in_continuity
    assert s.empty_form_placeholder == "_"
    with pytest.raises(ValueError):
        cr.CorpipeSettings.from_config({**COREF_CFG, "input": {**COREF_CFG["input"], "parse": "parses_other"}})
    with pytest.raises(ValueError):
        cr.CorpipeSettings.from_config({**COREF_CFG, "input": {**COREF_CFG["input"], "empty_form_placeholder": " "}})


def test_script_tokenizer_names_follow_the_script():
    assert cr.script_tokenizer_name("google/umt5-xl") == "google/umt5-xl"
    assert cr.script_tokenizer_name("google/mt5-large") == "google/mt5-xl"
    assert cr.script_tokenizer_name("/tmp/tiny-umt5") == "google/umt5-xl"
    assert cr.script_tokenizer_name("xlm-roberta-large") == "xlm-roberta-large"


# ----------------------------------------------------------------------------------------- CorPipe: output


@pytest.mark.parametrize("value, chunks", [
    ("(e1-person(e2-place)", ["(e1-person", "(e2-place)"]),
    ("e1)(e2", ["e1)", "(e2"]),
    ("(c5--1)c4)", ["(c5--1)", "c4)"]),
    ("(e10)(e9)e4)e3)", ["(e10)", "(e9)", "e4)", "e3)"]),
    ("(e2[2/2])e1)", ["(e2[2/2])", "e1)"]),
])
def test_entity_chunks_split_as_udapi_does(value, chunks):
    assert cr.entity_chunks(value) == chunks


def test_read_output_reads_nodes_fields_and_empty_nodes():
    lines = out_lines([(0, [("1", "Tom", "Entity=(c1--1)", "_"), ("1.1", "_", "Entity=(c1--1)", "1:nsubj"),
                            ("2", "ran", "SpaceAfter=No", "_"), ("3", ".", "_", "_")])], header=False)
    lines.insert(1, "# global.Entity = eid-head\n")
    (sent,), fields = cr.read_output(lines)
    assert fields == ("eid", "head") and sent.sent_id == "0"
    assert [n.ord for n in sent.nodes] == [(1, 0), (1, 1), (2, 0), (3, 0)]
    assert [n.word for n in sent.nodes] == [1, None, 2, 3] and sent.nodes[1].deps == "1:nsubj"
    assert [n.entity for n in sent.nodes] == ["(c1--1)", "(c1--1)", "", ""]
    with pytest.raises(ValueError):
        cr.read_output(["1\tTom\t_\n"])


def test_sentence_mentions_nest_and_close_last_in_first_out():
    rows = [("1", "a", "Entity=(c6--1(c6--2", "_"), ("2", "b", "Entity=c6)", "_"), ("3", "c", "Entity=c6)", "_")]
    (sent,), fields = cr.read_output(out_lines([(0, rows)]))
    mentions, unclosed = cr.sentence_mentions(sent, fields)
    assert unclosed == 0
    assert mentions == [cr.RawMention("c6", 0, 1, 2), cr.RawMention("c6", 0, 2, 1)]


def test_sentence_mentions_count_unclosed_and_refuse_unopened():
    (sent,), fields = cr.read_output(out_lines([(0, [("1", "a", "Entity=(c1--1", "_"), ("2", "b", "_", "_")])]))
    assert cr.sentence_mentions(sent, fields) == ([], 1)
    (sent,), fields = cr.read_output(out_lines([(0, [("1", "a", "Entity=c9)", "_")])]))
    with pytest.raises(ValueError):
        cr.sentence_mentions(sent, fields)


def test_sentence_mentions_flag_discontinuous_subspans():
    rows = [("1", "a", "Entity=(e2[1/2]--1)", "_"), ("2", "b", "_", "_"), ("3", "c", "Entity=(e2[2/2]--1)", "_")]
    (sent,), fields = cr.read_output(out_lines([(0, rows)]))
    mentions, _ = cr.sentence_mentions(sent, fields)
    assert [(m.eid, m.first, m.last, m.subspan) for m in mentions] == [("e2", 0, 0, True), ("e2", 2, 2, True)]


def test_document_chains_on_the_readme_example():
    doc = parsed("S1", README_TEXT, README_SPANS)
    out, fields = cr.read_output(README_OUTPUT)
    res = cr.document_chains("S1", doc, [0, 1], out, fields, zero_in_continuity=False)
    texts = [[README_TEXT[m["start"]:m["end"]] for m in c["mentions"]] for c in res["chains"]]
    assert texts == [["Susan", "her", "Susan"], ["home", "there"], ["Martin", "Martin"], ["Martin and Paul", "them"],
                     ["Paul"]]
    first = res["chains"][0]["mentions"][0]
    assert first == {"k": 0, "start": 0, "end": 5, "words": [1, 1], "head": 1}
    assert res["chains"][3]["mentions"][0]["words"] == [2, 4] and res["chains"][3]["mentions"][0]["head"] == 2
    assert res["pair_continuity"] == [1]
    d = res["diagnostics"]
    assert (d["mentions"], d["chains"], d["singletons"], d["zero_mentions"]) == (10, 5, 1, 0)
    assert d["syntactic_words_sent"] == 23 and d["characters_sent"] == len(README_TEXT) - 1
    assert d["pairs_with_data"] == 1 and d["pair_continuity_share"] == 1.0
    assert all(c["zero"] == [] for c in res["chains"])


def test_document_chains_with_empty_nodes_from_the_official_script():
    # Rows written by corpipe26_onestage.py with a randomly initialised model on the README's first sentence.
    rows = [("1", "Susan", "Entity=(c1--1(c2--1(c3--1(c4--1", "_"), ("1.1", "_", "Entity=(c5--1)", "1:obl:arg:dat"),
            ("1.2", "_", "Entity=(c6--1)", "1:obl:agent:ins"), ("2", "came", "Entity=c4)", "_"),
            ("2.1", "_", "Entity=(c6--1)", "2:root"), ("3", "home", "Entity=c3)", "_"),
            ("3.1", "_", "Entity=(c6--1)", "3:obl:agent:ins"), ("4", "and", "Entity=c2)", "_"),
            ("5", "Martin", "Entity=c1)", "_"), ("6", "greeted", "Entity=(c6--1", "_"), ("7", "her", "Entity=c6)", "_"),
            ("8", "there", "Entity=(c6--1", "_"), ("9", ".", "Entity=c6)", "_")]
    doc = parsed("S1", README_TEXT, README_SPANS)
    out, fields = cr.read_output(out_lines([(0, rows)]))
    res = cr.document_chains("S1", doc, [0], out, fields, zero_in_continuity=False)
    chains = res["chains"]
    assert len(chains) == 6
    assert chains[0]["mentions"] == [{"k": 0, "start": 0, "end": 26, "words": [1, 5], "head": 1, "empty_nodes": 4}]
    assert [README_TEXT[m["start"]:m["end"]] for m in chains[5]["mentions"]] == ["greeted her", "there."]
    assert chains[4]["zero"] == [{"k": 0, "parent": 1, "deprel": "obl:arg:dat", "start": 0, "end": 5}]
    assert [z["parent"] for z in chains[5]["zero"]] == [1, 2, 3]
    d = res["diagnostics"]
    assert (d["mentions"], d["zero_mentions"], d["mentions_with_empty_nodes"]) == (6, 4, 4)
    # Sentence 1 was not sent, so nothing is known about the pair: null, not 0.
    assert res["pair_continuity"] == [None] and d["pairs_with_data"] == 0 and d["pair_continuity_share"] is None


def test_document_chains_map_a_multiword_token_word_to_its_token():
    text = "Sam don't stop."
    doc = parsed("S1", text, [(0, len(text))], mwt={"don't": ["do", "n't"]})
    rows = [("1", "Sam", "_", "_"), ("2", "do", "_", "_"), ("3", "n't", "Entity=(c1--1)", "_"), ("4", "stop", "_", "_"),
            ("5", ".", "_", "_")]
    out, fields = cr.read_output(out_lines([(0, rows)]))
    res = cr.document_chains("S1", doc, [0], out, fields, zero_in_continuity=False)
    m = res["chains"][0]["mentions"][0]
    assert text[m["start"]:m["end"]] == "don't" and m["words"] == [3, 3]


def test_document_chains_check_the_forms_written_with_placeholders():
    doc = _odd_doc()
    made = cr.input_conllu(doc, fake_count, limit=20)
    rows0 = [(str(i), f, "Entity=(c1--1)" if f == "Tom" else "_", "_") for i, f in made.forms[0]]
    rows2 = [("1", "Ok", "Entity=(c1--1)", "_")]
    out, fields = cr.read_output(out_lines([(0, rows0), (2, rows2)]))
    res = cr.document_chains("S", doc, made.written, out, fields, zero_in_continuity=False, forms=made.forms)
    assert res["pair_continuity"] == [None, None] and res["diagnostics"]["sentences_sent"] == 2
    with pytest.raises(ValueError, match="differ from those sent"):  # without the forms, the placeholder mismatches
        cr.document_chains("S", doc, made.written, out, fields, zero_in_continuity=False)


def test_zero_mentions_count_towards_continuity_only_when_switched_on():
    text = "Tom ran. He fell."
    doc = parsed("S1", text, [(0, 8), (9, 17)])
    out, fields = cr.read_output(out_lines([
        (0, [("1", "Tom", "Entity=(c1--1)", "_"), ("2", "ran", "_", "_"), ("3", ".", "_", "_")]),
        (1, [("1", "He", "_", "_"), ("1.1", "_", "Entity=(c1--1)", "1:nsubj"), ("2", "fell", "_", "_"),
             ("3", ".", "_", "_")])]))
    off = cr.document_chains("S1", doc, [0, 1], out, fields, zero_in_continuity=False)
    on = cr.document_chains("S1", doc, [0, 1], out, fields, zero_in_continuity=True)
    assert off["pair_continuity"] == [0] and on["pair_continuity"] == [1]
    assert off["chains"][0]["zero"][0]["start"] == 9


def test_document_chains_refuse_mismatched_output():
    doc = parsed("S1", README_TEXT, README_SPANS)
    out, fields = cr.read_output(README_OUTPUT)
    with pytest.raises(ValueError):
        cr.document_chains("S1", doc, [0], out, fields, zero_in_continuity=False)  # two sentences for one
    other = parsed("S1", README_TEXT.replace("came", "went"), README_SPANS)
    out2, _ = cr.read_output(out_lines([(0, word_rows("Susan came home.", {}))]))
    with pytest.raises(ValueError):
        cr.document_chains("S1", other, [0], out2, fields, zero_in_continuity=False)
    empty = cr.document_chains("S3", None, [], [], fields, zero_in_continuity=False)
    assert empty["chains"] == [] and empty["pair_continuity"] == [] and empty["diagnostics"]["sentences"] == 0


# --------------------------------------------------------------------------------------- CorPipe: cost


def test_read_cache_reads_the_scripts_tokenised_documents(tmp_path):
    path = tmp_path / "d0000000.conllu"
    path.write_text("x")
    assert cr.read_cache(path) is None
    docs = [[(list(range(10)), [], [], [], [])]]
    with open(tmp_path / "d0000000.conllu.mentions1.umt5-xl", "wb") as fh:
        pickle.dump(docs, fh, protocol=3)
    assert cr.read_cache(path) == docs


def test_encoder_cost_rebuilds_the_scripts_segments():
    doc = [(list(range(10)),), (list(range(15)),)]
    # Sentence 0: [CLS] + no context + [SEP] + 10 + [SEP] + 15 of right context + [SEP] = 29 positions.
    # Sentence 1: [CLS] + 10 of left context + [SEP] + 15 + [SEP] + [SEP] = 29 positions; one batch of two.
    assert cr.encoder_cost([doc], 2560, 50, 8) == {"tokens": 25, "encoder_positions": 58, "padded_positions": 58,
                                                   "truncated_sentences": 0}
    # Segment 16: sentence 0 (10 subwords) takes 2 of sentence 1's subwords as right context and fills the segment;
    # sentence 1 (15 > 16 - 4 subwords) is one the script would cut to 12, which fills it too.
    small = cr.encoder_cost([doc], 16, 50, 1)
    assert small["truncated_sentences"] == 1 and small["encoder_positions"] == 16 + 16
    assert small["padded_positions"] == small["encoder_positions"]
    no_right = cr.encoder_cost([doc], 2560, None, 8)
    assert no_right["encoder_positions"] == (13 + 1) + (3 + 10 + 15 + 1)


# ----------------------------------------------------------------------------------------- CorPipe: launch


def test_corpipe_environment_keeps_tf32_off_and_names_the_device():
    env = cr.corpipe_environment(TorchRuntime(device="cuda"))
    assert env["MINNT_ALLOW_TF32"] == "0" and env["MINNT_DEVICE"] == "cuda" and env["TRANSFORMERS_OFFLINE"] == "1"
    assert "MINNT_DEVICE" not in cr.corpipe_environment(TorchRuntime(device="auto"))
    assert cr.corpipe_environment(TorchRuntime(allow_tf32=True))["MINNT_ALLOW_TF32"] == "1"


def test_run_script_passes_argv_restores_it_and_reports_failure(tmp_path):
    script = tmp_path / "fake.py"
    script.write_text("import json, sys\njson.dump(sys.argv[1:], open(sys.argv[-1], 'w'))\n"
                      "sys.exit(int(sys.argv[1]))\n", encoding="utf-8")
    before, path_before = sys.argv[:], sys.path[:]
    out = tmp_path / "argv.json"
    cr.run_script(script, ["0", str(out)])
    assert json.loads(out.read_text()) == ["0", str(out)] and sys.argv == before and sys.path == path_before
    with pytest.raises(RuntimeError, match="exited with status 3"):
        cr.run_script(script, ["3", str(out)])
    assert sys.argv == before


def test_patched_environ_restores_values(monkeypatch):
    monkeypatch.setenv("INTRACT_TEST_A", "old")
    monkeypatch.delenv("INTRACT_TEST_B", raising=False)
    with cr.patched_environ({"INTRACT_TEST_A": "new", "INTRACT_TEST_B": "set"}):
        assert os.environ["INTRACT_TEST_A"] == "new" and os.environ["INTRACT_TEST_B"] == "set"
    assert os.environ["INTRACT_TEST_A"] == "old" and "INTRACT_TEST_B" not in os.environ


# A stand-in for corpipe26_onestage.py's shape: a minnt model with an `_encoder` whose output carries
# last_hidden_state, heads after it, weights loaded with load_weights, and .numpy(force=True) on a head's output
# (Model.predict). It also emulates minnt.startup()'s TF32 switch.
FAKE_SCRIPT = """
import json, os, sys, types
import minnt, torch

torch.backends.cuda.matmul.allow_tf32 = os.environ.get("MINNT_ALLOW_TF32") == "1"

class Encoder(torch.nn.Module):  # token ids in, as umT5 takes them
    def __init__(self):
        super().__init__()
        self.emb = torch.nn.Embedding(10, 4)
        self.lin = torch.nn.Linear(4, 4)
    def forward(self, ids):
        return types.SimpleNamespace(last_hidden_state=self.lin(self.emb(ids)))

class Model(minnt.TrainableModule):
    def __init__(self):
        super().__init__()
        self._encoder = Encoder()
        self._head = torch.nn.Linear(4, 2)

out = sys.argv[-1]
torch.manual_seed(0)
Model().save_weights(out + ".pt")
model = Model()
if "--load" in sys.argv:
    model.load_weights(out + ".pt")
hidden = model._encoder(torch.tensor([[1, 2, 3]])).last_hidden_state
scores = model._head(hidden)
json.dump({"encoder": str(model._encoder.lin.weight.dtype), "hidden": str(hidden.dtype), "head": str(scores.dtype),
           "numpy": scores.numpy(force=True).dtype.name, "device": os.environ.get("MINNT_DEVICE"),
           "tf32": os.environ.get("MINNT_ALLOW_TF32")}, open(out, "w"))
"""


def test_launch_runs_bf16_with_a_float32_head_and_stops_runs_it_cannot_trust(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    minnt = pytest.importorskip("minnt")
    for key in ("CUBLAS_WORKSPACE_CONFIG", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    script = tmp_path / "fake_corpipe.py"
    script.write_text(FAKE_SCRIPT, encoding="utf-8")
    out = tmp_path / "seen.json"
    original = minnt.TrainableModule.load_weights
    try:
        rec = cr.launch(script, ["--load", str(out)], TorchRuntime(device="cpu"))
        seen = json.loads(out.read_text())
        assert seen == {"encoder": "torch.float32", "hidden": "torch.float32", "head": "torch.float32",
                        "numpy": "float32", "device": "cpu", "tf32": "0"}
        assert rec["allow_tf32_after_run"] is False and rec["minnt_allow_tf32"] == "0" and rec["weight_loads"] == 1
        assert rec["setup_seconds"] >= 0 and rec["predict_seconds"] >= 0 and "MINNT_ALLOW_TF32" not in os.environ
        half = cr.launch(script, ["--load", str(out)], TorchRuntime(device="cpu", dtype="bfloat16"))
        seen = json.loads(out.read_text())
        # The encoder runs in bf16; its states reach the head in float32, so the scores stay 32-bit and survive
        # .numpy(), which a bfloat16 tensor would not.
        assert (seen["encoder"], seen["hidden"], seen["head"], seen["numpy"]) == (
            "torch.bfloat16", "torch.float32", "torch.float32", "float32")
        assert half["bf16_parameters"] == 40 + 20 and half["float32_parameters"] == 10
        with pytest.raises(RuntimeError, match="loaded weights 0 times"):
            cr.launch(script, [str(out)], TorchRuntime(device="cpu", dtype="bfloat16"))
        rogue = tmp_path / "rogue.py"
        rogue.write_text("import torch\ntorch.backends.cuda.matmul.allow_tf32 = True\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="TF32"):
            cr.launch(rogue, [], TorchRuntime(device="cpu"))
    finally:
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.use_deterministic_algorithms(False)
    assert minnt.TrainableModule.load_weights is original


# ----------------------------------------------------------------------------------- coref_corpipe stage


def _document(story_id: str, pages: tuple[str, ...]) -> records.Document:
    return records.Document(story_id=story_id, lang="en-us", level="young", kind="generated", title="T", pages=pages)


def _write_corpipe_inputs(work: Path) -> list[records.Document]:
    """documents and parses_stanza artefacts: parsed, parsed with no sentence, unparsed, and one with odd forms."""
    s1 = _document("S1", (README_TEXT[:45], README_TEXT[46:]))
    s2 = _document("S2", ("Oops.", "Nope, again."))
    s3 = _document("S3", ("",))
    s4 = _document("S4", ("Then \xa0 Tom ran.", "LONG Ok."))
    docs = [s1, s2, s3, s4]
    records.write_jsonl(records.artefact_path(work, "en-us", "documents", 0, 1), [d.to_json() for d in docs])
    text = ""
    units = P.document_units(s1, README_SPANS)
    text += P.format_document("S1", units, [tokens_of(u.text, u.start) for u in units], s1.text)
    units2 = P.document_units(s2, [(0, 5), (6, 18)])
    text += P.format_document("S2", units2, [None, None], s2.text)
    units4 = P.document_units(s4, [(0, 15), (16, 20), (21, 24)])
    toks4 = [[P.Token(form=f, words=[P.Word(id=i, form=f, head=0, deprel="dep")], start=a, end=a + len(f))
              for i, (f, a) in enumerate([("Then", 0), ("\xa0", 5), ("Tom", 7), ("ran", 11), (".", 14)], 1)],
             [P.Token(form="LONG", words=[P.Word(id=1, form="LONG", head=0, deprel="dep")], start=16, end=20)],
             tokens_of(s4.text[21:24], 21)]
    text += P.format_document("S4", units4, toks4, s4.text)
    with P.ConlluShardWriter(records.artefact_path(work, "en-us", "parses_stanza", 0, 1, "conllu.gz")) as fh:
        fh.write(text)
    return docs


def stage_count(form: str) -> int:
    """fake_count, with a form "LONG" too long for any segment."""
    return 10_000 if form == "LONG" else fake_count(form)


def _fake_launch(names: dict[str, str]):
    """A stand-in for the official script: single-word mentions on the given names, and a tokenised cache."""
    calls = []

    def launch(script, args, runtime):
        out_dir = Path(args[args.index("--exp") + 1])
        inputs = [Path(a) for a in args[args.index("--test") + 1:]]
        out_dir.mkdir(parents=True, exist_ok=True)
        calls.append({"script": script, "args": list(args), "runtime": runtime})
        for path in inputs:
            lines, cache = [], []
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("# newdoc"):
                    lines += [line, "# global.Entity = eid-etype-head-other"]
                    continue
                cols = line.split("\t")
                if len(cols) == 10 and cols[0].isdigit():
                    if cols[0] == "1":
                        cache.append([])
                    cache[-1].append(cols[1])
                    if cols[1] in names:
                        cols[9] = f"Entity=({names[cols[1]]}--1)"
                    line = "\t".join(cols)
                lines.append(line)
            (out_dir / (path.stem + cr.OUTPUT_SUFFIX)).write_text("\n".join(lines) + "\n", encoding="utf-8")
            with open(path.parent / (path.name + ".mentions1.umt5-xl"), "wb") as fh:
                pickle.dump([[(list(range(len(words) + 1)), [], [], [], []) for words in cache]], fh, protocol=3)
        return {"fake": True, "setup_seconds": 1.0, "predict_seconds": 2.0}

    return launch, calls


def _stub_stage(monkeypatch, tmp_path, launch):
    monkeypatch.setattr(cr, "launch", launch)
    monkeypatch.setattr(coref_stage, "check_versions", lambda wanted: {"checked": True})
    monkeypatch.setattr(coref_stage, "verify_pins", lambda config, scfg: coref_stage.Pinned(
        script=tmp_path / "corpipe26_onestage.py", model_dir=tmp_path / "model", options={"segment": 512},
        record={"pins": "verified", "variant": "xl"}, encoder="google/umt5-xl"))
    monkeypatch.setattr(coref_stage, "load_counter", lambda encoder, runtime: stage_count)


def test_coref_stage_end_to_end_with_a_fake_corpipe(tmp_path, monkeypatch):
    work = tmp_path / "work"
    docs = _write_corpipe_inputs(work)
    launch, calls = _fake_launch({"Susan": "c7", "Martin": "c3", "Paul": "c9", "Tom": "c2", "Ok": "c2"})
    _stub_stage(monkeypatch, tmp_path, launch)
    ctx = cli.StageContext(stage=coref_stage.STAGE, config={"stages": {"coref_corpipe": COREF_CFG}}, lang="en-us",
                           work=work)
    counts = cli.run_stage(coref_stage, ctx)["counts"]
    assert len(calls) == 1 and "--segment" in calls[0]["args"] and calls[0]["runtime"].allow_tf32 is False
    assert [Path(a).name for a in calls[0]["args"][calls[0]["args"].index("--test") + 1:]] == [
        "d0000000.conllu", "d0000003.conllu"]
    out = {r["story_id"]: r for r in records.read_jsonl(ctx.path("coref_corpipe"))}
    assert list(out) == ["S1", "S2", "S3", "S4"]
    s1 = out["S1"]
    texts = [[README_TEXT[m["start"]:m["end"]] for m in c["mentions"]] for c in s1["chains"]]
    assert texts == [["Susan", "Susan"], ["Martin", "Martin"], ["Paul"]]
    assert [c["entity"] for c in s1["chains"]] == [1, 2, 3] and s1["pair_continuity"] == [1]
    assert s1["values"] == {} and s1["diagnostics"]["subword_tokens"] == 25
    assert s1["diagnostics"]["encoder_positions"] == 58
    assert out["S2"]["chains"] == [] and out["S2"]["pair_continuity"] == [None]
    assert out["S3"]["diagnostics"]["sentences"] == 0
    s4 = out["S4"]  # the no-break space went in as "_", the long sentence was left out: both its pairs are null
    assert s4["diagnostics"]["forms_replaced"] == 1 and s4["diagnostics"]["sentences_refused"] == [1]
    assert s4["pair_continuity"] == [None, None] and len(s4["chains"]) == 1
    assert counts["documents"] == 4 and counts["documents_without_sentences"] == 2 and counts["mentions"] == 7
    # Registered words and characters of every document (DESIGN.md, Words), the parser's words apart: 21 + 3 + 0 + 5,
    # where the parser's count is 23 + 0 + 0 + 7.
    assert counts["words"] == counts["whitespace_tokens"] == sum(len(d.text.split()) for d in docs) == 29
    assert counts["characters"] == sum(len(d.text) for d in docs)
    assert counts["syntactic_words"] == 23 + 5 + 2 and counts["tokens"] == 25 + 6 + 3
    assert counts["sentences_refused"] == 1 and counts["forms_replaced"] == 1 and counts["segment"] == 2560
    assert counts["batch_size"] == 8 and counts["right"] == 50 and counts["variant"] == "xl"
    assert counts["setup_seconds"]["script_setup"] == 1.0 and counts["seconds_predict"] == 2.0
    assert counts["pins_verified"] == {"pins": "verified", "variant": "xl"}


def test_coref_stage_writes_nothing_when_its_checks_fail(tmp_path, monkeypatch):
    work = tmp_path / "work"
    _write_corpipe_inputs(work)
    launch, _ = _fake_launch({})

    def truncating(script, args, runtime):  # a cache with a sentence longer than the segment
        rec = launch(script, args, runtime)
        for cache in Path(args[args.index("--test") + 1]).parent.glob("*.mentions1.*"):
            cache.write_bytes(pickle.dumps([[(list(range(3000)), [], [], [], [])]], protocol=3))
        return rec

    _stub_stage(monkeypatch, tmp_path, truncating)
    ctx = cli.StageContext(stage=coref_stage.STAGE, config={"stages": {"coref_corpipe": COREF_CFG}}, lang="en-us",
                           work=work)
    with pytest.raises(RuntimeError, match="exceeded the segment"):
        coref_stage.run(ctx)
    assert not ctx.path("coref_corpipe").exists()


def test_coref_stage_refuses_translations_and_a_missing_parse(tmp_path, monkeypatch):
    cfg = {"stages": {"coref_corpipe": COREF_CFG}}
    with pytest.raises(ValueError, match="English sources"):
        coref_stage.run(cli.StageContext(stage=coref_stage.STAGE, config=cfg, lang="de-de", work=tmp_path))
    with pytest.raises(FileNotFoundError):
        coref_stage.run(cli.StageContext(stage=coref_stage.STAGE, config=cfg, lang="en-us", work=tmp_path))


def test_joined_pairs_documents_with_parses_in_order():
    docs = [_document("A", ("a",)), _document("B", ("b",)), _document("C", ("c",))]
    parses = [P.ConlluDocument("A"), P.ConlluDocument("C")]
    got = [(d.story_id, p.story_id if p else None) for d, p in coref_stage.joined(iter(docs), iter(parses))]
    assert got == [("A", "A"), ("B", None), ("C", "C")]
    with pytest.raises(ValueError, match="matches no document"):
        list(coref_stage.joined(iter(docs[:1]), iter(parses)))
    assert len(list(coref_stage.joined(iter(docs[:1]), iter(parses), strict=False))) == 1


def test_call_options_follow_command_line_then_options_then_defaults():
    s = cr.CorpipeSettings(segment=2560, batch_size=0)
    assert coref_stage.call_options(s, {"segment": 512, "batch_size": 6, "right": 40}) == {
        "segment": 2560, "batch_size": 6, "right": 40}
    assert coref_stage.call_options(cr.CorpipeSettings(segment=0), {}) == {"segment": 512, "batch_size": 8,
                                                                           "right": 50}


def _snapshot(hub: Path, repo: str, revision: str, files: dict[str, bytes]) -> dict:
    snap = hf_snapshot_dir(repo, revision, {"HF_HUB_CACHE": str(hub)})
    snap.mkdir(parents=True)
    for name, data in files.items():
        (snap / name).write_bytes(data)
    (snap.parent.parent / "refs").mkdir()
    (snap.parent.parent / "refs" / "main").write_text(revision)
    return {"repo": repo, "revision": revision, "files": {k: sha(v) for k, v in files.items()}}


def _pinned_tree(tmp_path: Path, variant: str = "xl") -> tuple[dict, dict, dict]:
    """Code, model and hub snapshots on disk, with their models.lock.json entries, the environment and the config."""
    v = COREF_CFG["model"]["variants"][variant]
    code = tmp_path / "code"
    code.mkdir(parents=True)
    (code / "corpipe26_onestage.py").write_bytes(b"print('corpipe')\n")
    model = tmp_path / "model"
    model.mkdir()
    files = {"model.pt": b"weights", "tags.txt": b"\nPUSH\n", "zdeprels.txt": b"[NONE]\n",
             "options.json": json.dumps({"encoder": v["encoder"], "segment": 512}).encode()}
    for name, data in files.items():
        (model / name).write_bytes(data)
    hub = tmp_path / "hub"
    models = {
        "ufal/crac2026-corpipe": {"repo": "ufal/crac2026-corpipe", "revision": "c1",
                                  "files": {"corpipe26_onestage.py": sha(b"print('corpipe')\n")}},
        v["corpipe"]: {"repo": v["corpipe"], "revision": "m1", "licence": "CC BY-NC-SA 4.0",
                       "files": {k: sha(d) for k, d in files.items()}},
        v["encoder"]: _snapshot(hub, v["encoder"], "rev1", {"config.json": b"{}"}),
    }
    if v["tokenizer"] != v["encoder"]:
        models[v["tokenizer"]] = _snapshot(hub, v["tokenizer"], "rev2", {"spiece.model": b"spm"})
    env = {"INTRACT_CORPIPE_SRC": str(code), "INTRACT_CORPIPE_MODEL": str(model), "HF_HUB_CACHE": str(hub)}
    scfg = json.loads(json.dumps(COREF_CFG))
    scfg["model"]["variant"] = variant
    return {"models": models}, env, scfg


def test_verify_pins_checks_code_model_encoder_and_ref(tmp_path):
    config, env, scfg = _pinned_tree(tmp_path)
    pinned = coref_stage.verify_pins(config, scfg, env)
    assert pinned.script == tmp_path / "code" / "corpipe26_onestage.py" and pinned.options["segment"] == 512
    assert pinned.encoder == "google/umt5-xl" and pinned.record["variant"] == "xl" and "tokenizer" not in pinned.record
    assert {f["file"] for f in pinned.record["model"]["files"]} == {"model.pt", "tags.txt", "zdeprels.txt",
                                                                    "options.json"}
    (tmp_path / "hub" / "models--google--umt5-xl" / "refs" / "main").write_text("rev2")
    with pytest.raises(PinError, match="refs/main"):
        coref_stage.verify_pins(config, scfg, env)


def test_verify_pins_of_the_large_fallback_check_both_hub_snapshots(tmp_path):
    config, env, scfg = _pinned_tree(tmp_path, "large")
    pinned = coref_stage.verify_pins(config, scfg, env)
    assert pinned.encoder == "google/mt5-large" and pinned.record["tokenizer"]["repo"] == "google/mt5-xl"
    assert pinned.record["model"]["repo"] == "ufal/corpipe26-onestage-corefud1.4-large-260702"
    (tmp_path / "hub" / "models--google--mt5-xl" / "refs" / "main").write_text("other")
    with pytest.raises(PinError, match="google/mt5-xl"):
        coref_stage.verify_pins(config, scfg, env)


def test_verify_pins_refuses_another_encoder_and_an_uncovered_script(tmp_path):
    config, env, scfg = _pinned_tree(tmp_path)
    options = json.dumps({"encoder": "google/mt5-large"}).encode()
    (tmp_path / "model" / "options.json").write_bytes(options)
    config["models"]["ufal/corpipe26-onestage-corefud1.4-xl-260702"]["files"]["options.json"] = sha(options)
    with pytest.raises(PinError, match="google/umt5-xl model"):
        coref_stage.verify_pins(config, scfg, env)
    config, env, scfg = _pinned_tree(tmp_path / "again")
    (tmp_path / "again" / "code" / "other.py").write_bytes(b"x")
    config["models"]["ufal/crac2026-corpipe"]["files"] = {"other.py": sha(b"x")}
    with pytest.raises(PinError, match="does not cover"):
        coref_stage.verify_pins(config, scfg, env)


def test_model_variant_reads_the_switch_and_checks_the_scripts_tokeniser():
    assert coref_stage.model_variant(COREF_CFG)["corpipe"] == "ufal/corpipe26-onestage-corefud1.4-xl-260702"
    bad = json.loads(json.dumps(COREF_CFG))
    bad["model"]["variant"] = "small"
    with pytest.raises(ValueError, match="not one of"):
        coref_stage.model_variant(bad)
    bad["model"]["variant"] = "large"
    bad["model"]["variants"]["large"]["tokenizer"] = "google/mt5-large"
    with pytest.raises(ValueError, match="loads the tokeniser"):
        coref_stage.model_variant(bad)


def test_check_versions_compares_prefixes():
    import importlib.metadata

    have = importlib.metadata.version("pytest")
    major = have.split(".")[0]
    assert coref_stage.check_versions({"pytest": major}) == {"pytest": have}
    with pytest.raises(PinError):
        coref_stage.check_versions({"pytest": "0.0"})
    with pytest.raises(PinError):
        coref_stage.check_versions({"no-such-package-intract": "1"})


# ------------------------------------------------------------------------------------------ MetricX: plain


class FakeTokenizer:
    """Characters to ids 2..31, the end-of-sequence mark (1) appended, truncation keeping it last, as mT5's does."""

    eos_token_id = 1
    pad_token_id = 0

    def __call__(self, texts, max_length, truncation, padding):
        assert truncation is True and padding is False
        out = []
        for t in texts:
            ids = [2 + ord(c) % 30 for c in t]
            out.append(ids[:max_length - 1] + [1])
        return {"input_ids": out}


def test_qe_input_matches_the_official_reference_free_format():
    s = mq.QESettings.from_config(QE_CFG)
    assert mq.qe_input("The cat sat.", "Die Katze saß.", s) == "source: The cat sat. candidate: Die Katze saß."


def test_encode_drops_the_end_of_sequence_mark_and_flags_the_limit():
    s = mq.QESettings(max_input_length=8, bucket_edges=(8,), tokens_per_batch=8)
    enc = mq.encode(FakeTokenizer(), ["abc", "abcdefghijk"], s)
    assert enc[0] == mq.Encoded(ids=(2 + ord("a") % 30, 2 + ord("b") % 30, 2 + ord("c") % 30), at_limit=False)
    assert len(enc[1].ids) == 7 and enc[1].at_limit

    class NoEos(FakeTokenizer):
        def __call__(self, texts, max_length, truncation, padding):
            return {"input_ids": [[5, 6] for _ in texts]}

    with pytest.raises(RuntimeError, match="end-of-sequence"):
        mq.encode(NoEos(), ["x"], s)


def test_plan_batches_gives_each_pair_a_shape_of_its_own():
    s = mq.QESettings(max_input_length=64, bucket_edges=(8, 16, 64), tokens_per_batch=32)
    lengths = [3, 9, 8, 60, 2, 15, 5, 7, 1]
    batches = mq.plan_batches(lengths, s)
    seen = sorted(i for b in batches for i in b.items)
    assert seen == list(range(len(lengths)))
    shape = {i: (b.width, b.rows) for b in batches for i in b.items}
    assert shape[0] == (8, 4) and shape[1] == (16, 2) and shape[3] == (64, 1)
    assert all(len(b.items) <= b.rows for b in batches)
    sub = mq.plan_batches([lengths[i] for i in (1, 3, 6)], s)  # a smaller shard: same shapes for the same pairs
    assert [(b.width, b.rows) for b in sub] == [shape[6], shape[1], shape[3]]
    single = mq.plan_batches(lengths, mq.QESettings(mode="single", max_input_length=64, bucket_edges=(64,),
                                                   tokens_per_batch=64))
    assert [(b.width, b.rows, b.items) for b in single[:2]] == [(3, 1, (0,)), (9, 1, (1,))]


def test_qe_settings_refuse_inconsistent_buckets():
    with pytest.raises(ValueError):
        mq.QESettings(bucket_edges=(64, 32, 1536)).check()
    with pytest.raises(ValueError):
        mq.QESettings(bucket_edges=(64, 512)).check()
    with pytest.raises(ValueError):
        mq.QESettings(tokens_per_batch=100).check()
    with pytest.raises(ValueError):
        mq.QESettings(mode="sorted").check()
    s = mq.QESettings.from_config(QE_CFG)
    assert s.logit_index == 250089 and s.clip == (0.0, 25.0) and s.max_input_length == 1536 and s.mode == "buckets"


def test_word_weighted_mean_ignores_weightless_pages_and_refuses_missing_scores():
    assert mq.word_weighted_mean([(4.0, 4), (2.0, 3)]) == pytest.approx(22 / 7)
    assert mq.word_weighted_mean([(4.0, 0)]) is None
    assert mq.word_weighted_mean([]) is None
    assert mq.word_weighted_mean([(4.0, 2), (None, 0)]) == 4.0
    assert mq.word_weighted_mean([(4.0, 2), (None, 3)]) is None
    assert mq.word_weighted_mean([(4.0, 2), (math.nan, 3)]) is None


def test_checkpoint_ties_embeddings_reads_the_checkpoints_own_config(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"tie_word_embeddings": False}))
    assert mq.checkpoint_ties_embeddings(tmp_path) is False
    (tmp_path / "config.json").write_text(json.dumps({"tie_word_embeddings": True}))
    assert mq.checkpoint_ties_embeddings(tmp_path) is True
    (tmp_path / "config.json").write_text("{}")  # MT5Config in transformers 4.30.2 defaults to False
    assert mq.checkpoint_ties_embeddings(tmp_path) is False


def test_validation_pairs_add_every_edge_kind():
    pairs = [("A.", "B."), ("C.", "  "), ("E.", "F.\n"), ("G.", "H.")]
    rows = mq.validation_pairs(pairs, 2)
    assert rows[:4] == [{"source": s, "hypothesis": h} for s, h in pairs]
    assert rows[4:] == [{"source": "A.", "hypothesis": "B. "}, {"source": "A.", "hypothesis": "B.\n"},
                        {"source": "A.", "hypothesis": ""}, {"source": "E.", "hypothesis": "F. "},
                        {"source": "E.", "hypothesis": "F.\n"}, {"source": "E.", "hypothesis": ""}]
    assert mq.count_edge_kinds([r["hypothesis"] for r in rows]) == {"trailing_space": 3, "trailing_newline": 3,
                                                                     "empty": 2}
    with pytest.raises(ValueError):
        mq.validation_pairs(pairs, 4)


def _tokenizer_files(folder: Path, special: dict | None = None, **config) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    cfg = {"eos_token": "</s>", "unk_token": "<unk>", "pad_token": "<pad>", "extra_ids": 0,
           "additional_special_tokens": None, **config}
    (folder / "tokenizer_config.json").write_text(json.dumps(cfg))
    (folder / "special_tokens_map.json").write_text(json.dumps({"eos_token": "</s>", "unk_token": "<unk>",
                                                                "pad_token": "<pad>", **(special or {})}))
    return folder


def test_check_tokenizer_files_accepts_only_mt5_xls_settings(tmp_path):
    assert mq.check_tokenizer_files(_tokenizer_files(tmp_path / "ok"))["eos_token"] == "</s>"
    with pytest.raises(ValueError, match="extra_ids"):
        mq.check_tokenizer_files(_tokenizer_files(tmp_path / "unset", extra_ids=None))
    with pytest.raises(ValueError, match="extra_ids"):
        mq.check_tokenizer_files(_tokenizer_files(tmp_path / "sentinels", extra_ids=100))
    # special_tokens_map.json overrides tokenizer_config.json, as 4.30.2's from_pretrained applies it after.
    assert mq.check_tokenizer_files(_tokenizer_files(tmp_path / "cfg", eos_token="<eos>"))["eos_token"] == "</s>"
    with pytest.raises(ValueError, match="special tokens"):
        mq.check_tokenizer_files(_tokenizer_files(tmp_path / "eos", special={"eos_token": "<eos>"}))
    with pytest.raises(ValueError, match="additional special"):
        mq.check_tokenizer_files(_tokenizer_files(tmp_path / "extra", special={"additional_special_tokens": ["<x>"]}))


def test_build_tokenizer_reproduces_the_4_30_2_pipeline_on_a_small_model(tmp_path):
    pytest.importorskip("tokenizers")
    pytest.importorskip("google.protobuf")
    pb = pytest.importorskip("sentencepiece.sentencepiece_model_pb2")
    proto = pb.ModelProto()
    pieces = [("<pad>", 0.0, 3), ("</s>", 0.0, 3), ("<unk>", 0.0, 2), ("▁", -2.0, 1), ("a", -3.0, 1),
              ("b", -3.0, 1), ("▁a", -1.0, 1), ("▁b", -1.0, 1), ("▁ab", -0.5, 1)]
    for piece, score, kind in pieces:
        p = proto.pieces.add()
        p.piece, p.score, p.type = piece, score, kind
    proto.trainer_spec.model_type = 1
    proto.trainer_spec.unk_id = 2
    proto.trainer_spec.byte_fallback = True  # ignored, as 4.30.2's converter ignored it
    folder = _tokenizer_files(tmp_path / "spm")
    (folder / "spiece.model").write_bytes(proto.SerializeToString())
    tok = mq.build_tokenizer(folder)
    ids = {p: i for i, (p, _, _) in enumerate(pieces)}
    got = tok(["a b", "a b ", "a  b", "ab", "", "a</s>b", "a z"], max_length=16, truncation=True,
              padding=False)["input_ids"]
    assert got[0] == [ids["▁a"], ids["▁b"], 1]
    assert got[1] == [ids["▁a"], ids["▁b"], ids["▁"], 1]  # the final "▁" that 4.30.2 keeps
    assert got[2] == got[0]  # runs of spaces collapse (Replace(" {2,}", " "))
    assert got[3] == [ids["▁ab"], 1] and got[4] == [1]
    assert got[5] == [ids["▁a"], 1, ids["▁b"], 1]  # "</s>" in the text is the special token
    assert got[6] == [ids["▁a"], ids["▁"], 2, 1]  # unknown character: <unk>, no byte pieces
    assert tok(["a b " * 10], max_length=5, truncation=True, padding=False)["input_ids"][0][-1] == 1
    assert (tok.eos_token_id, tok.pad_token_id, tok.unk_token_id) == (1, 0, 2)
    with pytest.raises(ValueError):
        tok(["a"], max_length=4, truncation=True, padding=True)


# ------------------------------------------------------------------------------------- MetricX: tiny model


def _tiny_mt5(seed: int = 0, untied: bool = True):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    cfg = transformers.MT5Config(vocab_size=40, d_model=16, d_kv=4, d_ff=32, num_layers=2, num_decoder_layers=2,
                                 num_heads=4, relative_attention_num_buckets=8, relative_attention_max_distance=16,
                                 feed_forward_proj="gated-gelu", decoder_start_token_id=0, pad_token_id=0,
                                 eos_token_id=1)
    torch.manual_seed(seed)
    model = transformers.MT5ForConditionalGeneration(cfg).eval()
    if untied:  # MetricX-24 keeps a head of its own; give the tiny model one too
        model.lm_head.weight = torch.nn.Parameter(torch.randn(model.lm_head.weight.shape,
                                                              generator=torch.Generator().manual_seed(seed + 1)))
    return model


def _manual_metricx(model, ids, mask, index, rescale=False, clip=(0.0, 25.0)):
    """MT5ForRegression.forward of metricx24/models.py, written out on the model's modules."""
    import torch

    with torch.no_grad():
        hidden = model.encoder(input_ids=ids, attention_mask=mask).last_hidden_state
        dec = torch.zeros((ids.shape[0], 1), dtype=torch.long)
        out = model.decoder(input_ids=dec, encoder_hidden_states=hidden, encoder_attention_mask=mask).last_hidden_state
        if rescale:
            out = out * (model.config.d_model ** -0.5)
        return torch.clamp((out @ model.lm_head.weight.T)[:, 0, index], *clip)


def test_forward_scores_follow_the_modules_of_the_model():
    torch = pytest.importorskip("torch")
    model = _tiny_mt5()
    s = mq.QESettings(logit_index=7, clip=(-50.0, 50.0))
    ids = torch.tensor([[5, 6, 7, 8, 0], [9, 10, 11, 0, 0]])
    mask = (ids != 0).long()
    with torch.no_grad():
        got = mq.forward_scores(model, ids, mask, s)
        rescaled = mq.forward_scores(model, ids, mask, s, rescale=True)
    assert torch.allclose(got, _manual_metricx(model, ids, mask, 7, clip=s.clip), atol=1e-6)
    assert torch.allclose(rescaled, _manual_metricx(model, ids, mask, 7, rescale=True, clip=s.clip), atol=1e-6)
    with torch.no_grad():
        clipped = mq.forward_scores(model, ids, mask, mq.QESettings(logit_index=7, clip=(0.0, 1e-9)))
    assert float(clipped.max()) <= 1e-9 and float(clipped.min()) >= 0.0


def test_scores_do_not_depend_on_batch_neighbours():
    torch = pytest.importorskip("torch")
    model = _tiny_mt5(seed=3)
    s = mq.QESettings(logit_index=7, max_input_length=64, bucket_edges=(16, 32, 64), tokens_per_batch=64)
    scorer = mq.QEScorer(tokenizer=FakeTokenizer(), model=model, settings=s)
    pairs = [("a", "bb"), ("The cat.", "Die Katze."), ("x" * 20, "y" * 25), ("one", "two"), ("q", "r" * 9)]
    together = [r.score for r in scorer.score(pairs)]
    alone = [scorer.score([p])[0].score for p in pairs]
    assert together == alone  # bitwise: every pair is computed in a tensor of the same shape
    single = mq.QEScorer(tokenizer=FakeTokenizer(), model=model,
                         settings=mq.QESettings(mode="single", logit_index=7, max_input_length=64,
                                                bucket_edges=(64,), tokens_per_batch=64))
    unpadded = [r.score for r in single.score(pairs)]
    assert torch.allclose(torch.tensor(together), torch.tensor(unpadded), atol=1e-5)
    assert scorer.stats["batches"] > 0 and scorer.stats["positions"] > scorer.stats["positions_real"] > 0
    assert scorer.stats["filler_rows"] > 0 and single.stats["filler_rows"] == 0
    chunked = mq.QEScorer(tokenizer=FakeTokenizer(), model=model,
                          settings=mq.QESettings(logit_index=7, max_input_length=64, bucket_edges=(16, 32, 64),
                                                 tokens_per_batch=64, chunk_pairs=2))
    assert [r.score for r in chunked.score(pairs)] == together


def test_load_model_keeps_a_separate_head_and_refuses_a_tied_one(tmp_path):
    torch = pytest.importorskip("torch")
    model = _tiny_mt5(seed=5)
    sd = {k: v.detach().clone() for k, v in model.state_dict().items()}
    raw = model.config.to_dict()
    raw.update(tie_word_embeddings=False, architectures=["MT5ForRegression"], torch_dtype="float32")
    good = tmp_path / "good"
    good.mkdir()
    (good / "config.json").write_text(json.dumps(raw))
    torch.save(sd, good / "pytorch_model.bin")
    s = mq.QESettings(logit_index=7)
    loaded, device, tied = mq.load_model(good, TorchRuntime(device="cpu", deterministic_algorithms=False), s)
    assert tied is False and str(device) == "cpu"
    assert loaded.lm_head.weight.data_ptr() != loaded.shared.weight.data_ptr()
    assert torch.equal(loaded.lm_head.weight, sd["lm_head.weight"])
    ids = torch.tensor([[5, 6, 7, 8]])
    mask = torch.ones_like(ids)
    with torch.no_grad():
        assert torch.allclose(mq.forward_scores(loaded, ids, mask, s), _manual_metricx(model, ids, mask, 7), atol=1e-6)
    headless = tmp_path / "headless"  # a config that says untied over weights without a head of their own
    headless.mkdir()
    (headless / "config.json").write_text(json.dumps(raw))
    torch.save({k: v for k, v in sd.items() if k != "lm_head.weight"}, headless / "pytorch_model.bin")
    with pytest.raises(RuntimeError):
        mq.load_model(headless, TorchRuntime(device="cpu", deterministic_algorithms=False), s)


# The tiny checkpoint of the official comparison: the official MT5ForRegression with these settings and weights.
TINY_CONFIG = dict(vocab_size=250112, d_model=8, d_kv=4, d_ff=16, num_layers=2, num_decoder_layers=2, num_heads=2,
                   relative_attention_num_buckets=8, relative_attention_max_distance=16,
                   feed_forward_proj="gated-gelu", tie_word_embeddings=False, decoder_start_token_id=0,
                   pad_token_id=0, eos_token_id=1, dropout_rate=0.0)
TINY_TIED = {"encoder.embed_tokens.weight": "shared.weight", "decoder.embed_tokens.weight": "shared.weight"}


def tiny_weights(torch, name: str, shape) -> object:
    """Integer k in [-32768, 32767] over a power of two: exact in float32, so every torch release agrees."""
    idx = torch.arange(math.prod(shape), dtype=torch.int64)
    k = (idx * 2654435761 + zlib.crc32(name.encode("utf-8"))) % 65536 - 32768
    base = k.to(torch.float64) / 65536.0
    if "layer_norm" in name:
        out = 1.0 + base / 4.0
    elif name == "lm_head.weight":
        out = base * -12.0  # keeps the tiny model's scores near 12, inside the [0, 25] clamp
    else:
        out = base
    return out.to(torch.float32).reshape(tuple(shape))


def _official_tiny_checkpoint(folder: Path) -> Path:
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    model = transformers.MT5ForConditionalGeneration(transformers.MT5Config(**TINY_CONFIG))
    # transformers 5 ties a freshly built mT5's head to its embeddings; MetricX-24's head is its own.
    model.lm_head.weight = torch.nn.Parameter(torch.empty_like(model.lm_head.weight))
    with torch.no_grad():
        for name, param in model.named_parameters(remove_duplicate=False):
            param.copy_(tiny_weights(torch, TINY_TIED.get(name, name), param.shape))
    folder.mkdir(parents=True)
    raw = {**model.config.to_dict(), "tie_word_embeddings": False, "architectures": ["MT5ForRegression"]}
    (folder / "config.json").write_text(json.dumps(raw))
    torch.save(model.state_dict(), folder / "pytorch_model.bin")
    return folder


# Official scores on the tiny checkpoint, with the official tokeniser's ids after `_remove_eos`: FLORES-200 dev pairs
# (English with Greek, Thai, Chinese and German), a candidate ending in a space, an empty candidate, a white-space-only
# candidate and a literal "<extra_id_10>" (from tiny_metricx/official/official.jsonl, 3 November 2026).
TINY_CASES = [
    ("flores:ell_Grek-3991", 12.297067642211914, [10219, 267, 486, 18147, 639, 46261, 345, 527, 320, 72586, 272, 67388, 20604, 268, 77215, 89336, 8211, 265, 260, 259, 53939, 267, 2195, 29098, 64904, 15209, 3476, 54825, 63762, 259, 2046, 259, 589, 141766, 10588, 41168, 3142, 5792, 7424, 64904, 170899, 46373, 142527, 75187, 260]),  # noqa: E501
    ("flores:tha_Thai-21938", 12.441418647766113, [10219, 267, 13065, 3706, 259, 49511, 461, 45837, 10112, 27743, 259, 125337, 910, 259, 4944, 23749, 347, 260, 259, 53939, 267, 70546, 88450, 38797, 122488, 86727, 6582, 18169, 150852, 227124, 87196, 172224, 115758, 108604, 6088, 17138, 81755, 226547, 80327, 2361, 94536]),  # noqa: E501
    ("flores:zho_Hans-24929", 13.292027473449707, [10219, 267, 13065, 3706, 259, 49511, 461, 45837, 10112, 27743, 259, 125337, 910, 259, 4944, 23749, 347, 260, 259, 53939, 267, 259, 63193, 38455, 53739, 261, 213552, 104049, 73582, 5234, 1083, 189580, 5696, 25557, 3582, 48734, 1322, 5234, 306]),  # noqa: E501
    ("flores:deu_Latn-2994", 8.746256828308105, [10219, 267, 486, 18147, 639, 46261, 345, 527, 320, 72586, 272, 67388, 20604, 268, 77215, 89336, 8211, 265, 260, 259, 53939, 267, 1683, 51910, 4052, 1227, 259, 158665, 89604, 20604, 268, 77215, 89336, 8211, 265, 46261, 67835, 260]),  # noqa: E501
    ("tail_mt:space-26919", 12.954567909240723, [10219, 267, 1641, 15914, 261, 259, 96846, 263, 702, 287, 259, 129768, 3934, 5736, 304, 35226, 259, 50496, 287, 281, 25645, 304, 259, 262, 1546, 39837, 16080, 533, 738, 9019, 259, 40421, 455, 4054, 267, 259, 262, 259, 29941, 13159, 1059, 31831, 533, 738, 390, 64798, 285, 259, 4342, 5902, 281, 314, 4339, 63184, 263, 332, 72081, 276, 1388, 1371, 581, 260, 399, 260, 22233, 259, 3151, 260, 259, 53939, 267, 575, 6090, 402, 10053, 25625, 343, 1021, 55970, 10033, 2216, 556, 2042, 831, 31858, 614, 13317, 445, 259, 5322, 26910, 883, 1698, 21802, 52083, 31163, 12234, 7900, 3197, 55230, 831, 259, 22559, 259, 19689, 10149, 259, 79630, 1686, 40169, 35581, 1240, 12441, 402, 8832, 267, 259, 105825, 7139, 259, 35482, 445, 259, 10489, 445, 2008, 35956, 38938, 259, 477, 8784, 259, 79630, 102768, 614, 14203, 259, 111604, 24374, 31152, 10053, 445, 65028, 4341, 35886, 31763, 259, 15629, 1240, 33990, 53536, 259, 150007, 10126, 259, 50468, 556, 913, 260, 259]),  # noqa: E501
    ("empty_mt-44099", 12.789260864257812, [10219, 267, 13065, 3706, 259, 49511, 461, 45837, 10112, 27743, 259, 125337, 910, 259, 4944, 23749, 347, 260, 259, 53939, 267, 259]),  # noqa: E501
    ("whitespace_only_mt-44171", 12.93037223815918, [10219, 267, 1641, 15914, 261, 259, 96846, 263, 702, 287, 259, 129768, 3934, 5736, 304, 35226, 259, 50496, 287, 281, 25645, 304, 259, 262, 1546, 39837, 16080, 533, 738, 9019, 259, 40421, 455, 4054, 267, 259, 262, 259, 29941, 13159, 1059, 31831, 533, 738, 390, 64798, 285, 259, 4342, 5902, 281, 314, 4339, 63184, 263, 332, 72081, 276, 1388, 1371, 581, 260, 399, 260, 22233, 259, 3151, 260, 259, 53939, 267, 259]),  # noqa: E501
    ("odd_mt-44218", 12.699580192565918, [10219, 267, 13065, 3706, 259, 49511, 461, 45837, 10112, 27743, 259, 125337, 910, 259, 4944, 23749, 347, 260, 259, 53939, 267, 250089]),  # noqa: E501
]


class RecordedTokenizer:
    """Hands back the official tokeniser's recorded ids for each case (keyed by its QE input), with "</s>" after."""

    eos_token_id = 1
    pad_token_id = 0

    def __init__(self, settings):
        self.ids = {mq.qe_input(label, "", settings): ids + [1] for label, _, ids in TINY_CASES}

    def __call__(self, texts, max_length, truncation, padding):
        return {"input_ids": [self.ids[t] for t in texts]}


@pytest.mark.parametrize("mode", ["single", "buckets"])
def test_port_reproduces_the_official_predict_py_on_a_tiny_checkpoint(tmp_path, mode):
    folder = _official_tiny_checkpoint(tmp_path / "tiny")
    settings = mq.QESettings(mode=mode)
    model, device, tied = mq.load_model(folder, TorchRuntime(device="cpu", deterministic_algorithms=False, threads=1),
                                        settings)
    scorer = mq.QEScorer(tokenizer=RecordedTokenizer(settings), model=model, settings=settings, device=device,
                         rescale=tied)
    got = scorer.score([(label, "") for label, _, _ in TINY_CASES])
    want = [score for _, score, _ in TINY_CASES]
    assert tied is False and [r.tokens for r in got] == [len(ids) for _, _, ids in TINY_CASES]
    # Observed: identical under torch 2.10 and transformers 5.2 in single mode, within 8.6e-6 otherwise.
    assert max(abs(r.score - w) for r, w in zip(got, want, strict=True)) <= 2e-5


def test_bf16_keeps_the_head_and_the_score_in_float32(tmp_path):
    torch = pytest.importorskip("torch")
    folder = _official_tiny_checkpoint(tmp_path / "tiny")
    settings = mq.QESettings()
    runtime = TorchRuntime(device="cpu", dtype="bfloat16", deterministic_algorithms=False, threads=1)
    model, device, _ = mq.load_model(folder, runtime, settings)
    assert model.lm_head.weight.dtype == torch.float32
    assert model.encoder.block[0].layer[0].SelfAttention.q.weight.dtype == torch.bfloat16
    got = mq.QEScorer(tokenizer=RecordedTokenizer(settings), model=model, settings=settings).score(
        [(label, "") for label, _, _ in TINY_CASES])
    assert all(math.isfinite(r.score) for r in got)
    assert max(abs(r.score - w) for r, (_, w, _) in zip(got, TINY_CASES, strict=True)) < 0.5


# ------------------------------------------------------------------------------------- qe_metricx stage


class FakeLock:
    def __init__(self, listed=()):
        self.listed = set(listed)
        self.record = {"state": "locked"}
        self.inputs = []
        self.texts = []

    def check_input(self, path):
        self.inputs.append(Path(path))
        return {"name": Path(path).name}

    def check_text(self, story_id, title_line, pages):
        self.texts.append((story_id, title_line, list(pages)))
        fp = fingerprint(pages)
        if fp in self.listed:
            raise CatalogueLocked(f"{story_id} is a catalogue text")
        return fp


class FakeScorer:
    def __init__(self, scores=None):
        self.seen = []
        self.scores = scores or {}
        self.record = {"scorer": "fake", "setup_seconds": {"verify_pins": 1.0, "load": 2.0}}
        self.stats = {"batches": 1, "positions": 64, "positions_real": 40, "filler_rows": 3}

    def score(self, pairs):
        self.seen.extend(pairs)
        return [mq.QEResult(score=self.scores.get(mt, float(len(mt) % 7)), tokens=len(src) + len(mt), width=64,
                            at_limit=False) for src, mt in pairs]


PAIRS = [
    {"pair_id": "a-2", "story_id": "A", "page": 2, "src": "The dog ran.", "mt": "Der Hund rannte."},
    {"pair_id": "a-1", "story_id": "A", "page": 1, "src": "A dog.", "mt": "Ein Hund lief weg."},
    {"pair_id": "b", "src": "Hello there.", "mt": "Hallo\N{ZERO WIDTH SPACE} Café."},
    {"pair_id": "c", "src": "x", "mt": "y", "lang": "fr-fr"},
]


def _qe_ctx(tmp_path, rows, monkeypatch, lock=None, shard=0, nshards=1, limit=None, scorer=None, cfg=None):
    path = tmp_path / "pairs.jsonl"
    if isinstance(rows, str):
        path.write_text(rows, encoding="utf-8")
    else:
        records.write_jsonl(path, rows)
    scorer, lock = scorer or FakeScorer(), lock or FakeLock()
    monkeypatch.setattr(qe_stage, "load_lock", lambda ctx: lock)
    monkeypatch.setattr(qe_stage, "build_scorer", lambda config, scfg, settings: scorer)
    ctx = cli.StageContext(stage=qe_stage.STAGE, config={"stages": {"qe_metricx": cfg or QE_CFG}}, lang="de-de",
                           work=tmp_path / "work", shard=shard, nshards=nshards, input=path, limit=limit)
    return ctx, scorer, lock


def test_qe_stage_runs_in_core_where_the_port_is_validated():
    assert qe_stage.STAGE.env == "core" and qe_stage.STAGE.device == "gpu"
    assert QE_CFG["versions"] == {"torch": "2.14", "transformers": "5.19"}


def test_qe_stage_scores_pages_and_weights_them_by_words(tmp_path, monkeypatch):
    ctx, scorer, lock = _qe_ctx(tmp_path, PAIRS, monkeypatch)
    counts = cli.run_stage(qe_stage, ctx)["counts"]
    out = {r["story_id"]: r for r in records.read_jsonl(ctx.path("qe_metricx"))}
    assert list(out) == ["A", "b"]
    a = out["A"]
    assert [p["pair_id"] for p in a["pages"]] == ["a-1", "a-2"] and [p["words"] for p in a["pages"]] == [4, 3]
    assert a["values"]["metricx_qe"] == pytest.approx((4.0 * 4 + 2.0 * 3) / 7)
    assert out["b"]["pages"][0]["page"] is None
    assert ("Hello there.", "Hallo Café.") in scorer.seen  # normalised: NFC, zero width space removed
    assert counts["documents"] == 2 and counts["pairs"] == 3 and counts["rows_other_language"] == 1
    assert counts["words"] == 9 and counts["batches"] == 1 and counts["scorer"]["scorer"] == "fake"
    assert counts["positions_real"] == 40 and counts["filler_rows"] == 3
    assert counts["page_weight"] == "translation_words"
    assert counts["setup_seconds"] == {"verify_pins": 1.0, "load": 2.0} and counts["seconds_score"] >= 0
    assert counts["whitespace_tokens"] == 2 + 4 + 3 + 3 + 2 + 2
    assert lock.inputs == [ctx.input]


def test_qe_stage_locks_the_pages_as_delivered_before_normalising(tmp_path, monkeypatch):
    ctx, scorer, lock = _qe_ctx(tmp_path, PAIRS, monkeypatch)
    qe_stage.run(ctx)
    # As delivered: the lock sees the zero width space that normalisation removes before scoring.
    assert ("b (translated pages)", "", ["Hallo\N{ZERO WIDTH SPACE} Café."]) in lock.texts
    assert ("A (English pages)", "", ["A dog.", "The dog ran."]) in lock.texts


def test_qe_stage_applies_the_catalogue_lock_before_scoring(tmp_path, monkeypatch):
    listed = fingerprint(["A dog.", "The dog ran."])  # story A's English pages, in page order
    ctx, scorer, _ = _qe_ctx(tmp_path, PAIRS, monkeypatch, lock=FakeLock({listed}))
    with pytest.raises(CatalogueLocked):
        qe_stage.run(ctx)
    assert scorer.seen == []


def test_qe_stage_shards_by_story_and_honours_the_limit(tmp_path, monkeypatch):
    rows = [{"pair_id": f"p{i}", "story_id": f"S{i // 2}", "page": i % 2, "src": f"Page {i}.", "mt": f"Seite {i}."}
            for i in range(40)]
    seen = {}
    for shard in (0, 1):
        ctx, _, _ = _qe_ctx(tmp_path / str(shard), rows, monkeypatch, shard=shard, nshards=2)
        qe_stage.run(ctx)
        seen[shard] = {r["story_id"] for r in records.read_jsonl(ctx.path("qe_metricx"))}
    assert seen[0] | seen[1] == {f"S{i}" for i in range(20)} and not seen[0] & seen[1]
    assert all(records.shard_of(s, 2) == 1 for s in seen[1])
    ctx, scorer, _ = _qe_ctx(tmp_path / "limit", rows, monkeypatch, limit=3)
    assert qe_stage.run(ctx)["documents"] == 3 and len(scorer.seen) == 6


@pytest.mark.parametrize("bad, message", [
    ([{"pair_id": "x", "src": "a", "mt": "b"}, {"pair_id": "x", "src": "c", "mt": "d"}], "repeated"),
    ([{"pair_id": "x", "src": "a", "mt": "b", "page": "1"}], "page must be an integer"),
    ([{"pair_id": "x", "src": "a", "mt": 3}], "'mt' must be a string"),
    ([{"pair_id": "x", "src": "a", "mt": "b", "words": -1}], "finite non-negative"),
    ('{"pair_id": "x", "src": "a", "mt": "b", "words": NaN}\n', "finite non-negative"),
    ('{"pair_id": "x", "src": "a", "mt": "b", "words": Infinity}\n', "finite non-negative"),
    ([{"pair_id": "x", "story_id": "S", "page": 1, "src": "a", "mt": "b"},
      {"pair_id": "y", "story_id": "S", "src": "c", "mt": "d"}], "some pages only"),
    ([{"pair_id": "x", "story_id": "S", "page": 1, "src": "a", "mt": "b"},
      {"pair_id": "y", "story_id": "S", "page": 1, "src": "c", "mt": "d"}], "repeats a page"),
])
def test_qe_stage_validates_its_input(tmp_path, monkeypatch, bad, message):
    ctx, _, _ = _qe_ctx(tmp_path, bad, monkeypatch)
    with pytest.raises(ValueError, match=message):
        qe_stage.run(ctx)


def test_qe_stage_needs_an_input(tmp_path):
    ctx = cli.StageContext(stage=qe_stage.STAGE, config={"stages": {"qe_metricx": QE_CFG}}, lang="de-de",
                           work=tmp_path)
    with pytest.raises(ValueError, match="--input"):
        qe_stage.run(ctx)


def test_qe_stage_with_words_given_and_no_words(tmp_path, monkeypatch):
    rows = [{"pair_id": "x", "src": "a", "mt": "b", "words": 0}, {"pair_id": "y", "src": "c", "mt": "...", }]
    ctx, _, _ = _qe_ctx(tmp_path, rows, monkeypatch)
    counts = qe_stage.run(ctx)
    out = list(records.read_jsonl(ctx.path("qe_metricx")))
    assert [r["values"]["metricx_qe"] for r in out] == [None, None] and counts["texts_without_value"] == 2


def test_qe_stage_weights_by_source_words_when_switched(tmp_path, monkeypatch):
    cfg = json.loads(json.dumps(QE_CFG))
    cfg["output"]["page_weight"] = "source_words"
    rows = [{"pair_id": "1", "story_id": "S", "page": 1, "src": "One two three.", "mt": ""},
            {"pair_id": "2", "story_id": "S", "page": 2, "src": "Four.", "mt": "Vier fünf sechs sieben."}]
    ctx, _, _ = _qe_ctx(tmp_path, rows, monkeypatch, scorer=FakeScorer({"": 20.0, "Vier fünf sechs sieben.": 4.0}),
                        cfg=cfg)
    qe_stage.run(ctx)
    (rec,) = records.read_jsonl(ctx.path("qe_metricx"))
    assert [p["words"] for p in rec["pages"]] == [3, 1] and rec["values"]["metricx_qe"] == pytest.approx(16.0)
    cfg["output"]["page_weight"] = "characters"
    ctx, _, _ = _qe_ctx(tmp_path / "bad", rows, monkeypatch, cfg=cfg)
    with pytest.raises(ValueError, match="page_weight"):
        qe_stage.run(ctx)


def test_qe_stage_writes_null_for_a_score_that_is_not_finite(tmp_path, monkeypatch):
    rows = [{"pair_id": "1", "story_id": "S", "page": 1, "src": "One two.", "mt": "Eins zwei."},
            {"pair_id": "2", "story_id": "S", "page": 2, "src": "Three.", "mt": "Drei."},
            {"pair_id": "3", "src": "Four.", "mt": "Vier."}]
    ctx, _, _ = _qe_ctx(tmp_path, rows, monkeypatch, scorer=FakeScorer({"Drei.": math.nan}))
    counts = qe_stage.run(ctx)
    out = {r["story_id"]: r for r in records.read_jsonl(ctx.path("qe_metricx"))}
    assert [p["qe"] for p in out["S"]["pages"]] == [3.0, None] and out["S"]["values"]["metricx_qe"] is None
    assert out["S"]["diagnostics"]["non_finite_pages"] == 1 and out["3"]["values"]["metricx_qe"] == 5.0
    assert counts["non_finite_pages"] == 1 and counts["texts_without_value"] == 1


# ---------------------------------------------------------------------------------------------- aligner


def test_aligner_settings_from_the_config_file():
    s = AL.AlignerSettings.from_config(COREF_CFG["aligner"])
    assert (s.model, s.layer, s.method, s.max_length) == ("google-bert/bert-base-multilingual-cased", 8, "argmax", 512)
    with pytest.raises(ValueError):
        AL.AlignerSettings.from_config({**COREF_CFG["aligner"], "method": "itermax"})


def test_padded_width_and_embedding_batches():
    s = AL.AlignerSettings(max_length=64, batch_size=2, pad_multiple=8)
    assert [AL.padded_width(n, s) for n in (1, 8, 9, 70)] == [8, 8, 16, 64]
    plan = AL.plan_embedding_batches([3, 12, 5, 7, 20], s)
    assert plan == [([0, 2], 8), ([3], 8), ([1], 16), ([4], 24)]
    dynamic = AL.plan_embedding_batches([3, 12, 5], AL.AlignerSettings(batch_size=2, fixed_shapes=False))
    assert dynamic == [([0, 1], None), ([2], None)]


def test_argmax_align_is_mutual():
    np = pytest.importorskip("numpy")
    a = np.array([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]])
    b = np.array([[0.0, 1.0], [1.0, 0.1]])
    assert AL.Aligner.argmax_align(a, b) == [(0, 1), (1, 0)]  # word 2's best match prefers word 0
    assert AL.Aligner.argmax_align(a[:0], b) == []


# "katze" is left out, so "Katze" splits into two subwords ("kat", "##ze").
VOCAB = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", ".", "the", "cat", "sat", "on", "mat", "die", "auf", "der",
         "matte", "sa", "##ß", "kat", "##ze", "a", "dog"]


def _tiny_aligner(tmp_path, **overrides):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    pytest.importorskip("numpy")
    tmp_path.mkdir(parents=True, exist_ok=True)
    # Built from a dict: transformers 5.2's BertTokenizerFast ignores vocab_file and would map every word to [UNK].
    tok = transformers.BertTokenizerFast(vocab={t: i for i, t in enumerate(VOCAB)})
    assert tok.convert_ids_to_tokens(tok(["katze"], is_split_into_words=True)["input_ids"])[1:3] == ["kat", "##ze"]
    cfg = transformers.BertConfig(vocab_size=len(VOCAB), hidden_size=16, num_hidden_layers=3, num_attention_heads=2,
                                  intermediate_size=32, max_position_embeddings=64)
    torch.manual_seed(11)
    model = transformers.BertModel(cfg).eval()
    settings = AL.AlignerSettings(**{"layer": 2, "max_length": 32, "batch_size": 2, "pad_multiple": 4, **overrides})
    model.encoder.layer = model.encoder.layer[:settings.layer]
    model.config.num_hidden_layers = settings.layer
    return AL.Aligner(tok, model, settings), tok, model


# Lower case, so the tiny WordPiece vocabulary needs no lowercasing step.
SENTS = [["the", "cat", "sat", "on", "the", "mat", "."], ["die", "katze", "saß", "auf", "der", "matte", "."],
         ["a", "dog", "."], ["the", "cat"]]


def test_embed_averages_subwords_and_normalises(tmp_path):
    torch = pytest.importorskip("torch")
    np = pytest.importorskip("numpy")
    aligner, tok, model = _tiny_aligner(tmp_path)
    vecs = aligner.embed(SENTS)
    assert [v.shape for v in vecs] == [(7, 16), (7, 16), (3, 16), (2, 16)]
    assert all(np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-5) for v in vecs)
    enc = tok([SENTS[1]], is_split_into_words=True, return_tensors="pt")
    with torch.no_grad():
        hs = model(**enc).last_hidden_state[0].numpy()
    wid = enc.word_ids(0)
    katze = [t for t, w in enumerate(wid) if w == 1]
    assert len(katze) == 2  # "katze" -> kat ##ze
    want = hs[katze].mean(axis=0)
    assert np.allclose(vecs[1][1], want / np.linalg.norm(want), atol=1e-5)


def test_fixed_shapes_make_vectors_independent_of_the_batch(tmp_path):
    np = pytest.importorskip("numpy")
    aligner, _, _ = _tiny_aligner(tmp_path)
    together = aligner.embed(SENTS)
    alone = [aligner.embed([s])[0] for s in SENTS]
    assert all(np.array_equal(a, b) for a, b in zip(together, alone, strict=True))
    dynamic, _, _ = _tiny_aligner(tmp_path / "d", fixed_shapes=False)
    dyn = dynamic.embed(SENTS)
    assert all(np.allclose(a, b, atol=1e-5) for a, b in zip(together, dyn, strict=True))
    assert dynamic.align(SENTS[:1], SENTS[1:2]) == aligner.align(SENTS[:1], SENTS[1:2])


def test_truncated_words_never_align_and_compact_changes_nothing(tmp_path):
    np = pytest.importorskip("numpy")
    aligner, _, _ = _tiny_aligner(tmp_path, max_length=6, pad_multiple=2)
    vecs = aligner.embed(SENTS[:1])[0]
    assert np.all(vecs[4:] == 0) and np.all(np.abs(vecs[:4]).sum(axis=1) > 0)  # [CLS] + 4 words + [SEP]
    assert all(i < 4 for i, _ in AL.Aligner.argmax_align(vecs, vecs))
    full, _, _ = _tiny_aligner(tmp_path / "c")
    before = full.embed(SENTS)
    rows = full.compact(SENTS)
    assert rows < len(VOCAB)
    after = full.embed(SENTS)
    assert all(np.array_equal(a, b) for a, b in zip(before, after, strict=True))


def test_from_pinned_verifies_then_keeps_the_first_layers(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    _, tok, _ = _tiny_aligner(tmp_path)
    import transformers

    folder = tmp_path / "mbert"
    model = transformers.BertModel(transformers.BertConfig(vocab_size=len(VOCAB), hidden_size=16, num_hidden_layers=3,
                                                           num_attention_heads=2, intermediate_size=32,
                                                           max_position_embeddings=64))
    model.save_pretrained(folder)
    tok.save_pretrained(folder)
    files = {p.name: sha(p.read_bytes()) for p in folder.iterdir() if p.is_file()}
    config = {"models": {"google-bert/bert-base-multilingual-cased": {"repo": "x", "revision": "y", "files": files}}}
    for key in ("CUBLAS_WORKSPACE_CONFIG", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    settings = AL.AlignerSettings(layer=2, max_length=32, batch_size=2, pad_multiple=4, threads=1)
    try:
        aligner, verified = AL.Aligner.from_pinned(config, settings, {"INTRACT_MBERT": str(folder)})
        assert len(aligner.model.encoder.layer) == 2 and {v["file"] for v in verified} == set(files)
        assert aligner.align([["the", "cat"]], [["die", "katze"]])[0]
    finally:
        import torch

        torch.use_deterministic_algorithms(False)
    (folder / sorted(files)[0]).write_text("changed")
    with pytest.raises(PinError):
        AL.Aligner.from_pinned(config, settings, {"INTRACT_MBERT": str(folder)})
