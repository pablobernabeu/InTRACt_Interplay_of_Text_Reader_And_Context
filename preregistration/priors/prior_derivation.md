# From the review's effects to the Registered Report's priors

Decision (August 2026, Pablo): the InTRACt Stage 1 Registered Report will use
**literature-derived informative priors as the primary priors** for its
confirmatory coefficients, derived from this review's extraction. This document
freezes the derivation methodology before any extraction rows exist, so the
pipeline cannot be tuned to the data it will consume. The concrete
implementation will be a deterministic script (`tools/derive_priors.py`)
joining `extraction/corrected_effect_sizes.csv` many-to-one to
`extraction/corrected_extraction.csv` on `record_id` and writing a prior table for the
Registered Report's supplement; it must follow the rules below and be run —
and its output frozen — **before any Applaydu outcome data are accessed**.
The script must fail if an effect row has no wide row or if the wide file has
duplicate `record_id` values; it may not guess an age stratum from free text.

## 1. Mapping review evidence to model coefficients

**Revised August 2026.** The Registered Report was rebuilt around the variables the
platform is confirmed to hold, and the mapping below is against that hypothesis set,
not the July one. The change is not cosmetic: every confirmatory prediction now
concerns **log reading time per word** or an **ordinal rating of the text just read**,
and quiz accuracy has moved to a contingent annex. A prior derived from comprehension
evidence therefore no longer serves a single confirmatory coefficient, which is why the
review's outcome criterion broadened to admit processing and rating outcomes (see
`preliminary_screening/search_parameters.md`).

| RR prediction | Coefficient | Review evidence pooled | Outcome class required |
| --- | --- | --- | --- |
| `pred_h1_lexical` | lexical difficulty → reading time | `effect_word_frequency_on_reading`, `effect_lexical_coverage_on_reading`, `effect_other_lexical_on_reading` (AoA, word length, surprisal, rarity/familiarity), `effect_lexical_diversity_on_reading` | `reading_time`, `fixation_duration` |
| `pred_h1_syntax` | grammatical integration load → reading time | `effect_syntactic_complexity_on_reading`, `effect_sentence_length_on_reading` | `reading_time`, `fixation_duration` |
| `pred_h1_coherence` | referential continuity → reading time | `effect_coherence_on_reading` | `reading_time`, `fixation_duration` |
| `pred_h2_syntax_by_age` | syntax × age band | the syntax rows, with `sample_age_stratum` as moderator (§3a) | `reading_time`, `fixation_duration` |
| `pred_h3_coherence_by_age` | coherence × age band | the coherence rows, with `sample_age_stratum` as moderator (§3a) | `reading_time`, `fixation_duration` |
| `pred_h4_narration_selectivity` | differential attenuation of the lexical and coherence coefficients under narration | `effect_narration_main` rows on a processing outcome, plus any paper reporting text-feature effects separately with and without narration | `reading_time`, `fixation_duration` |
| `pred_h5_reported_difficulty` | text features → rated difficulty | rows whose `outcome_construct` is `subjective_difficulty` | `subjective_difficulty` |
| `pred_h6_accumulated_reading` | accumulated reading → reading pace | `effect_reading_frequency_on_reading` rows whose outcome class is pace | `reading_time`, `oral_reading_rate` (flagged; see below) |
| Context only: `effect_reading_rate_on_comprehension` | — | pace as a *predictor* of comprehension; its outcome is comprehension by construction, so it informs the Background and the contingent annex, never a pace-outcome prior | `comprehension_accuracy`, `comprehension_composite` |
| Contingent annex (quiz accuracy) | text features and narration → item accuracy | the same effect columns, comprehension rows | `comprehension_accuracy`, `comprehension_composite` |

Sign harmonisation is unchanged in principle. Within the lexical family, frequency and
coverage are flipped so that every row points in a **difficulty** direction; syntax rows
keep a complexity direction; coherence rows keep a facilitation direction. What changes
is the outcome side: `outcome_direction` now has to carry `subjective_difficulty` as a
*lower_better* construct, so that a text rated harder harmonises with a text read more
slowly rather than with a text comprehended better.

**Outcome classes are pooled separately and never mixed.** A comprehension effect and a
reading-time effect for the same predictor are different quantities on different scales
with, frequently, opposite signs — harder text lowers accuracy and raises reading time.
`outcome_construct` is the field that keeps them apart, and pooling runs within a class.
Rows with `outcome_direction = unclear` are excluded from pooling and listed.

`oral_reading_rate` is admitted for H6 only, and flagged: oral reading is not the
Report's silent self-paced outcome, so those rows enter a sensitivity pool rather than
the primary one, and the primary/sensitivity split is reported.

**Where the evidence is thin, say so rather than manufacture a prior.** A full-text scan
of the 57 includes before the outcome broadening found roughly six papers with any child
reading-time data on a text feature, and the ERIC and Europe PMC harvests returned 13 and
25 hits respectively for the rated-difficulty strand. If a coefficient still has fewer
than two contributing papers after the new screening, it keeps the weakly informative
prior of §5 and the Report says which coefficients those are.

## 2. Effect metrics: retain broadly, pool narrowly

Automated extraction is least reliable for numerical detail, and a mathematically
available conversion is not necessarily a scientifically valid one. The extraction
therefore retains every reported type, while derivation uses **metric families**. It
must never treat a standardised regression coefficient, zero-order correlation,
partial correlation, standardised mean difference and odds ratio as interchangeable.

The primary prior for a standardised regression coefficient uses directly reported
`beta_std` estimates on the mapped predictor and outcome scale. If fewer than two
independent papers remain, §5's weakly informative prior is used; estimates are not
mixed merely to raise *k*. Separate, clearly named sensitivity pools may use:

1. **Correlation family:** direct Pearson `r`; `rho` is a rank-correlation sensitivity,
   never silently relabelled as Pearson *r*. A signed partial *r* may be derived from
   *t* and denominator df, or from *F* only when numerator df = 1, as
   `sign × sqrt(statistic / (statistic + denominator_df))` for *F* and
   `sign × sqrt(t^2 / (t^2 + df))` for *t*. Fisher-*z* pooling follows conversion.
2. **Partial-association sensitivity:** `eta2_p` may become signed
   `sqrt(eta2_p)`, and `f2` signed `sqrt(f2/(1+f2))`, only for a one-df effect with
   an explicit `direction`. Otherwise they are retained but excluded from numerical
   pooling. These are not zero-order correlations.
3. **Semipartial sensitivity:** `r2_change` may become signed
   `sqrt(r2_change)` only with an explicit direction. It is a semipartial correlation
   and is never pooled in the partial- or zero-order-correlation pool.
4. **Design-specific contrasts:** `d`/`g` and `or`/`log_or` stay in their own
   families. A conversion is allowed only when the paper's design, coding, group
   allocation and outcome make the target coefficient identifiable; the conversion
   and assumptions must be emitted in the audit table. No generic OR→d→r or d→r
   chain is used for continuous-predictor coefficients.
5. `b_unstd`, `b_unclear`, and `other` are retained but excluded unless the exact
   predictor and outcome scaling needed for a pre-specified conversion is present.
   `direction_only` never supplies a magnitude; it enters only the separately
   reported sign-consistency check.

Every conversion output records the source `effect_id`, formula, inputs and target
family. Rows that cannot be converted are listed with a machine-readable exclusion
reason. This trades some apparent sample size for a much lower risk of a precisely
estimated but conceptually wrong prior.

## 3. Pooling model

Within each (coefficient, outcome class, metric family): a random-effects
meta-analysis on the common scale with **one estimate per paper per relation**
(`is_primary = yes`; `record_id` is the clustering unit). When all eligible estimates
are retained in a sensitivity analysis, dependence is handled with a multilevel model
or robust variance estimation; labelled subgroups and alternative specifications are
never analysed as independent studies. Estimate the pooled mean μ̂, its standard
error, and the between-study SD τ̂ (REML; Bayesian RE model as a sensitivity). k, the
paper list, metric family, exclusions and forest plots go in the RR supplement.

## 3a. The age moderator

The population criterion broadened in August 2026 from ages 7-10 to ages 7 and older
within compulsory schooling, because the Report's own age variable is a contrast between
a 7-8 band and an open-ended 9+ band (`preliminary_screening/search_parameters.md`,
*Population: why 7 and older*). Broadening the gate must not broaden the prior's centre:
a coefficient pooled indiscriminately over 8-year-olds and 15-year-olds would sit
somewhere neither band occupies.

The arrangement is therefore:

- **Primary pool:** rows for which `sample_in_target_age_band = yes` **and**
  `sample_age_stratum = core_7_10`. This is the prior the Report uses.
- **Moderated pool:** rows with band `yes` or `partial` and a known stratum
  (`core_7_10`, `older_11_18`, or `spans_7_18`), with stratum entered as a
  categorical moderator in the random-effects model. Its estimate is the review's own
  evidence on whether text-feature effects shrink with age, which is what
  `pred_h2_syntax_by_age` and `pred_h3_coherence_by_age` predict — so the moderator is
  reported next to those predictions rather than buried in a sensitivity table.
- **Sensitivity:** the pooled estimate over all known strata, unmoderated. Rows with
  band `partial` are flagged and enter only moderated/sensitivity analyses.

`spans_7_18` rows enter the moderated and sensitivity pools, never the primary one,
because their contribution cannot be attributed to a band. When the primary pool has
fewer than two papers for a coefficient but the moderated pool does not, the Report
reports the moderated estimate and states the substitution explicitly; it does not
silently promote it.

Rows with `sample_in_target_age_band = no` or `unclear` must have
`sample_age_stratum = unclear`. Any unclear-stratum row is excluded from the primary
and moderated age analyses. Otherwise-eligible rows whose age is unclear may appear
only in a separately labelled unknown-age sensitivity; they never increase the *k*
used to justify an age-specific informative prior.

## 4. Double-counting guard

A `*_pooled` row (meta-analysis) and primary studies it subsumes may both be in
the corpus; the long rows' `notes` flag the overlap. Rule: prefer the pooled
row and drop the overlapping primaries **when the meta-analysis covers ≥ 3
corpus primaries**; otherwise use the primaries and drop the pooled row. Either
way, report the alternative as a sensitivity.

## 5. From pooled estimate to prior

For a confirmatory coefficient with a pooled review estimate (translated to the
model's scale — within-language standardised β for reading time; log odds for
accuracy):

- **Location:** the pooled, harmonised estimate μ̂ (sign preserved).
- **Scale:** `2 × sqrt(SE(μ̂)² + τ̂²)`, floored at 0.10 (reading-time β scale)
  or 0.10 log-odds (quiz scale). The doubling plus floor guards against the
  lab-to-app ecological gap: review outcomes are lab comprehension tests and
  reading times, not in-app quizzes and passive timing.
- **Shape:** Student-t with ν = 3 (heavy tails let the data override a
  misplaced centre).
- **Fallback:** coefficients with no pooled estimate (k < 2 papers, or
  interactions) keep the generic weakly informative priors
  (`t(3, 0, 0.5)` mains; `t(3, 0, 0.25)` interactions).
- **Sensitivities (pre-specified):** (a) generic weakly-informative priors for
  every coefficient; (b) halved and doubled derived scales; (c) the §4
  alternative pooling.

## 6. Draft replacement text for the preregistration's Analytic Plan

> Priors for the confirmatory coefficients are derived from the accompanying
> systematic review (OSF/GitHub: InTRACt literature review) through a
> deterministic, archived pipeline frozen before any outcome data were
> accessed. For each confirmatory main effect, the review's extracted
> estimates for the corresponding predictor family and outcome class were
> sign-harmonised, classified into compatible metric families, and pooled with a
> random-effects meta-analysis (one estimate per study per relation). Estimates
> were pooled within an outcome class, never across classes, so that a
> reading-time coefficient is informed only by reading-time evidence and the
> rating coefficient only by rated-difficulty evidence. The primary pool was
> restricted to samples both confirmed in the target band and in the 7-10 stratum;
> the same estimates were refitted
> with the age stratum as a moderator, and that moderator is reported alongside
> the two age-band predictions. The
> prior is Student's t(3, μ̂, σ), where μ̂ is the pooled estimate translated to
> the model scale and σ is twice the combined pooling and between-study
> uncertainty, floored at 0.10; the full prior table, forest plots, and
> conversion rules appear in Supplement X. Coefficients without adequate
> review evidence — all interaction terms and any family with fewer than two
> contributing studies — retain weakly informative priors, t(3, 0, 0.5) for
> standardised main effects and t(3, 0, 0.25) for interactions. Sensitivity
> analyses refit all models with (a) weakly informative priors throughout and
> (b) halved and doubled derived prior scales; conclusions are reported under
> each.

The prereg's existing sentence assigning generic weakly-informative priors to
all effects, and the prior-sensitivity sentence, are superseded by the above;
the intercept, SD, and LKJ priors are unchanged.

## 7. Interlocking obligations

- The extraction reliability protocol (dual extraction, §2b of the
  instructions) supplies estimate-detection, grouping and per-field agreement
  statistics the RR methods section cites for the pipeline feeding these priors.
- `deterministic_extraction.md` §"From extraction to priors" states the
  consumption contract the script must honour (clustering, `is_primary`,
  sign harmonisation, pooled-row guard).
- `preliminary_screening/search_parameters.md` defines the population and outcome
  criteria this document assumes: ages 7 and older within compulsory schooling, and
  three outcome classes of which two exist specifically to serve the confirmatory
  coefficients here. Narrowing either criterion invalidates the mapping in §1.
- Any change to this document after extraction rows exist must be flagged as a
  deviation in the RR.
