# Feature Specification

First draft, 3 November 2026, revised the same day after review. It covers the English path and is not frozen.

This specification maps each registered feature, covariate and diagnostic of the English path to the code that
computes it. The rules are registered in the protocol (`../preregistration.qmd`) and its supplement
(`../supplementary.qmd`, Section S3 above all), and each row quotes the passage that registers its quantity. Where
the protocol leaves a choice open, the row names the default the code takes, and sections 3 and 4.1 list each open
choice with the switch that holds its default, so that it can be decided and recorded here. Section 4.2 lists the
places where what the code writes departs from the registered text, which no default can settle. The draft becomes
the frozen specification when the inventory is frozen under the fourth rule, qmd § Materials: "Fourth, the full
inventory, the software versions, the model checkpoints, the tokenisation rules and the matched-token proportions
will be frozen and published before any feature is linked to outcome data."

Before in-principle acceptance the pipeline runs only on public data, the stand-in in `standin/` and FLORES-200
(`DESIGN.md`). `DESIGN.md` fixes the contracts every stage follows; this file says what each stage computes.

## 1. How to read the tables

**Row ids** name the family: TXT text layer and units, SEG segmentation, PRS parses, GRM grammatical, LEX lexical,
DSC discourse, COV covariates and masks, REF English outputs that the translations read, CHK checks run after
acceptance. Ids are stable; a new row takes the next free number.

**Roles.** A row may have several.

- *anchor*: a feature that identifies a confirmatory component (Outcome-blind dimension reduction).
- *component*: a feature that enters a family's component solution without being an anchor.
- *covariate*: an adjustment in the confirmatory models.
- *sensitivity*: a registered alternative or variant used by a sensitivity analysis or a reported correlation.
- *diagnostic*: reported, or a gate that decides inclusion, and never a predictor.
- *mask*: decides which tokens, units or texts another quantity uses.
- *input*: a registered unit every feature is computed from (normalised pages, words, sentences, parses).
- *reference for translations*: an English output that a translation's value, gate or mask reads.

**Anchors** are written `qmd § <section>: "<quote>"`, where `qmd` is `preregistration.qmd` and `supp` is
`supplementary.qmd`. A section is named by its deepest heading, with ` / ` between nested headings. Every quote is
verbatim, and `tests/unit/test_spec_anchors.py` checks that it occurs in the named section's own text, outside its
subsections, after whitespace is collapsed, HTML comments are removed and Markdown emphasis and code markers (`*`,
`_`, backticks) are dropped. Quotes are taken from passages that are identical in the committed protocol and in the
working copy of 3 November 2026, which holds uncommitted edits elsewhere; the test checks the working copy and, where
git is available, the committed text (`git show HEAD`).

**Module and function** paths are relative to `src/intract_features/`. A reference written as
`<module>.py:<function>` (or `<module>.py:<Class>.<member>`) in backticks names code that exists, and the test
checks that it does, wherever in this file the reference appears. "planned:" names a module that is not yet
written, with the benchmark code it should promote.

**Stage** names the modules of `src/intract_features/stages/` that write the row's per-text values, even where only
some of them are written yet (the status says which), or "none" where no stage of the fixed list writes any. A
catalogue-level aggregate, such as a per-language share or correlation, has the stage "none" and names its per-text
inputs; section 6 lists what has no stage.

**Pins** name models and code by repository and the first 12 characters of the commit. `config/models.lock.json`
and `config/resources.lock.json`, which the ARC builder owns, hold the full revisions and file checksums, and the
code verifies a pin before it loads the file. The test checks every `repository@commit` written here against
`config/models.lock.json`, and every other commit prefix or SHA-256 written here against the files of `config/`. A
file whose checksum the lock still holds as null, pending a conversion on ARC, is said to be pending.

**Settings** are written `stages/<stage>.toml [table] key = value`, relative to `config/` (a top-level key has no
table), and the test checks that the key exists and holds that value. Every code span that looks like a setting
must be written in this form, so that none escapes the check.

**Status** is one of:

- `implemented`: the named stage writes the quantity as registered, the named function computes it, unit tests
  cover it and no open choice acts on it;
- `default pending <ids>`: as above, but the value rests on a default behind a switch: a choice the protocol leaves
  open (a gap, G1a to G9, section 3, or an open choice FS-nn, section 4.1), or a stand-in for a resource that a
  pending benchmark (Pnn, `../pending_benchmarks.md`) will deliver;
- `conflict <ids>`: the stage writes a value under the registered quantity's name, but the value departs from the
  quoted anchor. The ids name each departure (a conflict CF-nn, section 4.2, or a gap whose default departs from the
  registered text), which only the PI can settle;
- `not yet built`: no tested stage writes the quantity as registered. No stage writes it, or a stage writes only
  part of it, or the code that would is written but untested; a library function named in the module column may
  exist. The ids in brackets name what it waits for and the open choices that the code already written takes.

A status names the open choices that act on the row's own computation. A choice that acts on an input row (TXT-01
to TXT-04, SEG-01, PRS-01, PRS-02) reaches every row computed from it and is not repeated there. G1b, for example,
acts on the pages and so on every feature, and it is named only on the rows whose registered wording it touches
(TXT-01, TXT-05, TXT-09, TXT-13).

Statuses describe the package at 05:30 on 3 November 2026, while the builders were still at work, and the unit tests
that need torch, NumPy, wordfreq, lexical_diversity, OpenCC or pyarrow were skipped in the shared development
environment. The test catches a renamed function, a changed default, a moved pin or a quote that no longer matches,
but a status has to be revised by hand.

## 2. Registered quantities of the English path

### 2.1 Text layer and units

| id | quantity | role | anchor | module and function | stage | pins | status |
|---|---|---|---|---|---|---|---|
| TXT-01 | Pages of a text, joined by one space into the string every offset refers to | input | qmd § Materials: "Pages are joined with a single space."<br>qmd § Materials: "Every feature value is computed on the text as served." | `io/catalogue.py:split_lines`<br>`records.py:Document.text`<br>`records.py:Document.page_spans`<br>`text/titles.py:exclude_page_titles` | documents | the delivery format of `story_texts/extract_story_texts.py`, whose definitions `tests/unit/test_io.py` reads from its source | default pending G1a, G1b |
| TXT-02 | Registered normalisation: NFC, then invisible format characters removed, once at load time | input | supp § S3: "Before any stage runs, each text is normalised once to Unicode normalisation form NFC and stripped of invisible format characters, and its pages are joined with one space." | `text/normalise.py:Normaliser`<br>`text/normalise.py:normalise` | documents | Unicode Character Database 15.0.0 (Python 3.12) | default pending FS-01, FS-02 |
| TXT-03 | The registered word function | input | qmd § Measures: "A word, in the processing outcome's denominator and in every per-word quantity, is a whitespace-delimited token of the text as served that contains at least one letter or digit. A token of punctuation alone attaches to a neighbouring word." | `text/words.py:words`<br>`text/words.py:word_spans`<br>`text/words.py:count_words`<br>`text/words.py:word_extents` | documents, sat, seg_check, features_gramlex, features_discourse, surprisal_goldfish, surprisal_xglm | Unicode White_Space and general categories of the pinned version | default pending FS-01, FS-20, FS-32 |
| TXT-04 | Syntactic words for parse counts and lookups | input | qmd § Measures: "Parse counts and frequency lookups use syntactic words instead, the units a parser yields after splitting multi-word tokens."<br>supp § S3: "so the counting rules are fixed on syntactic words after multi-word-token expansion." | `parse/__init__.py:read_conllu`<br>`parse/__init__.py:tokens_from_conllu` | parse_stanza, parse_udpipe | as PRS-01 and PRS-02 | implemented |
| TXT-05 | Titles: the delivered title line, and page-initial titles under S3's rule | mask, reference for translations | supp § S3: "A title is the first line of a text or page if it has at most eight words and no sentence-final mark. Titles are identified on the English source and carried to each translation by line index if line structure survives." | `io/catalogue.py:split_lines`<br>`text/titles.py:find_page_titles`<br>`text/titles.py:is_title_line`<br>`text/titles.py:carry_page_titles`<br>`text/titles.py:exclude_page_titles` | documents | none | default pending G1a, G1b, G9, FS-34 |
| TXT-06 | Version key: story identifier, reading language, reading level and app version | input | qmd § Materials: "Every session will be linked to the features of the exact version it was served, matched on story identifier, reading language, reading level and app version." | `io/catalogue.py:parse_row`<br>`io/catalogue.py:level_of` | documents | none | not yet built |
| TXT-07 | Generated-or-classic indicator | covariate | qmd § Measures: "The generated-or-classic indicator enters as a covariate"<br>qmd § Confirmatory models: "the reading level, log text length, dialogue share, name-token share, valence, arousal and the generated-or-classic indicator" | `io/catalogue.py:kind_of` | documents | none | implemented |
| TXT-08 | The five story attributes, passed through from the delivery | sensitivity | qmd § Sensitivity analyses: "Because families choose the story attributes, a further refit enters the five attributes as fixed effects, falling back to catalogue means per attribute level where a factor is too sparse." | `io/catalogue.py:parse_row` | documents | none | implemented |
| TXT-09 | Word count per text: the outcome's denominator and, logged, the text-length covariate | input, covariate, reference for translations | qmd § Measures: "The processing outcome, serving Hypotheses 1 to 4 and 6, is the natural logarithm of elapsed reading time divided by the story's word count, standardised within reading language."<br>qmd § Measures: "Text length in words, dialogue share, name-token share, mean valence and mean arousal are pre-specified secondary text predictors and enter every model as covariates" | `features/pages.py:page_features`<br>`text/words.py:count_words` | features_gramlex | as TXT-03 | default pending G1a, G1b |
| TXT-10 | Catalogue median word count per language, and each story's word count in story units | input | qmd § Measures: "It is expressed in story units, each story's word count being divided by the median word count of the texts in its language's catalogue, so the unit does not depend on which readings are eligible." | planned: a catalogue-level aggregation step | none | none | not yet built |
| TXT-11 | Ratio of a catalogue's words to the English words of the same stories | reference for translations | qmd § Sampling plan: "Each language's word count is converted by the ratio of its catalogue's words to the English words of the same stories." | planned: a catalogue-level aggregation step | none | none | not yet built |
| TXT-12 | Page count of the delivered text | diagnostic, reference for translations | qmd § Sampling plan: "The page count recorded for the session must also equal that of the delivered text of its version."<br>qmd § Materials: "Where pages are parallel, the search runs page by page, so a page break ends a sentence exactly when it does in English." | `features/pages.py:page_features` | features_gramlex | none | implemented |
| TXT-13 | Pages per hundred words, and the page breaks that fall inside a sentence | sensitivity, diagnostic | qmd § Sensitivity analyses: "Pages per hundred words, computed from the delivered text, will enter a tier-1 refit along with its age-band interaction, and how pagination aligns with sentence ends will be reported." | `features/pages.py:page_features`<br>`features/pages.py:page_break_alignment` | features_gramlex | none | default pending G1b |
| TXT-14 | Letters per text, the denominator of the per-character refit | input, sensitivity | qmd § Sensitivity analyses: "The tier-1 model will be refitted with the outcome per character, counted in the unit Supplementary Tables 3 and 4 use for word length" | `features/lexical.py:LetterCounter` | none | none | not yet built |
| TXT-15 | Agreement of the registered word count with the platform's own | diagnostic | qmd § Measures: "Where the extract includes the platform's own word count, we will report its agreement with ours before any outcome model is fitted." | planned: the audit of the frozen extract | none | none | not yet built |

Notes.

- TXT-01. `split_lines` is copied verbatim from the extraction, whose delivery format puts the title on the first
  line and one page on each further line, with an in-page line break escaped as a backslash and `n`. Under the
  default title action (G1b), a page-initial title line is cut out of its page before the pages are joined, so
  `Document.text` is not the text as served wherever a page title is found. A page that held only its title stays
  in place, empty, so that page indices keep matching the pages served.
- TXT-05. The delivered title line is kept in `Document.title` and read by no feature (G1a). The page-title rule is
  applied on English pages and carried to a translation by line index (FS-34). G9 decides how often the rule can
  fire. The documents stage counts the pages that hold an in-page line break (`pages_with_line_breaks`), the page
  titles found (`page_titles`) and their words (`page_title_words`), so that G1b and G9 can be judged on the
  stand-in.
- TXT-06. The delivered tables carry no app-version field, so documents are keyed by story identifier, language and
  level, and the registered key is incomplete until the extract's app version is linked at the audit, after
  acceptance.
- TXT-08. The attributes (hero, world, theme, prompt, sidekick) are kept in `Document.meta`; the refit itself is R
  code run after acceptance.
- TXT-09. The denominator is defined on the text as served, qmd § Measures: "A word, in the processing outcome's
  denominator and in every per-word quantity, is a whitespace-delimited token of the text as served that contains at
  least one letter or digit." Two defaults change it. The delivered title line is not part of the pages (G1a), and
  under `stages/documents.toml [titles] action = "exclude"` a page title found under
  `stages/documents.toml [titles] page_rule = "multiline"` leaves its page (G1b), so its words leave the word count
  as they leave every other feature. The logarithm is taken in the model, not here.
- TXT-13. Pages per hundred words divides the page count by the registered word count, so a page title excluded
  under G1b raises it.
- TXT-14. `LetterCounter` counts letters per word by script (S3's word-length rule), but no stage writes a per-text
  total. Whether names and every word or only content words enter the total is not registered and should be fixed
  here when the row is built; the outcome's denominator counts every word, so every word is the natural default.
- TXT-15. The documents stage checks the delivered table's own `words` column against its pages
  (`catalogue_word_count_mismatches`), a consistency check of the delivery, not this diagnostic.

Tests: `tests/unit/test_text.py`, `test_io.py`, `test_documents.py`, `test_pages.py`, `test_lock.py`.

### 2.2 Segmentation

| id | quantity | role | anchor | module and function | stage | pins | status |
|---|---|---|---|---|---|---|---|
| SEG-01 | English sentences: the registered SaT call with the colon rule | input, reference for translations | qmd § Materials: "In English, a sentence ends where the registered Segment any Text (SaT) model places a boundary"<br>supp § S3: "the `sat-12l-sm` model run through `wtpsplit` 2.2.2"<br>supp § S3: "at a threshold of .25, with no boundary after a colon."<br>supp § S3: "Both parsers, the word function, the dialogue spans and every sentence-based feature take these sentences" | `segment/sat.py:predict`<br>`segment/sat.py:segment_text`<br>`segment/sat.py:registered_segments`<br>`segment/sat.py:apply_colon_rule` | sat | `segment-any-text/sat-12l-sm@d70c72a9331b`; tokeniser `FacebookAI/xlm-roberta-base@e73636d4f797`; wtpsplit 2.2.2; fp32, TF32 off | default pending G9, FS-33 |
| SEG-02 | Pages holding each sentence's first and last characters | reference for translations | qmd § Materials: "Where pages are parallel, the search runs page by page, so a page break ends a sentence exactly when it does in English." | `segment/__init__.py:page_anchors` | sat | none | implemented |
| SEG-03 | Five-sentence floor on the English source | mask, reference for translations | qmd § Outcome-blind dimension reduction: "A text whose English source has fewer than five sentences enters no family's solution in any language." | `segment/diagnostics.py:floor_excluded` | sat, seg_check | `pipeline.toml [floor] min_english_sentences = 5` | implemented |
| SEG-04 | Sentences and words per text, and the number of texts the floor removes | diagnostic | qmd § Outcome-blind dimension reduction: "We will report, per language, the distribution of sentences and of words per text and the number of texts the minimum removes." | `stages/seg_check.py:run`<br>`segment/diagnostics.py:quantiles` | seg_check | none | implemented |
| SEG-05 | Eight-sentence floor | sensitivity | qmd § Sensitivity analyses: "With the sentence floor raised to eight, we will refit the tier-1 model and report its three component coefficients and distinct-text count with the primary estimates." | `segment/diagnostics.py:floor_excluded` | none | none | not yet built |
| SEG-06 | English SaT against the frozen rule segmenter, boundary F1 of at least 95 (0.95 on the code's scale) | diagnostic | qmd § Outcome-neutral quality checks: "The second requires English SaT to reach a boundary F1 of 95 against a frozen rule segmenter on the served English texts."<br>qmd § Materials: "Boundary accuracy is scored without counting as an error a quotation mark placed on the other side of a boundary" | `segment/rules.py:rule_spans`<br>`segment/diagnostics.py:score_text`<br>`segment/diagnostics.py:boot_prf`<br>`stages/seg_check.py:run` | seg_check | frozen rule SEG-3 (`stages/seg_check.toml [rule]`) | default pending FS-03 |
| SEG-07 | Segmentation diagnostics: sentence length and the share of sentences without a terminal mark | diagnostic | supp § S3: "Per language, we will report the mean and standard deviation of sentence length and the proportion of sentences ending without a terminal mark."<br>supp § S3: "the union segmenter and the segmentation diagnostics recognise . ! ? … and their full-width forms as terminal marks" | `segment/diagnostics.py:mean_sd`<br>`segment/diagnostics.py:ends_with_terminal`<br>`stages/seg_check.py:run` | seg_check | none | implemented |
| SEG-08 | English sentences and terminal marks per text, the denominators of each translation's ratios to its source | reference for translations | supp § S3: "For every text, we will report the ratios of its sentences and of its terminal marks to those of its English source, with their median, interquartile range and share within 10 per cent." | `stages/sat.py:run` writes the sentence count (`n_sentences`); planned: a count of terminal marks beside it | sat | none | not yet built |

Notes.

- SEG-01. The call is S3's, and the settings S3 leaves open come from plan v3 and the builder (FS-33). The segments
  artefact also stores p', the boundary probability at the candidate positions. In English it lets the registered
  boundaries be rebuilt from the artefact and audited (`segment/sat.py:boundaries_from_candidates`); in a
  translation the union segmenter reads the translation's own p'. Boundaries that only an in-page line break forced
  are counted (`newline_forced`) so that G9 can be judged on the stand-in.
- SEG-03. The flag is written on the English source's segments record; every language takes it from there.
- SEG-05. `floor_excluded` takes the minimum as an argument, so the row needs only a stage that writes the flag at 8.
- SEG-06. The check runs on the keyed sample (REF-01), the code's name for what the protocol calls the fixed sample. The score is quote-tolerant boundary F1 with exact matching
  beside it and 2,000 cluster-bootstrap replicates, as in the benchmark.
- SEG-07. The per-language summaries are seg_check's; the per-text ratios to the English source are
  translation-side, and their English denominators are SEG-08.
- SEG-08. Every segments record holds `n_sentences`. No stage writes a text's count of terminal marks yet; the
  marks would be the union segmenter's (`stages/sat.toml [union] terminal_marks`).

Tests: `tests/unit/test_segment.py`; `tests/gpu/test_segment_gpu.py` (marked `gpu`).

### 2.3 Parses

| id | quantity | role | anchor | module and function | stage | pins | status |
|---|---|---|---|---|---|---|---|
| PRS-01 | Stanza parse of every registered sentence | input | supp § S3: "The two parsers of the grammatical features are Stanza 1.15.0 in its `nocharlm` tier, which tracks release 2.18 of Universal Dependencies, and UDPipe 2 with its models of release 2.17"<br>supp § S3: "Both run on every sentence of every text, each with the registered treebank for the language and its own tokeniser"<br>supp § S3: "The treebanks are Alpino for Dutch, GUM for English" | `parse/stanza_wrap.py:StanzaParser`<br>`parse/__init__.py:parse_shard` | parse_stanza | stanza 1.15.0; `models.lock.json` key `stanza-1.15.0` holds the frozen `resources.json` and every model file's checksums: English tokenize, pos, lemma and depparse from `gum_nocharlm`, mwt from `gum`, and the `conll17` pretrain, from `stanfordnlp/stanza-en@810dca30ddb2` | default pending FS-04 |
| PRS-02 | UDPipe 2 parse of every registered sentence | input | supp § S3: "The two parsers of the grammatical features are Stanza 1.15.0 in its `nocharlm` tier, which tracks release 2.18 of Universal Dependencies, and UDPipe 2 with its models of release 2.17"<br>supp § S3: "Both run on every sentence of every text, each with the registered treebank for the language and its own tokeniser" | `parse/udpipe_server.py:ServerProcess`<br>`parse/udpipe_client.py:UDPipeClient`<br>`parse/__init__.py:parse_shard` | parse_udpipe | model `english-gum-ud-2.17-251125` (archive SHA-256 in `models.lock.json` key `udpipe-2.17`); code `ufal/udpipe@223da86f482d` (branch udpipe-2); TensorFlow 2.21.0 (`envs/udpipe.lock`); embeddings `google-bert/bert-base-multilingual-uncased@7cbf9a625e29` | implemented |
| PRS-03 | UDPipe determinism rerun, which decides the CPU fallback | diagnostic | supp § S3: "UDPipe 2 runs on a GPU with deterministic operations, and it moves to a CPU if a rerun of the pilot on 1 per cent of the catalogue does not reproduce identical output." | `stages/parse_udpipe.py:_rerun` | parse_udpipe | as PRS-02 | implemented |
| PRS-04 | Long-unit rule: a sentence of more than 100 words takes Stanza's parse in both members | mask | supp § S3: "A unit longer than 100 words takes Stanza's parse in both members of the mean." | `parse/long_units.py:LongUnitRule.udpipe_member`<br>`features/parsemean.py:grammatical_features` | features_gramlex | `stages/parse_udpipe.toml [long_units] max_words = 100` | implemented |
| PRS-05 | Share of long units per language, and the flag above 1 per cent | diagnostic | supp § S3: "The share of such units is reported per language, a language above 1 per cent is flagged, and the calibration applies the same rule." | `parse/long_units.py:LongUnitRule.summary` | none | none | not yet built |
| PRS-06 | Second Stanza package on the keyed sample, reported as correlations | diagnostic | supp § S3: "In the 14 languages that have a second Stanza package, it runs on the fixed sample of 2,000 texts per language. Only its correlations are reported, and it is never averaged in, because it changes the annotation convention." | planned: a second-package option of the parse_stanza stage | none | the English package is not named (G3) | not yet built (G3) |
| PRS-07 | Triad flag: transported reliability against three parses of the keyed sample | diagnostic | supp § S3 / Measurement error and calibration: "the method-of-triads value from the pairwise correlations of three parses of the fixed sample, by Stanza, UDPipe 2 and Stanza on a second treebank." | planned: computed after acceptance from PRS-01, PRS-02 and PRS-06 | none | none | not yet built (G3) |
| PRS-08 | Third parser, trained only after its pilot's "go" and joining the mean only under its frozen rules | input | qmd § Materials: "the XLM-R-large encoder [@conneauUnsupervisedCrosslingualRepresentation2020] and fixed hyperparameters, seed and stopping rule" | planned: no stage in this plan | none | XLM-R-large and the third parser's frozen recipe, neither in the model lock yet | not yet built (P05, P46) |

Notes.

- PRS-01 and PRS-02. Each sentence is one parser unit, so neither parser can move a boundary. A line break inside a
  sentence is flattened to a space before parsing (`parse/__init__.py:flatten_line_breaks`, G9), one character for
  one, so offsets keep their meaning. Every token records its offsets in `Document.text` (`TokenRange` in MISC).
- PRS-01. The stage parses one text per call, so a parser batch never holds more than one story's sentences; the
  Stanza parser batch is otherwise Stanza's own (FS-04).
- PRS-03. Off on the stand-in by default (`stages/parse_udpipe.toml rerun_check_documents = 0`); the registered
  rerun is the 1 per cent pilot after acceptance.
- PRS-05. `features_gramlex` counts long units per text and in its timing record; the per-language share and flag
  are an aggregate (section 6).

Tests: `tests/unit/test_parse.py`; `tests/gpu/test_parse_gpu.py` (marked `gpu`).

### 2.4 Grammatical

| id | quantity | role | anchor | module and function | stage | pins | status |
|---|---|---|---|---|---|---|---|
| GRM-01 | Mean dependency distance, two-parser mean | anchor | qmd § Materials: "*Grammatical* features are mean dependency distance, clauses per sentence, the ratio of subordinate to main clauses, mean sentence length and noun-phrase elaboration, the number of modifiers per common noun."<br>qmd § Materials: "Each feature but sentence length is the unweighted mean of its values under two parsers, Stanza and UDPipe 2"<br>qmd § Outcome-blind dimension reduction: "For GrammaticalLoad, the anchors are dependency distance, subordination, clause density, sentence length and noun-phrase elaboration." | `features/grammatical.py:sentence_counts`<br>`features/grammatical.py:parse_features`<br>`features/parsemean.py:grammatical_features` | features_gramlex | PRS-01, PRS-02 | implemented |
| GRM-02 | Clauses per sentence, two-parser mean | anchor | qmd § Materials: "*Grammatical* features are mean dependency distance, clauses per sentence, the ratio of subordinate to main clauses, mean sentence length and noun-phrase elaboration, the number of modifiers per common noun."<br>qmd § Materials: "Open clausal complements are not counted as clauses." | `features/grammatical.py:sentence_counts`<br>`features/grammatical.py:parse_features`<br>`features/parsemean.py:grammatical_features` | features_gramlex | PRS-01, PRS-02 | implemented |
| GRM-03 | Subordination, the ratio of subordinate to main clauses, two-parser mean | anchor | qmd § Materials: "*Grammatical* features are mean dependency distance, clauses per sentence, the ratio of subordinate to main clauses, mean sentence length and noun-phrase elaboration, the number of modifiers per common noun."<br>qmd § Outcome-neutral quality checks: "The reported-speech rule keeps the translation's own speech spans where their agreement with the English source reaches a kappa of .70."<br>supp § S3 / Validation without human annotation: "The reported-speech rule for clause heads needs a sentence-level κ of at least .70 against the English source" | `features/grammatical.py:sentence_counts`<br>`features/grammatical.py:speech_span`<br>`features/grammatical.py:speech_ids_from_mask`<br>`features/grammatical.py:parse_diagnostics`<br>`features/parsemean.py:grammatical_features` | features_gramlex | PRS-01, PRS-02 | conflict CF-01, G6 |
| GRM-04 | Mean sentence length in registered words, not averaged over parsers | anchor | qmd § Materials: "Each feature but sentence length is the unweighted mean of its values under two parsers, Stanza and UDPipe 2"<br>qmd § Outcome-blind dimension reduction: "For GrammaticalLoad, the anchors are dependency distance, subordination, clause density, sentence length and noun-phrase elaboration." | `features/grammatical.py:words_per_sentence`<br>`features/grammatical.py:mean_sentence_length` | features_gramlex | SEG-01, TXT-03 | default pending FS-05, FS-06 |
| GRM-05 | Noun-phrase elaboration, modifiers per common noun, two-parser mean | anchor | supp § S3: "Noun-phrase elaboration counts the dependents of common nouns with the relations amod, nmod, acl, nummod or appos, leaving out determiners" | `features/grammatical.py:sentence_counts`<br>`features/grammatical.py:base`<br>`features/grammatical.py:parse_features`<br>`features/parsemean.py:grammatical_features` | features_gramlex | PRS-01, PRS-02 | default pending FS-31 |
| GRM-06 | Each parser's value, and their difference, for every grammatical anchor | diagnostic | supp § S3 / Measurement error and calibration: "is the variance of the difference between the Stanza and UDPipe 2 scores within reading level, measured on every text the children read." | `features/parsemean.py:grammatical_features` | features_gramlex | PRS-01, PRS-02 | implemented |
| GRM-07 | Correlation between subordination and clauses per sentence, per language | diagnostic | supp § S3: "Each language's correlation between subordination and clauses per sentence is reported with the per-language quality table" | planned: computed after acceptance from GRM-02 and GRM-03 | none | none | not yet built |
| GRM-08 | Clause heads counted from each word's own label | diagnostic | supp § S3: "Each parser alone. A second Stanza package, where the language has one, on the fixed sample, reported as correlations and never averaged in. Clause heads counted from each word's own label, as a descriptive analysis" | planned: a variant counter in `features/grammatical.py` | none | none | not yet built |
| GRM-09 | Correlation between surprisal and each grammatical feature, per language | diagnostic | qmd § Outcome-blind dimension reduction: "The correlation between surprisal and each grammatical feature will be reported per language next to the loadings" | planned: a catalogue-level aggregation of LEX-12 and GRM-01 to GRM-05 | none | none | not yet built |
| GRM-10 | Split-half reliability of each grammatical feature, per language | diagnostic | qmd § Outcome-blind dimension reduction: "A per-language quality table gives each resource's size, the matched-token proportions, split-half reliability" | planned: halves formed from per-sentence counts that `features_gramlex` does not yet write | none | none | not yet built (FS-35) |

Notes.

- GRM-01 to GRM-05. The counting rules are gfeat.py's (error model, 23 October 2026), promoted exactly: punctuation
  removed and positions renumbered for dependency distance, clause heads from the subordinate and main relation sets
  with predicate conjuncts inheriting their first conjunct's type, and elaboration on the relation set S3 names.
  Relations are matched by their base, so a subtype counts under its base relation (FS-31). Each parser's value
  pools its sentence counts over the text, and the two values are averaged text by text.
- GRM-03. A ccomp or csubj head inside direct speech counts as a main clause (the reported-speech rule). The
  registered rule reads the language's own speech spans, those of the registered dialogue detector that the κ .70
  gate tests; the default reads gfeat's quotation-mark spans instead (G6), which leave out single quotation marks,
  so English speech in ‘…’ is missed. The value written as `values.subordination` is plan v3's empirical logit,
  not the registered ratio (CF-01); each parser's raw ratio is in the diagnostics (`subordinate_main_ratio`).
- GRM-04. Words are placed in sentences by their first letter or digit (FS-05), and a segment with no word is left
  out of the denominator (FS-06).
- GRM-05. Matching by base relation counts English nmod:poss, the relation of possessive pronouns such as *his* and
  *my*, and acl:relcl, relative clauses, as elaboration (FS-31).
- GRM-06. Both members are kept in the diagnostics, together with UDPipe's value without the long-unit rule. The
  variance within reading level, Var_D, is computed at calibration, after acceptance.
- GRM-08. gfeat's own-label variant was removed in promotion because no primary quantity uses it; the descriptive
  analysis S3 registers needs it back.
- GRM-10. Halves need each sentence's counts under each parser member (non-punctuation words, summed dependency
  distance and dependencies, main and subordinate clause heads, common nouns and their elaborating dependents) and
  each sentence's registered words. `features_gramlex` writes text totals only, so either it writes these per
  sentence, or a stage computes the half values itself once FS-35 is decided.

Tests: `tests/unit/test_grammatical.py`; `tests/golden/features_gramlex/`.

### 2.5 Lexical

| id | quantity | role | anchor | module and function | stage | pins | status |
|---|---|---|---|---|---|---|---|
| LEX-01 | Mean log frequency (Zipf) of non-name content tokens, absent tokens at the floor | anchor | qmd § Materials: "*Lexical* features are mean log frequency of content words, the share of content tokens below ten per million (Zipf 4) on the uniform frequency resource, mean rated age of acquisition and mean orthographic length."<br>qmd § Materials: "A content token that is not a name and is absent from the frequency resource counts as rare and takes the resource's floor value in the mean."<br>supp § S3: "The primary frequency resource is a set of 19 lists built for this study from the 2024 release of the OpenSubtitles corpus"<br>qmd § Outcome-blind dimension reduction: "For LexicalDifficulty, they are frequency, surprisal and word length." | `features/lexical.py:frequency_features`<br>`features/lexical.py:build_frequency_resource`<br>`features/lexical.py:CountList`<br>`features/lexical.py:WordfreqList` | features_gramlex | interim: wordfreq 3.1.1, `best` list; primary: OpenSubtitles 2024 lists, not yet built | default pending P48, FS-08, FS-22 |
| LEX-02 | Rare-word share: content tokens below Zipf 4, absent tokens counted as rare | component, reference for translations | qmd § Materials: "*Lexical* features are mean log frequency of content words, the share of content tokens below ten per million (Zipf 4) on the uniform frequency resource, mean rated age of acquisition and mean orthographic length."<br>supp § S3: "An inflection diagnostic is therefore computed on the translated benchmark before submission and on the catalogue's fixed sample after acceptance, and it is reported beside the lexical slopes." | `features/lexical.py:frequency_features` | features_gramlex | as LEX-01 | default pending P48, FS-08, FS-22 |
| LEX-03 | Frequency variants: the mean over matched tokens, and the shares at Zipf 3 and over matched tokens | sensitivity | supp § S3: "The mean over matched tokens alone is a sensitivity analysis."<br>supp § S3: "The shares at Zipf 3 and over matched tokens alone are sensitivity analyses." | `features/lexical.py:frequency_features` | features_gramlex | as LEX-01 | default pending P48, FS-22 |
| LEX-04 | Mean log frequency on the 2018 OpenSubtitles lists | sensitivity | supp § S3: "Lists built by the same script from the 2018 release" | planned: the OpenSubtitles list builder, read by `features/lexical.py:load_count_list` | none | OpenSubtitles 2018 lists, not yet built | not yet built (P48) |
| LEX-05 | Contextual diversity: token-weighted mean of log film counts | sensitivity | qmd § Sensitivity analyses: "Contextual diversity, the number of films whose subtitles contain a word, replaces mean log frequency in one"<br>supp § S3: "It is counted in the same pass as frequency."<br>supp § S3: "The contextual-diversity refit under Sensitivity analyses replaces the mean-frequency anchor with the token-weighted mean of these values over the same tokens, and each language's text-level correlation between the two is reported." | planned: the OpenSubtitles list builder with film counts, and a lookup in `features/lexical.py` | none | OpenSubtitles 2024 lists, not yet built | not yet built (P48) |
| LEX-06 | Register diagnostic: English mean Zipf under the 2024 list against CYP-LEX | diagnostic | supp § S3: "Within reading level, it correlates each English source text's mean Zipf under the 2024 list with its mean under CYP-LEX, in the bands for ages 7 to 9 and 10 to 12." | planned: a lookup against CYP-LEX bands | none | CYP-LEX (only the correlations are deposited) | not yet built (P48) |
| LEX-07 | Word length: letters per non-name content word, by script | anchor | supp § S3: "Word length counts letters per content word, names excluded, by script. Latin, Greek and Cyrillic letters are counted without combining marks, and Arabic and Hebrew letters as base letters."<br>qmd § Outcome-blind dimension reduction: "For LexicalDifficulty, they are frequency, surprisal and word length." | `features/lexical.py:word_length_features`<br>`features/lexical.py:LetterCounter` | features_gramlex | none | default pending FS-09, FS-22 |
| LEX-08 | Mean length of all words | sensitivity | supp § S3: "The mean length of all words. Diversity over windows of 25 and 100 lemmas, over content forms and over all words, and the Measure of Textual Lexical Diversity" | `features/lexical.py:word_length_features` | features_gramlex | none | default pending FS-09, FS-22 |
| LEX-09 | Lexical density: share of non-name words that contain a content syntactic word | component | supp § S3: "Lexical density is the share of words, in the outcome's unit, that contain a content syntactic word, with punctuation and names excluded." | `features/lexical.py:density_features`<br>`features/lexical.py:classify_words` | features_gramlex | none | default pending FS-07, FS-22 |
| LEX-10 | Lexical diversity: MATTR over windows of 50 content lemmas | component | qmd § Materials: "Diversity is the moving-average type-token ratio over windows of 50 content lemmas." | `features/diversity.py:diversity_sequences`<br>`features/diversity.py:mattr`<br>`features/diversity.py:diversity_features` | features_gramlex | none | default pending FS-10, FS-22 |
| LEX-11 | Diversity variants: windows of 25 and 100, content forms, all words, and MTLD | sensitivity | qmd § Materials: "Its per-language correlations with the content-form and all-word versions and with the Measure of Textual Lexical Diversity will be reported."<br>supp § S3: "The mean length of all words. Diversity over windows of 25 and 100 lemmas, over content forms and over all words, and the Measure of Textual Lexical Diversity" | `features/diversity.py:diversity_features`<br>`features/diversity.py:mtld` | features_gramlex | none | default pending FS-10, FS-11, FS-12, FS-13, FS-22 |
| LEX-12 | Mean corrected word surprisal, Goldfish 1 GB tier, names excluded | anchor | qmd § Materials: "A word's surprisal is the sum of the surprisals of its subword tokens."<br>qmd § Materials: "The mean is taken over the words of the outcome's denominator, excluding names and words containing a character the model cannot encode."<br>qmd § Materials: "Surprisal is computed with the names present in context and excluded only from the mean."<br>supp § S3: "Each text is scored in windows of 512 tokens, the model's maximum, each beginning with the start token `[CLS]` as in training and never ending with `[SEP]`. Windows advance by 256 tokens, and the last one ends at the text's final token."<br>supp § S3: "with `[SEP]` in the set of boundary tokens."<br>supp § S3: "A fixed table replaces characters that a language's tokeniser cannot encode, such as the em dash (U+2014) in 10 of the 18 tokenisers, with equivalents in its vocabulary. A word that still holds an unknown token leaves the mean." | `features/surprisal.py:prepare_text`<br>`features/surprisal.py:plan_windows`<br>`features/surprisal.py:Scorer.score`<br>`features/surprisal.py:word_surprisal`<br>`features/surprisal.py:summarise`<br>`stages/surprisal_goldfish.py:run` | surprisal_goldfish | `goldfish-models/eng_latn_1000mb@1467d2805d90` (Apache-2.0); the pickled weights are converted once to safetensors by `features/surprisal.py:convert_pickled_checkpoint`, and the converted file's SHA-256 is pending in the model lock | not yet built (P06, P53, FS-20) |
| LEX-13 | Mean corrected word surprisal, Goldfish 100 MB tier, names excluded | sensitivity | qmd § Sensitivity analyses: "Surprisal comes from the 100 MB tier of the same language models in another, and from the multilingual XGLM-4.5B model in a third"<br>supp § S3: "The controlled contrast is `goldfish-models/<lang>_100mb`, which keeps architecture, vocabulary, corpus and tokeniser fixed and varies the byte-scaled data tenfold" | `features/surprisal.py:Scorer.score`<br>`features/surprisal.py:summarise`<br>`stages/surprisal_goldfish.py:run` | surprisal_goldfish | `goldfish-models/eng_latn_100mb@7101f5bcbf4d` (Apache-2.0), converted as LEX-12, its SHA-256 pending likewise | not yet built (P06, P53, FS-20) |
| LEX-14 | Mean corrected word surprisal, XGLM-4.5B, names excluded | sensitivity | qmd § Sensitivity analyses: "Surprisal comes from the 100 MB tier of the same language models in another, and from the multilingual XGLM-4.5B model in a third"<br>qmd § Timeline: "If the projection exceeds 400 GPU-hours, three steps apply in order until it fits."<br>qmd § Timeline: "First, the pretrained models used for sensitivity or validation, namely XGLM-4.5B, MetricX-24 and the coreference resolver, run with 16-bit (bf16) weights and 32-bit log-probabilities" | `features/surprisal.py:Scorer.score`<br>`features/surprisal.py:summarise`<br>`stages/surprisal_xglm.py:run` | surprisal_xglm | `facebook/xglm-4.5B@1c2905c6ab3e` (MIT, safetensors, pinned by SHA-256) | not yet built (P06, P53, FS-20, FS-25) |
| LEX-15 | Surprisal diagnostics per text: subword tokens, windows, replacements and unknown tokens | diagnostic | supp § S3: "Per language, we will report the mean and maximum subword-token count per text, the tokens-per-word ratio, the replacement counts and the proportion of texts longer than one window." | `features/surprisal.py:summarise` | surprisal_goldfish, surprisal_xglm | as LEX-12 to LEX-14 | implemented |
| LEX-16 | Mean surprisal of classic and of generated texts | diagnostic | qmd § Sensitivity analyses: "We will therefore report the mean per-word surprisal of classic and of generated texts per language before any outcome data are linked." | planned: computed from LEX-12 and TXT-07 | none | none | not yet built |
| LEX-17 | Mean age of acquisition, native rated norms | component | qmd § Materials: "*Lexical* features are mean log frequency of content words, the share of content tokens below ten per million (Zipf 4) on the uniform frequency resource, mean rated age of acquisition and mean orthographic length."<br>qmd § Outcome-blind dimension reduction: "They are therefore not anchors and enter the language-specific solutions but not the pooled one."<br>supp § S3: "Broad native rated sets, available for seven of the ten: English at about 30,000 words" | planned: a norm lookup beside `features/lexical.py:frequency_features` | none | Kuperman et al. (2012) ratings; file checksum not yet pinned | not yet built |
| LEX-18 | Mean concreteness, native rated norms | component | qmd § Materials: "Mean per-word surprisal under a language-specific neural language model, lexical density, lexical diversity and concreteness complete the family."<br>qmd § Outcome-blind dimension reduction: "They are therefore not anchors and enter the language-specific solutions but not the pooled one."<br>supp § S3: "Native human ratings only, with no value predicted or projected" | planned: a norm lookup beside `features/lexical.py:frequency_features` | none | Brysbaert et al. (2014) ratings; file checksum not yet pinned | not yet built |
| LEX-19 | Predicted age of acquisition and concreteness | sensitivity | qmd § Materials: "Predicted age of acquisition and concreteness, built by the same procedure, enter only the pooled sensitivity solutions." | planned: a lookup in the predicted resource | none | the predicted resource, not yet built | not yet built (P11, P50) |
| LEX-20 | Every norm-based mean with and without the name exclusion, and the two versions' correlation | diagnostic | qmd § Materials: "Each norm-based mean is reported with and without the exclusion, together with the two versions' correlation within each language." | `features/affect.py:text_affect` | features_discourse | none | not yet built |
| LEX-21 | Matched-token proportion of the frequency and affect lookups, and whether a text's value is defined | diagnostic | qmd § Materials: "Third, every measure reports the proportion of tokens it matched, and a language in which a measure matches fewer than 80 per cent of content-word tokens does not contribute it."<br>qmd § Outcome-blind dimension reduction: "A text's value is defined when at least one of its non-name content tokens is found in the feature's resource." | `features/lexical.py:frequency_features`<br>`features/affect.py:AffectSummary.coverage` | features_gramlex, features_discourse | none | default pending P48, FS-08, FS-22 |
| LEX-22 | Agreement of LexicalDifficulty's inputs across alternative resources | diagnostic | supp § S3: "The pairs compared are the 2024 and 2018 lists, the 1 GB and 100 MB surprisal models, and the two parsers' lemmas for diversity and density." | `stages/features_gramlex.py:document_features` writes the UDPipe lemma versions; planned: the agreement, an aggregate | none | none | not yet built (P48) |
| LEX-23 | Register gap: mean surprisal on a held-out OSCAR 21.09 sample beside the story texts' | diagnostic | supp § S3: "To measure the mismatch, we will report each model's mean per-word surprisal on the story texts, after acceptance and before linkage, and on a held-out 10 MB sample of its training corpus, OSCAR 21.09." | planned: the OSCAR sample scored as documents by `stages/surprisal_goldfish.py:run` | none | OSCAR 21.09 sample (gated access; no application on record, scout critique, item 15) | not yet built |
| LEX-24 | Corrected surprisal of every registered word, and its mean over all words but those holding an unknown token, under each model | input, diagnostic | qmd § Materials: "A word's surprisal is the sum of the surprisals of its subword tokens."<br>qmd § Materials: "Surprisal is computed with the names present in context and excluded only from the mean." | `features/surprisal.py:word_surprisal`<br>`features/surprisal.py:summarise`<br>`features/surprisal.py:text_mean`<br>`stages/surprisal_goldfish.py:run`<br>`stages/surprisal_xglm.py:run` | surprisal_goldfish, surprisal_xglm | as LEX-12 to LEX-14 | default pending FS-20, FS-25 |
| LEX-25 | Split-half reliability of each lexical feature, per language | diagnostic | qmd § Outcome-blind dimension reduction: "A per-language quality table gives each resource's size, the matched-token proportions, split-half reliability"<br>supp § S3: "Before submission, the per-language correlation matrices of the lexical features and their split-half values, labelled as internal consistency, are published from the translated benchmark." | planned: halves formed from per-token values that `features_gramlex` does not yet write | none | none | not yet built (FS-35) |

Notes.

- LEX-01 to LEX-03. Lookups take the lower-cased syntactic word through the shared lookup normalisation
  (`features/lexical.py:LookupNormaliser`). wordfreq stands in until the OpenSubtitles 2024 lists exist, although
  S3 keeps wordfreq only as the independent list of the third list gate; `CountList` reads the lists with the
  Laplace-smoothed Zipf of van Heuven et al. (2014) once the builder writes them.
- LEX-01 to LEX-03 and LEX-07 to LEX-11. Lexical features read the Stanza parse (FS-22).
- LEX-02. The English share is the reference for the inflection diagnostic of the translations.
- LEX-12 to LEX-14. Promoted from the benchmark scorers (predictability/scripts/gf_scorer.py and
  verify-surprisal/scripts/gf.py), with t_pm.py's checks (the correction's telescoping identity, non-negative
  surprisal and a brute-force word probability) kept as unit tests. Words are the registered words, and a
  punctuation-only token's subword surprisals join the word it attaches to (FS-20). Fixed batch shapes and fp32 with
  TF32 off follow DESIGN.md; XGLM-4.5B moves to bf16 only under the budget guard (P08), whose condition the Timeline
  sentence quoted first sets. The 1 GB tier stays primary unless the MECO check says otherwise (P07, P49).
- LEX-12 to LEX-14, the name mask. With `stages/surprisal_goldfish.toml [names] source = "none"`, and the same in
  `stages/surprisal_xglm.toml [names] source = "none"`, the default until P06 and P53 fix the name rule, no mask is
  applied and the registered mean (`mean_surprisal`) is written as null. LEX-24's per-word values are stored
  instead, so the registered mean can be recomputed under the frozen mask (`features/surprisal.py:text_mean`)
  without a second GPU pass. The alternative source, "artefact", reads two fields from the diagnostics of
  `features_gramlex`: the indices of the registered words that are names (`name_word_indices`) and the registered
  word count (`words`). That stage writes neither (its word count is `values.word_count`), so the route cannot run
  yet.
- LEX-15. The per-language summaries (mean and maximum tokens per text, tokens per word, the share of texts longer
  than one window) are aggregates of these per-text counts. The diagnostics also hold plan v3's descriptive extras
  (next-token entropy, the within-text standard deviation and surprisal per character), which the protocol does not
  register.
- LEX-17 and LEX-18. Native norms enter the language-specific solutions only, and the token-coverage rule decides
  each case; S3 expects English concreteness to pass it.
- LEX-20. Only the affect means have both versions so far (`valence_mean_with_names` and the like, COV-06); the
  frequency, age-of-acquisition and concreteness means have only the exclusion, and the within-language correlation
  is an aggregate.
- LEX-21. Per text, `features_gramlex` reports the content and matched tokens of the frequency lookup and
  `features_discourse` the affect coverage. Age of acquisition, concreteness, contextual diversity and the 2018
  lists will report theirs when built (LEX-04, LEX-05, LEX-17, LEX-18), and the duration's proportion is COV-12. The
  80 per cent rule and the text-coverage rule are applied over the catalogue, after acceptance.
- LEX-22. The UDPipe lemma versions of diversity and density are in the diagnostics of `features_gramlex`
  (`udpipe_alternatives`); the list and tier pairs wait for LEX-04 and LEX-13, and the agreement is an aggregate.
- LEX-24. The mean over all words keeps the names and leaves out words that hold an unknown token or were not
  tokenised; plan v3 reports it beside the registered mean. The per-word values are `diagnostics.word_surprisal`.
- LEX-25. Halves need per-token values: each content token's Zipf value or absence, its letters, whether it is a
  name, and the lemma sequences of the diversity measures. `features_gramlex` writes text totals only; the surprisal
  stages already store per-word values (LEX-24).

Tests: `tests/unit/test_lexical.py`, `test_diversity.py`, `test_surprisal.py`; `tests/golden/features_gramlex/`;
`tests/gpu/test_lm_gpu.py` (marked `gpu`).

### 2.6 Discourse

| id | quantity | role | anchor | module and function | stage | pins | status |
|---|---|---|---|---|---|---|---|
| DSC-01 | Mean semantic similarity of adjacent sentences, multilingual-E5-large-instruct | anchor | qmd § Materials: "*Discourse* features are mean semantic similarity between adjacent sentences from a multilingual sentence encoder, referential overlap, and causal and contrastive connectives per hundred words."<br>supp § S3: "identified by checkpoint, since no DOI is registered, and prompted with its developers' instruction for semantic similarity on both sentences of a pair."<br>qmd § Outcome-blind dimension reduction: "For ReferentialContinuity, they are adjacent-sentence similarity, referential overlap and the densities of causal and contrastive connectives." | `features/similarity.py:SentenceEncoder.encode`<br>`features/similarity.py:adjacent_cosines`<br>`features/similarity.py:mean_similarity`<br>`stages/encode_e5.py:run_encoder` | encode_e5 | `intfloat/multilingual-e5-large-instruct@274baa43b0e1` (MIT) | implemented |
| DSC-02 | Adjacent-sentence similarity under BGE-M3, and its correlation with the primary | sensitivity | supp § S3: "peer-reviewed and covering over 100 languages, retained as the sensitivity encoder"<br>supp § S3: "All ten in both, and the per-language correlation between the two estimates is reported with the feature-pipeline validation." | `features/similarity.py:SentenceEncoder.encode`<br>`features/similarity.py:adjacent_cosines`<br>`stages/encode_bgem3.py:run` | encode_bgem3 | `BAAI/bge-m3@5617a9f61b02` (MIT); the pickled weights are converted once to safetensors, and the converted file's SHA-256 is pending in the model lock | default pending FS-26 |
| DSC-03 | Referential overlap: adjacent pairs sharing a content lemma tagged NOUN or PROPN | anchor | qmd § Materials: "Referential overlap is the proportion of adjacent sentence pairs sharing at least one content lemma in a nominal position"<br>supp § S3: "For referential overlap as defined under Materials, a content lemma is in a nominal position when its universal part-of-speech tag is NOUN or PROPN, or X in Arabic, whose treebank tags names X" | `features/overlap.py:nominal_keys`<br>`features/overlap.py:adjacent_pairs`<br>`features/overlap.py:overlap_flags`<br>`features/overlap.py:share` | features_discourse | PRS-01 | default pending FS-22 |
| DSC-04 | Anaphoric continuation: overlap, or a third-person pronoun subject in the second sentence | sensitivity | supp § S3: "Anaphoric continuation, which also counts a pair as continuous when the next sentence's main clause has a third-person pronoun subject or, where the dropped-subject gate is passed, a dropped one." | `features/overlap.py:has_third_person_pronoun_subject`<br>`features/overlap.py:continuation_flags` | features_discourse | PRS-01 | default pending FS-22 |
| DSC-05 | Causal connectives per hundred words | anchor | qmd § Materials: "*Discourse* features are mean semantic similarity between adjacent sentences from a multilingual sentence encoder, referential overlap, and causal and contrastive connectives per hundred words."<br>supp § S3: "The causal anchors are *because*, *therefore*, *thus* and clause-initial *so*, and the contrastive anchors are *but*, *however*, *although*, *though*, *even though*, *even if* and *whereas*."<br>supp § S3: "Connectives per 100 words of the outcome's unit, counting the cues a reader met in the version served"<br>qmd § Confirmatory models: "The cue density counts causal and contrastive connectives per hundred words, untransformed so that its term is linear in the cues met." | `features/connectives.py:ConnectiveCounter.count`<br>`features/connectives.py:is_clause_initial`<br>`features/connectives.py:per_words` | features_discourse | PRS-01 | default pending FS-14, FS-22 |
| DSC-06 | Contrastive connectives per hundred words | anchor | supp § S3: "The causal anchors are *because*, *therefore*, *thus* and clause-initial *so*, and the contrastive anchors are *but*, *however*, *although*, *though*, *even though*, *even if* and *whereas*."<br>supp § S3: "Connectives per 100 words of the outcome's unit, counting the cues a reader met in the version served" | `features/connectives.py:ConnectiveCounter.count`<br>`features/connectives.py:is_not_x_but_y`<br>`features/connectives.py:per_words` | features_discourse | PRS-01 | default pending FS-15, FS-22 |
| DSC-07 | Causal density without *so* | sensitivity | supp § S3: "so the inventory induced without *so* is a sensitivity analysis." | `features/connectives.py:ConnectiveCounter.count`<br>`features/connectives.py:per_words` | features_discourse | PRS-01 | default pending FS-14, FS-22 |
| DSC-08 | Additive and temporal connective densities | diagnostic | qmd § Measures: "The variability of valence and of arousal, and the additive and temporal connective densities, will be computed for description only and excluded from the component solution." | planned: the `additive_temporal` switch of `features_discourse`, which refuses to run without lists | none | none | not yet built (G4) |
| DSC-09 | English anchor flags per sentence, for inducing the translations' inventories | reference for translations | supp § S3: "counting co-occurrence only over aligned sentence pairs whose English side carries anchors of one relation class." | `stages/features_discourse.py:run`<br>`features/connectives.py:ConnectiveCounter.count` | features_discourse | PRS-01 | default pending FS-14, FS-15, FS-22 |
| DSC-10 | CorPipe 26 coreference chains on every English source | reference for translations | qmd § Materials: "Coreference is resolved only on the English source of each version, as a reference for each language's overlap"<br>supp § S3: "with its umT5-xl one-stage model, instead resolves coreference on every English source as a validation reference."<br>qmd § Timeline: "If the projection exceeds 400 GPU-hours, three steps apply in order until it fits."<br>qmd § Timeline: "First, the pretrained models used for sensitivity or validation, namely XGLM-4.5B, MetricX-24 and the coreference resolver, run with 16-bit (bf16) weights and 32-bit log-probabilities" | `reference/corpipe_run.py:input_conllu`<br>`reference/corpipe_run.py:launch`<br>`reference/corpipe_run.py:document_chains`<br>`stages/coref_corpipe.py:run` | coref_corpipe | `ufal/corpipe26-onestage-corefud1.4-xl-260702@1235c0ee2f1e` (CC BY-NC-SA 4.0, hdl 11234/1-6205) with its encoder `google/umt5-xl@e02ba7fcf3d6`; code `ufal/crac2026-corpipe@ec853c3b2d97` (MPL-2.0), the script pinned by SHA-256; the budget guard's smaller model `ufal/corpipe26-onestage-corefud1.4-large-260702@c2d4f6974da7` with its encoder `google/mt5-large@50b7223e98fc` | default pending G8, FS-27 |
| DSC-11 | English chain continuity of adjacent pairs, and the English-internal ceiling of the κ with overlap | diagnostic | supp § S3: "Each language's κ between projected English chain continuity and its own overlap is reported beside the English-internal ceiling." | `reference/corpipe_run.py:document_chains` | coref_corpipe | as DSC-10 | default pending G8, FS-27, FS-28 |
| DSC-12 | Overlap anchor masked by the English coreference chains | sensitivity | qmd § Materials: "Its coreference chains, resolved in English and projected onto the translation by word alignment, mask a sensitivity overlap anchor computed on the served text (Sensitivity analyses)."<br>qmd § Sensitivity analyses: "Under the English-source rule in Materials, a further refit replaces referential overlap with continuity through English coreference chains projected onto each translation"<br>supp § S3: "An overlap anchor masked by the English source's coreference chains, projected through the word aligner" | planned: a masked variant of `features/overlap.py:overlap_flags` | none | as DSC-10 | not yet built (G8) |
| DSC-13 | Split-half reliability of each discourse feature, per language, connective use included | diagnostic | qmd § Outcome-blind dimension reduction: "A per-language quality table gives each resource's size, the matched-token proportions, split-half reliability"<br>supp § S3: "A story's split-half reliability of connective use describes how evenly the story uses connectives." | planned: halves formed from per-pair flags and per-sentence counts that `features_discourse` does not yet write | none | none | not yet built (FS-35) |

Notes.

- DSC-01 and DSC-02. Promoted from translated_union's seglib2.E5 and tu5_e5.py (e5: the developers' instruction
  for semantic similarity, mean pooling, L2 normalisation, at most 512 tokens) and verify-discourse's enc_compare.py
  (BGE-M3: the first token's hidden state, no instruction). Pairs are adjacent registered sentences, a text with fewer
  than two sentences has no value, each sentence is padded to its own length bucket so its embedding never depends on
  its batch, and embeddings are not stored. Per-pair cosines are kept for the agreement and generalisability
  tables.
- DSC-03 and DSC-04. Pairs in which either sentence has no parse are left out and counted. English has no
  dropped-subject branch, since that clause applies only in the eight null-subject languages.
- DSC-05 to DSC-07. The registered log(1 + x) transform is applied at the dimension reduction, so densities are
  written raw. Untransformed, the causal and contrastive densities sum to the cue term of the Hypothesis 3
  decomposition. The English inventory is the anchor list itself.
- DSC-09. Written as the indices of the sentences that hold a causal or a contrastive anchor
  (`diagnostics.sentences_causal`, `diagnostics.sentences_contrastive`).
- DSC-10 and DSC-11. The model card and the model's `options.json` name `google/umt5-xl` as the encoder, as S3
  does, and the stage checks it. By default the stage reads the `parses_stanza` CoNLL-U, so CorPipe sees the
  registered sentences and Stanza's syntactic words, the tree serving only to pick each mention's head (G8). Each
  story is its own input file, so its output never depends on its shard. The pinned official script runs unchanged,
  with TF32 turned off (minnt turns it on by default). Under the budget guard, bf16 is the first step and the
  smaller model the second (P08).
- DSC-12. For English the served text is the source, so the chains mask the English overlap directly; the
  translations need the word aligner (section 5).
- DSC-13. The encoder stages already keep per-pair cosines. `features_discourse` writes overlap and continuation as
  counts and connectives as the indices of the sentences with a hit, so halves also need the per-pair overlap and
  continuation flags, each sentence's causal and contrastive counts, and each sentence's registered words.

Tests: `tests/unit/test_overlap.py`, `test_connectives.py`, `test_similarity.py`, `test_reference.py`.

### 2.7 Covariates and masks

| id | quantity | role | anchor | module and function | stage | pins | status |
|---|---|---|---|---|---|---|---|
| COV-01 | Dialogue share: words whose first letter lies inside direct speech | covariate, reference for translations | qmd § Measures: "Dialogue share is the proportion of a text's words that lie inside direct speech, detected from the quotation marks catalogued by the Unicode Common Locale Data Repository"<br>supp § S3: "Dialogue spans are detected from the primary and alternate quotation pairs of release 47 of the Unicode Common Locale Data Repository"<br>supp § S3: "A line-initial dialogue dash opens a turn that runs to the end of the line, if line breaks survive within pages, and an opener unmatched at the end of its page closes there."<br>supp § S3: "The share of a text's words whose first letter lies inside direct speech, with spans detected from quotation marks and dialogue dashes by the rules given before this table" | `features/dialogue.py:QuoteInventory`<br>`features/dialogue.py:speech_mask`<br>`features/dialogue.py:speech_words`<br>`features/dialogue.py:share` | features_discourse | CLDR 47: `cldr-misc-full` 47.0.0, `main/en/delimiters.json`, SHA-256 7dba09b7aba3f8c98292df1e6fee27cdc950d3542139472799ca350d877909bb (Unicode-3.0), recorded in a comment of `stages/features_discourse.toml [dialogue]` and not yet in `resources.lock.json` | default pending G9, FS-23 |
| COV-02 | Speech status of each English sentence | reference for translations | supp § S3 / Validation without human annotation: "The reported-speech rule for clause heads needs a sentence-level κ of at least .70 against the English source, and below that, a language takes speech status from the English source through the aligner."<br>supp § S3 / Validation without human annotation: "Keeps the served value at r ≥ .80 and the language's own speech spans at κ ≥ .70" | `features/dialogue.py:spans_with_speech` | none | as COV-01 | not yet built |
| COV-03 | Name inventory and name mask, route A for English | mask, reference for translations | qmd § Materials: "Names are taken from a frozen inventory, built after acceptance and before linkage by a two-route rule that no person reviews."<br>qmd § Materials: "A type is a name if the Stanza parse tags at least half its occurrences as a proper noun, or as X in Arabic, the catch-all tag its treebank gives names." | `features/names.py:NameCounts.inventory`<br>`features/names.py:write_inventory`<br>`features/names.py:name_flags`<br>`features/lexical.py:name_predicate` | features_discourse, features_gramlex | PRS-01 | default pending P06, P53 |
| COV-04 | Name-token share on the empirical-logit scale | covariate, reference for translations | qmd § Materials: "Name-token share, the empirical logit of the proportion of words in the outcome's unit that are names, therefore enters every model as a covariate."<br>qmd § Outcome-blind dimension reduction: "Dialogue share and name-token share, which are covariates, are likewise excluded from the component solution." | `features/names.py:words_overlapping`<br>`features/names.py:NameMeasures.share_elogit` | features_discourse | PRS-01 | default pending P06, P53, FS-16 |
| COV-05 | Distinct name types per hundred words, and mean repetitions per type | diagnostic, sensitivity, reference for translations | qmd § Materials: "We will also report the number of distinct name types per hundred words and the mean repetitions per type, counting types by lemma."<br>qmd § Sensitivity analyses: "A last refit enters the English-source values of the covariates beside the served-text values and adds name types per hundred words." | `features/names.py:NameMeasures.types_per`<br>`features/names.py:NameMeasures.tokens_per_type` | features_discourse | PRS-01 | default pending P06, P53, FS-17 |
| COV-06 | Mean valence and mean arousal over matched non-name content tokens, with and without the name exclusion | covariate, reference for translations | qmd § Materials: "*Affective* features are the mean and the variability of valence and of arousal."<br>supp § S3: "MEmoLon, induced for 91 languages from a single procedure, at over 100,000 entries per language"<br>supp § S3: "Lookups try the language-aware lower case, the surface form and the lemma, then a script fallback."<br>supp § S3: "Rows equal to a language file's unknown-word default are dropped." | `features/affect.py:load_memolon`<br>`features/affect.py:candidate_keys`<br>`features/affect.py:text_affect` | features_discourse | MEmoLon MTL_grouped v1.0, doi:10.5281/zenodo.3756607 (CC BY 4.0), `resources.lock.json` key `memolon_mtl_grouped_en` | default pending FS-22 |
| COV-07 | Variability of valence and of arousal | diagnostic | qmd § Measures: "The variability of valence and of arousal, and the additive and temporal connective densities, will be computed for description only and excluded from the component solution." | `features/affect.py:text_affect` | features_discourse | as COV-06 | default pending FS-18, FS-22 |
| COV-08 | Mean valence and arousal from native rated norms | sensitivity | qmd § Materials: "Native norms will be run as a pre-specified sensitivity analysis, and their correlation with the single-specification values will be reported for each language."<br>supp § S3: "Native rated norms, whose size differs by more than an order of magnitude across the ten: English about 14,000" | planned: a second lexicon read by `features/affect.py:text_affect` | none | Warriner et al. (2013) norms; file checksum not yet pinned | not yet built |
| COV-09 | Mean valence and arousal from a child-rated set, inside each age band | diagnostic | supp § S3: "For the languages in which a child-rated set is available, we will recompute mean valence and mean arousal from it at rating ages inside each band." | planned: as COV-08 | none | no child-rated English set is named yet | not yet built |
| COV-10 | Predicted spoken duration per word, log scale | sensitivity | qmd § Materials: "One further text quantity serves Hypothesis 4 alone, a predicted spoken duration per word on a log scale."<br>supp § S3: "Predicted seconds, the rate per unit times the text's spoken units plus 0.55 s per sentence end and 0.20 s per clause mark, divided by the words and log-transformed. The units are eSpeak NG 1.52.0 phones, through phonemizer 3.4.0, at 0.08 s each in the 13 languages written in Latin, Greek or Cyrillic script."<br>qmd § Sensitivity analyses: "We will also report the Hypothesis 4 contrast within each age band and the duration-adjusted contrast from a refit adding the spoken duration per word and its interaction with narration." | `features/duration.py:Phonemizer`<br>`features/duration.py:count_phones`<br>`features/duration.py:PauseRules.clause_mark_count`<br>`features/duration.py:DurationConstants.seconds`<br>`features/duration.py:log_seconds_per_word` | features_discourse | eSpeak NG 1.52.0 and phonemizer 3.4.0 (GPL-3.0, run as a separate process); voice `en-us` | default pending G5, FS-19 |
| COV-11 | Correlation of the predicted duration with each component | diagnostic | supp § S3: "Its correlation with each component is reported before any outcome is linked" | planned: computed after acceptance from COV-10 and the component scores | none | none | not yet built |
| COV-12 | Matched-token proportion of the predicted duration | diagnostic | qmd § Materials: "Its resources and matched-token proportion are given in Supplementary Table 3."<br>supp § S3: "All ten, with the matched-token proportion reported per language as for every other measure." | planned: a share formed from the per-text counts `features_discourse` writes | none | as COV-10 | not yet built (FS-36) |

Notes.

- COV-01. The detector runs on the normalised text, never on lookup keys. Spans come from the locale's CLDR 47
  primary and alternate pairs in `config/languages.toml`, the direction of an ambiguous mark from its spacing, and
  dash turns only where in-page line breaks survive (G9). The served value equals the English-source value in
  English, and the gates of section 5 compare the two in each translation. Validation on public hand-annotated text is P54.
- COV-02. `spans_with_speech` computes it, but no stage writes it per sentence.
- COV-03. For English the inventory has route A only; route B projects English names into the translations. The two
  feature stages mask names differently by default: `features_discourse` builds the type-level inventory over the
  catalogue and writes it beside its artefact, while `features_gramlex` masks a syntactic word by its own tag
  (`stages/features_gramlex.toml [lexical.names] rule = "token_upos"`), the error-model benchmark's rule, unless
  that key is set to "inventory" and pointed at the inventory. One frozen inventory should mask both before the
  inventory is frozen (P06, P53).
- COV-04 and COV-05. A word of the outcome's unit is a name when a token holding a name overlaps it. Types are
  counted by lemma.
- COV-06 and COV-07. Lookups use the shared normalisation and the order lower case, surface form, lemma; English has
  no script fallback. Multi-word entries and rows equal to the unknown-word default are dropped. The admission rule
  compares a language's FLORES-200 document means with English, so English is the reference.
- COV-10. Phones from eSpeak NG through phonemizer, sentence ends from the registered segmentation (FS-19) and
  clause marks under G5. eSpeak NG 1.52.0 has to be built from its tag, since Debian bookworm ships 1.51 (scout
  report).
- COV-12. `features_discourse` writes each text's phones and phonemized words (`phonemized_words`). What a matched
  token is for a quantity that looks nothing up in a list is not registered (FS-36).

Tests: `tests/unit/test_dialogue.py`, `test_names.py`, `test_affect.py`, `test_duration.py`.

### 2.8 English references and checks run after acceptance

| id | quantity | role | anchor | module and function | stage | pins | status |
|---|---|---|---|---|---|---|---|
| REF-01 | Keyed-sample membership: each story's keyed hash and the cut-off of each sample size | reference for translations | qmd § Outcome-neutral quality checks: "A registered sentence aligner pairs the two on a fixed sample of 2,000 story versions per language, chosen from the story identifiers by a rule fixed in advance, so that every run draws the same versions."<br>supp § S3 / Validation without human annotation: "After acceptance, the three segmentation checks registered under Outcome-neutral quality checks run on the fixed sample." | `records.py:keyed_hash`<br>`text/keyed.py:keyed_cutoffs`<br>`text/keyed.py:in_keyed_sample`<br>`stages/documents.py:run` | documents | `pipeline.toml [keys]` and `stages/documents.toml [keyed_sample]` | default pending G7 |
| REF-02 | English pages as the source of MetricX-24 quality estimation | reference for translations | qmd § Sensitivity analyses: "Translation quality is estimated for every translated page against its English source by MetricX-24 in its reference-free mode"<br>qmd § Sensitivity analyses: "A text's value is the word-weighted mean over its pages."<br>supp § S3 / Validation without human annotation: "Every translated page is scored against its English source by MetricX-24-Hybrid-XL in its reference-free quality-estimation mode" | `reference/metricx_qe.py:qe_input`<br>`reference/metricx_qe.py:QEScorer.score`<br>`reference/metricx_qe.py:word_weighted_mean`<br>`stages/qe_metricx.py:run` | qe_metricx | `google/metricx-24-hybrid-xl-v2p6@f6e7f99a6555` (Apache-2.0; the pickled shards are pinned by SHA-256, and an optional safetensors conversion is pending); tokeniser `google/mt5-xl@63fc6450d805` (Apache-2.0); the official code it reproduces, `google-research/metricx@fc4978eb0646` | default pending FS-29, FS-30 |
| REF-03 | English page embeddings for the adequacy covariate | reference for translations | qmd § Sensitivity analyses: "One refit adds the within-story deviation of that estimate, with an adequacy covariate, the cosine between the sentence-encoder embeddings of each English page and its translation." | planned: a page-pair cosine beside `features/similarity.py:SentenceEncoder.encode` | none | as DSC-01 | not yet built |
| CHK-01 | Anomaly battery: language identity, length ratio, loops, unknown characters and script purity | mask, diagnostic | qmd § Outcome-neutral quality checks: "A registered anomaly battery checks every text for language identity, an extreme length ratio to its English source, repeated loops, unknown characters and script purity."<br>qmd § Outcome-neutral quality checks: "Texts that fail are excluded and counted, and a language is flagged if more than 5 per cent fail."<br>supp § S3 / Validation without human annotation: "Its length-ratio check flags a ratio to the English source beyond three median absolute deviations." | planned: no module or stage yet | none | the language-identification tool is not registered (G2) | not yet built (G2) |
| CHK-02 | Agreement table, generalisability study, known-groups check and per-language quality table, English beside every language | diagnostic | qmd § Outcome-blind dimension reduction: "One agreement table gives, for every feature, covariate and component, the story share and, per language, the Spearman correlation with the English source and with the other languages."<br>qmd § Outcome-blind dimension reduction: "A known-groups check reports each component's standardised differences between a story's versions at the three reading levels, and the share of stories whose versions it orders by level, with English beside every language."<br>qmd § Outcome-blind dimension reduction: "A generalisability study of every feature and component, within reading level, estimates variance components for story and for story by language."<br>qmd § Outcome-blind dimension reduction: "A per-language quality table gives each resource's size, the matched-token proportions, split-half reliability, the accuracy of segmentation and parsing, the story share" | planned: computed after acceptance from the artefacts' `values`, except split-half reliability (GRM-10, LEX-25, DSC-13) | none | none | not yet built |
| CHK-03 | English-source component scores | reference for translations | qmd § Confirmatory models: "It enters instead as an adjustment, through the language's own failed score and the English-source score of the same story version."<br>qmd § Sensitivity analyses: "A descriptive two-stage least-squares refit will use the English-source score as an instrument for a partly included language's own score." | planned: R code run after acceptance, outside this package | none | none | not yet built |

Notes.

- REF-01. Each document stores its keyed hash (`meta.keyed_hash`), which depends on its identifier alone, and the
  documents manifest records the cut-off of each sample size over the stories of the input; a story is in the
  sample of n when `text/keyed.py:in_keyed_sample` says so, and a larger sample contains every smaller one (the
  connective sample is enlarged by count alone, up to 10,000 versions). The keyed order is the same in every
  language, but each language's sample is cut from its own story set, so two languages share a sample only where
  their story sets agree; the Czech and Slovak deliveries are partial.
- REF-02. The English dry run has no translations of the stand-in, so the stage reads page pairs from `--input` and
  is timed on the translated benchmark's. A text's value weights pages by the registered word count of the
  translated page. The scorer is a port of the developers' code (google-research/metricx, which pins transformers
  4.30.2), admitted only if it reproduces the official scores on public pairs (FS-30). Its validation against
  public human judgements is P13 and P57.
- CHK-01. The extraction already flags repetitive texts by their compression ratio, which is not the registered
  loop check. The language-identification tool and the rules for loops, unknown characters and script purity are
  still to be registered (G2). Running the battery before parsing would also bound the Stanza batch memory that
  loops inflate (scout critique, item 9).
- CHK-02. The agreement table, the known-groups check and the generalisability study read the per-text values the
  stages write. Split-half reliability needs each feature recomputed on two halves of every text, which the
  artefacts cannot support yet (GRM-10, LEX-25, DSC-13).
- CHK-03. The reduction, the calibration and these scores are R code run after acceptance; the row is listed
  because English enters each of them.

## 3. Gaps G1a to G9 and the default each builder takes

The scout's gap G1 is split in two here: G1a is the title line the scout asked about, and G1b is the page-title rule,
whose default changes a registered quantity.

| gap | open question | default taken | switch | where | decided by |
|---|---|---|---|---|---|
| G1a | The delivered title line, the first line of each delivered file | Excluded from the pages, so no feature and no word count reads it; it is kept in `Document.title`. The extraction's own `words` column leaves it out too. Where the extraction's anomaly check finds the title line blank, or starting with a page marker because the first page was taken for the title, the documents stage counts it (`title_lines_empty`, `title_lines_page_marker`) and records it in `meta.title_line_issue`, but the line still stays out of the pages, so such a text loses that page. | none: the delivery format (`io/catalogue.py:split_lines`) | TXT-01, TXT-05, TXT-09 | this specification; the scout recommends exclusion, as the extraction does |
| G1b | Page-initial titles under S3's rule: which pages are tested, which marks are sentence-final, how the final-mark test reads, and what a title found does | A page is tested only when an in-page line break follows its first line; the sentence-final marks are S3's terminal marks with the language's own added; a line holding any of them anywhere is no title; and a title found is cut out of its page into `meta.page_titles`, so its words leave `Document.text`, the word count (the outcome's denominator), the sentences and every feature. The alternatives are "mark", which records the title and serves the page whole, and keeping the title as its own sentence, which "mark" already gives wherever SaT is forced to a boundary at the line break after it (G9), unless the title ends in a colon. | `stages/documents.toml [titles] page_rule = "multiline"`<br>`stages/documents.toml [titles] terminal_marks`<br>`stages/documents.toml [titles] final_mark_test = "anywhere"`<br>`stages/documents.toml [titles] action = "exclude"` | TXT-01, TXT-05, TXT-09, TXT-13, `text/titles.py`, documents | the PI. The default changes a registered quantity, since the outcome's denominator is defined on the text as served, and S3's rule, which sits in its segmentation paragraph, does not say that a title leaves the text. The scout's recommendation covered only the title line (G1a). |
| G2 | Language identification, unknown characters and script purity in the anomaly battery | None: the battery is not built. | none | CHK-01 | this specification, after a public-data check of candidate tools |
| G3 | English's second Stanza package, for the correlations and the triad flag | None: no stage runs a second package. The scout recommends `ewt_nocharlm`. | none | PRS-06, PRS-07 | this specification |
| G4 | English anchors for the additive and temporal densities | Off: no list, and the stage refuses the switch without one. The scout recommends deriving them from GUM by the procedure that chose the causal and contrastive anchors. | `stages/features_discourse.toml [connectives] additive_temporal = false`<br>`stages/features_discourse.toml [connectives] additive = []`<br>`stages/features_discourse.toml [connectives] temporal = []` | DSC-08, features_discourse | this specification |
| G5 | What a clause mark is in the duration formula | Comma, semicolon and colon with their full-width forms, not between two digits, and dashes: a run of dash characters, a run of two or more hyphens or a hyphen between spaces counts once. | `stages/features_discourse.toml [duration] clause_marks = [",", ";", ":", "，", "；", "："]`<br>`stages/features_discourse.toml [duration] clause_dashes`<br>`stages/features_discourse.toml [duration] ascii_double_hyphen_is_dash = true`<br>`stages/features_discourse.toml [duration] spaced_hyphen_is_dash = true`<br>`stages/features_discourse.toml [duration] skip_between_digits = true` | COV-10, `features/duration.py` | this specification |
| G6 | Which spans count as direct speech in the subordination count | gfeat's quotation-mark spans: the words strictly between paired double marks, guillemets or corner brackets of one sentence, single quotation marks left out because they double as apostrophes, so English speech in ‘…’ is missed. This departs from S3, whose reported-speech rule reads the language's own speech spans, those the registered dialogue detector finds and the κ .70 gate tests, and from the scout's recommendation to promote gfeat with the registered dialogue spans as its input. The detector's spans are available as `detector_spans`; switching changes the error-model counts, so EM-5 and EM-6 must be rerun. | `stages/features_gramlex.toml [grammatical.speech] rule = "quote_marks"` | GRM-03, `features/grammatical.py` | the PI, since the default departs from the registered rule; then the error model's last run |
| G7 | The key string of every keyed sample | `intract\|<purpose>\|v1\|<story id>`, hashed with SHA-256; the keyed sample's purpose is `keyed_sample` and sharding's is `shard`. The benchmarks used the prefix `intract-presub`. The keyed samples and the shards take the prefix and version from `pipeline.toml [keys]`: the two stages that assign shards, documents and qe_metricx, pass that table to `records.py:shard_of`, whose defaults are its committed values, and seg_check checks each document's stored keyed hash against it. | `pipeline.toml [keys] prefix = "intract"`<br>`pipeline.toml [keys] version = "v1"`<br>`stages/documents.toml [keyed_sample] purpose = "keyed_sample"` | REF-01, `records.py`, `text/keyed.py` | this specification |
| G8 | Which CoNLL-U and tokenisation CorPipe reads | The `parses_stanza` CoNLL-U: the registered sentences with Stanza's GUM syntactic words, one input file per story; the tree only picks each mention's head. `parses_udpipe` is the alternative. | `stages/coref_corpipe.toml [input] parse = "parses_stanza"` | DSC-10 to DSC-12, `reference/corpipe_run.py`, coref_corpipe | this specification |
| G9 | In-page line breaks | They exist in the delivery format, escaped and decoded by the extraction (scout critique, item 21); how often they occur in the catalogue is not counted. SaT is forced to a boundary at each one, which is wtpsplit 2.2.2's default and plan v3's setting, and the forced boundaries are counted; page-initial titles are looked for only on pages that hold one; and a line-initial dash opens a dialogue turn to the line's end. A break inside a sentence is flattened to a space before parsing, which the registered sentences require and no switch changes. | `stages/sat.toml [call] split_on_input_newlines = true`<br>`stages/documents.toml [titles] page_rule = "multiline"`<br>`stages/features_discourse.toml [dialogue] dash_turns = true` | SEG-01, TXT-05, COV-01 | this specification, with the per-page count of line breaks if it is authorised |

## 4. Other open choices, and conflicts with the registered text

### 4.1 Open choices

These are choices the protocol leaves open that have no gap number or pending-benchmark id. Each default sits behind
the switch named, or is fixed in the code named where no switch exists. FS-21 of the first draft is now CF-01
(section 4.2), and its number is not reused.

| id | open choice | default taken | switch | rows |
|---|---|---|---|---|
| FS-01 | The Unicode Character Database the run uses | 15.0.0, the version of Python 3.12; a different version is recorded and the run continues. | `stages/documents.toml [normalise] unicode_version = "15.0.0"`<br>`stages/documents.toml [normalise] on_unicode_mismatch = "warn"` | TXT-02, TXT-03 |
| FS-02 | Which characters are the "invisible format characters" | The benchmark's set: U+200B to U+200F, U+202A to U+202E, U+2060 to U+2069, U+061C and U+FEFF. The soft hyphen and the other format characters are kept. | `stages/documents.toml [normalise] delete_ranges = [[0x200B, 0x200F], [0x202A, 0x202E], [0x2060, 0x2069], [0x061C, 0x061C], [0xFEFF, 0xFEFF]]` | TXT-02 |
| FS-03 | Whether the point estimate or the lower 95 per cent limit of SaT's F1 must reach .95 | The point estimate, as the benchmark decided. | `stages/seg_check.toml [criterion] statistic = "point"` | SEG-06 |
| FS-04 | Stanza's parser batch | Stanza's own batch, one text per call. A cap is adopted only if a capped reparse of the benchmark's looping shard is byte-identical. | `stages/parse_stanza.toml [batch] depparse_batch_size = 0` | PRS-01 |
| FS-05 | Which sentence a word belongs to | The sentence holding its first letter or digit. | `stages/features_gramlex.toml [sentences] word_anchor = "first_alnum"` | GRM-04 |
| FS-06 | Whether a segment with no word enters mean sentence length | It does not. | `stages/features_gramlex.toml [sentences] count_empty_sentences = false` | GRM-04 |
| FS-07 | When a word of the outcome's unit is a name | When any of its letter- or digit-bearing syntactic words is a name. | `stages/features_gramlex.toml [lexical.names] word_rule = "any"` | LEX-09 |
| FS-08 | The unit a frequency value is averaged over | The orthographic word: a surface token's value is the mean of its content words, matched only if all are found. S3 registers this for Arabic and Hebrew; plan v3 applies it everywhere. | `stages/features_gramlex.toml [lexical.frequency] aggregation = "orthographic_word"` | LEX-01, LEX-02, LEX-21 |
| FS-09 | The unit word length is counted on | The content syntactic word, as the error-model benchmark counted it, reading "content word" from the third rule's content-word tokens. Plan v3 counts the letters of words of the outcome's unit that contain a content word, the reading Measures favours, qmd § Measures: "A word, in the processing outcome's denominator and in every per-word quantity, is a whitespace-delimited token of the text as served that contains at least one letter or digit." It also ties the length to the outcome's unit, qmd § Measures: "Mean orthographic length anchors LexicalDifficulty and helps determine how many words a text contains, since the same content in longer words needs fewer of them." The alternative value is "word". | `stages/features_gramlex.toml [lexical.word_length] unit = "syntactic_word"` | LEX-07, LEX-08 |
| FS-10 | MATTR for a text no longer than its window | The plain type-token ratio, as in the benchmarks. | `stages/features_gramlex.toml [diversity] short_text = "ttr"` | LEX-10, LEX-11 |
| FS-11 | When an MTLD factor closes | When the running type-token ratio reaches .72. Whether McCarthy and Jarvis (2010) close it on reaching or only on falling below is UNVERIFIED. | `stages/features_gramlex.toml [diversity] mtld_inclusive = true` | LEX-11 |
| FS-12 | The fewest tokens an MTLD factor may hold | None. | `stages/features_gramlex.toml [diversity] mtld_min_factor_tokens = 0` | LEX-11 |
| FS-13 | The unit MTLD is computed on | Content lemmas, the primary's unit, with MTLD over all words in the diagnostics. | `stages/features_gramlex.toml [diversity] mtld_unit = "content_lemma"` | LEX-11 |
| FS-14 | What "clause-initial" means for *so* | The benchmark's rule: sentence-initial, second after a sentence-initial quotation mark, or after a comma, semicolon, colon, dash or *and*, and not before *that*, *on*, *forth*, a degree word or an auxiliary. | `stages/features_discourse.toml [connectives] clause_boundary_before`<br>`stages/features_discourse.toml [connectives] clause_initial_blocked_before` | DSC-05, DSC-07, DSC-09 |
| FS-15 | Whether S3's hygiene rule governs the counting of the English anchors, and if so how "not X but Y" is detected | S3 states the rule within inventory induction, supp § S3: "A target form joins a class only if it occurs in at least 20 pairs." and supp § S3: "Hygiene rules block pronouns, finite verbs, names, numerals and the expressions and so on and not X but Y." Whether it also governs the counting of the English anchors is itself open. The default applies it: a coordinating *but* whose conjunct has no subject and whose head conjunct carries a negator is not counted. No benchmark implemented this. | `stages/features_discourse.toml [connectives] block_not_x_but_y = true` | DSC-06, DSC-09 |
| FS-16 | The constant of the name-token share's empirical logit | 0.5: log((k + 0.5) / (n - k + 0.5)). | `stages/features_discourse.toml [names] elogit_offset = 0.5` | COV-04 |
| FS-17 | What "mean repetitions per type" counts | Name tokens per name type. | none (`features/names.py:NameMeasures.tokens_per_type`) | COV-05 |
| FS-18 | The formula for the variability of valence and arousal | The sample standard deviation over a text's matched tokens. | `stages/features_discourse.toml [affect] sd_ddof = 1` | COV-07 |
| FS-19 | What a sentence end is in the duration formula | One per sentence of the registered segmentation; the benchmark counted runs of terminal marks. | `stages/features_discourse.toml [duration] sentence_ends = "segments"` | COV-10 |
| FS-20 | Which neighbour a punctuation-only token attaches to | The preceding word, except that an opening quotation mark (the opening mark of a quotation pair whose two marks differ), a turn-initial dash or a text-initial token joins the following word (plan v3, `text/words.py:word_extents`). Word counts never change; the surprisal stages credit a punctuation-only token's subword surprisals to the word it joins. | `stages/surprisal_goldfish.toml [text] attach_punctuation = "word_extents"`<br>`stages/surprisal_goldfish.toml [text] openers = "quote_pairs"`<br>`stages/surprisal_xglm.toml [text] attach_punctuation = "word_extents"` | TXT-03, LEX-12 to LEX-14, LEX-24 |
| FS-22 | Which parse the lexical, discourse and affect features read | Stanza's, as the error model served LexicalDifficulty and ReferentialContinuity, so that the calibration constants describe the same scores; UDPipe's lemmas serve only the agreement S3 reports. The protocol names Stanza for the name rule only and says "the parse" elsewhere. | `stages/features_discourse.toml [parse] artefact = "parses_stanza"`, with no switch in `features_gramlex`, whose lexical block always reads Stanza's parse | LEX-01 to LEX-03, LEX-07 to LEX-11, LEX-21, DSC-03 to DSC-07, DSC-09, COV-06, COV-07 |
| FS-23 | Where a word without a letter falls in dialogue share | By its first letter or digit, the word function's anchor; S3 names the first letter, so the two differ only for words with no letter. | none (`stages/features_discourse.py:run`) | COV-01 |
| FS-24 | The union segmenter's quotation-mark term (translations only) | Off, as in the benchmark, until the PI rules on the plan's admission test (scout critique, item 3). | `stages/sat.toml [union] quote_term = false` | none on the English path |
| FS-25 | XGLM-4.5B's window stride | Half its 2,048-token window, as the Goldfish rule halves 512, with the last window ending at the final token; plan v3 names no stride. | `stages/surprisal_xglm.toml [windows] stride = 1024` | LEX-14, LEX-24 |
| FS-26 | BGE-M3's input length | 512 tokens, as the benchmark and e5 truncate, although BGE-M3 reads up to 8,192. | `stages/encode_bgem3.toml [encoding] max_length = 512` | DSC-02 |
| FS-27 | CorPipe's context window | 2,560 subword tokens, the segment size of every score the model card reports, including the 79.3 S3 cites; the model's options keep the training value, 512. | `stages/coref_corpipe.toml [call] segment = 2560` | DSC-10, DSC-11 |
| FS-28 | Whether a predicted zero mention counts towards chain continuity | It does not; zero mentions are recorded either way. | `stages/coref_corpipe.toml [output] zero_mentions_in_continuity = false` | DSC-11 |
| FS-29 | How MetricX inputs are batched | Each pair padded to its own length bucket in fixed-shape batches, kept only if it agrees with one pair per forward pass on the GPU. | `stages/qe_metricx.toml [batching] mode = "buckets"` | REF-02 |
| FS-30 | When the MetricX port is admitted | It must reproduce every official score within 0.01 on the 0 to 25 scale and correlate at least .9999 with them on public pairs. | `stages/qe_metricx.toml [validation] max_abs_difference = 0.01`<br>`stages/qe_metricx.toml [validation] min_pearson = 0.9999` | REF-02 |
| FS-31 | Whether a relation subtype counts under its base relation in noun-phrase elaboration | Yes: relations are matched by their base, as in gfeat.py, so English nmod:poss (possessive pronouns such as *his* and *my* before a noun: 368 of the 461 nmod:poss relations in the GUM test file the verify-discourse benchmark downloaded) and acl:relcl (relative clauses) count as elaboration. Treebanks differ: in the rigour benchmark's UDPipe parse of German HDT a possessive is a determiner (det), left out with the other determiners. S3 lists base relations only. | none (`features/grammatical.py:base`) | GRM-05 |
| FS-32 | What counts as a letter or a digit in the word function | A letter is a character of Unicode general category L other than Lm (modifier letters), and a digit any character of category N, so other numbers such as ² or ½ make a word too, as in the error-model benchmark's `lexrules.registered_words`; a token of modifier letters alone joins the preceding word. | none (`text/words.py:is_word_token`) | TXT-03 |
| FS-33 | The SaT call settings the protocol does not register | Plan v3's stride 64, block size 512, batch size 32 and `strip_whitespace` false, which are wtpsplit 2.2.2's defaults for `SaT.split`, and `pad_last_batch` true, which is not (the library's default is false). The stage also opens every model call with a sentinel text of at least 510 subword tokens, so that blocks are always padded to full width and a text's probabilities do not depend on the texts that share its call. | `stages/sat.toml [call] pad_last_batch = true`<br>`stages/sat.toml [runtime] fixed_block_width = true` | SEG-01 |
| FS-34 | What "if line structure survives" means when titles are carried to a translation | The translation has as many pages as its English source, and the title's page as many lines as the English page as served. The alternative, "text_lines", also requires every other page to keep its number of lines. | `stages/documents.toml [titles] carry_rule = "page_lines"` | TXT-05 |
| FS-35 | How a text is halved for split-half reliability, and whether the half correlation is stepped up | None: not built. The benchmarks halved texts three ways, each stepped up with Spearman-Brown: odd and even sentences (grammatical, `pud_parallel.py`, and the XL-5 check in verify-xl's `splithalf_tinystories.py`), the first and second halves of the sentences (discourse, `rc_composite_reliability.py`) and odd and even content tokens (lexical, `b5_splithalf.py`). | none | GRM-10, LEX-25, DSC-13 |
| FS-36 | What the matched-token proportion of the predicted duration counts | None: not built. S3 asks for it as for every other measure, but the duration looks nothing up in a list; the stage writes each text's phones and phonemized words, from which the share of registered words given phones could be formed. | none | COV-12 |

### 4.2 Conflicts with the registered text

Here the value the code writes under a registered quantity's name departs from the quoted anchor. A default cannot
settle such a case: the PI either amends the protocol or has the code changed. G6's default (section 3) is of this
kind too, and GRM-03's status names both.

| id | conflict | registered text | what the code writes | switch | rows |
|---|---|---|---|---|---|
| CF-01 | The form of subordination (FS-21 in the first draft) | qmd § Materials: "the ratio of subordinate to main clauses"<br>qmd § Outcome-blind dimension reduction: "and bounded proportions with an empirical logit, wherever the transform lowers the median absolute skewness of the feature's within-language distributions over the catalogue." | `values.subordination` is plan v3's empirical logit of the subordinate share, log((sub + 0.5) / (main + 0.5)), gfeat's SUBlog, computed per parser (`features/grammatical.py:parse_features`) and averaged over the two (`features/parsemean.py:grammatical_features`). The registered ratio is written only per parser, as `subordinate_main_ratio` in the diagnostics (`features/grammatical.py:parse_diagnostics`), and its two-parser mean is not written. The transform rule reads raw values and covers counts and bounded proportions, so it gives a ratio no transform and cannot turn it into the logit. | none: `stages/features_gramlex.toml [grammatical] empirical_logit_offset = 0.5` sets only the offset, and no switch writes the registered ratio as the value | GRM-03 |

## 5. What the translations need from English

| # | English output | rows | what reads it |
|---|---|---|---|
| 1 | The normalised English text with its page offsets: the source of the page anchors, of quality estimation and of the anomaly battery's length ratio | TXT-01, TXT-02, REF-02, CHK-01 | qmd § Sensitivity analyses: "Translation quality is estimated for every translated page against its English source by MetricX-24 in its reference-free mode"<br>qmd § Outcome-neutral quality checks: "A registered anomaly battery checks every text for language identity, an extreme length ratio to its English source, repeated loops, unknown characters and script purity." |
| 2 | English sentence ends, their page anchors and their non-space lengths, and each text's counts of sentences and terminal marks, for the union projection, the floor, the merge rate and the ratios to the source | SEG-01, SEG-02, SEG-03, SEG-08 | qmd § Materials: "Its sentence boundaries decide where a translation's sentences end wherever the translation marks no end itself, as set out above."<br>supp § S3: "For every text, we will report the ratios of its sentences and of its terminal marks to those of its English source, with their median, interquartile range and share within 10 per cent." |
| 3 | English word counts and the catalogue median, for English-equivalent words and the story unit | TXT-09, TXT-10, TXT-11 | qmd § Sampling plan: "Each language's word count is converted by the ratio of its catalogue's words to the English words of the same stories." |
| 4 | Titles identified on the English source, carried by line index | TXT-05 | supp § S3: "A title is the first line of a text or page if it has at most eight words and no sentence-final mark. Titles are identified on the English source and carried to each translation by line index if line structure survives." |
| 5 | The Stanza English parse: names for route B, pronoun subjects for the dropped-subject gate, connective anchor flags, and the CoNLL-U CorPipe reads | PRS-01, COV-03, DSC-04, DSC-09, DSC-10 | qmd § Materials: "A type is also a name if word alignment projects it from a name in the English source, where the alignment covers at least half of that source's names." |
| 6 | CorPipe chains, projected through word alignment | DSC-10, DSC-11, DSC-12 | qmd § Materials: "Its coreference chains, resolved in English and projected onto the translation by word alignment, mask a sensitivity overlap anchor computed on the served text (Sensitivity analyses)." |
| 7 | Dialogue spans, the English dialogue share and each sentence's speech status, for the two dialogue gates and the fallback | COV-01, COV-02 | qmd § Outcome-neutral quality checks: "Dialogue share keeps its served-text value where it correlates at least .80 with the English source's value."<br>qmd § Outcome-neutral quality checks: "The reported-speech rule keeps the translation's own speech spans where their agreement with the English source reaches a kappa of .70." |
| 8 | English valence and arousal means, the fallback for a language without an admitted affective measure | COV-06 | qmd § Materials: "Because the affective covariates enter every model, a language without an acceptable affective measure takes them from the English source text of the same version." |
| 9 | The English rare-word share, for the inflection diagnostic | LEX-02 | supp § S3: "An inflection diagnostic is therefore computed on the translated benchmark before submission and on the catalogue's fixed sample after acceptance, and it is reported beside the lexical slopes." |
| 10 | English covariate values, for the ninth family's last refit | TXT-09, COV-01, COV-04, COV-05, COV-06 | qmd § Sensitivity analyses: "A last refit enters the English-source values of the covariates beside the served-text values and adds name types per hundred words." |
| 11 | e5 embeddings of English windows and pages, for the sentence aligner and the adequacy covariate, computed per pair and not stored | REF-03, DSC-01 | qmd § Outcome-neutral quality checks: "A registered sentence aligner pairs the two on a fixed sample of 2,000 story versions per language, chosen from the story identifiers by a rule fixed in advance, so that every run draws the same versions." |
| 12 | English component scores: proxies for failed components, the two-stage instrument and the agreement and known-groups tables | CHK-03, CHK-02 | qmd § Confirmatory models: "It enters instead as an adjustment, through the language's own failed score and the English-source score of the same story version." |
| 13 | The English page count, the parallel-page anchor | TXT-12 | qmd § Materials: "Where pages are parallel, the search runs page by page, so a page break ends a sentence exactly when it does in English." |
| 14 | The keyed order of the story identifiers, from which each language's keyed samples are cut | REF-01 | qmd § Outcome-neutral quality checks: "chosen from the story identifiers by a rule fixed in advance" |

Notes.

- Output 5. Per-sentence pronoun-subject flags are computed in `features_discourse` but only their aggregate is
  written; the dropped-subject gate needs them written per sentence, as COV-02 needs speech status.
- Outputs 5 and 6. Word alignment (multilingual BERT, layer 8, ArgMax, after SimAlign) is translation-side. It is
  promoted from the names benchmark as `reference/align.py:Aligner.align`, configured in
  `stages/coref_corpipe.toml [aligner]`; the rules built on it wait for P06 and P53. The aligner uses the cased
  multilingual BERT, `google-bert/bert-base-multilingual-cased@3f076fdb1ab6` (the benchmark's), whereas UDPipe 2
  embeds with the uncased model (PRS-02); the model lock holds both.
- Output 11. The vecalign-cost aligner and its admission at one-to-one precision of .95 (P41) are translation-side.
- Output 14. The order is the same in every language, because the hash reads only the story identifier, but a
  language's sample of n is the first n stories of its own set, so samples coincide only where story sets do
  (REF-01).
- Two translation-side rules were registered on 3 November 2026 (`ISSUES.md` FP-11). Serbian is
  transliterated to Latin by the CLDR 47 Serbian-Latin-BGN transform after NFC, and its parse, frequency lookups and
  connective induction read the transliteration, with each token mapped back to the served text by character
  offsets (supp § S3, the fifth script rule). The Serbian frequency lists are built from subtitles transliterated the
  same way. In Kazakh, every component is treated as below the reliability floor, because its reliability cannot be
  estimated (qmd § Outcome-neutral quality checks), so Kazakh's scores feed only the partial-inclusion adjustment.
  The transliteration is built and tested (`text/sr_translit.py`, against `config/cldr/cldr47_Serbian-Latin-BGN.xml`)
  and is wired into the stages when the sr-rs locale joins `languages.toml`. The Kazakh rule acts in the
  calibration run after acceptance, which applies the floor, so this package only computes Kazakh's scores.

## 6. Stage map

| stage | device, environment | reads | writes | rows |
|---|---|---|---|---|
| documents | CPU, core | `--input` table in the catalogue's schema, behind the catalogue lock | documents | TXT-01, TXT-02, TXT-03, TXT-05 to TXT-08, REF-01 |
| sat | GPU, core | documents | segments | TXT-03, SEG-01 to SEG-03, SEG-08 |
| seg_check | CPU, core | documents, segments | `_checks/seg_check.json` | TXT-03, SEG-03, SEG-04, SEG-06, SEG-07 |
| parse_stanza | CPU, core | documents, segments | parses_stanza | TXT-04, PRS-01 |
| parse_udpipe | GPU, udpipe | documents, segments | parses_udpipe | TXT-04, PRS-02, PRS-03 |
| features_gramlex | CPU, core | documents, segments, parses_stanza, parses_udpipe | features_gramlex | TXT-03, TXT-09, TXT-12, TXT-13, PRS-04, GRM-01 to GRM-06, LEX-01 to LEX-03, LEX-07 to LEX-11, LEX-21, COV-03 |
| features_discourse | CPU, core | documents, segments, parses_stanza | features_discourse | TXT-03, DSC-03 to DSC-07, DSC-09, COV-01, COV-03 to COV-07, COV-10, LEX-20, LEX-21 |
| surprisal_goldfish | GPU, core | documents | surprisal_goldfish | TXT-03, LEX-12, LEX-13, LEX-15, LEX-24 |
| surprisal_xglm | GPU, core | documents | surprisal_xglm | TXT-03, LEX-14, LEX-15, LEX-24 |
| encode_e5 | GPU, core | documents, segments | encode_e5 | DSC-01 |
| encode_bgem3 | GPU, core | documents, segments | encode_bgem3 | DSC-02 |
| coref_corpipe | GPU, corpipe | documents, parses_stanza | coref_corpipe | DSC-10, DSC-11 |
| qe_metricx | GPU, core | `--input` page pairs | qe_metricx | REF-02 |
| aggregate_timing | CPU, core | every `_timing` record of a run | `_summary/timing.tsv` and `timing.json`: throughput and a projection of each stage's cost to the English catalogue | none |

aggregate_timing measures cost only and computes no registered quantity. These parts of the registered inventory have
no stage in the fixed list:

- catalogue-level aggregates: the median word count and the conversion to English-equivalent words (TXT-10,
  TXT-11), the long-unit share (PRS-05), the subordination correlation (GRM-07), the surprisal correlations (GRM-09),
  the classic-generated comparison (LEX-16), the agreement across resources (LEX-22), the correlations of LEX-20 and
  the duration's correlations (COV-11);
- split-half reliability (GRM-10, LEX-25, DSC-13), which needs per-sentence and per-token values that
  `features_gramlex` and `features_discourse` do not write, and a halving rule (FS-35);
- the anomaly battery (CHK-01), which should run before parsing;
- the second Stanza package (PRS-06), which could be an option of parse_stanza.

Per-text values that a fixed stage could write but does not yet: each text's terminal marks (SEG-08, in sat), its
letters (TXT-14, in features_gramlex), the frequency means without the name exclusion (LEX-20, in features_gramlex),
each sentence's speech status and pronoun-subject flag (COV-02 and output 5, in features_discourse) and the
duration's matched tokens once FS-36 is decided (COV-12). An aggregation stage run after the per-text stages is left
for the next draft.

## 7. Checklist: the scout's inventory against this specification

The scout's inventory of 2 November 2026 (sections 1a to 1e) was the checklist. Its row ids map as follows.

- Text layer: T1 TXT-01; T2 TXT-02; T3 TXT-03; T4 TXT-05; T5 TXT-09; T6 TXT-09, TXT-10, TXT-11; T7 TXT-12, TXT-13;
  T8 TXT-07; T9 COV-01, COV-02; T10 COV-03, COV-04, COV-05; T11 COV-06, COV-07, COV-08; T12 COV-10.
- Segmentation: S1 SEG-01; S2 SEG-03; S3 SEG-06; S4 SEG-07, SEG-08.
- Lexical: L1 LEX-01; L2 LEX-02; L3 LEX-03, LEX-04, LEX-05; L4 LEX-12, LEX-24; L5 LEX-13; L6 LEX-14; L7 LEX-15,
  LEX-16, LEX-23; L8 LEX-07, LEX-08; L9 LEX-09; L10 LEX-10, LEX-11; L11 LEX-17, LEX-18, LEX-19; L12 LEX-20; L13
  LEX-06.
- Grammatical: the scout's G1 PRS-01; G2 PRS-02; G3 PRS-04; G4 to G8 GRM-01 to GRM-05; G9 GRM-06, GRM-07, PRS-05;
  G10 PRS-06, PRS-07; G11 PRS-08.
- Discourse and references: D1 DSC-01; D2 DSC-02; D3 DSC-03; D4 DSC-04; D5 DSC-05, DSC-06, DSC-07; D6 DSC-08; D7
  DSC-09; D8 DSC-10 to DSC-12; D9 section 5; Q1 REF-02; Q2 REF-03; Q3 to Q5 REF-01 and section 5; Q6 CHK-01; Q7 to
  Q9 PRS-07, CHK-02, CHK-03 and the split-half reliability of the quality table, GRM-10, LEX-25 and DSC-13.

Rows the scout's inventory did not list, found on re-reading the protocol: TXT-04, TXT-06, TXT-08, TXT-14, TXT-15,
SEG-02, SEG-04, SEG-05, PRS-03, GRM-08, GRM-09, LEX-21, LEX-22, COV-09, COV-11 and COV-12.

The scout's L7 also lists the entropy, the within-text standard deviation and surprisal per character. The protocol
registers none of them, so they have no row; the surprisal module writes them to its diagnostics as plan v3's
descriptive extras (LEX-15).

Out of scope here: the benchmarks run before submission on public data (among them the MECO check, P49; the TED2020
inventory, P52; the name-rule selection, P06; the dialogue-detector validation, P54), the dimension reduction, the
calibration and every model fitted after linkage.
