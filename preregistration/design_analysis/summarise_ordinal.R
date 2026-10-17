# Pool the cached ordinal grid points, try to solve for the 0.90 target, and,
# where the target lies beyond the range simulated, project the requirement from
# the observed scaling of the standard error.
#
# run_ordinal_analysis.R runs this script at its end. It can also be run on its
# own from the preregistration directory, on the cached grid points:
#   Rscript design_analysis/summarise_ordinal.R
#
# Reads design_analysis/sweeps/ordinal_<k>.csv. Writes sweeps/ordinal_texts.csv
# and minimum_texts_ordinal.csv, with the projection columns the protocol quotes.
#
# solve_curve refuses to extrapolate, which is right: a preregistration should
# not quote a crossing the simulation never reached. What can be reported
# instead is the scaling law the simulation did establish. The grid points
# estimate how the interval width falls with the number of texts, the exponent
# is written beside the theoretical -0.5 as width_scaling_exponent, and the
# fitted line gives the number of texts at which the width reaches the value a
# determinate verdict needs. That projection is labelled as a projection
# wherever it is quoted.
#
# The width needed is computed from the attenuated coefficient, not from the true
# one. The simulation generates child variance that the fitted model omits, and
# in a logit model that omission attenuates every coefficient towards zero by
# about 1 / sqrt(1 + c^2 sd^2), with c = 16 sqrt(3) / (15 pi) (Zeger, Liang &
# Albert, 1988), so a verdict has to clear the region boundary from the
# attenuated value. The factor is computed analytically from the specification's
# child standard deviation, because at 60 replicates a grid point the simulated
# mean estimate is too noisy to resolve an attenuation of a few per cent, and the
# requirement is sensitive to it through the small gap between the effect and the
# region. The replicate-weighted mean of the fitted estimates is written beside
# it, with its Monte Carlo standard error, as a check on the approximation, and
# the projection from the true value as projected_texts_unattenuated.

suppressPackageStartupMessages(library(pilotr))
source("design_analysis/helpers.R")

OUT    <- "design_analysis"
CACHE  <- file.path(OUT, "sweeps")
TARGET <- 0.90
Z95    <- 1.959964
Z90    <- stats::qnorm(TARGET)

# Grid points cached before the thinned and failed counts were recorded lack
# those columns, so every file is given the union of the columns before binding.
files <- list.files(CACHE, pattern = "^ordinal_[0-9]+\\.csv$", full.names = TRUE)
stopifnot(length(files) >= 3)
parts <- lapply(files, utils::read.csv, stringsAsFactors = FALSE)
cols <- unique(unlist(lapply(parts, names)))
res <- do.call(rbind, lapply(parts, function(p) {
  for (nm in setdiff(cols, names(p))) p[[nm]] <- NA
  p[, cols]
}))
res <- res[order(res$param, res$texts), ]
stopifnot(all(c("mean_est", "n_boundary", "n_skipped") %in% names(res)))
# The pooled points must come from one design: one rating rate, one rater floor,
# one replicate count and one effect size, and the region they were scored
# against, where recorded, must be the one the projection uses.
single <- function(x) length(unique(x)) == 1
stopifnot(single(res$rated_rate), single(res$min_raters), single(res$n_sims),
          single(abs(res$true)))
ROPE <- ORD_ROPE
if ("rope" %in% names(res)) stopifnot(all(is.na(res$rope) | abs(res$rope - ROPE) < 1e-12))
utils::write.csv(res, file.path(CACHE, "ordinal_texts.csv"), row.names = FALSE)

# A determinate verdict nine times in ten requires the 95 per cent interval to
# clear the region boundary with room for sampling variation in the estimate:
# ROPE + 1.96 se + qnorm(.90) se < expected estimate.
width_for <- function(b) 2 * Z95 * (abs(b) - ROPE) / (Z95 + Z90)

spec <- load_spec(file.path(OUT, "tier1_reported_difficulty.json"))
SD_CHILD <- spec$random$subject$intercept_sd
ATTENUATION <- 1 / sqrt(1 + (16 * sqrt(3) / (15 * pi))^2 * SD_CHILD^2)

per_param <- split(res, res$param)

solved <- do.call(rbind, lapply(per_param, function(d) {
  s <- solve_at(d$texts, d$p_meaningful, d$n_returned, TARGET)

  # The expectation of the fitted estimate does not depend on the number of
  # texts, so the grid points are pooled for the check, each weighted by the
  # inverse of its Monte Carlo variance.
  b_att <- d$true[1] * ATTENUATION
  mc_var <- d$sd_est^2 / d$n_returned
  b_sim <- stats::weighted.mean(d$mean_est, 1 / mc_var)
  b_sim_se <- sqrt(1 / sum(1 / mc_var))
  w_att <- width_for(b_att)
  w_raw <- width_for(d$true[1])

  # The scaling check and the projection, from a log-log fit of width on texts.
  fit <- stats::lm(log(mean_ci_width) ~ log(texts), data = d)
  slope <- unname(stats::coef(fit)[2])
  project <- function(w) exp((log(w) - stats::coef(fit)[1]) / slope)
  k_proj <- project(w_att)
  share_qualifying <- stats::median(d$median_qualifying_texts / d$texts)

  data.frame(
    param = d$param[1], model = "reported_difficulty", axis = "texts",
    target = TARGET,
    value = s$value,
    lo    = s$lo,
    hi    = s$hi,
    note  = s$note,
    true = d$true[1],
    attenuated_estimate = round(b_att, 4),
    attenuation = round(ATTENUATION, 4),
    simulated_mean_estimate = round(b_sim, 4),
    simulated_mean_estimate_se = round(b_sim_se, 4),
    width_needed = round(w_att, 4),
    width_scaling_exponent = round(slope, 3),
    projected_texts = round(unname(k_proj), -2),
    projected_qualifying_texts = round(unname(k_proj) * share_qualifying, -2),
    projected_texts_unattenuated = round(unname(project(w_raw)), -2),
    stringsAsFactors = FALSE
  )
}))
rownames(solved) <- NULL
utils::write.csv(solved, file.path(OUT, "minimum_texts_ordinal.csv"), row.names = FALSE)

writeLines("== ordinal outcome, pooled grid points ==")
print(res[, c("param", "texts", "median_qualifying_texts", "mean_est", "mean_ci_width",
              "p_meaningful", "p_meaningful_lo", "p_meaningful_hi",
              "n_returned", "n_boundary", "n_bad_se", "n_skipped")], row.names = FALSE)
writeLines("")
writeLines("== solved or projected requirement ==")
print(solved, row.names = FALSE)

# session_info_ordinal.txt is written by run_ordinal_analysis.R when it computes
# a grid point, so that summarising cached points cannot overwrite the record of
# the session that produced them.
