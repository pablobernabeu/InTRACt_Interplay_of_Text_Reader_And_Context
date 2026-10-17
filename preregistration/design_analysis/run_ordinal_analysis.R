# InTRACt Stage 1: precision for the ordinal outcome behind Hypothesis 5.
#
# Run from the preregistration directory:
#   Rscript design_analysis/run_ordinal_analysis.R
# This script reads only tier1_reported_difficulty.json, runs or reads each grid
# point, and ends by running summarise_ordinal.R, which pools the grid points
# into sweeps/ordinal_texts.csv and writes minimum_texts_ordinal.csv with the
# projection columns the protocol quotes. summarise_ordinal.R can also be run on
# its own from the cached grid points.
#
# Hypothesis 5 models the child's three-point difficulty rating with a cumulative
# logit, which the general precision routine cannot fit, since it works through a
# linear mixed model. Treating an ordered three-category response as continuous
# would answer a different question, so the simulation is kept and the fitter is
# replaced: pilotr generates the response from the same portable specification,
# and ordinal::clmm fits the model the protocol specifies. Each replicate's seed
# is set in run_point below and overrides the specification's own seed.
#
# Three features of the real setting are represented. The rating is optional and
# was absent for 25 of the 35 sessions in the structural sample, so each reading
# is retained with the availability probability set below. The protocol's
# five-rater floor is applied inside every replicate: a text with fewer than five
# rated readings contributes nothing, exactly as in the fitted model. And as in
# tier 1, a reading contributes one row per account, so no account intercept is
# fitted. The child variance is still generated. In a linear model an omitted
# intercept only inflates the residual, but in a cumulative logit it also
# attenuates every coefficient towards zero, so summarise_ordinal.R projects
# from the attenuated coefficient, and each grid point records the mean fitted
# estimate as a check on it. The floor is what makes the requirement reported
# here a function of texts *generated* rather than texts analysed; the median
# number of texts that actually qualify, and the median rated readings per
# qualifying text, are reported beside each grid point so the two scales can be
# told apart.
#
# The region of practical equivalence is an odds ratio between 1/1.05 (about
# 0.952) and 1.05, which on the log-odds scale the model works on is a
# half-width of log(1.05) = 0.0488. The sweep is run at a true effect of 0.10 log
# odds, an odds ratio of about 1.11, which is about twice the region's half-width
# (2 x 0.0488 = 0.098) and so the smallest effect the protocol treats as worth
# reporting, matching the convention used for the reading-time models. Both are
# defined once, in helpers.R.
#
# Each grid point is cached in design_analysis/sweeps/ as soon as it finishes
# and reused on a later run, so an interrupted run resumes rather than restarts.
# A key file beside each grid point records the settings that produced it (see
# helpers.R), and a grid point whose settings differ from the current ones stops
# the run instead of being reused. session_info_ordinal.txt is written only by a
# run that computed at least one grid point.

suppressPackageStartupMessages({
  library(pilotr)
  library(ordinal)
})
source("design_analysis/helpers.R")

N_SIMS   <- env_number("INTRACT_ORD_SIMS", "60")
WORKERS  <- env_number("INTRACT_WORKERS", "6")
# The default rating rate rounds the 10 of 35 sessions rated in the structural
# sample (0.286). MIN_RATERS is the protocol's five-rater floor, and M_FIXED
# matches the twelve readings per text used in run_design_analysis.R.
RATED    <- env_number("INTRACT_RATED_RATE", "0.30", integer = FALSE, min = 0, max = 1)
if (RATED == 0) stop("INTRACT_RATED_RATE must be above 0", call. = FALSE)
# 3,200 is deliberately absent from the default grid: a six-worker run at that
# size exhausted memory, and the four smaller points already pin the scaling
# law that summarise_ordinal.R projects the requirement from.
TEXTS    <- env_numbers("INTRACT_ORD_TEXTS", "200,400,800,1600", min = 1)
if (any(TEXTS != round(TEXTS))) stop("INTRACT_ORD_TEXTS must list whole numbers",
                                     call. = FALSE)
MIN_RATERS <- 5L
M_FIXED  <- 12
OUT      <- "design_analysis"
CACHE    <- file.path(OUT, "sweeps")
dir.create(CACHE, showWarnings = FALSE, recursive = TRUE)

spec0 <- at_effect(load_spec(file.path(OUT, "tier1_reported_difficulty.json")), ORD_TRUE_B)

FOCAL <- c("LexPC", "SynPC", "CohPC")

# One replicate: simulate, thin to the rated subset, apply the five-rater floor,
# fit the cumulative logit, and return the estimate and standard error of each
# focal coefficient. The thinning is seeded from the replicate's own seed, so a
# replicate reproduces identically whether it runs serially, in parallel or in a
# resumed run; pilotr already guarantees this for the simulation itself. A
# replicate that yields no estimate returns one row saying why, so that thinned
# and failed replicates are counted apart.
one_rep <- function(spec, seed) {
  status_row <- function(status) {
    data.frame(param = NA_character_, status = status, stringsAsFactors = FALSE)
  }
  spec$seed <- seed
  d <- model_data(spec, simulate_design(spec))
  set.seed(seed)
  d <- d[stats::runif(nrow(d)) < RATED, , drop = FALSE]
  n_per_text <- table(d$item)
  keep_texts <- names(n_per_text)[n_per_text >= MIN_RATERS]
  d <- d[d$item %in% keep_texts, , drop = FALSE]
  # Degenerate replicates are skipped: a cumulative logit with two thresholds, four
  # coefficients and a text variance is not estimable on a handful of rows, on
  # fewer than three observed categories, or on a few texts. The floors never bind
  # at the registered grid (200 texts give about 58 qualifying texts and 350 rated
  # readings), and run_point counts every skipped replicate, so a re-run at a lower
  # availability cannot drop replicates unseen.
  if (nrow(d) < 50 || length(unique(d$story_rating)) < 3 || length(keep_texts) < 10)
    return(status_row("thin"))
  d$y <- factor(d$story_rating, ordered = TRUE)
  d$item <- factor(d$item)
  # A warning does not make a fixed-effect estimate uninterpretable, so warnings
  # are recorded and the fit is kept; only a genuine failure discards a replicate.
  # summary() is inside the same handler because clmm reports an ill-conditioned
  # Hessian there and not at fitting time.
  warned <- FALSE
  on_warning <- function(w) {
    warned <<- TRUE
    invokeRestart("muffleWarning")
  }
  fit <- withCallingHandlers(
    tryCatch(ordinal::clmm(y ~ LexPC + SynPC + CohPC + age + (1 | item),
                           data = d, Hess = TRUE), error = function(e) e),
    warning = on_warning
  )
  if (inherits(fit, "error")) return(status_row(paste("fit_error:", conditionMessage(fit))))
  co <- withCallingHandlers(tryCatch(summary(fit)$coefficients, error = function(e) NULL),
                            warning = on_warning)
  # A non-finite standard error comes from a text variance estimated at the
  # boundary of zero. Those replicates are not a random subset: their share falls
  # from about a quarter at 200 texts to a few per cent at 1,600, so dropping them
  # would bias the widths at the small grid points and the fitted scaling exponent.
  # At the boundary the mixed model reduces to the fixed-effects cumulative logit,
  # so that model is fitted in its place and the replicate is kept and counted.
  boundary <- is.null(co) || any(!is.finite(co[intersect(FOCAL, rownames(co)), 1:2]))
  if (boundary) {
    fit <- withCallingHandlers(
      tryCatch(ordinal::clm(y ~ LexPC + SynPC + CohPC + age, data = d),
               error = function(e) e),
      warning = on_warning
    )
    if (inherits(fit, "error"))
      return(status_row(paste("fit_error:", conditionMessage(fit))))
    co <- tryCatch(summary(fit)$coefficients, error = function(e) e)
    if (inherits(co, "error")) return(status_row(paste("fit_error:", conditionMessage(co))))
  }
  rows <- intersect(FOCAL, rownames(co))
  if (!length(rows)) return(status_row("fit_error: no focal coefficient in the fit"))
  data.frame(param = rows, status = "ok", est = co[rows, "Estimate"],
             se = co[rows, "Std. Error"], n_rows = nrow(d), n_texts = length(keep_texts),
             raters_per_text = nrow(d) / length(keep_texts),
             warned = warned, boundary = boundary, stringsAsFactors = FALSE)
}

# The replicate loop is embarrassingly parallel, and every replicate carries its
# own seed, so a worker pool returns results identical to a serial run. If the
# pool cannot start, which has happened on this machine, the run falls back to
# serial rather than dying.
cl <- NULL
if (WORKERS > 1) {
  cl <- tryCatch(parallel::makePSOCKcluster(WORKERS), error = function(e) {
    msg("cluster setup failed, running serially: ", conditionMessage(e))
    NULL
  })
  if (!is.null(cl)) {
    parallel::clusterEvalQ(cl, {
      suppressPackageStartupMessages({
        library(pilotr)
        library(ordinal)
      })
    })
    parallel::clusterExport(cl, c("one_rep", "RATED", "MIN_RATERS", "FOCAL"))
  }
}

computed <- FALSE

# One grid point of k generated texts. Reads the cached summary if one with the
# same settings exists, and otherwise runs N_SIMS replicates and caches one
# summary row per focal coefficient.
run_point <- function(k) {
  cached <- file.path(CACHE, sprintf("ordinal_%d.csv", k))
  settings <- cache_key(grid_point = sprintf("ordinal_%d", k), spec = spec0, texts = k,
                        per_text = M_FIXED, n_sims = N_SIMS, rated_rate = RATED,
                        min_raters = MIN_RATERS, rope = ORD_ROPE,
                        seeds = "900000 + 1000 * texts + replicate")
  point <- cache_read(cached, settings)
  if (!is.null(point)) return(point)
  spec <- spec0
  spec$units <- list(subject = list(n = k * M_FIXED), item = list(n = k, per_subject = 1))
  msg("ordinal sweep, ", k, " texts (", N_SIMS, " replicates, ",
      if (is.null(cl)) "serial" else paste(WORKERS, "workers"), ")")
  # Consecutive seeds, offset by grid point. Grid points 200 texts apart cannot
  # share a seed below 200,000 replicates.
  seeds <- 900000L + k * 1000L + seq_len(N_SIMS)
  reps <- if (is.null(cl)) {
    lapply(seeds, function(s) one_rep(spec, s))
  } else {
    parallel::parLapply(cl, seeds, function(s) one_rep(spec, s))
  }
  status <- vapply(reps, function(r) r$status[1], "")
  n_thin <- sum(status == "thin")
  n_fit_error <- sum(startsWith(status, "fit_error"))
  if (n_fit_error)
    msg("  ", n_fit_error, " replicates failed to fit, e.g. ",
        status[startsWith(status, "fit_error")][1])
  ok <- do.call(rbind, reps[status == "ok"])
  rows <- list()
  for (pm in FOCAL) {
    r <- if (is.null(ok)) ok else ok[ok$param == pm, ]
    if (is.null(r) || !nrow(r)) next
    # Even the fixed-effects refit can leave a non-finite standard error; such a
    # replicate carries no interval and is dropped and counted.
    bad <- !is.finite(r$est) | !is.finite(r$se)
    n_bad <- sum(bad)
    r <- r[!bad, , drop = FALSE]
    if (!nrow(r)) next
    stopifnot(nrow(r) + n_bad + n_thin + n_fit_error <= N_SIMS)
    true_pm <- unname(focal_from(spec0, pm))
    lo <- r$est - 1.959964 * r$se
    hi <- r$est + 1.959964 * r$se
    # Hypothesis 5 is directional, so only a determinate verdict in the direction
    # of the true effect counts as a success.
    meaningful <- if (true_pm > 0) lo > ORD_ROPE else hi < -ORD_ROPE
    equivalent <- (lo > -ORD_ROPE) & (hi < ORD_ROPE)
    w <- wilson(sum(meaningful), nrow(r))
    rows[[length(rows) + 1L]] <- data.frame(
      model = "reported_difficulty", sweep = "texts", param = pm,
      true = true_pm,
      texts = k, per_text = M_FIXED, rated_rate = RATED, min_raters = MIN_RATERS,
      median_qualifying_texts = stats::median(r$n_texts),
      median_raters_per_text = round(stats::median(r$raters_per_text), 2),
      # The mean fitted estimate, which the omitted child intercept attenuates
      # towards zero. summarise_ordinal.R checks its analytic attenuation against it.
      mean_est = mean(r$est), sd_est = stats::sd(r$est),
      mean_se = mean(r$se),
      mean_ci_width = mean(hi - lo),
      p_meaningful = mean(meaningful),
      p_meaningful_lo = w[1], p_meaningful_hi = w[2],
      p_equivalent = mean(equivalent),
      n_returned = nrow(r), n_boundary = sum(r$boundary), n_bad_se = n_bad,
      n_skipped = N_SIMS - nrow(r) - n_bad, n_thin = n_thin, n_fit_error = n_fit_error,
      n_warned = sum(r$warned), n_sims = N_SIMS, rope = ORD_ROPE,
      stringsAsFactors = FALSE
    )
  }
  if (!length(rows))
    stop("no replicate at ", k, " texts returned an estimate (", n_thin, " thinned, ",
         n_fit_error, " failed to fit)", call. = FALSE)
  point <- do.call(rbind, rows)
  point <- cache_write(point, cached, settings)
  computed <<- TRUE
  point
}

res <- do.call(rbind, lapply(TEXTS, run_point))
if (!is.null(cl)) parallel::stopCluster(cl)

writeLines("")
writeLines("== ordinal outcome: precision by number of texts generated ==")
print(res[order(res$param, res$texts),
          c("param", "texts", "median_qualifying_texts", "median_raters_per_text",
            "mean_est", "mean_ci_width", "p_meaningful", "p_meaningful_lo",
            "p_meaningful_hi", "n_returned", "n_boundary", "n_bad_se", "n_skipped",
            "n_warned")],
      row.names = FALSE)

if (computed) {
  write_session(file.path(OUT, "session_info_ordinal.txt"),
                c(paste("grid points:", paste(TEXTS, collapse = ", ")),
                  paste("replicates per grid point:", N_SIMS),
                  paste("rating availability:", RATED)))
}

# The pooled grid and the solved and projected requirement.
source(file.path(OUT, "summarise_ordinal.R"))
msg("done")
