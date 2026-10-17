# InTRACt Stage 1: re-solve the archived precision curves at 0.95 assurance.
#
# Run from the preregistration directory, after run_design_analysis.R:
#   Rscript design_analysis/solve_at_095.R
#
# Nature Human Behaviour's Registered Report guidelines name 0.95 as the a priori
# power floor for frequentist plans. The protocol registers 0.90 for its
# estimation-with-ROPE design and reports the 0.95 figures beside it so that a
# reader can see what the stricter target would require. Nothing is re-simulated:
# the cached sweeps are read and the same solver is applied with one input changed.

library(pilotr)
source("design_analysis/helpers.R")
OUT   <- "design_analysis"
CACHE <- file.path(OUT, "sweeps")

# Reads one cached sweep written by run_design_analysis.R.
read_sweep <- function(key) {
  utils::read.csv(file.path(CACHE, paste0(key, ".csv")), stringsAsFactors = FALSE)
}

# Solves one parameter's curve for the swept value that reaches the target.
solve_one <- function(d, xname, target) {
  s <- solve_at(d[[xname]], d$p_meaningful, d$n_returned, target)
  data.frame(param = d$param[1], model = d$model[1], axis = xname, target = target,
             value = s$value, lo = s$lo, hi = s$hi, note = s$note, stringsAsFactors = FALSE)
}

dev  <- read_sweep("dev_texts")
narr <- read_sweep("narr_texts")
t2   <- read_sweep("t2_children")

solved <- do.call(rbind, c(
  lapply(split(dev,  dev$param),  solve_one, xname = "texts",    target = 0.95),
  lapply(split(narr, narr$param), solve_one, xname = "texts",    target = 0.95),
  lapply(split(t2,   t2$param),   solve_one, xname = "children", target = 0.95)
))
rownames(solved) <- NULL
utils::write.csv(solved, file.path(OUT, "minimum_texts_095.csv"), row.names = FALSE)
writeLines("== swept value needed for a determinate verdict 95 times in 100 ==")
print(solved, row.names = FALSE)
