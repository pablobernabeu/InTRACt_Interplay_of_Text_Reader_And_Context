"""Parsing: the registered sentences handed to both parsers, the shared parse model and the CoNLL-U artefacts.

Supplementary Section S3 registers two parsers, "Stanza 1.15.0 in its `nocharlm` tier ... and UDPipe 2 with its
models of release 2.17", and "Both run on every sentence of every text, each with the registered treebank for the
language and its own tokeniser". The sentences are those of the segmentation artefact (S3: "Both parsers, the word
function, the dialogue spans and every sentence-based feature take these sentences"). This module turns a document
and its sentence spans into parser units, writes a parse in the layout DESIGN.md fixes and reads it back.

Artefact format (parses_stanza and parses_udpipe, extension conllu.gz), one file per parser and shard:

    # newdoc id = <story_id>
    # sent_id = <story_id>-<k>
    # text = <sentence k>
    # span = <start>:<end>
    1	Tom	Tom	PROPN	NNP	Number=Sing	2	nsubj	_	TokenRange=0:3
    ...

* k is the 0-based index of the sentence in the document's list in the segments artefact, so sentence k of a parse
  is sentence k of the segmentation, and every sentence keeps its block even when the parser returns nothing for it.
* `# span` gives the sentence's [start, end) offsets in Document.text after leading and trailing whitespace are
  stripped, and `# text` is that substring with every line-break character replaced by one space. Line breaks
  inside a page survive extraction (critique item 21, gap G9), and both parsers read a line break as a sentence
  boundary (Stanza splits paragraphs at a blank line, UDPipe's presegmented mode takes one sentence per line), so
  a sentence is flattened before it is parsed ([input] line_breaks = "flatten"; "refuse" stops the stage instead).
  The replacement is one character for one, so offsets are unchanged.
* MISC is rebuilt uniformly for both parsers: `TokenRange=<start>:<end>` gives each surface token's offsets in
  Document.text, found by aligning the tokens' characters with the sentence (align_tokens), and `SpaceAfter=No`
  marks a token followed by a non-space character. Every character offset in every artefact refers to
  Document.text (DESIGN.md), which the dialogue spans and the word function also use. Words inside a multi-word
  token carry `_`.
* A sentence the parser returns no parse for is written as a block of comments ending in `# parse = empty`, with no
  word lines. When the parser refused the sentence (UDPipe's limit of 1,000 words), a `# refused = <reason>` comment
  comes before it. Strict CoNLL-U validators reject such a block; read_conllu() returns it with no tokens.
* A document with no sentences writes nothing.
"""

from __future__ import annotations

import gzip
import hashlib
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from intract_features.records import Document, sha256_file

__all__ = [
    "FAILED_SUFFIX", "LINE_BREAK_MODES", "ConlluDocument", "ConlluSentence", "ConlluShardWriter", "ParseCounts",
    "PinError", "Refused", "SegmentRules", "Token", "Unit", "Word", "align_tokens", "call_groups", "document_units",
    "file_digests", "flatten_line_breaks", "format_document", "format_sentence", "iter_parsed", "join_units",
    "md5_file", "model_pin", "parse_document", "parse_shard", "read_conllu", "sha256_file", "spans_from_record",
    "text_sha256", "tokens_from_conllu",
]

# The characters str.splitlines() breaks on. Any of them inside a sentence would split it in one parser or the
# other, so each becomes one space before parsing (one for one, so offsets keep their meaning).
LINE_BREAKS = frozenset("\n\r\x0b\x0c\x1c\x1d\x1e\x85\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}")
_FLATTEN = str.maketrans({c: " " for c in LINE_BREAKS})
# [input] line_breaks: what a line break inside a registered sentence does (gap G9; see the module docstring).
LINE_BREAK_MODES = ("flatten", "refuse")
# The suffix under which a shard that fails a check is kept for inspection instead of being published.
FAILED_SUFFIX = ".failed"


class PinError(RuntimeError):
    """A pinned file is missing or differs from its pin, so it must not be loaded (DESIGN.md, Configuration)."""


@dataclass(frozen=True)
class Unit:
    """One registered sentence of a document, as both parsers receive it.

    `k` is its index in the segments artefact; [start, end) are its offsets in Document.text after stripping
    leading and trailing whitespace; `text` is that substring with line breaks flattened to spaces.
    """

    k: int
    start: int
    end: int
    text: str


@dataclass
class Word:
    """One syntactic word: a CoNLL-U word line."""

    id: int
    form: str
    lemma: str = "_"
    upos: str = "_"
    xpos: str = "_"
    feats: str = "_"
    head: int = 0
    deprel: str = "_"
    deps: str = "_"


@dataclass
class Token:
    """One surface token: a single word, or a multi-word token whose words follow it.

    `start` and `end` are the token's offsets in Document.text, or None where the alignment could not place it.
    """

    form: str
    words: list[Word]
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class Refused:
    """A unit the parser refused to parse; the artefact keeps its block, with `# refused = <reason>`."""

    reason: str


@dataclass
class ConlluSentence:
    """A sentence block read back from a parse artefact."""

    sent_id: str
    k: int
    text: str
    span: tuple[int, int] | None
    tokens: list[Token] = field(default_factory=list)
    empty: bool = False
    refused: str | None = None

    @property
    def words(self) -> list[Word]:
        """The sentence's syntactic words in order (multi-word tokens expanded)."""
        return [w for t in self.tokens for w in t.words]


@dataclass
class ConlluDocument:
    """The sentences of one document in a parse artefact, in segmentation order."""

    story_id: str
    sentences: list[ConlluSentence] = field(default_factory=list)


# --------------------------------------------------------------------------------------------- hashing and pins


def md5_file(path: Path, chunk: int = 1 << 20) -> str:
    """MD5 hex digest of a file, read in chunks (Stanza's resources.json records MD5s, not SHA-256)."""
    return file_digests(path, chunk)[0]


def file_digests(path: Path, chunk: int = 1 << 20) -> tuple[str, str]:
    """MD5 and SHA-256 hex digests of a file in one pass, so a 100 MB model file is read once for both pins."""
    md5, sha = hashlib.md5(usedforsecurity=False), hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            md5.update(block)
            sha.update(block)
    return md5.hexdigest(), sha.hexdigest()


def text_sha256(text: str) -> str:
    """SHA-256 of a text's UTF-8 bytes, the digest the segments artefact records for the text it was cut from."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def model_pin(cfg: dict, key: str) -> dict:
    """The models.lock.json entry `key`, which a parser verifies before it loads any file.

    The lock file belongs to the ARC set-up; its entries are read either at the top level or under a "models"
    table. A missing entry stops the stage, because DESIGN.md requires a verified pin before a file is loaded.
    """
    models = cfg.get("models") or {}
    entry = models.get(key)
    if entry is None and isinstance(models.get("models"), dict):
        entry = models["models"].get(key)
    if not isinstance(entry, dict):
        raise PinError(f"config/models.lock.json has no entry {key!r}; the parser's pins must be recorded there "
                       "before it can run")
    return entry


# ----------------------------------------------------------------------------------------------- sentence units


def flatten_line_breaks(text: str) -> str:
    """Replace every line-break character with one space, keeping the string's length."""
    return text.translate(_FLATTEN)


@dataclass(frozen=True)
class SegmentRules:
    """Which segmentation a segments record must come from, read from a stage's [segments] table.

    qmd Materials: "In English, a sentence ends where the registered Segment any Text (SaT) model places a boundary";
    "In each translation, the union segmenter keeps every sentence end the translation marks itself and takes the
    others from its English source". The sat stage's record of a translation is SaT alone, the union segmenter's
    input (segment/__init__.py), and it is a translation's sentences only in the registered sensitivity analysis
    ("by SaT alone in another"), which allow_sat_alone switches on.
    """

    source_segmenter: str
    translation_segmenter: str
    allow_sat_alone: bool

    @classmethod
    def from_config(cls, table: Mapping) -> SegmentRules:
        """Read the rules from a [segments] table."""
        return cls(source_segmenter=str(table["source_segmenter"]),
                   translation_segmenter=str(table["translation_segmenter"]),
                   allow_sat_alone=bool(table["allow_sat_alone"]))

    def refusal(self, rec: Mapping) -> str | None:
        """Why a segments record is not the registered segmentation for its language, or None if it is."""
        segmenter, is_source = rec.get("segmenter"), rec.get("is_source")
        if not isinstance(is_source, bool):
            return "carries no is_source flag"
        if is_source:
            ok = segmenter == self.source_segmenter
        else:
            # SaT alone on a translation is the source segmenter's output, accepted only for the sensitivity analysis
            sat_alone = self.allow_sat_alone and segmenter == self.source_segmenter
            ok = segmenter == self.translation_segmenter or sat_alone
        if ok:
            return None
        role = "the English source" if is_source else "a translation"
        return f"comes from segmenter {segmenter!r}, which is not the registered segmentation of {role}"


def spans_from_record(rec: dict, field_name: str) -> list[tuple[int, int]]:
    """The [start, end) sentence spans of one segments record.

    `rec[field_name]` is a list whose items are either objects with "start" and "end" or sequences whose first two
    items are start and end, as the sat stage writes them ([start, end, page_start, page_end], declared in the
    record's "sentence_fields"); anything else is refused, so a change in the segments format cannot pass unnoticed.
    """
    sid = rec.get("story_id")
    if field_name not in rec:
        raise ValueError(f"segments record {sid!r} has no {field_name!r} field")
    declared = rec.get("sentence_fields")
    if declared is not None and tuple(declared[:2]) != ("start", "end"):
        raise ValueError(f"segments record {sid!r} declares sentence fields {declared!r}; start and end must lead")
    spans = []
    for i, item in enumerate(rec[field_name]):
        if isinstance(item, dict) and "start" in item and "end" in item:
            start, end = item["start"], item["end"]
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            start, end = item[0], item[1]
        else:
            raise ValueError(f"segments record {sid!r}: sentence {i} is neither {{start, end}} nor [start, end, ...]")
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in (start, end)):
            raise ValueError(f"segments record {sid!r}: sentence {i} has non-integer offsets {start!r}, {end!r}")
        spans.append((start, end))
    return spans


def document_units(doc: Document, spans: Sequence[tuple[int, int]], *, allow_uncovered_text: bool = False,
                   line_breaks: str = "flatten") -> list[Unit]:
    """Turn a document's sentence spans into parser units.

    Spans must lie inside Document.text, in order and without overlap. A non-space character outside every span
    is an error unless `allow_uncovered_text` is set, because S3 has both parsers run "on every sentence of every
    text", so text that no sentence holds would go unparsed. `line_breaks` says what a line break inside a sentence
    does: "flatten" replaces it with a space, "refuse" stops here (gap G9, pending the Feature Specification).
    """
    if line_breaks not in LINE_BREAK_MODES:
        raise ValueError(f"line_breaks must be one of {LINE_BREAK_MODES}, not {line_breaks!r}")
    text = doc.text
    units, uncovered, prev = [], [], 0
    for k, (start, end) in enumerate(spans):
        if start < prev or end < start or end > len(text):
            raise ValueError(f"{doc.story_id}: sentence {k} span [{start}, {end}) is out of order, overlaps the one "
                             f"before it or lies outside the text ({len(text)} characters)")
        if text[prev:start].strip():
            uncovered.append((prev, start))
        raw = text[start:end]
        stripped = raw.strip()
        if line_breaks == "refuse" and not LINE_BREAKS.isdisjoint(stripped):
            raise ValueError(f"{doc.story_id}: sentence {k} holds a line break, which [input] line_breaks = "
                             "'refuse' does not allow")
        s = start + (len(raw) - len(raw.lstrip()))
        units.append(Unit(k=k, start=s, end=s + len(stripped), text=flatten_line_breaks(stripped)))
        prev = end
    if text[prev:].strip():
        uncovered.append((prev, len(text)))
    if uncovered and not allow_uncovered_text:
        raise ValueError(f"{doc.story_id}: text outside every sentence at {uncovered[:3]}; every sentence of every "
                         "text must be parsed (S3)")
    return units


def join_units(documents: Iterable[Document], segment_records: Iterable[dict], *, lang: str, field_name: str,
               rules: SegmentRules, allow_uncovered_text: bool = False,
               line_breaks: str = "flatten") -> Iterator[tuple[Document, list[Unit]]]:
    """Pair each document with the units of its segments record, in document order.

    Both artefacts come from the same shard (a story's shard is a keyed hash of its id). The stage stops at a
    document without a segments record, a duplicate record, a record for another language, a record cut from
    another text (its text_sha256 differs, so the segments artefact is stale) and a record whose segmenter is not
    the registered one for the language (`rules`).
    """
    segs: dict[str, dict] = {}
    for rec in segment_records:
        sid = rec.get("story_id")
        if sid in segs:
            raise ValueError(f"two segments records for {sid!r}")
        if rec.get("lang") != lang:
            raise ValueError(f"segments record {sid!r} is for {rec.get('lang')!r}, not {lang!r}")
        segs[sid] = rec
    for doc in documents:
        rec = segs.get(doc.story_id)
        if rec is None:
            raise ValueError(f"no segments record for {doc.story_id!r}")
        if rec.get("text_sha256") != text_sha256(doc.text):
            raise ValueError(f"segments record {doc.story_id!r} was cut from another text or records no text_sha256 "
                             "(stale artefact)")
        problem = rules.refusal(rec)
        if problem:
            raise ValueError(f"segments record {doc.story_id!r} {problem}")
        spans = spans_from_record(rec, field_name)
        yield doc, document_units(doc, spans, allow_uncovered_text=allow_uncovered_text, line_breaks=line_breaks)


# ---------------------------------------------------------------------------------------- offsets and CoNLL-U


def _nonspace(text: str) -> tuple[str, list[int]]:
    """The non-space characters of a text, and the offset of each."""
    offsets = [i for i, c in enumerate(text) if not c.isspace()]
    return "".join(text[i] for i in offsets), offsets


def _occurrences(s: str, sub: str, lo: int, hi: int) -> list[int]:
    """Every start of `sub` lying wholly inside s[lo:hi]."""
    out, i = [], s.find(sub, lo, hi)
    while i >= 0:
        out.append(i)
        i = s.find(sub, i + 1, hi)
    return out


def align_tokens(unit: Unit, tokens: Sequence[Token], max_skip: int) -> int:
    """Set each surface token's offsets in Document.text by aligning it with the unit; return the tokens not placed.

    Only non-space characters are compared, because a tokeniser may change the whitespace inside a token: Stanza
    1.15.0 maps every whitespace character in a token to a space, and removes it in Chinese, Japanese and Korean
    (models/tokenization/vocab.py, normalize_token), so a token over "10<NNBSP>000" reads "10 000". A token is
    placed where its characters continue the text; failing that, at its only occurrence within `max_skip`
    characters further on (a tokeniser may drop a character it keeps in no token).

    A token whose characters differ from the text is left unplaced, and the search for the next token starts where
    the unplaced tokens would end if their lengths held. The next token is placed at its only occurrence within
    `max_skip` characters of that point; if it occurs there several times, it is placed only at that point itself.
    A token of one character, and a token that occurs several times, is placed only where the token after it
    continues the text (or where it ends the unit). A single unplaced token between two placed ones then takes the
    gap between them, if the gap's length is within `max_skip` of its own (parse_document counts such a token as
    inexact: its text differs from its form); several unplaced tokens in a row keep no offsets. So an unplaced
    token never moves the tokens after it, and no token is placed inside the characters of the tokens before it.
    """
    ns, offs = _nonspace(unit.text)
    forms = ["".join(t.form.split()) for t in tokens]
    # the next form with characters after each token, found once so that a long unit stays linear
    following: list[str | None] = [None] * len(forms)
    nxt_form: str | None = None
    for i in range(len(forms) - 1, -1, -1):
        following[i] = nxt_form
        if forms[i]:
            nxt_form = forms[i]
    p = 0  # the next non-space character no placed token holds
    pending: list[int] = []  # tokens left unplaced since the last placed one
    pending_len = 0

    def place(i: int, a: int, b: int) -> None:
        tokens[i].start, tokens[i].end = unit.start + offs[a], unit.start + offs[b - 1] + 1

    def confirmed(i: int, q: int) -> bool:
        end, nxt = q + len(forms[i]), following[i]
        return end == len(ns) if nxt is None else ns.startswith(nxt, end)

    def accept(i: int, hits: list[int], expected: int | None) -> int | None:
        f = forms[i]
        if len(hits) == 1 and (len(f) > 1 or confirmed(i, hits[0])):
            return hits[0]
        if expected is not None and expected in hits and confirmed(i, expected):
            return expected
        return None

    for tok in tokens:
        tok.start = tok.end = None
    for i, f in enumerate(forms):
        if not f:
            continue
        if not pending:
            q = p if ns.startswith(f, p) else accept(i, _occurrences(ns, f, p, p + max_skip + len(f)), None)
        else:
            expected = p + pending_len
            q = accept(i, _occurrences(ns, f, max(p, expected - max_skip), expected + max_skip + len(f)), expected)
        if q is None:
            pending.append(i)
            pending_len += len(f)
            continue
        if len(pending) == 1 and q > p and abs((q - p) - pending_len) <= max_skip:
            place(pending[0], p, q)
        place(i, q, q + len(f))
        p, pending, pending_len = q + len(f), [], 0
    if len(pending) == 1 and len(ns) > p and abs((len(ns) - p) - pending_len) <= max_skip:
        place(pending[0], p, len(ns))
    return sum(1 for t in tokens if t.start is None)


def _inexact(tokens: Sequence[Token], doc_text: str) -> int:
    """Placed tokens whose text in Document.text differs from their form in non-space characters."""
    return sum(1 for t in tokens if t.start is not None
               and "".join(doc_text[t.start:t.end].split()) != "".join(t.form.split()))


def _field(value: object) -> str:
    """A CoNLL-U column value: None or empty becomes "_", and tabs or line breaks become spaces."""
    if value is None or value == "":
        return "_"
    return flatten_line_breaks(str(value)).replace("\t", " ")


def _misc(tok: Token, doc_text: str) -> str:
    parts = []
    if tok.end is not None and tok.end < len(doc_text) and not doc_text[tok.end].isspace():
        parts.append("SpaceAfter=No")
    if tok.start is not None:
        parts.append(f"TokenRange={tok.start}:{tok.end}")
    return "|".join(parts) or "_"


def _word_line(w: Word, misc: str) -> str:
    return "\t".join([str(w.id), _field(w.form), _field(w.lemma), _field(w.upos), _field(w.xpos), _field(w.feats),
                      str(w.head), _field(w.deprel), _field(w.deps), misc])


def _check_ids(tokens: Sequence[Token], where: str) -> None:
    ids = [w.id for t in tokens for w in t.words]
    if any(not t.words for t in tokens) or ids != list(range(1, len(ids) + 1)):
        raise ValueError(f"{where}: word ids {ids[:12]} are not 1..n with a word in every token")
    if any(not 0 <= w.head <= len(ids) for t in tokens for w in t.words):
        raise ValueError(f"{where}: a head lies outside 0..{len(ids)}")


def _has_tokens(parse: object) -> bool:
    return isinstance(parse, list) and len(parse) > 0


def format_sentence(story_id: str, unit: Unit, tokens: Sequence[Token] | Refused | None, doc_text: str) -> str:
    """One CoNLL-U sentence block (comments, word lines, blank line) for sentence `unit.k` of a document."""
    lines = [f"# sent_id = {story_id}-{unit.k}", f"# text = {unit.text}", f"# span = {unit.start}:{unit.end}"]
    if isinstance(tokens, Refused) or not tokens:
        if isinstance(tokens, Refused):
            lines.append(f"# refused = {_field(tokens.reason)}")
        lines.append("# parse = empty")
        return "\n".join(lines) + "\n\n"
    _check_ids(tokens, f"{story_id}-{unit.k}")
    for tok in tokens:
        misc = _misc(tok, doc_text)
        if len(tok.words) > 1:
            first, last = tok.words[0].id, tok.words[-1].id
            lines.append(f"{first}-{last}\t{_field(tok.form)}\t_\t_\t_\t_\t_\t_\t_\t{misc}")
            lines.extend(_word_line(w, "_") for w in tok.words)
        else:
            lines.append(_word_line(tok.words[0], misc))
    return "\n".join(lines) + "\n\n"


def format_document(story_id: str, units: Sequence[Unit], parses: Sequence[Sequence[Token] | Refused | None],
                    doc_text: str) -> str:
    """The CoNLL-U of one document: `# newdoc id` before its first sentence, then one block per unit."""
    if len(units) != len(parses):
        raise ValueError(f"{story_id}: {len(parses)} parses for {len(units)} sentences")
    if not units:
        return ""
    blocks = [format_sentence(story_id, u, p, doc_text) for u, p in zip(units, parses, strict=True)]
    return f"# newdoc id = {story_id}\n" + "".join(blocks)


def _token_range(misc: str) -> tuple[int, int] | None:
    for part in misc.split("|"):
        if part.startswith("TokenRange="):
            a, b = part[len("TokenRange="):].split(":")
            return int(a), int(b)
    return None


def tokens_from_conllu(lines: Iterable[str], *, keep_ranges: bool = False) -> list[Token]:
    """Tokens from the word lines of one CoNLL-U sentence (comments already removed).

    Multi-word token ranges ("3-4") open a token whose words follow; empty nodes ("3.1") are skipped, as in the
    benchmark readers. A parser's MISC is not kept, because the artefact rebuilds it; with `keep_ranges` a token's
    offsets are read back from the TokenRange of its own line.
    """
    tokens: list[Token] = []
    mwt_end = 0
    for line in lines:
        cols = line.rstrip("\r\n").split("\t")
        if len(cols) != 10:
            raise ValueError(f"CoNLL-U word line has {len(cols)} columns, not 10: {line[:80]!r}")
        if "." in cols[0]:
            continue
        rng = _token_range(cols[9]) if keep_ranges else None
        if "-" in cols[0]:
            first, last = (int(x) for x in cols[0].split("-"))
            if last <= first:
                raise ValueError(f"bad multi-word range {cols[0]!r}")
            tokens.append(Token(form=cols[1], words=[], start=rng and rng[0], end=rng and rng[1]))
            mwt_end = last
            continue
        head = int(cols[6]) if cols[6] not in ("_", "") else 0
        word = Word(id=int(cols[0]), form=cols[1], lemma=cols[2], upos=cols[3], xpos=cols[4], feats=cols[5],
                    head=head, deprel=cols[7], deps=cols[8])
        if word.id <= mwt_end and tokens:
            tokens[-1].words.append(word)
        else:
            tokens.append(Token(form=word.form, words=[word], start=rng and rng[0], end=rng and rng[1]))
    return tokens


def _comment(line: str) -> tuple[str, str]:
    """Key and value of a "# key = value" comment line; the value may be empty ("# text = ")."""
    body = line[1:].lstrip(" ")
    key, sep, value = body.partition(" = ")
    if not sep:
        key, value = (body[:-2], "") if body.endswith(" =") else (body, "")
    return key.strip(), value


def _blocks(lines: Iterable[str]) -> Iterator[list[str]]:
    """Blank-line separated blocks of a CoNLL-U stream, without line ends (LF or CRLF, as a converting checkout
    may leave them)."""
    block: list[str] = []
    for line in lines:
        line = line.rstrip("\n")
        if line.endswith("\r"):
            line = line[:-1]
        if line:
            block.append(line)
        elif block:
            yield block
            block = []
    if block:
        yield block


def read_conllu(path: Path) -> Iterator[ConlluDocument]:
    """Read a parse artefact back, one document at a time, checking the layout of the module docstring.

    This is the one reader of the parse artefacts, used by every stage that reads them. It checks that sentence ids
    run 0..n-1 per document, that no document appears twice, that comments come before a block's word lines, and that
    a block holds word lines or, alone, `# parse = empty`, so a truncated or hand-edited file stops the reader
    instead of shifting sentence k. External CoNLL-U (UD gold, earlier benchmark parses) follows none of these
    conventions and is read by features.grammatical.parse_conllu.
    """
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    doc: ConlluDocument | None = None
    seen: set[str] = set()
    with opener(path, "rt", encoding="utf-8", newline="\n") as fh:
        for block in _blocks(fh):
            first_word = next((i for i, ln in enumerate(block) if not ln.startswith("#")), len(block))
            if any(ln.startswith("#") for ln in block[first_word:]):
                raise ValueError(f"{path}: a comment among the word lines of a sentence")
            comments = dict(_comment(ln) for ln in block[:first_word])
            body = block[first_word:]
            if "newdoc id" in comments:
                if doc is not None:
                    yield doc
                story_id = comments["newdoc id"]
                if not story_id or story_id in seen:
                    raise ValueError(f"{path}: document {story_id!r} is empty or appears twice")
                seen.add(story_id)
                doc = ConlluDocument(story_id=story_id)
            if doc is None:
                raise ValueError(f"{path}: a sentence before any '# newdoc id'")
            sent_id = comments.get("sent_id", "")
            prefix, _, k = sent_id.rpartition("-")
            if prefix != doc.story_id or not k.isdigit() or int(k) != len(doc.sentences):
                raise ValueError(f"{path}: sentence id {sent_id!r} out of sequence in document {doc.story_id!r}")
            if (comments.get("parse") == "empty") == bool(body):
                raise ValueError(f"{path}: sentence {sent_id!r} needs word lines or, alone, '# parse = empty'")
            span = None
            if comments.get("span"):
                a, b = comments["span"].split(":")
                span = (int(a), int(b))
            doc.sentences.append(ConlluSentence(
                sent_id=sent_id, k=int(k), text=comments.get("text", ""), span=span,
                tokens=tokens_from_conllu(body, keep_ranges=True), empty=comments.get("parse") == "empty",
                refused=comments.get("refused")))
    if doc is not None:
        yield doc


class ConlluShardWriter:
    """Write one parse artefact atomically and reproducibly.

    The text goes to a temporary file that is renamed into place on success, so a job killed at its time limit
    never leaves a file that looks complete (DESIGN.md). A run also removes whatever an earlier run published at
    the path when it starts, so a run that fails, is rejected or is killed leaves no earlier parse standing there
    as if it matched this run's inputs. gzip runs with mtime 0 and no file name, so a rerun on the same inputs is
    byte-identical and run records can compare hashes. reject() keeps the output as <path>.failed for inspection
    instead of publishing it; a later successful run removes that file.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.tmp = self.path.with_name(self.path.name + ".tmp")
        self.failed = self.path.with_name(self.path.name + FAILED_SUFFIX)
        self._rejected = False
        self._raw = None
        self._fh = None

    def __enter__(self) -> ConlluShardWriter:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.unlink(missing_ok=True)
        self._raw = open(self.tmp, "wb")
        self._fh = gzip.GzipFile(filename="", fileobj=self._raw, mode="wb", mtime=0) if self.path.suffix == ".gz" \
            else self._raw
        return self

    def write(self, text: str) -> None:
        """Append text (UTF-8, LF line ends)."""
        self._fh.write(text.encode("utf-8"))

    def reject(self) -> Path:
        """Keep the output as <path>.failed instead of <path> when the writer closes; returns that path."""
        self._rejected = True
        return self.failed

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fh is not self._raw:
            self._fh.close()
        self._raw.close()
        if self._rejected:
            self.tmp.replace(self.failed)
        elif exc_type is not None:
            self.tmp.unlink(missing_ok=True)
        else:
            self.tmp.replace(self.path)
            self.failed.unlink(missing_ok=True)


# ------------------------------------------------------------------------------------------- parsing documents


ParseResult = list[Token] | Refused | None
ParseFn = Callable[[list[str]], list[ParseResult]]


@dataclass
class ParseCounts:
    """Counts for the timing record, from which the dry run projects each parser's cost per unit.

    `words` are syntactic words (the unit of the presub throughput figures, words per second), `parser_tokens`
    surface tokens and `whitespace_tokens` whitespace-delimited tokens of the units (the unit of the catalogue's
    structure table), so the ratio of parser words to whitespace tokens is measured, not assumed. No subword model
    runs in the parent process, so there is no `tokens` count in DESIGN.md's sense. `empty_parses` counts the units
    sent to the parser that came back without a parse, the refused ones (`refused_units`) included. `offset_misses`
    are tokens the alignment could not place and `offset_inexact` placed tokens whose text differs from their form.
    """

    documents: int = 0
    documents_without_sentences: int = 0
    calls: int = 0
    sentences: int = 0
    empty_units: int = 0
    empty_parses: int = 0
    refused_units: int = 0
    characters: int = 0
    whitespace_tokens: int = 0
    parser_tokens: int = 0
    words: int = 0
    units_with_line_breaks: int = 0
    offset_misses: int = 0
    offset_inexact: int = 0
    max_unit_whitespace_tokens: int = 0
    max_refused_whitespace_tokens: int = 0
    max_document_sentences: int = 0

    _SUMMED = ("calls", "sentences", "empty_units", "empty_parses", "refused_units", "characters", "whitespace_tokens",
               "parser_tokens", "words", "units_with_line_breaks", "offset_misses", "offset_inexact")

    def add(self, stats: dict) -> None:
        """Add one document's statistics (iter_parsed or parse_document)."""
        self.documents += 1
        self.documents_without_sentences += stats["sentences"] == 0
        for key in self._SUMMED:
            setattr(self, key, getattr(self, key) + stats[key])
        self.max_unit_whitespace_tokens = max(self.max_unit_whitespace_tokens, stats["max_unit_whitespace_tokens"])
        self.max_refused_whitespace_tokens = max(self.max_refused_whitespace_tokens,
                                                 stats["max_refused_whitespace_tokens"])
        self.max_document_sentences = max(self.max_document_sentences, stats["sentences"])

    def as_dict(self) -> dict:
        """The counts as a plain dictionary."""
        return dict(self.__dict__)


def call_groups(items: Iterable[tuple[Document, list[Unit]]],
                sentences_per_call: int) -> Iterator[list[tuple[Document, list[Unit]]]]:
    """Group documents into parser calls, in order.

    With `sentences_per_call` 0 every text is a call of its own: a text's parse then cannot depend on which texts
    share its shard, so the 1 per cent smoke run reproduces the full run's rows (DESIGN.md, Determinism), and
    Stanza's padded parser batch is bounded by one story (the TU-4s lesson, see stanza_wrap). A positive value packs
    whole texts into calls of at most that many sentences, as TU-4s (400) and TU-4u (500) did, and a longer text
    is a call of its own. Grouping is greedy from the first document, so a prefix of whole groups regroups alike.
    """
    group: list[tuple[Document, list[Unit]]] = []
    size = 0
    for doc, units in items:
        n = sum(1 for u in units if u.text)
        if group and (sentences_per_call <= 0 or size + n > sentences_per_call):
            yield group
            group, size = [], 0
        group.append((doc, units))
        size += n
    if group:
        yield group


def _check_result(p: object, where: str) -> ParseResult:
    if p is None or isinstance(p, Refused):
        return p
    if isinstance(p, list) and all(isinstance(t, Token) for t in p):
        return p
    raise TypeError(f"{where}: a parser returned {type(p).__name__}, not a token list, Refused or None")


def _document_output(doc: Document, units: Sequence[Unit], parses: list[ParseResult],
                     max_skip: int) -> tuple[str, dict]:
    """Align, format and count one document's parses."""
    misses = sum(align_tokens(u, p, max_skip) for u, p in zip(units, parses, strict=True) if _has_tokens(p))
    inexact = sum(_inexact(p, doc.text) for p in parses if _has_tokens(p))
    text = format_document(doc.story_id, units, parses, doc.text)
    ws = [len(u.text.split()) for u in units]
    live = [(u, p) for u, p in zip(units, parses, strict=True) if u.text]
    stats = {
        "sentences": len(units),
        "empty_units": len(units) - len(live),
        "empty_parses": sum(1 for _, p in live if not _has_tokens(p)),
        "refused_units": sum(1 for _, p in live if isinstance(p, Refused)),
        "characters": sum(len(u.text) for u in units),
        "whitespace_tokens": sum(ws),
        "parser_tokens": sum(len(p) for p in parses if _has_tokens(p)),
        "words": sum(len(t.words) for p in parses if _has_tokens(p) for t in p),
        "units_with_line_breaks": sum(1 for u in units if doc.text[u.start:u.end] != u.text),
        "offset_misses": misses,
        "offset_inexact": inexact,
        "max_unit_whitespace_tokens": max(ws, default=0),
        "max_refused_whitespace_tokens": max((len(u.text.split()) for u, p in live if isinstance(p, Refused)),
                                             default=0),
    }
    return text, stats


ParsedDocument = tuple[int, Document, list[Unit], list[ParseResult], str, dict]


def iter_parsed(items: Iterable[tuple[Document, list[Unit]]], parse_fn: ParseFn, *, max_skip: int,
                sentences_per_call: int = 0) -> Iterator[ParsedDocument]:
    """Parse documents call by call (call_groups) and yield, per document, its call's index, the document, its
    units, its parses aligned with the units (a token list, Refused or None), its CoNLL-U and its statistics.

    An empty unit is not sent to the parser and keeps an empty block. A parser returns one result per sentence it
    is given, in order.
    """
    for gi, group in enumerate(call_groups(items, sentences_per_call)):
        live = [(j, u) for j, (_, units) in enumerate(group) for u in units if u.text]
        parsed = parse_fn([u.text for _, u in live]) if live else []
        if len(parsed) != len(live):
            raise RuntimeError(f"{group[0][0].story_id}: the parser returned {len(parsed)} sentences for {len(live)}")
        by_doc: list[dict[int, ParseResult]] = [{} for _ in group]
        for (j, u), p in zip(live, parsed, strict=True):
            by_doc[j][u.k] = _check_result(p, f"{group[j][0].story_id}-{u.k}")
        for j, (doc, units) in enumerate(group):
            parses = [by_doc[j].get(u.k) for u in units]
            text, stats = _document_output(doc, units, parses, max_skip)
            stats["calls"] = int(j == 0 and bool(live))
            yield gi, doc, units, parses, text, stats


def parse_document(doc: Document, units: Sequence[Unit], parse_fn: ParseFn, *, max_skip: int) -> tuple[str, dict]:
    """Parse one document's units in a single parser call and return its CoNLL-U and statistics."""
    [(_, _, _, _, text, stats)] = iter_parsed([(doc, list(units))], parse_fn, max_skip=max_skip)
    return text, stats


def parse_shard(path: Path, items: Iterable[tuple[Document, list[Unit]]], parse_fn: ParseFn, *, max_skip: int,
                keep_first: int = 0, check: Callable[[ParseCounts], str | None] | None = None,
                sentences_per_call: int = 0,
                observe: Callable[[Document, list[Unit], list[ParseResult]], None] | None = None,
                ) -> tuple[ParseCounts, list[tuple[Document, list[Unit], str]]]:
    """Parse every document of a shard into one artefact; return the counts and the documents kept for a rerun.

    `keep_first` keeps at least that many documents, completed to a whole parser call, so a rerun with the same
    `sentences_per_call` regroups them alike. `observe`, if given, sees each document's units and parses as they
    are written. `check`, if given, runs before the file is published; a message from it keeps the output as
    <path>.failed and raises, so a parse that fails a quality check is never mistaken for a finished artefact.
    """
    counts, kept, keep_group = ParseCounts(), [], None
    with ConlluShardWriter(path) as writer:
        for gi, doc, units, parses, text, stats in iter_parsed(items, parse_fn, max_skip=max_skip,
                                                               sentences_per_call=sentences_per_call):
            writer.write(text)
            counts.add(stats)
            if observe is not None:
                observe(doc, units, parses)
            if len(kept) < keep_first or gi == keep_group:
                kept.append((doc, units, text))
                if len(kept) == keep_first:
                    keep_group = gi
        problem = check(counts) if check is not None else None
        if problem:
            kept_as = writer.reject()
            raise RuntimeError(f"{problem}; output kept as {kept_as}")
    return counts, kept
