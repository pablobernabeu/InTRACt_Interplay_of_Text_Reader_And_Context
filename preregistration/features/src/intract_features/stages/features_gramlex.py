"""Stage features_gramlex: the registered grammatical, lexical, diversity and page features of every text.

Reads documents, segments, parses_stanza and parses_udpipe of one shard and writes one record per document to the
features_gramlex artefact. `values` holds the registered quantities and their registered variants; `diagnostics`
holds the two parser members, counts, coverage and alignment. CPU only, in the core environment.

Each input is read through its producer's reader: segments with segment.sentences_from_record (checked against the
document's text hash, so a stale artefact stops the stage), parses with parse.read_conllu (sentence k of a document
is sentence k of its segmentation, and each surface token carries its offsets in Document.text as TokenRange), and
words with text.words.words, the registered word function, whose anchors place each word in a sentence. Every
artefact follows the documents' order, which the stage reads first, so it streams a shard in constant memory.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from intract_features import config as config_mod
from intract_features import records
from intract_features.cli import Stage, StageContext
from intract_features.features import dialogue, diversity, grammatical, lexical, pages, parsemean
from intract_features.parse import read_conllu as read_parse
from intract_features.parse.long_units import LongUnitRule
from intract_features.segment import sentences_from_record
from intract_features.text import words as text_words

STAGE = Stage(name="features_gramlex", inputs=("documents", "segments", "parses_stanza", "parses_udpipe"),
              outputs=("features_gramlex",), device="cpu", env="core",
              description="registered grammatical, lexical, diversity and page features")

NAN = float("nan")
LEXICAL_VALUES = ("mean_zipf", "rare_share", "mean_zipf_matched", "rare_share_zipf3", "rare_share_matched",
                  "word_length", "word_length_all_words", "lexical_density", "mattr", "mattr_content_forms",
                  "mattr_all_words", "mtld")


class Aligned:
    """Records of a stream written in the documents' order, fetched story by story in that order.

    Every stage writes its artefact while reading the documents in order, so a stream that reaches a later story
    has no record of the one requested, and nothing needs to be held back: memory stays constant however many
    stories a stage dropped. A record of an earlier story (out of order or duplicated) or of an unknown story is
    skipped and counted, so a broken order shows up as missing records and in the timing record.
    """

    def __init__(self, items: Iterable[tuple[str | None, object]], order: Mapping[str, int]):
        self._it: Iterator = iter(items)
        self._order = order
        self._peek: tuple | None = None
        self.out_of_order = 0
        self.unknown = 0

    def get(self, key: str):
        """The record of `key`, or None if the stream has none."""
        want = self._order[key]
        while True:
            if self._peek is None:
                self._peek = next(self._it, None)
                if self._peek is None:
                    return None
            k, v = self._peek
            at = self._order.get(k)
            if at == want:
                self._peek = None
                return v
            if at is not None and at > want:
                return None
            if at is None:
                self.unknown += 1
            else:
                self.out_of_order += 1
            self._peek = None


def check_language(lang_cfg: Mapping) -> None:
    """Refuse a language whose registered lexical rules this version does not implement."""
    if not lang_cfg.get("spaced", True):
        raise NotImplementedError("unspaced scripts take their words from the frozen segmenter (qmd Measures), "
                                  "which this stage does not yet read")
    if lang_cfg["iso"] == "ko":
        raise NotImplementedError("Korean content status by Kiwi morphemes (S3) is not implemented")


@dataclass(frozen=True)
class GramlexEnv:
    """Everything the stage builds once per run: rules, the lookup key, letters, resources and settings."""

    gram: grammatical.GrammarRules
    lex: lexical.LexicalRules
    div: diversity.DiversityRules
    long_rule: LongUnitRule
    key: lexical.LookupNormaliser
    letters: lexical.LetterCounter
    resource: object
    inventory: frozenset[str] | None
    quotes: dialogue.QuoteInventory | None
    anchor: str
    count_empty: bool
    per_words: int
    strict: bool

    @classmethod
    def build(cls, config: Mapping, lang: str) -> GramlexEnv:
        """Read the merged configuration for one language and load its frequency resource."""
        cfg = config["stages"][STAGE.name]
        lang_cfg = config_mod.language(config, lang)
        check_language(lang_cfg)
        iso = lang_cfg["iso"]
        gram = grammatical.GrammarRules.from_config(cfg)
        quotes = None
        if gram.speech_rule == "detector_spans":
            dialogue_cfg = config["stages"][cfg["grammatical"]["speech"]["detector_config_stage"]]["dialogue"]
            quotes = dialogue.QuoteInventory.from_config(lang_cfg["quotes"], dialogue_cfg, iso)
        lex = lexical.LexicalRules.from_config(cfg, iso)
        lex_code = "zh-hant" if iso == "zh" and lang_cfg.get("script") == "Hant" else iso
        key = lexical.LookupNormaliser(cfg["lexical"]["normalisation"], lex_code,
                                       cfg["lexical"]["casing"]["dotted_i_languages"])
        inventory = lexical.load_inventory(Path(lex.name_inventory)) if lex.name_rule == "inventory" else None
        anchor = cfg["sentences"]["word_anchor"]
        if anchor not in ("first_alnum", "start"):
            raise ValueError(f"sentences.word_anchor must be 'first_alnum' or 'start', not {anchor!r}")
        long_rule = LongUnitRule.from_config(config, cfg["parser_mean"]["long_unit_config_stage"])
        resource = lexical.build_frequency_resource(cfg["lexical"]["frequency"], iso, config.get("resources"))
        return cls(gram=gram, lex=lex, div=diversity.DiversityRules.from_config(cfg, iso), long_rule=long_rule,
                   key=key, letters=lexical.LetterCounter(cfg["lexical"]["letters"], iso), resource=resource,
                   inventory=inventory, quotes=quotes, anchor=anchor,
                   count_empty=bool(cfg["sentences"]["count_empty_sentences"]),
                   per_words=int(cfg["pages"]["per_words"]), strict=bool(cfg["stage"]["strict"]))


def clean(obj):
    """Map every non-finite number to None, recursively, so that each record is strict JSON (DESIGN.md)."""
    if isinstance(obj, float):
        return records.finite_or_none(obj)
    if isinstance(obj, Mapping):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [clean(v) for v in obj]
    return obj


def sentence_dicts(parsed) -> list[dict]:
    """The sentences of one parse.read_conllu document as gfeat-shaped dicts, each with its tokens' offsets in
    Document.text under "token_spans" (None for a token the parse stage could not place)."""
    out = []
    for s in parsed.sentences:
        words = [{"id": w.id, "form": w.form, "lemma": w.lemma, "upos": w.upos, "head": w.head, "deprel": w.deprel}
                 for t in s.tokens for w in t.words]
        spans = [None if t.start is None or t.end is None else (t.start, t.end) for t in s.tokens]
        out.append({"sent_id": s.sent_id, "text": s.text, "words": words, "tokens": [t.form for t in s.tokens],
                    "token_words": [tuple(w.id for w in t.words) for t in s.tokens], "token_spans": spans})
    return out


def place_tokens(sents: Sequence[dict], sentences: Sequence[tuple[int, int]], text: str) -> Counter:
    """Fill in offsets for any sentence with an unplaced token by aligning the sentence on non-space characters.

    Returns how each sentence's offsets were found: "token_range" (all from the artefact), "empty" (a sentence the
    parser returned nothing for), or the status of grammatical.align_tokens.
    """
    status: Counter = Counter()
    for s, (a, b) in zip(sents, sentences, strict=True):
        if not s["tokens"]:
            status["empty"] += 1
        elif all(sp is not None for sp in s["token_spans"]):
            status["token_range"] += 1
        else:
            spans, st = grammatical.align_tokens(text[a:b], s["tokens"])
            s["token_spans"] = [None if sp is None else (a + sp[0], a + sp[1]) for sp in spans]
            status[st] += 1
    return status


def _usable(parse, n_sentences: int, which: str, missing: list, info: Counter, strict: bool):
    """The parse's sentences if they pair one to one with the segments, else None with the reason recorded.

    A document with no sentence has no parse block (parse/__init__.py), which is no fault.
    """
    if parse is None and n_sentences == 0:
        return []
    if parse is None:
        reason = f"{which}: no parse"
    elif len(parse) != n_sentences:
        reason = f"{which}: {len(parse)} parsed sentences for {n_sentences} segments"
    else:
        return parse
    if strict:
        raise ValueError(reason)
    missing.append(reason)
    info[f"{which}_unusable"] += 1
    return None


def _sentence_counts(parse: Sequence[dict], text: str, mask: Sequence[bool] | None, env: GramlexEnv) -> list[dict]:
    """Each sentence's counts; under the detector route, direct speech comes from the detector's mask (gap G6)."""
    if mask is None:
        return [grammatical.sentence_counts(s, env.gram) for s in parse]
    return [grammatical.sentence_counts(
        s, env.gram, speech_ids=grammatical.speech_ids_from_mask(text, s["token_spans"], s["token_words"], mask))
        for s in parse]


def parse_tokens(sents: Sequence[dict], env: GramlexEnv) -> list[lexical.Token]:
    """A parse's surface tokens with document offsets and decided words."""
    is_name = lexical.name_predicate(sents, env.lex, env.key, env.inventory)
    return lexical.build_tokens(sents, [s["token_spans"] for s in sents], is_name, env.lex)


def lexical_block(tokens: Sequence[lexical.Token], text: str, words: Sequence[tuple[int, int]],
                  env: GramlexEnv) -> tuple[dict, dict]:
    """The lexical and diversity values of one parse, with their diagnostics."""
    classes = lexical.classify_words(words, tokens, env.lex.name_word_rule)
    seqs = diversity.diversity_sequences(tokens, env.div)
    values, diag = {}, {}
    for part, (v, d) in (("frequency", lexical.frequency_features(tokens, env.resource, env.key, env.lex)),
                         ("word_length", lexical.word_length_features(tokens, text, words, classes, env.letters,
                                                                      env.lex)),
                         ("density", lexical.density_features(tokens, classes, env.lex)),
                         ("diversity", diversity.diversity_features(seqs, env.div))):
        values.update(v)
        diag[part] = d
    diag["names"] = {"name_syntactic_words": sum(w.name for t in tokens for w in t.words),
                     "name_words": sum(1 for _, nm, _ in classes if nm)}
    return values, diag


def document_features(doc: records.Document, words: Sequence[text_words.Word],
                      sentences: Sequence[tuple[int, int]] | None, stanza: Sequence[dict] | None,
                      udpipe: Sequence[dict] | None, env: GramlexEnv) -> tuple[dict, Counter]:
    """The output record of one document and the counts it adds to the timing record.

    `words` are the registered words (text.words.words), `sentences` the segmentation's spans, and `stanza` and
    `udpipe` the parsed sentences (sentence_dicts), each None where its input has no record of the document.
    """
    text = doc.text
    spans = [(w.start, w.end) for w in words]
    info: Counter = Counter(documents=1, words=len(words), characters=len(text))
    missing: list[str] = []
    values = dict(pages.page_features(len(doc.pages), len(words), env.per_words))
    diag: dict = {"characters": len(text)}
    if sentences is None:
        if env.strict:
            raise ValueError(f"{doc.story_id}: no segmentation")
        missing.append("segments: none")
        info["segments_missing"] += 1
        stanza = udpipe = None
        values["mean_sentence_length"] = NAN
        gvals, gdiag = parsemean.grammatical_features(None, None, [], env.gram, env.long_rule)
    else:
        anchors = [w.anchor if env.anchor == "first_alnum" else w.start for w in words]
        wps, outside = grammatical.words_per_sentence(anchors, sentences)
        values["mean_sentence_length"] = grammatical.mean_sentence_length(wps, env.count_empty)
        diag.update(sentences=len(sentences), sentences_with_words=sum(1 for c in wps if c),
                    words_outside_sentences=outside, pages=pages.page_break_alignment(doc.page_spans(), sentences))
        info["sentences"] += len(sentences)
        stanza = _usable(stanza, len(sentences), "stanza", missing, info, env.strict)
        udpipe = _usable(udpipe, len(sentences), "udpipe", missing, info, env.strict)
        mask = dialogue.speech_mask(doc.pages, env.quotes) if env.quotes is not None else None
        counts = {}
        for name, parse in (("stanza", stanza), ("udpipe", udpipe)):
            if parse is not None:
                info.update({f"{name}_offsets_{k}": v for k, v in place_tokens(parse, sentences, text).items()})
                info[f"syntactic_words_{name}"] += sum(len(s["words"]) for s in parse)
            counts[name] = None if parse is None else _sentence_counts(parse, text, mask, env)
        gvals, gdiag = parsemean.grammatical_features(counts["stanza"], counts["udpipe"], wps, env.gram,
                                                      env.long_rule)
        info["long_units"] += gdiag["long_units"]
    values.update(gvals)
    diag["grammatical"] = gdiag
    if stanza is not None:
        lvals, ldiag = lexical_block(parse_tokens(stanza, env), text, spans, env)
        values.update(lvals)
        diag["lexical"] = ldiag
    else:
        values.update(dict.fromkeys(LEXICAL_VALUES, NAN))
        values.update({f"mattr_window{w}": NAN for w in env.div.variant_windows})
    if udpipe is not None:
        # S3: the agreement of LexicalDifficulty across "the two parsers' lemmas for diversity and density"
        tokens_u = parse_tokens(udpipe, env)
        dens_u, _ = lexical.density_features(tokens_u, lexical.classify_words(spans, tokens_u, env.lex.name_word_rule),
                                             env.lex)
        seqs_u = diversity.diversity_sequences(tokens_u, env.div)
        diag["udpipe_alternatives"] = {"mattr": diversity.mattr(seqs_u["content_lemma"], env.div.window,
                                                                env.div.short_text),
                                       "lexical_density": dens_u["lexical_density"]}
    diag["missing"] = missing
    return {"story_id": doc.story_id, "lang": doc.lang, "values": clean(values), "diagnostics": clean(diag)}, info


def _segment_spans(rec: Mapping | None, doc: records.Document) -> list[tuple[int, int]] | None:
    """The sentence spans of a segments record, refusing one cut from another text."""
    if rec is None:
        return None
    digest = rec.get("text_sha256")
    if digest is not None and digest != hashlib.sha256(doc.text.encode("utf-8")).hexdigest():
        raise ValueError(f"segments record {doc.story_id!r} was cut from another text (stale artefact)")
    return [(s.start, s.end) for s in sentences_from_record(rec)]


def run(ctx: StageContext) -> dict:
    """Compute the features of every document of the shard and write them; return counts for the timing record."""
    env = GramlexEnv.build(ctx.config, ctx.lang)
    # One cheap pass over the documents gives their order, which every other artefact follows.
    order = {obj["story_id"]: i for i, obj in enumerate(ctx.read("documents"))}
    streams = {
        "segments": Aligned(((r["story_id"], r) for r in ctx.read("segments")), order),
        "stanza": Aligned(((d.story_id, d) for d in read_parse(ctx.path("parses_stanza", ext="conllu.gz"))), order),
        "udpipe": Aligned(((d.story_id, d) for d in read_parse(ctx.path("parses_udpipe", ext="conllu.gz"))), order),
    }
    info: Counter = Counter()

    def outputs() -> Iterator[dict]:
        for doc in ctx.documents():
            parses = {name: streams[name].get(doc.story_id) for name in ("stanza", "udpipe")}
            rec, doc_info = document_features(
                doc, text_words.words(doc.text), _segment_spans(streams["segments"].get(doc.story_id), doc),
                *(None if p is None else sentence_dicts(p) for p in parses.values()), env)
            broken = {n: (s.out_of_order, s.unknown) for n, s in streams.items() if s.out_of_order or s.unknown}
            if broken and env.strict:
                # raised inside the writer's loop, so no artefact that looks complete is left behind
                raise ValueError(f"records out of the documents' order or unknown (out of order, unknown): {broken}")
            info.update(doc_info)
            yield rec

    written = ctx.write(STAGE.outputs[0], outputs())
    counts = dict(info)
    counts["documents"] = written
    for name, s in streams.items():
        if s.out_of_order or s.unknown:
            counts[f"{name}_out_of_order"], counts[f"{name}_unknown"] = s.out_of_order, s.unknown
    counts["frequency_resource"] = env.resource.describe() if env.resource is not None else {"resource": "none"}
    return counts
