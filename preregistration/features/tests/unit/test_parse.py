"""Unit tests of the parse package and the parse stages.

Everything runs on hand-built fixtures: a fake `stanza` and `torch` stand in for the libraries, a small HTTP server
script stands in for UDPipe 2 (answering, like upstream udpipe2_server.py at the pinned commit, HTTP 400 with its
own text for a sentence over its word limit), and fake model files carry real MD5 and SHA-256 pins, so the pin
checks, the Greek workaround, the CoNLL-U contract (sentence k = segment k), the token alignment, the refusals and
the server's lifecycle are exercised without any model. No story text is read; every sentence is invented here.
"""

import gzip
import hashlib
import json
import re
import socketserver
import subprocess
import sys
import tomllib
import types
import urllib.request
from pathlib import Path

import pytest

from intract_features import parse as P
from intract_features import records
from intract_features.cli import StageContext, run_stage
from intract_features.parse import long_units, stanza_wrap, udpipe_client, udpipe_server
from intract_features.stages import parse_stanza, parse_udpipe

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
MODEL = "english-gum-ud-2.17-251125"
TOKEN_RE = re.compile(r"[^\W_]+|[^\w\s@]")  # "@" is never a token, so "@@@" yields no sentence
UPSTREAM_TOO_LONG = ("During tokenization, sentence longer than 1000 words was found, aborting.\n"
                     "That should only happen with presegmented input.\n"
                     "Please make sure you do not generate such long sentences.\n")


def load_cfg(models: dict | None = None) -> dict:
    cfg = tomllib.loads((CONFIG / "pipeline.toml").read_text(encoding="utf-8"))
    cfg["languages"] = tomllib.loads((CONFIG / "languages.toml").read_text(encoding="utf-8"))
    cfg["stages"] = {n: tomllib.loads((CONFIG / "stages" / f"{n}.toml").read_text(encoding="utf-8"))
                     for n in ("parse_stanza", "parse_udpipe")}
    cfg["models"] = models or {}
    return cfg


def make_doc(story_id="S1", pages=("Tom ran home. He was happy!", "Then\nhe ate du pain.")):
    return records.Document(story_id=story_id, lang="en-us", level="young", kind="generated", title="T",
                            pages=tuple(pages))


def spans_of(text: str, sentences: list[str]) -> list[tuple[int, int]]:
    """[start, end) of each sentence, extended over the whitespace after it."""
    spans, pos = [], 0
    for s in sentences:
        start = text.index(s, pos)
        end = start + len(s)
        while end < len(text) and text[end] == " ":
            end += 1
        spans.append((start, end))
        pos = end
    return spans


SENTS = ["Tom ran home.", "He was happy!", "Then\nhe ate du pain."]


def seg_record(doc, sentences=SENTS, **over):
    """A segments record as the sat stage writes it for the English source."""
    rec = {"story_id": doc.story_id, "lang": doc.lang, "segmenter": "sat", "is_source": True,
           "text_sha256": hashlib.sha256(doc.text.encode("utf-8")).hexdigest(),
           "sentences": [{"start": s, "end": e} for s, e in spans_of(doc.text, sentences)]}
    rec.update(over)
    return rec


RULES = P.SegmentRules(source_segmenter="sat", translation_segmenter="union", allow_sat_alone=False)


# ------------------------------------------------------------------------------------------- fake stanza, torch


class FWord:
    def __init__(self, wid, text, lemma, head):
        self.id, self.text, self.lemma, self.head = wid, text, lemma, head
        self.upos = "PUNCT" if not text[0].isalnum() else "X"
        self.xpos, self.feats = None, None
        self.deprel = "root" if head == 0 else ("punct" if self.upos == "PUNCT" else "dep")


class FToken:
    def __init__(self, words, text):
        self.words, self.text, self.id = words, text, tuple(w.id for w in words)


class FSentence:
    def __init__(self, tokens):
        self.tokens = tokens

    @property
    def words(self):
        return [w for t in self.tokens for w in t.words]


class FakeDepparse:
    config = {"batch_size": 5000, "deep_biaff_hidden_dim": 400}

    def get_known_relations(self):
        return ["root", "dep", "punct"]


class FakePipeline:
    instances: list = []
    fail_lemma_pretrain = False
    no_lemmas = False
    mwt = {"du": ["de", "le"]}

    def __init__(self, **kwargs):
        if FakePipeline.fail_lemma_pretrain and "lemma_pretrain_path" not in kwargs:
            raise FileNotFoundError("Pretrained file /nlp/scr/horatio/stanza_resources/el/pretrain/conll17.pt does "
                                    "not exist, and no text/xz file was provided")
        self.kwargs = kwargs
        self.processors = {"depparse": FakeDepparse()}
        FakePipeline.instances.append(self)

    def _sentence(self, paragraph):
        tokens, wid = [], 0
        for form in TOKEN_RE.findall(paragraph):
            words = []
            for part in self.mwt.get(form, [form]):
                wid += 1
                words.append(FWord(wid, part, None if self.no_lemmas else part.lower(), 0 if wid == 1 else 1))
            tokens.append(FToken(words, form))
        return FSentence(tokens) if tokens else None

    def __call__(self, text):
        # Stanza's paragraph rule (models/tokenization/data.py, NEWLINE_WHITESPACE_RE)
        paragraphs = re.split(r"\n[\s\u0080-\u009f]*\n", text)
        return types.SimpleNamespace(sentences=[s for s in map(self._sentence, paragraphs) if s is not None])


@pytest.fixture
def fake_stanza(monkeypatch):
    FakePipeline.instances, FakePipeline.fail_lemma_pretrain, FakePipeline.no_lemmas = [], False, False
    stanza = types.ModuleType("stanza")
    stanza.__version__ = "1.15.0"
    stanza.Pipeline = FakePipeline
    torch = types.ModuleType("torch")
    torch.__version__ = "fake"
    torch.threads = 8
    torch.set_num_threads = lambda n: setattr(torch, "threads", n)
    torch.get_num_threads = lambda: torch.threads
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "stanza", stanza)
    monkeypatch.setitem(sys.modules, "torch", torch)
    return stanza


def _md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


@pytest.fixture
def stanza_models(tmp_path):
    """A model directory with tiny files and a resources.json whose MD5s match them; returns (dir, resources, pin).

    The pin also holds each file's SHA-256 under "files", as models.lock.json does.
    """
    root = tmp_path / "stanza"
    blobs = {("en", "tokenize", "gum_nocharlm"): b"tok", ("en", "tokenize", "gum_charlm"): b"tokc",
             ("en", "mwt", "gum"): b"mwt", ("en", "pos", "gum_nocharlm"): b"pos", ("en", "pos", "gum_charlm"): b"posc",
             ("en", "lemma", "gum_nocharlm"): b"lem", ("en", "depparse", "gum_nocharlm"): b"dep",
             ("en", "depparse", "gum_charlm"): b"depc", ("en", "pretrain", "conll17"): b"pre",
             ("el", "tokenize", "gdt_nocharlm"): b"eltok", ("el", "mwt", "gdt"): b"elmwt",
             ("el", "pos", "gdt_nocharlm"): b"elpos", ("el", "lemma", "gdt_nocharlm"): b"ellem",
             ("el", "depparse", "gdt_nocharlm"): b"eldep", ("el", "pretrain", "conll17"): b"elpre",
             ("zz", "pos", "t_nocharlm"): b"zzpos"}
    resources: dict = {"url": "fake"}
    pre = [{"model": "pretrain", "package": "conll17"}]
    charlm = [{"model": "forward_charlm", "package": "1billion"}]
    files = {}
    for (lang, proc, pkg), blob in blobs.items():
        path = root / lang / proc / f"{pkg}.pt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        meta = {"md5": _md5(blob)}
        if proc in ("pos", "depparse") and lang != "zz":
            meta["dependencies"] = pre
        if proc == "tokenize" and pkg.endswith("_charlm"):
            meta["dependencies"] = charlm
        resources.setdefault(lang, {}).setdefault(proc, {})[pkg] = meta
        files[f"{lang}/{proc}/{pkg}.pt"] = {"sha256": hashlib.sha256(blob).hexdigest(), "md5": _md5(blob)}
    resources["en"]["packages"] = {"gum": {"tokenize": "gum_nocharlm", "mwt": "gum", "pos": "gum_charlm",
                                           "lemma": "gum_nocharlm", "depparse": "gum_charlm"}}
    resources["el"]["packages"] = {"gdt": {"tokenize": "gdt_nocharlm", "mwt": "gdt", "pos": "gdt_nocharlm",
                                           "lemma": "gdt_nocharlm", "depparse": "gdt_nocharlm"}}
    rj = root / "resources.json"
    rj.write_text(json.dumps(resources), encoding="utf-8")
    pin = {"version": "1.15.0", "resources_json_sha256": records.sha256_file(rj), "files": files}
    return root, resources, pin


def write_inputs(work: Path, docs, segs) -> None:
    records.write_jsonl(records.artefact_path(work, "en-us", "documents", 0, 1), [d.to_json() for d in docs])
    records.write_jsonl(records.artefact_path(work, "en-us", "segments", 0, 1), segs)


# --------------------------------------------------------------------------------------------- sentence units


def test_flatten_line_breaks_keeps_length():
    s = "a\nb\r\nc\u2028d\x85e"
    flat = P.flatten_line_breaks(s)
    assert len(flat) == len(s)
    assert flat == "a b  c d e"
    assert not set(flat) & P.LINE_BREAKS


def test_document_units_strip_flatten_and_offsets():
    doc = make_doc()
    units = P.document_units(doc, spans_of(doc.text, SENTS))
    assert [u.k for u in units] == [0, 1, 2]
    assert [u.text for u in units] == ["Tom ran home.", "He was happy!", "Then he ate du pain."]
    for u in units:  # offsets refer to Document.text, line breaks flattened one for one
        assert P.flatten_line_breaks(doc.text[u.start:u.end]) == u.text


def test_document_units_can_refuse_a_line_break_instead():
    doc = make_doc()
    with pytest.raises(ValueError, match="line break"):
        P.document_units(doc, spans_of(doc.text, SENTS), line_breaks="refuse")
    plain = make_doc(pages=("One. Two.",))
    assert len(P.document_units(plain, [(0, 4), (5, 9)], line_breaks="refuse")) == 2
    with pytest.raises(ValueError, match="line_breaks"):
        P.document_units(plain, [(0, 4), (5, 9)], line_breaks="keep")


def test_document_units_rejects_bad_spans_and_uncovered_text():
    doc = make_doc()
    with pytest.raises(ValueError, match="out of order"):
        P.document_units(doc, [(5, 10), (8, 12)])
    with pytest.raises(ValueError, match="outside"):
        P.document_units(doc, [(0, len(doc.text) + 1)])
    with pytest.raises(ValueError, match="every sentence"):
        P.document_units(doc, [(0, 13)])  # the rest of the text is in no sentence
    assert len(P.document_units(doc, [(0, 13)], allow_uncovered_text=True)) == 1


def test_document_units_keeps_an_empty_unit():
    doc = make_doc(pages=("One.   Two.",))
    units = P.document_units(doc, [(0, 4), (4, 7), (7, 11)])
    assert [u.text for u in units] == ["One.", "", "Two."]
    assert units[1].start == units[1].end


def test_spans_from_record_accepts_two_shapes_and_refuses_others():
    assert P.spans_from_record({"sentences": [{"start": 0, "end": 3, "page_start": 0}]}, "sentences") == [(0, 3)]
    assert P.spans_from_record({"sentences": [[0, 3, 0, 0], [4, 9]]}, "sentences") == [(0, 3), (4, 9)]
    sat_like = {"sentence_fields": ["start", "end", "page_start", "page_end"], "sentences": [[0, 3, 0, 0]]}
    assert P.spans_from_record(sat_like, "sentences") == [(0, 3)]
    with pytest.raises(ValueError, match="must lead"):
        P.spans_from_record({**sat_like, "sentence_fields": ["page_start", "page_end", "start", "end"]}, "sentences")
    with pytest.raises(ValueError, match="no 'sentences'"):
        P.spans_from_record({"story_id": "S1", "spans": []}, "sentences")
    with pytest.raises(ValueError, match="neither"):
        P.spans_from_record({"sentences": [3]}, "sentences")
    with pytest.raises(ValueError, match="non-integer"):
        P.spans_from_record({"sentences": [[0.0, 3]]}, "sentences")


def _join(docs, recs, rules=RULES):
    return list(P.join_units(docs, recs, lang="en-us", field_name="sentences", rules=rules))


def test_join_units_checks_pairing():
    d1, d2 = make_doc("S1"), make_doc("S2")
    pairs = _join([d1, d2], [seg_record(d2), seg_record(d1)])
    assert [d.story_id for d, _ in pairs] == ["S1", "S2"]
    with pytest.raises(ValueError, match="no segments record"):
        _join([d1, d2], [seg_record(d1)])
    with pytest.raises(ValueError, match="two segments records"):
        _join([d1], [seg_record(d1), seg_record(d1)])
    with pytest.raises(ValueError, match="not 'en-us'"):
        _join([d1], [seg_record(d1, lang="fr-fr")])
    with pytest.raises(ValueError, match="not 'en-us'"):
        _join([d1], [{k: v for k, v in seg_record(d1).items() if k != "lang"}])


def test_join_units_refuses_a_stale_segments_record():
    d1 = make_doc("S1")
    with pytest.raises(ValueError, match="stale"):
        _join([d1], [seg_record(d1, text_sha256="0" * 64)])
    with pytest.raises(ValueError, match="stale"):
        _join([d1], [{k: v for k, v in seg_record(d1).items() if k != "text_sha256"}])


def test_join_units_takes_only_the_registered_segmentation():
    d1 = make_doc("S1")
    with pytest.raises(ValueError, match="not the registered segmentation of the English source"):
        _join([d1], [seg_record(d1, segmenter="union")])
    # a translation's SaT record is the union segmenter's input, not its sentences
    with pytest.raises(ValueError, match="not the registered segmentation of a translation"):
        _join([d1], [seg_record(d1, is_source=False)])
    assert len(_join([d1], [seg_record(d1, is_source=False, segmenter="union")])) == 1
    sat_alone = P.SegmentRules.from_config({"source_segmenter": "sat", "translation_segmenter": "union",
                                            "allow_sat_alone": True})
    assert len(_join([d1], [seg_record(d1, is_source=False)], sat_alone)) == 1
    with pytest.raises(ValueError, match="is_source"):
        _join([d1], [{k: v for k, v in seg_record(d1).items() if k != "is_source"}])


# ------------------------------------------------------------------------------------------ token alignment


def _tokens(forms, mwt=None):
    mwt = mwt or {}
    toks, wid = [], 0
    for f in forms:
        words = []
        for part in mwt.get(f, [f]):
            wid += 1
            words.append(P.Word(id=wid, form=part, lemma=part.lower(), upos="X", head=0 if wid == 1 else 1,
                                deprel="root" if wid == 1 else "dep"))
        toks.append(P.Token(form=f, words=words))
    return toks


def _unit(text, start=0):
    return P.Unit(k=0, start=start, end=start + len(text), text=text)


def test_align_tokens_offsets_and_misses():
    unit = P.Unit(k=0, start=10, end=23, text="Tom ran home.")
    toks = _tokens(["Tom", "XYZ", "ran", "home", "."])
    assert P.align_tokens(unit, toks, max_skip=16) == 1
    assert [(t.start, t.end) for t in toks] == [(10, 13), (None, None), (14, 17), (18, 22), (22, 23)]


def test_align_tokens_ignores_whitespace_the_parser_normalised():
    # Stanza's normalize_token maps NBSP and NNBSP inside a token to a space (the reviewer's reproduction)
    text = "Visit www.example\u00a0long\u00a0address\u00a0here.org today ."
    toks = _tokens(["Visit", "www.example long address here.org", "today", "."])
    assert P.align_tokens(_unit(text), toks, 16) == 0
    assert text[toks[1].start:toks[1].end] == "www.example\u00a0long\u00a0address\u00a0here.org"
    assert (toks[3].start, toks[3].end) == (len(text) - 1, len(text))
    t2 = "It cost 10\u202f000 coins ."
    toks = _tokens(["It", "cost", "10 000", "coins", "."])
    assert P.align_tokens(_unit(t2), toks, 16) == 0 and t2[toks[2].start:toks[2].end] == "10\u202f000"
    # Chinese, Japanese and Korean: Stanza removes the space inside a token
    t3 = "東京 タワー へ 行く"
    toks = _tokens(["東京タワー", "へ", "行く"])
    assert P.align_tokens(_unit(t3), toks, 16) == 0 and t3[toks[0].start:toks[0].end] == "東京 タワー"


def test_align_tokens_skips_a_dropped_character():
    text = "Hello ~ world ."
    toks = _tokens(["Hello", "world", "."])
    assert P.align_tokens(_unit(text), toks, 16) == 0
    assert [text[t.start:t.end] for t in toks] == ["Hello", "world", "."]


def test_align_tokens_never_places_a_token_inside_a_changed_one():
    # The old aligner bound the final "." to the first full stop inside the changed token; it must go to the end.
    text = "Visit a.b.c.d.e."
    toks = _tokens(["Visit", "X.Y.Z.W.V", "."])
    assert P.align_tokens(_unit(text), toks, 16) == 0
    assert (toks[2].start, toks[2].end) == (15, 16)
    assert text[toks[1].start:toks[1].end] == "a.b.c.d.e"  # one changed token takes the gap, inexactly
    # a changed token of another length: the "." could sit at several full stops, so nothing is guessed
    text = "Visit a.b.c.d.e.f.g."
    toks = _tokens(["Visit", "X.Y.Z", "."])
    assert P.align_tokens(_unit(text), toks, 16) == 2
    assert toks[2].start is None
    # two changed tokens in a row keep no offsets, and the alignment resumes after them
    text = "Visit a.b.c.d.e f.g now."
    toks = _tokens(["Visit", "X.Y.Z.W.V", "Q.R", "now", "."])
    assert P.align_tokens(_unit(text), toks, 16) == 2
    assert [text[t.start:t.end] for t in (toks[0], toks[3], toks[4])] == ["Visit", "now", "."]


def test_align_tokens_offsets_increase_and_hold_their_forms():
    text = "Ann said, \u201cno, no, no, no!\u201d and left."
    forms = ["Ann", "said", ",", "\u201c", "no", ",", "no", ",", "no", ",", "no", "!", "\u201d", "and", "left", "."]
    toks = _tokens(forms)
    assert P.align_tokens(_unit(text, 7), toks, 16) == 0
    ends = [t.end for t in toks]
    assert ends == sorted(ends) and all(text[t.start - 7:t.end - 7] == t.form for t in toks)


def test_parse_document_counts_inexact_offsets():
    doc = make_doc(pages=("Visit a.b.c.d.e.",))
    units = P.document_units(doc, [(0, len(doc.text))])
    _, stats = P.parse_document(doc, units, lambda texts: [_tokens(["Visit", "X.Y.Z.W.V", "."])], max_skip=16)
    assert stats["offset_misses"] == 0 and stats["offset_inexact"] == 1


# ------------------------------------------------------------------------------------------ CoNLL-U contract


def test_format_and_read_round_trip(tmp_path):
    doc = make_doc()
    units = P.document_units(doc, spans_of(doc.text, SENTS))
    parses = [_tokens(TOKEN_RE.findall(u.text), mwt={"du": ["de", "le"]}) for u in units]
    parses[1] = None  # the parser returned nothing for sentence 1
    for u, p in zip(units, parses, strict=True):
        if p:
            assert P.align_tokens(u, p, 16) == 0
    text = P.format_document(doc.story_id, units, parses, doc.text)
    assert text.startswith("# newdoc id = S1\n# sent_id = S1-0\n# text = Tom ran home.\n# span = 0:13\n")
    assert "# sent_id = S1-1\n# text = He was happy!\n# span = 14:27\n# parse = empty\n\n" in text
    assert "\tSpaceAfter=No|TokenRange=8:12\n" in text  # "home" is followed by "."
    assert re.search(r"^4-5\tdu\t_\t_\t_\t_\t_\t_\t_\tTokenRange=\d+:\d+$", text, re.M)
    path = tmp_path / "p.conllu.gz"
    with P.ConlluShardWriter(path) as w:
        w.write(text)
    (back,) = list(P.read_conllu(path))
    assert back.story_id == "S1" and [s.k for s in back.sentences] == [0, 1, 2]
    assert back.sentences[1].empty and back.sentences[1].tokens == [] and back.sentences[1].refused is None
    s2 = back.sentences[2]
    assert s2.text == "Then he ate du pain." and s2.span == (units[2].start, units[2].end)
    assert [w.form for w in s2.words] == ["Then", "he", "ate", "de", "le", "pain", "."]
    for tok in s2.tokens:
        assert doc.text[tok.start:tok.end] == tok.form


def test_a_refused_unit_keeps_a_marked_empty_block(tmp_path):
    doc = make_doc(pages=("Short one. " + " ".join(["word"] * 8) + ".",))
    units = P.document_units(doc, [(0, 11), (11, len(doc.text))])
    text = P.format_document("S1", units, [_tokens(["Short", "one", "."]), P.Refused("too long")], doc.text)
    assert "# span = 11:" in text and "# refused = too long\n# parse = empty\n\n" in text
    path = tmp_path / "r.conllu"
    path.write_text(text, encoding="utf-8", newline="\r\n")  # CRLF, as a converting checkout would leave it
    (back,) = list(P.read_conllu(path))
    assert back.sentences[1].empty and back.sentences[1].refused == "too long" and not back.sentences[1].tokens
    assert back.sentences[0].span == (0, 10) and [t.form for t in back.sentences[0].tokens] == ["Short", "one", "."]


def test_read_conllu_refuses_ids_out_of_sequence(tmp_path):
    p = tmp_path / "bad.conllu"
    p.write_text("# newdoc id = S1\n# sent_id = S1-1\n# text = A\n1\tA\ta\tX\t_\t_\t0\troot\t_\t_\n\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="out of sequence"):
        list(P.read_conllu(p))


_WORD = "1\tA\ta\tX\t_\t_\t0\troot\t_\t_\n"


# The checks io/conllu.py made before the artefact format was consolidated on this module (one reader, one writer).
@pytest.mark.parametrize("content, message", [
    ("# sent_id = a-0\n# text = A\n" + _WORD + "\n", "before any"),
    ("# newdoc id = a\n# sent_id = b-0\n# text = A\n" + _WORD + "\n", "out of sequence"),
    ("# newdoc id = a\n# sent_id = a-0\n# text = A\n" + _WORD + "# late\n\n", "among the word lines"),
    ("# newdoc id = a\n# sent_id = a-0\n# text = A\n# span = 0:1\n\n", "needs word lines"),
    ("# newdoc id = a\n# sent_id = a-0\n# text = A\n# parse = empty\n" + _WORD + "\n", "needs word lines"),
    ("# newdoc id = a\n# sent_id = a-0\n# text = A\n" + _WORD + "\n# newdoc id = a\n# sent_id = a-0\n# text = A\n"
     + _WORD + "\n", "appears twice"),
    ("# newdoc id = a\n# sent_id = a-0\n# text = A\n1\tA\ta\n\n", "columns"),
])
def test_read_conllu_refuses_malformed_blocks(tmp_path, content, message):
    p = tmp_path / "bad.conllu"
    p.write_text(content, encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match=message):
        list(P.read_conllu(p))


def test_format_sentence_refuses_bad_word_ids():
    toks = _tokens(["A", "b"])
    toks[1].words[0].id = 3
    with pytest.raises(ValueError, match="not 1..n"):
        P.format_sentence("S1", P.Unit(0, 0, 3, "A b"), toks, "A b")


def test_tokens_from_conllu_multiword_and_empty_nodes():
    lines = ["1-2\tdu\t_\t_\t_\t_\t_\t_\t_\t_", "1\tde\tde\tADP\t_\t_\t3\tcase\t_\t_",
             "2\tle\tle\tDET\t_\t_\t3\tdet\t_\t_", "2.1\tx\tx\tX\t_\t_\t_\t_\t_\t_",
             "3\tpain\tpain\tNOUN\t_\t_\t0\troot\t_\t_"]
    toks = P.tokens_from_conllu(lines)
    assert [t.form for t in toks] == ["du", "pain"] and [len(t.words) for t in toks] == [2, 1]
    with pytest.raises(ValueError, match="10"):
        P.tokens_from_conllu(["1\tA"])


def test_shard_writer_is_atomic_reproducible_and_can_reject(tmp_path):
    path = tmp_path / "x" / "shard-0-of-1.conllu.gz"
    with P.ConlluShardWriter(path) as w:
        w.write("# newdoc id = S1\n")
    first = path.read_bytes()
    with P.ConlluShardWriter(path) as w:
        w.write("# newdoc id = S1\n")
    assert path.read_bytes() == first  # gzip mtime 0, no file name
    assert gzip.decompress(first) == b"# newdoc id = S1\n"
    other = tmp_path / "y.conllu.gz"
    with pytest.raises(KeyError), P.ConlluShardWriter(other) as w:
        w.write("partial")
        raise KeyError("killed")
    assert not other.exists() and not other.with_name(other.name + ".tmp").exists()
    with P.ConlluShardWriter(other) as w:
        w.write("bad")
        assert w.reject() == other.with_name(other.name + P.FAILED_SUFFIX)
    assert not other.exists() and other.with_name(other.name + ".failed").exists()


def test_shard_writer_never_leaves_an_earlier_run_standing(tmp_path):
    path = tmp_path / "shard-0-of-1.conllu"
    with P.ConlluShardWriter(path) as w:
        w.write("good\n")
    with P.ConlluShardWriter(path) as w:  # a rerun whose check fails
        w.write("new\n")
        w.reject()
    assert not path.exists() and path.with_name(path.name + ".failed").read_text(encoding="utf-8") == "new\n"
    with P.ConlluShardWriter(path) as w:  # a later run that succeeds clears the failed output
        w.write("fixed\n")
    assert path.read_text(encoding="utf-8") == "fixed\n" and not path.with_name(path.name + ".failed").exists()
    with pytest.raises(OSError), P.ConlluShardWriter(path) as w:  # a run that dies leaves nothing behind
        raise OSError("node lost")
    assert not path.exists()


def test_parse_document_counts_and_empty_units():
    doc = make_doc(pages=("One two.   Three\nfour!",))
    units = P.document_units(doc, [(0, 8), (8, 11), (11, len(doc.text))])
    seen = []

    def fake_parse(texts):
        seen.append(texts)
        return [_tokens(TOKEN_RE.findall(t)) for t in texts]

    text, stats = P.parse_document(doc, units, fake_parse, max_skip=16)
    assert seen == [["One two.", "Three four!"]]  # one call per text, the empty unit never sent
    assert stats["sentences"] == 3 and stats["empty_units"] == 1 and stats["units_with_line_breaks"] == 1
    assert stats["words"] == 6 and stats["whitespace_tokens"] == 4 and stats["offset_misses"] == 0
    assert stats["calls"] == 1 and stats["refused_units"] == 0
    assert "# sent_id = S1-1\n# text = \n# span = 11:11\n# parse = empty" in text
    counts = P.ParseCounts()
    counts.add(stats)
    json.dumps(counts.as_dict(), allow_nan=False)


def test_parse_document_refuses_a_malformed_parser_result():
    doc = make_doc(pages=("One two.",))
    units = P.document_units(doc, [(0, 8)])
    with pytest.raises(TypeError, match="not a token list"):
        P.parse_document(doc, units, lambda texts: ["1\tOne"], max_skip=16)
    with pytest.raises(RuntimeError, match="returned 0 sentences for 1"):
        P.parse_document(doc, units, lambda texts: [], max_skip=16)


def _docs_of_sizes(sizes):
    docs, items = [], []
    for i, n in enumerate(sizes):
        doc = make_doc(f"D{i}", pages=(" ".join(f"Word{j} here." for j in range(n)),))
        spans, pos = [], 0
        for j in range(n):
            s = f"Word{j} here."
            start = doc.text.index(s, pos)
            spans.append((start, start + len(s)))
            pos = start + len(s)
        docs.append(doc)
        items.append((doc, P.document_units(doc, spans)))
    return docs, items


def test_parse_shard_groups_texts_into_calls_and_keeps_whole_calls(tmp_path):
    _, items = _docs_of_sizes([2, 2, 5, 1])
    calls = []

    def fake_parse(texts):
        calls.append(len(texts))
        return [_tokens(TOKEN_RE.findall(t)) for t in texts]

    assert [[d.story_id for d, _ in g] for g in P.call_groups(items, 4)] == [["D0", "D1"], ["D2"], ["D3"]]
    seen = []
    counts, kept = P.parse_shard(tmp_path / "a.conllu", items, fake_parse, max_skip=16, keep_first=1,
                                 sentences_per_call=4, observe=lambda d, u, p: seen.append((d.story_id, len(p))))
    assert calls == [4, 5, 1] and counts.calls == 3 and counts.documents == 4
    assert [d.story_id for d, _, _ in kept] == ["D0", "D1"]  # completed to the whole first call
    assert seen == [("D0", 2), ("D1", 2), ("D2", 5), ("D3", 1)]
    grouped = (tmp_path / "a.conllu").read_text(encoding="utf-8")
    calls.clear()
    P.parse_shard(tmp_path / "b.conllu", items, fake_parse, max_skip=16)
    assert calls == [2, 2, 5, 1]  # the default: one call per text
    assert (tmp_path / "b.conllu").read_text(encoding="utf-8") == grouped  # this fake parser ignores its neighbours


def test_parse_shard_check_keeps_a_failed_shard_and_removes_the_old_one(tmp_path):
    _, items = _docs_of_sizes([1])
    out = tmp_path / "s.conllu"
    out.write_text("an earlier run's parse\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="bad parse; output kept as"):
        P.parse_shard(out, items, lambda t: [_tokens(["Word0", "here", "."])], max_skip=16, check=lambda c: "bad parse")
    assert not out.exists() and out.with_name(out.name + ".failed").exists()


def test_model_pin_lookup():
    assert P.model_pin({"models": {"a": {"x": 1}}}, "a") == {"x": 1}
    assert P.model_pin({"models": {"models": {"a": {"x": 2}}}}, "a") == {"x": 2}
    with pytest.raises(P.PinError, match="no entry 'b'"):
        P.model_pin({"models": {}}, "b")


def test_file_digests_match_hashlib(tmp_path):
    f = tmp_path / "blob"
    f.write_bytes(b"abc" * 1000)
    assert P.file_digests(f, chunk=7) == (hashlib.md5(b"abc" * 1000).hexdigest(),
                                          hashlib.sha256(b"abc" * 1000).hexdigest())
    assert P.md5_file(f) == hashlib.md5(b"abc" * 1000).hexdigest()


# ---------------------------------------------------------------------------------------------- Stanza wrapper


def test_resolve_processors_from_languages_toml(stanza_models):
    _, resources, _ = stanza_models
    packages = load_cfg()["languages"]["en-us"]["stanza_packages"]
    got = stanza_wrap.resolve_processors(resources, "en", packages, "nocharlm")
    # languages.toml's tokenize = "gum" resolves through the gum bundle to the nocharlm tokeniser
    assert got == {"tokenize": "gum_nocharlm", "mwt": "gum", "pos": "gum_nocharlm", "lemma": "gum_nocharlm",
                   "depparse": "gum_nocharlm"}


def test_resolve_processors_refuses_what_stanza_would_do_silently(stanza_models):
    _, resources, _ = stanza_models
    base = {"tokenize": "gum_nocharlm", "mwt": "gum", "pos": "gum_nocharlm", "lemma": "gum_nocharlm",
            "depparse": "gum_nocharlm"}
    with pytest.raises(ValueError, match="tier"):  # the bundle maps pos to a charlm model
        stanza_wrap.resolve_processors(resources, "en", {**base, "pos": "gum"}, "nocharlm")
    with pytest.raises(ValueError, match="no depparse package 'ewt_nocharlm'"):
        stanza_wrap.resolve_processors(resources, "en", {**base, "depparse": "ewt_nocharlm"}, "nocharlm")
    with pytest.raises(ValueError, match="would add mwt"):
        stanza_wrap.resolve_processors(resources, "en", {k: v for k, v in base.items() if k != "mwt"}, "nocharlm")
    with pytest.raises(ValueError, match="names no Stanza package"):
        stanza_wrap.resolve_processors(resources, "en", {"tokenize": "gum_nocharlm", "mwt": "gum"}, "nocharlm")
    assert stanza_wrap.resolve_processors(resources, "en", {**base, "lemma": "identity"}, "nocharlm")["lemma"] == \
        "identity"


EN_PROCS = {"tokenize": "gum_nocharlm", "mwt": "gum", "pos": "gum_nocharlm", "lemma": "gum_nocharlm",
            "depparse": "gum_nocharlm"}


def test_model_files_follow_dependencies_and_verify(stanza_models):
    root, resources, _ = stanza_models
    files = stanza_wrap.model_files(resources, "en", EN_PROCS, root)
    assert sorted((f.processor, f.package) for f in files) == sorted([*EN_PROCS.items(), ("pretrain", "conll17")])
    rows = stanza_wrap.verify_model_files(files, root)
    assert {r["file"] for r in rows} >= {"en/pretrain/conll17.pt", "en/depparse/gum_nocharlm.pt"}
    (root / "en" / "depparse" / "gum_nocharlm.pt").write_bytes(b"tampered")
    (root / "en" / "mwt" / "gum.pt").unlink()
    with pytest.raises(P.PinError) as err:
        stanza_wrap.verify_model_files(files, root)
    assert "en/depparse/gum_nocharlm.pt has MD5" in str(err.value) and "en/mwt/gum.pt is missing" in str(err.value)


def test_model_files_verify_their_sha256_pins(stanza_models):
    root, resources, pin = stanza_models
    files = stanza_wrap.model_files(resources, "en", EN_PROCS, root)
    rows = stanza_wrap.verify_model_files(files, root, pin["files"])
    assert all(r["sha256"] == pin["files"][r["file"]]["sha256"] for r in rows)
    partial = {k: v for k, v in pin["files"].items() if k != "en/pretrain/conll17.pt"}
    with pytest.raises(P.PinError, match="en/pretrain/conll17.pt has no SHA-256 pin"):
        stanza_wrap.verify_model_files(files, root, partial)
    wrong = {**pin["files"], "en/lemma/gum_nocharlm.pt": {"sha256": "0" * 64}}
    with pytest.raises(P.PinError, match="en/lemma/gum_nocharlm.pt has SHA-256"):
        stanza_wrap.verify_model_files(files, root, wrong)


def test_load_resources_checks_its_pin(stanza_models):
    root, resources, pin = stanza_models
    assert stanza_wrap.load_resources(root / "resources.json", pin["resources_json_sha256"]) == resources
    with pytest.raises(P.PinError, match="SHA-256"):
        stanza_wrap.load_resources(root / "resources.json", "0" * 64)
    with pytest.raises(P.PinError, match="missing"):
        stanza_wrap.load_resources(root / "nope.json", "0" * 64)


def test_pipeline_kwargs_and_the_batch_switch(stanza_models):
    root, _, _ = stanza_models
    scfg = load_cfg()["stages"]["parse_stanza"]
    kw = stanza_wrap.pipeline_kwargs("en", EN_PROCS, root, root / "resources.json", scfg)
    assert kw["package"] is None and kw["use_gpu"] is False and kw["download_method"] is None
    assert kw["tokenize_no_ssplit"] is True and "depparse_batch_size" not in kw  # Stanza's own batch by default
    capped = {**scfg, "batch": {"depparse_batch_size": 1000, "depparse_min_length_to_batch_separately": 0}}
    assert stanza_wrap.pipeline_kwargs("en", EN_PROCS, root, root, capped)["depparse_batch_size"] == 1000
    kw = stanza_wrap.pipeline_kwargs("th", {**EN_PROCS, "lemma": "identity"}, root, root, scfg)
    assert kw["lemma_use_identity"] is True


EL_PROCS = {"tokenize": "gdt_nocharlm", "mwt": "gdt", "pos": "gdt_nocharlm", "lemma": "gdt_nocharlm",
            "depparse": "gdt_nocharlm"}
BASE_KW = {"lang": "el", "package": None, "tokenize_no_ssplit": True, "use_gpu": False, "download_method": None,
           "logging_level": "WARN"}


def test_greek_workaround_only_on_the_missing_pretrain(stanza_models):
    root, resources, _ = stanza_models
    FakePipeline.instances, FakePipeline.fail_lemma_pretrain = [], True
    try:
        nlp, wa = stanza_wrap.build_pipeline(FakePipeline, dict(BASE_KW), resources, "el", EL_PROCS, root)
        path = root / "el" / "pretrain" / "conll17.pt"
        assert nlp.kwargs == {**BASE_KW, "lemma_pretrain_path": str(path)}  # every other argument unchanged
        assert wa["lemma_pretrain_path"] == "el/pretrain/conll17.pt" and "Pretrained file" in wa["error"]
        with pytest.raises(FileNotFoundError, match="Pretrained file"):  # no lemma model to hand a pretrain to
            stanza_wrap.build_pipeline(FakePipeline, dict(BASE_KW), resources, "el", {**EL_PROCS, "lemma": "identity"},
                                       root)
        with pytest.raises(FileNotFoundError, match="Pretrained file"):  # the POS package declares no pretrain
            stanza_wrap.build_pipeline(FakePipeline, {**BASE_KW, "lang": "zz"}, resources, "zz",
                                       {**EL_PROCS, "pos": "t_nocharlm"}, root)
        path.unlink()
        with pytest.raises(FileNotFoundError, match="for the lemmatiser workaround is missing"):
            stanza_wrap.build_pipeline(FakePipeline, dict(BASE_KW), resources, "el", EL_PROCS, root)
    finally:
        FakePipeline.fail_lemma_pretrain = False
    nlp, wa = stanza_wrap.build_pipeline(FakePipeline, {**BASE_KW, "lang": "en"}, resources, "en", EN_PROCS, root)
    assert wa is None and nlp.kwargs == {**BASE_KW, "lang": "en"}

    def other_error(**kwargs):
        raise FileNotFoundError("Could not find model file")

    with pytest.raises(FileNotFoundError, match="Could not find"):
        stanza_wrap.build_pipeline(other_error, {}, resources, "el", EL_PROCS, root)


def test_padded_batches_mirror_stanza_with_the_root_node():
    # data_to_batches: lengths count ROOT, so a 150-word sentence (151) is batched alone and one of 149 is not
    assert stanza_wrap.padded_batches([150], 5000, 150) == [(1, 151)]
    assert stanza_wrap.padded_batches([149, 149], 5000, 150) == [(2, 150)]
    assert stanza_wrap.padded_batches([3, 200, 5, 2], 9, 150) == [(1, 201), (1, 6), (2, 4)]  # 6 + 4 > 9
    assert stanza_wrap.padded_batches([4, 4], 10, 150) == [(2, 5)]
    assert stanza_wrap.padded_batches([4, 4], 9, 150) == [(1, 5), (1, 5)]


def test_label_scorer_estimate_and_ranking():
    # one 5,500-word loop: n L (D+1) R + 2 n L^2 R floats with L = 5,501, D = 400, R = 51
    assert stanza_wrap.label_scorer_floats(1, 5501, 400, 51) == 5501 * 401 * 51 + 2 * 5501 ** 2 * 51
    parser = stanza_wrap.StanzaParser(None, {"effective_depparse": {
        "batch_size": 5000, "min_length_to_batch_separately": 150, "relations": 51, "deep_biaff_hidden_dim": 400}})
    # a 2,000-word unit outweighs 35 sentences of 140 words, although it pads fewer words (2,001 against 4,935)
    pre = parser.preflight([[" ".join(["w"] * 2000)] + [" ".join(["w"] * 140)] * 35], spaced=True)
    assert pre["estimated"] and (pre["sentences"], pre["padded_length"]) == (1, 2001)
    assert pre["estimated_label_scorer_mb"] == pytest.approx(
        stanza_wrap.label_scorer_floats(1, 2001, 400, 51) * 4 / 2**20)
    assert stanza_wrap.StanzaParser(None, {}).preflight([["a b"]], spaced=True)["estimated"] is False


def test_word_proxy_overestimates_words():
    assert stanza_wrap.word_proxy("Don't go, Tom!", spaced=True) == 7  # Don ' t go , Tom !
    assert stanza_wrap.word_proxy("我们 去 学校", spaced=False) == 5


def test_stanza_parser_end_to_end_with_fakes(fake_stanza, stanza_models):
    root, _, pin = stanza_models
    cfg = load_cfg({"stanza-1.15.0": pin})
    parser = stanza_wrap.StanzaParser.from_config(cfg, "en-us", model_dir=root)
    assert parser.info["processors"]["tokenize"] == "gum_nocharlm" and parser.info["threads"] == 1
    assert parser.info["lemma_pretrain_workaround"] is None and parser.info["model_files_sha256_pinned"]
    assert parser.info["effective_depparse"] == {"batch_size": 5000, "min_length_to_batch_separately": 150,
                                                 "relations": 3, "deep_biaff_hidden_dim": 400}
    assert len(parser.info["model_files_verified"]) == 6
    out = parser.parse(["Tom ran.", "@@@", "He sat down."])
    assert parser.fallback_calls == 1 and out[1] is None  # a paragraph with no sentence keeps None
    assert [t.form for t in out[2]] == ["He", "sat", "down", "."]
    batch = parser.stats()["max_padded_batch"]
    assert (batch["sentences"], batch["padded_length"]) == (1, 5)  # four words and ROOT
    assert batch["estimated_label_scorer_mb"] == pytest.approx(stanza_wrap.label_scorer_floats(1, 5, 400, 3) * 4
                                                               / 2**20)
    # three sentences for two texts forces the per-sentence fallback, where one text then comes back as two
    parser.nlp = lambda text: types.SimpleNamespace(sentences=[1, 2, 3] if "\n\n" in text else [1, 2])
    with pytest.raises(RuntimeError, match="split one registered sentence"):
        parser.parse(["A b.", "C d."])


def test_stanza_parser_refuses_another_version_and_a_bad_file_pin(fake_stanza, stanza_models):
    root, _, pin = stanza_models
    fake_stanza.__version__ = "1.14.0"
    with pytest.raises(P.PinError, match="1.15.0"):
        stanza_wrap.StanzaParser.from_config(load_cfg({"stanza-1.15.0": pin}), "en-us", model_dir=root)
    fake_stanza.__version__ = "1.15.0"
    bad = {**pin, "files": {**pin["files"], "en/pos/gum_nocharlm.pt": {"sha256": "f" * 64}}}
    with pytest.raises(P.PinError, match="en/pos/gum_nocharlm.pt has SHA-256"):
        stanza_wrap.StanzaParser.from_config(load_cfg({"stanza-1.15.0": bad}), "en-us", model_dir=root)
    assert not FakePipeline.instances  # nothing was loaded


# ------------------------------------------------------------------------------------------ parse_stanza stage


def _ctx(module, cfg, work, **extra):
    return StageContext(stage=module.STAGE, config=cfg, lang="en-us", work=work, extra=extra)


def test_stage_metadata():
    s, u = parse_stanza.STAGE, parse_udpipe.STAGE
    assert (s.name, s.device, s.env, s.inputs, s.outputs) == ("parse_stanza", "cpu", "core",
                                                              ("documents", "segments"), ("parses_stanza",))
    assert (u.name, u.device, u.env, u.inputs, u.outputs) == ("parse_udpipe", "gpu", "udpipe",
                                                              ("documents", "segments"), ("parses_udpipe",))


def test_parse_stanza_stage_writes_the_contract_and_reruns_identically(fake_stanza, stanza_models, tmp_path, capsys):
    root, _, pin = stanza_models
    cfg = load_cfg({"stanza-1.15.0": pin})
    docs = [make_doc("S1"), make_doc("S2", pages=("Ann sat.", "@@@ Bob ran."))]
    segs = [seg_record(docs[0]), seg_record(docs[1], ["Ann sat.", "@@@", "Bob ran."])]
    write_inputs(tmp_path, docs, segs)
    rec = run_stage(parse_stanza, _ctx(parse_stanza, cfg, tmp_path, stanza_model_dir=root))
    out = records.artefact_path(tmp_path, "en-us", "parses_stanza", 0, 1, ext="conllu.gz")
    first = out.read_bytes()
    back = {d.story_id: d for d in P.read_conllu(out)}
    assert [s.k for s in back["S1"].sentences] == [0, 1, 2] and [s.k for s in back["S2"].sentences] == [0, 1, 2]
    assert back["S2"].sentences[1].empty  # "@@@" gave no sentence; k stays aligned with the segmentation
    for d in docs:
        for sent in back[d.story_id].sentences:
            for tok in sent.tokens:
                assert d.text[tok.start:tok.end] == tok.form
    counts = rec["counts"]
    assert counts["documents"] == 2 and counts["sentences"] == 6 and counts["empty_parses"] == 1
    assert counts["calls"] == 2 and counts["sentences_per_call"] == 0
    assert counts["parser"]["processors"]["depparse"] == "gum_nocharlm" and counts["stanza"]["lemma_missing"] == 0
    assert counts["stanza"]["preflight"]["estimated"] and "parse_stanza: preflight" in capsys.readouterr().err
    timing = tmp_path / "en-us" / "_timing" / "parse_stanza-shard-0-of-1.json"
    assert json.loads(timing.read_text(encoding="utf-8"))["counts"]["words"] == counts["words"]
    run_stage(parse_stanza, _ctx(parse_stanza, cfg, tmp_path, stanza_model_dir=root))
    assert out.read_bytes() == first  # a rerun is byte-identical


def test_parse_stanza_stage_refuses_a_stale_segmentation_before_loading_models(fake_stanza, stanza_models,
                                                                               tmp_path):
    root, _, pin = stanza_models
    doc = make_doc()
    write_inputs(tmp_path, [doc], [seg_record(doc, text_sha256="1" * 64)])
    with pytest.raises(ValueError, match="stale"):
        parse_stanza.run(_ctx(parse_stanza, load_cfg({"stanza-1.15.0": pin}), tmp_path, stanza_model_dir=root))
    assert not FakePipeline.instances


def test_parse_stanza_stage_lemma_check_keeps_a_failed_shard(fake_stanza, stanza_models, tmp_path):
    root, _, pin = stanza_models
    doc = make_doc()
    write_inputs(tmp_path, [doc], [seg_record(doc)])
    FakePipeline.no_lemmas = True
    try:
        with pytest.raises(RuntimeError, match="no lemma"):
            parse_stanza.run(_ctx(parse_stanza, load_cfg({"stanza-1.15.0": pin}), tmp_path, stanza_model_dir=root))
    finally:
        FakePipeline.no_lemmas = False
    out = records.artefact_path(tmp_path, "en-us", "parses_stanza", 0, 1, ext="conllu.gz")
    assert not out.exists() and out.with_name(out.name + ".failed").exists()


# ------------------------------------------------------------------------------------------- UDPipe server side


def test_gpu_allocated_and_reexec_path(tmp_path):
    assert udpipe_server.gpu_allocated({"CUDA_VISIBLE_DEVICES": "0"})
    assert not udpipe_server.gpu_allocated({"CUDA_VISIBLE_DEVICES": ""})
    assert not udpipe_server.gpu_allocated({"CUDA_VISIBLE_DEVICES": "-1", "SLURM_JOB_GPUS": "0"})
    assert udpipe_server.gpu_allocated({"SLURM_JOB_GPUS": "0"})
    assert not udpipe_server.gpu_allocated({})
    lib = tmp_path / "lib" / "python3.12" / "site-packages" / "nvidia" / "cusolver" / "lib"
    lib.mkdir(parents=True)
    dirs = udpipe_server.cuda_library_dirs(str(tmp_path), (3, 12))
    assert dirs == [str(lib)]
    assert udpipe_server.library_path_for_reexec({"LD_LIBRARY_PATH": "/x"}, ["/a", "/b"]) == "/a:/b:/x"
    assert udpipe_server.library_path_for_reexec({"LD_LIBRARY_PATH": "/b:/a"}, ["/a", "/b"]) is None
    assert udpipe_server.library_path_for_reexec({}, []) is None


def test_bind_localhost_only_keeps_text_on_the_node(monkeypatch):
    monkeypatch.setattr(socketserver.TCPServer, "__init__", socketserver.TCPServer.__init__)  # restored after

    class Upstream(socketserver.ThreadingTCPServer):  # how udpipe2_server.py's UDServer binds
        def __init__(self, host):
            super().__init__((host, 0), socketserver.BaseRequestHandler)

    udpipe_server.bind_localhost_only()
    for host in ("", "0.0.0.0", "127.0.0.1"):
        server = Upstream(host)
        try:
            assert server.server_address[0] == "127.0.0.1"
        finally:
            server.server_close()


def _udpipe_tree(tmp_path):
    src = tmp_path / "udpipe"
    (src / "wembedding_service").mkdir(parents=True)
    (src / "udpipe2_server.py").write_text("# upstream server\n", encoding="utf-8")
    (src / "udpipe2.py").write_text("NAME = 'udpipe2 sibling'\n", encoding="utf-8")
    (src / "wembedding_service" / "wembeddings.py").write_text("# embeddings\n", encoding="utf-8")
    (src / ".git").mkdir()
    (src / ".git" / "HEAD").write_text("ref: refs/heads/udpipe-2\n", encoding="utf-8")
    models = tmp_path / "models"
    (models / "english-ud-2.17-251125.model").mkdir(parents=True)
    (models / "english-ud-2.17-251125.model" / "weights.h5").write_bytes(b"w")
    (models / "english-ud-2.17-251125.model" / "mappings.pickle").write_bytes(b"m")
    (models / "MODELS.txt").write_text(
        "# name path variant acknowledgements\n"
        f"{MODEL}:en_gum english-ud-2.17-251125.model gum https://ufal.mff.cuni.cz/udpipe/2/models\n",
        encoding="utf-8")
    hub = tmp_path / "hub"
    repo = hub / f"models--{MBERT}"
    (repo / "refs").mkdir(parents=True)
    (repo / "refs" / "main").write_text(MBERT_COMMIT, encoding="utf-8")
    (repo / "snapshots" / MBERT_COMMIT).mkdir(parents=True)
    (repo / "snapshots" / MBERT_COMMIT / "config.json").write_text("{}", encoding="utf-8")
    (repo / "snapshots" / MBERT_COMMIT / "tf_model.h5").write_bytes(b"weights")
    return src, models, hub


MBERT, MBERT_COMMIT = "bert-base-multilingual-uncased", "7cbf9a625e29989f6b9c6c2fa68234c304f7e38f"


def _pins(src, models, hub):
    return udpipe_server.print_pins(src, models, [MODEL], hub_cache=hub, embedding_repo=MBERT,
                                    embedding_commit=MBERT_COMMIT)


def test_models_table_and_upstream_argv(tmp_path):
    _, models, _ = _udpipe_tree(tmp_path)
    table = udpipe_server.read_models_table(models / "MODELS.txt")
    assert list(table) == [MODEL]
    argv = udpipe_server.upstream_argv(Path("/src"), models, table, [MODEL], 20001, 8, ["--batch_size", "32"])
    assert argv[1:4] == ["20001", MODEL, f"{MODEL}:en_gum"]
    assert argv[4] == str(models / "english-ud-2.17-251125.model") and argv[5:7] == ["gum", table[MODEL][3]]
    assert argv[-4:] == ["--threads", "8", "--batch_size", "32"]
    with pytest.raises(KeyError):
        udpipe_server.upstream_argv(Path("/src"), models, table, ["unknown"], 1, 1, [])


def test_server_files_verify_against_printed_pins(tmp_path):
    src, models, hub = _udpipe_tree(tmp_path)
    pins = _pins(src, models, hub)
    assert set(pins["source_files"]) == {"udpipe2_server.py", "udpipe2.py", "wembedding_service/wembeddings.py"}
    assert set(pins["model_files"][MODEL]) == {"weights.h5", "mappings.pickle"}
    assert set(pins["embedding_snapshot"]["files"]) == {"config.json", "tf_model.h5"}
    got = udpipe_server.verify_server_files(src, models, MODEL, pins, hub)
    assert got["source_files"] == 3 and got["model_files"] == 2 and got["embedding_snapshot"]["files"] == 2
    with pytest.raises(P.PinError, match="hub cache is not set"):
        udpipe_server.verify_server_files(src, models, MODEL, pins)
    with pytest.raises(P.PinError, match="no embedding snapshot"):
        udpipe_server.verify_server_files(src, models, MODEL, {k: v for k, v in pins.items()
                                                               if k != "embedding_snapshot"}, hub)
    ref = hub / f"models--{MBERT}" / "refs" / "main"
    ref.write_text("0" * 40, encoding="utf-8")  # refs/main moved: UDPipe would load another snapshot
    with pytest.raises(P.PinError, match="would not load the pinned"):
        udpipe_server.verify_server_files(src, models, MODEL, pins, hub)
    ref.write_text(MBERT_COMMIT, encoding="utf-8")
    (models / "english-ud-2.17-251125.model" / "extra.bin").write_bytes(b"x")
    with pytest.raises(P.PinError, match="extra.bin not pinned"):
        udpipe_server.verify_server_files(src, models, MODEL, pins, hub)
    (models / "english-ud-2.17-251125.model" / "extra.bin").unlink()
    (src / "udpipe2.py").write_text("# changed\n", encoding="utf-8")
    with pytest.raises(P.PinError, match="udpipe2.py has SHA-256"):
        udpipe_server.verify_server_files(src, models, MODEL, pins, hub)
    with pytest.raises(P.PinError, match="no SHA-256 pins"):
        udpipe_server.verify_server_files(src, models, MODEL, {}, hub)
    archive = tmp_path / "a.tar.gz"
    archive.write_bytes(b"archive")
    with pytest.raises(P.PinError, match="a.tar.gz has SHA-256"):
        udpipe_server.print_pins(src, models, [MODEL], archive, "0" * 64)
    ok = udpipe_server.print_pins(src, models, [MODEL], archive, records.sha256_file(archive))
    assert ok["archive_sha256"] == records.sha256_file(archive)


def test_print_pins_command_line(tmp_path, capsys):
    src, models, hub = _udpipe_tree(tmp_path)
    assert udpipe_server.main(["--print-pins", "--udpipe-src", str(src), "--models-dir", str(models),
                               "--model", MODEL, "--hf-hub-cache", str(hub), "--embedding-repo", MBERT,
                               "--embedding-commit", MBERT_COMMIT]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed["model_files"]) == {MODEL} and printed["embedding_snapshot"]["commit"] == MBERT_COMMIT
    with pytest.raises(SystemExit):
        udpipe_server.main(["--udpipe-src", str(src), "--models-dir", str(models), "--model", MODEL])


# A stand-in for upstream udpipe2_server.py, run in this process by main() through runpy: it binds as UDServer does,
# imports a sibling module of the checkout, and writes what it saw beside itself.
FAKE_UPSTREAM = r'''
import json, socketserver, sys
from pathlib import Path
import udpipe2
class UDServer(socketserver.ThreadingTCPServer):
    def __init__(self):
        super().__init__(("", 0), socketserver.BaseRequestHandler)
server = UDServer()
host = server.server_address[0]
server.server_close()
Path(__file__).with_name("seen.json").write_text(json.dumps({"argv": sys.argv, "host": host,
                                                             "sibling": udpipe2.NAME}), encoding="utf-8")
'''


def test_server_main_runs_upstream_bound_to_localhost(tmp_path, monkeypatch, capsys):
    src, models, _ = _udpipe_tree(tmp_path)
    (src / "udpipe2_server.py").write_text(FAKE_UPSTREAM, encoding="utf-8")
    monkeypatch.setattr(socketserver.TCPServer, "__init__", socketserver.TCPServer.__init__)  # restored after
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(udpipe_server, "_maybe_reexec", lambda: None)
    monkeypatch.setattr(udpipe_server, "configure_tensorflow", lambda seed: {"seed": seed, "op_determinism": True})
    try:
        assert udpipe_server.main(["--udpipe-src", str(src), "--models-dir", str(models), "--model", MODEL,
                                   "--port", "4321", "--threads", "3", "--seed", "7", "--",
                                   "--batch_size", "32", "--max_request_size", "4194304"]) == 0
    finally:
        sys.modules.pop("udpipe2", None)
    seen = json.loads((src / "seen.json").read_text(encoding="utf-8"))
    assert seen["host"] == "127.0.0.1" and seen["sibling"] == "udpipe2 sibling"
    assert Path(seen["argv"][0]).name == "udpipe2_server.py" and seen["argv"][1:4] == ["4321", MODEL, f"{MODEL}:en_gum"]
    assert seen["argv"][-6:] == ["--threads", "3", "--batch_size", "32", "--max_request_size", "4194304"]
    err = capsys.readouterr().err
    versions = json.loads(err.split("udpipe_server: versions ", 1)[1].splitlines()[0])
    assert versions["op_determinism"] is True and versions["seed"] == 7
    resources = json.loads(err.split("udpipe_server: resources ", 1)[1].splitlines()[0])
    assert resources["serve_seconds"] >= 0


def test_server_command_is_isolated_and_local():
    cmd = udpipe_server.server_command(python="py", src=Path("s"), models_dir=Path("m"), model=MODEL, port=4321,
                                       threads=8, seed=20261026, batch_size=32, max_request_size=4194304)
    assert cmd[:4] == ["py", "-I", "-m", "intract_features.parse.udpipe_server"]
    assert cmd[cmd.index("--") + 1:] == ["--batch_size", "32", "--max_request_size", "4194304"]
    assert "20261026" in cmd and "4321" in cmd


# A stand-in for UDPipe 2's REST server: /models, and /process answering presegmented lines with one CoNLL-U sentence
# per line that holds a token ("@@@" holds none). Arguments: port, unused, N (answer the first N requests with HTTP
# 500), "header" to put the generator and model comments in a block of their own, and the word limit per line, over
# which the whole request is answered as upstream answers TooLongError (HTTP 400, text/plain). It counts requests.
FAKE_SERVER = r'''
import json, re, sys, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
port = int(sys.argv[1]); fail = [int(sys.argv[3]) if len(sys.argv) > 3 else 0]
header = "# generator = UDPipe 2\n# udpipe_model = MODEL\n\n" if len(sys.argv) > 4 and sys.argv[4] == "header" else ""
limit = int(sys.argv[5]) if len(sys.argv) > 5 else 1000
posts = [0]
TOK = re.compile(r"[^\W_]+|[^\w\s@]")
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype="application/json"):
        body = (json.dumps(body) if ctype == "application/json" else body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        self.send(200, {"models": {"MODEL": ["tokenizer"]}, "default_model": "MODEL", "posts": posts[0]})
    def do_POST(self):
        posts[0] += 1
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode(), True)
        if fail[0] > 0:
            fail[0] -= 1; return self.send(500, {"error": "busy"})
        if form["model"][0] != "MODEL":
            return self.send(400, "unknown model", "text/plain")
        assert form["tokenizer"][0] == "presegmented"
        lines = form["data"][0].split("\n")[:-1]
        if any(len(TOK.findall(line)) > limit for line in lines):
            return self.send(400, TOO_LONG, "text/plain")
        blocks = []
        for i, line in enumerate(lines, 1):
            toks = TOK.findall(line)
            if not toks: continue
            rows = ["# newpar", f"# sent_id = {i}", f"# text = {line}"]
            rows += [f"{j}\t{t}\t{t.lower()}\tX\t_\t_\t{0 if j == 1 else 1}\t{'root' if j == 1 else 'dep'}\t_\t_"
                     for j, t in enumerate(toks, 1)]
            blocks.append("\n".join(rows))
        self.send(200, {"model": "MODEL", "acknowledgements": [], "result": header + "\n\n".join(blocks) + "\n\n"})
print("udpipe_server: versions " + json.dumps({"gpus": [], "seed": 1}), file=sys.stderr, flush=True)
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
'''.replace("MODEL", MODEL).replace("TOO_LONG", repr(UPSTREAM_TOO_LONG))


@pytest.fixture
def fake_server_script(tmp_path):
    script = tmp_path / "fake_udpipe.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    return script


def _fake_server(script, tmp_path, fail_first=0, header=False, limit=1000):
    port = udpipe_server.free_port()
    cmd = [sys.executable, "-I", str(script), str(port), "x", str(fail_first), "header" if header else "plain",
           str(limit)]
    return udpipe_server.ServerProcess(cmd, f"http://127.0.0.1:{port}", tmp_path / f"server-{port}.log",
                                       startup_timeout=60, poll_interval=0.1, stop_timeout=10, probe_timeout=5)


def _client(url, model=MODEL, **over):
    scfg = load_cfg()["stages"]["parse_udpipe"]
    kw = {"tokenizer": scfg["tokenizer"], "timeout": 60.0, "retries": int(scfg["retries"]), "retry_sleep": 0.0,
          "max_request_bytes": int(scfg["max_request_bytes"])}
    return udpipe_client.UDPipeClient(url, model, **{**kw, **over})


def _posts(server) -> int:
    with urllib.request.urlopen(server.base_url + "/models", timeout=5) as r:
        return json.loads(r.read())["posts"]


def test_server_process_lifecycle(fake_server_script, tmp_path):
    with _fake_server(fake_server_script, tmp_path) as server:
        with urllib.request.urlopen(server.base_url + "/models", timeout=5) as r:
            assert r.status == 200
        assert server.startup_seconds is not None and server.versions() == {"gpus": [], "seed": 1}
    assert server.proc.returncode is not None
    assert server.usage is None or server.usage["cpu_seconds"] >= 0  # getrusage exists on Unix only
    assert server.resources() is None  # the stand-in logs no resources line
    dead = tmp_path / "dead.py"
    dead.write_text("import sys; print('boom', file=sys.stderr); sys.exit(3)\n", encoding="utf-8")
    port = udpipe_server.free_port()
    with pytest.raises(RuntimeError, match="boom"), udpipe_server.ServerProcess(
            [sys.executable, "-I", str(dead)], f"http://127.0.0.1:{port}", tmp_path / "dead.log",
            startup_timeout=30, poll_interval=0.1, stop_timeout=10, probe_timeout=5):
        pass


# ------------------------------------------------------------------------------------------- UDPipe client side


def test_split_blocks_counts_only_blocks_with_words():
    result = ("# generator = UDPipe 2\n# udpipe_model = m\n\n# sent_id = 1\n1\tA\ta\tX\t_\t_\t0\troot\t_\t_\n\n"
              "# sent_id = 2\n# text = @@@\n\n\n")
    blocks = udpipe_client.split_blocks(result)
    assert len(blocks) == 1 and udpipe_client.block_tokens(blocks[0])[0].form == "A"


def test_refusals_are_told_apart_by_the_upstream_text():
    assert isinstance(udpipe_client.refusal_from(400, UPSTREAM_TOO_LONG, MODEL), udpipe_client.SentenceTooLong)
    read_path = "Sentence longer than 1000 words was found on input, aborting.\n"
    assert isinstance(udpipe_client.refusal_from(400, read_path, MODEL), udpipe_client.SentenceTooLong)
    assert isinstance(udpipe_client.refusal_from(400, "The payload size is too large.", MODEL),
                      udpipe_client.PayloadTooLarge)
    other = udpipe_client.refusal_from(400, "An internal error occurred during processing.", MODEL)
    assert type(other) is udpipe_client.UDPipeRefusal and "HTTP 400" in str(other)


def test_client_ignores_a_header_block(fake_server_script, tmp_path):
    with _fake_server(fake_server_script, tmp_path, header=True) as server:
        client = _client(server.base_url)
        out = client.parse(["Tom ran.", "He sat."])
    assert [len(p) for p in out] == [3, 3] and client.fallback_requests == 0


def test_client_reports_another_served_model():
    client = _client("http://127.0.0.1:1")
    assert client.model_problem() is None
    client.models_reported = {MODEL, "english-ewt-ud-2.17-251125"}
    assert "english-ewt-ud-2.17-251125" in client.model_problem()


def test_client_refuses_a_remote_server():
    with pytest.raises(ValueError, match="local"):
        _client("https://lindat.mff.cuni.cz/services/udpipe/api")


def test_wait_for_server_times_out_and_notices_a_dead_process():
    port = udpipe_server.free_port()
    ticks = iter(range(100))
    with pytest.raises(TimeoutError):
        udpipe_client.wait_for_server(f"http://127.0.0.1:{port}", 2, 0, probe_timeout=1, sleep=lambda s: None,
                                      clock=lambda: next(ticks))
    with pytest.raises(RuntimeError, match="exited"):
        udpipe_client.wait_for_server(f"http://127.0.0.1:{port}", 60, 0, probe_timeout=1, alive=lambda: False,
                                      sleep=lambda s: None)


def test_client_parses_falls_back_and_retries(fake_server_script, tmp_path):
    with _fake_server(fake_server_script, tmp_path, fail_first=1) as server:
        client = _client(server.base_url)
        out = client.parse(["Tom ran home.", "@@@", "He sat."])
        assert out[1] is None and [t.form for t in out[0]] == ["Tom", "ran", "home", "."]
        assert client.retried == 1 and client.fallback_requests == 1 and client.models_reported == {MODEL}
        bad = _client(server.base_url, "no-such-model")
        with pytest.raises(udpipe_client.UDPipeRefusal, match="HTTP 400"):
            bad.parse(["Tom ran."])
        assert bad.retried == 0  # a refusal is not retried


def test_client_resends_one_per_request_after_a_too_long_refusal(fake_server_script, tmp_path):
    with _fake_server(fake_server_script, tmp_path, limit=5) as server:
        client = _client(server.base_url)
        out = client.parse(["Tom ran home.", "one two three four five six seven", "He sat."])
        assert [t.form for t in out[0]] == ["Tom", "ran", "home", "."] and len(out[2]) == 3
        assert isinstance(out[1], P.Refused) and "1000 words" in out[1].reason
        stats = client.stats()
        assert stats["too_long_fallbacks"] == 1 and stats["refused_too_long"] == 1
        assert stats["refused_max_whitespace_tokens"] == 7 and _posts(server) == 4  # the refused call, then 3
        alone = client.parse(["a b c d e f"])  # a call of one sentence is not sent again
        assert isinstance(alone[0], P.Refused) and _posts(server) == 5 and client.too_long_fallbacks == 1


def test_client_splits_a_call_over_the_size_limit_without_sending_it(fake_server_script, tmp_path):
    texts = ["Tom ran home.", "He sat down.", "Ann was happy."]  # 125 bytes encoded together, at most 94 alone
    with _fake_server(fake_server_script, tmp_path) as server:
        client = _client(server.base_url, max_request_bytes=110)
        out = client.parse(texts)
        assert [len(p) for p in out] == [4, 4, 4] and client.payload_fallbacks == 1 and _posts(server) == 3
        with pytest.raises(udpipe_client.PayloadTooLarge, match="not sent"):
            client.parse([" ".join(["word"] * 40)])
        assert _posts(server) == 3


def test_client_bypasses_any_proxy_the_environment_names(fake_server_script, tmp_path, monkeypatch):
    for var in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(var, raising=False)
    with _fake_server(fake_server_script, tmp_path) as server:
        for var in ("http_proxy", "HTTP_PROXY"):
            monkeypatch.setenv(var, "http://127.0.0.1:9")  # nothing listens there
        out = _client(server.base_url, retries=1).parse(["Tom ran."])
    assert [t.form for t in out[0]] == ["Tom", "ran", "."]


# ------------------------------------------------------------------------------------------ parse_udpipe stage


def _external(cfg):
    cfg["stages"]["parse_udpipe"]["allow_unverified_external_server"] = True
    return cfg


def test_parse_udpipe_stage_with_a_running_server(fake_server_script, tmp_path):
    docs = [make_doc("S1"), make_doc("S2", pages=("Ann sat.", "@@@ Bob ran."))]
    write_inputs(tmp_path, docs, [seg_record(docs[0]), seg_record(docs[1], ["Ann sat.", "@@@", "Bob ran."])])
    cfg = _external(load_cfg())
    cfg["stages"]["parse_udpipe"]["rerun_check_documents"] = 2
    with _fake_server(fake_server_script, tmp_path) as server:
        rec = run_stage(parse_udpipe, _ctx(parse_udpipe, cfg, tmp_path, udpipe_url=server.base_url))
    out = records.artefact_path(tmp_path, "en-us", "parses_udpipe", 0, 1, ext="conllu.gz")
    back = {d.story_id: d for d in P.read_conllu(out)}
    assert [s.k for s in back["S2"].sentences] == [0, 1, 2] and back["S2"].sentences[1].empty
    assert [w.form for w in back["S1"].sentences[2].words] == ["Then", "he", "ate", "du", "pain", "."]
    u = rec["counts"]["udpipe"]
    assert u["server"] == {"external": True} and u["pins_verified"] is None
    assert u["model"] == MODEL and u["seed"] == 20261026 and u["refusal_check"]["refused_units"] == 0
    assert u["rerun_check"] == {"documents": 2, "identical": 2, "all_identical": True, "fresh_server": False}


def test_parse_udpipe_stage_refuses_an_unverified_server_by_default(tmp_path):
    doc = make_doc()
    write_inputs(tmp_path, [doc], [seg_record(doc)])
    with pytest.raises(RuntimeError, match="allow_unverified_external_server"):
        parse_udpipe.run(_ctx(parse_udpipe, load_cfg(), tmp_path, udpipe_url="http://127.0.0.1:1"))
    assert not records.artefact_path(tmp_path, "en-us", "parses_udpipe", 0, 1, ext="conllu.gz").exists()


LONG_UNIT = " ".join(f"w{i}" for i in range(120)) + "."  # 120 registered words: long under S3
NOT_LONG_UNIT = " ".join(["!"] * 60) + " ok go now."  # 63 tokens for UDPipe, 3 registered words: not long


def _refusal_inputs(tmp_path):
    doc = make_doc("S1", pages=("Tom ran home.", LONG_UNIT, NOT_LONG_UNIT, "He sat."))
    write_inputs(tmp_path, [doc], [seg_record(doc, ["Tom ran home.", LONG_UNIT, NOT_LONG_UNIT, "He sat."])])
    return doc


def test_parse_udpipe_stage_keeps_refused_units_and_checks_them(fake_server_script, tmp_path, capsys):
    _refusal_inputs(tmp_path)
    with _fake_server(fake_server_script, tmp_path, limit=50) as server:
        rec = run_stage(parse_udpipe, _ctx(parse_udpipe, _external(load_cfg()), tmp_path, udpipe_url=server.base_url))
    out = records.artefact_path(tmp_path, "en-us", "parses_udpipe", 0, 1, ext="conllu.gz")
    (back,) = list(P.read_conllu(out))
    assert [s.refused is not None for s in back.sentences] == [False, True, True, False]
    assert back.sentences[1].empty and len(back.sentences[3].tokens) == 3
    c, u = rec["counts"], rec["counts"]["udpipe"]
    assert c["refused_units"] == 2 and c["empty_parses"] == 2 and c["max_refused_whitespace_tokens"] == 120
    assert u["refused_too_long"] == 2 and u["too_long_fallbacks"] == 1
    assert u["refusal_check"] == {"refused_units": 2, "long": 1, "not_long": 1, "unchecked": 0,
                                  "max_registered_words": 120, "rule_max_words": 100, "fail_on_not_long": False}
    assert "refused unit S1-2 is not long under S3" in capsys.readouterr().err


def test_parse_udpipe_stage_can_fail_on_a_refused_unit_that_is_not_long(fake_server_script, tmp_path):
    _refusal_inputs(tmp_path)
    cfg = _external(load_cfg())
    cfg["stages"]["parse_udpipe"]["refusals"]["refused_not_long"] = "fail"
    with _fake_server(fake_server_script, tmp_path, limit=50) as server, \
            pytest.raises(RuntimeError, match="not long under S3"):
        parse_udpipe.run(_ctx(parse_udpipe, cfg, tmp_path, udpipe_url=server.base_url))
    out = records.artefact_path(tmp_path, "en-us", "parses_udpipe", 0, 1, ext="conllu.gz")
    assert not out.exists() and out.with_name(out.name + ".failed").exists()


def test_parse_udpipe_stage_rejects_a_shard_served_by_another_model(fake_server_script, tmp_path, monkeypatch):
    doc = make_doc()
    write_inputs(tmp_path, [doc], [seg_record(doc)])
    monkeypatch.setattr(udpipe_client.UDPipeClient, "model_problem", lambda self: "served another model")
    with _fake_server(fake_server_script, tmp_path) as server, pytest.raises(RuntimeError, match="another model"):
        parse_udpipe.run(_ctx(parse_udpipe, _external(load_cfg()), tmp_path, udpipe_url=server.base_url))
    out = records.artefact_path(tmp_path, "en-us", "parses_udpipe", 0, 1, ext="conllu.gz")
    assert not out.exists() and out.with_name(out.name + ".failed").exists()


def test_parse_udpipe_stage_starts_and_verifies_its_own_server(fake_server_script, tmp_path, monkeypatch):
    src, models, hub = _udpipe_tree(tmp_path)
    doc = make_doc()
    write_inputs(tmp_path, [doc], [seg_record(doc)])
    cfg = load_cfg({"udpipe-2.17": _pins(src, models, hub)})
    cfg["stages"]["parse_udpipe"].update(device="cpu", rerun_check_documents=1, poll_interval_s=0.1)
    monkeypatch.setenv("INTRACT_UDPIPE_SRC", str(src))
    monkeypatch.setenv("INTRACT_UDPIPE_MODELS", str(models))
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    seen = []

    def fake_command(*, python, src, models_dir, model, port, threads, seed, batch_size, max_request_size):
        seen.append((model, threads, seed, batch_size, max_request_size))
        # the server's environment is offline: print what it was given, then serve
        return [sys.executable, "-I", "-c", "import os, runpy, sys; print('offline', os.environ.get("
                "'HF_HUB_OFFLINE'), os.environ.get('TRANSFORMERS_OFFLINE'), flush=True); sys.argv = sys.argv[1:]; "
                "runpy.run_path(sys.argv[0], run_name='__main__')", str(fake_server_script), str(port)]

    monkeypatch.setattr(parse_udpipe, "server_command", fake_command)
    counts = parse_udpipe.run(_ctx(parse_udpipe, cfg, tmp_path))
    assert seen == [(MODEL, 8, 20261026, 32, 4194304)] * 2  # the parse and the fresh-server rerun
    u = counts["udpipe"]
    assert u["pins_verified"]["model_files"] == 2 and u["pins_verified"]["embedding_snapshot"]["files"] == 2
    assert u["server"]["versions"] == {"gpus": [], "seed": 1} and u["server"]["external"] is False
    assert u["server"]["process"] is None or u["server"]["process"]["cpu_seconds"] >= 0
    assert u["rerun_check"]["all_identical"] and u["rerun_check"]["fresh_server"]
    log = tmp_path / "en-us" / "_logs" / "parse_udpipe-shard-0-of-1.server.log"
    assert "offline 1 1" in log.read_text(encoding="utf-8")


def test_parse_udpipe_stage_refuses_to_run_a_gpu_job_without_a_gpu(tmp_path, monkeypatch):
    for var in ("CUDA_VISIBLE_DEVICES", "SLURM_JOB_GPUS", "SLURM_STEP_GPUS"):
        monkeypatch.delenv(var, raising=False)
    doc = make_doc()
    write_inputs(tmp_path, [doc], [seg_record(doc)])
    with pytest.raises(RuntimeError, match="registered CPU fallback"):
        parse_udpipe.run(_ctx(parse_udpipe, load_cfg(), tmp_path))


# -------------------------------------------------------------------------------------------- long-unit rule


def test_long_unit_rule_reads_config_and_is_strict():
    rule = long_units.LongUnitRule.from_config(load_cfg())
    assert (rule.max_words, rule.flag_share) == (100, 0.01)
    assert not rule.is_long(100) and rule.is_long(101)


def test_udpipe_member_and_pairs_take_stanza_for_long_units():
    rule = long_units.LongUnitRule(max_words=100, flag_share=0.01)
    counts = [10, 101, 20, 30]
    assert rule.udpipe_member(["s0", "s1", "s2", "s3"], ["u0", "u1", "u2", "u3"], counts) == ["u0", "s1", "u2", "u3"]
    # pair i joins units i and i+1: pairs touching unit 1 take Stanza's value
    assert rule.udpipe_pair_member(["s01", "s12", "s23"], ["u01", "u12", "u23"], counts) == ["s01", "s12", "u23"]
    with pytest.raises(ValueError):
        rule.udpipe_member(["s"], ["u", "v"], [1, 2])
    with pytest.raises(ValueError):
        rule.udpipe_pair_member(["s"], ["u"], [1, 2, 3])


def test_long_unit_summary_flags_above_one_per_cent():
    rule = long_units.LongUnitRule(max_words=100, flag_share=0.01)
    exactly = rule.summary([101] + [5] * 99)
    assert exactly["share_units"] == 0.01 and not exactly["flagged"]  # "above 1 per cent"
    above = rule.summary([101, 150] + [5] * 98)
    assert above["flagged"] and above["long_words"] == 251
    assert rule.summary([])["share_units"] == 0.0
    assert rule.summary_from_counts(100, 2, 741, 251) == above  # an aggregation step's counts give the same report
    assert rule.summary_from_counts(200, 2)["flagged"] is False and "words" not in rule.summary_from_counts(1, 0)


def test_unit_word_counts_place_words_by_their_first_letter():
    doc = make_doc(pages=("Hi there. \u201cBye\u201d now", "-- yes."))
    units = P.document_units(doc, [(0, 9), (10, len(doc.text))])
    assert long_units.unit_word_counts(doc.text, units) == [2, 3]
    assert long_units.unit_word_counts(doc.text, units[:1]) == [2]


def test_refusal_check_flags_a_refused_unit_that_is_not_long():
    rule = long_units.LongUnitRule(max_words=100, flag_share=0.01)
    doc = make_doc(pages=(LONG_UNIT, NOT_LONG_UNIT))
    units = P.document_units(doc, [(0, len(LONG_UNIT)), (len(LONG_UNIT) + 1, len(doc.text))])
    refused = [P.Refused("x"), P.Refused("x")]
    check = long_units.RefusalCheck(rule, spaced=True, fail=False)
    check.observe(doc, units, refused)
    check.observe(doc, units, [None, None])  # nothing refused: nothing counted
    assert (check.refused, check.long, check.not_long, check.max_words) == (2, 1, 1, 120)
    assert check.problem() is None and check.not_long_units == ["S1-1"]
    strict = long_units.RefusalCheck(rule, spaced=True, fail=True)
    strict.observe(doc, units, refused)
    assert "not long under S3" in strict.problem()
    unspaced = long_units.RefusalCheck(rule, spaced=False, fail=True)
    unspaced.observe(doc, units, refused)
    assert unspaced.unchecked == 2 and unspaced.problem() is None


# ---------------------------------------------------------------------------------------------- packaging


def test_config_tables_hold_the_registered_constants():
    cfg = load_cfg()
    s, u = cfg["stages"]["parse_stanza"], cfg["stages"]["parse_udpipe"]
    assert s["stanza_version"] == "1.15.0" and s["required_tier"] == "nocharlm" and s["tokenize_no_ssplit"]
    assert s["batch"] == {"depparse_batch_size": 0, "depparse_min_length_to_batch_separately": 0}
    assert s["calls"]["sentences_per_call"] == 0 and u["calls"]["sentences_per_call"] == 0
    assert s["input"]["line_breaks"] == "flatten" and s["segments"]["translation_segmenter"] == "union"
    assert u["input_config_stage"] == "parse_stanza" and "input" not in u and "offset_max_skip" not in u
    assert u["tokenizer"] == "presegmented" and u["device"] == "gpu" and u["long_units"]["max_words"] == 100
    assert u["refusals"]["refused_not_long"] == "flag" and u["allow_unverified_external_server"] is False
    assert u["max_request_bytes"] == 4096 * 1024
    assert cfg["languages"]["en-us"]["udpipe_model"] == MODEL and cfg["languages"]["en-us"]["spaced"] is True


def test_modules_import_without_heavy_libraries():
    code = ("import sys, intract_features.parse.stanza_wrap, intract_features.parse.udpipe_server, "
            "intract_features.parse.udpipe_client, intract_features.parse.long_units, "
            "intract_features.stages.parse_stanza, intract_features.stages.parse_udpipe; "
            "print(sorted(m for m in ('stanza', 'torch', 'tensorflow', 'numpy', 'transformers') if m in sys.modules))")
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
