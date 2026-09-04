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
OUT   <- "design_analysis"
CACHE <- file.path(OUT, "sweeps")

read_sweep <- function(key) utils::read.csv(file.path(CACHE, paste0(key, ".csv")),
                                            stringsAsFactors = FALSE)

solve_one <- function(d, xname, target) {
  d <- d[order(d[[xname]]), ]
  frame <- data.frame(x = d[[xname]], p_meaningful = d$p_meaningful,
                      n_returned = d$n_returned)
  out <- tryCatch(solve_curve(frame, target = target), error = function(e) NULL)
  base <- data.frame(param = d$param[1], model = d$model[1], axis = xname,
                     target = target, stringsAsFactors = FALSE)
  if (is.null(out))
    return(cbind(base, value = NA_real_, lo = NA_real_, hi = NA_real_,
                 note = paste0("not reached within ", min(d[[xname]]), " to ",
                               max(d[[xname]]))))
  cbind(base, value = out$value, lo = out$lo, hi = out$hi, note = "")
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
