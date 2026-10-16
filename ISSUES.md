# Code audit register

This file records every finding of the strong-codebase audit run on 12 and 13 September 2026 over the working tree of branch `wip/bib-2026-07-21`, and what became of each one. Eight auditors each covered one area, an adversarial verifier re-checked every finding in that area by reading the cited code and re-running checks, and a completeness critic looked for what the areas had missed. Every script run happened on copies outside the repository. No simulation, figure, results file, rendered draft or manuscript text was changed.

The audit raised 280 findings. Verifiers refuted 3, leaving 277: 29 BLOCKING, 135 MAJOR and 113 MINOR, of which 79 are HIGH-RISK. 63 were resolved and verified, 25 partly resolved, 70 duplicate another finding, 1 needed no change, and 118 are deferred with the reason given.

Severity follows the audit's tiers. BLOCKING breaks reproducibility or can silently produce a wrong result, MAJOR covers dead code, missing pins, drift and undocumented behaviour, and MINOR covers style and stale wording. A HIGH-RISK finding touches code behind a number the protocol reports, or the count script already supplied to the data controller, and is never acted on without the maintainer's sign-off.

## Decisions needed

### A new Hypothesis 1 decision rule for narration-dominated main effects (22 September 2026)

**Decided on 23 September 2026: kept, with one tightening.** The author asked for the
decision to rest on the study plan, the data and the literature. The plan already treats the
compression diagnostic as a registered contingency for Hypothesis 4 and already promotes a
within-account contrast when the data cover the threshold, so the rule adds no new kind of
decision. The data make the concern concrete: with narration on in 32 of 35 sessions, a
pooled continuity coefficient inside the region is about 0.09 times the unnarrated slope,
which is inside the region for any unnarrated slope below 0.55 *SD*. The literature makes it
likely: exposure time under narration had a standard deviation of 0.62 s against 11.56 s
self-paced (Valentini et al., 2024), and the reading-while-listening benefit vanishes where
the comparison is self-paced (Clinton-Lisell, 2023). The tightening: the text threshold in
Table 1 was simulated at twelve readings per text, and the unnarrated subset will carry far
fewer, so the rule now reads a threshold re-derived from the deposited texts sweep at the
observed unnarrated readings per text, registered as the seventh design-analysis adjustment
and run only if the diagnostic fires. The original note follows.

Narration was on in 32 of the 35 structural-sample sessions, so each prevalence-weighted
Hypothesis 1 main effect is about nine-tenths the narrated slope. Under the audio-pacing
account that Hypothesis 4 tests, the narrated continuity slope converges on zero and the
narrated lexical slope on the recording's duration function, so an inside-region continuity
verdict could arise from pacing alone and would have been read as "the laboratory effect
does not transfer". The 22 September pass added a rule, mirroring the existing Hypothesis 4
within-account promotion: where the compression diagnostic fires, the derived unnarrated
slope carries a component's Hypothesis 1 verdict if the unnarrated readings cover that
component's Table 1 threshold, and otherwise the pooled verdict stands, reported beside the
unnarrated slope and as consistent with pacing. It changes no hypothesis, sample or model,
but it is a registered contingency and the author must approve it before submission. It sits
in the Hypothesis 1 paragraph, the Table 1 Hypothesis 1 cell, and the "Four registered
contingencies" paragraph under Decision rules and diagnostics.

### One citation resting on a press report (22 September 2026)

**Resolved on 23 September 2026 from the author's PDF.** The paper says "many wanted plots
and dialogue to remain human-authored" and that parents' acceptance of AI images rested on
"the plot, dialogue, and narrative" being "still created by human authors" (Jin & Yuan, 2025,
pp. 9-10). The press report's "most" is not in the paper; the protocol now says "many" and
states the condition. The original note follows.

Jin and Yuan (2025, *International Journal of Child-Computer Interaction*, 46, 100787,
<https://doi.org/10.1016/j.ijcci.2025.100787>) was cited in the opening paragraph for the
finding that most parents interviewed were uncomfortable with a machine writing the text of a
child's story. No abstract is indexed on Crossref or OpenAlex, the publisher page is blocked,
and the attribution rested on a press report quoting the first author.

### The tier-2 design analysis

**Resolved on 17 September 2026** (see `CHANGELOG.md`): 609 children at 0.90 and 731 at 0.95. The original text follows.

Findings DA-01, DA-02. The simulation gives each child 25 readings, with every text read at all five session positions, where the protocol registers five readings on distinct texts, and its accumulated-reading contrast has a standard deviation of 0.45 where the protocol registers a per-SD unit. A synthetic check found that the two errors nearly cancel at 500 children, so the quoted 563 children may be roughly right by coincidence, but the specification does not represent the registered design. Both must be fixed together, followed by a re-run of the tier-2 sweep and new figures for Table 1, the Design and precision analysis and the supplement.

### The ordinal projection behind Hypothesis 5

**Resolved on 17 September 2026** (see `CHANGELOG.md`): 9,300 to 10,300 generated texts, 2,700 to 3,000 with five ratings. The original text follows.

Findings DA-04 to DA-07, DA-27, CR-04. The projection ignores the attenuation caused by the omitted child intercept, which on its own puts the requirement at about 9,000 to 9,800 generated texts where the protocol quotes 8,000 to 8,700. Replicates with non-finite standard errors are boundary fits whose share falls from 23 to 2 per cent across the grid, so dropping them can bias the fitted exponent.

### Hardening the simulation and figure code

Findings DA-03, DA-08, DA-10 to DA-16, DA-22 to DA-24, DA-29, DA-33, DA-36, TH-06 to TH-09, TH-17, FL-01, FL-03, FL-04, FL-08 to FL-15, ST-06, ST-24, CR-03. These guard against stale caches, relabelled solver errors, unvalidated settings and assertions that can pass on a wrong figure. Most would change no current number, but all edit code behind reported numbers.

### A reissue of the count script

**Done on 17 September 2026.** Version 2026-09-17 is in `count_script/lets_story_summary.py`, the supplied version is kept as `lets_story_summary_2026-08-05.py`, the tests are in `count_script/tests/`, and `CHANGELOG.md` records what changed. What remains for the author is to send the new version and the revised instruction sheet to the data controller, CS-12 (small-cell suppression, not implemented) and CS-14, CS-24, CS-25 and CS-26 (a docstring, stale comments, file length and some redundant logic) are untouched.

**Tested on 17 September 2026** against the supplied script (SHA-256 09316DCC...B29B7A, identical to the copy on the Desktop). On the real 35-row sample it reproduces the 6 August output exactly, apart from the run date, and on clean synthetic exports (43,226 rows, as one file and as three parts with one gzipped, and with commas, quotes and line breaks inside properly quoted titles) every count matched the truth. The defects appear only with inputs unlike the sample, and each was reproduced: user_id in six-significant-digit float form merged 2 of 2,000, 1,233 of 50,000 and 41,303 of 300,000 accounts with no warning (CS-01); a part without a header wrote its first data row, including a user_id, a timestamp and a reading time, into the summary CSV as that file's column names, and counted its other rows as sessions with no identifiers (CS-02); a part without `time_spent_reading` still produced "All 2,161 sessions carry a usable number" for a 4,322-row export (CS-03); one unclosed quote at line 200 left 199 of 4,233 rows read, one row reported skipped and exit status 0, where Python's default field limit would have raised an error (CS-04); and story_id blank on 554 rows gave 0 sessions with no story identifier and 802 texts for 800 (CS-06). The 7 August example output holds 132 two-way cells of a single session (CS-12).

Findings CS-01 to CS-16, CS-19 to CS-28. Four BLOCKING defects affect the supplied version 2026-08-05. Float-formatted user_id values merge or split accounts without warning. A part without a header row writes a raw session (identifier, timestamp, reading time) into the deliverable. A part missing the reading-time column still yields a verdict of all sessions usable, and an unclosed quote swallows rows silently. CS-12 records that no small-cell suppression is applied, although the protocol says the counts contain no record of any individual. The author decides whether to issue a new version to the data controller.

### The R environment

Findings RP-01, RP-02, TH-07. There is no lockfile, and the four study packages were installed from local builds with no recorded source, so the environment cannot be rebuilt and the rebuild-and-compare gate cannot be run.

### Before the branch is pushed or made public

Findings RS-02, RS-03, RS-04, RS-06, RS-10 to RS-12, RS-15, DC-55. The Code availability statement and the cover letter point to a default branch that holds none of this code. Thirteen publisher PDFs sit in unpushed history, the literature-review gitlink has no .gitmodules entry, node_modules is tracked, there is no licence and no CI, and dated drafts accumulate with no retention policy.

### Manuscript text

**Resolved on 17 September 2026**, except FL-05 (the search record's trend queries) and CR-07 (uncited bibliography entries). The original text follows.

Findings DA-17, DA-19, DA-25, DA-28, DA-30, RP-10, DC-19, CS-18, TH-16, TH-21, FL-05, FL-06, FL-16, CR-01, CR-07. Proposed corrections to the protocol, supplement and bibliography. For example, the simulated models were fitted by REML where the text says maximum likelihood, and four auxiliary assumptions name a data-controller question where the text says five.

### Facts only the author holds

Findings DC-44, DC-46, DC-49, CR-06, TH-11. The source of the session, country and language figures removed from the root README, which framework figure it should show, the funding arrangement against the competing-interests statement, the reference style, and whether diagram_theory.R can be deleted.

## Poster folder audit, 16 October 2026

A strong-codebase pass over `poster/`, run at the author's request after the poster had been sent for printing, so the printed PDFs could not change. Before any change, the source on `main` was rendered in a scratch copy: both PDFs matched the committed ones in text and in every pixel at 150 dpi, with only their embedded timestamps differing, and the README's generated sections were reproduced unchanged. After the restructure, a copy of the tree with no `preregistration/` beside it gave the same result, and the preview PNG was byte-identical. The author's untracked `InTRACt poster Oct 2026 v3.pdf` is also pixel-identical to `poster.pdf`.

| ID | Severity | Location | Finding | HIGH-RISK | Status |
|---|---|---|---|---|---|
| PO-01 | BLOCKING | `poster/` | No R lockfile for the poster build, so the environment cannot be rebuilt from a pin; the same root cause as RP-01 | yes | Deferred with RP-01, whose decision covers the repository. Mitigated: the README now gives the R, package and Quarto versions with which the committed PDFs were reproduced pixel for pixel on 16 October 2026, and says there is no lockfile. |
| PO-02 | MAJOR | `poster/InTRACt poster Oct 2026.pdf`, `… v2.pdf` | Two superseded renders of 16 October, written by no build step, tracked beside the live `poster.pdf` under near-identical names |  | Resolved in ec363d6, at the author's choice: removed from the tree. On `main` they remain in a572cdd and b5e36fd. |
| PO-03 | MAJOR | `poster/README.md:15`, `:69`, `:136` | The protocol link, the pointer to Supplementary Section S5 and the source of `data/design_analysis/` named `../preregistration/`, which on `main` is the June 2026 draft, although the printed QR caption promises the protocol |  | Resolved in 861ae41: the links go to the protocol branch, and the page says which branch holds the current protocol. See PO-08. |
| PO-04 | MAJOR | `poster/poster.qmd:32` | The build read its citation style from `../preregistration/apa7.csl`, so the poster folder did not build on its own |  | Resolved in 02c7f4e: `layout/apa7.csl` is a byte-identical copy, and a render with no `preregistration/` beside the folder reproduced both PDFs. |
| PO-05 | MAJOR | `poster/` | Thirteen files at the folder root, mixing the Typst template, its show rule, two Lua filters, the bibliography and the preview image with the poster and its source |  | Resolved in 02c7f4e: build files in `layout/`, the bibliography in `data/`, the preview in `img/`. The root holds the README, `poster.qmd`, `poster.pdf`, `poster-print.pdf` and `.gitignore`. |
| PO-06 | MINOR | `poster/R/figures.R:320` | The bibliography path was written twice, in `poster.qmd` and as `bib_urls()`'s default, so a move could leave the two disagreeing | yes | Resolved in 02c7f4e: `bib_urls()` takes the file from `poster.qmd`'s metadata and stops with a clear message when called outside a render without a file. Output verified unchanged. |
| PO-07 | MINOR | `poster/data/design_analysis/` | Copies of three protocol outputs, kept so that `main` builds; they can drift from the protocol if the design analysis is re-run |  | Deferred by design: identical to the protocol branch's files on 16 October 2026, and `R/figures.R` says to copy them again after a re-run. |
| PO-08 | MAJOR | `poster/README.md:15` | The page now links to the branch name `wip/bib-2026-07-21`, so renaming, merging or deleting that branch would break the protocol links that the printed QR code leads to |  | Deferred: the author decides whether and when the protocol branch is merged into `main`. Update the three links in the same change. |
| PO-09 | MINOR | `poster/R/*.R` | lintr defaults report brace, indentation and semicolon style lints, one 109-character line in `R/scopus_counts.R:193`, and "no visible binding" notes from ggplot's column names |  | Deferred with ST-14 and ST-15: no repository style configuration has been chosen, and reformatting code behind the printed poster waits for that pass. |

## Register

Findings are ordered by severity, then by area. Details follow the table for every finding that is not a duplicate, refuted or resolved in full.

### BLOCKING (29)

| ID | Area | Location | Finding | HIGH-RISK | Status |
|---|---|---|---|---|---|
| DA-01 | Design analysis | `preregistration/design_analysis/tier2_within_child.json:11` | Tier-2 simulation gives each child 25 readings, each text read at all five session positions, not five readings on distinct texts | yes | Resolved 17 September 2026: each child now reads five distinct texts in a random order, one per session position, with guards; the tier-2 sweep was re-run (609 children at 0.90, 731 at 0.95) and the protocol and supplement updated. |
| DA-02 | Design analysis | `preregistration/design_analysis/tier2_within_child.json:12` | Accumulated-reading contrast has SD 0.45, so the simulated coefficient is not on the per-SD unit the protocol registers | yes | Resolved 17 September 2026 with DA-01: the contrast has a population SD of 1, so the coefficient is per SD. |
| DA-03 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:90` | Sweep caches are keyed only on file name, so edited specs, replicate counts, ROPE or rating rate silently reuse stale results | yes | Partly resolved: the file-name-only cache is stated in both script headers and the README. Deferred: a cache key that stops on a mismatch is a logic change in code behind reported numbers, so it awaits sign-off. |
| DA-04 | Design analysis | `preregistration/design_analysis/summarise_ordinal.R:31` | Ordinal projection ignores the attenuation caused by the omitted child intercept, understating the quoted requirement by about 12 per cent | yes | Resolved 17 September 2026: the projection uses the analytic attenuation factor (Zeger, Liang and Albert, 1988), checked against the mean fitted estimates; it is now 9,300 to 10,300 generated texts. |
| DA-05 | Design analysis | `preregistration/design_analysis/run_ordinal_analysis.R:144` | Ordinal fits with non-finite SEs are boundary fits, not a random subset, and their share falls from 23 to 2 per cent across the grid | yes | Resolved 17 September 2026: boundary replicates are refitted as the fixed-effects cumulative logit and kept; none is discarded. |
| DA-18 | Design analysis | `preregistration/check_reported_numbers.R:41` | The number-check gate covers a few design-analysis figures and matches bare substrings, so it can pass while quoted numbers are wrong |  | Partly resolved: the gate anchors numbers and now covers the 0.95 requirements and the main effects. Deferred: it does not read the supplement or check the null, readings and ordinal sweep tables; choosing that coverage needs the maintainer. |
| TH-01 | Theory object and checks | `preregistration/theory/check_manuscript_claims.R:1` | check_manuscript_claims.R never reads the manuscript, so it cannot fail on any quoted theory number |  | Partly resolved: the script's header and the README say it never reads the manuscript, and check_reported_numbers.R now compares the score and four counts. Deferred: the thirty implications, the 0.17 similarity and the diagnostic-prediction counts are still compared by eye; the phrases to anchor need the maintainer. |
| TH-02 | Theory object and checks | `preregistration/check_reported_numbers.R:85` | Theory counts and the ordinal ceiling are checked by fixed wording, never compared with the artefact |  | Resolved: theory counts are compared with the object's counts through a number-word lookup. |
| TH-03 | Theory object and checks | `preregistration/check_reported_numbers.R:73` | has(fmt(n)) passes when the number appears anywhere as a substring, and all zero counts share one phrase |  | Resolved: numbers are matched with digit boundaries, and precision figures, intersections and theory counts inside their phrases; the three Scopus concept sizes are matched by digits alone. |
| TH-04 | Theory object and checks | `preregistration/check_reported_numbers.R:10` | check_reported_numbers.R leaves most quoted precision numbers and the whole supplement unchecked |  | Partly resolved: the 0.95 requirements and the grammatical and continuity main effects are now checked. Deferred: the supplement is not read. |
| TH-05 | Theory object and checks | `preregistration/check_reported_numbers.R:88` | Missing theoryforge or a missing ordinal CSV is skipped and the script still reports a full match with exit 0 |  | Resolved: a skipped block exits 1 unless INTRACT_ALLOW_SKIP=1 is set; verified by removing the ordinal CSV in a scratch copy. |
| TH-06 | Theory object and checks | `preregistration/theory/make_figure1.R:93` | Figure 2 content assertion ignores the rank and invisible-edge lines, so a stale id draws a phantom node while the assertion passes | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| TH-07 | Theory object and checks | `preregistration/theory/build_theory.R:7` | The quoted rigour score depends on an unpinned, locally built theoryforge with no lockfile or version assertion | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-01 | Figures and literature sizing | `preregistration/literature/replot_scopus_figures.R:37` | replot_scopus_figures.R strips the plot caption that reports omitted counts and never checks the archived CSVs for missing values | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| CS-01 | Count script | `preregistration/count_script/lets_story_summary.py:1265` | Float-formatted user_id values silently merge or split accounts, with no detection or warning | yes | Resolved 17 September 2026 in version 2026-09-17: identifiers in scientific notation are counted and reported, the account figures are marked unreliable, and the instruction sheet asks for integers or text. The lost digits cannot be recovered. |
| CS-02 | Count script | `preregistration/count_script/lets_story_summary.py:1764` | A part without a header row has its first data row, including a reading time and a user_id, written to the summary data file as column names | yes | Resolved 17 September 2026 in version 2026-09-17: a file whose first line is not a header stops the run, named, with nothing written. |
| CS-03 | Count script | `preregistration/count_script/lets_story_summary.py:1675` | If one part lacks time_spent_reading, the reading-time verdict reports all sessions usable while covering only a subset, and the absence is not recorded | yes | Resolved 17 September 2026 in version 2026-09-17: the verdict names the sessions the check could not cover, and the per-file record states whether each file carries the column. |
| CS-04 | Count script | `preregistration/count_script/lets_story_summary.py:175` | An unclosed quote silently swallows later rows; the raised csv field limit removes the only loud failure, and the skipped-row count reports 0 or 1 | yes | Resolved 17 September 2026 in version 2026-09-17: the field limit is back to 1 MB, every physical line is accounted for against the rows read, and a mismatch stops the run before anything is written. |
| CS-06 | Count script | `preregistration/count_script/lets_story_summary.py:1267` | A blank story_id silently falls back to story_title, which in this export is a two-value category, distorting distinct texts and hiding missing story identifiers | yes | Resolved 17 September 2026 in version 2026-09-17: an empty story_id is counted as one, the title no longer stands in for it, and rows with a title but no identifier are reported. |
| RS-02 | Repository structure | `preregistration/preregistration.qmd:439` | Code availability URL leads to a default branch without the code; working branch has no upstream |  | Deferred: the author must push the branch, after deciding RS-12 and RS-03, and reconcile it with origin/main. |
| RP-01 | Reproducibility | `preregistration/README.md:127` | No R lockfile: the R environment cannot be rebuilt, so the strict rebuild-and-compare gate is unattainable |  | Deferred: renv::init() would record the four study packages with no source, so their sources (tagged releases behind the Zenodo DOIs) must be chosen first. |
| RP-06 | Reproducibility | `preregistration/design_analysis/run_design_analysis.R:90` | The sweep cache is keyed only by file name, so a changed replicate count, spec or grid silently reuses stale simulations and the session record is rewritten to describe the new settings | yes | Duplicate of DA-03 (partly). |
| RP-12 | Reproducibility | `preregistration/check_reported_numbers.R:62` | check_reported_numbers.R exits 0 when checks are skipped, and its substring matching lets small numbers pass anywhere in the manuscript |  | Resolved: see TH-03 and TH-05. |
| RP-13 | Reproducibility | `preregistration/theory/check_manuscript_claims.R:7` | theory/check_manuscript_claims.R never reads the manuscript, and the README says editing a hypothesis in the manuscript alone will make tf_check fail |  | Duplicate of TH-01 (partly). |
| DC-01 | Documentation and comments | `preregistration/README.md:36` | README promises that manuscript and theory object cannot drift apart, but no script compares most quoted theory numbers with the text |  | Resolved: the README no longer promises that manuscript and theory object cannot drift apart. |
| DC-02 | Documentation and comments | `preregistration/check_reported_numbers.R:7` | check_reported_numbers.R header claims it exits non-zero on any mismatch, but several of its checks cannot fail |  | Resolved: the header's claims now hold: every check can fail, verified with planted mismatches. |
| ST-01 | Style and naming | `preregistration/check_reported_numbers.R:79` | check_reported_numbers.R reports success and exits 0 when whole check blocks are skipped |  | Duplicate of TH-05 (resolved). |
| ST-02 | Style and naming | `preregistration/check_reported_numbers.R:19` | Reported-number checks use unanchored substring matching over the whole manuscript |  | Duplicate of TH-03 (resolved). |
| ST-03 | Style and naming | `preregistration/design_analysis/run_design_analysis.R:191` | Every solve_curve error is caught as NULL and relabelled 'not reached', and the gate accepts any refusal | yes | Duplicate of DA-08 (deferred). |

### MAJOR (135)

| ID | Area | Location | Finding | HIGH-RISK | Status |
|---|---|---|---|---|---|
| DA-06 | Design analysis | `preregistration/design_analysis/run_ordinal_analysis.R:90` | n_warned cannot register the ordinal failure mode: summary.clmm warnings fall outside the handler and no convergence field is read | yes | Resolved 17 September 2026: summary() runs inside the warning handler. |
| DA-07 | Design analysis | `preregistration/design_analysis/run_ordinal_analysis.R:78` | Discarded ordinal replicates (NULL returns) are not counted, and their 50-row and 10-text floors are undocumented | yes | Resolved 17 September 2026: n_skipped is recorded and the floors are justified in the script. |
| DA-08 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:191` | Every solve_curve error is recorded as 'not reached within X to Y', whatever its cause | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| DA-09 | Design analysis | `preregistration/design_analysis/run_ordinal_analysis.R:190` | run_ordinal_analysis.R and summarise_ordinal.R write the same two files in different schemas, and the run order is nowhere stated | yes | Partly resolved: the run order is documented in both scripts and the README. Deferred: giving the two scripts distinct outputs changes files the protocol quotes and awaits sign-off. |
| DA-10 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:226` | session_info.txt is rewritten on cached runs with the wrong replicate count, and no session is recorded for the ordinal, summary or 0.95 scripts |  | Deferred: it changes what run_design_analysis.R writes and belongs with the cache-key change in DA-03. |
| DA-11 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:142` | Secondary sweeps hard-code 120 replicates and ignore INTRACT_N_SIMS | yes | Partly resolved: the fixed 120 replicates are documented in the script and the README. Deferred: reading them from a variable changes code behind reported numbers and awaits sign-off. |
| DA-12 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:31` | Environment variables are parsed without validation, and a zero replicate count yields cached NA rows reported as 'not reached' |  | Deferred: validating the environment variables is a code edit in a script behind reported numbers, held back so this pass changed only comments there, and belongs with the sign-off on DA-03. |
| DA-13 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:66` | safe_workers comment misdescribes the fallback, has an unused argument, and the resume claim holds per sweep only |  | Partly resolved: the cluster comment now describes the probe. Deferred: removing the unused argument is a code edit, held back so this pass changed comments only in scripts behind reported numbers. |
| DA-14 | Design analysis | `preregistration/design_analysis/tier1_developmental.json:17` | The deposited JSON specifications do not hold the values actually simulated |  | Resolved: script headers and the README now state what each sweep substitutes for the specifications. |
| DA-15 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:130` | Focal vectors restate effect sizes and signs that should be derived from the spec | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| DA-16 | Design analysis | `preregistration/design_analysis/summarise_ordinal.R:19` | summarise_ordinal.R re-declares ROPE, TRUE_B and the 0.90 target instead of reading them from the sweep | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| DA-17 | Design analysis | `preregistration/supplementary.qmd:137` | Protocol and supplement say the simulated models were fitted by maximum likelihood; pilotr fits REML with derivative checks switched off |  | Resolved 17 September 2026: the protocol and S5 say restricted maximum likelihood. |
| DA-19 | Design analysis | `preregistration/supplementary.qmd:141` | How the crossing and its 95 per cent interval are computed is not described anywhere in the protocol or supplement |  | Resolved 17 September 2026: S5 describes the probit-on-square-root solve, the weights, the heterogeneity factor and the refusal to extrapolate. |
| DA-20 | Design analysis | `preregistration/README.md:62` | README design_analysis section omits the run order, INTRACT_RATED_RATE, the outputs, and caveats about the cache and the 120 replicates |  | Resolved: the README gives the run order, every environment variable, the fixed 120 replicates and the cache caveat. |
| DA-21 | Design analysis | `preregistration/README.md:70` | README claims every analysis script is run against simulated data, but the repository has no analysis scripts |  | Resolved: the README now says the analysis scripts will be run against simulated data before the transfer. |
| DA-22 | Design analysis | `preregistration/theory/intract.theory.yaml:496` | The theory object's formal_model points to a design_analysis file that does not exist |  | Deferred: the theory object's formal_model entry feeds the rigour score the manuscript quotes, so correcting it can move that score. |
| TH-08 | Theory object and checks | `preregistration/theory/build_theory.R:12` | build_theory.R sinks output and messages with no on.exit or finally, so an error is hidden in a truncated tf_check.txt | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| TH-09 | Theory object and checks | `preregistration/theory/build_theory.R:32` | build_theory.R fails open: a cyclic graph, a failed diagram or a non-data-frame result still exits 0 | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| TH-10 | Theory object and checks | `preregistration/theory/build_theory.R:5` | build_theory.R header lists tf_implications.txt, which nothing writes, and the README omits the SVG it does write |  | Resolved: build_theory.R's header lists what it writes. |
| TH-11 | Theory object and checks | `preregistration/theory/diagram_theory.R:1` | diagram_theory.R is an unreferenced one-off probe with no header |  | Deferred: whether diagram_theory.R is dead is uncertain; the README now describes it, and deleting it needs the maintainer. |
| TH-12 | Theory object and checks | `preregistration/theory/report_theory.R:14` | report_theory.R has no header, duplicates check_manuscript_claims.R and prints each conditioning set twice |  | Resolved: report_theory.R has a header and prints each conditioning set once; verified by running it. |
| TH-13 | Theory object and checks | `preregistration/theory/intract.theory.yaml:8` | yaml header and README claim a manuscript hypothesis edit makes tf_check fail, but nothing compares hypothesis text |  | Resolved: the yaml header and README no longer claim that a manuscript edit makes tf_check fail. |
| TH-14 | Theory object and checks | `preregistration/README.md:37` | README quotes the superseded rigour score 90.9 |  | Resolved: the README quotes 90.7 and points to tf_check.txt. |
| TH-15 | Theory object and checks | `preregistration/theory/intract.theory.yaml:496` | formal_model.spec_ref points at a file that has never existed, and the formalisation item passes regardless |  | Duplicate of DA-22 (deferred). |
| TH-16 | Theory object and checks | `preregistration/theory/intract.theory.yaml:11` | Four auxiliary assumptions name a data-controller question, while the yaml, supplement and protocol say every one or five do |  | Resolved 17 September 2026: the within-window assumption now names question (l), so five is correct in the yaml, the protocol and S1. |
| TH-17 | Theory object and checks | `preregistration/theory/make_figure1.R:33` | make_figure1.R hard-codes 12 nodes and 18 edges instead of deriving them from the theory object | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| TH-18 | Theory object and checks | `preregistration/theory/make_figure1.R:121` | Figure 2 layout depends on the Graphviz 2.40.1 bundled inside DiagrammeR, which is neither documented nor pinned |  | Duplicate of RP-05 (resolved). |
| TH-19 | Theory object and checks | `preregistration/check_reported_numbers.R:23` | Title check assumes a double-quoted one-line YAML title and crashes with an uninformative error otherwise |  | Resolved: the title is read from the YAML front matter and a missing abstract stops the script; verified at 78 characters and 148 words. |
| TH-20 | Theory object and checks | `preregistration/check_reported_numbers.R:8` | The check scripts are not wired into rendering, a hook or CI, despite claims that drift cannot happen |  | Duplicate of RS-10 (deferred). |
| TH-21 | Theory object and checks | `preregistration/supplementary.qmd:33` | The supplement credits build_theory.R with outputs it does not produce |  | Resolved 17 September 2026: S1 credits build_theory.R, check_manuscript_claims.R and make_figure1.R for their own outputs. |
| FL-02 | Figures and literature sizing | `preregistration/downloaded_papers_zotero_keys/download_report.csv:1` | Thirteen publisher PDFs, two with no licence evidence, are committed on a branch due to become public |  | Duplicate of RS-12 (deferred). |
| FL-03 | Figures and literature sizing | `preregistration/literature/replot_scopus_figures.R:39` | Figure 1 legend shows the internal column name 'grp' because strip_chrome replaces the package's labelled colour scale | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-04 | Figures and literature sizing | `preregistration/literature/scopus_gap_analysis.R:65` | scopus_gap_analysis.R writes default-styled PNGs and no PDFs, leaving a mixed state unless replot is run afterwards | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-05 | Figures and literature sizing | `preregistration/literature/scopus_gap_analysis.R:117` | The search record omits the trend queries, and its 'Children's reading' column is a different, narrower query than the concept set | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-06 | Figures and literature sizing | `preregistration/literature/scopus_gap_analysis.R:22` | Year window includes 2026, which was incomplete at the search date, and nothing says so |  | Resolved 17 September 2026: the protocol, Figure 1 caption and the S4 caption mark 2026 as counted to 26 August. |
| FL-07 | Figures and literature sizing | `preregistration/literature/scopus_gap_analysis.R:135` | Run stamp and figure scripts record almost no environment, contrary to the protocol's claim |  | Deferred: recording the environment changes what the Scopus script writes, and is best done with its next run. |
| FL-08 | Figures and literature sizing | `preregistration/literature/scopus_gap_analysis.R:63` | No missing-value or coherence assertions before the Scopus counts are archived | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-09 | Figures and literature sizing | `preregistration/literature/replot_scopus_figures.R:23` | replot_scopus_figures.R retypes the comparison queries by hand as lookup keys and never checks that they matched | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-10 | Figures and literature sizing | `preregistration/literature/scopus_gap_analysis.R:123` | The record's trend table picks columns by substring matching and silently loses any unmatched term | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-11 | Figures and literature sizing | `preregistration/literature/replot_scopus_figures.R:81` | Year breaks and label expansion in the trend figure are hard-coded | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-13 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:101` | Design constants in the precision figure are typed into subtitles and code instead of read from the CSVs and specs | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-14 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:118` | Figure-check widths are hard-coded, not derived from the save width, and not the width the manuscript prints at | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-15 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:98` | Panel subsets and series lookups rely on unchecked assumptions about precision_sweep.csv | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-16 | Figures and literature sizing | `preregistration/supplementary.qmd:133` | Supplementary trend caption does not explain the shaded bands, and the replot comment overstates what the captions carry |  | Resolved 17 September 2026: the S4 caption explains the Wilson bands. |
| FL-17 | Figures and literature sizing | `preregistration/check_reported_numbers.R:66` | The search date and trend counts quoted by hand in the protocol are not checked against the archived Scopus files |  | Duplicate of TH-04 (partly). |
| FL-27 | Figures and literature sizing | `preregistration/literature/replot_scopus_figures.R:50` | Scopus figure dimensions and check widths are duplicated and hand-computed | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| CS-05 | Count script | `preregistration/count_script/lets_story_summary.py:1243` | An equal-field-count shift puts reading-time values into read_language labels crossed with age band, and the shape anchors cannot catch it in the export's real column order | yes | Resolved 17 September 2026 in version 2026-09-17: the shape test uses four anchors (date, speech flag, both page counts, language) and needs two failures. |
| CS-07 | Count script | `preregistration/count_script/lets_story_summary.py:955` | Folder input reads every .txt and .tsv file too, so a README in the export folder is counted as sessions; the docs say 'every CSV inside' | yes | Resolved 17 September 2026 in version 2026-09-17: folder input reads .csv, .tsv, .csv.gz, .tsv.gz and .zip only. |
| CS-08 | Count script | `preregistration/count_script/lets_story_summary.py:961` | Twin-file detection covers only .gz beside a plain file in folder mode; .zip twins and pattern inputs are counted twice, and duplicates stay in every count | yes | Resolved 17 September 2026 in version 2026-09-17: a repeat is detected by checksum whatever its name or input mode, and the script skips its own two outputs. |
| CS-09 | Count script | `preregistration/count_script/lets_story_summary.py:1087` | One non-UTF-8 byte in the first 4 MB switches the whole file to latin-1, garbling genuine UTF-8 labels while reporting zero replaced characters | yes | Resolved 17 September 2026 in version 2026-09-17: the fallback to latin-1 is recorded in the file record with the byte at which UTF-8 decoding failed. |
| CS-10 | Count script | `preregistration/count_script/lets_story_summary.py:630` | Semicolon-separated exports are accepted but decimal commas are not, so every reading time becomes 'not a number' and page counts become violations | yes | Resolved 17 September 2026 in version 2026-09-17: a semicolon-separated file written with decimal commas is detected and read as numbers, and the decimal mark is recorded. |
| CS-11 | Count script | `preregistration/count_script/lets_story_summary.py:1296` | Part 2 (the analysed age bands) matches age labels exactly; any spelling variant silently drops out | yes | Resolved 17 September 2026 in version 2026-09-17: age bands match on a spacing- and case-insensitive key, and the raw labels counted in Part 2 are recorded. |
| CS-12 | Count script | `preregistration/count_script/lets_story_summary.py:1826` | No small-cell suppression is applied; most cross-tab cells in the sample output hold a single session or account, yet the protocol says the counts contain no record of any individual | yes | Not implemented, by decision (17 September 2026). Suppression was written and tested, then removed: it changes the deliverable, nobody had asked for it, and an option carried for a hypothetical is a liability in a script that runs once on someone else's machine. The counts go out as they are. If a disclosure rule later requires suppression, the decision is the data controller's and the university's, and preregistration.qmd:435 would need the wording in option (b) above. |
| CS-13 | Count script | `preregistration/count_script/lets_story_summary.py:1678` | Dead code: main() computes a reading-time verdict that is never used and duplicates build_manifest's; Summary.rows is never read |  | Resolved 17 September 2026 in version 2026-09-17: main() no longer computes the unused verdict; build_manifest states it once, from the summary rows. |
| CS-14 | Count script | `preregistration/count_script/lets_story_summary.py:1116` | process_source docstring claims memory does not grow with export size, but a digest is stored for every distinct row |  | Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only. |
| CS-25 | Count script | `preregistration/count_script/lets_story_summary.py:1636` | A 1,969-line single file with a 330-line main() and some functions and methods lacking docstrings |  | Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only. |
| CS-27 | Count script | `preregistration/count_script/lets_story_summary.py:956` | Folder globbing is case-sensitive on POSIX, so files with upper-case extensions are silently skipped on macOS and Linux | yes | Resolved 17 September 2026 in version 2026-09-17: folder listing is case-insensitive, so an upper-case extension is not skipped. |
| RS-01 | Repository structure | `preregistration/_rename-output.R:8` | Post-render rename ignores failure, so a stale dated draft can look current |  | Resolved: the hook stops with an error when the rename fails; verified with the dated draft held open. |
| RS-03 | Repository structure | `private_InTRACt_literature_review:1` | Literature-review gitlink has no .gitmodules and points at a private repository |  | Deferred: add a .gitmodules entry or remove the gitlink; either changes what a public clone contains. |
| RS-04 | Repository structure | `mindmap/source files/node_modules:1` | mindmap/source files/node_modules is tracked: 4,375 files, 41 MiB, 63 per cent of tracked bytes |  | Deferred: untracking node_modules (git rm -r --cached) changes what later clones receive. |
| RS-05 | Repository structure | `.gitignore:1` | No root .gitignore; .claude is excluded only by a local exclude file |  | Resolved: a root .gitignore exists; it untracks nothing. |
| RS-06 | Repository structure | `preregistration/InTRACt preregistration draft - 2026-09-04.pdf:1` | Dated protocol drafts accumulate with no retention policy; the public branch's newest draft is a superseded design |  | Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only. |
| RS-07 | Repository structure | `preregistration/preregistration.qmd:40` | Dated HTML drafts are not snapshots: they load today's figures and libraries by relative path and link a PDF that no longer exists |  | Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only. |
| RS-09 | Repository structure | `preregistration/_rename-output.R:1` | _rename-output.R has no header and the renaming convention is undocumented |  | Resolved: the hook has a header and the README explains the dated drafts. |
| RS-10 | Repository structure | `.github/workflows/render-preregistration.yml:1` | No CI on this branch; the manuscript-number gates are never run, and the main-branch workflow targets the old layout |  | Deferred: adding CI, and wiring the check scripts into it, is a repository decision. |
| RS-11 | Repository structure | `LICENSE:1` | No LICENSE for a repository the protocol says will be public |  | Deferred: the licence must be chosen by the author. |
| RS-12 | Repository structure | `preregistration/downloaded_papers_zotero_keys/download_report.csv:1` | Thirteen publisher PDFs from a Zotero library are tracked and referenced by nothing |  | Deferred: the publisher PDFs sit in unpushed history and should be removed from it before any push, which rewrites history. |
| RS-13 | Repository structure | `README.md:35` | Root README describes a superseded study and embeds a superseded framework figure |  | Partly resolved: the root README's text now matches the protocol. Deferred: the framework figure (DC-46) and the funder line (DC-49) need the author. |
| RS-14 | Repository structure | `preregistration/README.md:37` | preregistration/README.md quotes a stale rigour score and omits the checker, the render hook and several outputs |  | Resolved: the README quotes the current score and describes the checker, the hook and the SVG. |
| RS-15 | Repository structure | `preregistration/count_script/lets_story_summary.py:1` | Opaque auto-sync commits bundle 41 unrelated files, including the count script's first appearance |  | Deferred: the auto-sync process that bundles unrelated files into commits lives outside this repository. |
| RS-16 | Repository structure | `preregistration/count_script/lets_story_summary.py:1` | No recorded hash ties the repository's count script to the copy sent to the data controller |  | Deferred: the checksum must be taken from the exact bytes sent (the CRLF copy), which only the author can confirm. |
| RS-17 | Repository structure | `mindmap/source files/capture.js:20` | mindmap.png regeneration is undocumented and depends on the network |  | Partly resolved: capture.js's header records the network dependency. Deferred: vendoring the font is a maintainer decision. |
| RS-18 | Repository structure | `CHANGELOG.md:1` | No CHANGELOG for a protocol that has been rebuilt several times |  | Resolved: CHANGELOG.md was created. |
| RP-02 | Reproducibility | `preregistration/README.md:128` | The four study packages were installed from local builds with no provenance, and the cited DOIs do not name versions |  | Deferred: the source each study package was built from is known only to the author. |
| RP-03 | Reproducibility | `preregistration/README.md:59` | The R version is not documented, and the machine's R setup has drifted: Rscript is not on PATH, PATH points at a missing R 4.5.1, and two R 4.6 installs share one library |  | Resolved: the README records R 4.6.1; the broken R-4.5.1 PATH entry is machine setup outside the repository. |
| RP-04 | Reproducibility | `preregistration/_quarto.yml:1` | Quarto and TinyTeX/LaTeX versions are neither recorded nor pinned, and the committed drafts show Quarto drift |  | Partly resolved: the README records the Quarto and LuaTeX versions of the 2026-09-05 draft. Deferred: pinning them, for example with quarto-required in _quarto.yml, is a maintainer decision. |
| RP-05 | Reproducibility | `preregistration/theory/make_figure1.R:121` | Figure 1's Graphviz layout engine is not recorded: it is viz.js 1.8.2 bundled inside DiagrammeR, not a system Graphviz |  | Resolved: make_figure1.R and the README name the bundled viz.js engine. |
| RP-07 | Reproducibility | `preregistration/design_analysis/run_design_analysis.R:137` | Fresh and resumed runs write different bytes: the truth column changes type after the CSV round trip, and some solved values lose their last digits | yes | Duplicate of DA-23 (deferred). |
| RP-08 | Reproducibility | `preregistration/design_analysis/run_design_analysis.R:142` | Three sweeps hard-code 120 replicates and ignore INTRACT_N_SIMS, and the session record prints that literal whatever was run | yes | Duplicate of DA-11 (partly). |
| RP-09 | Reproducibility | `preregistration/design_analysis/run_ordinal_analysis.R:132` | Ordinal-analysis seeds are hard-coded in the script, overriding the spec's seed, and R's RNG kind for the thinning step is neither set nor recorded | yes | Duplicate of DA-25 (partly). |
| RP-10 | Reproducibility | `preregistration/preregistration.qmd:439` | The protocol says a session record sits beside every output, but only the reading-time design analysis writes one |  | Resolved 17 September 2026: Code availability names the session records that exist, and the ordinal summary now writes one. |
| RP-11 | Reproducibility | `preregistration/design_analysis/run_ordinal_analysis.R:190` | run_ordinal_analysis.R and summarise_ordinal.R write the same two files with different schemas, so the committed result depends on which ran last | yes | Duplicate of DA-09 (partly). |
| RP-14 | Reproducibility | `preregistration/README.md:37` | The README quotes a theory score of 90.9, but the regenerated tf_check.txt gives 90.7 |  | Duplicate of TH-14 (resolved). |
| RP-16 | Reproducibility | `preregistration/README.md:111` | The count script writes today's date into its output, so the README's claim that a rerun reproduces the 6 August output line for line cannot hold literally |  | Duplicate of CS-17 (resolved). |
| DC-03 | Documentation and comments | `preregistration/theory/check_manuscript_claims.R:6` | check_manuscript_claims.R header and README row say it prints the manuscript's numbers, but it never reads the manuscript |  | Resolved: the header and README say the script does not read the manuscript. |
| DC-04 | Documentation and comments | `preregistration/README.md:37` | README quotes a rigour score of 90.9, while the regenerated output and the manuscript give 90.7 |  | Duplicate of TH-14 (resolved). |
| DC-05 | Documentation and comments | `preregistration/theory/build_theory.R:4` | build_theory.R header lists an output it never writes, and the README omits one it does write |  | Duplicate of TH-10 (resolved). |
| DC-06 | Documentation and comments | `preregistration/theory/build_theory.R:39` | build_theory.R swallows errors from the implications derivation and the SVG render, with no comment saying why | yes | Duplicate of TH-09 (deferred). |
| DC-07 | Documentation and comments | `preregistration/theory/diagram_theory.R:1` | diagram_theory.R has no header, is undocumented and appears to be a leftover inspection script |  | Duplicate of TH-11 (deferred). |
| DC-08 | Documentation and comments | `preregistration/theory/report_theory.R:1` | report_theory.R has no header comment |  | Duplicate of TH-12 (resolved). |
| DC-09 | Documentation and comments | `preregistration/_rename-output.R:1` | _rename-output.R has no header, and the dated-draft mechanism it implements is undocumented |  | Duplicate of RS-09 (resolved). |
| DC-10 | Documentation and comments | `preregistration/README.md:19` | The README never mentions check_reported_numbers.R, the script that gates the manuscript's numbers |  | Resolved: the README has a section on checking the manuscript. |
| DC-11 | Documentation and comments | `preregistration/README.md:58` | No ordered end-to-end run order with inputs and outputs, and the stated dependencies are partly wrong |  | Resolved: the README has an ordered pipeline table. |
| DC-12 | Documentation and comments | `preregistration/README.md:64` | Environment variables are incompletely and partly inaccurately documented |  | Duplicate of DA-20 (resolved). |
| DC-13 | Documentation and comments | `preregistration/README.md:125` | The README gives no environment setup: R version, package versions and sources, Quarto, fonts or Python |  | Partly resolved: the README has a Requirements section. Deferred: an R lockfile (RP-01) is still missing. |
| DC-14 | Documentation and comments | `preregistration/README.md:66` | No expected runtime or memory footprint documented, although a known out-of-memory failure exists |  | Partly resolved: the README says runtimes are not recorded and names the known out-of-memory point. Deferred: measuring runtimes needs a full run of the simulations. |
| DC-15 | Documentation and comments | `preregistration/README.md:19` | No map from a reported number to the script, file and column that produce it |  | Resolved: the README maps each quoted number to its artefact and script. |
| DC-20 | Documentation and comments | `preregistration/README.md:111` | README says rerunning the count script reproduces its output line for line, but the output carries the run date |  | Duplicate of CS-17 (resolved). |
| DC-21 | Documentation and comments | `preregistration/supplementary.qmd:185` | The supplement repeats the line-for-line reproduction claim for the count script |  | Duplicate of CS-18 (deferred). |
| DC-25 | Documentation and comments | `preregistration/design_analysis/run_design_analysis.R:66` | Stale comment: the worker-cluster fallback does not attempt the first grid point as described |  | Duplicate of DA-13 (partly). |
| DC-29 | Documentation and comments | `preregistration/design_analysis/run_design_analysis.R:111` | Design-analysis grid constants have no stated source, and the tier-2 labels copy the spec instead of reading it | yes | Partly resolved: a TODO marks the grid constants' unrecorded source. Deferred: deriving the tier-2 labels from the specification is a code change behind reported numbers. |
| DC-35 | Documentation and comments | `preregistration/theory/make_figure1.R:33` | make_figure1.R hard-codes the node and edge counts it asserts and reports | yes | Duplicate of TH-17 (deferred). |
| DC-36 | Documentation and comments | `mindmap/source files/capture.js:1` | capture.js has no header, and package.json gives no way to run it |  | Resolved: capture.js has a header and package.json a capture script. |
| DC-38 | Documentation and comments | `mindmap/source files/capture.js:10` | The Chromium sandbox is disabled with no justification |  | Partly resolved: a TODO marks the undocumented sandbox flags. Deferred: the reason for disabling the sandbox is not recorded anywhere. |
| DC-41 | Documentation and comments | `README.md:35` | Root README describes five directional hypotheses; the protocol registers six, two of them two-sided |  | Resolved: the root README describes the six registered hypotheses. |
| DC-42 | Documentation and comments | `README.md:11` | Root README gives the age range as 7 to 10; the protocol uses bands 7-8 and 9 or older |  | Resolved: the root README gives the two age bands. |
| DC-43 | Documentation and comments | `README.md:43` | Root README names in-app quiz accuracy as a secondary outcome; the protocol makes no comprehension claim |  | Resolved: the root README gives log reading time per word and the difficulty rating as outcomes. |
| DC-44 | Documentation and comments | `README.md:11` | Root README's figures on languages, countries and sessions appear nowhere in the protocol and conflict with it |  | Resolved: the unsourced session, country and language figures were removed; restore them with a source if wanted. |
| DC-45 | Documentation and comments | `README.md:43` | Root README's inclusion rule of at least five sessions matches neither tier of the protocol |  | Resolved: the root README gives the two tiers' eligibility rules. |
| DC-46 | Documentation and comments | `README.md:29` | The root README's framework figure (mindmap.png) is superseded by the protocol's nomological net |  | Deferred: which figure the root README shows is the author's choice. |
| DC-47 | Documentation and comments | `README.md:51` | Root README says the data are nested and effects judged educationally meaningful; the protocol says crossed, with a conventional region of practical equivalence |  | Resolved: the root README describes crossed effects and the registered regions of practical equivalence. |
| DC-48 | Documentation and comments | `README.md:45` | Root README says all text indices, sentiment included, are reduced to composites; the protocol keeps affect separate and reduces within three families |  | Resolved: the root README describes the three components and the covariates. |
| DC-49 | Documentation and comments | `README.md:13` | Root README names Kinder as a funder, which conflicts with the draft competing-interests option denying Ferrero funding |  | Deferred: the funding arrangement and the competing-interests statement need the author. |
| DC-50 | Documentation and comments | `README.md:57` | Root README's contents section points to a private gitlink as an active area and omits the reproducible parts of the repository |  | Resolved: the root README describes the gitlink as a link to a private repository. |
| DC-53 | Documentation and comments | `preregistration/preregistration.qmd:439` | Code availability says session records beside every output record the versions used, but most outputs have none |  | Duplicate of RP-10 (deferred). |
| DC-54 | Documentation and comments | `preregistration/supplementary.qmd:137` | The supplement and protocol say the simulated models were fitted by maximum likelihood, but pilotr fits them by REML |  | Duplicate of DA-17 (resolved 17 September 2026). |
| DC-55 | Documentation and comments | `preregistration/cover_letter.md:77` | The cover letter says all analysis code is already public; the protocol says it will be public at submission, and the branch is unpushed |  | Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only. |
| DC-56 | Documentation and comments | `CHANGELOG.md:0` | No changelog records what changed between the dated protocol drafts |  | Duplicate of RS-18 (resolved). |
| DC-57 | Documentation and comments | `preregistration/README.md:1` | No glossary maps variable names across the Python, R, JSON, theory and manuscript layers |  | Duplicate of ST-22 (deferred). |
| ST-04 | Style and naming | `preregistration/design_analysis/solve_at_095.R:19` | Solver wrapper, progress logger and constants duplicated across the design-analysis scripts | yes | Duplicate of DA-33 (deferred). |
| ST-05 | Style and naming | `preregistration/design_analysis/run_ordinal_analysis.R:190` | run_ordinal_analysis.R and summarise_ordinal.R overwrite the same outputs with different schemas; run order undocumented | yes | Duplicate of DA-09 (partly). |
| ST-06 | Style and naming | `preregistration/design_analysis/run_ordinal_analysis.R:86` | Ordinal replicate fitter swallows errors without recording their cause, and an all-failed grid point vanishes | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| ST-07 | Style and naming | `preregistration/theory/build_theory.R:39` | build_theory.R can leave stale theory outputs in place without a message and diverts errors into tf_check.txt | yes | Duplicate of TH-09 (deferred). |
| ST-08 | Style and naming | `preregistration/_rename-output.R:8` | Quarto post-render hook ignores file.rename failure and still logs 'Renamed' |  | Duplicate of RS-01 (resolved). |
| ST-09 | Style and naming | `preregistration/theory/report_theory.R:1` | Three R scripts have no header saying what they do, how to run them, or what they write |  | Partly resolved: report_theory.R and _rename-output.R have headers. Deferred: diagram_theory.R waits on the decision in TH-11. |
| ST-10 | Style and naming | `preregistration/theory/diagram_theory.R:1` | diagram_theory.R looks like an undocumented exploratory probe (possible dead code) |  | Duplicate of TH-11 (deferred). |
| ST-11 | Style and naming | `preregistration/theory/check_manuscript_claims.R:5` | check_manuscript_claims.R never reads the manuscript, contrary to its header and the README |  | Duplicate of DC-03 (resolved). |
| ST-17 | Style and naming | `preregistration/design_analysis/run_design_analysis.R:71` | safe_workers() takes a spec argument it never uses |  | Duplicate of DA-13 (partly). |
| ST-18 | Style and naming | `preregistration/count_script/lets_story_summary.py:1688` | Count script computes time_verdict and never uses it; the comment above claims it keeps the outputs in agreement | yes | Duplicate of CS-13 (deferred). |
| ST-19 | Style and naming | `preregistration/count_script/lets_story_summary.py:907` | Public methods of the count script's Summary class, and several helpers, lack docstrings |  | Duplicate of CS-25 (deferred). |
| CR-01 | Completeness critic | `preregistration/supplementary.qmd:185` | Supplementary Table S8 activity-counter rows and the '438 seconds against 222' statement have no generating script, although the text says both tables can be regenerated from the count script |  | Resolved 17 September 2026: S8 credits the script only for the rows it generates and no longer quotes a reading time. |
| CR-02 | Completeness critic | `public_InTRACt.code-workspace:8` | The repository's literature-review gitlink records a three-month-old dirty checkout, while the tracked workspace file opens a newer sibling clone |  | Duplicate of RS-03 (deferred). |
| CR-05 | Completeness critic | `preregistration/check_reported_numbers.R:24` | check_reported_numbers.R hard-codes the journal's title and abstract limits instead of reading journal.json, which records them |  | Resolved: the limits are read from journal.json. |
| CR-08 | Completeness critic | `preregistration/title.tex:23` | title.tex calls \setstretch, which works only because preregistration.qmd sets linestretch; this coupling is undocumented |  | Partly resolved: the README documents the coupling between title.tex and linestretch. Deferred: title.tex itself is an end product. |
| CR-12 | Completeness critic | `preregistration/.gitignore:1` | Nothing ignores the count script's fixed output names, and the auto-sync process commits untracked files to a branch due to be public |  | Resolved: the root .gitignore excludes the count script's two output files. |

### MINOR (113)

| ID | Area | Location | Finding | HIGH-RISK | Status |
|---|---|---|---|---|---|
| DA-23 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:137` | A cached re-run does not byte-reproduce precision_sweep.csv or minimum_texts.csv | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| DA-24 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:167` | The tier-2 sweep labels readings per child as per_text and hard-codes 250 texts | yes | Resolved 17 September 2026: the tier-2 CSV records texts from the specification and per_child. |
| DA-25 | Design analysis | `preregistration/design_analysis/run_ordinal_analysis.R:132` | Ordinal script bypasses pilotr's replicate seeds and the JSON seed despite claiming 'the same seed discipline' |  | Resolved 17 September 2026: S5 describes the per-replicate seeding. |
| DA-26 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:144` | Replicate seeds are shared across grid points and between the null and alternative sweeps, which is undocumented |  | Resolved: the shared replicate seeds are documented in run_design_analysis.R and the README. |
| DA-27 | Design analysis | `preregistration/design_analysis/run_ordinal_analysis.R:150` | p_meaningful counts a determinate verdict in the wrong direction as a success for directional hypotheses | yes | Resolved 17 September 2026 for the ordinal sweep, which now counts only verdicts in the true direction. The lme4 sweeps are unchanged. |
| DA-28 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:48` | 'Twelve readings of each text' is a mean: each reader draws a text at random, giving 4 to 19 readings per text |  | Resolved 17 September 2026: the protocol, S5 and the figure subtitle say twelve readings per text on average. |
| DA-29 | Design analysis | `preregistration/design_analysis/tier1_developmental.json:22` | The simulated outcome is not exactly standardised once fixed-effect variance is included | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| DA-30 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:46` | The protocol says the tier-2 model 'added' terms to the tier-1 model, but F_T2 drops the age band and its interactions |  | Resolved 17 September 2026: the tier-2 model is described as simulated. |
| DA-31 | Design analysis | `preregistration/design_analysis/run_ordinal_analysis.R:43` | Magic numbers without a stated source: rated rate, replicate floors, seed offsets, grids and repeated 1.959964 literals |  | Resolved: the rating rate, rater floor, replicate floors and seed offsets carry their source or a TODO; the 1.959964 literals are left, as the fix advised. |
| DA-32 | Design analysis | `preregistration/design_analysis/summarise_ordinal.R:10` | summarise_ordinal.R header claims the grid tests the inverse-square-root law and omits prerequisites and outputs |  | Resolved: summarise_ordinal.R's header states its prerequisite, outputs and what the grid estimates. |
| DA-33 | Design analysis | `preregistration/design_analysis/solve_at_095.R:19` | The solver helper is copied into four scripts, and a Wilson interval is re-implemented without clamping | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| DA-34 | Design analysis | `preregistration/design_analysis/run_ordinal_analysis.R:122` | Several helper functions lack a one-line purpose comment |  | Partly resolved: msg, wilson and run_point have purpose comments. Deferred: read_sweep in solve_at_095.R and run_sweep's argument list remain. |
| DA-35 | Design analysis | `preregistration/design_analysis/run_ordinal.log:9` | The ignored run_ordinal.log is stale: it records an unfinished 3,200-text sweep from a superseded default grid |  | Deferred: run_ordinal.log is an ignored local file, and deleting it is the maintainer's call. |
| DA-36 | Design analysis | `preregistration/design_analysis/run_design_analysis.R:61` | at_effect silently leaves a zero coefficient at zero when the sign is kept |  | Deferred: the zero-coefficient assertion is a code edit in a script behind reported numbers, held back so this pass changed only comments there, and belongs with the sign-off on DA-03. |
| TH-22 | Theory object and checks | `preregistration/theory/intract.theory.yaml:501` | The yaml provenance log does not record the twelfth construct or propositions p15 to p18 |  | Deferred: the provenance entries for the twelfth construct and propositions p15 to p18 need the author's dates. |
| TH-23 | Theory object and checks | `preregistration/theory/make_figure1.R:1` | The nomological net is called Figure 1 in the script, the yaml and the file names, but it is Figure 2 |  | Resolved: script, yaml and README call the net Figure 2; the fig1_ file names are unchanged. |
| TH-24 | Theory object and checks | `preregistration/theory/build_theory.R:41` | theory/intract_nomological_net.svg is regenerated on every build but consumed by nothing |  | Resolved: the README describes the SVG and says the manuscript does not use it. |
| TH-25 | Theory object and checks | `preregistration/theory/check_manuscript_claims.R:48` | Hand-written dangling-reference loop duplicates tf_validate(full = TRUE) and covers less |  | Deferred: whether tf_validate() raises or returns on a dangling reference was not confirmed, so the replacement could fail open. |
| TH-26 | Theory object and checks | `preregistration/theory/make_figure1.R:124` | The regenerated Figure 2 PDF differs from the committed one on every run because cairo embeds CreationDate |  | Duplicate of RP-19 (deferred). |
| TH-27 | Theory object and checks | `preregistration/theory/build_theory.R:11` | Line endings of theory outputs and scripts depend on the platform and core.autocrlf, with no .gitattributes |  | Duplicate of RS-26 (deferred). |
| TH-28 | Theory object and checks | `preregistration/theory/make_figure1.R:57` | Styling constants in make_figure1.R carry no reason, and the minus glyph is a raw non-ASCII literal |  | Deferred: the reasons for the styling constants are not recoverable from the code or its history. |
| TH-29 | Theory object and checks | `preregistration/theory/make_figure1.R:121` | Figure 2 gets no text-size or colour check, unlike the other manuscript figures | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| TH-30 | Theory object and checks | `preregistration/check_reported_numbers.R:32` | Helper named get masks base::get in check_reported_numbers.R |  | Resolved: the helper is now row_of. |
| FL-12 | Figures and literature sizing | `preregistration/literature/replot_scopus_figures.R:55` | The figure check in replot_scopus_figures.R only warns, for every check, so failures never stop it | yes | Partly resolved: the README says the Scopus figure checks only warn. Deferred: making them fatal changes figure code and awaits sign-off. |
| FL-18 | Figures and literature sizing | `preregistration/literature/scopus_gap_analysis.R:3` | API key handling is sound, but the variable name is undocumented and a project .Renviron is not ignored |  | Resolved: the script header and README name SCOPUS_API_KEY, and the root .gitignore excludes .Renviron. |
| FL-20 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:28` | Dead lookup entries for CohPC_narr | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-21 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:87` | Unused log_x argument with a no-op else branch |  | Deferred: although the rewrite cannot change the figure, it is a code edit in a figure script, held back so this pass changed only comments there. |
| FL-22 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:91` | Stale comment on the numeric conversion of 'truth' |  | Resolved: the comment describes the conversion as it happens. |
| FL-23 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:133` | Main figure is saved before the supplement panels are checked | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-24 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:109` | Figure panel tags are uppercase, while both captions refer to lowercase panels | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| FL-25 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:53` | Magic numbers in the precision figure have no stated rationale |  | Deferred: the rationale for the figure constants is not recorded. |
| FL-26 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:56` | Palette comments misdescribe the colours as three, all taken from the Okabe-Ito set |  | Resolved: the palette comment lists the four colours and which are Okabe-Ito. |
| FL-28 | Figures and literature sizing | `preregistration/literature/replot_scopus_figures.R:1` | Script headers omit inputs, outputs, run order and, for replot, the working directory |  | Resolved: both Scopus script headers give inputs, outputs, run order and working directory. |
| FL-29 | Figures and literature sizing | `preregistration/figures/make_precision_figure.R:134` | The regenerated PDFs never match the committed files byte for byte, because cairo stamps a creation date |  | Duplicate of RP-19 (deferred). |
| FL-30 | Figures and literature sizing | `preregistration/downloaded_papers_zotero_keys/download_report.csv:1` | downloaded_papers_zotero_keys is an orphaned output with no generator, adding about 18 MB to history |  | Duplicate of RS-12 (deferred). |
| FL-31 | Figures and literature sizing | `preregistration/downloaded_papers_zotero_keys/download_report.csv:4` | download_report.csv exposes local filesystem paths and Zotero storage keys |  | Duplicate of RS-12 (deferred). |
| FL-32 | Figures and literature sizing | `preregistration/literature/replot_scopus_figures.R:66` | The three R scripts save, load and log in inconsistent ways | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| CS-15 | Count script | `preregistration/count_script/lets_story_summary.py:626` | Missing-value tokens are inconsistent: blank() treats NA and NULL as empty, time_class() calls them 'not a number', and nan, None and N/A count as values | yes | Resolved 17 September 2026 in version 2026-09-17: MISSING_TOKENS is used by blank() and by time_class(), so NA, NULL, N/A, NaN, None and a lone dash count as empty everywhere. |
| CS-16 | Count script | `preregistration/count_script/lets_story_summary.py:687` | parse_when reads any 10-digit number in the epoch range as Unix seconds, and mixes UTC epochs with as-logged ISO times | yes | Partly resolved 17 September 2026: the format each file's dates were read in is recorded per file, so a mix of as-logged timestamps and UTC epochs is visible. Reading a 10-digit number as an epoch is unchanged. |
| CS-17 | Count script | `preregistration/README.md:111` | README says a re-run reproduces the 6 August output 'line for line', but the run date is embedded, so one line always differs |  | Resolved: the README says one line, the run date, differs. |
| CS-18 | Count script | `preregistration/supplementary.qmd:185` | Supplementary S8 makes the same 'line for line' claim, which fails on the run-date row |  | Resolved 17 September 2026: S8 says line for line apart from the date of the run. |
| CS-19 | Count script | `preregistration/count_script/lets_story_summary.py:1954` | The manifest is written in text mode, so its bytes differ between Windows (CRLF) and POSIX (LF) runs; the 'identical page' claim holds only on one platform | yes | Resolved 17 September 2026 in version 2026-09-17: the manifest is written with newline="\n" on every platform. |
| CS-20 | Count script | `preregistration/count_script/lets_story_summary.py:1630` | --manifest-from writes into the working directory and overwrites the manifest it is meant to be compared with; short rows are dropped silently | yes | Resolved 17 September 2026 in version 2026-09-17: --manifest-from writes <input>_manifest_rebuilt.html beside its input and counts rows with fewer than five fields. |
| CS-21 | Count script | `preregistration/count_script/lets_story_summary.py:1639` | Ad hoc argv handling: --help and -h are treated as file names, and a malformed --manifest-from call reports a missing file | yes | Resolved 17 September 2026 in version 2026-09-17: --help, -h and --version work, options are validated, and an unknown option is refused. |
| CS-22 | Count script | `preregistration/count_script/HOW_TO_RUN.md:51` | HOW_TO_RUN promises outputs of 'a few tens of kilobytes', but the 35-row manifest is 99 KB and a synthetic 200,000-row summary is 370 KB |  | Not fixed, by decision (17 September 2026): the instruction sheet was not reissued, so that the data controller receives one file and no new instructions. The measured sizes are recorded in preregistration/README.md instead. |
| CS-23 | Count script | `preregistration/count_script/lets_story_summary.py:132` | 'Ten times wider than one another' and labels like '1 to 9' describe half-open decade bins loosely |  | Not fixed, by decision (17 September 2026): as CS-22, the sheet stands as sent. The half-open bands are described in the script's own header. |
| CS-24 | Count script | `preregistration/count_script/lets_story_summary.py:1171` | Stale or inaccurate comments on the KEEP scope, zip closing, lookup count and identifier caching |  | Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only. |
| CS-26 | Count script | `preregistration/count_script/lets_story_summary.py:1838` | Redundant logic: band lists written inline in emit alongside a _bands helper, Counters used as sets, and an always-true length check | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| CS-28 | Count script | `preregistration/count_script/lets_story_summary.py:966` | Files skipped as twins, zip archives with no CSV, and empty files are reported only on stdout, not in the summary data file | yes | Resolved 17 September 2026 in version 2026-09-17: every note about a skipped, empty or duplicate file is written into the summary data file as well as printed. |
| RS-08 | Repository structure | `preregistration/_rename-output.R:5` | Supplement outputs are overwritten undated while protocol outputs are dated |  | Partly resolved: the hook header and README state that the supplement is overwritten. Deferred: whether to date the supplement too is a maintainer decision. |
| RS-19 | Repository structure | `preregistration/preregistration_files/libs/quarto-html/quarto-syntax-highlighting-7f8f88aac4f3542376d5c11b86a4c14d.css:1` | Quarto HTML libraries are tracked, including superseded CSS hashes that old drafts still load |  | Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only. |
| RS-20 | Repository structure | `mindmap/source files/capture_output.txt:2` | capture_output.txt records a save path in a different checkout |  | Deferred: capture_output.txt is a stale log; removing or regenerating it is the maintainer's call. |
| RS-23 | Repository structure | `preregistration/InTRACt references.bib:1` | Spaces and mixed naming conventions in paths |  | Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only. |
| RS-24 | Repository structure | `preregistration/check_reported_numbers.R:1` | Checker and render hook sit at the preregistration root, apart from the other scripts |  | Deferred: moving the scripts changes every documented command. |
| RS-25 | Repository structure | `CITATION.cff:1` | No CITATION.cff |  | Deferred: CITATION.cff needs author metadata (co-authors, ORCIDs). |
| RS-26 | Repository structure | `.gitattributes:1` | No .gitattributes; working-tree line endings are mixed |  | Deferred: a .gitattributes line-ending policy renormalises tracked files, end products included. |
| RS-27 | Repository structure | `.claude/worktrees/goofy-chandrasekhar-cae89e:1` | A second git worktree lives inside the repository tree, hidden only by a local exclude |  | Deferred: the worktree under .claude/worktrees is local state that only its owner should remove. |
| RS-28 | Repository structure | `preregistration/theory/build_theory.R:5` | build_theory.R header lists a file it never writes, and a second nomological-net SVG sits beside Figure 2 |  | Resolved: see TH-10. |
| RP-15 | Reproducibility | `preregistration/design_analysis/session_info.txt:1` | No output records the version or checksum of the inputs it came from, and the working-tree theory YAML and bib differ from HEAD with their regenerated outputs uncommitted |  | Deferred: a checksum manifest of inputs should be taken once the working-tree edits are committed, so it describes a committed state. |
| RP-17 | Reproducibility | `preregistration/count_script/HOW_TO_RUN.md:7` | The count script's 'Python 3.8 or later' requirement has been checked statically but never at run time |  | Deferred: no Python 3.8 interpreter is available here to test the stated minimum. |
| RP-18 | Reproducibility | `mindmap/source files/package.json:14` | Node: the lockfile pins puppeteer, but no Node version is recorded, node_modules is tracked, and capture_output.txt records a path from another checkout |  | Duplicate of RS-04 (deferred). |
| RP-19 | Reproducibility | `preregistration/design_analysis/run_design_analysis.R:227` | Timestamps embedded in generated files defeat byte-identical comparison of session records, figures and rendered documents |  | Deferred: removing the timestamps changes generated files; the alternative is a documented tolerance for those lines. |
| RP-20 | Reproducibility | `preregistration/design_analysis/solve_at_095.R:1` | autocrlf without a .gitattributes file: outputs are CRLF on disk but LF in git, so regenerated files match the working tree but not the git blobs |  | Duplicate of RS-26 (deferred). |
| RP-21 | Reproducibility | `preregistration/design_analysis/run_design_analysis.R:127` | The same replicate seeds are reused at every grid point and across the alternative, null and readings sweeps, and nothing documents it |  | Duplicate of DA-26 (resolved). |
| RP-22 | Reproducibility | `preregistration/design_analysis/run_design_analysis.R:66` | The safe_workers comment describes a fallback the code does not implement, and each grid point starts a fresh worker cluster |  | Duplicate of DA-13 (partly). |
| RP-23 | Reproducibility | `preregistration/README.md:66` | The ordinal script reads two environment variables the README does not mention |  | Duplicate of DA-20 (resolved). |
| RP-24 | Reproducibility | `preregistration/theory/build_theory.R:5` | build_theory.R's header lists an output file the script never writes |  | Duplicate of TH-10 (resolved). |
| RP-25 | Reproducibility | `preregistration/design_analysis/run_ordinal_analysis.R:3` | run_ordinal_analysis.R says to run it after run_design_analysis.R, though it reads nothing that script writes |  | Resolved: run_ordinal_analysis.R's header gives the real run order. |
| RP-26 | Reproducibility | `preregistration/_rename-output.R:1` | Draft file names come from the render date, not the content, so dated drafts accumulate |  | Duplicate of RS-06 (deferred). |
| DC-16 | Documentation and comments | `preregistration/README.md:70` | The README says every analysis script is already run against simulated data, but no outcome-model scripts exist yet |  | Duplicate of DA-21 (resolved). |
| DC-17 | Documentation and comments | `preregistration/README.md:53` | The README row for run_design_analysis.R omits two sweeps and overstates what is solved |  | Resolved: the README row lists all five sweeps. |
| DC-18 | Documentation and comments | `preregistration/README.md:107` | README calls the count script's nineteen columns categorical, but they include an identifier, a timestamp and numeric page counts |  | Resolved: the README describes the nineteen columns accurately. |
| DC-19 | Documentation and comments | `preregistration/preregistration.qmd:226` | The protocol describes the count script as reading nineteen categorical columns |  | Resolved 17 September 2026: the protocol says nineteen columns besides the outcome. |
| DC-22 | Documentation and comments | `preregistration/count_script/lets_story_summary.py:1607` | Text the count script writes into its output still refers to 'either hypothesis', from when there were two |  | Resolved: the README notes the 'either hypothesis' wording; the supplied script is unchanged. |
| DC-23 | Documentation and comments | `preregistration/README.md:107` | README asserts the count script is the version supplied but records no checksum to prove it |  | Duplicate of RS-16 (deferred). |
| DC-24 | Documentation and comments | `preregistration/README.md:93` | README does not say that the Scopus figure checks are non-fatal, unlike the precision figure checks |  | Resolved: the README says the Scopus figure checks only warn. |
| DC-26 | Documentation and comments | `preregistration/design_analysis/run_design_analysis.R:20` | Comment says the simulation's missing child intercept matches the real fit, but the protocol may add one |  | Resolved: the comment states when the omitted child intercept matches the real fit. |
| DC-27 | Documentation and comments | `preregistration/design_analysis/run_ordinal_analysis.R:25` | Ordinal script comments misstate the region bounds, the effect-to-region ratio and the seed discipline |  | Resolved: the region bounds, effect ratio and seed wording are corrected. |
| DC-28 | Documentation and comments | `preregistration/design_analysis/run_ordinal_analysis.R:78` | Unexplained magic numbers in the ordinal replicate loop | yes | Duplicate of DA-07 (partly). |
| DC-30 | Documentation and comments | `preregistration/figures/make_precision_figure.R:55` | Stale colour comment and incomplete header in make_precision_figure.R |  | Duplicate of FL-26 (resolved). |
| DC-31 | Documentation and comments | `preregistration/figures/make_precision_figure.R:118` | Print widths used for the figure type-size audit have no cited source |  | Duplicate of FL-14 (deferred). |
| DC-32 | Documentation and comments | `preregistration/literature/replot_scopus_figures.R:29` | replot_scopus_figures.R says its palette is Okabe-Ito, but two of the six colours are not |  | Resolved: the palette comment is corrected. |
| DC-33 | Documentation and comments | `preregistration/figures/make_precision_figure.R:93` | Warnings and messages suppressed without saying what is suppressed or why | yes | Duplicate of ST-24 (deferred). |
| DC-34 | Documentation and comments | `preregistration/theory/make_figure1.R:1` | make_figure1.R header calls the nomological net Figure 1, but the manuscript numbers it Figure 2 |  | Duplicate of TH-23 (resolved). |
| DC-37 | Documentation and comments | `mindmap/source files/capture.js:17` | capture.js comment says the HTML is loaded as a data URL, but the code uses setContent |  | Resolved: the setContent comment is corrected. |
| DC-39 | Documentation and comments | `mindmap/source files/capture_output.txt:2` | capture_output.txt records a run from the repository's old folder name |  | Duplicate of RS-20 (deferred). |
| DC-40 | Documentation and comments | `preregistration/theory/make_figure1.R:22` | A few comments restate the code, as section markers or step labels |  | Resolved: the restating comment was rewritten as a reason. |
| DC-51 | Documentation and comments | `README.md:69` | The issue-tracker link in the root README is relative and does not resolve |  | Resolved: the issue-tracker link is absolute. |
| DC-52 | Documentation and comments | `README.md:3` | The root README's prose style is inconsistent with the project's other documentation |  | Resolved: the root README was rewritten in the register of the other documentation. |
| ST-12 | Style and naming | `.gitattributes:0` | No .gitattributes: working-tree line endings depend on each clone's autocrlf and are already split between LF and CRLF |  | Duplicate of RS-26 (deferred). |
| ST-13 | Style and naming | `preregistration/design_analysis/solve_at_095.R:45` | Three files mix LF and CRLF within the same file |  | Duplicate of RS-26 (deferred). |
| ST-14 | Style and naming | `.lintr:0` | No committed linter or formatter configuration for R, Python, Node or editors |  | Deferred: committing formatter configuration comes with the formatting pass in ST-15. |
| ST-15 | Style and naming | `preregistration/design_analysis/run_ordinal_analysis.R:103` | lintr style lints across the R scripts (line length, indentation, infix spacing, semicolons, braces) |  | Deferred: styler is not installed, and a formatting-only commit should follow the sign-off on the logic changes. |
| ST-16 | Style and naming | `preregistration/figures/make_precision_figure.R:68` | All nine object_usage_linter hits are ggplot2 aes() false positives; no undefined variable found |  | No change needed: the nine object_usage_linter hits are ggplot2 aes() false positives, so no variable is undefined. |
| ST-20 | Style and naming | `preregistration/count_script/lets_story_summary.py:1148` | Count script naming and minor style: single-letter capitals, capitalised locals, inconsistent private prefix |  | Duplicate of CS-25 (deferred). |
| ST-21 | Style and naming | `preregistration/check_reported_numbers.R:32` | R naming inconsistencies and local names that mask base or graphics functions |  | Partly resolved: the helper that masked base::get was renamed. Deferred: the remaining naming lints belong to the formatting pass (ST-15). |
| ST-22 | Style and naming | `preregistration/design_analysis/tier1_developmental.json:18` | The same entities carry different names across the export, specs, R code, theory object and manuscript, with no glossary |  | Deferred: the canonical names need the author's choice; the proposed glossary is in the fix below. |
| ST-23 | Style and naming | `preregistration/literature/replot_scopus_figures.R:55` | Mixed failure and logging idioms: stop, quit, warning and NULL-returning tryCatch; cat to stdout for progress |  | Duplicate of FL-32 (deferred). |
| ST-24 | Style and naming | `preregistration/figures/make_precision_figure.R:93` | Figure script coerces the truth column with warnings suppressed; a partial coercion failure drops rows without notice | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| ST-25 | Style and naming | `mindmap/source files/capture.js:9` | capture.js passes the legacy headless: 'new' value and disables the Chromium sandbox |  | Deferred: changing the headless value or the sandbox flags needs a capture run with network access to confirm the figure is unchanged. |
| ST-26 | Style and naming | `mindmap/source files/capture.js:17` | capture.js comment says the page is loaded as a data URL; the code uses page.setContent |  | Duplicate of DC-37 (resolved). |
| ST-27 | Style and naming | `mindmap/source files/capture.js:29` | process.exit(1) inside try bypasses the finally block that closes the browser |  | Resolved: capture.js sets process.exitCode so the finally block runs; node --check passes. |
| ST-28 | Style and naming | `mindmap/source files/mindmap.html:9` | Mindmap rendering depends on unpinned remote Google Fonts fetched at capture time |  | Duplicate of RS-17 (partly). |
| ST-29 | Style and naming | `mindmap/source files/capture_output.txt:2` | capture_output.txt records an old repository path and carries a byte-order mark |  | Duplicate of RS-20 (deferred). |
| ST-30 | Style and naming | `mindmap/source files/package.json:5` | Mindmap package.json keeps npm init placeholders and has no script for the capture |  | Resolved: package.json names capture.js and adds npm run capture. |
| ST-31 | Style and naming | `preregistration/design_analysis/run_ordinal_analysis.R:100` | Several script-local R helpers have no purpose comment |  | Duplicate of DA-34 (partly). |
| CR-03 | Completeness critic | `preregistration/design_analysis/run_design_analysis.R:100` | run_design_analysis.R labels grid points by row count and discards pilotr's own grid column, which would label them directly | yes | Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off. |
| CR-04 | Completeness critic | `preregistration/design_analysis/run_design_analysis.R:172` | Singular and non-converged fits at two readings per text are counted in the quoted precision without disclosure, and the pooled grid drops the warning and attempt counts | yes | Partly resolved 17 September 2026: S5 discloses the four singular fits at two readings per text. Deferred: the pooled CSV still omits the attempt and warning columns. |
| CR-06 | Completeness critic | `preregistration/README.md:5` | The reference-style record in journal.json contradicts the README and the manuscript's APA 7 setting, and nature.csl is used by nothing |  | Deferred: journal.json records the journal's own style, and reverting to APA 7 was a deliberate decision. |
| CR-07 | Completeness critic | `preregistration/InTRACt references.bib:1` | Over half the bibliography is uncited: 322 of 591 entries appear in neither the protocol, the supplement nor the cover letter |  | Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only. |
| CR-09 | Completeness critic | `preregistration/figures/make_precision_figure.R:131` | Every figure script writes a PNG that no document uses, and the stated reason (a repository preview) does not exist |  | Partly resolved: make_precision_figure.R's comment no longer claims a repository preview. Deferred: whether to stop writing the unused PNGs is a maintainer decision. |
| CR-10 | Completeness critic | `preregistration/README.md:94` | The README says every claim in evidence_notes.md carries a DOI, but many cite by author and year only |  | Resolved: the README says most claims cite a DOI. |
| CR-11 | Completeness critic | `preregistration/count_script/lets_story_summary.py:1` | The count script supplied to the data controller is the CRLF copy, but git stores LF, so a checksum taken from a clone will not match |  | Duplicate of RS-16 (deferred). |

## Details

<details><summary><b>DA-01</b> (BLOCKING, HIGH-RISK): Tier-2 simulation gives each child 25 readings, each text read at all five session positions, not five readings on distinct texts</summary>

Location: `preregistration/design_analysis/tier2_within_child.json:11`. Verifier's verdict: confirmed.

Impact: The within-child trend is estimated from 25 rows per child, with text identity perfectly balanced across session order. That design is far richer than five sessions on distinct texts, so the quoted 563 (463 to 674) and 681 (543 to 834) are most likely optimistic on this count. The net error once DA-02 is also taken into account has not been established. The figures do not describe the registered tier-2 design.

Proposed fix: Needs a maintainer decision, and must be applied together with DA-02, never alone: my synthetic check shows each fix on its own moves the SE by a factor of about 2.3, in opposite directions. Respecify tier 2 so each child reads per_subject distinct texts, each at one session position, either by deriving the session position from the item slot or by extending pilotr so a within factor is spread across item slots and not crossed with them. Assert `all(table(d$subject) == t2$units$item$per_subject)` on one replicate before sweeping. Clear sweeps/t2_children.csv, re-run, re-solve at 0.90 and 0.95, then propose the revised figures for qmd:129, qmd:302, supp:139 and supp:141.

Status: Resolved 17 September 2026: each child now reads five distinct texts in a random order, one per session position, with guards; the tier-2 sweep was re-run (609 children at 0.90, 731 at 0.95) and the protocol and supplement updated.

</details>

<details><summary><b>DA-02</b> (BLOCKING, HIGH-RISK): Accumulated-reading contrast has SD 0.45, so the simulated coefficient is not on the per-SD unit the protocol registers</summary>

Location: `preregistration/design_analysis/tier2_within_child.json:12`. Verifier's verdict: confirmed.

Impact: A true coefficient of -0.10 per unit of a predictor with SD 0.45 is -0.045 per SD. On the registered per-SD scale, an effect of 0.10 against a ROPE of 0.05 would tolerate a standard error about 2.2 times larger, which is roughly one fifth of the children under a square-root law with all else equal. The quoted 563 and 681 therefore answer a different estimand. This error pulls the opposite way to DA-01, so the net error is unknown.

Proposed fix: Apply together with DA-01. Rescale the contrast to unit within-child SD, [-1.414, -0.707, 0, 0.707, 1.414], so the coefficient is per SD as qmd:188 registers. Otherwise state the per-contrast-unit scale in the spec, in the header and in supplement S5, and reconcile it with qmd:188. Re-run tier 2 once both fixes are in place and propose the revised figures.

Status: Resolved 17 September 2026 with DA-01: the contrast has a population SD of 1, so the coefficient is per SD.

</details>

<details><summary><b>DA-03</b> (BLOCKING, HIGH-RISK): Sweep caches are keyed only on file name, so edited specs, replicate counts, ROPE or rating rate silently reuse stale results</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:90`. Verifier's verdict: confirmed.

Impact: preregistration.qmd:308 registers re-runs at observed inputs: rating availability, category proportions, sessions per child, and a pooled effect below 0.10. Unless someone clears sweeps/ by hand, those re-runs silently return the archived numbers together with a fresh session record. That is a plausible-looking wrong answer at exactly the gates the protocol relies on.

Proposed fix: Store a key file beside each cache file. For run_sweep, deparse the spec, n_sims, ROPE, values, focal, formula and packageVersion('pilotr'). For run_point, include RATED, MIN_RATERS, TRUE_B, ROPE, N_SIMS and the spec. Reuse the cache only when the key matches, and otherwise stop with a message saying which file to delete. In summarise_ordinal.R, stop unless rated_rate, min_raters and n_sims each take a single value. Until then, state in both headers and in the README that sweeps/ must be cleared after any change to a spec or setting.

Status: Partly resolved: the file-name-only cache is stated in both script headers and the README. Deferred: a cache key that stops on a mismatch is a logic change in code behind reported numbers, so it awaits sign-off.

</details>

<details><summary><b>DA-04</b> (BLOCKING, HIGH-RISK): Ordinal projection ignores the attenuation caused by the omitted child intercept, understating the quoted requirement by about 12 per cent</summary>

Location: `preregistration/design_analysis/summarise_ordinal.R:31`. Verifier's verdict: confirmed.

Impact: On this correction alone the quoted H5 projection understates the requirement: about 9,000 to 9,800 generated texts and 2,600 to 2,900 qualifying texts. The 'upper bound' reasoning is wrong for H5.

Proposed fix: In run_point, record mean(est) and sd(est) per parameter and grid point, re-run the ordinal sweep, and project from the mean fitted |estimate| in place of TRUE_B. As an interim step, apply the attenuation factor explicitly with a comment citing the approximation. Propose revised H5 figures for qmd:128 and supp:145. Qualify the upper-bound sentence at qmd:298 as describing the Gaussian models, and state that for H5 the omitted child variance attenuates the coefficient.

Status: Resolved 17 September 2026: the projection uses the analytic attenuation factor (Zeger, Liang and Albert, 1988), checked against the mean fitted estimates; it is now 9,300 to 10,300 generated texts.

</details>

<details><summary><b>DA-05</b> (BLOCKING, HIGH-RISK): Ordinal fits with non-finite SEs are boundary fits, not a random subset, and their share falls from 23 to 2 per cent across the grid</summary>

Location: `preregistration/design_analysis/run_ordinal_analysis.R:144`. Verifier's verdict: confirmed.

Impact: The mean widths at the small grid points, and the fitted exponent of -0.51 to -0.53 that feeds the extrapolated 8,000 to 8,700 figure, can be biased by informative exclusion. The diagnostics suggest the dropped fits would have had smaller SEs, which would steepen the exponent and understate the projection, on top of DA-04. Ten replicates do not establish that direction.

Proposed fix: Keep boundary replicates. Where vcov is undefined, refit without the text term using ordinal::clm, or take the fixed-effect SEs with the variance held at zero, and count these as n_boundary. Report the projection with and without them, re-run the ordinal sweep, and propose a disclosure sentence for supp:143.

Status: Resolved 17 September 2026: boundary replicates are refitted as the fixed-effects cumulative logit and kept; none is discarded.

</details>

<details><summary><b>DA-18</b> (BLOCKING): The number-check gate covers a few design-analysis figures and matches bare substrings, so it can pass while quoted numbers are wrong</summary>

Location: `preregistration/check_reported_numbers.R:41`. Verifier's verdict: confirmed.

Impact: The gate described as able to 'gate a commit' would pass while most design-analysis figures were wrong, and DA-01, DA-02 and DA-04 will change several of them.

Proposed fix: Match each value in its sentence, or with boundary-anchored regular expressions such as grepl('(?<![0-9,])738(?![0-9])', qmd, perl = TRUE). Add checks for minimum_texts_095.csv, sweeps/dev_texts_null.csv, sweeps/dev_readings.csv and sweeps/ordinal_texts.csv, and read supplementary.qmd as well as the protocol. This is a non-end-product script, but choosing which figures to cover needs the maintainer.

Status: Partly resolved: the gate anchors numbers and now covers the 0.95 requirements and the main effects. Deferred: it does not read the supplement or check the null, readings and ordinal sweep tables; choosing that coverage needs the maintainer.

</details>

<details><summary><b>TH-01</b> (BLOCKING): check_manuscript_claims.R never reads the manuscript, so it cannot fail on any quoted theory number</summary>

Location: `preregistration/theory/check_manuscript_claims.R:1`. Verifier's verdict: confirmed.

Impact: The object can gain or lose a construct, an edge, a diagnostic prediction or an implication, or the supplement can be edited, and the script still exits 0. The header and README tell a reviewer the comparison is made.

Proposed fix: Make one script own the comparison, to avoid two drifting checkers. Extend check_reported_numbers.R, which already reads the qmd, with a second haystack for supplementary.qmd and anchored phrases built from the object: sprintf('%s of the eighteen', ...), 'seven of the ten', sprintf('%.1f out of 100', score), sprintf('similarity %.2f', max(red$similarity)), 'thirty of them'. Map numbers to words with a lookup vector and fail on absence. Then rewrite check_manuscript_claims.R:1-8 and README.md:33 to say that script prints the object's numbers and fails only on dangling references.

Status: Partly resolved: the script's header and the README say it never reads the manuscript, and check_reported_numbers.R now compares the score and four counts. Deferred: the thirty implications, the 0.17 similarity and the diagnostic-prediction counts are still compared by eye; the phrases to anchor need the maintainer.

</details>

<details><summary><b>TH-04</b> (BLOCKING): check_reported_numbers.R leaves most quoted precision numbers and the whole supplement unchecked</summary>

Location: `preregistration/check_reported_numbers.R:10`. Verifier's verdict: confirmed.

Impact: A re-solve of the 0.95 curves, or of the SynPC or CohPC main effects, or any edit to the supplement, drifts silently while the gate prints a full pass.

Proposed fix: Add the developmental SynPC and CohPC rows to the spec list. Add a loop over minimum_texts_095.csv using anchored phrases (see TH-03). For NA rows such as CohPC_age, check the refusal sentence at qmd:126 instead of skipping. Read supplementary.qmd into a second haystack with expectations for the 0.95 intervals at :141 and the theory numbers at :35-39. Consolidate with TH-01 so only one script compares theory numbers.

Status: Partly resolved: the 0.95 requirements and the grammatical and continuity main effects are now checked. Deferred: the supplement is not read.

</details>

<details><summary><b>TH-06</b> (BLOCKING, HIGH-RISK): Figure 2 content assertion ignores the rank and invisible-edge lines, so a stale id draws a phantom node while the assertion passes</summary>

Location: `preregistration/theory/make_figure1.R:93`. Verifier's verdict: confirmed.

Impact: Renaming a construct can produce a plausible-looking Figure 2 with an extra box labelled by a stale identifier, and the assertion described as guaranteeing content equivalence passes.

Proposed fix: After building styled, extract every quoted construct id from the whole DOT string, invisible and rank lines included: ids <- unique(gsub('"', '', regmatches(styled, gregexpr('"c_[A-Za-z0-9_]+"', styled))[[1]])); stopifnot(setequal(ids, nodes$id)). Build the rank rows and the invisible edge from named vectors checked with stopifnot(all(c(rank_ids, invis_ids) %in% nodes$id)). Guards only, since the current figure is unchanged, but it is figure code and needs sign-off.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>TH-07</b> (BLOCKING, HIGH-RISK): The quoted rigour score depends on an unpinned, locally built theoryforge with no lockfile or version assertion</summary>

Location: `preregistration/theory/build_theory.R:7`. Verifier's verdict: confirmed.

Impact: A different build of theoryforge 0.6.0, or a later release with a revised checklist, can yield a different score or implication set. Nothing records which source produced the deposited outputs.

Proposed fix: Create an renv lockfile covering theoryforge, pilotr, depictr, scopusflow, DiagrammeR, DiagrammeRsvg, rsvg and V8, installing theoryforge from the archived release behind DOI 10.5281/zenodo.21229964 (README.md:128) so the lock records its source. Add stopifnot(packageVersion('theoryforge') == '0.6.0') after library(theoryforge) in build_theory.R, check_manuscript_claims.R and make_figure1.R, and before line 80 of check_reported_numbers.R. Recording an md5 of rigor_checklist.yaml in tf_check.txt would change an end product and needs sign-off.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-01</b> (BLOCKING, HIGH-RISK): replot_scopus_figures.R strips the plot caption that reports omitted counts and never checks the archived CSVs for missing values</summary>

Location: `preregistration/literature/replot_scopus_figures.R:37`. Verifier's verdict: confirmed.

Impact: After any rerun where a year-topic count comes back missing, the supplementary trend figure would draw an unbroken line through the missing year with no note anywhere. In the gap figure a missing count would be dropped exactly as the legitimate empty three-way intersection is, so the two cases look the same. The result is a plausible figure that is wrong.

Proposed fix: In replot_scopus_figures.R, after line 62 add stopifnot('gap counts contain NA' = !anyNA(ints$n)). After line 72 add stopifnot('trend counts or shares contain NA' = !anyNA(cmp$n), !anyNA(cmp$reference_n), !anyNA(cmp$comparison_percentage[cmp$query_type == 'comparison'])). The last condition also catches a zero reference count. Add the same guard at the source in scopus_gap_analysis.R (see FL-08). Neither changes the current figures.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>CS-01</b> (BLOCKING, HIGH-RISK): Float-formatted user_id values silently merge or split accounts, with no detection or warning</summary>

Location: `preregistration/count_script/lets_story_summary.py:1265`. Verifier's verdict: confirmed.

Impact: A full export written like the sample collapses distinct children into one account. Distinct accounts, sessions per account, repeat readings, account span, active months and speech consistency are then all wrong, and nothing flags it. Mixed spellings across parts (integer in one, .0 in another) split one child into two. H6's within-child terms depend on these counts.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION. Leave the counts as they are and add a detector. Count user_id and story_id values matching `^[+-]?\d+(\.\d+)?[eE][+-]?\d+$` or `^\d+\.0+$`, write the count as a file-record row, and print a stdout warning when it is non-zero. The primary remedy stays outside the script: Gameloft exports user_id as text (open author item).

Status: Resolved 17 September 2026 in version 2026-09-17: identifiers in scientific notation are counted and reported, the account figures are marked unreliable, and the instruction sheet asks for integers or text. The lost digits cannot be recovered.

</details>

<details><summary><b>CS-02</b> (BLOCKING, HIGH-RISK): A part without a header row has its first data row, including a reading time and a user_id, written to the summary data file as column names</summary>

Location: `preregistration/count_script/lets_story_summary.py:1764`. Verifier's verdict: confirmed.

Impact: Splitting a large export by line count is a common way to deliver it, and it leaves every part after the first without a header. The deliverable sent to Oxford (and planned for deposit) would then carry one raw session: an account ID, timestamp, country, age band and an exact reading time. That breaks the sequestration promise. The headerless part's rows are also counted as unattributable sessions, and its first row is lost.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION. In process_source, stop with sys.exit when a source's header matches none of the KEEP names or lacks user_id, and write none of its cells. The message should ask for the header to be repeated in every part. As a second guard, from the second source on, stop if the header does not match the first source's header as a set of names, ignoring case.

Status: Resolved 17 September 2026 in version 2026-09-17: a file whose first line is not a header stops the run, named, with nothing written.

</details>

<details><summary><b>CS-03</b> (BLOCKING, HIGH-RISK): If one part lacks time_spent_reading, the reading-time verdict reports all sessions usable while covering only a subset, and the absence is not recorded</summary>

Location: `preregistration/count_script/lets_story_summary.py:1675`. Verifier's verdict: confirmed.

Impact: The one check on the outcome variable can pass silently. The green verdict reads as covering the export when half the sessions were never checked.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION. Record TIME_COL in each file's absent list, and count rows from a file that lacks the column under a fifth unusable label ("column not in this file"). Base both verdicts on the total data rows, so a good verdict requires usable to equal allr["n_rows"].

Status: Resolved 17 September 2026 in version 2026-09-17: the verdict names the sessions the check could not cover, and the per-file record states whether each file carries the column.

</details>

<details><summary><b>CS-04</b> (BLOCKING, HIGH-RISK): An unclosed quote silently swallows later rows; the raised csv field limit removes the only loud failure, and the skipped-row count reports 0 or 1</summary>

Location: `preregistration/count_script/lets_story_summary.py:175`. Verifier's verdict: confirmed.

Impact: One field that opens with a stray quote makes the parser absorb every following line until the next quote character, possibly to the end of the file. Sessions, accounts and texts are undercounted without warning, and the integrity count meant to expose quoting problems reads 0 or 1. With the default field limit (131,072 characters), a runaway of any size would have raised csv.Error.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION. Track reader.line_num in process_source, and report records spanning more than one physical line and the physical lines they absorbed, as file-record rows with a stdout warning when non-zero. Do not reject such records outright, since clean() at 583-585 implies multi-line quoted fields were anticipated. Restoring a lower field_size_limit only guards against very long runaways, and it needs a maintainer check that no legitimate field (for example the *_ts columns) exceeds it.

Status: Resolved 17 September 2026 in version 2026-09-17: the field limit is back to 1 MB, every physical line is accounted for against the rows read, and a mismatch stops the run before anything is written.

</details>

<details><summary><b>CS-06</b> (BLOCKING, HIGH-RISK): A blank story_id silently falls back to story_title, which in this export is a two-value category, distorting distinct texts and hiding missing story identifiers</summary>

Location: `preregistration/count_script/lets_story_summary.py:1267`. Verifier's verdict: confirmed.

Impact: In this export story_title does not identify a text. Every crafted session with a blank story_id would be pooled into one pseudo-text, and an ID string and a title string for the same text count as two texts. Memory and the protocol say precision is governed by the number of distinct texts, and this count could be wrong without any integrity row showing it.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION. Treat a blank story_id as missing: count it in no_text_id and keep it out of the text tallies. Add a separate row "sessions with no story_id but a story_title", and state the rule in a comment at 1266.

Status: Resolved 17 September 2026 in version 2026-09-17: an empty story_id is counted as one, the title no longer stands in for it, and rows with a title but no identifier are reported.

</details>

<details><summary><b>RS-02</b> (BLOCKING): Code availability URL leads to a default branch without the code; working branch has no upstream</summary>

Location: `preregistration/preregistration.qmd:439`. Verifier's verdict: confirmed.

Impact: Anyone following the statement today, including an editor or reviewer, finds none of the code the protocol says can be reproduced now. The only copy of the theory object, design analysis, count script and supplement is an unpushed local branch plus uncommitted edits, so a disk or sync failure would lose them. The 15 commits unique to origin/main (drafts 06-07 to 06-15, embed-resources, render workflow) will conflict at merge.

Proposed fix: Maintainer, in order. (1) Before any push, decide RS-12 and RS-03. The publisher PDFs sit in unpushed commit c96726f, so remove them from the local branch history, for example with git filter-repo --path preregistration/downloaded_papers_zotero_keys --invert-paths on a fresh clone, rather than only untracking them. (2) Commit the working-tree edits and git push -u origin wip/bib-2026-07-21. (3) Reconcile with origin/main through a pull request. (4) Tag the submitted commit and archive it on Zenodo. Proposal only for the end product: cite that tag or DOI in the Code availability statement.

Status: Deferred: the author must push the branch, after deciding RS-12 and RS-03, and reconcile it with origin/main.

</details>

<details><summary><b>RP-01</b> (BLOCKING): No R lockfile: the R environment cannot be rebuilt, so the strict rebuild-and-compare gate is unattainable</summary>

Location: `preregistration/README.md:127`. Verifier's verdict: confirmed.

Impact: The protocol's precision numbers, theory scores and figures cannot be regenerated in a rebuilt environment. Every run in this audit used the installed user library at <local path> so a pass shows only that this one machine is consistent with itself.

Proposed fix: Work on a copy of preregistration/ with R 4.6.1. Run renv::init(), which copies CRAN and RSPM packages from the user library at their installed versions with no download. The four study packages carry no Remote fields, so renv will record them with an unknown source and renv::restore() would fail for them. Give each one an explicit source before renv::snapshot(): a tagged GitHub ref, using the subdirectory form if the R package sits under r/ as the pkgdown URL https://pablobernabeu.github.io/pilotr/r/ suggests, or a version-specific Zenodo tarball. Commit renv.lock, .Rprofile, renv/activate.R and renv/settings.json, and put renv::restore() in README.md before the first Rscript command. Run the rebuild-and-compare only in a scratch copy, because the scripts overwrite committed outputs.

Status: Deferred: renv::init() would record the four study packages with no source, so their sources (tagged releases behind the Zenodo DOIs) must be chosen first.

</details>

<details><summary><b>DA-06</b> (MAJOR, HIGH-RISK): n_warned cannot register the ordinal failure mode: summary.clmm warnings fall outside the handler and no convergence field is read</summary>

Location: `preregistration/design_analysis/run_ordinal_analysis.R:90`. Verifier's verdict: confirmed.

Impact: The committed zeros read as a clean bill of health, but the diagnostic is blind to the one failure mode that occurs. Under parLapply the summary warnings are also lost on the workers.

Proposed fix: Wrap summary() in the same withCallingHandlers. Per replicate, record max(abs(fit$gradient)), fit$optRes$convergence and the text variance from VarCorr(fit), and add an n_boundary column for variances below 1e-6. This changes the cached columns and the n_warned values, so a re-run is needed.

Status: Resolved 17 September 2026: summary() runs inside the warning handler.

</details>

<details><summary><b>DA-07</b> (MAJOR, HIGH-RISK): Discarded ordinal replicates (NULL returns) are not counted, and their 50-row and 10-text floors are undocumented</summary>

Location: `preregistration/design_analysis/run_ordinal_analysis.R:78`. Verifier's verdict: confirmed.

Impact: In the registered re-run at the observed, possibly lower, availability, whole replicates can drop out of the p_meaningful denominator unseen, inflating it.

Proposed fix: Add an explicit n_skipped column, equal to N_SIMS - n_returned - n_bad_se, with a tally of reasons. Document the 50-row and 10-text floors in the header and in supplement S5, and warn when n_skipped > 0.

Status: Resolved 17 September 2026: n_skipped is recorded and the floors are justified in the script.

</details>

<details><summary><b>DA-08</b> (MAJOR, HIGH-RISK): Every solve_curve error is recorded as 'not reached within X to Y', whatever its cause</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:191`. Verifier's verdict: confirmed.

Impact: A future solve that fails for a numerical reason would be reported as a substantive finding that the target was not reached.

Proposed fix: Capture the condition with `error = function(e) e`. Write 'not reached within X to Y' only when max(d$p_meaningful) < target, and otherwise write conditionMessage(e). The current notes stay byte-identical.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>DA-09</b> (MAJOR, HIGH-RISK): run_ordinal_analysis.R and summarise_ordinal.R write the same two files in different schemas, and the run order is nowhere stated</summary>

Location: `preregistration/design_analysis/run_ordinal_analysis.R:190`. Verifier's verdict: confirmed.

Impact: Running the scripts in the listed order silently deletes the projection columns the protocol quotes, and the number check then fails.

Proposed fix: Stating the order (run_design_analysis.R, solve_at_095.R, run_ordinal_analysis.R, summarise_ordinal.R) in both ordinal headers and in the README is documentation-only and safe. Removing the solve-and-write block from run_ordinal_analysis.R, or sourcing summarise_ordinal.R at its end, is a code change for the maintainer to approve.

Status: Partly resolved: the run order is documented in both scripts and the README. Deferred: giving the two scripts distinct outputs changes files the protocol quotes and awaits sign-off.

</details>

<details><summary><b>DA-10</b> (MAJOR): session_info.txt is rewritten on cached runs with the wrong replicate count, and no session is recorded for the ordinal, summary or 0.95 scripts</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:226`. Verifier's verdict: confirmed.

Impact: The environment record can silently come to describe a session that fitted nothing, and it never covers the ordinal results the protocol quotes.

Proposed fix: Write session information only when at least one sweep was computed, preferably one file per cache entry, and do the same in run_ordinal_analysis.R. Record packageDescription('pilotr')[c('Packaged','Built')] and the versions of ordinal and lme4.

Status: Deferred: it changes what run_design_analysis.R writes and belongs with the cache-key change in DA-03.

</details>

<details><summary><b>DA-11</b> (MAJOR, HIGH-RISK): Secondary sweeps hard-code 120 replicates and ignore INTRACT_N_SIMS</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:142`. Verifier's verdict: confirmed.

Impact: Setting INTRACT_N_SIMS for a quick or more precise run changes two of the five sweeps without warning, and any edit to the 120 would be misreported in the session record.

Proposed fix: Introduce N_SIMS_2 <- as.integer(Sys.getenv('INTRACT_N_SIMS_SECONDARY', '120')). Use it in the three calls and in the session string, and document it in the README. The default reproduces the current numbers.

Status: Partly resolved: the fixed 120 replicates are documented in the script and the README. Deferred: reading them from a variable changes code behind reported numbers and awaits sign-off.

</details>

<details><summary><b>DA-12</b> (MAJOR): Environment variables are parsed without validation, and a zero replicate count yields cached NA rows reported as 'not reached'</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:31`. Verifier's verdict: confirmed.

Impact: Mistyped settings produce either cryptic errors or cached NA sweeps that surface as plausible 'not reached' verdicts.

Proposed fix: Validate the raw strings before conversion, for example stopifnot(grepl('^[0-9]+$', Sys.getenv('INTRACT_N_SIMS', '200'))), and then check stopifnot(N_SIMS >= 1, WORKERS >= 1). Use >= 1, not >= 2, so quick cached checks with 1 replicate still run. In run_ordinal_analysis.R also check stopifnot(!is.na(RATED), RATED > 0, RATED <= 1, all(!is.na(TEXTS)), all(TEXTS > 0), all(TEXTS == round(TEXTS))).

Status: Deferred: validating the environment variables is a code edit in a script behind reported numbers, held back so this pass changed only comments there, and belongs with the sign-off on DA-03.

</details>

<details><summary><b>DA-13</b> (MAJOR): safe_workers comment misdescribes the fallback, has an unused argument, and the resume claim holds per sweep only</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:66`. Verifier's verdict: confirmed.

Impact: A reader or maintainer is misled about failure behaviour, and a long run can lose more work than the header promises.

Proposed fix: Rewrite the comment at lines 66-68 to describe the probe cluster, and note that precision_design starts a fresh cluster at each grid point with no fallback. Remove the unused `spec` argument and change the call at line 96 to safe_workers(). Caching per grid point is a separate decision.

Status: Partly resolved: the cluster comment now describes the probe. Deferred: removing the unused argument is a code edit, held back so this pass changed comments only in scripts behind reported numbers.

</details>

<details><summary><b>DA-15</b> (MAJOR, HIGH-RISK): Focal vectors restate effect sizes and signs that should be derived from the spec</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:130`. Verifier's verdict: confirmed.

Impact: If a sign changes in a JSON spec, the simulation follows the spec while the `true` column in the sweeps, precision_sweep.csv and the figure inputs silently keeps the old sign.

Proposed fix: Define ALT <- 2 * ROPE, and derive each focal vector from the modified spec, mapping ':' to '_' in names. Derive the truth labels from ALT. Assert that the result matches the current literals, so the numbers stay unchanged.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>DA-16</b> (MAJOR, HIGH-RISK): summarise_ordinal.R re-declares ROPE, TRUE_B and the 0.90 target instead of reading them from the sweep</summary>

Location: `preregistration/design_analysis/summarise_ordinal.R:19`. Verifier's verdict: confirmed.

Impact: If TRUE_B or ROPE changes in the sweep script, as the protocol's sixth adjustment anticipates, the projection is silently computed against the old values.

Proposed fix: Read TRUE_B as unique(abs(res$true)) with a length-one assertion. Write rope into each cached point and read it back, and define TARGET once. If DA-04 is adopted, project from the recorded mean estimate.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>DA-17</b> (MAJOR): Protocol and supplement say the simulated models were fitted by maximum likelihood; pilotr fits REML with derivative checks switched off</summary>

Location: `preregistration/supplementary.qmd:137`. Verifier's verdict: confirmed.

Impact: The stated estimator is wrong, and the convergence counts are weaker than the wording implies. For fixed-effect Wald intervals at these sample sizes the numerical difference is expected to be small, but that has not been verified.

Proposed fix: Propose "fitted by restricted maximum likelihood with lme4, with derivative-based convergence checks disabled" for qmd:298 and supp:137. Passing REML = FALSE instead is a high-risk change that needs a re-run.

Status: Resolved 17 September 2026: the protocol and S5 say restricted maximum likelihood.

</details>

<details><summary><b>DA-19</b> (MAJOR): How the crossing and its 95 per cent interval are computed is not described anywhere in the protocol or supplement</summary>

Location: `preregistration/supplementary.qmd:141`. Verifier's verdict: confirmed.

Impact: A reader cannot tell that the interval comes from a fitted curve with an assumed probit-in-square-root shape, and cannot reproduce it without the package source.

Proposed fix: A comment at run_design_analysis.R:185 naming the solve_curve defaults relied on is safe on its own. Propose one sentence for supplement S5 describing the probit-on-square-root curve, the n_returned weights, the dispersion floor and the delta-method interval. That sentence touches an end product.

Status: Resolved 17 September 2026: S5 describes the probit-on-square-root solve, the weights, the heterogeneity factor and the refusal to extrapolate.

</details>

<details><summary><b>DA-22</b> (MAJOR): The theory object's formal_model points to a design_analysis file that does not exist</summary>

Location: `preregistration/theory/intract.theory.yaml:496`. Verifier's verdict: confirmed.

Impact: A dangling reference. If theoryforge credits the presence of a formal model when scoring, the quoted rigour score may credit an absent artefact; I have not verified whether it does.

Proposed fix: Maintainer decision. Point spec_ref at an existing specification, for example design_analysis/tier1_developmental.json, which leaves the score unchanged because only the type is scored. Reconsider type 'sem'. Then re-run theory/build_theory.R and theory/check_manuscript_claims.R on a copy to confirm the score is still 90.7.

Status: Deferred: the theory object's formal_model entry feeds the rigour score the manuscript quotes, so correcting it can move that score.

</details>

<details><summary><b>TH-08</b> (MAJOR, HIGH-RISK): build_theory.R sinks output and messages with no on.exit or finally, so an error is hidden in a truncated tf_check.txt</summary>

Location: `preregistration/theory/build_theory.R:12`. Verifier's verdict: confirmed.

Impact: Whoever runs the documented command sees no error message. The deposited outputs are left inconsistent: a truncated check file sits beside stale CSVs and SVG. Run interactively, the open sinks also swallow all later console output.

Proposed fix: Write to a temporary file and move it only on success: tmp <- tempfile(fileext = '.txt'); out <- file(tmp, open = 'wt', encoding = 'UTF-8'); sink(out); tryCatch({ ...body... }, finally = { sink(); close(out) }); file.copy(tmp, 'theory/tf_check.txt', overwrite = TRUE). Do not sink messages, so errors reach stderr. This was verified to leave tf_check.txt byte-identical on success. Write the CSVs and the SVG only after the body completes.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>TH-09</b> (MAJOR, HIGH-RISK): build_theory.R fails open: a cyclic graph, a failed diagram or a non-data-frame result still exits 0</summary>

Location: `preregistration/theory/build_theory.R:32`. Verifier's verdict: confirmed.

Impact: The documented reproduction step reports success on an object that no longer supports the supplement's acyclicity and 'thirty' implications claims. The failure is visible only to someone who reads tf_check.txt line by line.

Proposed fix: After line 21 capture chk <- tf_check(theory), and stop if !identical(chk$gate, 'pass') || chk$n_blockers_failed > 0. Replace the tryCatch at line 32 with imp <- tf_implications(theory); stopifnot(isTRUE(imp$acyclic)); print(imp), which leaves the output unchanged for an acyclic object. Replace the is.data.frame guards with stopifnot(is.data.frame(sev), is.data.frame(red)). Let tf_render_diagram errors propagate instead of silently keeping a stale SVG.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>TH-11</b> (MAJOR): diagram_theory.R is an unreferenced one-off probe with no header</summary>

Location: `preregistration/theory/diagram_theory.R:1`. Verifier's verdict: confirmed.

Impact: A dead script in the deposited theory folder suggests an unexplained step in the pipeline.

Proposed fix: After maintainer confirmation, git rm preregistration/theory/diagram_theory.R. If it is kept, add a header saying it is a diagnostic that prints the structure of tf_diagram()'s return value, is not part of the build and writes nothing.

Status: Deferred: whether diagram_theory.R is dead is uncertain; the README now describes it, and deleting it needs the maintainer.

</details>

<details><summary><b>TH-16</b> (MAJOR): Four auxiliary assumptions name a data-controller question, while the yaml, supplement and protocol say every one or five do</summary>

Location: `preregistration/theory/intract.theory.yaml:11`. Verifier's verdict: confirmed.

Impact: The count of assumptions tied to open questions, which the protocol uses to frame its decision rules, disagrees with the object it cites.

Proposed fix: The maintainer confirms the mapping. If it is four, edit yaml :11-12 to 'Four of the auxiliary assumptions below correspond to questions put to the data controller' and yaml :516 to 'four of which', and, with sign-off, change 'Five' to 'Four' at preregistration.qmd:382 and supplementary.qmd:35. If a fifth mapping is intended (for example the age-band proxy), add the question letter to that assumption's statement and a 'through the auxiliary assumption' clause to its table row. No re-scoring is needed, since scoring ignores these fields, but re-running build_theory.R to confirm tf_check.txt is unchanged is cheap.

Status: Resolved 17 September 2026: the within-window assumption now names question (l), so five is correct in the yaml, the protocol and S1.

</details>

<details><summary><b>TH-17</b> (MAJOR, HIGH-RISK): make_figure1.R hard-codes 12 nodes and 18 edges instead of deriving them from the theory object</summary>

Location: `preregistration/theory/make_figure1.R:33`. Verifier's verdict: confirmed.

Impact: Any legitimate change to the theory object breaks figure generation until someone edits the magic numbers. Replacing them with counts of the parsed DOT would make the guard tautological.

Proposed fix: stopifnot(nrow(nodes) == length(th$constructs), nrow(edges) == length(th$propositions)), and writeLines(sprintf('content assertion passed: %d nodes, %d edges, wording unchanged', nrow(nodes), nrow(edges))). Derive the counts from the parsed yaml, not from the DOT parse, so the guard against a missed regex match stays meaningful.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>TH-21</b> (MAJOR): The supplement credits build_theory.R with outputs it does not produce</summary>

Location: `preregistration/supplementary.qmd:33`. Verifier's verdict: confirmed.

Impact: A reviewer following the supplement's reproduction instruction does not regenerate the figure or the diagnostic count.

Proposed fix: With sign-off, at supplementary.qmd:33: 'Running theory/build_theory.R reproduces the checklist scores, the redundancy screen and the implications in this section, theory/check_manuscript_claims.R prints the counts, and theory/make_figure1.R draws Figure 2.' Replace 'so the diagram cannot disagree with the hypotheses' with 'and checked against it' only after TH-06 is fixed.

Status: Resolved 17 September 2026: S1 credits build_theory.R, check_manuscript_claims.R and make_figure1.R for their own outputs.

</details>

<details><summary><b>FL-03</b> (MAJOR, HIGH-RISK): Figure 1 legend shows the internal column name 'grp' because strip_chrome replaces the package's labelled colour scale</summary>

Location: `preregistration/literature/replot_scopus_figures.R:39`. Verifier's verdict: confirmed.

Impact: The protocol's first figure prints an internal variable name and lowercase codes in its legend.

Proposed fix: In strip_chrome, or only for the intersections plot, replace the bare colour scale with scale_colour_manual(values = c(concept = PAIR[1], intersection = PAIR[2], highlight = PAIR[4]), breaks = c('concept', 'intersection'), labels = c('Concept', 'Intersection'), name = NULL, drop = TRUE). Keep suppressMessages off that call so any future replacement is visible. Regenerate the PNG and PDF only with maintainer sign-off.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-04</b> (MAJOR, HIGH-RISK): scopus_gap_analysis.R writes default-styled PNGs and no PDFs, leaving a mixed state unless replot is run afterwards</summary>

Location: `preregistration/literature/scopus_gap_analysis.R:65`. Verifier's verdict: confirmed.

Impact: Following the README rerun instructions leaves PNGs with titles, captions and a failing palette that no longer match the manuscript PDFs, while the PDFs stay from the previous run. No error is raised.

Proposed fix: Remove the two ggsave calls from scopus_gap_analysis.R (lines 65-67 and 87-89), leaving that script to archive counts only. State in both headers and in the README literature section that literature/replot_scopus_figures.R must be run after it. Optionally end the analysis script with a message saying so, or with source('literature/replot_scopus_figures.R').

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-05</b> (MAJOR, HIGH-RISK): The search record omits the trend queries, and its 'Children's reading' column is a different, narrower query than the concept set</summary>

Location: `preregistration/literature/scopus_gap_analysis.R:117`. Verifier's verdict: confirmed.

Impact: A reader cannot rerun the trend figure from the supplementary record, and could take the trend reference column for the 3,701-record concept set. README.md:91 and the script comment overstate what the record holds.

Proposed fix: In scopus_gap_analysis.R, after the trend table, write each unique(cmp$query) verbatim with its role (reference, narration, apps, machine-generated), and note that each count was a per-year request with date=YYYY. Rename the column to something like 'Reference set (trend query)'. The archived record can be updated from the query column of scopus_topic_trends.csv, which needs no API call, but the record is an end product, so only with sign-off. Reword README.md:91 and the comment at :91-93 to match.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-06</b> (MAJOR): Year window includes 2026, which was incomplete at the search date, and nothing says so</summary>

Location: `preregistration/literature/scopus_gap_analysis.R:22`. Verifier's verdict: confirmed.

Impact: The 2026 point covers under eight months of publication plus indexing lag, yet it is plotted and quoted beside full years. Its dip can be read as a real decline.

Proposed fix: With maintainer sign-off, state in the record, the supplementary caption and preregistration.qmd:75 that 2026 covered publications indexed up to 26 August 2026. The maintainer should record why the window starts in 2018. For a future rerun, consider ending the plotted window at the last complete year and reporting the current year separately.

Status: Resolved 17 September 2026: the protocol, Figure 1 caption and the S4 caption mark 2026 as counted to 26 August.

</details>

<details><summary><b>FL-07</b> (MAJOR): Run stamp and figure scripts record almost no environment, contrary to the protocol's claim</summary>

Location: `preregistration/literature/scopus_gap_analysis.R:135`. Verifier's verdict: confirmed.

Impact: The literature counts and all four figures cannot be tied to an exact software environment, and the protocol's sentence is untrue for these outputs.

Proposed fix: Append the R version, the view ('STANDARD', the scopus_compare_topics default) and utils::capture.output(utils::sessionInfo()) to the stamp at :135-139. Have make_precision_figure.R and replot_scopus_figures.R each write a session file beside their outputs, which touches no end product. Separately, and with sign-off, either note in the record that the 26 August 2026 environment beyond scopusflow was not captured, or reword preregistration.qmd:439.

Status: Deferred: recording the environment changes what the Scopus script writes, and is best done with its next run.

</details>

<details><summary><b>FL-08</b> (MAJOR, HIGH-RISK): No missing-value or coherence assertions before the Scopus counts are archived</summary>

Location: `preregistration/literature/scopus_gap_analysis.R:63`. Verifier's verdict: confirmed.

Impact: A partly failed run would archive a plausible CSV and record, and the protocol's headline empty intersection is never cross-checked against the pairwise counts.

Proposed fix: After line 60: stopifnot(!anyNA(ints$n)); then for each intersection row, stopifnot(ints$n[i] <= min(ints$n[match(strsplit(ints$members[i], '; ')[[1]], ints$label)])). After line 82: cmpc <- cmp[cmp$query_type == 'comparison', ]; stopifnot(!anyNA(cmp$n), !anyNA(cmp$reference_n), all(cmpc$n <= cmpc$reference_n)). Place the checks before any write.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-09</b> (MAJOR, HIGH-RISK): replot_scopus_figures.R retypes the comparison queries by hand as lookup keys and never checks that they matched</summary>

Location: `preregistration/literature/replot_scopus_figures.R:23`. Verifier's verdict: confirmed.

Impact: Any edit to a query in the analysis script would silently leave the full query expression as that series' label in the supplementary figure.

Proposed fix: After line 73: stopifnot(all(cmp$abridged_query[cmp$query_type == 'comparison'] %in% names(short_names))). Better, define the term-to-label map once in a sourced file used by both scopus_gap_analysis.R and replot_scopus_figures.R.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-10</b> (MAJOR, HIGH-RISK): The record's trend table picks columns by substring matching and silently loses any unmatched term</summary>

Location: `preregistration/literature/scopus_gap_analysis.R:123`. Verifier's verdict: confirmed.

Impact: The supplementary record's trend table can lose a series without any error.

Proposed fix: Label rows from cmp$query_type plus the shared term map (FL-09), with no substring fall-through. Before writing, assert stopifnot(!anyDuplicated(data.frame(cmp$year, lab)), all(c('ref', 'narr', 'apps', 'ai') %in% names(tw)), nrow(tw) == length(YEARS)). Build the header row from the same map.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-11</b> (MAJOR, HIGH-RISK): Year breaks and label expansion in the trend figure are hard-coded</summary>

Location: `preregistration/literature/replot_scopus_figures.R:81`. Verifier's verdict: confirmed.

Impact: Rerunning with a different window would produce wrong or missing year breaks with no error, and the label margin would not adapt to new labels.

Proposed fix: yrs <- range(cmp$year); use breaks = seq(yrs[1], yrs[2], by = 2). Either derive the right-hand room from max(nchar(labels)), as the package does, or have the maintainer record in a comment how 0.46 was chosen. Do not invent a rationale.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-13</b> (MAJOR, HIGH-RISK): Design constants in the precision figure are typed into subtitles and code instead of read from the CSVs and specs</summary>

Location: `preregistration/figures/make_precision_figure.R:101`. Verifier's verdict: confirmed.

Impact: If the design analysis is rerun with different grid constants (the protocol commits to re-running it at observed values), the figure would still print the old subtitles and target line, with no error.

Proposed fix: Keep the subtitle wording unchanged and add assertions tying it to the sources: stopifnot(unique(res$per_text[res$model == 'developmental' & res$sweep == 'texts']) == 12, unique(res$texts[res$sweep == 'readings']) == 250, unique(utils::read.csv('design_analysis/minimum_texts.csv')$target) == 0.90). Take the tier-2 readings per child from the spec JSON, not from the CSV per_text column. Change the subtitle text only with sign-off.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-14</b> (MAJOR, HIGH-RISK): Figure-check widths are hard-coded, not derived from the save width, and not the width the manuscript prints at</summary>

Location: `preregistration/figures/make_precision_figure.R:118`. Verifier's verdict: confirmed.

Impact: The check passes today at either scale, but it measures a print scale the manuscript does not use. If the save width at :133 or the embed width in the qmd changes, the check keeps using the old numbers and could pass while text prints below the 6 pt floor.

Proposed fix: FIG_W_IN <- 11; use it in all four save_plot calls, and pass render_width_cm = FIG_W_IN * 2.54 / 2 to check_figure. Keep width_cm = 8.9 as the journal print width unless the maintainer decides otherwise, and have the maintainer record its source in a comment. Do not switch the target to the manuscript's 16.51/2 cm without sign-off.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-15</b> (MAJOR, HIGH-RISK): Panel subsets and series lookups rely on unchecked assumptions about precision_sweep.csv</summary>

Location: `preregistration/figures/make_precision_figure.R:98`. Verifier's verdict: confirmed.

Impact: Adding a null or second-effect sweep for readings, narration or tier 2 (the run script already has one for texts) would put two curves into one series, drawn as a zig-zag, with no error. A new focal parameter would appear as an unlabelled NA series.

Proposed fix: Add 'res$truth == ALT' and the sweep condition to the readings, narration ('texts') and within_child ('children') subsets. In prep() add stopifnot(!anyDuplicated(d[c('param', xcol)]), all(d$param %in% names(construct_of))). Replace line 93 with res$truth <- as.numeric(res$truth); stopifnot(!anyNA(res$truth)).

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-16</b> (MAJOR): Supplementary trend caption does not explain the shaded bands, and the replot comment overstates what the captions carry</summary>

Location: `preregistration/supplementary.qmd:133`. Verifier's verdict: confirmed.

Impact: Readers see uncertainty bands with no statement of what they are, and the script comment describes documentation that does not exist.

Proposed fix: Maintainer wording for supplementary.qmd:133, keeping the package's own framing, for example: 'Shaded bands are Wilson score ranges (z = 1.96) on each yearly share, shown as an indication of stability, not as confidence intervals; they widen where the reference count is small. Records were counted on 26 August 2026; queries are in literature/scopus_search_record.md.' Reword replot:9-12 so it matches what each caption carries.

Status: Resolved 17 September 2026: the S4 caption explains the Wilson bands.

</details>

<details><summary><b>FL-27</b> (MAJOR, HIGH-RISK): Scopus figure dimensions and check widths are duplicated and hand-computed</summary>

Location: `preregistration/literature/replot_scopus_figures.R:50`. Verifier's verdict: confirmed.

Impact: Changing the size in one of the four places would not update the check or the other script.

Proposed fix: Define FIG_W_IN <- 7.5 and FIG_H_IN <- 4.6 once, pass render_width_cm = FIG_W_IN * 2.54, and keep width_cm = 14 unless the maintainer changes the target. Remove the duplicate sizes from scopus_gap_analysis.R by dropping its plotting (FL-04). Have the maintainer record where the height and the margin values come from.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>CS-05</b> (MAJOR, HIGH-RISK): An equal-field-count shift puts reading-time values into read_language labels crossed with age band, and the shape anchors cannot catch it in the export's real column order</summary>

Location: `preregistration/count_script/lets_story_summary.py:1243`. Verifier's verdict: confirmed.

Impact: This needs two faults in one row (an extra field and a missing one), so it is unlikely. When it happens, exact reading times are printed as language labels and broken down by age band in both parts, which is what the protocol says cannot happen.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION. After the field-count check, discard and count (as unshaped) any row where read_language, user_country or user_age_group parses with float(). Never print the offending value.

Status: Resolved 17 September 2026 in version 2026-09-17: the shape test uses four anchors (date, speech flag, both page counts, language) and needs two failures.

</details>

<details><summary><b>CS-07</b> (MAJOR, HIGH-RISK): Folder input reads every .txt and .tsv file too, so a README in the export folder is counted as sessions; the docs say 'every CSV inside'</summary>

Location: `preregistration/count_script/lets_story_summary.py:955`. Verifier's verdict: confirmed.

Impact: Any notes or log file with a .txt extension in the export folder adds phantom sessions, inflating session counts and the unattributable-row count.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION. The CS-02 guard (stop, or skip with a recorded file-record row, when a source's header matches no KEEP name) also fixes this without dropping .txt exports Gameloft might legitimately send. Align docstring 67 and 73 and HOW_TO_RUN.md:12 with the extensions and delimiters actually accepted.

Status: Resolved 17 September 2026 in version 2026-09-17: folder input reads .csv, .tsv, .csv.gz, .tsv.gz and .zip only.

</details>

<details><summary><b>CS-08</b> (MAJOR, HIGH-RISK): Twin-file detection covers only .gz beside a plain file in folder mode; .zip twins and pattern inputs are counted twice, and duplicates stay in every count</summary>

Location: `preregistration/count_script/lets_story_summary.py:961`. Verifier's verdict: confirmed.

Impact: A compressed copy supplied alongside the original doubles every session count. Only the duplicate-row count in the file record and a stdout warning show it.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION. Run twin detection on the resolved path list for every input form. Treat a .gz whose stem matches a plain file, or a .zip member whose name and ZipInfo.file_size match a sibling plain file, as a twin, and record each skip as a file-record row.

Status: Resolved 17 September 2026 in version 2026-09-17: a repeat is detected by checksum whatever its name or input mode, and the script skips its own two outputs.

</details>

<details><summary><b>CS-09</b> (MAJOR, HIGH-RISK): One non-UTF-8 byte in the first 4 MB switches the whole file to latin-1, garbling genuine UTF-8 labels while reporting zero replaced characters</summary>

Location: `preregistration/count_script/lets_story_summary.py:1087`. Verifier's verdict: confirmed.

Impact: A mostly UTF-8 file with one stray byte gets every accented or non-Latin label garbled. Languages, countries and title-fallback texts are then split across parts. The file record shows the encoding but claims no replacements.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION. On a probe failure, count invalid UTF-8 sequences in the probe. Below a maintainer-set threshold (for example 0.01% of probe bytes), keep utf-8-sig and let the oxford_count_replace handler record the replacements. Otherwise fall back to cp1252 rather than latin-1, and record which rule applied.

Status: Resolved 17 September 2026 in version 2026-09-17: the fallback to latin-1 is recorded in the file record with the byte at which UTF-8 decoding failed.

</details>

<details><summary><b>CS-10</b> (MAJOR, HIGH-RISK): Semicolon-separated exports are accepted but decimal commas are not, so every reading time becomes 'not a number' and page counts become violations</summary>

Location: `preregistration/count_script/lets_story_summary.py:630`. Verifier's verdict: confirmed.

Impact: The failure is loud (verdict "No session carries a usable number") but gives the wrong cause. A usable column would be reported as unusable, and the dictionary-suggested integrity check would fire on every row.

Proposed fix: Proposal only. When the sniffed delimiter is ';' and a value matches `^-?\d+,\d+$`, parse it with the comma as decimal separator in time_class, canon_num and pages_differ. Report how many values were read that way. Reissue under a new SCRIPT_VERSION.

Status: Resolved 17 September 2026 in version 2026-09-17: a semicolon-separated file written with decimal commas is detected and read as numbers, and the decimal mark is recorded.

</details>

<details><summary><b>CS-11</b> (MAJOR, HIGH-RISK): Part 2 (the analysed age bands) matches age labels exactly; any spelling variant silently drops out</summary>

Location: `preregistration/count_script/lets_story_summary.py:1296`. Verifier's verdict: confirmed.

Impact: If the full export or one part spells the bands differently, Part 2 undercounts without warning. Lines 158-162 describe Part 2 as the sample the sampling plan concerns. The variants would show only in Part 1's age-band list.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION. Do not silently normalise, since that changes Part 2 counts. Report "sessions whose age band matches an eligible band only after ignoring case and spaces" as an integrity row, with a stdout warning when non-zero.

Status: Resolved 17 September 2026 in version 2026-09-17: age bands match on a spacing- and case-insensitive key, and the raw labels counted in Part 2 are recorded.

</details>

<details><summary><b>CS-12</b> (MAJOR, HIGH-RISK): No small-cell suppression is applied; most cross-tab cells in the sample output hold a single session or account, yet the protocol says the counts contain no record of any individual</summary>

Location: `preregistration/count_script/lets_story_summary.py:1826`. Verifier's verdict: plausible.

Impact: Not a bug against any stated promise, since none promises suppression. But cells of 1, crossing country, language, age band and narration setting, describe one child's session. Publishing them sits awkwardly with the 'no record of any individual' wording and may matter to Gameloft's or the university's disclosure rules.

Proposed fix: Maintainer and data-protection decision. Either (a) suppress cells below a threshold in the cross-tabulated sections only, in a reissue under a new SCRIPT_VERSION, or (b) keep the counts and reword preregistration.qmd:435 to say the counts are unsuppressed aggregates, deposited under whatever access condition the agreement sets.

Status: Not implemented, by decision (17 September 2026). Suppression was written and tested, then removed: it changes the deliverable, nobody had asked for it, and an option carried for a hypothetical is a liability in a script that runs once on someone else's machine. The counts go out as they are. If a disclosure rule later requires suppression, the decision is the data controller's and the university's, and preregistration.qmd:435 would need the wording in option (b) above.

</details>

<details><summary><b>CS-13</b> (MAJOR): Dead code: main() computes a reading-time verdict that is never used and duplicates build_manifest's; Summary.rows is never read</summary>

Location: `preregistration/count_script/lets_story_summary.py:1678`. Verifier's verdict: confirmed.

Impact: Two copies of the verdict logic can drift, and the comment at 1674 misleads anyone who edits the verdict in main expecting the manifest to change.

Proposed fix: For a reissue only, so the deposited copy still matches what Gameloft ran: delete lines 1678-1679 and 1680-1688, keep time_absent and time_usable, reword 1674 to "The reading-time figures written to the summary; the manifest derives its verdict from those rows", and delete `self.rows = rows` at 900. Check the output is unchanged on the sample apart from the date row.

Status: Resolved 17 September 2026 in version 2026-09-17: main() no longer computes the unused verdict; build_manifest states it once, from the summary rows.

</details>

<details><summary><b>CS-14</b> (MAJOR): process_source docstring claims memory does not grow with export size, but a digest is stored for every distinct row</summary>

Location: `preregistration/count_script/lets_story_summary.py:1116`. Verifier's verdict: confirmed.

Impact: The docstring overstates the design. Someone sizing a machine from it would underestimate memory, and it contradicts HOW_TO_RUN.

Proposed fix: Docstring wording for a reissue: "The file is streamed a row at a time rather than loaded whole. Memory still grows with the export: one 8-byte digest is kept for every distinct row for the duplicate check, and the per-account and per-text tallies grow with the number of accounts and texts."

Status: Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only.

</details>

<details><summary><b>CS-25</b> (MAJOR): A 1,969-line single file with a 330-line main() and some functions and methods lacking docstrings</summary>

Location: `preregistration/count_script/lets_story_summary.py:1636`. Verifier's verdict: confirmed.

Impact: Harder to review. The missing docstrings are on small helpers.

Proposed fix: For a reissue: add one-line docstrings to Summary.has_row, Summary.text and Summary.num, and optionally to _txt, _fmt, _count_replace, add and fmt_date. Do not restructure main().

Status: Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only.

</details>

<details><summary><b>CS-27</b> (MAJOR, HIGH-RISK): Folder globbing is case-sensitive on POSIX, so files with upper-case extensions are silently skipped on macOS and Linux</summary>

Location: `preregistration/count_script/lets_story_summary.py:956`. Verifier's verdict: plausible.

Impact: On a Mac, a folder holding PART1.CSV and part2.csv would read only part2.csv with no note.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION: list the folder with sorted(os.listdir(a)) and keep names where name.lower().endswith(ext) for the accepted extensions.

Status: Resolved 17 September 2026 in version 2026-09-17: folder listing is case-insensitive, so an upper-case extension is not skipped.

</details>

<details><summary><b>RS-03</b> (MAJOR): Literature-review gitlink has no .gitmodules and points at a private repository</summary>

Location: `private_InTRACt_literature_review:1`. Verifier's verdict: confirmed.

Impact: A clone of the public repository gets an empty directory with no URL, submodule commands fail, and the README directs readers to a file they cannot obtain. Locally there are two divergent copies of the review: the workspace edits the sibling while the gitlink pins the nested one, so the recorded commit silently drifts from the review being worked on.

Proposed fix: Maintainer decision. (a) `git rm --cached private_InTRACt_literature_review`, ignore the path, keep a single clone (the sibling the workspace already uses) and rewrite README.md:57-63 to describe the review as a separate private repository with an access route; or (b) add a .gitmodules entry with the private URL and state that it is not publicly accessible. Option (a) matches the workspace file.

Status: Deferred: add a .gitmodules entry or remove the gitlink; either changes what a public clone contains.

</details>

<details><summary><b>RS-04</b> (MAJOR): mindmap/source files/node_modules is tracked: 4,375 files, 41 MiB, 63 per cent of tracked bytes</summary>

Location: `mindmap/source files/node_modules:1`. Verifier's verdict: confirmed.

Impact: Every clone and OneDrive sync carries 41 MiB and 4,375 files for a one-off screenshot tool, yet offline regeneration is still impossible because Chrome is fetched at install time. Vendored dependency code escapes review and makes lockfile updates unreadable in diffs.

Proposed fix: Correct the title to about 60 per cent of tracked bytes. Fix as proposed: git rm -r --cached "mindmap/source files/node_modules", ignore node_modules/, keep package-lock.json and document npm ci. A history purge is a separate decision.

Status: Deferred: untracking node_modules (git rm -r --cached) changes what later clones receive.

</details>

<details><summary><b>RS-06</b> (MAJOR): Dated protocol drafts accumulate with no retention policy; the public branch's newest draft is a superseded design</summary>

Location: `preregistration/InTRACt preregistration draft - 2026-09-04.pdf:1`. Verifier's verdict: confirmed.

Impact: A visitor to the public repository opens the 2026-06-15 draft as the latest protocol and reads a superseded design. On this branch the newest committed draft lags the source, and the draft that matches it is untracked and can be lost. Git history already versions the source, so the dated copies duplicate it and grow the repository with every render.

Proposed fix: Maintainer decision: keep in the tree only the draft for each tagged milestone (or none), publish renders as GitHub release assets or on OSF, and state the policy in preregistration/README.md. Proposal only for end products: `git rm` superseded drafts once the policy is agreed.

Status: Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only.

</details>

<details><summary><b>RS-07</b> (MAJOR): Dated HTML drafts are not snapshots: they load today's figures and libraries by relative path and link a PDF that no longer exists</summary>

Location: `preregistration/preregistration.qmd:40`. Verifier's verdict: confirmed.

Impact: A dated HTML draft is not a record of the protocol on its date: it silently shows whichever figure files are current (the 08-31 draft now displays the 09-02 precision figure), its PDF link is broken, and a copy sent on its own renders unstyled and without figures. The date in the filename invites readers to treat it as a faithful snapshot.

Proposed fix: Proposal for the end products: set `embed-resources: true` under format: html in preregistration.qmd and supplementary.qmd (as origin/main does), re-render, and treat older HTML drafts as unreliable or remove them under the RS-06 policy. If the PDF alone is the record, stop producing dated HTML, or have _rename-output.R rewrite the alternate-format href to the dated PDF name.

Status: Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only.

</details>

<details><summary><b>RS-10</b> (MAJOR): No CI on this branch; the manuscript-number gates are never run, and the main-branch workflow targets the old layout</summary>

Location: `.github/workflows/render-preregistration.yml:1`. Verifier's verdict: confirmed.

Impact: The two gates exist only as manual steps, so a manuscript number can drift from its artefact unnoticed (the README's 90.9 against the theory object's 90.7, RS-14, is a live example). Merging would restore an auto-committing workflow built for the earlier document layout.

Proposed fix: Maintainer: add a workflow on this branch that, from preregistration/, runs Rscript check_reported_numbers.R and Rscript theory/check_manuscript_claims.R, and renders both documents as a build check without committing. Pin R 4.6.1, drop the mindmap.png trigger and settle draft auto-commits under RS-06. README numbers need their own check or should be removed from the README.

Status: Deferred: adding CI, and wiring the check scripts into it, is a repository decision.

</details>

<details><summary><b>RS-11</b> (MAJOR): No LICENSE for a repository the protocol says will be public</summary>

Location: `LICENSE:1`. Verifier's verdict: confirmed.

Impact: Without a licence the scripts are all rights reserved by default: reviewers may read the design analysis, theory checks and count script but may not legally reuse or adapt them, which undercuts the open-code commitment of the Registered Report.

Proposed fix: Maintainer decision: add a root LICENSE (for example MIT or GPL-3 for code, with CC BY 4.0 for text and figures stated in the README), noting that apa7.csl and nature.csl stay under CC BY-SA 3.0 and that third-party PDFs (RS-12) are excluded.

Status: Deferred: the licence must be chosen by the author.

</details>

<details><summary><b>RS-12</b> (MAJOR): Thirteen publisher PDFs from a Zotero library are tracked and referenced by nothing</summary>

Location: `preregistration/downloaded_papers_zotero_keys/download_report.csv:1`. Verifier's verdict: confirmed.

Impact: Making the repository public, as the Code availability statement promises, would redistribute publisher PDFs of unknown reuse terms, which risks copyright infringement. The folder is also orphaned from every workflow on this branch and adds 17 MiB to each clone.

Proposed fix: Maintainer, before the first push of wip/bib-2026-07-21: remove the folder from the local branch history (for example git filter-repo --path preregistration/downloaded_papers_zotero_keys --invert-paths on a fresh clone, then re-point the working copy). Keep the PDFs in the private review repository or a Zotero group, and add the path to .gitignore. Because no remote ref contains c96726f, this is the cheapest point to rewrite.

Status: Deferred: the publisher PDFs sit in unpushed history and should be removed from it before any push, which rewrites history.

</details>

<details><summary><b>RS-13</b> (MAJOR): Root README describes a superseded study and embeds a superseded framework figure</summary>

Location: `README.md:35`. Verifier's verdict: confirmed.

Impact: The first page a visitor sees gives the wrong number and direction of hypotheses, an outcome the protocol does not register, and a conceptual figure whose constructs the protocol no longer uses. For a Registered Report this reads as a discrepancy between the public description and the registered plan.

Proposed fix: Rewrite README.md to summarise the current protocol (six hypotheses, two of them two-sided; ages 7 and older; ten or more languages; crossed random effects; no quiz outcome), replace the mindmap image with figures/fig1_nomological_net.png or drop it, list the preregistration/ subdirectories and point to preregistration/README.md, describe the review as a separate private repository, and use the absolute URL https://github.com/pablobernabeu/InTRACt_Interplay_of_Text_Reader_And_Context/issues. The author should decide how much of the confirmatory plan to state publicly before in-principle acceptance.

Status: Partly resolved: the root README's text now matches the protocol. Deferred: the framework figure (DC-46) and the funder line (DC-49) need the author.

</details>

<details><summary><b>RS-15</b> (MAJOR): Opaque auto-sync commits bundle 41 unrelated files, including the count script's first appearance</summary>

Location: `preregistration/count_script/lets_story_summary.py:1`. Verifier's verdict: confirmed.

Impact: History cannot show which code change produced which figure or reported number, nor what the count script looked like when it was sent, because its first recorded version is four weeks later and mixed with 40 other files. Bisecting a discrepancy between manuscript and artefact is impractical.

Proposed fix: From now on commit by logical change with descriptive messages, and disable or reconfigure the auto-sync for this repository. Once the supplied bytes are confirmed (RS-16), tag the corresponding commit, for example `git tag count-script-2026-08-05 <commit>`.

Status: Deferred: the auto-sync process that bundles unrelated files into commits lives outside this repository.

</details>

<details><summary><b>RS-16</b> (MAJOR): No recorded hash ties the repository's count script to the copy sent to the data controller</summary>

Location: `preregistration/count_script/lets_story_summary.py:1`. Verifier's verdict: confirmed.

Impact: Nothing in the repository demonstrates that the file presented as the script supplied on 7 August, whose output Supplementary Section S8 tabulates, is byte-identical to what the data controller received and ran.

Proposed fix: Author: compute the SHA-256 of the file as sent (Desktop folder or the 7 August attachment), compare it with `git show HEAD:preregistration/count_script/lets_story_summary.py | sha256sum` (and with CRLF conversion if needed), and record the hash and outcome in the count_script section of preregistration/README.md. The script itself stays untouched; pin its line endings in .gitattributes to the form sent (RS-26).

Status: Deferred: the checksum must be taken from the exact bytes sent (the CRLF copy), which only the author can confirm.

</details>

<details><summary><b>RS-17</b> (MAJOR): mindmap.png regeneration is undocumented and depends on the network</summary>

Location: `mindmap/source files/capture.js:20`. Verifier's verdict: confirmed.

Impact: The PNG cannot be regenerated offline, a regeneration would depend on whichever Inter version Google serves and whichever Chrome puppeteer fetches, so it may not match the committed image, and the command is known only to the author.

Proposed fix: Add mindmap/README.md stating the purpose (root README image only, superseded by Figure 2, see RS-13), the command `cd "mindmap/source files" && npm ci && node capture.js`, and the network requirement. Optionally add '"scripts": {"capture": "node capture.js"}' and remove the placeholder main and test fields, or retire mindmap/ if the README stops using the image.

Status: Partly resolved: capture.js's header records the network dependency. Deferred: vendoring the font is a maintainer decision.

</details>

<details><summary><b>RP-02</b> (MAJOR): The four study packages were installed from local builds with no provenance, and the cited DOIs do not name versions</summary>

Location: `preregistration/README.md:128`. Verifier's verdict: confirmed.

Impact: If the local build of pilotr 0.3.0 differs from the archived 0.3.0 release (for example uncommitted changes made before 21 August), nothing records the difference. Anyone reinstalling from the DOI may get different simulation or solver code under the same version number.

Proposed fix: Do not add version fields to the bib entries, because the protocol deliberately cites concept DOIs and names the releases in prose. Reinstall each study package from its tagged commit or version-specific archive, so that DESCRIPTION records RemoteType and RemoteSha, or record the SHA-256 of the source tarball actually installed. Add a table to README.md giving package, version, git tag or commit and version-specific DOI.

Status: Deferred: the source each study package was built from is known only to the author.

</details>

<details><summary><b>RP-04</b> (MAJOR): Quarto and TinyTeX/LaTeX versions are neither recorded nor pinned, and the committed drafts show Quarto drift</summary>

Location: `preregistration/_quarto.yml:1`. Verifier's verdict: confirmed.

Impact: The rendered protocol and supplement (page layout, citation rendering, crossref labels) depend on unrecorded tool versions. A render after a TinyTeX or Quarto update can change the PDFs with no record of why.

Proposed fix: The README record ('Rendered with Quarto 1.10.18, TinyTeX v2026.06, TeX Live 2026, LuaHBTeX 1.24.0') is documentation only and can go in now. Adding quarto-required: ">=1.10.18" to _quarto.yml, and pdf-engine: lualatex to the qmd headers, needs maintainer sign-off.

Status: Partly resolved: the README records the Quarto and LuaTeX versions of the 2026-09-05 draft. Deferred: pinning them, for example with quarto-required in _quarto.yml, is a maintainer decision.

</details>

<details><summary><b>RP-10</b> (MAJOR): The protocol says a session record sits beside every output, but only the reading-time design analysis writes one</summary>

Location: `preregistration/preregistration.qmd:439`. Verifier's verdict: confirmed.

Impact: The Code availability statement makes a claim the repository does not meet. The ordinal package version behind the Hypothesis 5 projection, and the plotting stack behind Figures 1 to 3, are unrecorded.

Proposed fix: The new session files would exist only after rerunning scripts that regenerate end products: figure PDFs with new CreationDates, and the ordinal outputs. So either add the sessionInfo writes now and let them populate at the next planned rerun, or ask the maintainer to reword qmd:439 to name the records that exist (design_analysis/session_info.txt, theory/tf_check.txt, literature/scopus_run_stamp.txt). The rewording is an end-product edit and needs sign-off.

Status: Resolved 17 September 2026: Code availability names the session records that exist, and the ordinal summary now writes one.

</details>

<details><summary><b>DC-13</b> (MAJOR): The README gives no environment setup: R version, package versions and sources, Quarto, fonts or Python</summary>

Location: `preregistration/README.md:125`. Verifier's verdict: confirmed.

Impact: A reader cannot rebuild the environment the reported numbers came from, and the claim that reproduction is possible now is not supported by any setup instructions.

Proposed fix: Add a 'Requirements' section: R 4.6.1; install commands with exact versions and sources for theoryforge 0.6.0, pilotr 0.3.0, scopusflow 0.4.0 and depictr 0.3.0 (for example remotes::install_github("<owner>/pilotr@v0.3.0") or the Zenodo tarball); lme4 2.0-1, ordinal 2026.7-26, ggplot2 4.0.3, DiagrammeR 1.0.12, DiagrammeRsvg 0.1, rsvg 2.7.0, patchwork 1.3.2; Quarto 1.10.18 with a LaTeX engine and Times New Roman; Python 3.8 or later for count_script. Point to the renv.lock once it exists. The maintainer must confirm the install sources.

Status: Partly resolved: the README has a Requirements section. Deferred: an R lockfile (RP-01) is still missing.

</details>

<details><summary><b>DC-14</b> (MAJOR): No expected runtime or memory footprint documented, although a known out-of-memory failure exists</summary>

Location: `preregistration/README.md:66`. Verifier's verdict: confirmed.

Impact: A user cannot plan a rerun and may hit the documented memory exhaustion by adding 3200 to INTRACT_ORD_TEXTS. The only timing record is not versioned.

Proposed fix: Add to README: 'On the author's workstation (state CPU cores and RAM), run_design_analysis.R took about an hour with six workers (26 August 2026), and the four ordinal grid points about 11 minutes. A 3,200-text ordinal point with six workers exhausted memory.' The maintainer must supply the hardware.

Status: Partly resolved: the README says runtimes are not recorded and names the known out-of-memory point. Deferred: measuring runtimes needs a full run of the simulations.

</details>

<details><summary><b>DC-29</b> (MAJOR, HIGH-RISK): Design-analysis grid constants have no stated source, and the tier-2 labels copy the spec instead of reading it</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:111`. Verifier's verdict: confirmed.

Impact: A change to the tier-2 JSON would leave mislabelled rows in precision_sweep.csv and in the supplementary figure caption. The basis for the grid cannot be defended from the repository.

Proposed fix: Add WHY comments for the grid constants (maintainer to supply). Derive texts = t2$units$item$n. Record the tier-2 value under a correctly named column (readings_per_child) only with sign-off, because that changes precision_sweep.csv. Drop the truth-sign claim.

Status: Partly resolved: a TODO marks the grid constants' unrecorded source. Deferred: deriving the tier-2 labels from the specification is a code change behind reported numbers.

</details>

<details><summary><b>DC-38</b> (MAJOR): The Chromium sandbox is disabled with no justification</summary>

Location: `mindmap/source files/capture.js:10`. Verifier's verdict: confirmed.

Impact: An undocumented workaround that weakens browser isolation. Its necessity cannot be judged.

Proposed fix: Remove both flags if the capture works without them on the author's machine. Otherwise add '// Needed because <reason>' and set headless: true. Test before committing.

Status: Partly resolved: a TODO marks the undocumented sandbox flags. Deferred: the reason for disabling the sandbox is not recorded anywhere.

</details>

<details><summary><b>DC-46</b> (MAJOR): The root README's framework figure (mindmap.png) is superseded by the protocol's nomological net</summary>

Location: `README.md:29`. Verifier's verdict: confirmed.

Impact: Visitors meet a conceptual model with constructs the study does not measure.

Proposed fix: Replace the image with figures/fig1_nomological_net.png and a caption from preregistration.qmd:472, or keep the mind map labelled 'Early conceptual sketch (2026), superseded by the theory object'. Maintainer to decide.

Status: Deferred: which figure the root README shows is the author's choice.

</details>

<details><summary><b>DC-49</b> (MAJOR): Root README names Kinder as a funder, which conflicts with the draft competing-interests option denying Ferrero funding</summary>

Location: `README.md:13`. Verifier's verdict: plausible.

Impact: If the README is right, the first competing-interests option would be an inaccurate declaration to the journal. If the README is wrong, the public page misstates funding.

Proposed fix: The author must confirm the funder and grant. If Kinder or Ferrero funds the work, use the second competing-interests option describing that relationship and name it in the Acknowledgements and cover letter. Otherwise correct README.md:13.

Status: Deferred: the funding arrangement and the competing-interests statement need the author.

</details>

<details><summary><b>DC-55</b> (MAJOR): The cover letter says all analysis code is already public; the protocol says it will be public at submission, and the branch is unpushed</summary>

Location: `preregistration/cover_letter.md:77`. Verifier's verdict: confirmed.

Impact: The two submission documents disagree, and the remote cannot currently hold the code state the manuscript describes.

Proposed fix: Commit and push the branch before submission, then align the wording, for example cover letter: 'All analysis code is version-controlled at <url> and will be public and complete at submission'.

Status: Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only.

</details>

<details><summary><b>ST-06</b> (MAJOR, HIGH-RISK): Ordinal replicate fitter swallows errors without recording their cause, and an all-failed grid point vanishes</summary>

Location: `preregistration/design_analysis/run_ordinal_analysis.R:86`. Verifier's verdict: confirmed.

Impact: If clmm starts failing, through a package update or a renamed simulated column such as story_rating, the failures leave no message and no count of their own: thinning refusals and fit errors look identical. A grid point where every replicate fails disappears from the sweep and the solver runs on fewer points. The only trace is the arithmetic gap n_returned + n_bad_se < n_sims, which nothing checks.

Proposed fix: Have one_rep return a one-row status frame instead of NULL, for example `data.frame(param = NA_character_, status = "thin")` or `status = paste("fit_error:", conditionMessage(e))`, with successful rows carrying status = "ok". In run_point, count n_thin and n_fit_error, write them to the cache, and `stopifnot(n_returned + n_bad_se + n_thin + n_fit_error == N_SIMS)` for each param. After :172 add `missing <- setdiff(TEXTS, res$texts); if (length(missing)) warning("no replicates returned at ", paste(missing, collapse = ", "))`. Any change in cache columns needs a check that summarise_ordinal.R still reproduces the archived numbers.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>ST-09</b> (MAJOR): Three R scripts have no header saying what they do, how to run them, or what they write</summary>

Location: `preregistration/theory/report_theory.R:1`. Verifier's verdict: confirmed.

Impact: A reader cannot tell from the file that _rename-output.R runs automatically after every render and produces the dated drafts, or that report_theory.R and diagram_theory.R must be run from the preregistration directory. The purpose of diagram_theory.R cannot be recovered from the code alone (see ST-10).

Proposed fix: Add headers to _rename-output.R and report_theory.R as proposed, noting in report_theory.R that it also prints blocking failures, edge count and the largest construct similarity. Leave diagram_theory.R to the maintainer's decision under ST-10.

Status: Partly resolved: report_theory.R and _rename-output.R have headers. Deferred: diagram_theory.R waits on the decision in TH-11.

</details>

<details><summary><b>CR-01</b> (MAJOR): Supplementary Table S8 activity-counter rows and the '438 seconds against 222' statement have no generating script, although the text says both tables can be regenerated from the count script</summary>

Location: `preregistration/supplementary.qmd:185`. Verifier's verdict: confirmed.

Impact: A reviewer told that both tables regenerate from the deposited script cannot reproduce three rows or the 438/222 comparison, and nothing records how they were computed. The supplement also discloses a real session's reading time while stating that no reading-time value is reported, which is at odds with the outcome-blindness framing of the sample.

Proposed fix: Maintainer decision, touching an end product. Either deposit a short script that derives rows 208-210 and the 438/222 comparison from the sample, or reword supplementary.qmd:185 to credit only the timing table and the nineteen-column rows to the count script and say the activity-counter rows were tallied separately. Also drop the 438/222 figures (or the 'no value is reported' note at :203), and copy the two timing labels verbatim. The same overstatement is in preregistration/README.md:110-112 ('Supplementary Section S8 tabulates it'), which is editable and can be aligned once the wording is decided.

Status: Resolved 17 September 2026: S8 credits the script only for the rows it generates and no longer quotes a reading time.

</details>

<details><summary><b>CR-08</b> (MAJOR): title.tex calls \setstretch, which works only because preregistration.qmd sets linestretch; this coupling is undocumented</summary>

Location: `preregistration/title.tex:23`. Verifier's verdict: confirmed.

Impact: Removing 'linestretch: 1' as a no-op, or reusing the partial for the supplement (for example, to add its author block), makes the PDF render fail with 'Undefined control sequence \setstretch' inside the title block.

Proposed fix: Needs sign-off, as title.tex is an end product. Make the partial self-sufficient: replace '\setstretch{1.15}' at title.tex:23 with '\linespread{1.15}\selectfont', which needs no package, then compare the rendered title block. A no-op '\providecommand{\setstretch}[1]{}' would hide the error but silently drop the spacing. As an interim documentation-only step (safe on its own), add a README sentence saying title.tex requires linestretch in the PDF YAML.

Status: Partly resolved: the README documents the coupling between title.tex and linestretch. Deferred: title.tex itself is an end product.

</details>

<details><summary><b>DA-23</b> (MINOR, HIGH-RISK): A cached re-run does not byte-reproduce precision_sweep.csv or minimum_texts.csv</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:137`. Verifier's verdict: confirmed.

Impact: A rebuild-and-compare gate that compares bytes fails even though the values agree. No quoted number changes.

Proposed fix: Write truth as numeric on both paths, and make any rebuild-and-compare gate compare numerically with a tolerance rather than byte for byte. Correct the figure comment.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>DA-24</b> (MINOR, HIGH-RISK): The tier-2 sweep labels readings per child as per_text and hard-codes 250 texts</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:167`. Verifier's verdict: confirmed.

Impact: A reader of the CSVs is told there were five readings per text in tier 2, which is false.

Proposed fix: Use texts = t2$units$item$n and a per_child column taken from t2$units$item$per_subject, and add per_child to KEEP. Do this in the same re-run as DA-01.

Status: Resolved 17 September 2026: the tier-2 CSV records texts from the specification and per_child.

</details>

<details><summary><b>DA-25</b> (MINOR): Ordinal script bypasses pilotr's replicate seeds and the JSON seed despite claiming 'the same seed discipline'</summary>

Location: `preregistration/design_analysis/run_ordinal_analysis.R:132`. Verifier's verdict: confirmed.

Impact: The documentation describes a seeding scheme the script does not use, and the JSON seed is dead for this analysis. I found no numerical consequence.

Proposed fix: Reword the header now. Propose for supp:143: "each replicate is seeded deterministically from its grid point and replicate index". Switching to replicate_seeds would change the numbers.

Status: Resolved 17 September 2026: S5 describes the per-replicate seeding.

</details>

<details><summary><b>DA-27</b> (MINOR, HIGH-RISK): p_meaningful counts a determinate verdict in the wrong direction as a success for directional hypotheses</summary>

Location: `preregistration/design_analysis/run_ordinal_analysis.R:150`. Verifier's verdict: confirmed.

Impact: The assurance measure differs from the registered directional rule. The effect on the quoted figures is negligible.

Proposed fix: For H1, H4, H5 and H6, count only a verdict in the direction of sign(true), and keep the two-sided rate for H2 and H3. This changes p_meaningful slightly.

Status: Resolved 17 September 2026 for the ordinal sweep, which now counts only verdicts in the true direction. The lme4 sweeps are unchanged.

</details>

<details><summary><b>DA-28</b> (MINOR): 'Twelve readings of each text' is a mean: each reader draws a text at random, giving 4 to 19 readings per text</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:48`. Verifier's verdict: confirmed.

Impact: The design is described as balanced when readings per text are Poisson-like. The effect on precision is minor.

Proposed fix: Changing the comment at run_design_analysis.R:48-49 to say twelve readings per text on average is safe on its own. Propose 'an average of twelve readings per text' for qmd:125, supp:139, supp:145 and the figure subtitle, which regenerates a figure and so needs sign-off.

Status: Resolved 17 September 2026: the protocol, S5 and the figure subtitle say twelve readings per text on average.

</details>

<details><summary><b>DA-29</b> (MINOR, HIGH-RISK): The simulated outcome is not exactly standardised once fixed-effect variance is included</summary>

Location: `preregistration/design_analysis/tier1_developmental.json:22`. Verifier's verdict: confirmed.

Impact: Relative to the outcome SD, the ROPE and the effect are about 2 per cent smaller than stated. The effect on the quoted figures is negligible.

Proposed fix: Either note the approximation in supplement S5, or set sigma to sqrt(1 - 0.2025 - 0.09 - 0.0375), about 0.819, for the alternative sweeps and re-run.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>DA-30</b> (MINOR): The protocol says the tier-2 model 'added' terms to the tier-1 model, but F_T2 drops the age band and its interactions</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:46`. Verifier's verdict: confirmed.

Impact: The simulated tier-2 model is misdescribed.

Proposed fix: Propose for qmd:298 and supp:137: "The tier-2 model contained the three components, a single accumulated-reading trend, and child and text intercepts, without the age band or its interactions."

Status: Resolved 17 September 2026: the tier-2 model is described as simulated.

</details>

<details><summary><b>DA-33</b> (MINOR, HIGH-RISK): The solver helper is copied into four scripts, and a Wilson interval is re-implemented without clamping</summary>

Location: `preregistration/design_analysis/solve_at_095.R:19`. Verifier's verdict: confirmed.

Impact: Drift risk: one copy has already diverged in its output schema (DA-09).

Proposed fix: Move solve_one, msg and wilson into design_analysis/helpers.R and source it from each script. Verify byte-identical outputs on a copy afterwards.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>DA-34</b> (MINOR): Several helper functions lack a one-line purpose comment</summary>

Location: `preregistration/design_analysis/run_ordinal_analysis.R:122`. Verifier's verdict: confirmed.

Impact: Readers have to infer each helper's contract.

Proposed fix: Add a one-line purpose comment above msg, read_sweep, wilson and run_point, and describe run_sweep's arguments and returned frame. units_by_readings can share the existing comment.

Status: Partly resolved: msg, wilson and run_point have purpose comments. Deferred: read_sweep in solve_at_095.R and run_sweep's argument list remain.

</details>

<details><summary><b>DA-35</b> (MINOR): The ignored run_ordinal.log is stale: it records an unfinished 3,200-text sweep from a superseded default grid</summary>

Location: `preregistration/design_analysis/run_ordinal.log:9`. Verifier's verdict: confirmed.

Impact: A reader of the working tree may think a 3,200-text point was attempted under the current settings.

Proposed fix: Do not delete it without the maintainer. Either leave it, since it is ignored and matches the header comment, or append a line recording that the 3,200-text point was abandoned for lack of memory. Scripts writing their own timestamped logs is a separate improvement.

Status: Deferred: run_ordinal.log is an ignored local file, and deleting it is the maintainer's call.

</details>

<details><summary><b>DA-36</b> (MINOR): at_effect silently leaves a zero coefficient at zero when the sign is kept</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:61`. Verifier's verdict: confirmed.

Impact: A future spec with a placeholder zero would silently simulate no effect while being labelled truth 0.10.

Proposed fix: In at_effect, add `if (keep_sign) stopifnot(all(unlist(spec$fixed$coefficients) != 0))`, which leaves the null sweep with keep_sign = FALSE unaffected. Add the same check before the loop at run_ordinal_analysis.R:60.

Status: Deferred: the zero-coefficient assertion is a code edit in a script behind reported numbers, held back so this pass changed only comments there, and belongs with the sign-off on DA-03.

</details>

<details><summary><b>TH-22</b> (MINOR): The yaml provenance log does not record the twelfth construct or propositions p15 to p18</summary>

Location: `preregistration/theory/intract.theory.yaml:501`. Verifier's verdict: confirmed.

Impact: The object's own history understates how it reached its current form, which weakens the provenance record the Registered Report deposits.

Proposed fix: The maintainer supplies the history. Append steps such as step 7 (tf_add_construct and tf_add_proposition: c_text_provenance and p15-p18, with the reason recorded at supplementary.qmd:39) and step 8 (the prediction that became the seventh diagnostic one, with the date and reason). Do not write a reason the record does not contain.

Status: Deferred: the provenance entries for the twelfth construct and propositions p15 to p18 need the author's dates.

</details>

<details><summary><b>TH-25</b> (MINOR): Hand-written dangling-reference loop duplicates tf_validate(full = TRUE) and covers less</summary>

Location: `preregistration/theory/check_manuscript_claims.R:48`. Verifier's verdict: confirmed.

Impact: Duplicated logic that misses dangling protects and supports references, which the library call would catch.

Proposed fix: Insert validation immediately after line 12, before tf_check: tryCatch(tf_validate(th, full = TRUE), error = function(e) { writeLines(c('== DANGLING OR INVALID REFERENCES ==', paste0('  ', conditionMessage(e)))); quit(status = 1) }). Then delete lines 48-64 and change line 65 to '== theory object validates: no dangling references =='.

Status: Deferred: whether tf_validate() raises or returns on a dangling reference was not confirmed, so the replacement could fail open.

</details>

<details><summary><b>TH-28</b> (MINOR): Styling constants in make_figure1.R carry no reason, and the minus glyph is a raw non-ASCII literal</summary>

Location: `preregistration/theory/make_figure1.R:57`. Verifier's verdict: confirmed.

Impact: A later maintainer cannot tell which choices are deliberate, such as colour-blind safety or rank grouping, and which are incidental. The literal glyph depends on the source being read as UTF-8.

Proposed fix: Replace the literal at line 60 with the escape − (label=\"−\" inside the sprintf string), which is figure code, so regenerate and confirm the SVG is byte-identical before committing. Add rationale comments only for choices the maintainer confirms, for example whether Okabe-Ito was chosen for colour-vision safety.

Status: Deferred: the reasons for the styling constants are not recoverable from the code or its history.

</details>

<details><summary><b>TH-29</b> (MINOR, HIGH-RISK): Figure 2 gets no text-size or colour check, unlike the other manuscript figures</summary>

Location: `preregistration/theory/make_figure1.R:121`. Verifier's verdict: plausible.

Impact: The figure whose text is densest could fall below the journal's minimum type size when printed, and no gate would catch it.

Proposed fix: In make_figure1.R, after export_svg, parse the svg width attribute in pt and assert min_font_pt * (render_width_pt / svg_width_pt) >= 6. Take render_width_pt from the same 17.78 cm the other figures use, and min_font_pt from the smallest fontsize in styled (12). Alternatively record the computed print size in README.md next to the depictr note.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-12</b> (MINOR, HIGH-RISK): The figure check in replot_scopus_figures.R only warns, for every check, so failures never stop it</summary>

Location: `preregistration/literature/replot_scopus_figures.R:55`. Verifier's verdict: confirmed.

Impact: A later presentation change that pushed text below 6 pt or broke contrast would still overwrite both manuscript figures with exit status 0, so a batch rebuild would treat it as success.

Proposed fix: Keep the warning for redundant_encoding only. For any other failed check, stop: hard <- failed[failed$check != 'redundant_encoding', , drop = FALSE]; if (nrow(hard)) stop('figure check failed for ', what, ': ', paste(hard$check, collapse = ', '), call. = FALSE). Say in README.md:93 that redundant_encoding is tolerated and why.

Status: Partly resolved: the README says the Scopus figure checks only warn. Deferred: making them fatal changes figure code and awaits sign-off.

</details>

<details><summary><b>FL-20</b> (MINOR, HIGH-RISK): Dead lookup entries for CohPC_narr</summary>

Location: `preregistration/figures/make_precision_figure.R:28`. Verifier's verdict: confirmed.

Impact: The mapping suggests a series that the figure never draws. Removing it would not change any output.

Proposed fix: Maintainer choice: keep the entries with a comment saying they are unused until CohPC_narr becomes focal in run_design_analysis.R, or delete them.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-21</b> (MINOR): Unused log_x argument with a no-op else branch</summary>

Location: `preregistration/figures/make_precision_figure.R:87`. Verifier's verdict: confirmed.

Impact: Misleading control flow. Output is unaffected.

Proposed fix: Replace line 87 with 'if (log_x) p <- p + scale_x_log10()'. Do not remove the argument in the same change.

Status: Deferred: although the rewrite cannot change the figure, it is a code edit in a figure script, held back so this pass changed only comments there.

</details>

<details><summary><b>FL-23</b> (MINOR, HIGH-RISK): Main figure is saved before the supplement panels are checked</summary>

Location: `preregistration/figures/make_precision_figure.R:133`. Verifier's verdict: confirmed.

Impact: If a supplement panel fails, the run stops after the main figure has been rewritten but before the supplement is, leaving the two figures from different runs.

Proposed fix: Build pa, pb, ps_a and ps_b and call audit_panel on all four before the first save_plot, then save both figures. No output changes when the checks pass.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-24</b> (MINOR, HIGH-RISK): Figure panel tags are uppercase, while both captions refer to lowercase panels</summary>

Location: `preregistration/figures/make_precision_figure.R:109`. Verifier's verdict: confirmed.

Impact: Figure and caption use different panel labels.

Proposed fix: Pass tag_levels = 'a' to both arrange_plots calls and regenerate with sign-off, or change the captions to A and B. A bold tag face is a separate style choice for the maintainer.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>FL-25</b> (MINOR): Magic numbers in the precision figure have no stated rationale</summary>

Location: `preregistration/figures/make_precision_figure.R:53`. Verifier's verdict: confirmed.

Impact: Future edits cannot tell which values are journal requirements and which are taste.

Proposed fix: Gather the values into a named constants block and have the maintainer add the source for the print width and dpi. Do not invent reasons for the others.

Status: Deferred: the rationale for the figure constants is not recorded.

</details>

<details><summary><b>FL-32</b> (MINOR, HIGH-RISK): The three R scripts save, load and log in inconsistent ways</summary>

Location: `preregistration/literature/replot_scopus_figures.R:66`. Verifier's verdict: confirmed.

Impact: Minor friction for maintenance, with no effect on output.

Proposed fix: Unify the loading pattern and move msg() into a shared sourced helper, neither of which touches output. Switch the saving helper only with a before-and-after raster comparison (see FL-29) and maintainer sign-off.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>CS-15</b> (MINOR, HIGH-RISK): Missing-value tokens are inconsistent: blank() treats NA and NULL as empty, time_class() calls them 'not a number', and nan, None and N/A count as values</summary>

Location: `preregistration/count_script/lets_story_summary.py:626`. Verifier's verdict: confirmed.

Impact: The usable total is unchanged, but an export writing NA for missing times is reported as holding text in a numeric column, not as empty. Exports that write nan or None give inflated field-present counts for the four nullable fields.

Proposed fix: Proposal only. Have time_class call blank() first, and widen blank() to include NAN, NONE and N/A. Reissue under a new SCRIPT_VERSION.

Status: Resolved 17 September 2026 in version 2026-09-17: MISSING_TOKENS is used by blank() and by time_class(), so NA, NULL, N/A, NaN, None and a lone dash count as empty everywhere.

</details>

<details><summary><b>CS-16</b> (MINOR, HIGH-RISK): parse_when reads any 10-digit number in the epoch range as Unix seconds, and mixes UTC epochs with as-logged ISO times</summary>

Location: `preregistration/count_script/lets_story_summary.py:687`. Verifier's verdict: confirmed.

Impact: A compact date-hour format would be silently misdated by eight years instead of counted as unreadable. A file mixing epoch and offset timestamps would shift day and hour counts. The sample's format is not affected (S8: dates in UTC).

Proposed fix: Proposal only. Before accepting a 10-digit value as an epoch, reject it if its first eight digits parse as a valid YYYYMMDD date in the export window. Note the as-logged convention in the docstring. Reissue under a new SCRIPT_VERSION.

Status: Partly resolved 17 September 2026: the format each file's dates were read in is recorded per file, so a mix of as-logged timestamps and UTC epochs is visible. Reading a 10-digit number as an epoch is unchanged.

</details>

<details><summary><b>CS-18</b> (MINOR): Supplementary S8 makes the same 'line for line' claim, which fails on the run-date row</summary>

Location: `preregistration/supplementary.qmd:185`. Verifier's verdict: confirmed.

Impact: A small overstatement in an end product that reviewers can check against the deposit.

Proposed fix: For maintainer sign-off: "re-running it on the sample reproduces that summary line for line apart from the date of the run, so both tables can be regenerated from the sample deposit."

Status: Resolved 17 September 2026: S8 says line for line apart from the date of the run.

</details>

<details><summary><b>CS-19</b> (MINOR, HIGH-RISK): The manifest is written in text mode, so its bytes differ between Windows (CRLF) and POSIX (LF) runs; the 'identical page' claim holds only on one platform</summary>

Location: `preregistration/count_script/lets_story_summary.py:1954`. Verifier's verdict: plausible.

Impact: If Gameloft runs on one OS and Oxford rebuilds on another, checksums of the two HTML files differ, although the content matches.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION: open both HTML writes with `newline="\n"`. Note this makes the page's bytes differ from the CRLF 6 August reference.

Status: Resolved 17 September 2026 in version 2026-09-17: the manifest is written with newline="\n" on every platform.

</details>

<details><summary><b>CS-20</b> (MINOR, HIGH-RISK): --manifest-from writes into the working directory and overwrites the manifest it is meant to be compared with; short rows are dropped silently</summary>

Location: `preregistration/count_script/lets_story_summary.py:1630`. Verifier's verdict: confirmed.

Impact: Following the instructions destroys the original page. The rebuilt page cannot then be compared with it, which is what the command is offered to demonstrate.

Proposed fix: Proposal only: write the rebuild to a distinct name (e.g. lets_story_manifest_rebuilt.html) or accept an output path, and report dropped rows. Until then, amend HOW_TO_RUN to say run it from another folder. Reissue under a new SCRIPT_VERSION.

Status: Resolved 17 September 2026 in version 2026-09-17: --manifest-from writes <input>_manifest_rebuilt.html beside its input and counts rows with fewer than five fields.

</details>

<details><summary><b>CS-21</b> (MINOR, HIGH-RISK): Ad hoc argv handling: --help and -h are treated as file names, and a malformed --manifest-from call reports a missing file</summary>

Location: `preregistration/count_script/lets_story_summary.py:1639`. Verifier's verdict: confirmed.

Impact: No documented command is broken, but a data controller who types --help gets a misleading error.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION: use argparse with positional `paths` (nargs='*') and `--manifest-from PATH`, and require at least one of the two, so both documented forms are unchanged and --help prints usage.

Status: Resolved 17 September 2026 in version 2026-09-17: --help, -h and --version work, options are validated, and an unknown option is refused.

</details>

<details><summary><b>CS-22</b> (MINOR): HOW_TO_RUN promises outputs of 'a few tens of kilobytes', but the 35-row manifest is 99 KB and a synthetic 200,000-row summary is 370 KB</summary>

Location: `preregistration/count_script/HOW_TO_RUN.md:51`. Verifier's verdict: confirmed.

Impact: A minor mismatch. A data controller with an attachment size limit could be surprised.

Proposed fix: For a reissued HOW_TO_RUN: "Both are small: the page is about 100 KB, and the data file ranges from about 40 KB to a few hundred kilobytes depending on how many countries, languages and days the export covers."

Status: Not fixed, by decision (17 September 2026): the instruction sheet was not reissued, so that the data controller receives one file and no new instructions. The measured sizes are recorded in preregistration/README.md instead.

</details>

<details><summary><b>CS-23</b> (MINOR): 'Ten times wider than one another' and labels like '1 to 9' describe half-open decade bins loosely</summary>

Location: `preregistration/count_script/lets_story_summary.py:132`. Verifier's verdict: confirmed.

Impact: Wording only, since S8 says reading times are whole seconds. Non-integer values sit under labels whose upper bound they exceed.

Proposed fix: Reuse the protocol's wording, "bands whose boundaries are successive powers of ten", in README.md:107 (editable), and propose the same for the supplementary.qmd:231 caption, HOW_TO_RUN.md:128 and the script comment at 123 in a reissue. Leave the output labels unchanged.

Status: Not fixed, by decision (17 September 2026): as CS-22, the sheet stands as sent. The half-open bands are described in the script's own header.

</details>

<details><summary><b>CS-24</b> (MINOR): Stale or inaccurate comments on the KEEP scope, zip closing, lookup count and identifier caching</summary>

Location: `preregistration/count_script/lets_story_summary.py:1171`. Verifier's verdict: confirmed.

Impact: Misleading rationale for future maintainers. No behavioural effect.

Proposed fix: Comment-only proposals for a reissue: (1) "Identifiers are not cached: a cache would hold every distinct account and text for the whole run." (3) "instead of looking up each KEEP name on every row". (4) Optionally "Apart from the reading-time groups described below, every value that reaches a count ...". Drop item (2).

Status: Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only.

</details>

<details><summary><b>CS-26</b> (MINOR, HIGH-RISK): Redundant logic: band lists written inline in emit alongside a _bands helper, Counters used as sets, and an always-true length check</summary>

Location: `preregistration/count_script/lets_story_summary.py:1838`. Verifier's verdict: confirmed.

Impact: No wrong output. It adds code to read and invites inconsistent edits.

Proposed fix: Proposal for a reissue: route the inline bands through _bands, use sets for lang_u and age_u, and reduce 1225 to `if all_present:`. Check output is byte-identical on the sample before release.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>CS-28</b> (MINOR, HIGH-RISK): Files skipped as twins, zip archives with no CSV, and empty files are reported only on stdout, not in the summary data file</summary>

Location: `preregistration/count_script/lets_story_summary.py:966`. Verifier's verdict: confirmed.

Impact: Oxford receives only the two files, so it cannot see that an input was skipped.

Proposed fix: Proposal for a reissue under a new SCRIPT_VERSION: collect the twin-skip and zip-without-CSV notes and write each as a `file record | skipped file | <name> | <reason>` row. Optionally add a reason row for an empty file, which is already listed with 0 rows.

Status: Resolved 17 September 2026 in version 2026-09-17: every note about a skipped, empty or duplicate file is written into the summary data file as well as printed.

</details>

<details><summary><b>RS-08</b> (MINOR): Supplement outputs are overwritten undated while protocol outputs are dated</summary>

Location: `preregistration/_rename-output.R:5`. Verifier's verdict: plausible.

Impact: The protocol and its supplement follow opposite output policies, so no committed supplement can be paired with a dated protocol draft (the 09-04 protocol PDF has no 09-04 supplement, and the supplement in HEAD matches neither it nor the working tree). A reader cannot tell which supplement accompanied which protocol version.

Proposed fix: Maintainer: choose one output policy for both documents under RS-06. If dated drafts stay, loop over c("preregistration", "supplementary") with matching prefixes and the RS-01 return check. Otherwise stop dating and rely on tags.

Status: Partly resolved: the hook header and README state that the supplement is overwritten. Deferred: whether to date the supplement too is a maintainer decision.

</details>

<details><summary><b>RS-19</b> (MINOR): Quarto HTML libraries are tracked, including superseded CSS hashes that old drafts still load</summary>

Location: `preregistration/preregistration_files/libs/quarto-html/quarto-syntax-highlighting-7f8f88aac4f3542376d5c11b86a4c14d.css:1`. Verifier's verdict: confirmed.

Impact: Generated libraries are versioned beside the sources and gain a copy per Quarto upgrade. Deleting the older hashes as apparent clutter would silently break the styling of the older HTML drafts, which is not obvious from the tree.

Proposed fix: After RS-07 is decided (embed-resources: true), untrack both *_files/ directories and ignore `preregistration/*_files/`. Until then leave them, since each hash is referenced.

Status: Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only.

</details>

<details><summary><b>RS-20</b> (MINOR): capture_output.txt records a save path in a different checkout</summary>

Location: `mindmap/source files/capture_output.txt:2`. Verifier's verdict: confirmed.

Impact: The tracked log implies the PNG was saved from this repository; it was produced in another checkout, so it cannot confirm that the committed mindmap.png came from the committed mindmap.html.

Proposed fix: Untrack and ignore the log, or regenerate it from this checkout if the bounding-box record is wanted, and mention it in mindmap/README.md (RS-17).

Status: Deferred: capture_output.txt is a stale log; removing or regenerating it is the maintainer's call.

</details>

<details><summary><b>RS-23</b> (MINOR): Spaces and mixed naming conventions in paths</summary>

Location: `preregistration/InTRACt references.bib:1`. Verifier's verdict: confirmed.

Impact: Every shell command, workflow glob and link must quote these paths, which has already forced one workaround, and inconsistent names obscure which files belong together.

Proposed fix: Maintainer decision, best combined with another structural change: rename to intract_references.bib, mindmap/src/ and drafts such as intract_preregistration_YYYY-MM-DD.pdf, updating the YAML, _rename-output.R and any workflow in the same commit. Proposal only for the end products (bibliography and drafts).

Status: Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only.

</details>

<details><summary><b>RS-24</b> (MINOR): Checker and render hook sit at the preregistration root, apart from the other scripts</summary>

Location: `preregistration/check_reported_numbers.R:1`. Verifier's verdict: plausible.

Impact: The two manuscript checkers live in different places, and the preregistration root mixes end products, configuration and code, which makes the inventory harder to audit.

Proposed fix: Maintainer decision: move check_reported_numbers.R into a checks/ directory with check_manuscript_claims.R (adjusting relative paths and README commands); leave _rename-output.R at the root or move it to scripts/ and update _quarto.yml.

Status: Deferred: moving the scripts changes every documented command.

</details>

<details><summary><b>RS-25</b> (MINOR): No CITATION.cff</summary>

Location: `CITATION.cff:1`. Verifier's verdict: confirmed.

Impact: Reusers cannot cite the code in a standard form, and GitHub shows no 'Cite this repository' entry.

Proposed fix: Author: add CITATION.cff with title, authors and ORCIDs, the repository URL, the licence chosen under RS-11 and the Zenodo DOI once the submission commit is archived.

Status: Deferred: CITATION.cff needs author metadata (co-authors, ORCIDs).

</details>

<details><summary><b>RS-26</b> (MINOR): No .gitattributes; working-tree line endings are mixed</summary>

Location: `.gitattributes:1`. Verifier's verdict: confirmed.

Impact: Working-tree line endings depend on each machine's Git settings, two files already mix them, and byte-level comparisons or hashes of scripts (RS-16) differ across platforms.

Proposed fix: After RS-16's hash is recorded, add .gitattributes with `* text=auto eol=lf` and explicit `*.pdf binary`, `*.png binary`, `*.woff binary`, then `git add --renormalize .` in a dedicated commit.

Status: Deferred: a .gitattributes line-ending policy renormalises tracked files, end products included.

</details>

<details><summary><b>RS-27</b> (MINOR): A second git worktree lives inside the repository tree, hidden only by a local exclude</summary>

Location: `.claude/worktrees/goofy-chandrasekhar-cae89e:1`. Verifier's verdict: confirmed.

Impact: Recursive tools (grep, IDE search, OneDrive sync) see a second, older copy of the protocol sources, risking edits to or quotations from the wrong file, and any other clone would show .claude/ as untracked.

Proposed fix: Maintainer: git worktree remove or git worktree move it outside the repository and OneDrive. Add .claude/worktrees/ to the root .gitignore (RS-05).

Status: Deferred: the worktree under .claude/worktrees is local state that only its owner should remove.

</details>

<details><summary><b>RP-15</b> (MINOR): No output records the version or checksum of the inputs it came from, and the working-tree theory YAML and bib differ from HEAD with their regenerated outputs uncommitted</summary>

Location: `preregistration/design_analysis/session_info.txt:1`. Verifier's verdict: confirmed.

Impact: Nothing in the artefacts links a quoted number to the exact input bytes. HEAD's tf_check.txt (90.9) and the working tree's (90.7) each describe a different YAML, and only commit state tells them apart.

Proposed fix: Fold the input fingerprint into the RP-06 cache guard, not a separate manifest script. Committing the YAML together with its regenerated tf_* outputs is a maintainer action at the end of the current pass.

Status: Deferred: a checksum manifest of inputs should be taken once the working-tree edits are committed, so it describes a committed state.

</details>

<details><summary><b>RP-17</b> (MINOR): The count script's 'Python 3.8 or later' requirement has been checked statically but never at run time</summary>

Location: `preregistration/count_script/HOW_TO_RUN.md:7`. Verifier's verdict: plausible.

Impact: The script is probably 3.8 compatible, but a standard-library behaviour change between 3.8 and 3.13 (csv, zipfile, hashlib.blake2b) would surface only at the data controller's end.

Proposed fix: Run it once under a Python 3.8 interpreter on the sample (this needs an interpreter that is not installed here, so it is a maintainer task). Record the tested versions in preregistration/README.md, not in HOW_TO_RUN.md, which was supplied to the data controller.

Status: Deferred: no Python 3.8 interpreter is available here to test the stated minimum.

</details>

<details><summary><b>RP-19</b> (MINOR): Timestamps embedded in generated files defeat byte-identical comparison of session records, figures and rendered documents</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:227`. Verifier's verdict: confirmed.

Impact: Regenerated PDFs and session records can never match the committed bytes. A verification gate must either skip these files or strip the timestamps, and nothing documents which.

Proposed fix: The documentation part (README: compare CSV and TXT outputs byte for byte, excluding the session_info 'run:' line and PDF CreationDate) is safe now. SOURCE_DATE_EPOCH is honoured by LuaTeX. Whether R's cairo-based devices and rsvg honour it is unverified here, so test that before relying on it.

Status: Deferred: removing the timestamps changes generated files; the alternative is a documented tolerance for those lines.

</details>

<details><summary><b>DC-19</b> (MINOR): The protocol describes the count script as reading nineteen categorical columns</summary>

Location: `preregistration/preregistration.qmd:226`. Verifier's verdict: confirmed.

Impact: A slightly inaccurate description of the supplied script in the end product.

Proposed fix: Maintainer to consider: 'which reads nineteen columns other than the outcome, among them identifiers, the session timestamp and page counts, and the reading-time column'.

Status: Resolved 17 September 2026: the protocol says nineteen columns besides the outcome.

</details>

<details><summary><b>ST-14</b> (MINOR): No committed linter or formatter configuration for R, Python, Node or editors</summary>

Location: `.lintr:0`. Verifier's verdict: confirmed.

Impact: Contributors cannot tell which style is intended. Lint output is dominated by convention mismatches, which hides the few lints that matter, and each tool applies its own defaults (lintr 80 columns, ruff 88).

Proposed fix: Add preregistration/.lintr: `linters: linters_with_defaults(line_length_linter(100), object_name_linter(styles = c("snake_case", "SNAKE_CASE", "symbols")), object_usage_linter = NULL)`, with `encoding: "UTF-8"`. Add a root .editorconfig (`[*] end_of_line = lf`, `insert_final_newline = true`, `indent_style = space`, `indent_size = 2`, and `[*.py] indent_size = 4`). Add preregistration/count_script/ruff.toml with `target-version = "py38"`, `line-length = 100` and `lint.ignore = ["B905"]`, because zip(strict=) needs Python 3.10. The maintainer chooses the widths.

Status: Deferred: committing formatter configuration comes with the formatting pass in ST-15.

</details>

<details><summary><b>ST-15</b> (MINOR): lintr style lints across the R scripts (line length, indentation, infix spacing, semicolons, braces)</summary>

Location: `preregistration/design_analysis/run_ordinal_analysis.R:103`. Verifier's verdict: confirmed.

Impact: Readability only. The compound semicolon lines at run_design_analysis.R:75 and run_ordinal_analysis.R:88 pack the error-handling logic into one line, which makes ST-03 and ST-06 harder to see on review.

Proposed fix: Adopt the .lintr from ST-14, then reformat with styler::style_file() (not installed; the maintainer installs it) and review the diff. Rewrite wilson() with spaced operators over several lines. Split the semicolon compound statements. Leave make_figure1.R's DOT strings long or build them with paste0 over several lines. Run the rebuild-and-compare gate to confirm no output changes.

Status: Deferred: styler is not installed, and a formatting-only commit should follow the sign-off on the logic changes.

</details>

<details><summary><b>ST-21</b> (MINOR): R naming inconsistencies and local names that mask base or graphics functions</summary>

Location: `preregistration/check_reported_numbers.R:32`. Verifier's verdict: confirmed.

Impact: Readability, and a latent masking hazard: once `get` is redefined in check_reported_numbers.R, any later code there calling get() by name gets the local version.

Proposed fix: Rename get to row_for, title to qmd_title, lines to dot_lines and raw to svg_raw. Use `th` everywhere, or `theory` everywhere. Name the palette OKABE_ITO in the shared file from ST-04. Keep _rename-output.R but mention it in the README.

Status: Partly resolved: the helper that masked base::get was renamed. Deferred: the remaining naming lints belong to the formatting pass (ST-15).

</details>

<details><summary><b>ST-22</b> (MINOR): The same entities carry different names across the export, specs, R code, theory object and manuscript, with no glossary</summary>

Location: `preregistration/design_analysis/tier1_developmental.json:18`. Verifier's verdict: confirmed.

Impact: A reader following a hypothesis from the manuscript to the spec, the code and the export has to map six or seven names per entity by inference. Two mappings invite error: a contrast named `age` that is really a two-level band, and a construct called "lexical accessibility" whose coefficient is labelled "Lexical difficulty", so the sign reads in opposite directions.

Proposed fix: Add the glossary with one row per entity, using only mappings the files state, and have the maintainer confirm the theory-object column before it is written. Corrections to the auditor's rows:
- child/account: theory id "(none)".
- reading time: export time_spent_reading; count script TIME_COL (validity bands only); spec response z_log_time_per_word; R response .y; theory c_processing_effort.
- difficulty rating: export story_rating; count script reports emptiness only (py:58, :568); spec response story_rating; R model reported_difficulty; theory c_experienced_difficulty.
- lexical dimension: LexPC; figure label "Lexical difficulty"; theory c_lexical_accessibility. Add a note that higher LexPC is taken to mean lower accessibility, once the maintainer confirms the sign.

Status: Deferred: the canonical names need the author's choice; the proposed glossary is in the fix below.

</details>

<details><summary><b>ST-24</b> (MINOR, HIGH-RISK): Figure script coerces the truth column with warnings suppressed; a partial coercion failure drops rows without notice</summary>

Location: `preregistration/figures/make_precision_figure.R:93`. Verifier's verdict: confirmed.

Impact: If a future sweep wrote truth as, for example, "0.10 (twice ROPE)" for some rows only, those grid points would vanish from panel a with no warning, and the curve would be drawn over fewer points. The empty-panel guard does not catch a partial loss.

Proposed fix: `truth_num <- suppressWarnings(as.numeric(res$truth)); bad <- is.na(truth_num) & !is.na(res$truth); if (any(bad)) stop("non-numeric truth values: ", paste(unique(res$truth[bad]), collapse = ", "), call. = FALSE); res$truth <- truth_num`. In prep(), also check that every param has the same number of distinct x values, e.g. `stopifnot(length(unique(table(d$param))) == 1)`, rather than typing a grid size. Afterwards, render on copies and confirm the figures are unchanged.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>ST-25</b> (MINOR): capture.js passes the legacy headless: 'new' value and disables the Chromium sandbox</summary>

Location: `mindmap/source files/capture.js:9`. Verifier's verdict: confirmed.

Impact: No functional failure on 24.40.0. The value is outside the declared type (TypeScript or a stricter future release would reject it), and turning the sandbox off is unnecessary on Windows, where there is no setuid sandbox, while the page fetches third-party content.

Proposed fix: Change :9 to `headless: true,`, which is equivalent on 24.40.0. Keep or drop :10 by maintainer decision, for example `args: process.platform === 'linux' ? ['--no-sandbox'] : []`.

Status: Deferred: changing the headless value or the sandbox flags needs a capture run with network access to confirm the figure is unchanged.

</details>

<details><summary><b>CR-03</b> (MINOR, HIGH-RISK): run_design_analysis.R labels grid points by row count and discards pilotr's own grid column, which would label them directly</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:100`. Verifier's verdict: plausible.

Impact: If precision_design ever returns fewer focal rows at some grid points, the integer check catches most cases loudly. It passes silently, though, when the dropped rows total a multiple of the grid length, and then every later row carries the wrong number of texts, producing plausible but wrong curves and crossings. pilotr is unpinned (RP-01), so its row shape can change without notice.

Proposed fix: In run_sweep, replace lines 100-103 with an exact-shape assertion and a label taken from the lead column: stopifnot(nrow(res) == length(values) * length(focal), all(table(res[[1]]) == length(focal))); res[[axis_name]] <- if (is.list(values)) axis_values[res[[1]]] else res[[1]]. Optionally add the lead column to KEEP. Needs sign-off as design_analysis logic; verify by re-solving from the committed caches that minimum_texts*.csv are unchanged.

Status: Deferred. HIGH-RISK. It changes code behind a reported number or the count script already supplied to the data controller, so it awaits maintainer sign-off.

</details>

<details><summary><b>CR-04</b> (MINOR, HIGH-RISK): Singular and non-converged fits at two readings per text are counted in the quoted precision without disclosure, and the pooled grid drops the warning and attempt counts</summary>

Location: `preregistration/design_analysis/run_design_analysis.R:172`. Verifier's verdict: confirmed.

Impact: The 2-readings-per-text point mixes four boundary fits, whose text variance collapses, into the width and verdict probability the protocol quotes. The effect is small (4 of 120), but it is invisible from the pooled artefact and the manuscript.

Proposed fix: Add n_attempted, n_warning and p_meaningful_mcse to KEEP at run_design_analysis.R:172. make_precision_figure.R reads columns by name (d$p_meaningful etc.), so extra columns do not break it, but precision_sweep.csv is regenerated, so this needs sign-off. Add one S5 sentence saying that at two readings per text, 4 of 120 fits per parameter were singular, 4 raised warnings and 116 converged, and all were retained in the widths and probabilities. Reword :137 so the per-sweep files are said to add the Monte Carlo standard errors, attempt counts and warning counts.

Status: Partly resolved 17 September 2026: S5 discloses the four singular fits at two readings per text. Deferred: the pooled CSV still omits the attempt and warning columns.

</details>

<details><summary><b>CR-06</b> (MINOR): The reference-style record in journal.json contradicts the README and the manuscript's APA 7 setting, and nature.csl is used by nothing</summary>

Location: `preregistration/README.md:5`. Verifier's verdict: confirmed.

Impact: The journal profile that other passes read says the protocol's reference style is wrong, while the README says it is right for Stage 1. Which is correct cannot be settled from the repository, and the unused CSL could be mistaken for the active one.

Proposed fix: Maintainer decision after re-checking the NHB guidelines and the editorial ruling. Either add a stage note to journal.json (for example 'reference_style_stage1_decision' citing commit 9875294 and the basis for accepting author-date at Stage 1) or switch both qmd files to nature.csl. In either case, record the source URL and retrieval date of both CSL files in the README.

Status: Deferred: journal.json records the journal's own style, and reverting to APA 7 was a deliberate decision.

</details>

<details><summary><b>CR-07</b> (MINOR): Over half the bibliography is uncited: 322 of 591 entries appear in neither the protocol, the supplement nor the cover letter</summary>

Location: `preregistration/InTRACt references.bib:1`. Verifier's verdict: confirmed.

Impact: Pandoc lists only cited works, so the rendered output is unaffected. But the hand-maintained brace protection and Crossref checks apply to twice as many entries as the manuscript uses, and a reviewer reading the deposited bib cannot tell which entries the protocol rests on.

Proposed fix: Maintainer decision. The documentation-only option (a README sentence saying the bib deliberately holds the shared review library, including uncited entries) touches no end product. Pruning to the cited set edits the bib, an end product, and should keep the full library elsewhere, such as the review repository.

Status: Deferred. The fix edits an end product (the protocol, supplement, cover letter, bibliography, a figure or results file, or the supplied count script), so it is a proposal only.

</details>

<details><summary><b>CR-09</b> (MINOR): Every figure script writes a PNG that no document uses, and the stated reason (a repository preview) does not exist</summary>

Location: `preregistration/figures/make_precision_figure.R:131`. Verifier's verdict: confirmed.

Impact: Six tracked binaries are regenerated and committed on every figure run with no consumer, and a comment gives a reason that no longer holds. They could not be mistaken for results, but they add churn to diffs and history.

Proposed fix: Maintainer decision. Either use the PNGs for the HTML format (format-specific image paths, since browsers render embedded PDFs poorly), which gives them a consumer, or stop writing and tracking them. Either way, reword make_precision_figure.R:131-132 and README.md:77-79 to match.

Status: Partly resolved: make_precision_figure.R's comment no longer claims a repository preview. Deferred: whether to stop writing the unused PNGs is a maintainer decision.

</details>

## Refuted

- FL-19, Forty-three sequential API requests with no checkpoint: one late failure discards every earlier count. The central claim is wrong. scopus_gap_analysis.R writes the gap CSV at :63, before the trend requests begin at :73, so a failure during the trends does not discard the 7 gap counts. The proposed 'move the gap CSV write to immediately after :60 (before any trend request)' describes the code as it already is. The request counts (7, then 9 + 3 x 9 = 36), the absence of any cache argument in either function's formals and max_tries 3 are correct, per the dumped source. The real residual is different. A failure during the 36 trend requests loses the trend counts gathered so far. It also leaves a new scopus_gap_sizes.csv and default PNG beside the previous run's trend CSV, record and stamp, with no error about the mixed state.
- RS-21, nature.csl is unused and neither CSL file records its source revision. Both halves fail. Keeping the unused style is intended and documented: preregistration/README.md:5 says '`nature.csl` is kept alongside it for the numbered-superscript variant Nature Human Behaviour uses at Stage 2'. The revision is also recorded: nature.csl:5 and :21, and apa7.csl:7 and :31, carry the upstream <id> and <updated> timestamps. Both files are versioned in git (last touched in e800c11 and edc4f8a), so any later refresh shows up as a diff, and the CSL that rendered a given draft is recoverable from that commit. The claimed untraceable formatting change cannot happen silently.
- RS-22, journal.json looks like configuration but nothing reads it; .vscode tracks a personal preference. preregistration/README.md:7 already describes journal.json as a record, not as enforced configuration ('`journal.json` records the limits and the date they were read'), so the first proposed fix repeats what the README says and nothing suggests the limits are enforced. .vscode/settings.json is tracked and holds only '"editor.wordWrap": "on"', a reasonable shared setting for a prose-heavy Quarto repository rather than a defect.
