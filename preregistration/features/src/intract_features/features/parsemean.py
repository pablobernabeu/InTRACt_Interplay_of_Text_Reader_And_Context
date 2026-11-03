"""The registered parser mean of the grammatical features, with S3's long-unit rule.

qmd Materials: "Each feature but sentence length is the unweighted mean of its values under two parsers, Stanza
and UDPipe 2". Each parser's value is computed on the whole text from that parser's summed sentence counts, and the
two values are averaged text by text, as em_core.py formed PU = (P + Us) / 2 anchor by anchor.

S3: "A unit longer than 100 words takes Stanza's parse in both members of the mean." A unit is a registered
sentence, its length counted in words of the outcome's unit, so a long sentence contributes Stanza's counts to the
UDPipe member and no disagreement to Var_D, as em_counts.py built the member Us. The rule and its constants are
parse.long_units.LongUnitRule, configured once in config/stages/parse_udpipe.toml ([long_units]).

Both members are kept for the diagnostics, because Var_D, the variance of their difference within reading level,
scales the noise of GrammaticalLoad (S3, Measurement error and calibration). UDPipe without the rule is kept too,
so the rule's effect can be read off.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from intract_features.features.grammatical import GrammarRules, parse_diagnostics, parse_features, sum_counts
from intract_features.parse.long_units import LongUnitRule

NAN = float("nan")
KEYS = ("mean_dependency_distance", "clauses_per_sentence", "subordination", "noun_phrase_elaboration")


def parser_mean(a: Mapping[str, float], b: Mapping[str, float]) -> dict[str, float]:
    """Unweighted mean of two members, feature by feature; undefined in either member means undefined."""
    return {k: (a[k] + b[k]) / 2 for k in a}


def grammatical_features(stanza: Sequence[Mapping] | None, udpipe: Sequence[Mapping] | None,
                         words_per_sentence: Sequence[int], rules: GrammarRules,
                         long_rule: LongUnitRule) -> tuple[dict[str, float], dict]:
    """Parser-mean grammatical anchors of one text, and diagnostics holding both members.

    `stanza` and `udpipe` are the per-sentence counts (grammatical.sentence_counts) aligned with the segmentation's
    sentences, or None where that parse is missing; the mean is then undefined, and the members that exist are
    still reported.
    """
    diag: dict = {"long_units": sum(long_rule.mask(words_per_sentence))}
    members: dict[str, dict[str, float]] = {}
    if stanza is not None:
        tot = sum_counts(stanza)
        members["stanza"] = parse_features(tot, rules)
        diag["stanza"] = {**members["stanza"], **parse_diagnostics(tot)}
    if udpipe is not None:
        tot = sum_counts(udpipe)
        diag["udpipe_alone"] = {**parse_features(tot, rules), **parse_diagnostics(tot)}
    if stanza is not None and udpipe is not None:
        tot = sum_counts(long_rule.udpipe_member(stanza, udpipe, words_per_sentence))
        members["udpipe"] = parse_features(tot, rules)
        diag["udpipe"] = {**members["udpipe"], **parse_diagnostics(tot)}
        return parser_mean(members["stanza"], members["udpipe"]), diag
    return dict.fromkeys(KEYS, NAN), diag
