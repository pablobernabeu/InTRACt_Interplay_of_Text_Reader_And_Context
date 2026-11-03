# The third parser's frozen rules

Supplementary Section S3 registers a third parser, Stanza retrained with the XLM-RoBERTa-large encoder, which joins the two-parser mean only if rules fixed in advance say so. This folder deposits those rules and the parser's training recipe with their SHA-256 checksums, as S3 states.

- `decision_rules_v3.json` holds version 3 of the decision rules, frozen on 3 November 2026 at 21:51:44 UTC, before any of the parser's gains was computed. The rules themselves hash to `6eac12739a2b9283bb07b5ed792d92cbad0d8f9cead61c584e84fc1f1f27525f`. Their `registered_text` repeats, word for word, the protocol's passage that begins "It joins the mean only in the languages" (Materials). The record also holds the decision it was frozen under, the earlier versions it replaces, the registered treebanks and the checksums of the code that applies it. Its `terms` entry defines the short labels the rules use, such as P, U and X for the three parsers and R1 to R4 for the fallbacks for delay or cost.
- `recipe.json` holds the training recipe, frozen on 23 October 2026, together with version 1 of the rules, which version 3 replaces. Version 1 is kept unchanged, so its checksum can still be verified.
- `SHA256SUMS` lists the checksums of both files (`sha256sum -c SHA256SUMS`).

The code that drafts, freezes, checks and applies the rules runs on the University of Oxford's Advanced Research Computing cluster and is not part of this repository. A change to that code after the freeze is logged with its reason and decides nothing, since the rules are fixed by their checksum.
