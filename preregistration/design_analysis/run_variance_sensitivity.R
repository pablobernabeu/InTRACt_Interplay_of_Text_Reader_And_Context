# InTRACt Stage 1: sensitivity of the precision requirements to the share of
# variance between texts.
#
# Run from the preregistration directory, after run_design_analysis.R:
#   Rscript design_analysis/run_variance_sensitivity.R
#
# The design specifications generate data in which texts carry 9 per cent of the
# variance, children 20 per cent and the residual 71 per cent. These values are
# assumptions, set before any reading time from the platform could be linked to a
# text: no estimate of them existed for this app. Published decompositions of
# children's reading rates over many passages put the share between passages at
# about 10 to 13 per cent, within a range of about 1 to 20 per cent (Poncy et al.,
# 2005; Barth et al., 2014; Francis et al., 2018; Wang et al., 2024). This script
# re-runs the texts sweeps for Hypotheses 1 to 4 with the text share at 5, 13 and
# 20 per cent, holding the child variance and the total fixed, and solves each
# curve as the main analysis does. It solves both the simulation's own criterion,
# an interval wholly outside the region, and the Bayes-factor criterion, priced as
# solve_at_bf10.R prices it.
#
# Only the text share can move these requirements. In tier 1 each child
# contributes one reading, so the child variance reaches the fitted model as
# residual, and how the remainder splits between child and residual cannot change
# a requirement. The child share matters only for the tier-2 model of Hypothesis
# 6, where a larger child share and a smaller residual, as the published
# decompositions report, would lower the requirement.
#
# Each sweep is cached in design_analysis/sweeps/ under its share, with a key
# file as in run_design_analysis.R, and the 9 per cent rows are read from that script's own
# cached sweeps, so the table puts the registered figures beside the sensitivity
# figures without re-running them.

library(pilotr)
source("design_analysis/helpers.R")
need_package(requireNamespace("lme4", quietly = TRUE), "lme4",
             "pilotr fits every replicate with it")

N_SIMS  <- env_number("INTRACT_N_SIMS", "200")
WORKERS <- env_number("INTRACT_WORKERS", "6")
ROPE    <- 0.05
EFFECT  <- 2 * ROPE
OUT     <- "design_analysis"
CACHE   <- file.path(OUT, "sweeps")
dir.create(CACHE, showWarnings = FALSE, recursive = TRUE)

CHILD_VAR <- 0.45^2                  # as in every reading-time specification
# The registered value, 0.09, is read from cache. INTRACT_SHARES restricts the run
# to a subset, for example "0.05,0.13" to tabulate sweeps already cached.
SHARES    <- env_numbers("INTRACT_SHARES", "0.05,0.13,0.20", min = 0, max = 1 - CHILD_VAR)
TEXTS     <- c(50, 100, 200, 400, 800, 1600)
M_FIXED   <- 12

# Set the text share, keeping the child variance and the total variance of 1.
at_share <- function(spec, share) {
  spec$random$item$intercept_sd <- sqrt(share)
  spec$response$sigma <- sqrt(1 - CHILD_VAR - share)
  spec
}

workers <- make_worker_probe(WORKERS)
computed <- FALSE

# Runs one texts sweep, or reads it from design_analysis/sweeps/ if a sweep with
# the same settings is cached there.
run_sweep <- function(key, spec, focal, formula, model) {
  cached <- file.path(CACHE, paste0(key, ".csv"))
  values <- units_by_texts(TEXTS, M_FIXED)
  settings <- cache_key(sweep = key, spec = spec, path = "units", values = values,
                        focal = as.list(focal), formula = deparse1(formula), rope = ROPE,
                        n_sims = N_SIMS)
  res <- cache_read(cached, settings)
  if (!is.null(res)) return(res)
  msg("sweep: ", key, " (", length(TEXTS), " grid points, ", N_SIMS, " replicates each)")
  res <- sweep_spec(spec, "units", values, precision_design,
                    focal = focal, formula = formula, rope = ROPE, n_sims = N_SIMS,
                    workers = workers())
  res$texts <- label_grid(res, values, TEXTS, focal)
  res$model <- model
  res$n_sims <- N_SIMS
  res <- cache_write(res, cached, settings)
  computed <<- TRUE
  res
}

F_DEV  <- .y ~ LexPC + SynPC + CohPC + age + SynPC_age + CohPC_age + (1 | item)
F_NARR <- .y ~ LexPC + CohPC + narr + LexPC_narr + CohPC_narr + (1 | item)

dev_spec  <- at_effect(load_spec(file.path(OUT, "tier1_developmental.json")), EFFECT)
narr_spec <- at_effect(load_spec(file.path(OUT, "tier1_narration.json")), EFFECT)
focal_dev  <- focal_from(dev_spec, c("LexPC", "SynPC", "CohPC", "SynPC_age", "CohPC_age"))
focal_narr <- focal_from(narr_spec, c("LexPC", "CohPC", "LexPC_narr"))

sweeps <- list()
for (s in SHARES) {
  tag <- sprintf("sens_text%02d", round(100 * s))
  sweeps[[paste0(tag, "_dev")]] <-
    cbind(run_sweep(paste0(tag, "_dev_texts"), at_share(dev_spec, s), focal_dev, F_DEV,
                    "developmental"), text_share = s)
  sweeps[[paste0(tag, "_narr")]] <-
    cbind(run_sweep(paste0(tag, "_narr_texts"), at_share(narr_spec, s), focal_narr, F_NARR,
                    "narration"), text_share = s)
}
# The registered figures, at the specifications' own 9 per cent, from the main
# analysis's cached sweeps.
reg <- function(key, model) {
  d <- utils::read.csv(file.path(CACHE, paste0(key, ".csv")), stringsAsFactors = FALSE)
  d$model <- model
  d$text_share <- 0.30^2
  d
}
sweeps$reg_dev  <- reg("dev_texts", "developmental")
sweeps$reg_narr <- reg("narr_texts", "narration")

# ---- Solve each curve under both criteria -------------------------------------

Z_SIM <- stats::qnorm(0.975)
prior_scale <- function(param) ifelse(grepl("_age$|_narr$", param), 0.25, 0.5)
z_star <- function(scale, bf = 10) {
  p0 <- stats::pt(ROPE / scale, 3) - stats::pt(-ROPE / scale, 3)
  stats::qnorm(1 - 1 / (1 + bf * (1 - p0) / p0))
}
REACH <- paste0("not reached within ", format(min(TEXTS), big.mark = ","), " to ",
                format(max(TEXTS), big.mark = ","), " texts")
note_of <- function(s) switch(s$status, solved = "", "not reached" = REACH, s$note)
rows <- list()
for (d in sweeps) {
  for (prm in unique(d$param)) {
    e <- d[d$param == prm, ]
    e <- e[order(e$texts), ]
    se <- e$mean_ci_width / (2 * Z_SIM)
    p_bf <- stats::pnorm((EFFECT - ROPE) / se - z_star(prior_scale(prm)))
    for (tg in c(0.90, 0.95)) {
      sim <- solve_at(e$texts, e$p_meaningful, e$n_returned, tg)
      bf  <- solve_at(e$texts, p_bf, e$n_returned, tg)
      rows[[length(rows) + 1]] <- data.frame(
        text_share = e$text_share[1], model = e$model[1], param = prm, target = tg,
        criterion = c("interval", "bf10"),
        value = c(sim$value, bf$value), lo = c(sim$lo, NA),
        hi = c(sim$hi, NA), note = c(note_of(sim), note_of(bf)), stringsAsFactors = FALSE
      )
    }
  }
}
tab <- do.call(rbind, rows)
tab <- tab[order(tab$model, tab$param, tab$target, tab$criterion, tab$text_share), ]
utils::write.csv(tab, file.path(OUT, "variance_sensitivity.csv"), row.names = FALSE)
msg("wrote ", file.path(OUT, "variance_sensitivity.csv"))

writeLines("")
writeLines("== distinct texts needed at 0.90, by share of variance between texts ==")
wide <- stats::reshape(
  tab[tab$target == 0.90, c("model", "param", "criterion", "text_share", "value")],
  idvar = c("model", "param", "criterion"), timevar = "text_share",
  direction = "wide"
)
print(wide, row.names = FALSE, digits = 4)

if (computed) {
  write_session(file.path(OUT, "session_info_variance_sensitivity.txt"),
                c(paste("replicates per grid point:", N_SIMS),
                  paste("text shares:", paste(c(0.09, SHARES), collapse = ", "))))
}
msg("done")
