"""Serbian Cyrillic to Latin, faithful to CLDR 47's Serbian-Latin-BGN transform, with a character-offset map back to
the served text and a round-trip collision count. Pure Python, no dependency.

Source of the rules: unicode-org/cldr, tag release-47 (annotated tag adbaf76b, commit
2ef784e3a4168bc2a43cd1b5b9839b6636f5899c), common/transforms/Serbian-Latin-BGN.xml, SHA-256 b415bc12451ffd7e
9a3c04b724613d1623a765100b7837876aa5ec55f0720762, transform alias "Serbian-Latin/BGN sr-Latn-t-sr-m0-bgn". The file
is kept as config/cldr/cldr47_Serbian-Latin-BGN.xml, and tests/unit/test_sr_translit.py checks the table below
against it.

Why a transliteration at all: UD_Serbian-SET and both parsers' Serbian models (Stanza set_nocharlm, UDPipe 2.17
serbian-set) are in Latin script, while the delivered Serbian is Cyrillic. On 3 November 2026 the route was registered
(supplementary.qmd S3, the fifth script rule; P82 settled): the parse, the frequency lookups and connective
induction read the transliteration, and each token is mapped back to the served text by character offsets. Ported
unchanged from the translated benchmark (presub translated_union/scripts/sr_translit.py), where it parsed 39,689
machine-translated sentences; the stages read it once the sr-rs locale is added to languages.toml (ISSUES.md FP-11).

What the rules do, in order:
  1. A global filter: only the 60 letters of the Serbian Cyrillic alphabet are touched; every other character,
     Latin letters, punctuation, digits, combining marks and Cyrillic letters outside Serbian, passes unchanged.
  2. NFD on the filtered letters. None of the 60 has a canonical decomposition (the test checks this), so the step
     changes nothing.
  3. One rule per letter. Lj, Nj and Dž are written for Љ, Њ and Џ before a lowercase Serbian letter ($lower, the
     rule's post-context, which is read on the untransformed text) and LJ, NJ and DŽ otherwise.
CLDR's file writes Ć and ć decomposed (C or c plus U+0301) while Č, Š and Ž are precomposed, and the transform ends
without an NFC step. cldr_raw() returns that rule output unchanged; transliterate() then applies NFC, the strand's
normalisation of every text (tu_common.normalise), so ć is U+0107 as in UD_Serbian-SET.

Offset map: transliterate() returns, for every output character, the half-open span of served characters it comes
from, so a token found in the Latin text maps back to the exact served substring (Љ gives two Latin characters, both
mapped to the one Cyrillic letter).

Round trip: the transform is deterministic but not one-to-one. нј and њ both give nj, лј and љ both give lj, дж and
џ both give dž, and Latin letters already in the served text pass unchanged. roundtrip() counts these collisions
with the obvious inverse (to_cyrillic), which exists only for that count.
"""
import unicodedata

CLDR = {"repo": "unicode-org/cldr", "tag": "release-47", "commit": "2ef784e3a4168bc2a43cd1b5b9839b6636f5899c",
        "file": "common/transforms/Serbian-Latin-BGN.xml",
        "sha256": "b415bc12451ffd7e9a3c04b724613d1623a765100b7837876aa5ec55f0720762",
        "alias": "Serbian-Latin/BGN sr-Latn-t-sr-m0-bgn"}
NAME = "sr-Latn-BGN (CLDR 47) + NFC"

# The rule table exactly as the CLDR file writes it: Ć and ć decomposed, as there (chr, so the source holds no
# invisible combining character)
ACUTE = chr(0x301)
RULES = {
    "А": "A", "а": "a", "Б": "B", "б": "b", "В": "V", "в": "v", "Г": "G", "г": "g", "Д": "D", "д": "d",
    "Ђ": "Đ", "ђ": "đ", "Е": "E", "е": "e", "Ж": "Ž", "ж": "ž", "З": "Z", "з": "z", "И": "I", "и": "i",
    "Ј": "J", "ј": "j", "К": "K", "к": "k", "Л": "L", "л": "l", "Љ": "LJ", "љ": "lj", "М": "M", "м": "m",
    "Н": "N", "н": "n", "Њ": "NJ", "њ": "nj", "О": "O", "о": "o", "П": "P", "п": "p", "Р": "R", "р": "r",
    "С": "S", "с": "s", "Т": "T", "т": "t", "Ћ": "C" + ACUTE, "ћ": "c" + ACUTE, "У": "U", "у": "u", "Ф": "F",
    "ф": "f", "Х": "H", "х": "h", "Ц": "C", "ц": "c", "Ч": "Č", "ч": "č", "Џ": "DŽ", "џ": "dž", "Ш": "Š",
    "ш": "š",
}
# Post-context rules (Љ} $lower → Lj ; and so on), tried before the plain rule as in the file
BEFORE_LOWER = {"Љ": "Lj", "Њ": "Nj", "Џ": "Dž"}
FILTER = frozenset("АБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШабвгдђежзијклљмнњопрстћуфхцчџш")
LOWER = frozenset("бвгдђжзјклљмнњпрстћфхцчџш" + "аеиоу")   # $lower = [$lowerConsonants $lowerVowels]


def cldr_raw(text):
    """The CLDR rule output, character for character, with the served index of each output character."""
    out, src = [], []
    for i, ch in enumerate(text):
        if ch not in FILTER:
            out.append(ch)
            src.append(i)
            continue
        nxt = text[i + 1] if i + 1 < len(text) else ""
        piece = BEFORE_LOWER[ch] if ch in BEFORE_LOWER and nxt in LOWER else RULES[ch]
        out.extend(piece)
        src.extend([i] * len(piece))
    return "".join(out), src


class Translit:
    """text: the Latin text (NFC); starts, ends: per output character, the served span [start, end)."""
    __slots__ = ("text", "starts", "ends")

    def __init__(self, text, starts, ends):
        self.text, self.starts, self.ends = text, starts, ends

    def served_span(self, a, b):
        """Served span of the Latin span [a, b), b > a."""
        return self.starts[a], self.ends[b - 1]


def _clusters(raw, src):
    """Split the raw output into a starter and the non-starters (combining marks) that follow it: NFC composes only
    within such a cluster in Latin and Cyrillic text, so each cluster can be normalised on its own."""
    cl = []
    for ch, s in zip(raw, src, strict=True):
        if cl and unicodedata.combining(ch):
            cl[-1][0].append(ch)
            cl[-1][1].append(s)
        else:
            cl.append(([ch], [s]))
    return cl


def transliterate(text):
    """Latin text (CLDR rules, then NFC) and its offset map. Raises if the cluster-wise NFC ever differed from NFC of
    the whole text, which would make the map wrong (it cannot happen in Latin or Cyrillic text)."""
    raw, src = cldr_raw(text)
    out, starts, ends = [], [], []
    for chars, srcs in _clusters(raw, src):
        piece = unicodedata.normalize("NFC", "".join(chars))
        a, b = min(srcs), max(srcs) + 1
        out.append(piece)
        starts.extend([a] * len(piece))
        ends.extend([b] * len(piece))
    lat = "".join(out)
    if lat != unicodedata.normalize("NFC", raw):
        raise ValueError("cluster-wise NFC differs from NFC of the whole text")
    return Translit(lat, starts, ends)


def token_spans(text, tokens):
    """Locate each token in text in order (whitespace skipped). Returns [(start, end) or None], so a token the parser
    altered is reported, not guessed."""
    spans, pos = [], 0
    for t in tokens:
        k = text.find(t, pos) if t else -1
        if k < 0 or text[pos:k].strip():
            spans.append(None)
            continue
        spans.append((k, k + len(t)))
        pos = k + len(t)
    return spans


def served_forms(served, tl, tokens):
    """For tokens of the Latin text tl.text: the served substring of each (None where the token was not found), and
    how many were found and how many transliterate back to exactly the Latin token."""
    forms, found, exact = [], 0, 0
    for t, sp in zip(tokens, token_spans(tl.text, tokens), strict=True):
        if sp is None:
            forms.append(None)
            continue
        a, b = tl.served_span(*sp)
        f = served[a:b]
        forms.append(f)
        found += 1
        exact += transliterate(f).text == t
    return forms, found, exact


# ---- the inverse, only for the round-trip count ----
# single letters from the table (NFC, so ć is one character); the six two-letter outputs are the digraphs below
_INV1 = {unicodedata.normalize("NFC", lat): cyr for cyr, lat in RULES.items()
         if len(unicodedata.normalize("NFC", lat)) == 1}
_INV2 = {"LJ": "Љ", "Lj": "Љ", "lj": "љ", "NJ": "Њ", "Nj": "Њ", "nj": "њ", "DŽ": "Џ", "Dž": "Џ", "dž": "џ"}


def to_cyrillic(lat):
    """Serbian Latin to Cyrillic, digraphs first. Characters outside the Serbian Latin alphabet pass unchanged."""
    out, i = [], 0
    while i < len(lat):
        two = lat[i:i + 2]
        if two in _INV2:
            out.append(_INV2[two])
            i += 2
            continue
        out.append(_INV1.get(lat[i], lat[i]))
        i += 1
    return "".join(out)


def _is_latin_letter(ch):
    return ch.isalpha() and unicodedata.name(ch, "").startswith("LATIN")


def _is_cyrillic_letter(ch):
    return ch.isalpha() and unicodedata.name(ch, "").startswith("CYRILLIC")


DIGRAPHS = ("лј", "нј", "дж")


def roundtrip(texts):
    """Round-trip collisions over served texts: tokens (whitespace) whose to_cyrillic(transliterate(token)) differs
    from the token, by cause, with token and type counts and a few examples per cause."""
    n_tok = n_diff = n_sent = n_sent_diff = 0
    cause = {"cyrillic_digraph_lj_nj_dz": {}, "latin_letters_in_served": {}, "other": {}}
    non_serbian_cyr = {}
    for text in texts:
        n_sent += 1
        sent_diff = False
        for tok in text.split():
            n_tok += 1
            if any(_is_cyrillic_letter(ch) and ch not in FILTER for ch in tok):
                non_serbian_cyr[tok] = non_serbian_cyr.get(tok, 0) + 1
            back = to_cyrillic(transliterate(tok).text)
            if back == tok:
                continue
            n_diff += 1
            sent_diff = True
            low = tok.lower()
            if any(d in low for d in DIGRAPHS):
                key = "cyrillic_digraph_lj_nj_dz"
            elif any(_is_latin_letter(ch) for ch in tok):
                key = "latin_letters_in_served"
            else:
                key = "other"
            cause[key][tok] = cause[key].get(tok, 0) + 1
        n_sent_diff += sent_diff

    def summ(d):
        top = sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        return {"tokens": sum(d.values()), "types": len(d), "examples": [k for k, _ in top]}
    return {"transform": NAME, "cldr": CLDR, "sentences": n_sent, "sentences_changed_by_round_trip": n_sent_diff,
            "tokens": n_tok, "tokens_changed_by_round_trip": n_diff,
            "share_tokens_changed": round(n_diff / n_tok, 6) if n_tok else None,
            "by_cause": {k: summ(v) for k, v in cause.items()},
            "tokens_with_non_serbian_cyrillic_left_in_cyrillic": summ(non_serbian_cyr)}
