# InTRACt Stage 1: precision-based design analysis.
#
# Run from the preregistration directory:  Rscript design_analysis/run_design_analysis.R
#
# What this answers. The text coefficients in Hypothesis 1 are identified between
# distinct texts, not between sessions, because every child reading a given text
# meets the same words in the same order. How many distinct texts the export holds
# is the one quantity the data controller has not yet settled: the estimate on the
# table ranges from a few hundred to a few million. The design analysis therefore
# sweeps the number of distinct texts and reports, at each value, whether the study
# could reach a determinate verdict about an effect at the smallest size worth
# caring about. A second sweep holds the number of texts fixed and varies readings
# per text, which separates the two ways of getting more data and shows which one
# the design is actually short of.
#
# Everything is on the within-language standardised scale of log reading time per
# word, so the region of practical equivalence of 0.05 standard deviations, fixed
# in the protocol, is directly comparable across sweeps.
#
# Tier 1 fits no child intercept. A child contributing a single session offers no
# way to separate child variance from residual variance, so the analysis formula
# omits that term while the simulation still generates the variance, which then
# reaches the model as inflated residual. The real fit does the same whenever the
# registered estimability rule drops the Account intercept (fewer than ten per
# cent of tier-1 readings from accounts with two or more readings). Where the
# real fit includes that intercept, these requirements are an upper bound.
#
# The deposited specifications are not simulated exactly as written. Every
# coefficient is set to 0.10 in absolute size, keeping the specification's sign
# (the null sweep sets all of them to zero), the tier-2 accumulated-reading
# coefficient is set to -0.10, and the units are replaced at every grid point.
#
# Each sweep is written to design_analysis/sweeps/ as soon as it finishes and is
# reused on a later run, so a long run can be resumed rather than restarted. A
# key file beside each sweep records the settings that produced it (see
# helpers.R), and a sweep whose settings differ from the current ones stops the
# run instead of being reused. The key does not cover the code of the tier-2
# preparation step, so delete t2_children.csv after any change to prep_t2.
# session_info.txt is written only by a run that computed at least one sweep.

library(pilotr)
source("design_analysis/helpers.R")
need_package(requireNamespace("lme4", quietly = TRUE), "lme4",
             "pilotr fits every replicate with it")

N_SIMS   <- env_number("INTRACT_N_SIMS", "200")
N_SIMS_2 <- env_number("INTRACT_N_SIMS_2", "120")
WORKERS  <- env_number("INTRACT_WORKERS", "6")
ROPE     <- 0.05
# An effect exactly the size of the region of practical equivalence can never be
# declared determinately outside it, so the meaningful-decision sweeps are run at
# twice the region's half-width, the smallest size the protocol treats as worth
# reporting.
EFFECT   <- 2 * ROPE
OUT      <- "design_analysis"
CACHE    <- file.path(OUT, "sweeps")
dir.create(CACHE, showWarnings = FALSE, recursive = TRUE)

# Analysis formulae. Tier 1 drops the child intercept; tier 2 keeps it.
F_DEV  <- .y ~ LexPC + SynPC + CohPC + age + SynPC_age + CohPC_age + (1 | item)
F_NARR <- .y ~ LexPC + CohPC + narr + LexPC_narr + CohPC_narr + (1 | item)
F_T2   <- .y ~ LexPC + SynPC + CohPC + accum + (1 | subject) + (1 | item)

# Grid points for the readings sweep, which holds the number of texts fixed.
units_by_readings <- function(per_text, texts) {
  lapply(per_text, function(m) {
    list(subject = list(n = texts * m), item = list(n = texts, per_subject = 1))
  })
}

workers <- make_worker_probe(WORKERS)
computed <- FALSE

# Runs one sweep, or reads it from design_analysis/sweeps/ if a sweep with the
# same settings is cached there.
run_sweep <- function(key, spec, path, values, focal, formula, label,
                      axis_name, axis_values, constant = list(), n_sims = N_SIMS,
                      prep = NULL) {
  cached <- file.path(CACHE, paste0(key, ".csv"))
  settings <- cache_key(sweep = key, spec = spec, path = path, values = values,
                        focal = as.list(focal), formula = deparse1(formula), rope = ROPE,
                        n_sims = n_sims, prep = if (is.null(prep)) NULL else "prep_t2")
  res <- cache_read(cached, settings)
  if (!is.null(res)) return(res)
  msg("sweep: ", key, " over ", axis_name,
      " (", length(values), " grid points, ", n_sims, " replicates each)")
  res <- sweep_spec(spec, path, values, precision_design,
                    focal = focal, formula = formula, prep = prep, rope = ROPE,
                    n_sims = n_sims, workers = workers())
  res$sweep <- label
  res[[axis_name]] <- label_grid(res, values, axis_values, focal)
  for (nm in names(constant)) res[[nm]] <- constant[[nm]]
  res$n_sims <- n_sims
  res <- cache_write(res, cached, settings)
  computed <<- TRUE
  res
}

# Grid values. M_FIXED is the mean number of readings per text: each simulated
# reader draws one text at random, so individual texts receive more or fewer.
# These are design choices, not estimates. The texts grid doubles from 50 to
# 1,600, spreading the points evenly on a log scale and bracketing every
# reading-time requirement, and the children grid spans the tier-2 requirement
# in the same way. Twelve readings per text is the middle of the readings grid,
# and 250 texts lies where a main effect's verdict is still uncertain, so each
# sweep holds the other quantity at a moderate value; the readings sweep
# shows how far the requirements move with readings per text. The texts and
# narration sweeps use N_SIMS replicates and the secondary sweeps N_SIMS_2, which
# by default keeps the Monte Carlo standard error of a decision probability near
# 0.90 at about 0.02 and 0.03; each grid point's Wilson interval reports it.
TEXTS    <- c(50, 100, 200, 400, 800, 1600)
PER_TEXT <- c(2, 5, 12, 30, 60)
M_FIXED  <- 12
K_FIXED  <- 250
CHILDREN <- c(200, 500, 1000, 2000)

all_rows <- list()
truth_alt <- sprintf("%.2f", EFFECT)

# ---- Hypotheses 1 to 3: text effects and their moderation by age band ----------

dev_spec <- load_spec(file.path(OUT, "tier1_developmental.json"))

# pilotr derives the replicate seeds from the specification's own seed (20260826
# here), so every grid point, and the alternative, null and readings sweeps,
# reuse the same replicate seeds. The simulated data still differ between grid
# points because the design size differs.
dev_alt  <- at_effect(dev_spec, EFFECT)
dev_null <- at_effect(dev_spec, 0, keep_sign = FALSE)
DEV_FOCAL <- c("LexPC", "SynPC", "CohPC", "SynPC_age", "CohPC_age")

all_rows$dev_texts <- run_sweep(
  "dev_texts", dev_alt, "units", units_by_texts(TEXTS, M_FIXED),
  focal_from(dev_alt, DEV_FOCAL), F_DEV, "texts", "texts", TEXTS,
  list(per_text = M_FIXED, truth = truth_alt, model = "developmental")
)

all_rows$dev_readings <- run_sweep(
  "dev_readings", dev_alt, "units", units_by_readings(PER_TEXT, K_FIXED),
  focal_from(dev_alt, DEV_FOCAL), F_DEV, "readings", "per_text", PER_TEXT,
  list(texts = K_FIXED, truth = truth_alt, model = "developmental"), n_sims = N_SIMS_2
)

all_rows$dev_texts_null <- run_sweep(
  "dev_texts_null", dev_null, "units", units_by_texts(TEXTS, M_FIXED),
  focal_from(dev_null, DEV_FOCAL), F_DEV, "texts", "texts", TEXTS,
  list(per_text = M_FIXED, truth = sprintf("%.2f", 0), model = "developmental"),
  n_sims = N_SIMS_2
)

# ---- Hypothesis 4: selectivity of narration ----------------------------------

narr_spec <- at_effect(load_spec(file.path(OUT, "tier1_narration.json")), EFFECT)

all_rows$narr_texts <- run_sweep(
  "narr_texts", narr_spec, "units", units_by_texts(TEXTS, M_FIXED),
  focal_from(narr_spec, c("LexPC", "CohPC", "LexPC_narr")), F_NARR, "texts", "texts", TEXTS,
  list(per_text = M_FIXED, truth = truth_alt, model = "narration")
)

# ---- Hypothesis 6: accumulated reading, within child --------------------------

t2 <- load_spec(file.path(OUT, "tier2_within_child.json"))
t2$fixed$coefficients$accum <- -EFFECT

# The protocol registers each tier-2 child as reading five distinct texts, one per
# session, with accumulated reading entered per within-child standard deviation.
# pilotr crosses a within-subject factor with every item a subject reads, so the
# simulation generates each of a child's five texts at all five session positions
# (25 rows). The preparation step draws a random reading order for each child's
# five texts and keeps each text's reading at its drawn position only, which
# leaves five rows per child on five distinct texts. The order has to be drawn
# here: pilotr returns a child's sampled texts sorted by index, so keeping the
# j-th text at the j-th position would tie session position to text identity,
# and the text intercepts would then absorb the contrast. The draw uses a seed
# computed from the simulated design alone, never from the response, and
# restores the caller's random-number state. The contrast in the specification
# has a population standard deviation of exactly 1 over the five positions, so
# the coefficient is on the registered per-SD unit. The checks below guard the
# row count, the distinct texts and the independence of position from text.
stopifnot(abs(sqrt(mean(unlist(t2$factors[[1]]$contrasts$accum)^2)) - 1) < 1e-3)
prep_t2 <- local({
  sp <- t2
  function(d) {
    d <- pilotr::model_data(sp, d)
    levels_pos <- sp$factors[[1]]$levels
    n_pos <- length(levels_pos)
    had_seed <- exists(".Random.seed", envir = globalenv(), inherits = FALSE)
    if (had_seed) old_seed <- get(".Random.seed", envir = globalenv())
    # .Random.seed is R's own name for the generator's state, so it cannot follow
    # the scripts' naming style.
    # nolint start: object_name_linter.
    on.exit(if (had_seed) assign(".Random.seed", old_seed, envir = globalenv())
            else rm(".Random.seed", envir = globalenv()))
    # nolint end
    set.seed(sum(as.numeric(d$item) * seq_len(nrow(d))) %% .Machine$integer.max)
    slot <- stats::ave(d$item, d$subject, FUN = function(v) match(v, unique(v)))
    subjects <- sort(unique(d$subject))
    order_of <- t(vapply(subjects, function(s) sample.int(n_pos), integer(n_pos)))
    drawn <- order_of[cbind(match(d$subject, subjects), slot)]
    d[drawn == match(d$session_order, levels_pos), , drop = FALSE]
  }
})
local({
  probe <- t2
  probe$units$subject$n <- 400
  d <- prep_t2(simulate_design(probe))
  per_child <- table(d$subject)
  stopifnot(all(per_child == t2$units$item$per_subject),
            all(tapply(d$item, d$subject, function(v) !anyDuplicated(v))),
            abs(stats::cor(d$item, d$accum)) < 0.08)
})

all_rows$t2 <- run_sweep(
  "t2_children", t2, "units$subject$n", CHILDREN, focal_from(t2, "accum"), F_T2,
  "children", "children", CHILDREN,
  list(texts = t2$units$item$n, per_child = t2$units$item$per_subject,
       truth = truth_alt, model = "within_child"),
  n_sims = N_SIMS_2, prep = prep_t2
)

# ---- Bind, save, and solve each curve for the target -------------------------

# The last four columns were added on 18 October 2026, after the poster copied
# this table, so they come last and the poster's copy matches the first twenty.
KEEP <- c("model", "sweep", "param", "true", "texts", "per_text", "per_child", "children",
          "mean_ci_width", "p_meaningful", "p_meaningful_lo", "p_meaningful_hi",
          "p_equivalent", "p_equivalent_lo", "p_equivalent_hi",
          "n_returned", "n_converged", "n_singular", "n_sims", "truth",
          "p_meaningful_mcse", "p_equivalent_mcse", "n_attempted", "n_warning")

res <- do.call(rbind, lapply(all_rows, function(d) {
  for (nm in setdiff(KEEP, names(d))) d[[nm]] <- NA
  d[, KEEP, drop = FALSE]
}))
rownames(res) <- NULL
utils::write.csv(res, file.path(OUT, "precision_sweep.csv"), row.names = FALSE)
msg("wrote ", file.path(OUT, "precision_sweep.csv"), " (", nrow(res), " rows)")

# Solves one parameter's curve for the swept value that reaches the target.
solve_one <- function(d, xname, target = 0.90) {
  s <- solve_at(d[[xname]], d$p_meaningful, d$n_returned, target)
  data.frame(param = d$param[1], model = d$model[1], axis = xname, target = target,
             value = s$value, lo = s$lo, hi = s$hi, note = s$note, stringsAsFactors = FALSE)
}

solved <- do.call(rbind, c(
  lapply(split(all_rows$dev_texts, all_rows$dev_texts$param), solve_one, xname = "texts"),
  lapply(split(all_rows$narr_texts, all_rows$narr_texts$param), solve_one, xname = "texts"),
  lapply(split(all_rows$t2, all_rows$t2$param), solve_one, xname = "children")
))
rownames(solved) <- NULL
utils::write.csv(solved, file.path(OUT, "minimum_texts.csv"), row.names = FALSE)
msg("wrote ", file.path(OUT, "minimum_texts.csv"))

writeLines("")
writeLines("== swept value needed for a determinate verdict nine times in ten ==")
print(solved, row.names = FALSE)
writeLines("")
writeLines("== precision by number of distinct texts (developmental model) ==")
print(all_rows$dev_texts[, c("texts", "param", "mean_ci_width", "p_meaningful",
                             "p_meaningful_lo", "p_meaningful_hi")], row.names = FALSE)
writeLines("")
writeLines("== precision by readings per text, 250 texts held fixed ==")
print(all_rows$dev_readings[, c("per_text", "param", "mean_ci_width", "p_meaningful")],
      row.names = FALSE)
writeLines("")
writeLines("== declaring practical equivalence when nothing is there ==")
print(all_rows$dev_texts_null[, c("texts", "param", "p_equivalent", "mean_ci_width")],
      row.names = FALSE)

if (computed) {
  write_session(file.path(OUT, "session_info.txt"),
                c(paste("replicates per grid point:", N_SIMS,
                        paste0("(secondary sweeps ", N_SIMS_2, ")")),
                  paste("region of practical equivalence:", ROPE)))
} else {
  msg("every sweep came from cache, so session_info.txt is left as the record of ",
      "the run that computed them")
}
msg("done")
