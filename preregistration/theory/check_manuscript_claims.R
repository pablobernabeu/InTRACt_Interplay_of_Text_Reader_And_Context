# Verify that what the manuscript says about the theory object is true of the
# theory object. Run from the preregistration directory:
#   Rscript theory/check_manuscript_claims.R
#
# A Registered Report that describes its own deposited artefacts is making
# checkable claims, so they are checked rather than trusted. Every number the
# manuscript quotes about the theory is printed here beside the number the
# object actually yields.

library(theoryforge)

th  <- tf_read("theory/intract.theory.yaml")
chk <- tf_check(th)
imp <- tf_implications(th)
red <- tf_redundancy_check(th)

counts <- list(
  constructs            = length(th$constructs),
  propositions          = length(th$propositions),
  auxiliary_assumptions = length(th$auxiliary_assumptions),
  alternatives          = length(th$alternatives),
  predictions           = length(th$predictions),
  evidence_entries      = length(th$evidence)
)

diagnostic <- sum(vapply(th$predictions,
                         function(p) length(p$diagnostic_vs) > 0, logical(1)))
interval <- sum(vapply(th$predictions,
                       function(p) identical(p$type, "interval"), logical(1)))

writeLines("== counts the manuscript quotes ==")
for (nm in names(counts)) writeLines(sprintf("  %-22s %d", nm, counts[[nm]]))
writeLines(sprintf("  %-22s %d", "diagnostic predictions", diagnostic))
writeLines(sprintf("  %-22s %d", "interval predictions", interval))
writeLines("")
writeLines("== scores and structure ==")
writeLines(sprintf("  aggregate score        %.1f", chk$aggregate_score))
writeLines(sprintf("  gate                   %s", chk$gate))
writeLines(sprintf("  blocking failures      %d", chk$n_blockers_failed))
writeLines(sprintf("  checklist items passed %d of %d",
                   sum(vapply(chk$items, function(i) i$status == "pass", logical(1))),
                   length(chk$items)))
writeLines(sprintf("  acyclic                %s", imp$acyclic))
writeLines(sprintf("  edges                  %d", imp$n_edges))
writeLines(sprintf("  testable implications  %d", length(imp$implications)))
writeLines(sprintf("  largest construct similarity  %.2f", max(red$similarity)))

# Every prediction must name a proposition, and every diagnostic_vs must name a
# registered alternative. tf_check tests reachability; this tests the labels.
alt_ids  <- vapply(th$alternatives, function(a) a$id, character(1))
prop_ids <- vapply(th$propositions, function(p) p$id, character(1))
bad <- character(0)
for (p in th$predictions) {
  miss_d <- setdiff(unlist(p$derives_from), prop_ids)
  miss_a <- setdiff(unlist(p$diagnostic_vs), alt_ids)
  if (length(miss_d)) bad <- c(bad, sprintf("%s derives from unknown %s", p$id, paste(miss_d, collapse = ", ")))
  if (length(miss_a)) bad <- c(bad, sprintf("%s is diagnostic against unknown %s", p$id, paste(miss_a, collapse = ", ")))
}
writeLines("")
if (length(bad)) {
  writeLines("== DANGLING REFERENCES ==")
  writeLines(paste0("  ", bad))
  quit(status = 1)
}
writeLines("== no dangling references between predictions, propositions and alternatives ==")
