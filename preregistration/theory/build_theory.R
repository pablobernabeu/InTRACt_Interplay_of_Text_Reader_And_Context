# Build, check and score the InTRACt theory object.
#
# Run from the preregistration directory:  Rscript theory/build_theory.R
# Writes theory/tf_check.txt (which includes the testable implications),
# theory/tf_severity.csv, theory/tf_redundancy.csv and
# theory/intract_nomological_net.svg, theoryforge's default rendering of the
# net. The manuscript does not use that SVG: its Figure 2 is drawn by the
# script theory/make_nomological_net.R.

library(theoryforge)

theory <- tf_read("theory/intract.theory.yaml")

out <- file("theory/tf_check.txt", open = "wt", encoding = "UTF-8")
sink(out)
sink(out, type = "message")

cat("theoryforge ", as.character(packageVersion("theoryforge")),
    "  |  R ", R.version$major, ".", R.version$minor, "\n\n", sep = "")

cat("== Schema validation ==\n")
print(tf_validate(theory, full = TRUE))

cat("\n== Rigour checklist ==\n")
print(tf_check(theory))

cat("\n== Prediction severity ==\n")
sev <- tf_severity(theory)
print(sev)

cat("\n== Construct redundancy screen ==\n")
red <- tf_redundancy_check(theory)
print(red)

cat("\n== Testable implications of the causal graph ==\n")
print(tryCatch(tf_implications(theory),
               error = function(e) paste("not derivable:", conditionMessage(e))))

sink(type = "message")
sink()
close(out)

if (is.data.frame(sev)) utils::write.csv(sev, "theory/tf_severity.csv", row.names = FALSE)
if (is.data.frame(red)) utils::write.csv(red, "theory/tf_redundancy.csv", row.names = FALSE)

svg <- tryCatch(tf_render_diagram(theory, type = "nomological_net", as = "svg"),
                error = function(e) NULL)
if (!is.null(svg)) writeLines(as.character(svg), "theory/intract_nomological_net.svg")

writeLines(readLines("theory/tf_check.txt"))
