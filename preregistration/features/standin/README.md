# The stand-in corpus

The feature pipeline has to be timed on ARC before submission, yet the protocol commits
that "No linguistic feature registered here has been computed on the story texts, and none
will be before in-principle acceptance" (`../../preregistration.qmd`, Data provenance,
sequestration and outcome blindness). The dry run therefore reads a public stand-in:
children's stories from SimpleStories, matched one for one to the texts of the English
catalogue by length and cut into exactly their numbers of pages. Each stand-in text has its
catalogue text's page count and, within a few per cent, its word count, and its page
lengths follow the catalogue's with a somewhat wider spread. Every stage thus meets the
catalogue's volume of text and its page structure. What the stand-in does not match is
listed under Limits below.

The stand-in is not a registered rule. Its design is the English-pipeline scout's of 2-3
November 2026 (section 5 of that report), recommended there for the dry run, and
`../config/stages/standin.toml` holds every constant beside the words of the design it
implements. Where the scout left a detail open, the builder takes a default behind a named
switch, listed under Switches below, until the Feature Specification settles it.

| File | What it does |
|---|---|
| `build_standin.py` | Downloads and verifies the pinned shards, builds the stand-in, checks it and writes its manifest |
| `catalogue_structure.py` | Writes the structure table of the English catalogue, and reads it back for the builder |
| `typography.py` | Gives the ASCII stories the catalogue's typographic punctuation |
| `../tests/unit/test_standin.py` | Tests on synthetic fixtures and the public SimpleStories test split |

## Inputs

**The structure table.** One row per catalogue text: story id, kind (generated or
classic), level, number of pages, whitespace tokens in all and on each page, and
characters. `catalogue_structure.py` writes it from the published English table
(`../../story_texts/data/en-us/stories.csv.xz`). It reads the text column only to divide
each text into pages and count whitespace tokens and characters, and writes identifiers
and numbers only. That is still a computation on the story texts, so running it needs the
PI's go-ahead, recorded in the lab log and in the sequestration disclosure; the dry run
uses the scout's table of 2 November 2026 as it is. The module reproduces the scout's
`length_profile.py`, which wrote that table: on a synthetic table with line-break escapes,
CRLF line ends, empty pages and blank levels, the two give byte-identical output. With
`--with-combination` it adds a column that groups the young, mid and old versions of one
story, so that they share one story key. The builder reads that column as optional and
otherwise gives each text its own key. The builder refuses any table that has a `text`
column.

**SimpleStories** (Finke et al., 2025, arXiv:2504.09184), the train split of the Hugging
Face dataset `SimpleStories/SimpleStories` at revision
`e63b8adc3b1a1bdc7cac5b500d150b71346b0628`: 2,115,696 English stories written by language
models in 2024, ASCII only, in seven parquet shards. Each shard is pinned by size and
SHA-256, taken from the Hugging Face tree API for that revision on 3 November 2026; the
resolve URL's headers gave the same values for the first shard:

| Shard | Bytes | SHA-256 |
|---|---|---|
| `data/train-00000-of-00007.parquet` | 238,015,938 | `ca33531b99f3bebb4125e82f56017c223a4900331b55bcf7cde1b0f750d88fd4` |
| `data/train-00001-of-00007.parquet` | 238,000,197 | `eac50d3053e1b68345061edbe5aebd90062b5ff4a77d7002ca4c5580360c7664` |
| `data/train-00002-of-00007.parquet` | 237,741,821 | `71ada93c7f128743c4a94de81f55cc48319bde0636aeb35889aded5d52841427` |
| `data/train-00003-of-00007.parquet` | 237,658,974 | `cb299fafbef9cb030eebdac229494b313757db746f238084b23131e39b77d71e` |
| `data/train-00004-of-00007.parquet` | 238,085,905 | `6370179dae77b578e69f0e0882171b6e1586e84fe8e74ce71d8ab3e4246f96e1` |
| `data/train-00005-of-00007.parquet` | 237,848,790 | `2ca55fb42b239ce8e649f297b11895bc6611af8e5017eb7c46e0ccc05e2a8220` |
| `data/train-00006-of-00007.parquet` | 237,678,067 | `fe8aa328bfbcbf05f6953c6e9086635a840fe703bf36709a3a4d17806de89998` |

The test split (`data/test-00000-of-00001.parquet`, 16,838,557 bytes, SHA-256
`24a513732fd6c1158e33a6130e3977749ae13d583948e5a2198ed53235e29bec`) is pinned too, for the
tests. Every shard is verified by size and SHA-256 before anything reads it.

## How a stand-in text is made

1. **Candidates.** Each story's lines are stripped and empty lines dropped, n is its
   number of whitespace tokens (`str.split()`, the count of the catalogue's `words`
   column), and stories with n < 50 are dropped. Each candidate is keyed by
   k = SHA-256("intract-standin|v1|cand|" + generation_id).
2. **Targets.** Each catalogue text is keyed by
   K = SHA-256("intract-standin|v1|target|" + story id + "|" + level), an empty level
   entering as the empty string, and T is its number of whitespace tokens. Targets are
   processed in ascending K.
3. **Selection.** The target takes the unused candidate with |n - T| <= 0.03 T and the
   smallest |n - T|, ties going to the smallest k. If none qualifies, m = ceil(T/500)
   pieces are joined. Each piece but the last aims at T/m and the last at what remains of
   T, and each is chosen by the same rule, with the tolerance taken on its own aim, or
   failing that by the nearest unused n. With m = 1 (T <= 500) that is simply the nearest
   unused story. Pieces are concatenated in ascending k, and m is recorded.
4. **Paging.** Page j ends after token round(N (t_1 + ... + t_j) / T), N being the
   stand-in's tokens and t_j the catalogue page's. Each cut snaps to the nearest token
   within 6 that ends in . ! ? or the ellipsis character, closing quotation marks and
   brackets skipped, keeping cuts increasing and pages non-empty, ties going to the earlier
   token. Cuts are taken on the ASCII tokens, so the typography switch never moves one.
   Tokens within a page are joined by single spaces.
5. **Output.** One row per target in the published schema (`STORY_COLS` of
   `../../story_texts/extract_story_texts.py`), in the published tables' CSV dialect and xz
   preset, in ascending K: `id` is "SI" + the rank of K; `age` is the level; `lang` is
   `en-us`; `pages` and `words` are the stand-in's own counts; `text` is the title line
   followed by one line per page, which `split_lines()` reads back exactly as it reads a
   catalogue text. The title is the topic of the first piece in the text. The versions of
   one story share a story key, "SK" + the story's number in order of first appearance
   among the targets in ascending K (SK1, SK2, ...):
   a generated row carries it as `hero` and in `folder` (`SK12-mid`), and a classic row
   has `hero` "Public domain" and `folder` `PD_SK12 old`, as the catalogue names a
   classic's folder. `world`, `theme`, `prompt`, `sidekick` and `build_error` are empty.
6. **Sizes.** The full build covers every target, 40,559 for English. The smoke set is
   the smallest 1 per cent of K, 406 targets. Because candidates are consumed strictly in
   ascending K, each smoke row is identical to the same row of the full build, and the
   full build's manifest records the hash of its first 406 rows so that the two run
   records can be compared.
7. **Acceptance.** Pages per text must be identical (by construction). In each group
   (young, mid and old generated texts, all classics, everything), the quantiles 1, 5, 25,
   50, 75, 95 and 99 of tokens per text must lie within 3 per cent of the catalogue's and
   those of tokens per page within 10 per cent. The manifest reports every quantile, the
   minimum and maximum, and the share of joins.
8. **Projection.** The manifest gives, per group, the ratio of the catalogue's characters
   to the stand-in's, pages joined with one space. It scales the stages whose cost follows
   characters or subword tokens (SaT, the language models, e5, CorPipe, MetricX). On the
   first 2,000 targets matched against the test split it came to 1.044 (young), 1.073
   (mid) and 1.092 (old), close to the scout's estimates of 1.045, 1.072 and 1.088.
9. **Manifest.** `standin_manifest.json` records the builder's version and file hashes,
   every setting, each shard's pin and verification, the counts of rows read and dropped,
   the selection, the acceptance checks, the projection, the typography replacements, the
   output hashes and the timings. `rows_sha256` hashes the table's data rows as written, the
   decompressed CSV without its header, so a smoke build and the first rows of a full build
   compare equal whatever xz version compressed them. The builder and its manifest are
   deposited and the table
   is rebuilt from the pins. If the table itself is ever deposited, it must keep the MIT
   notice (see Licence).

## Typography

SimpleStories is ASCII only. Which quotation marks the catalogue uses is not known and
cannot be counted before acceptance without the PI's authorisation (UNVERIFIED). The only
evidence points the other way: of the eleven English texts edited between the October
deliveries, seven were edited "to straighten typographic quotation marks"
(`../../README.md`), so at least those now hold straight marks. A stand-in left in ASCII
would never exercise the dialogue detector's curly quotation marks, the clash between the
right single quotation mark and the apostrophe, the ellipsis among the terminal marks, or
the em dash that the surprisal stage replaces in some tokenisers, while a stand-in made
typographic never exercises S3's rule that reads the direction of a straight mark from its
spacing. `typography.py` turns straight quotation marks into curly ones, apostrophes into
U+2019, three full stops into the ellipsis character and spaced hyphens and hyphen runs
into em dashes. It works one whitespace token at a time and never adds, removes or moves a
space, so every token count the matching uses is unchanged, and it is idempotent. Its
docstring states each rule. The switch is on by default, `--typography off` builds the
other variant, and the manifest counts every replacement.

## Switches

| Switch (`standin.toml`) | Default | Status |
|---|---|---|
| `typography.enabled` and its four rules | on | The critique's item 8 asked for it |
| `paging.line_breaks` | `space` | The scout's rule. `escape` keeps a paragraph break inside a page as the delivery's two-character escape, to exercise in-page line breaks (gap G9; critique item 21). Pending the Feature Specification |
| `paging.rounding` | `half_up` | Not in the scout's design: which way a half rounds. Pending |
| `candidates.duplicate_ids` | `keep_first` | Not in the scout's design, which found generation_id unique in the test split only. Pending |
| `candidates.drop_backslash` | `true` | Not in the scout's design: the delivery format reserves the backslash for its line-break escape. The test split holds none. Pending |
| `output.trailing_newline` | `false` | Not in the scout's design; `split_lines()` reads either form. Pending |
| `acceptance.quantiles` | 1, 5, 25, 50, 75, 95, 99 | Not in the scout's design, which names no quantiles. Pending, see the next section |
| `acceptance.enforce` | `false` | Not in the scout's design: whether a failed check sets exit status 3, which stops an afterok chain on ARC. With `false` the failure is printed and recorded in the manifest and the build exits 0. Pending the PI, see the next section |

`--typography on|off` and `--line-breaks space|escape` override the file for one build.

## What the acceptance check shows

On the first 2,000 targets of the structure table, matched against the test split,
tokens per text met the 3 per cent check in every group, but tokens per page did not meet
the 10 per cent check at the lower quantiles. Snapping a cut by up to six tokens to reach a
sentence end widens the spread of page lengths. In the young, mid and old groups the 1st
percentile fell 29 to 33 per cent below the catalogue's and the 5th 18 to 21 per cent (13
per cent over all groups together), while the 25th to 99th stayed within 9 per cent, the
young 95th excepted at 11 per cent. A window of 3 halved the shortfall (14 to 17 and 6 to 7
per cent), and no snapping removed it but broke pages inside sentences. The build writes
every output when a check fails, prints the failure and records it in the manifest. With
`acceptance.enforce = false`, the default, it then exits 0, so the ARC chain goes on and the
PI can judge the recorded quantiles; with `true` it exits 3, which stops an afterok chain.
Which of the three to accept, the wider spread, a check on the 25th to 75th percentiles only
or a narrower window, is a decision for the PI and the Feature Specification. Page lengths
matter less for the dry run's costs than total length, which every check passes.

## Limits

The stand-in matches the catalogue's texts, pages and whitespace tokens. It does not match:

- **Sentence length.** The public test split has about 9.1 whitespace tokens per
  sentence-final token, and the catalogue's figure is not known before acceptance. Stages
  whose cost follows sentences (e5 and BGE-M3, the parsers' batch shapes) are therefore
  timed on the stand-in's sentence counts, which the manifest does not yet record.
- **Very long units.** Critique item 9's loops of thousands of words on one page never
  occur, so S3's long-unit rule (more than 100 words) and the parsers' memory bounds are
  not exercised at the catalogue's worst case.
- **Quotation style.** See Typography above.
- **Normalisation.** The typographic marks the builder writes are stable under NFC and lie
  outside the deleted format characters, so the documents stage's normalisation changes
  nothing on the stand-in.
- **Scene breaks.** SimpleStories' `---` lines survive as tokens and become em dashes under
  typography. In a 2,000-target trial 10 of 36,133 pages started with one, which the
  dialogue detector's dash-turn rule reads as a turn to the end of the line.

## Licence

The dataset card at the pinned revision declares the MIT licence. Neither the dataset
repository nor the generation repository (`github.com/simple-stories/simple_stories_generate`)
holds a licence file, so no copyright holder is named anywhere (checked on 3 November
2026). The builder writes `NOTICE-SimpleStories.txt` beside every table it builds: the
MIT permission notice, with the copyright line given to the SimpleStories authors as the
card cites them, and a statement of what the builder changed. That notice must travel with
the table if the table is ever deposited or shared. The builder itself is code of this
repository, under its MIT licence.

## How to rebuild

Python 3.12 or later and pyarrow (tested with 26.0.0); the standard library does the rest.
The stand-in sits beside the installed package, so it runs as a module from the features
directory:

```bash
cd preregistration/features
# The structure table: a structural count of the published English table. Only with the PI's
# recorded go-ahead (see Inputs); the dry run uses the scout's table of 2 November 2026.
python -m standin.catalogue_structure ../story_texts/data/en-us/stories.csv.xz WORK/structure.tsv \
    --with-combination --authorisation "<lab-log entry of the PI's go-ahead>"
# The pinned shards, about 1.7 GB, each verified before it is kept.
python -m standin.build_standin download --dest WORK/simplestories
# The smoke set, then the full English scale.
python -m standin.build_standin build --structure WORK/structure.tsv --shards WORK/simplestories --out WORK/standin_smoke --smoke
python -m standin.build_standin build --structure WORK/structure.tsv --shards WORK/simplestories --out WORK/standin_full
```

Each build writes `en-us/stories.csv.xz`, `selection.tsv` (each target's pieces, lengths
and tolerance), `NOTICE-SimpleStories.txt` and `standin_manifest.json` into its output
folder, every file under a temporary name renamed once complete. The exit status is 0 when
the build succeeds, 3 when the outputs are written but an acceptance check fails and
`acceptance.enforce` is true, and 1 when the build stops (a missing or altered shard, a
malformed structure table).

The build reads the shards twice, once for every story's length and key and once for the
chosen stories, and holds about 80 bytes per candidate in between (a 38-byte entry and
Python's overhead). On the test split the first pass ran at about 11,000 stories a second
on one core of a laptop, which puts the train split at a few minutes a pass and under half
a gigabyte. Both figures are extrapolations, and the train split has not been read here.

Whether the structure table is deposited beside the builder is for the PI to decide.
`../DESIGN.md` keeps outputs on real data out of the repository. `selection.tsv` and the
manifest's acceptance and projection sections also hold catalogue structure (story ids,
page counts, token quantiles, character totals), so they follow the same decision.

## Tests

`../tests/unit/test_standin.py` covers the pins and their verification, the keys, the
tolerance (inclusive and exact), ties, joins, the nearest-length fallback, paging with its
snapping, ties and rounding, the published schema, the shared story keys, byte-identical
rebuilds, the typography rules and their invariants, and the structure table. The smoke
property is tested twice: on synthetic candidates, and on the public test split with a
synthetic structure table. The second test reads the pinned test split from the folder
`INTRACT_SIMPLESTORIES_DIR` names, and skips when pyarrow, the variable or the file is
absent.
