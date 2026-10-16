# InTRACt Stage 1: price the Bayes-factor criterion from the archived precision curves.
#
# Run from the preregistration directory, after run_design_analysis.R:
#   Rscript design_analysis/solve_at_bf10.R
#
# A determinate non-negligible verdict in the protocol needs two things: fewer than
# 5 per cent of the posterior inside the region of practical equivalence, and an
# interval Bayes factor of at least 10 for the region outside against the region
# inside, computed under the weakly informative prior of the reference refit (Student
# t with 3 degrees of freedom centred at zero, scale 0.5 for a main effect and 0.25
# for an interaction). Under that prior the Bayes factor is the ratio of posterior to
# prior odds of the two regions, so it reaches 10 when the posterior mass inside the
# region falls to m* = 1 / (1 + 10 * prior odds), which for a normal posterior means
# the estimate sits z* = qnorm(1 - m*) standard errors beyond the region's edge. The
# simulation's own criterion, an interval wholly outside the region, needs 1.96. The
# Bayes-factor criterion is therefore the binding one for a non-negligible verdict,
# and this script prices it without re-simulating: each grid point's mean interval
# width gives its standard error, the probability that a true effect of 0.10 clears
# z* is Phi(0.05 / SE - z*), and the solver of solve_at_095.R inverts the curve at
# 0.90 and 0.95. The same approximation at z = 1.96 is written beside the simulated
# probability as a calibration check, so that a reader can see how well the normal
# approximation reproduces the simulation before trusting it one step further. The
# registered re-run of the design analysis at the observed inputs computes this
# criterion by simulation from the brms refit and supersedes these figures.

library(pilotr)
OUT   <- "design_analysis"
CACHE <- file.path(OUT, "sweeps")

ROPE   <- 0.05   # half-width of the region, and the distance of the 0.10 effect from its edge
EFFECT <- 0.10
Z_SIM  <- stats::qnorm(0.975)   # the simulation's interval-wholly-outside criterion

# Prior scale by parameter: main effects 0.5, interactions 0.25, as registered under Priors.
prior_scale <- function(param) ifelse(grepl("_age$|_narr$", param), 0.25, 0.5)

# Posterior mass inside the region at which the interval Bayes factor reaches 10 under a
# t(3, 0, scale) encompassing prior, and the normal-posterior z it corresponds to.
bf10_threshold <- function(scale, bf = 10) {
  p0 <- stats::pt(ROPE / scale, 3) - stats::pt(-ROPE / scale, 3)
  prior_odds <- (1 - p0) / p0
  m_star <- 1 / (1 + bf * prior_odds)
  list(prior_rope = p0, prior_odds = prior_odds, m_star = m_star,
       z_star = stats::qnorm(1 - m_star))
}

read_sweep <- function(key) utils::read.csv(file.path(CACHE, paste0(key, ".csv")),
                                            stringsAsFactors = FALSE)

# Replace each grid point's simulated decision probability by the analytic probability
# of clearing z*, keeping the replicate count as the solver's weight.
approximate <- function(d) {
  se <- d$mean_ci_width / (2 * Z_SIM)
  thr <- bf10_threshold(prior_scale(d$param[1]))
  d$p_bf10     <- stats::pnorm((EFFECT - ROPE) / se - thr$z_star)
  d$p_approx   <- stats::pnorm((EFFECT - ROPE) / se - Z_SIM)
  d$z_star     <- thr$z_star
  d$m_star     <- thr$m_star
  d$prior_rope <- thr$prior_rope
  d
}

# Solve the approximated curve for the Bayes-factor criterion and, beside it, for the
# simulation's own criterion, so that the two can be compared on the same footing.
solve_one <- function(d, xname, target) {
  d <- d[order(d[[xname]]), ]
  solve_p <- function(p) {
    frame <- data.frame(x = d[[xname]], p_meaningful = p, n_returned = d$n_returned)
    out <- tryCatch(solve_curve(frame, target = target), error = function(e) NULL)
    if (is.null(out)) NA_real_ else out$value
  }
  v_bf  <- solve_p(d$p_bf10)
  v_196 <- solve_p(d$p_approx)
  data.frame(param = d$param[1], model = d$model[1], axis = xname, target = target,
             prior_scale = prior_scale(d$param[1]), prior_rope = d$prior_rope[1],
             m_star = d$m_star[1], z_star = d$z_star[1],
             value = v_bf, value_at_196 = v_196,
             note = if (is.na(v_bf)) paste0("not reached within ", min(d[[xname]]),
                                            " to ", max(d[[xname]]))
                    else "normal approximation from the archived mean interval widths",
             stringsAsFactors = FALSE)
}

dev  <- read_sweep("dev_texts")
narr <- read_sweep("narr_texts")
t2   <- read_sweep("t2_children")
dev  <- do.call(rbind, lapply(split(dev,  dev$param),  approximate))
narr <- do.call(rbind, lapply(split(narr, narr$param), approximate))
t2   <- do.call(rbind, lapply(split(t2,   t2$param),   approximate))

solved <- do.call(rbind, c(
  lapply(split(dev,  dev$param),  solve_one, xname = "texts",    target = 0.90),
  lapply(split(dev,  dev$param),  solve_one, xname = "texts",    target = 0.95),
  lapply(split(narr, narr$param), solve_one, xname = "texts",    target = 0.90),
  lapply(split(narr, narr$param), solve_one, xname = "texts",    target = 0.95),
  lapply(split(t2,   t2$param),   solve_one, xname = "children", target = 0.90),
  lapply(split(t2,   t2$param),   solve_one, xname = "children", target = 0.95)
))
rownames(solved) <- NULL
utils::write.csv(solved, file.path(OUT, "minimum_texts_bf10.csv"), row.names = FALSE)

calib <- rbind(
  data.frame(sweep = "dev_texts",   x = dev$texts,     param = dev$param,
             p_simulated = dev$p_meaningful,  p_approx_196 = dev$p_approx,  p_bf10 = dev$p_bf10),
  data.frame(sweep = "narr_texts",  x = narr$texts,    param = narr$param,
             p_simulated = narr$p_meaningful, p_approx_196 = narr$p_approx, p_bf10 = narr$p_bf10),
  data.frame(sweep = "t2_children", x = t2$children,   param = t2$param,
             p_simulated = t2$p_meaningful,   p_approx_196 = t2$p_approx,   p_bf10 = t2$p_bf10)
)
utils::write.csv(calib, file.path(CACHE, "bf10_calibration.csv"), row.names = FALSE)

writeLines("== Bayes factor of 10 under the weakly informative prior: threshold per prior scale ==")
for (s in c(0.5, 0.25)) {
  thr <- bf10_threshold(s)
  writeLines(sprintf("  scale %.2f: prior mass in region %.4f, prior odds %.2f, posterior mass for BF10 = 10: %.4f, z* = %.3f",
                     s, thr$prior_rope, thr$prior_odds, thr$m_star, thr$z_star))
}
writeLines("")
writeLines("== calibration of the normal approximation at the simulation's own criterion (z = 1.96) ==")
print(calib[, c("sweep", "param", "x", "p_simulated", "p_approx_196", "p_bf10")], row.names = FALSE, digits = 3)
writeLines("")
writeLines("== swept value needed for a Bayes factor of at least 10 (value), and for the simulation's")
writeLines("   own criterion under the same approximation (value_at_196), nine times in ten and 95 times in 100 ==")
print(solved[, c("param", "model", "axis", "target", "value", "value_at_196", "note")],
      row.names = FALSE, digits = 4)
