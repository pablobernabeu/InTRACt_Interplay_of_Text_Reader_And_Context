# Changelog

This file records notable changes to the code, documentation and generated artefacts in this
repository, in the format of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Earlier
changes are recorded only in the git history and in the dated protocol drafts under
`preregistration/`. Any change that could alter a reported number must be entered here with its
date and rationale.

## [Unreleased]

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
