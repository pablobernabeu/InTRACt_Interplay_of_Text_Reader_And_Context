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
# Two features of the real setting are represented. The rating is optional and was
# absent for 25 of the 35 sessions in the structural sample, so only a fraction of
# simulated readings are retained. As in tier 1, a reading contributes one row per
# account, so no account intercept is fitted.
#
# The region of practical equivalence is an odds ratio between 0.95 and 1.05, which
# on the log-odds scale the model works on is a half-width of log(1.05) = 0.0488.
# The sweep is run at a true effect of 0.10 log odds, an odds ratio of about 1.11,
# which is twice the region's half-width and so the smallest effect the protocol
# treats as worth reporting, matching the convention used for reading time.

suppressPackageStartupMessages({
  library(pilotr)
  library(ordinal)
})

N_SIMS   <- as.integer(Sys.getenv("INTRACT_ORD_SIMS", "150"))
RATED    <- as.numeric(Sys.getenv("INTRACT_RATED_RATE", "0.30"))
TEXTS    <- as.numeric(strsplit(Sys.getenv("INTRACT_ORD_TEXTS", "200,400,800,1600,3200"), ",")[[1]])
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

# One replicate: simulate, thin to the rated subset, fit the cumulative logit, and
# return the estimate and standard error of each focal coefficient.
one_rep <- function(spec, seed) {
  spec$seed <- seed
  d <- model_data(spec, simulate_design(spec))
  keep <- stats::runif(nrow(d)) < RATED
  d <- d[keep, , drop = FALSE]
  if (nrow(d) < 50 || length(unique(d$story_rating)) < 3) return(NULL)
  d$y <- factor(d$story_rating, ordered = TRUE)
  d$item <- factor(d$item)
  # A warning does not make a fixed-effect estimate uninterpretable, so warnings are
  # recorded and the fit is kept; only a genuine failure discards the replicate.
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
             n = nrow(d), warned = warned, stringsAsFactors = FALSE)
}

wilson <- function(k, n) {
  if (n == 0) return(c(NA, NA))
  z <- 1.959964; p <- k / n
  c((p + z^2/(2*n) - z*sqrt(p*(1-p)/n + z^2/(4*n^2))) / (1 + z^2/n),
    (p + z^2/(2*n) + z*sqrt(p*(1-p)/n + z^2/(4*n^2))) / (1 + z^2/n))
}

cached <- file.path(CACHE, "ordinal_texts.csv")
if (file.exists(cached)) {
  msg("cached: ordinal_texts")
  res <- utils::read.csv(cached, stringsAsFactors = FALSE)
} else {
  rows <- list()
  for (k in TEXTS) {
    spec <- spec0
    spec$units <- list(subject = list(n = k * M_FIXED), item = list(n = k, per_subject = 1))
    msg("ordinal sweep, ", k, " texts (", N_SIMS, " replicates)")
    reps <- lapply(seq_len(N_SIMS), function(i) one_rep(spec, seed = 900000L + k * 1000L + i))
    reps <- do.call(rbind, Filter(Negate(is.null), reps))
    if (is.null(reps)) next
    for (pm in FOCAL) {
      r <- reps[reps$param == pm, ]
      if (!nrow(r)) next
      lo <- r$est - 1.959964 * r$se
      hi <- r$est + 1.959964 * r$se
      meaningful <- (lo > ROPE) | (hi < -ROPE)
      equivalent <- (lo > -ROPE) & (hi < ROPE)
      w <- wilson(sum(meaningful), nrow(r))
      rows[[length(rows) + 1L]] <- data.frame(
        model = "reported_difficulty", sweep = "texts", param = pm,
        true = TRUE_B * sign(spec0$fixed$coefficients[[pm]]),
        texts = k, per_text = M_FIXED, rated_rate = RATED,
        mean_ci_width = mean(hi - lo),
        p_meaningful = mean(meaningful),
        p_meaningful_lo = w[1], p_meaningful_hi = w[2],
        p_equivalent = mean(equivalent),
        median_rated_sessions = stats::median(r$n),
        n_returned = nrow(r), n_warned = sum(r$warned), n_sims = N_SIMS,
        stringsAsFactors = FALSE)
    }
  }
  res <- do.call(rbind, rows)
  utils::write.csv(res, cached, row.names = FALSE)
  msg("wrote ", cached)
}

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
writeLines("== ordinal outcome: precision by number of distinct texts ==")
print(res[order(res$param, res$texts),
          c("param", "texts", "median_rated_sessions", "mean_ci_width",
            "p_meaningful", "p_meaningful_lo", "p_meaningful_hi", "n_returned")],
      row.names = FALSE)
writeLines("")
writeLines("== texts needed for a determinate verdict nine times in ten ==")
print(solved, row.names = FALSE)
msg("done")
