library(theoryforge)
th <- tf_read("theory/intract.theory.yaml")
chk <- tf_check(th)
imp <- tf_implications(th)
red <- tf_redundancy_check(th)
writeLines(sprintf("score=%s gate=%s blockers=%s acyclic=%s edges=%s implications=%s maxsim=%.3f",
                   chk$aggregate_score, chk$gate, chk$n_blockers_failed,
                   imp$acyclic, imp$n_edges, length(imp$implications), max(red$similarity)))
writeLines("")
writeLines("-- checklist --")
for (it in chk$items) writeLines(sprintf("  %-20s %-6s %.3f", it$id, it$status, it$score))
writeLines("")
writeLines("-- testable implications --")
for (i in imp$implications) writeLines(paste0("  ", i$statement,
  if (length(i$given)) paste0("  |  given ", paste(unlist(i$given), collapse=", ")) else ""))
