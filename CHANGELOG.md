# Changelog

This file records notable changes to the code, documentation and generated artefacts in this
repository, in the format of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Earlier
changes are recorded only in the git history and in the dated protocol drafts under
`preregistration/` and `preregistration/drafts/`. Any change that could alter a reported number must be entered here with its
date and rationale.

## [Unreleased]

### 26 October 2026: story texts in every language

No reported number changes. The data controller exported the stories in every language directly
from the app's content, as two zip files with one plain-text file per story and language.

- `story_texts/extract_story_texts.py` (version 2026-10-26) reads the zip files as well as the
  viewer of 1 October, which it still reproduces byte for byte. It writes one compressed table
  per language, gives each story the Story ID the viewer gave its English text, and decodes the
  `\n` that the export writes for a line break inside a page. It reads the zip files through a
  memory map, because on the machine that ran it a file seek was occasionally ignored, which
  zip's own checks caught as unreadable archives. English is extracted first and the other
  languages in parallel processes.
- `story_texts/data/` now holds 21 languages, 770,854 texts in all, from this delivery. Nineteen
  hold all 40,559 stories; Czech holds 132 and Slovak 101. The tables take 362 MB, the largest
  23 MB. The English table is replaced by the 26 October export, so that every language comes
  from one extraction. Its texts match those of 1 October in 40,539 stories once the line-break
  escapes are decoded: 8 have lost the empty page the viewer showed in them, and 12 were edited
  in between (see `preregistration/README.md`).
- `anomalies.csv` lists the new delivery's unusual texts, among them six Hebrew texts that repeat
  a few words hundreds of times, 23 translated texts whose first line is a page marker in
  place of a title, and 39 texts whose page count differs from that of the same story in
  English, six of them the Hebrew texts. The structure checks count pages, lines and repetition only, and compute no
  linguistic feature.
- `story_texts/publish_story_texts.py` checks each compressed table and copies it byte for byte.
  Tables are now compressed at xz preset 6, which on a 30 MB sample came within 3 per cent of
  preset 9 in size, at the same speed and about a seventh of the memory.

### 19 October 2026: the classic stories' authorship

No reported number changes. The data controller has answered question (j): the classic stories
were created with the same generative model as the other stories and translated in the same way.

- Table 2 and the C4 paragraph of the protocol, and Supplementary Section S7, record that the
  answer rules out C4's condition, so C4 will not be run. The generated-or-classic indicator
  stays a covariate.
- Materials describes the classics as a fixed set the same model wrote from public-domain tales.
  The rationale for the registered surprisal comparison of classic and generated texts, in
  Sensitivity analyses and Supplementary Section S3, now rests on the classics echoing the tales'
  wording, which the surprisal model's training corpus may contain. The analysis is unchanged.

### 18 October 2026 (evening, later): English story texts published

No reported number changes. The rights holders, Ferrero International and Gameloft, agreed to
the texts' release under CC BY-NC 4.0, so the exclusion of 1 October below gives way to a
published, checked form.

- `preregistration/story_texts/data/en-us/stories.csv.xz` holds the 40,559 US English texts, one
  row per story, exactly as extracted, xz-compressed to 17 MB. `anomalies.csv`, the extraction
  record and a manifest with the checksum of every file sit beside it. The pages table is not
  published, because the text column carries the same pages with their markers.
- `story_texts/publish_story_texts.py` writes `data/` from the extraction, one table per
  language, and checks it. The Check workflow runs the check on every push. The texts in the
  app's other languages will be added in the same form as they are delivered.
- The published extraction record leaves out the data controller's path to the folder it built
  the viewer from. The delivery as received, with the viewer, and the open-items tracker stay
  on the local disk, still excluded by `.gitignore` and `tools/confidential.txt`.
- `tools/guard.py` allows each compressed table up to 50 MB, below GitHub's warning, and keeps
  the 10 MB limit for every other file. `.gitattributes` stores `data/` byte for byte.
- The protocol's Data availability statement, its Code availability statement and the cover
  letter say that the English texts are public, and the licence files name the rights holders.

### 18 October 2026 (evening): attempt and warning counts pooled, funding acknowledged

No reported number changes.

- `design_analysis/precision_sweep.csv` gains four columns at the end: the Monte Carlo standard
  error on each decision probability, and the number of fits attempted and of fits that raised
  warnings (CR-04). The table was rebuilt from the cached sweeps, with no new simulation, and its
  other twenty columns are unchanged. The poster's frozen copy keeps the table as printed, and
  matches the new one in every column it has. Supplementary Section S5 now points to the pooled
  table for these counts.
- `README.md` acknowledges the funders in a section of its own.

### 18 October 2026 (later): held-back figure and record fixes applied, citation completed

No reported number changes. Figures 1, 2 and 3 and the supplementary precision panels change
in presentation only, and reach a rendered draft at the next render.

- Figure 1: the legend names the groups Concept and Intersection, where it showed the package's
  internal column name, grp (FL-03).
- Figure 3 and the supplementary panels: the panels are tagged a and b, as the captions call
  them (FL-24).
- Figure 2: the dashed moderation lines are darker, at 3.52:1 against white, and meet the 3:1
  floor (TH-29).
- Theory object: `formal_model.spec_ref` names `design_analysis/tier1_developmental.json`, a
  file that exists. Every theory output is unchanged and the score stays at 90.7 (DA-22).
- Search record: `scopus_gap_analysis.R` writes the trend queries into the record, and the
  archived record of 26 August 2026 gains them from the archived counts, with no new search
  (FL-05).
- Supplementary Section S5 states that the simulated outcome's standard deviation is 1.01 to
  1.02, which made the simulated test slightly stricter than the registered criterion (DA-29).
- `CITATION.cff` carries the authors' ORCID iDs. Dependabot's update of
  `actions/upload-artifact` to 7.0.2 was merged after the checks passed on it.

### 18 October 2026: folders grouped, checks on every push, releases archivable

No reported number, table or figure changes. Rendered before and after the moves with a fixed
`SOURCE_DATE_EPOCH`, the protocol and supplement PDFs and HTML files are byte-identical.

- Layout: the 32 superseded protocol drafts are in `preregistration/drafts/`, with a copy of the
  Quarto libraries their HTML loads, and the current draft stays in `preregistration/`. After a
  render writes a new draft, `_rename-output.R` moves the one it supersedes into `drafts/`, and
  it never overwrites an archived file. The citation styles, the Lua filter and the title partial
  are in `preregistration/layout/`, as the poster's build files are in `poster/layout/`, and
  `mindmap/source files/` is now `mindmap/source/`.
- Checks: the Check workflow runs `check_reported_numbers.R` and
  `theory/check_manuscript_claims.R` with their packages restored from
  `preregistration/renv.lock`, lintr 3.4.0, the link and citation-key checks in `tools/`, a
  `CITATION.cff` schema check and the count-script scenarios on Python 3.8 and 3.13.
  `count_script/tests/check_expected.py` compares the scenarios' outcomes with the reports
  recorded in `tests/expected/`.
- Guard: `tools/guard.py` refuses a change to a frozen file (`tools/frozen.txt`) and the
  addition of a confidential or oversized one (`tools/confidential.txt`), in a pre-commit hook
  enabled with `git config core.hooksPath .githooks` and in the Guard workflow on every pushed
  commit.
- Render workflow: R 4.6.1 and Quarto 1.10.19 are pinned, the render is offered as a download,
  and it is committed only when the run is started with "commit" ticked.
- Citation: `CITATION.cff` gives the repository's citation, and a pushed tag starting `v` or
  `stage` publishes a GitHub release for Zenodo to archive under a DOI.
- Poster: the two CRAN entries in `poster/data/references.bib` name the Comprehensive R Archive
  Network (CRAN), so the README's generated reference list keeps the wording added on `main`.
- Drafts: eleven drafts of 17 June to 29 July 2026, rendered on the `code-based-diagram`
  branch and never on this line, are archived in `preregistration/drafts/`. That branch, two
  superseded branches of Riddhi's and six merged or superseded ones were deleted on GitHub.
- Protocol: the Priors paragraph cites Lewandowski et al. (2009) for the LKJ prior, so the next
  rendered draft gains one reference.

### 17 October 2026 (later): licence, and the simulation, figure and theory code hardened

No reported number, table or figure changes. A library restored from
`preregistration/renv.lock` reproduced every output byte for byte, and the PDFs pixel for pixel.

- Licence: the code is under the MIT licence (`LICENSE`, copyright the University of Oxford) and
  everything else under CC BY-NC 4.0 (`LICENSE-content.md`, copyright the InTRACt authors), which
  also lists the third-party files kept under their own licences. `mindmap/source
  files/node_modules` is no longer tracked, since `npm ci` rebuilds it from the lockfile.
- Design analysis: the functions the scripts share are in `design_analysis/helpers.R`. Each cached
  sweep has a key file recording the settings that produced it, and a run with other settings
  stops instead of reusing it. Settings read from the environment are validated, the secondary
  sweeps' 120 replicates became a setting (`INTRACT_N_SIMS_2`), and the focal effects are read
  from the specifications. A curve that reaches the target but cannot be solved is reported as not
  determined, where it used to be reported as not reached. A freshly computed sweep is passed on
  as read back from its file, so a fresh run and a cached run write identical tables, and a
  session record is written only by a run that computed something. The ordinal script records why
  each failed replicate failed, then runs `summarise_ordinal.R`, which alone writes the ordinal
  tables.
- Environment: pilotr fits with lme4 but only suggests it, so the lockfile, built from the
  scripts' own dependencies, had left lme4 out and a fresh simulation from a restored library
  failed. The simulation scripts now check for lme4 by name, and `preregistration/renv.lock`
  includes it and its dependencies (98 packages).
- Figures: the precision figure checks the CSV against its panel subtitles, and checks every
  panel before saving either figure, at the narrower of the journal's column width and half the
  protocol's text width. The Scopus figures stop on a missing value, on short names that match no
  archived query and on any failed check but the redundant-encoding one. The script for Figure 2
  checks its print size, 6.23 point at the protocol's width, and its colour contrast: the dashed
  moderation lines, at 2.86:1 against white, fall short of 3:1 and are reported.
- Scopus counts: `literature/scopus_gap_analysis.R` checks the counts for coherence before
  archiving them, matches the trend queries by their whole strings, and draws the figures through
  `replot_scopus_figures.R`. It was verified without the API, with its three calls replaced by the
  archived counts, which it reproduced apart from the run date.
- Theory: `build_theory.R` exits with an error if validation, the rigour checklist's gate or
  acyclicity fails, and an error while it writes the report now reaches the console.
- `preregistration/README.md` documents the cache keys, the new settings, the order of the ordinal
  steps and the retention of every dated draft, and `ISSUES.md` records what this pass resolved.

### 15 to 17 October 2026: poster, languages, variance sensitivity, merge into main, lockfiles and style

No registered threshold changes. The protocol gains a sensitivity analysis of its design-analysis
requirements, and every output rebuilt in this period was compared with the committed one.

- Poster: a conference poster, its source and the data behind its figures are in `poster/` (15
  October). Two superseded drafts were removed, the build files moved to `layout/`, the
  bibliography to `data/` and the preview to `img/`, and the folder now builds without
  `../preregistration/`. Both PDFs re-render pixel for pixel.
- Design analysis: the 9 per cent of variance between texts and the 20 per cent between children
  are stated as assumptions and compared with published decompositions of children's reading
  rates. `design_analysis/run_variance_sensitivity.R` re-derives the tier-1 requirements at text
  shares of 5, 13 and 20 per cent (Supplementary Section S5). The 20 per cent sweeps ran on the
  university cluster, where a re-run of the 5 per cent sweeps reproduced the local ones exactly.
  The ordinal model's latent-scale shares and placeholder thresholds are stated, and the grid
  choices in `run_design_analysis.R` are explained.
- Languages: the protocol registers every language the app offers, 19, with resources and script
  rules for the nine beyond the structural sample (Supplementary Table 4, so the later
  supplementary tables are renumbered) and placements by orthographic depth.
- The data controller's October answers are applied: the narration flag is treated as
  availability, so Hypothesis 4 is an intention-to-treat comparison, the age band is
  family-reported, the texts outside English are machine translations, and the English texts are
  held. The acknowledgements, competing interests and cover letter name Ferrero International and
  the John Fell Fund as funders.
- Repository: the protocol branch was merged into `main` on 17 October. The thirteen publisher
  PDFs from a Zotero library and the link to the private literature-review repository are no
  longer tracked, and both remain in history. `main`'s render workflow now runs only when started
  by hand, because on every push it re-rendered the protocol on the runner and committed the result
  over the draft rendered and checked locally.
- Environment: `poster/renv.lock` and `preregistration/renv.lock` pin every R package. pilotr,
  theoryforge and scopusflow, previously installed from local builds, are taken from CRAN at the
  same versions. The CRAN release of pilotr 0.3.0 differs from the local build only in functions
  the scripts never call. Libraries restored from the lockfiles reproduced the poster pixel for
  pixel, and every table, figure and theory output of the protocol that does not need the Scopus
  API or a fresh simulation.
- Figures: the protocol's PNG figures name `ragg::agg_png`, because `ggsave()` otherwise falls back
  to a device that rasterises text differently when ragg is absent. The PNGs are unchanged.
- `design_analysis/precision_sweep.csv`, and its copy under `poster/data/`, was regenerated from the
  cached sweeps. Its last column is no longer quoted, and every value is unchanged.
  `session_info.txt` was kept as the record of the September simulations.
- Style: `.lintr.R` records the R style, and every R script passes with no lints. The edits change
  layout only, and every edited file parses to the same code.

### 1 October 2026: story texts received and made readable by script

The data controller delivered the story texts as StoryReview, a browser viewer that shows one
story at a time. No reported number changes.

- `preregistration/story_texts/extract_story_texts.py` reads all 40,559 texts out of the viewer's
  data files and writes one table of stories, one of pages, a list of structurally unusual texts
  (16) and a record of every file read with its checksum. It stops without writing anything if
  the files are incomplete or its page and word counts disagree with the viewer's. Tested on the
  delivery and on synthetic viewers with a wrong word count, a missing chunk file and a broken
  wrapper.
- `.gitignore` excludes `preregistration/Oxford-40k-stories/`, the delivery and the script's
  outputs, because the texts are the data controller's property and this repository is public.
  The auto-sync commits untracked files, so without the exclusion it would have published them.
- Every text in the delivery is US English. The structural sample shows readings in ten
  languages.

### 25 September 2026 (later): count script assessed, priors aligned, open literature items closed

No further request can go to the data controller before submission, so the count script it has
held since 18 September 2026 (version 2026-09-17) was assessed against every use the protocol
makes of the provider-computed counts. No revision is needed. Only the revised version counts
account identifiers in scientific notation, a count two rules read, and the data controller holds
that version. Otherwise both versions write every count the protocol draws on. The revised version
reproduces the first on the 35-row sample (apart from the run date, its version number and
seventeen added rows), and both test suites in `count_script/tests/` pass when given absolute
script paths. `check_reported_numbers.R` exits 0. A five-lens verification (evidence, whole-document
consistency, count-script claims, priors, prose), each lens challenged by a second reviewer,
corrected the edits below before rendering.

- Count script and decision sources: the protocol gives the date the revision was sent, says where
  the two versions differ, and says the data controller has been asked to run the revision. The
  manifest is described as what it is, the script's record of each file read, with the build date
  and window coming from the certification. The identifier rule no longer presupposes a new
  request, because the revised script itself flags account identifiers in scientific notation and
  asks for a re-export, and it now also appears among the grounds for declaring a hypothesis
  untestable. The audit of the frozen extract and the output of the prior-derivation pipeline are
  named among the inputs to registered decisions. The Account rule is applied to the tier-1
  sample as the audit counts it, because the provider-computed sessions per account apply no
  tier-1 exclusion except the age bands. A switch in narration activates the contingent
  requirement only when the revised script finds no account identifier in scientific notation.
  Supplementary Section S8 no longer claims that every sample-table entry can be regenerated
  from the script's output, and its country row is corrected (Poland 5, not 4).
- Priors: derived priors are restricted to the three component main effects on reading time,
  wherever at least two papers report a standardised regression coefficient. The frozen rules
  translate no pooled estimate to the cumulative-logit scale of Hypothesis 5 or the within-child
  unit of Hypothesis 6, so those coefficients keep weakly informative priors, as do narrativity,
  valence and arousal, to which the rules map no evidence. The freeze is described as it
  happened: rules first committed in August, last revised on 16 September, after test extractions
  from 12 papers in June. The sixth design adjustment compares absolute pooled values, the
  alternative-pooling refit that the frozen rules pre-specify is registered, and a rule covers a
  prior table delayed by the review. The frozen rules are deposited verbatim as
  `preregistration/priors/prior_derivation.md` (the review's working copy of 16 September 2026,
  not yet committed there, LF endings, SHA-256 and provenance in the README).
- Orthographic depth: Polish is annotated at Seymour et al.'s middle level (Awramiuk and
  Krasowicz-Kupis 2013; Schüppert et al. 2017) and Korean as shallow in the reading direction
  (Lee et al. 2023; Leachman et al. 2025), both fixed with the feature inventory. The
  collaborator's search for a Korean classification is no longer needed.
- Korean length: the account of Ju et al. 2022 and Pae et al. 2020 in the 25 September entry below
  overstated them. With frequency modelled, neither jamo nor block length had a main effect, and
  the adult null confounds the two counts. Jamo remain the unit, now on the ground of
  comparability with the other languages' letter counts, and the counting convention is stated.
- Norms: Korean concreteness rests on one set of 450 nouns, and its valence and arousal sets hold
  252 to 450 words. Both Greek affect sets are named, and both were rated by native speakers. French
  has native age-of-acquisition sets restricted by word length, and the larger is now put to the
  token-coverage rule instead of being excluded by assertion.
- Wording: the Bruner et al. measure (mean log word frequency), the Kruchinina et al. signature
  (at most partial at 6 to 7), the splitter-agreement sample (the sixth check's 50 texts) and the
  per-doubling conversion for Hypothesis 6. The justification record
  `literature/evidence_notes.md` is corrected inline on the Korean and Greek norms, and the
  Kruchinina et al. title takes the en dash Crossref records.
- New sources, all DOIs checked against Crossref except the three without one (Schüppert et al.
  2017, Park 2004, Lee et al. 2022): Awramiuk and Krasowicz-Kupis 2013, Łockiewicz and
  Ciecholewska 2017, Dębska et al. 2019, Lee et al. 2023, Perfetti and Verhoeven 2017, Gorman et
  al. 2020, Hong et al. 2016, Lee and Shin 2023, Tae et al. 2026, Palogiannidi et al. 2016, Vaiouli
  et al. 2023, Dimitropoulou et al. 2009, Lachaud 2007. Leachman et al. 2025 and Ferrand et al.
  2008 were in the bibliography uncited, and the former's truncated title is corrected.
- Cover letter: "sizing" removed, the decision sources and conditional post-fitting rules stated
  as the protocol states them, the timeline aligned with the protocol's, the code described as
  public from submission, and a bracketed alternative for a certification still unsigned.

### 25 September 2026: pending decisions resolved from the literature and the data

The inconsistencies that the language pass surfaced were resolved and each choice motivated in
the text. `check_reported_numbers.R` exits 0, and Tables 1 and 2 keep their landscape pages (77
pages). New sources were checked against Crossref and, where a claim rests on them, against the
paper: Fieller 1954 and von Luxburg and Franz 2009, Matuschek et al. 2017, Gathercole et al. 2004,
Staub 2026, Schuurman et al. 2016, Wang et al. 2019, Ju et al. 2022 and Cheung 2019 (added to the
bibliography with Borenstein et al. 2009 and Li et al. 2019), and Barr et al. 2013 and Futrell et
al. 2015 (already there). Lahoud et al. 2023 is no longer cited.

- Rules that change: accumulated reading for Hypothesis 6 is counted in story units, split into
  the account mean and the deviation, and both are divided by the within-child root mean square
  per language, so the coefficient is per within-child standard deviation as simulated; session
  order enters as its logarithm, which leaves the term identified by story lengths. Concreteness
  and age of acquisition, which have no admissible uniform resource, are left out of the pooled
  lexical solution and enter the language-specific solutions and a pooled sensitivity solution.
  Korean word length is counted in jamo, with blocks as a check (Ju et al. 2022). The
  language-slope simplification order is continuity, lexical, grammatical. The permutation check
  scores maximum-likelihood refits by the Wald interval. A supplied audio duration replaces the
  predicted one only if it covers every eligible text. Account identifiers are to be exported as
  text, with a registered consequence if they still cannot distinguish accounts. Contingent
  hypotheses can be activated by the provider-computed counts for the narration-states
  requirement.
- Rules described accurately that were misdescribed: the Hypothesis 4 precondition (posterior
  criterion only, with the reason), the ReferentialContinuity anchors (four), the two untested
  interaction terms, the three Hypothesis 6 covariates, the pilot's two design inputs, timed-out
  sessions (absent if unfinished, censored if capped), the prior-derivation rules in S6 (now
  those frozen in the review's `prior_derivation.md`: one primary estimate per paper, metric
  families kept apart, an age-restricted primary pool) and the null-condition error rate (at most
  2 of 120 replicates).
- Literature claims corrected against the papers: the reading systems framework, the scope of
  the word-length evidence (Kuperman et al. 2024 covered Greek and excluded Korean), Kruchinina et
  al. 2026, the ages of the Tortorelli, Tucker and Koriat samples, the adult basis of the capacity
  account, and the evidence on shallow processing.
- `theory/make_figure1.R` is now `theory/make_nomological_net.R`, writing
  `figures/nomological_net.*`; the Scopus script and record say "search" in place of "sizing".

### 24 September 2026: language pass on the protocol and the supplement

No hypothesis, threshold, number or registered rule changed, `check_reported_numbers.R` exits 0,
and Tables 1 and 2 keep their landscape pages in the render (75 pages). Counted as whitespace
tokens of the `.qmd` sources, the protocol fell from 29,804 to 28,926 and the supplement from 9,295
to 8,978. The share of main-text sentences over 35 words fell from 25.5 to 3.5 per cent (mean
26.4 to 21.2 words).

- Engineering and Claude-dialect register removed. Criteria no longer "bind", diagnostics no
  longer "fire" and simulations no longer "price" a coefficient; "carries" (65 uses), "beside"
  (41), "gate" (18) and "The first is ..." scaffolding (32) are gone or rare. The interpretive
  sense of "reading" is now "interpretation", as in Table 1's column head. "The recording" is
  "the audio", since question (a) asks whether the voice is recorded. The Hypothesis 4 gate is
  "the Hypothesis 4 precondition", and Koriat's framework is "the cue-utilisation approach",
  distinct from the Hypothesis 3 rival.
- The heading "What is not yet settled, and what follows from each answer" is now "Questions
  outstanding at submission", Table 2's column heads are "Open question", "Bearing on the design"
  and "Decision rule for each answer", S4 is "The literature search" and now gives the three
  Scopus concept-set expressions, and the precision-figure caption is plain.
- Order: the reading systems framework and the three components now open the evidence review,
  the paragraph coupling Hypotheses 2 and 3 follows Hypothesis 3, and the two protocol-wide
  conventions moved from Ethics information to Data provenance.
- Places where the text misdescribed its own rules now describe them as registered: the
  convention on post-fitting decisions and the list of post-fitting rules under Decision rules;
  the Hypothesis 4 precondition, stated by its operational criterion (fewer than 5 per cent of
  draws inside the region); Bayes factors reported under the derived priors and their halved and
  doubled scales, the refits Priors registers; "before any outcome data existed" and "before any
  data were seen", now "before we had any access to outcome data"; the constraints on generality,
  which now name the generated stories; four Table 2 pointers; families, not children, as the
  choosers of story, level and narration; and Code availability, which now lists the
  Bayes-factor recomputation.

### 24 September 2026: the decision rule gains a Bayes-factor criterion; abstract in plain language

The analytic plan was checked against Nature Human Behaviour's Registered Report guidelines,
which name a Bayes factor of 10 as the evidence threshold for Bayesian plans and allow a
maximum feasible sample where inconclusive results would still matter. Under the registered
weakly informative priors, the posterior criterion for a non-negligible verdict (fewer than
5 per cent of the posterior inside the region) corresponds to an interval Bayes factor of
only 1.5 for a main effect and 3.2 for an interaction at its boundary, whereas the
equivalence criterion (95 per cent inside) corresponds to a Bayes factor above 100. The
rule therefore now takes the stricter criterion on each side: a non-negligible verdict
also requires an interval Bayes factor of at least 10, computed as the ratio of posterior to
prior odds of the two regions from the reference (weakly informative) refit, and the
equivalence verdict keeps the posterior criterion. The Hypothesis 4 contrast keeps its own
posterior criteria, with the Bayes factors of its constituent interactions reported beside
it. Because the Bayes factor is computed under the reference prior, a review-derived prior
centred on the prediction never supplies the evidence that confirms it, which replaces the
earlier answer to the circularity question under Priors.

- `design_analysis/solve_at_bf10.R` prices the new criterion from the archived curves by a
  normal approximation (calibration against the simulated probabilities within 0.06 at every
  grid point, written to `sweeps/bf10_calibration.csv`) and writes `minimum_texts_bf10.csv`.
  At 0.90 the binding requirements are about 930, 930 and 940 distinct texts for the three
  main effects (simulated posterior-criterion figures: 738, 660, 634), about 1,470 and 1,480
  for the two age-band interactions, about 1,470 for the narration interaction and about 810
  children in tier 2; at 0.95, 1,120, 1,120 and 1,130 texts, 970 children, and the
  interactions not reached within 1,600 texts. Table 1 and the Design and precision analysis
  quote these beside the simulated figures, and `check_reported_numbers.R` gates them.
- Twelve Crossref-verified methodological sources added (Morey and Rouder 2011; Klugkist,
  Kato and Hoijtink 2005; Linde et al. 2023; Campbell and Gustafson 2023 and the 2021
  arXiv reply; Schönbrodt and Wagenmakers 2018; van Doorn et al. 2023; Heck et al. 2023;
  Lakens et al. 2020; Rouder, Haaf and Vandekerckhove 2018; Hoijtink et al. 2019; Kelter
  2025; Schad and Modrák 2026); Kruschke 2018, already in the bibliography, is now cited.
- The abstract no longer uses "posterior", "crossed-effects" or "region of practical
  equivalence"; it names the three text properties in plain words and judges each
  association against a pre-set smallest effect of interest (149 words).

### 24 September 2026: anonymised title page, one home per registered rule, supplement de-duplicated

No hypothesis, threshold, Table 1 cell or Table 2 cell changed; `check_reported_numbers.R`
exits 0. The protocol fell from 29,543 to 28,902 words and the supplement from 9,189 to 8,981.

- The YAML `author:` block is removed and `title.tex` is no longer listed under
  `template-partials`, so the Stage 1 PDF renders with the title alone (the partial is kept
  for the de-anonymised version; `preregistration/README.md` says how to restore it). The
  CRediT placeholder no longer carries initials. Still identifying, and left as required
  disclosures: the Oxford mentions under Ethics, Data availability and Competing interests,
  the prior-access sentence about the earlier descriptive study, the GitHub URL, and the four
  self-cited packages, which render as "Bernabeu, 2026a-d" under author-date citation.
- Every registered rule is now stated in full once and pointed to elsewhere. Outcome readings
  live in Table 1, so the H2, H4, H5 and H6 paragraphs that restated them are rationale plus
  a pointer; posterior criteria live under Decision rules; the H1 narration rule lives in the
  H1 paragraph, with the seventh adjustment and the first contingency pointing to it; the
  untestable/underpowered/not-evaluable labels are stated once, after H6; the lexical-by-age
  reasoning (Hess 2026, Zoccolotti 2005) sits in the age-band paragraph of the Introduction;
  Delage 2019 moved into the H2 capacity rationale; the narration mechanism is stated under
  H4 only; the list of narration unknowns lives only in Table 2 row (a).
- Stale text fixed: the editorial confirmation of 3 August 2026 came "while this protocol was
  being written", not "before we wrote" it; "on the sign convention above" and "the paragraph
  on orthographic depth" pointed forward and now say "below"; "described under sensitivity"
  now names Sensitivity analyses; two S3 sentences referring to "an earlier version/draft of
  this protocol" are gone; "the field gains an estimate it does not have" is reworded so it
  makes no priority claim.
- Supplement: the sentence-segmentation diagnostics moved from Materials to S3; the count
  script's band description in Data provenance now points to Supplementary Table 5; S1, S5,
  S7 and S8 no longer repeat the main text.

### 23 September 2026: the two open items of the 22 September pass closed

- The Hypothesis 1 narration rule is kept, on the author's instruction to decide from the
  plan, the data and the literature (reasoning recorded in `ISSUES.md`). One tightening: the
  Table 1 text thresholds were simulated at twelve readings per text and the unnarrated
  subset will carry far fewer, so the rule now reads a threshold re-derived from the
  deposited texts sweep at the observed unnarrated readings per text, registered as the
  seventh design-analysis adjustment and run only if the compression diagnostic fires.
  "Six adjustments" becomes "Seven" under Design and precision analysis.
- Jin and Yuan (2025) verified from the PDF. The paper says "many wanted plots and dialogue
  to remain human-authored", not "most were uncomfortable"; the opening sentence now says
  "many" and states the condition under which those parents accepted machine-made images.

### 22 September 2026: rationale, literature and methods strengthened; one new decision rule

A general pass over the Stage 1 protocol against the strong-study checklist, with the
hypotheses, materials and analysis plan unchanged. Seven works were added to the
bibliography after a forward search of the 2025 and 2026 literature, each verified
against its Crossref record and cited only for what its abstract or full text states.

What the literature now carries that it did not:

- The two premises of the opening paragraph are sourced. Picton and Clark (2026) give
  the UK figures for fiction read on screen (one in five 8- to 18-year-olds in 2025) and
  the fall in print fiction since 2017; Ratner et al. (2025) give the platform's own
  2.4 million sessions in six months; Jin and Yuan (2025) give parents' discomfort with
  machine-written story text. A sentence now states what the field gains whatever the
  result.
- Timkey et al. (2026, PNAS, *n* = 368, 409 surprisal estimators) is cited for the
  finding that surprisal captures early disambiguation but not the rereading cost of
  structural repair, which is the strongest available reason for carrying a grammatical
  family separate from surprisal. Kiegeland et al. (2026, preprint) is cited for the
  unsettled choice of unit in surprisal theory, beside Giulianelli et al. (2024).
- Kruchinina et al. (2026), already in the bibliography but uncited, now supports the
  Hypothesis 2 argument: a sharp accuracy shift on passives between 7 and 8, and
  fixation patterns that still differed from adults' at 8 to 10 after accuracy had
  converged, which is why a time-based outcome is the right grain.
- Gleni et al. (2026) gives silent reading speed in 194 Greek children rising from 111
  to 166 words per minute across grades 3 to 6, driven by oculomotor change, beside
  Huestegge et al. (2009) on the age band as a proxy for automaticity.
- Zagato et al. (2026, *N* = 407) shows primary children's calibration matching older
  students' on narrative but not expository text, which bears directly on Hypothesis 5
  since every text here is narrative.
- Clinton-Lisell and Litzinger (2026) locate most of the screen shortfall in scrolling
  (paper better by 0.35 to 0.48 *SD* with scrolling, 0.03 to 0.12 without, tablet
  without scrolling ranked closest to paper); this app paginates on a tablet, and the
  constraints-on-generality paragraph now says so.

Methods:

- **New decision rule for Hypothesis 1 (author to approve).** Narration was on in
  about nine sessions in ten, so each prevalence-weighted main effect is dominated by
  the narrated slope; if the recording paces narrated sessions, the continuity slope
  converges on zero and the lexical slope on the recording's duration function, and an
  inside-region continuity verdict would have been misread as "the laboratory effect
  does not transfer". Where the compression diagnostic fires, the derived unnarrated
  slope now carries a component's Hypothesis 1 verdict if the unnarrated readings cover
  that component's threshold in Table 1; otherwise the pooled verdict stands, reported
  beside the unnarrated slope and as consistent with the recording having set the pace.
  Stated in the Hypothesis 1 paragraph, in Table 1, and under the registered
  contingencies. No hypothesis, sample or model changes.
- The classic stories may sit in the surprisal model's training corpus (OSCAR 21.09),
  which would pull their lexical component towards the easy end. Registered: per-language
  comparison of classic and generated surprisal before any outcome is joined, and a
  tier-1 refit on generated texts alone (second sensitivity family; S3 explains why).
- The intraclass correlation of the outcome at Text and Account level is registered as
  a reliability statement for the outcome.
- The platform's stated audience of 4 to 9 is recorded beside the age bands, so the
  unbounded 9+ band is read as sitting mostly at its lower edge.

Presentation: three paragraphs that grew past 280 words with the additions were split
at their topic shifts, two fronted adverbials received their comma, and the genAI-tell
densities are unchanged (em dash 0.0/1k, Claudisms 0.0/1k, contrastive frames 0.61/1k).

### 20 September 2026: content-attribution audit of every citation, and a cohesion pass

Every one of the 271 keys cited by the protocol and the supplement was checked against
what its source actually says, not only against the published bibliographic record
(`verify_references` check 3, which the earlier passes had not run). Of 327
claim-and-citation pairs, 286 were confirmed, 39 were partly supported and **two were
contradicted**. No reported number changed. Nothing is left unverified: the one source the
automated routes could not reach, Ripoll Salceda et al. (2020), was settled from the
author's copy of the PDF the same day.

The two contradictions:

- Schwalm et al. (2026) was cited for a speed-accuracy trade-off, with comprehension
  falling as reading speed rose. Its headline conclusion is the opposite: comprehension
  held across a broad band of rates and fell only at about 405 words per minute, while
  word-property effects on eye movements persisted throughout. The passage on skimming
  under Selection now states the finding correctly. It also no longer asserts that the
  faster readings carry attenuated text coefficients, for which the corrected source
  gives no warrant, and registers the ambiguity instead.
- Häuser et al. (2025) was cited in Supplementary S3 for a frequency-by-predictability
  interaction in database fit. The paper reports no such interaction; its fit
  differences ran by participant population. The clause is corrected.

Thirty-nine attributions were narrowed to what the source establishes. The substantive ones:
the argument-overlap rule is now credited to Kintsch and van Dijk (1978) rather than to
the 1988 construction-integration paper; the discourse tie-break rule no longer rests on
a contrast between deep and referential cohesion that Pickren et al. (2022) does not
support, and is stated as the registered convention it is; the surprisal-in-the-lexical-family
rationale no longer converts a model-fit result of Oh and Schuler (2024) into a claim
about human processing; the four digital-trace error types are now mapped onto the types
TED-On actually names; the 400 words-per-minute bound is justified from Rayner's stated
adult range rather than from a ceiling that review does not set; and populations are now
named where a result comes from adults, from second-language readers or from one grade
(Nahatame, Koriat, Chetail, Markovich, Malone, Baars, Zoccolotti, Arosio, Montag).

Glorfeld (1995) is added to the bibliography and cited beside Horn (1965) for the
95th-percentile parallel-analysis criterion, which is Glorfeld's modification.

The plausibility bound under Measures was checked against Ripoll Salceda et al. (2020) in
full. Their rule and its rationale are as the protocol described them, and their p. 161
attributes the rationale to Rayner et al. (2016), which is where the protocol's earlier
wording came from. Two details are now exact: the 19,237 figure is participants assessed,
not cases, so the protocol reads "313 cases from tests that assessed 19,237 participants";
and the deletion applied only to silent-reading measures, which the protocol now says. The
lower bound's two supporting figures were confirmed unchanged: 30 words per minute is the
slowest pooled mean in that meta-analysis (Table 2, first grade, silent) and 8 words per
minute is the floor of the normal range it proposes for that grade (Table 5).

On presentation, paragraphs over 280 words fell from 19 to 10 as the dimension
reduction, the design analysis, the Materials rules, the Hypothesis 4 rules, the outcome
transformation, Hypothesis 5 and the literature count were each broken at their topic
shifts, with no wording lost. GenAI-tell densities remain at or near zero (em dash
0.0/1k, Claudisms 0.0/1k, contrastive frames 0.62/1k), and the sentence-length
distribution is unchanged at a mean of 25.0 and a median of 24.

### 17 September 2026: count script tested and reissued as version 2026-09-17

The version supplied to the data controller on 7 August 2026 (script version
2026-08-05) was tested against malformed inputs, having been correct on the 35-row
sample and on clean synthetic exports. Five inputs unlike the sample made it report a
confident wrong figure. The tests are deposited in `count_script/tests/`, the supplied
version is kept byte for byte as `lets_story_summary_2026-08-05.py`, and
`lets_story_summary.py` is now version 2026-09-17.

What the tests found, and what the new version does about it:

- A part with no header row had its first data row read as the column names and
  written into the summary data file, reading time, account identifier and timestamp
  included (CS-02). The run now stops, names the file, and writes nothing.
- One unclosed quote turned 4,233 rows into 199, with one row reported skipped and
  exit status 0 (CS-04). The field-size limit is back to 1 MB, every physical line is
  accounted for against the rows read, and a mismatch stops the run before writing.
- Identifiers in scientific notation, the form the sample arrived in, merged accounts
  silently: 300,000 became 258,697 (CS-01). They are now counted and reported, and the
  account figures are marked unreliable. The digits cannot be recovered. The 35-row
  sample reached us in that form, unmodified since it was downloaded, and its other
  marks (warehouse-style timestamps, correct quoting) point to a clean export
  somewhere behind it, so the covering email describes the mechanism without
  attributing it and asks only that the script be run on the CSV straight from the
  export.
- A part without `time_spent_reading` still produced "All 2,161 sessions carry a usable
  number" for a 4,322-session export (CS-03). The verdict now names the sessions the
  check could not cover, and the per-file record says which files carry the column.
- An empty `story_id` was filled from the story title, which has two values in this
  export, so 554 empty identifiers were reported as none and 800 texts as 802 (CS-06).
  An empty identifier is now counted as one.

Also fixed, with tests: a stronger four-anchor test for a field shift that keeps the
field count (CS-05); folder input no longer reads a stray `.txt` as sessions and is
case-insensitive (CS-07, CS-27); a file supplied twice is detected by checksum, and the
script skips its own output (CS-08); the encoding fallback is recorded (CS-09); decimal
commas are read as decimal points (CS-10); the analysed age bands match regardless of
spacing and case (CS-11); the duplicated
reading-time verdict in `main()` is gone (CS-13); missing-value tokens are treated alike
(CS-15); the date format found is recorded per file (CS-16); the manifest is written with
Unix line endings (CS-19); `--manifest-from` writes beside its input and counts short
rows (CS-20); and `--help`, `--version` and option validation (CS-21). The instruction sheet was
not reissued, so that the data controller receives one file and no new instructions; its two
stale sentences (CS-22, CS-23) are recorded in `preregistration/README.md` instead of corrected.

On the real sample the new version reproduces every figure the old one reported, adding
seventeen rows of its own, and on a 259,280-row synthetic export the two agree exactly,
in 25.8 seconds against 27.0.

### 17 September 2026: protocol pass, with reported numbers changed

A study-level pass over the Stage 1 protocol and supplement, acting on the audit findings that
had awaited sign-off. Three reported numbers changed, each because its simulation did not
represent the registered design.

#### Changed numbers

- **Hypothesis 6 requirement: 563 → 609 children at 0.90 (528 to 697), 681 → 731 at 0.95
  (621 to 851).** `tier2_within_child.json` crossed each child's five texts with all five session
  positions (25 rows per child) and gave the accumulated-reading contrast a standard deviation of
  0.45 where the protocol registers a per-SD unit (DA-01, DA-02). The contrast is now
  ±1.414/±0.707/0, and `run_design_analysis.R` keeps one randomly ordered reading per text per
  child, with guards on the row count, the distinct texts and the independence of position from
  text identity. A first attempt that kept the j-th text at the j-th position tied position to
  text index, because pilotr returns a child's texts sorted, and was discarded before any number
  was taken from it. The tier-2 CSV now records `per_child` in place of a misleading `per_text`
  (DA-24).
- **Hypothesis 5 projection: 8,000 to 8,700 → 9,300 to 10,300 generated texts, 2,300 to 2,500 →
  2,700 to 3,000 with five ratings.** `run_ordinal_analysis.R` dropped boundary fits with
  undefined standard errors, which are not a random subset (DA-05), and `summarise_ordinal.R`
  projected from the true coefficient although the omitted child intercept attenuates a logit
  coefficient (DA-04). Boundary replicates are now refitted as the fixed-effects cumulative logit
  and kept, the projection uses the Zeger, Liang and Albert (1988) attenuation factor, checked
  against the mean fitted estimates, success is counted only in the true direction (DA-27),
  warnings raised in `summary()` are caught (DA-06) and skipped replicates are counted (DA-07).
  The script writes `design_analysis/session_info_ordinal.txt`.
- Figure 3 and Supplementary Figure 2 regenerated (panel subtitles now say twelve readings per
  text on average, and five distinct texts per child).

#### Fixed in the protocol and supplement

- Table 1 (Design Table): the Hypothesis 5 row ran off the foot of its landscape page. Column
  widths rebalanced towards the interpretation column, row padding reduced inside both landscape
  tables, and the duplicated "shown wrong" sentences in that cell condensed.
- Simulated models described as fitted by restricted maximum likelihood (DA-17); the tier-2
  model described as it is (DA-30); how requirements and their intervals are solved stated in
  S5 (DA-19); seeding described correctly (DA-25); twelve readings per text called an average
  (DA-28); singular fits at two readings per text disclosed (CR-04).
- The simulated decision criteria are now stated to be slightly stricter than the registered
  posterior rules, so the requirements are conservative.
- "Exploratory" removed from an analysis inside the Stage 1 plan (the template forbids
  exploratory analyses at Stage 1); it is now descriptive.
- Code availability names the session records that exist (RP-10). The count script is described
  as reading nineteen columns besides the outcome (DC-19). S8 no longer claims the script
  regenerates the activity-counter rows, and no longer quotes a real session's reading time
  (CS-18, CR-01). S1 credits the right scripts (TH-21). The theory object's within-window
  assumption now names question (l), so "five" auxiliary assumptions tied to questions is
  correct in the object, the protocol and S1 (TH-16).
- The 2026 point of the literature sizing is marked as a partial year to 26 August, and the
  trend figure's Wilson bands are explained (FL-06, FL-16).
- Supplementary Table 3 said French was the only language outside the age-of-acquisition anchor
  set with no broad native set; Korean is in the same position.
- The protocol now says the two authors of the earlier Let's Story study are authors of this
  protocol, as the supplement and cover letter already did.
- H6 wording "will be followed by" replaced with association language.
- An uncited claim in Supplementary Table 3 now cites Oh and Schuler (2023).

#### Bibliography, checked against Crossref for every cited entry

- Titles corrected: Heß et al. (2026), Lian et al. (2026), Louwen et al. (2026), Markovich et
  al. (2026), Schmalz et al. (2025), Tucker and Deacon (2025), Eberhart et al. (2025).
- Authors corrected: Eberhart (Janina), Markovich (Vered; Tal, Dana; Yinon, Rotem), Appel et al.
  (W. P. Malecki, T. V. Messingschlager, J. R. Winkler), Haeffel and Cobb (Willie R.), MECO Wave 2
  (Ziaka added).
- Article numbers corrected: Appel 1892, Bear and Phillips e3, Boeve and Bogaerts 266, David et
  al. 66, Kimchi et al. 343, O'Sullivan 1708. Altamura et al. is now in its issue (2026, 62(8),
  1648–1671).
- Added: Oh and Schuler (2023); Zeger, Liang and Albert (1988).

### 12 to 13 September 2026: code audit

These entries come from the code audit of 12 to 13 September 2026. No simulation, figure,
results file, rendered draft or manuscript text was regenerated or edited, and no reported
number changed. The findings that would change a reported number await sign-off in `ISSUES.md`.

#### Added

- `ISSUES.md`, the register of that audit's findings, each with its severity, its HIGH-RISK
  status and whether it was resolved or deferred.
- A root `.gitignore` for R and Python session files, `.Renviron`, `node_modules/`, local
  Claude Code state, Quarto's undated render outputs and the count script's deliverables. It
  untracks nothing already committed.
- `CHANGELOG.md`.

#### Fixed

- `preregistration/check_reported_numbers.R` could pass when it should fail. A block that cannot
  run, because theoryforge is missing or an artefact is absent, now exits 1 unless
  `INTRACT_ALLOW_SKIP=1` is set. Numbers are matched with digit boundaries, and precision
  figures, intersections and theory counts inside the phrase that quotes them. Theory counts are
  compared with the object's own counts through a number-word lookup, where the script used to
  test only that the words were present. The title limit and abstract limit are read from
  `journal.json`, and the title from the YAML front matter. The check now also covers the
  grammatical and continuity main effects, the 0.95 requirements, the auxiliary-assumption count
  and the Figure 1 caption. It passes on the current protocol and fails on a planted mismatch.
- `preregistration/_rename-output.R` reported a rename as done when it had failed, for instance
  when the dated draft was open in a viewer. It now stops with an error.
- `preregistration/theory/report_theory.R` printed each implication's conditioning set twice.
- `mindmap/source files/capture.js` called `process.exit()` inside a `try` block, which skipped
  the `finally` block that closes Chromium. It now sets `process.exitCode`.

#### Changed

- Script headers and comments that had drifted from the code were corrected: the outputs of
  `build_theory.R`, what `check_manuscript_claims.R` compares, the figure number in
  `make_figure1.R`, the worker-cluster fallback and the file-name-only cache in both simulation
  scripts, the values each sweep substitutes for the specifications, the shared replicate seeds,
  the ordinal region's bounds and effect ratio, the colour palettes and the key variable
  `SCOPUS_API_KEY`. Headers now name inputs, outputs and run order, and values with no recorded
  source carry `TODO: justify`.
- `preregistration/README.md` now gives the requirements, an ordered pipeline, how the
  manuscript is checked against its artefacts, the source of each quoted number, every
  environment variable, and the current rigour score, and it no longer claims that manuscript and
  theory object cannot drift apart.
- The root `README.md` now describes the registered study: six hypotheses, two of them
  two-sided, the age bands, the eligibility rules, the outcomes and the analysis. The session,
  country and language figures that no source in the repository supports were removed.
- `mindmap/source files/package.json` names `capture.js` as its entry point and adds
  `npm run capture`.
