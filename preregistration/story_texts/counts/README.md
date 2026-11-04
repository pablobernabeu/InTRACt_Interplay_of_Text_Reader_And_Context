# Counts made on the story texts before acceptance

The scripts behind the counts that Supplementary Section S7 ("Counts made on the story texts before acceptance") records, deposited on 4 November 2026 so that reviewers can see how each figure was made. None reads an outcome, computes a registered feature or runs a dimension reduction. Their outputs are numbers and story identifiers only. The extraction script, which also made the structural counts of 26 October, is `../extract_story_texts.py`.

| Script | Run | What it counted | Reported |
|---|---|---|---|
| `corpus_aggregates.py` | 20 October 2026 | Words, characters, pages and sentence-end marks of the English texts of the first delivery; corpus totals and percentiles only | S7, planning paragraph (7.1 words per sentence-end mark, 413-word median) |
| `repetition_scan.py` | 26 October 2026 | Each text's zlib compression ratio against its language's median; the texts below half of it | S7, and the loop check of the anomaly battery (S3) |
| `endings_en.py` | 28 October 2026 | How each English page ends: closing punctuation, a cut-off page marker or mid-sentence | S7 (214 stories; 107 inner pages in 105 stories) |
| `length_profile.py` | 2 November 2026 | Pages per English text and whitespace tokens and characters per page; writes `en_length_profile.json` (here) and a per-text table kept outside the repository | S7 |
| `pages_table.py` | 2 November 2026 | Pages per text by story type and reading level, from that per-text table | S7 |
| `story_sizes.py` | 3 November 2026 | Texts, pages and whitespace tokens per language, summed from the published tables' columns | S7 (sizing for Bulgarian, Hungarian, Kazakh and Serbian) |
| `versions_check.py` | 3 November 2026 | Attribute combinations of the English table and reading levels per combination, from the metadata columns only | S7 |
| `match_sim.py` | 3 November 2026 | Whether single public SimpleStories stories can match the catalogue's text lengths within 3 per cent, from the per-text counts | S7 (the stand-in's design) |
| `portuguese_variety.py` | 4 November 2026 | Markers that separate European from Brazilian Portuguese (the progressive, accents before m or n, hyphenated enclitics, vocabulary pairs) in the delivered Portuguese texts, at the PI's request | S7, and the choice of Portuguese treebank (S3) |

Two scripts were made portable for this deposit and are otherwise as they ran: `endings_en.py` and `repetition_scan.py` took absolute paths on the analysing machine, and `repetition_scan.py` read the delivery's extracted tables, which are byte-identical to the published `../data/<locale>/stories.csv.xz` (SHA-256 of all 21 compared on 4 November 2026). `story_sizes.py` gained a docstring.

Run them from this folder with Python 3.12 and the standard library (`match_sim.py` also needs pyarrow and the SimpleStories test split), for example `python -I -X utf8 story_sizes.py ../data en-us,bg-bg`.
