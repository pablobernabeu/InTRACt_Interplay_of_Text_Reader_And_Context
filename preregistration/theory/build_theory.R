# Build, check and score the InTRACt theory object.
#
# Run from the preregistration directory:  Rscript theory/build_theory.R
# Writes theory/tf_check.txt (which includes the testable implications),
# theory/tf_severity.csv, theory/tf_redundancy.csv and
# theory/intract_nomological_net.svg, theoryforge's default rendering of the
# net. The manuscript does not use that SVG: its Figure 2 is drawn by the
# script theory/make_nomological_net.R.
#
# The script fails, with a non-zero exit, if the object fails schema validation
# or the rigour checklist's gate, if its causal graph is cyclic or yields no
# implications, or if any step fails. The report is still written in the first
# three cases, since it records why.

library(theoryforge)

theory <- tf_read("theory/intract.theory.yaml")

# The report is written through a sink into a temporary file. An error in a step
# is caught, the sinks are removed and the error is raised again on the console,
# so it cannot be hidden in a truncated report, and the previous report is left
# in place. Without the catch, R would print the error into the sink.
report <- tempfile(fileext = ".txt")
out <- file(report, open = "wt", encoding = "UTF-8")
sink(out)
sink(out, type = "message")
res <- tryCatch({
  cat("theoryforge ", as.character(packageVersion("theoryforge")),
      "  |  R ", R.version$major, ".", R.version$minor, "\n\n", sep = "")

  cat("== Schema validation ==\n")
  valid <- tf_validate(theory, full = TRUE)
  print(valid)

  cat("\n== Rigour checklist ==\n")
  rigour <- tf_check(theory)
  print(rigour)

  cat("\n== Prediction severity ==\n")
  sev <- tf_severity(theory)
  print(sev)

  cat("\n== Construct redundancy screen ==\n")
  red <- tf_redundancy_check(theory)
  print(red)

  cat("\n== Testable implications of the causal graph ==\n")
  imp <- tryCatch(tf_implications(theory),
                  error = function(e) paste("not derivable:", conditionMessage(e)))
  print(imp)

  list(valid = valid, rigour = rigour, sev = sev, red = red, imp = imp)
}, error = function(e) e, finally = {
  sink(type = "message")
  sink()
  close(out)
})
if (inherits(res, "error"))
  stop("the report could not be completed, so tf_check.txt was left as it was: ",
       conditionMessage(res), call. = FALSE)
invisible(file.copy(report, "theory/tf_check.txt", overwrite = TRUE))

fail <- function(...) stop(..., " (see theory/tf_check.txt)", call. = FALSE)
if (!isTRUE(res$valid)) fail("the theory object fails schema validation")
if (!identical(res$rigour$gate, "pass"))
  fail("the rigour checklist's gate is '", res$rigour$gate, "', not 'pass'")
if (!is.list(res$imp) || !isTRUE(res$imp$acyclic))
  fail("the causal graph is cyclic or its implications could not be derived")
if (!is.data.frame(res$sev) || !is.data.frame(res$red))
  fail("the severity or redundancy screen did not return a table")

utils::write.csv(res$sev, "theory/tf_severity.csv", row.names = FALSE)
utils::write.csv(res$red, "theory/tf_redundancy.csv", row.names = FALSE)

svg <- tf_render_diagram(theory, type = "nomological_net", as = "svg")
writeLines(as.character(svg), "theory/intract_nomological_net.svg")

writeLines(readLines("theory/tf_check.txt"))
