# InTRACt Stage 1: precision for the ordinal outcome behind Hypothesis 5.
#
# Run from the preregistration directory, after run_design_analysis.R:
#   Rscript design_analysis/run_ordinal_analysis.R
#
# Hypothesis 5 models the child's three-point difficulty rating with a cumulative
# logit, which the general precision routine cannot fit, since it works through a
# linear mixed model. Treating an ordered three-category response as continuous
# would answer a different question, so the simulation is kept and the fitter is
# replaced: pilotr generates the response from the same portable specification,
# with the same seed discipline, and ordinal::clmm fits the model the protocol
# actually specifies.
#
# Three features of the real setting are represented. The rating is optional and
# was absent for 25 of the 35 sessions in the structural sample, so each reading
# is retained with the availability probability set below. The protocol's
# five-rater floor is applied inside every replicate: a text with fewer than five
# rated readings contributes nothing, exactly as in the fitted model. And as in
# tier 1, a reading contributes one row per account, so no account intercept is
# fitted. The floor is what makes the requirement reported here a function of
# texts *generated* rather than texts analysed; the median number of texts that
# actually qualify, and the median rated readings per qualifying text, are
# reported beside each grid point so the two scales can be told apart.
#
# The region of practical equivalence is an odds ratio between 0.95 and 1.05,
# which on the log-odds scale the model works on is a half-width of
# log(1.05) = 0.0488. The sweep is run at a true effect of 0.10 log odds, an
# odds ratio of about 1.11, which is twice the region's half-width and so the
# smallest effect the protocol treats as worth reporting, matching the
# convention used for the reading-time models.
#
# Each grid point is cached in design_analysis/sweeps/ as soon as it finishes
# and skipped on a later run, so an interrupted run resumes rather than
# restarts. Delete ordinal_*.csv there to force a rerun.

suppressPackageStartupMessages({
  library(pilotr)
  library(ordinal)
})

N_SIMS   <- as.integer(Sys.getenv("INTRACT_ORD_SIMS", "60"))
WORKERS  <- as.integer(Sys.getenv("INTRACT_WORKERS", "6"))
RATED    <- as.numeric(Sys.getenv("INTRACT_RATED_RATE", "0.30"))
# 3,200 is deliberately absent from the default grid: a six-worker run at that
# size exhausted memory, and the four smaller points already pin the scaling
# law that summarise_ordinal.R projects the requirement from.
TEXTS    <- as.numeric(strsplit(Sys.getenv("INTRACT_ORD_TEXTS",
                                           "200,400,800,1600"), ",")[[1]])
MIN_RATERS <- 5L
M_FIXED  <- 12
TRUE_B   <- 0.10
ROPE     <- log(1.05)
OUT      <- "design_analysis"
CACHE    <- file.path(OUT, "sweeps")
dir.create(CACHE, showWarnings = FALSE, recursive = TRUE)

msg <- function(...) { cat(format(Sys.time(), "%H:%M:%S"), " ", ..., "\n", sep = ""); flush.console() }

spec0 <- load_spec(file.path(OUT, "tier1_reported_difficulty.json"))
for (nm in names(spec0$fixed$coefficients))
  spec0$fixed$coefficients[[nm]] <- sign(spec0$fixed$coefficients[[nm]]) * TRUE_B

FOCAL <- c("LexPC", "SynPC", "CohPC")

# One replicate: simulate, thin to the rated subset, apply the five-rater floor,
# fit the cumulative logit, and return the estimate and standard error of each
# focal coefficient. The thinning is seeded from the replicate's own seed, so a
# replicate reproduces identically whether it runs serially, in parallel or in a
# resumed run; pilotr already guarantees this for the simulation itself.
one_rep <- function(spec, seed) {
  spec$seed <- seed
  d <- model_data(spec, simulate_design(spec))
  set.seed(seed)
  d <- d[stats::runif(nrow(d)) < RATED, , drop = FALSE]
  n_per_text <- table(d$item)
  keep_texts <- names(n_per_text)[n_per_text >= MIN_RATERS]
  d <- d[d$item %in% keep_texts, , drop = FALSE]
  if (nrow(d) < 50 || length(unique(d$story_rating)) < 3 || length(keep_texts) < 10)
    return(NULL)
  d$y <- factor(d$story_rating, ordered = TRUE)
  d$item <- factor(d$item)
  # A warning does not make a fixed-effect estimate uninterpretable, so warnings
  # are recorded and the fit is kept; only a genuine failure discards a replicate.
  warned <- FALSE
  fit <- withCallingHandlers(
    tryCatch(ordinal::clmm(y ~ LexPC + SynPC + CohPC + age + (1 | item),
                           data = d, Hess = TRUE), error = function(e) NULL),
    warning = function(w) { warned <<- TRUE; invokeRestart("muffleWarning") })
  if (is.null(fit)) return(NULL)
  co <- tryCatch(summary(fit)$coefficients, error = function(e) NULL)
  if (is.null(co)) return(NULL)
  rows <- intersect(FOCAL, rownames(co))
  if (!length(rows)) return(NULL)
  data.frame(param = rows, est = co[rows, "Estimate"], se = co[rows, "Std. Error"],
             n_rows = nrow(d), n_texts = length(keep_texts),
             raters_per_text = nrow(d) / length(keep_texts),
             warned = warned, stringsAsFactors = FALSE)
}

wilson <- function(k, n) {
  if (n == 0) return(c(NA, NA))
  z <- 1.959964; p <- k / n
  c((p + z^2/(2*n) - z*sqrt(p*(1-p)/n + z^2/(4*n^2))) / (1 + z^2/n),
    (p + z^2/(2*n) + z*sqrt(p*(1-p)/n + z^2/(4*n^2))) / (1 + z^2/n))
}

# The replicate loop is embarrassingly parallel, and every replicate carries its
# own seed, so a worker pool returns results identical to a serial run. If the
# pool cannot start, which has happened on this machine, the run falls back to
# serial rather than dying.
cl <- NULL
if (WORKERS > 1) {
  cl <- tryCatch(parallel::makePSOCKcluster(WORKERS), error = function(e) {
    msg("cluster setup failed, running serially: ", conditionMessage(e)); NULL })
  if (!is.null(cl)) {
    parallel::clusterEvalQ(cl, { suppressPackageStartupMessages({
      library(pilotr); library(ordinal) }) })
    parallel::clusterExport(cl, c("one_rep", "RATED", "MIN_RATERS", "FOCAL"))
  }
}

run_point <- function(k) {
  cached <- file.path(CACHE, sprintf("ordinal_%d.csv", k))
  if (file.exists(cached)) {
    msg("cached: ", basename(cached))
    return(utils::read.csv(cached, stringsAsFactors = FALSE))
  }
  spec <- spec0
  spec$units <- list(subject = list(n = k * M_FIXED), item = list(n = k, per_subject = 1))
  msg("ordinal sweep, ", k, " texts (", N_SIMS, " replicates, ",
      if (is.null(cl)) "serial" else paste(WORKERS, "workers"), ")")
  seeds <- 900000L + k * 1000L + seq_len(N_SIMS)
  reps <- if (is.null(cl)) lapply(seeds, function(s) one_rep(spec, s))
          else parallel::parLapply(cl, seeds, function(s) one_rep(spec, s))
  reps <- do.call(rbind, Filter(Negate(is.null), reps))
  if (is.null(reps)) return(NULL)
  rows <- list()
  for (pm in FOCAL) {
    r <- reps[reps$param == pm, ]
    if (!nrow(r)) next
    # clmm occasionally returns a non-finite standard error when the Hessian is
    # ill-conditioned; such a replicate carries no interval and is dropped and
    # counted rather than silently turning the summary into NaN.
    bad <- !is.finite(r$est) | !is.finite(r$se)
    n_bad <- sum(bad)
    r <- r[!bad, , drop = FALSE]
    if (!nrow(r)) next
    lo <- r$est - 1.959964 * r$se
    hi <- r$est + 1.959964 * r$se
    meaningful <- (lo > ROPE) | (hi < -ROPE)
    equivalent <- (lo > -ROPE) & (hi < ROPE)
    w <- wilson(sum(meaningful), nrow(r))
    rows[[length(rows) + 1L]] <- data.frame(
      model = "reported_difficulty", sweep = "texts", param = pm,
      true = TRUE_B * sign(spec0$fixed$coefficients[[pm]]),
      texts = k, per_text = M_FIXED, rated_rate = RATED, min_raters = MIN_RATERS,
      median_qualifying_texts = stats::median(r$n_texts),
      median_raters_per_text = round(stats::median(r$raters_per_text), 2),
      mean_ci_width = mean(hi - lo),
      p_meaningful = mean(meaningful),
      p_meaningful_lo = w[1], p_meaningful_hi = w[2],
      p_equivalent = mean(equivalent),
      n_returned = nrow(r), n_bad_se = n_bad, n_warned = sum(r$warned), n_sims = N_SIMS,
      stringsAsFactors = FALSE)
  }
  point <- do.call(rbind, rows)
  utils::write.csv(point, cached, row.names = FALSE)
  msg("  wrote ", cached)
  point
}

res <- do.call(rbind, Filter(Negate(is.null), lapply(TEXTS, run_point)))
if (!is.null(cl)) parallel::stopCluster(cl)
utils::write.csv(res, file.path(CACHE, "ordinal_texts.csv"), row.names = FALSE)

solve_one <- function(d, target = 0.90) {
  d <- d[order(d$texts), ]
  frame <- data.frame(x = d$texts, p_meaningful = d$p_meaningful, n_returned = d$n_returned)
  out <- tryCatch(solve_curve(frame, target = target), error = function(e) NULL)
  base <- data.frame(param = d$param[1], model = "reported_difficulty", axis = "texts",
                     target = target, stringsAsFactors = FALSE)
  if (is.null(out))
    return(cbind(base, value = NA_real_, lo = NA_real_, hi = NA_real_,
                 note = paste0("not reached within ", min(d$texts), " to ", max(d$texts))))
  cbind(base, value = out$value, lo = out$lo, hi = out$hi, note = "")
}

solved <- do.call(rbind, lapply(split(res, res$param), solve_one))
rownames(solved) <- NULL
utils::write.csv(solved, file.path(OUT, "minimum_texts_ordinal.csv"), row.names = FALSE)

writeLines("")
writeLines("== ordinal outcome: precision by number of texts generated ==")
print(res[order(res$param, res$texts),
          c("param", "texts", "median_qualifying_texts", "median_raters_per_text",
            "mean_ci_width", "p_meaningful", "p_meaningful_lo", "p_meaningful_hi",
            "n_returned", "n_bad_se", "n_warned")],
      row.names = FALSE)
writeLines("")
writeLines("== texts generated for a determinate verdict nine times in ten ==")
print(solved, row.names = FALSE)
msg("done")
