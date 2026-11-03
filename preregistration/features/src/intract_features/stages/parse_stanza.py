"""Stage parse_stanza: Stanza 1.15.0 in its nocharlm tier on every registered sentence of every text.

Reads `documents` and `segments` and writes `parses_stanza` (CoNLL-U, sentence k of a text = sentence k of its
segmentation; format in intract_features.parse). Supplementary S3: "Stanza 1.15.0 in its `nocharlm` tier ... Both
run on every sentence of every text, each with the registered treebank for the language and its own tokeniser."
Constants are in config/stages/parse_stanza.toml, which is also the one home of the input rules both parsers share
([input], [segments], offset_max_skip). The wrapper (parse/stanza_wrap.py) verifies every model file before it
builds the pipeline. The run record holds the verified files, the parser batch Stanza actually used, the pre-flight
estimate of the largest padded batch and the largest batch met, which bound the parser's memory.
"""

from __future__ import annotations

import json
import sys

from intract_features import config as config_mod
from intract_features.cli import Stage, StageContext
from intract_features.parse import ParseCounts, SegmentRules, call_groups, join_units, parse_shard
from intract_features.parse.stanza_wrap import StanzaParser

STAGE = Stage(name="parse_stanza", inputs=("documents", "segments"), outputs=("parses_stanza",), device="cpu",
              env="core", description="Stanza 1.15.0 nocharlm parse of the registered sentences (S3)")


def run(ctx: StageContext) -> dict:
    """Parse one shard of one language and return the counts and the parser record for the timing record."""
    scfg = ctx.stage_config()
    lcfg = config_mod.language(ctx.config, ctx.lang)
    per_call = int(scfg["calls"]["sentences_per_call"])
    # The inputs are paired and checked before the models load, so a bad shard fails in seconds.
    items = list(join_units(ctx.documents(), ctx.read("segments"), lang=ctx.lang,
                            field_name=scfg["input"]["segments_field"],
                            rules=SegmentRules.from_config(scfg["segments"]),
                            allow_uncovered_text=bool(scfg["input"]["allow_uncovered_text"]),
                            line_breaks=scfg["input"]["line_breaks"]))
    parser = StanzaParser.from_config(ctx.config, ctx.lang, stage=STAGE.name,
                                      model_dir=ctx.extra.get("stanza_model_dir"))
    calls = ([u.text for _, units in group for u in units if u.text] for group in call_groups(items, per_call))
    preflight = parser.preflight(calls, spaced=bool(lcfg["spaced"]))
    # Printed before parsing: a job killed for memory on one long unit leaves the estimate in its log.
    print("parse_stanza: preflight " + json.dumps(preflight, sort_keys=True), file=sys.stderr, flush=True)
    limit = float(scfg["max_lemma_missing_share"])

    def lemma_check(_: ParseCounts) -> str | None:
        share = parser.lemma_missing_share()
        return f"{share:.4%} of syntactic words have no lemma (limit {limit:.2%})" if share > limit else None

    counts, _ = parse_shard(ctx.path("parses_stanza", ext="conllu.gz"), items, parser.parse,
                            max_skip=int(scfg["offset_max_skip"]), check=lemma_check, sentences_per_call=per_call)
    return {**counts.as_dict(), "parser": parser.info, "stanza": {**parser.stats(), "preflight": preflight},
            "sentences_per_call": per_call}
