# Pool the cached ordinal grid points, try to solve for the 0.90 target, and,
# where the target lies beyond the range simulated, project the requirement from
# the observed scaling of the interval width.
#
#   Rscript design_analysis/summarise_ordinal.R
#
# solve_curve refuses to extrapolate, which is right: a preregistration should
# not quote a crossing the simulation never reached. What can be reported
# instead is the scaling law the simulation did establish. If the interval
# width falls as the inverse square root of the number of texts, which the
# grid points test directly, then the number of texts at which the width
# reaches the value a determinate verdict needs follows from any one point.
# That projection is labelled as a projection wherever it is quoted.

suppressPackageStartupMessages(library(pilotr))

OUT   <- "design_analysis"
CACHE <- file.path(OUT, "sweeps")
ROPE  <- log(1.05)
TRUE_B <- 0.10

files <- list.files(CACHE, pattern = "^ordinal_[0-9]+\\.csv$", full.names = TRUE)
stopifnot(length(files) >= 3)
res <- do.call(rbind, lapply(files, utils::read.csv))
res <- res[order(res$param, res$texts), ]
utils::write.csv(res, file.path(CACHE, "ordinal_texts.csv"), row.names = FALSE)

# A determinate verdict nine times in ten requires the 95 per cent interval to
# clear the region boundary with room for sampling variation in the estimate:
# ROPE + 1.96 se + qnorm(.90) se < true effect.
se_needed    <- (TRUE_B - ROPE) / (1.959964 + stats::qnorm(0.90))
width_needed <- 2 * 1.959964 * se_needed

per_param <- split(res, res$param)

solved <- do.call(rbind, lapply(per_param, function(d) {
  frame <- data.frame(x = d$texts, p_meaningful = d$p_meaningful,
                      n_returned = d$n_returned)
  out <- tryCatch(solve_curve(frame, target = 0.90), error = function(e) NULL)

  # The scaling check and the projection, from a log-log fit of width on texts.
  fit <- stats::lm(log(mean_ci_width) ~ log(texts), data = d)
  slope <- unname(stats::coef(fit)[2])
  k_proj <- exp((log(width_needed) - stats::coef(fit)[1]) / slope)

  data.frame(
    param = d$param[1], model = "reported_difficulty", axis = "texts",
    target = 0.90,
    value = if (is.null(out)) NA_real_ else out$value,
    lo    = if (is.null(out)) NA_real_ else out$lo,
    hi    = if (is.null(out)) NA_real_ else out$hi,
    note  = if (is.null(out))
      sprintf("not reached within %d to %d", min(d$texts), max(d$texts)) else "",
    width_scaling_exponent = round(slope, 3),
    projected_texts = round(k_proj, -2),
    projected_qualifying_texts = round(k_proj * stats::median(
      d$median_qualifying_texts / d$texts), -2),
    stringsAsFactors = FALSE)
}))
rownames(solved) <- NULL
utils::write.csv(solved, file.path(OUT, "minimum_texts_ordinal.csv"), row.names = FALSE)

writeLines("== ordinal outcome, pooled grid points ==")
print(res[, c("param", "texts", "median_qualifying_texts", "mean_ci_width",
              "p_meaningful", "p_meaningful_lo", "p_meaningful_hi",
              "n_returned", "n_bad_se")], row.names = FALSE)
writeLines("")
writeLines(sprintf("width needed for a determinate verdict nine times in ten: %.3f", width_needed))
writeLines("")
writeLines("== solved or projected requirement ==")
print(solved, row.names = FALSE)
