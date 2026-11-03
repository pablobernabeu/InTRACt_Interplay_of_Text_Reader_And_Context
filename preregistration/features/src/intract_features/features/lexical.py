"""Lexical features of one text: frequency, the rare-word share, word length and lexical density.

Promoted from error_model/scripts/lexrules.py (FreqList, normalise, letters) and the counting rules of
em_counts.py, with every constant moved to config/stages/features_gramlex.toml. The anchors:

- qmd Materials: "mean log frequency of content words, the share of content tokens below ten per million (Zipf 4)
  on the uniform frequency resource [...] and mean orthographic length. A content token that is not a name and is
  absent from the frequency resource counts as rare and takes the resource's floor value in the mean."
- qmd Measures: "Parse counts and frequency lookups use syntactic words instead, the units a parser yields after
  splitting multi-word tokens."
- S3: "Word length counts letters per content word, names excluded, by script." and "Lexical density is the share
  of words, in the outcome's unit, that contain a content syntactic word, with punctuation and names excluded."

The frequency resource is INTERIM (P48): wordfreq 3.1.1 stands in until the OpenSubtitles 2024 lists are built,
and `CountList` reads those lists, with the Laplace-smoothed Zipf of van Heuven et al. (2014), once they exist.
Lexical features are computed on the Stanza parse, as the error model served them (em_core.py: GrammaticalLoad
from the parser mean, LexicalDifficulty from Stanza); UDPipe's lemmas and tags serve only the reported agreement
for diversity and density (S3: "the two parsers' lemmas for diversity and density").
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

NAN = float("nan")
NAME_RULES = ("token_upos", "type_majority_text", "inventory")


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else NAN


def _ranges(pairs: Iterable[Sequence[int]]) -> tuple[tuple[int, int], ...]:
    return tuple((int(a), int(b)) for a, b in pairs)


def _in(cp: int, ranges: Iterable[tuple[int, int]]) -> bool:
    return any(a <= cp <= b for a, b in ranges)


@lru_cache(maxsize=1 << 16)
def is_wordlike(form: str) -> bool:
    """A form with at least one letter or digit (b4_pud_units.is_wordlike); cached, as forms recur constantly."""
    return any(c.isalnum() for c in form)


@dataclass(frozen=True)
class LexicalRules:
    """The lexical counting rules, read once from the [lexical] table of the stage configuration."""

    content_upos: frozenset[str]
    name_upos: frozenset[str]
    name_share: float
    name_rule: str
    name_inventory: str
    name_word_rule: str
    aggregation: str
    rare_zipf: float
    rare_zipf_sensitivity: float
    word_length_unit: str
    density_unit: str

    @classmethod
    def from_config(cls, stage_cfg: Mapping, iso: str) -> LexicalRules:
        """Build the rules for one language from the stage configuration."""
        lx = stage_cfg["lexical"]
        nm, fq = lx["names"], lx["frequency"]
        rules = cls(content_upos=frozenset(lx["content_upos"]),
                    name_upos=frozenset(nm["name_upos"]) | frozenset(nm.get("name_upos_extra", {}).get(iso, ())),
                    name_share=float(nm["name_share"]), name_rule=nm["rule"], name_inventory=nm["inventory"],
                    name_word_rule=nm["word_rule"], aggregation=fq["aggregation"], rare_zipf=float(fq["rare_zipf"]),
                    rare_zipf_sensitivity=float(fq["rare_zipf_sensitivity"]),
                    word_length_unit=lx["word_length"]["unit"], density_unit=lx["density"]["unit"])
        checks = {"names.rule": (rules.name_rule, NAME_RULES),
                  "names.word_rule": (rules.name_word_rule, ("any", "all")),
                  "frequency.aggregation": (rules.aggregation, ("orthographic_word", "syntactic_word")),
                  "word_length.unit": (rules.word_length_unit, ("syntactic_word", "word")),
                  "density.unit": (rules.density_unit, ("word", "syntactic_word"))}
        for name, (value, allowed) in checks.items():
            if value not in allowed:
                raise ValueError(f"lexical.{name} must be one of {allowed}, not {value!r}")
        return rules


# ---------------------------------------------------------------- casing and lookup normalisation


def lower(s: str, dotted_i: bool) -> str:
    """Lower-case with lower(), never casefold(); in a dotted-I language I with a dot becomes i and I becomes
    dotless i first (plan v3, lookup normalisation).

    The text is composed (NFC) before the dotted-I replacement, as lexrules.key_lower does: UDPipe 2.17 writes some
    Turkish lemmas with a decomposed I and combining dot above, which would otherwise become a dotless i with a
    stray dot and split one type in two.
    """
    if dotted_i:
        s = unicodedata.normalize("NFC", s).replace("\u0130", "i").replace("I", "\u0131")
    return s.lower()


class LookupNormaliser:
    """The one normalisation applied to frequency lists and texts alike (S3; lexrules.normalise).

    Order, as in lexrules.normalise: NFC, deletions, shared map, then the language's NFKC ranges, deleted ranges and
    map, lower-casing, the OpenCC conversion and the post-lower map. `lex` is the ISO code, or "zh-hant" for
    Traditional Chinese.
    """

    def __init__(self, norm_cfg: Mapping, lex: str, dotted_i_languages: Iterable[str]):
        self.lex = lex
        self._delete = dict.fromkeys(map(ord, norm_cfg.get("delete", ())), None)
        self._map = str.maketrans(dict(norm_cfg.get("map", {})))
        lang = norm_cfg.get("lang", {}).get(lex, {})
        self._nfkc = _ranges(lang.get("nfkc_ranges", ()))
        dels = _ranges(lang.get("delete_ranges", ()))
        cls = "".join(f"{re.escape(chr(a))}-{re.escape(chr(b))}" for a, b in dels)
        self._lang_delete = re.compile(f"[{cls}]") if dels else None
        self._lang_map = str.maketrans(dict(lang.get("map", {})))
        self._post = str.maketrans(dict(lang.get("post_lower_map", {})))
        self._dotted_i = lex in set(dotted_i_languages)
        self._opencc_mode = lang.get("opencc")
        self._opencc = None
        self._cache: dict[str, str] = {}

    def __call__(self, word: str) -> str:
        """The lookup key of a word form."""
        key = self._cache.get(word)
        if key is None:
            key = self._cache[word] = self._normalise(word)
        return key

    def _normalise(self, word: str) -> str:
        s = unicodedata.normalize("NFC", word).translate(self._delete).translate(self._map)
        if self._nfkc:
            s = "".join(unicodedata.normalize("NFKC", c) if _in(ord(c), self._nfkc) else c for c in s)
        if self._lang_delete is not None:
            s = self._lang_delete.sub("", s)
        s = lower(s.translate(self._lang_map), self._dotted_i)
        if self._opencc_mode:
            if self._opencc is None:
                import opencc  # Traditional Chinese only; OpenCC 1.4.2 is pinned in S3

                self._opencc = opencc.OpenCC(self._opencc_mode)
            s = self._opencc.convert(s)
        return s.translate(self._post)


# ---------------------------------------------------------------- letters by script


class LetterCounter:
    """Letters of a word by script (S3; lexrules.letters), on the NFC form.

    "jamo" counts conjoining jamo after canonical decomposition, "han" Han characters, "thai" consonants and vowels
    without tone marks, "arabic_base" base letters (category Lo, so no tatweel or marks), and "letters" every
    Unicode letter (category L), which leaves combining marks out.
    """

    def __init__(self, letters_cfg: Mapping, iso: str):
        self.rule = letters_cfg["rule_by_language"].get(iso, "letters")
        if self.rule not in ("letters", "jamo", "han", "thai", "arabic_base"):
            raise ValueError(f"unknown letter rule {self.rule!r} for {iso!r}")
        self._jamo = _ranges(letters_cfg["jamo_ranges"])
        self._thai = _ranges(letters_cfg["thai_ranges"])

    def __call__(self, word: str) -> int:
        """The letter count of one word."""
        w = unicodedata.normalize("NFC", word)
        if self.rule == "jamo":
            return sum(1 for c in unicodedata.normalize("NFD", w) if _in(ord(c), self._jamo))
        if self.rule == "han":
            return sum(1 for c in w if "CJK" in unicodedata.name(c, ""))
        if self.rule == "thai":
            return sum(1 for c in w if _in(ord(c), self._thai))
        if self.rule == "arabic_base":
            return sum(1 for c in w if unicodedata.category(c) == "Lo")
        return sum(1 for c in w if unicodedata.category(c).startswith("L"))


# ---------------------------------------------------------------- frequency resources


def sha256_of(path: Path) -> str:
    """SHA-256 hex of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_pin(path: Path, pins: Mapping, key: str) -> str:
    """Check a resource file against its pin in resources.lock.json before it is read (DESIGN.md, Configuration).

    Returns "verified", or "unpinned" when the lock has no entry yet; a mismatch raises. An entry is either the
    SHA-256 itself or a table with a "sha256" field.
    """
    entry = pins.get(key)
    if entry is None:
        return "unpinned"
    expected = entry if isinstance(entry, str) else entry.get("sha256")
    found = sha256_of(path)
    if expected != found:
        raise RuntimeError(f"{path} does not match its pin {key!r}: expected {expected}, found {found}")
    return "verified"


class WordfreqList:
    """INTERIM frequency resource (P48): a wordfreq wordlist read as a dictionary, as lexrules.FreqList did.

    No wordfreq tokeniser is used, so lookups take the registered key of the syntactic word. wordfreq stores bucket
    i as the frequency 10**(-i/100), so the Zipf value is exactly (900 - i)/100 (wordfreq.cB_to_zipf); the
    benchmark's log10(frequency) + 9 differs from it by about 1e-16. A word absent from the list takes the list's
    lowest Zipf as its floor.
    """

    def __init__(self, code: str, wordlist: str, version: str, pins: Mapping | None = None,
                 require_pin: bool = False):
        import importlib.metadata

        import wordfreq

        found = importlib.metadata.version("wordfreq")
        if found != version:
            raise RuntimeError(f"wordfreq {version} is configured but {found} is installed")
        available = wordfreq.available_languages(wordlist)
        if code not in available:
            raise LookupError(f"wordfreq {version} has no {wordlist!r} list for {code!r}")
        self.path = Path(available[code])
        key = f"wordfreq-{version}/{self.path.name}"
        self.pin = verify_pin(self.path, pins or {}, key)
        if require_pin and self.pin != "verified":  # checked before the list is read (DESIGN.md, Configuration)
            raise RuntimeError(f"{self.path} has no pin {key!r} in resources.lock.json")
        self.zipf: dict[str, float] = {}
        for index, bucket in enumerate(wordfreq.get_frequency_list(code, wordlist)):
            z = (900 - index) / 100
            for w in bucket:
                self.zipf[w] = z  # a later bucket overwrites, as in wordfreq.get_frequency_dict
        self.floor = min(self.zipf.values())
        self.name = f"wordfreq {version} {wordlist} {code}"

    def lookup(self, key: str) -> tuple[float, bool]:
        """(Zipf, absent) of one lookup key; an absent key takes the floor."""
        z = self.zipf.get(key)
        return (self.floor, True) if z is None else (z, False)

    def describe(self) -> dict:
        """What the run record should say about the resource."""
        return {"resource": self.name, "file": self.path.name, "pin": self.pin, "floor_zipf": self.floor,
                "types": len(self.zipf), "interim": True}


class CountList:
    """A frequency list of lookup units and counts, as the OpenSubtitles 2024 builder writes them (P48).

    Zipf = log10[(c + 1) / ((N + T) / 10**6)] + 3, with N the tokens and T the types of the list (van Heuven et
    al., 2014; S3: "frequencies are expressed as Zipf values with Laplace smoothing"), and an absent unit takes the
    smoothed floor, the value at c = 0 (S3: "takes the smoothed floor value").
    """

    def __init__(self, counts: Mapping[str, int], name: str, n_tokens: int | None = None,
                 n_types: int | None = None, pin: str = "unpinned"):
        n = sum(counts.values()) if n_tokens is None else n_tokens
        t = len(counts) if n_types is None else n_types
        per_million = (n + t) / 1e6
        self.zipf = {k: math.log10((c + 1) / per_million) + 3 for k, c in counts.items()}
        self.floor = math.log10(1 / per_million) + 3
        self.name, self.pin, self.n_tokens, self.n_types = name, pin, n, t

    def lookup(self, key: str) -> tuple[float, bool]:
        """(Zipf, absent) of one lookup key; an absent key takes the smoothed floor."""
        z = self.zipf.get(key)
        return (self.floor, True) if z is None else (z, False)

    def describe(self) -> dict:
        """What the run record should say about the resource."""
        return {"resource": self.name, "pin": self.pin, "floor_zipf": self.floor, "tokens": self.n_tokens,
                "types": self.n_types, "interim": False}


def load_count_list(path: Path, pins: Mapping | None = None, require_pin: bool = False) -> CountList:
    """Read a list of `unit<TAB>count` lines (lines starting with # are comments); the format awaits the list
    builder (P48)."""
    path = Path(path)
    pin = verify_pin(path, pins or {}, f"count_list/{path.name}")
    if require_pin and pin != "verified":  # checked before the list is read (DESIGN.md, Configuration)
        raise RuntimeError(f"{path} has no pin 'count_list/{path.name}' in resources.lock.json")
    counts: dict[str, int] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            unit, count = line.rstrip("\r\n").split("\t")
            counts[unit] = counts.get(unit, 0) + int(count)
    return CountList(counts, name=path.name, pin=pin)


def resource_pins(lock: Mapping | None) -> Mapping:
    """The entries of resources.lock.json, which may sit at its top level or under a "resources" table (the lock
    belongs to the ARC set-up; features_discourse reads it the same way)."""
    lock = lock or {}
    nested = lock.get("resources")
    return nested if isinstance(nested, Mapping) else lock


def build_frequency_resource(freq_cfg: Mapping, iso: str, pins: Mapping | None = None):
    """The configured frequency resource for a language, or None where it has no list (the anchor is then lost in
    that language, as the frequency gates would decide). `pins` is the parsed resources.lock.json."""
    pins = resource_pins(pins)
    require_pin = bool(freq_cfg.get("require_pin", False))
    if freq_cfg["resource"] == "wordfreq":
        code = "zh" if iso.startswith("zh") else iso  # lexrules.FreqList: one Chinese list for both scripts
        try:
            return WordfreqList(code, freq_cfg["wordfreq_wordlist"], freq_cfg["wordfreq_version"], pins,
                                require_pin=require_pin)
        except LookupError:
            return None
    if freq_cfg["resource"] == "count_list":
        if not freq_cfg["count_list"]:
            raise ValueError("lexical.frequency.count_list must name the list file")
        return load_count_list(Path(freq_cfg["count_list"]), pins, require_pin=require_pin)
    raise ValueError(f"unknown frequency resource {freq_cfg['resource']!r}")


# ---------------------------------------------------------------- names and tokens


@dataclass(frozen=True)
class SynWord:
    """One syntactic word of a parse, with its name and content status decided."""

    form: str
    lemma: str
    upos: str
    deprel: str
    name: bool
    content: bool


@dataclass(frozen=True)
class Token:
    """One surface token of a parse: its offsets in the document text (None if unaligned) and its words."""

    span: tuple[int, int] | None
    words: tuple[SynWord, ...]


def load_inventory(path: Path) -> frozenset[str]:
    """A frozen name inventory: one normalised type per line."""
    with open(path, encoding="utf-8") as fh:
        return frozenset(line.rstrip("\r\n") for line in fh if line.strip())


def name_predicate(sentences: Sequence[Mapping], rules: LexicalRules, key: Callable[[str], str],
                   inventory: frozenset[str] | None = None) -> Callable[[Mapping], bool]:
    """Whether a syntactic word of this text is a name, under the configured rule (PENDING P06 and P53).

    "token_upos": the word's own tag is a name tag (em_counts.py). "type_majority_text": route A within the text,
    a type (the lookup key of the form) is a name if at least `name_share` of its occurrences carry a name tag.
    "inventory": the type is in the frozen inventory.
    """
    if rules.name_rule == "token_upos":
        return lambda w: w["upos"] in rules.name_upos
    if rules.name_rule == "inventory":
        if inventory is None:
            raise ValueError("the inventory name rule needs the frozen inventory")
        return lambda w: key(w["form"]) in inventory
    tally: dict[str, list[int]] = {}
    for s in sentences:
        for w in s["words"]:
            t = tally.setdefault(key(w["form"]), [0, 0])
            t[0] += w["upos"] in rules.name_upos
            t[1] += 1
    types = {k for k, (tagged, total) in tally.items() if tagged / total >= rules.name_share}
    return lambda w: key(w["form"]) in types


def build_tokens(sentences: Sequence[Mapping], token_spans: Sequence[Sequence[tuple[int, int] | None]],
                 is_name: Callable[[Mapping], bool], rules: LexicalRules) -> list[Token]:
    """The surface tokens of a parsed text, in order, with their document offsets and decided words.

    `token_spans[k]` holds the offsets of sentence k's surface tokens in the document text (None where a token was
    not found). A content word has a content tag and is not a name, as em_counts.py never counted a name as content.
    """
    out: list[Token] = []
    for sent, spans in zip(sentences, token_spans, strict=True):
        byid = {w["id"]: w for w in sent["words"]}
        for span, ids in zip(spans, sent["token_words"], strict=True):
            words = []
            for i in ids:
                w = byid.get(i)
                if w is None:
                    continue
                name = is_name(w)
                lemma = w.get("lemma", "_")
                words.append(SynWord(form=w["form"], lemma=lemma if lemma not in ("_", "") else w["form"],
                                     upos=w["upos"], deprel=w["deprel"], name=name,
                                     content=w["upos"] in rules.content_upos and not name))
            out.append(Token(span=None if span is None else (span[0], span[1]), words=tuple(words)))
    return out


def classify_words(word_spans: Sequence[tuple[int, int]], tokens: Sequence[Token],
                   word_rule: str) -> list[tuple[bool, bool, bool]]:
    """(contains a content word, is a name, covered by a token) for each word of the outcome's unit.

    A word contains whatever syntactic words its overlapping tokens hold. It is a name when "any" (or "all") of
    those that bear a letter or digit are names (PENDING). Tokens and words are both in text order.
    """
    aligned = [t for t in tokens if t.span is not None]
    out = []
    j = 0
    for ws, we in word_spans:
        while j < len(aligned) and aligned[j].span[1] <= ws:
            j += 1
        k, words = j, []
        while k < len(aligned) and aligned[k].span[0] < we:
            if aligned[k].span[1] > ws:
                words.extend(aligned[k].words)
            k += 1
        bearing = [w.name for w in words if is_wordlike(w.form)]
        name = any(bearing) if word_rule == "any" else (bool(bearing) and all(bearing))
        out.append((any(w.content for w in words), name, bool(words)))
    return out


# ---------------------------------------------------------------- features


def frequency_features(tokens: Sequence[Token], resource, key: Callable[[str], str],
                       rules: LexicalRules) -> tuple[dict[str, float], dict]:
    """Mean Zipf of content tokens, the rare-word share and their registered sensitivity versions.

    A content token that is not a name and is absent from the resource takes the floor in the mean and counts as
    rare (qmd Materials). Under the orthographic-word aggregation a surface token's value is the mean of its content
    words (S3, second script rule), it is matched only when all of them are found and rare when absent or below
    Zipf 4. The matched-only mean and the shares at Zipf 3 and over matched tokens are sensitivity analyses (S3).
    """
    names = ("mean_zipf", "rare_share", "mean_zipf_matched", "rare_share_zipf3", "rare_share_matched")
    if resource is None:
        return dict.fromkeys(names, NAN), {"resource": "unavailable"}
    units: list[list[tuple[float, bool]]] = []
    n_syn = n_found = 0
    for t in tokens:
        vals = [resource.lookup(key(w.form)) for w in t.words if w.content]
        n_syn += len(vals)
        n_found += sum(not absent for _, absent in vals)
        if vals:
            units.extend([vals] if rules.aggregation == "orthographic_word" else [[v] for v in vals])
    zs = [sum(z for z, _ in u) / len(u) for u in units]
    absent_all = [all(a for _, a in u) for u in units]
    matched = [not any(a for _, a in u) for u in units]
    rare = [a or z < rules.rare_zipf for z, a in zip(zs, absent_all, strict=True)]
    rare3 = [a or z < rules.rare_zipf_sensitivity for z, a in zip(zs, absent_all, strict=True)]
    zm = [z for z, m in zip(zs, matched, strict=True) if m]
    n = len(units)
    # qmd, Outcome-blind dimension reduction: "A text's value is defined when at least one of its non-name content
    # tokens is found in the feature's resource." Content words exclude names (build_tokens), so a text none of whose
    # content words is found gets no value, rather than the floor and a rare share of 1.
    defined = n_found > 0
    values = {"mean_zipf": _mean(zs) if defined else NAN, "rare_share": sum(rare) / n if n and defined else NAN,
              "mean_zipf_matched": _mean(zm), "rare_share_zipf3": sum(rare3) / n if n and defined else NAN,
              "rare_share_matched": sum(z < rules.rare_zipf for z in zm) / len(zm) if zm else NAN}
    diag = {"content_tokens": n, "matched_tokens": sum(matched), "rare_tokens": sum(rare),
            "rare_tokens_zipf3": sum(rare3), "content_syntactic_words": n_syn, "found_syntactic_words": n_found,
            "defined": defined}
    return values, diag


def word_length_features(tokens: Sequence[Token], text: str, word_spans: Sequence[tuple[int, int]],
                         classes: Sequence[tuple[bool, bool, bool]], letters: LetterCounter,
                         rules: LexicalRules) -> tuple[dict[str, float], dict]:
    """Mean letters per content word, names excluded, and the mean over all words (S3's sensitivity version), in
    the configured unit."""
    if rules.word_length_unit == "syntactic_word":
        content = [letters(w.form) for t in tokens for w in t.words if w.content]
        every = [letters(w.form) for t in tokens for w in t.words
                 if not w.name and is_wordlike(w.form) and w.deprel.split(":")[0] != "punct"]
    else:
        content = [letters(text[s:e]) for (s, e), (c, nm, _) in zip(word_spans, classes, strict=True)
                   if c and not nm]
        every = [letters(text[s:e]) for (s, e), (_, nm, _) in zip(word_spans, classes, strict=True) if not nm]
    return ({"word_length": _mean(content), "word_length_all_words": _mean(every)},
            {"word_length_words": len(content), "word_length_all_words_n": len(every)})


def density_features(tokens: Sequence[Token], classes: Sequence[tuple[bool, bool, bool]],
                     rules: LexicalRules) -> tuple[dict[str, float], dict]:
    """Lexical density in the configured unit, with the other unit in the diagnostics.

    Word unit (S3): the share of non-name words of the outcome's unit that contain a content syntactic word.
    Syntactic unit (em_counts.py): content words over the non-name, non-punctuation syntactic words bearing a
    letter or digit.
    """
    words = [c for c, nm, _ in classes if not nm]
    word_unit = sum(words) / len(words) if words else NAN
    syn = [w.content for t in tokens for w in t.words
           if is_wordlike(w.form) and not w.name and w.deprel.split(":")[0] != "punct"]
    syn_unit = sum(syn) / len(syn) if syn else NAN
    primary, other = (word_unit, syn_unit) if rules.density_unit == "word" else (syn_unit, word_unit)
    other_name = "lexical_density_syntactic_word" if rules.density_unit == "word" else "lexical_density_word"
    return ({"lexical_density": primary},
            {other_name: other, "density_words": len(words), "density_content_words": sum(words),
             "density_syntactic_words": len(syn), "words_without_token": sum(1 for *_, cov in classes if not cov)})
