"""Stage encode_bgem3: adjacent-sentence similarity under BGE-M3, the sensitivity encoder.

S3, Table 3: "BGE-M3, peer-reviewed and covering over 100 languages, retained as the sensitivity encoder", with "the
per-language correlation between the two estimates [...] reported with the feature-pipeline validation". BGE-M3's
dense vector is the normalised hidden state of its first token, with no instruction (verify-discourse/scripts/
enc_compare.py; the model card: BGE-M3 "no longer requires adding instructions to the queries").

Reads ``documents`` and ``segments`` and writes ``encode_bgem3``, whose ``values`` hold
``adjacent_similarity_bgem3``; the loop, the inputs and the diagnostics are those of encode_e5.
"""

from __future__ import annotations

from intract_features.cli import Stage, StageContext
from intract_features.stages.encode_e5 import run_encoder

STAGE = Stage(name="encode_bgem3", inputs=("documents", "segments"), outputs=("encode_bgem3",), device="gpu",
              env="core", description="adjacent-sentence similarity, BGE-M3 dense vectors (sensitivity), fp32")


def run(ctx: StageContext) -> dict:
    """Compute the sensitivity similarity of every document of the shard; return the counts for the timing record."""
    return run_encoder(ctx, STAGE)
