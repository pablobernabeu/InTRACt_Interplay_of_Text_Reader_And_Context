# Verify that the numbers the manuscript quotes match the artefacts they came from.
#
#   Rscript check_reported_numbers.R
#
# A protocol that reports its own precision analysis and its own literature sizing
# is making arithmetic claims a reviewer can check, so they are checked here
# rather than trusted to have been copied correctly. Exits non-zero on any
# mismatch, so this can gate a commit.

qmd <- paste(readLines("preregistration.qmd", warn = FALSE), collapse = "\n")
fail <- character(0)

expect <- function(label, present, detail = "") {
  writeLines(sprintf("  %-52s %s%s", label, if (present) "ok" else "MISMATCH",
                     if (nzchar(detail)) paste0("   ", detail) else ""))
  if (!present) fail <<- c(fail, label)
}

has <- function(x) grepl(x, qmd, fixed = TRUE)
fmt <- function(x) formatC(round(x), format = "d", big.mark = ",")

writeLines("== title and abstract limits ==")
title <- sub('^title: "(.*)"$', "\\1", grep('^title: "', strsplit(qmd, "\n")[[1]], value = TRUE)[1])
expect("title at most 100 characters", nchar(title) <= 100, sprintf("%d characters", nchar(title)))
abs_txt <- sub(".*# Abstract \\{\\.unnumbered\\}\\s*(.*?)\\s*\\{\\{< pagebreak.*", "\\1", qmd)
n_words <- length(strsplit(gsub("[*_]", "", abs_txt), "\\s+")[[1]])
expect("abstract at most 150 words", n_words <= 150, sprintf("%d words", n_words))

writeLines("")
writeLines("== precision analysis ==")
mt <- utils::read.csv("design_analysis/minimum_texts.csv", stringsAsFactors = FALSE)
get <- function(model, param) mt[mt$model == model & mt$param == param, ]
for (spec in list(
  list("developmental", "LexPC",      "lexical main effect"),
  list("developmental", "SynPC_age",  "grammatical x age band"),
  list("developmental", "CohPC_age",  "continuity x age band"),
  list("narration",     "LexPC_narr", "narration selectivity"),
  list("within_child",  "accum",      "within-child accumulated reading"))) {
  r <- get(spec[[1]], spec[[2]])
  if (!nrow(r)) { expect(spec[[3]], FALSE, "absent from minimum_texts.csv"); next }
  expect(spec[[3]], has(fmt(r$value)) && has(fmt(r$lo)) && has(fmt(r$hi)),
         sprintf("%s [%s, %s]", fmt(r$value), fmt(r$lo), fmt(r$hi)))
}

writeLines("")
writeLines("== ordinal precision projection ==")
ord_path <- file.path("design_analysis", "minimum_texts_ordinal.csv")
if (file.exists(ord_path)) {
  mo <- utils::read.csv(ord_path, stringsAsFactors = FALSE)
  expect("target not reached within the simulated range",
         all(is.na(mo$value)) == grepl("not reached within the 1,600 texts simulated", qmd, fixed = TRUE),
         if (all(is.na(mo$value))) "refused, as quoted" else "solved, but the text claims refusal")
  pr <- range(mo$projected_texts)
  expect("projected generated-text range",
         has(sprintf("%s to %s generated texts", fmt(pr[1]), fmt(pr[2]))),
         sprintf("%s to %s", fmt(pr[1]), fmt(pr[2])))
  qr <- range(mo$projected_qualifying_texts)
  expect("projected qualifying-text range",
         has(sprintf("%s to %s carrying at least five ratings", fmt(qr[1]), fmt(qr[2]))),
         sprintf("%s to %s", fmt(qr[1]), fmt(qr[2])))
} else {
  writeLines("  minimum_texts_ordinal.csv absent; skipped")
}

writeLines("")
writeLines("== literature sizing ==")
gp <- utils::read.csv("literature/scopus_gap_sizes.csv", stringsAsFactors = FALSE)
for (lab in gp$label) {
  n <- gp$n[gp$label == lab]
  if (n == 0) {
    expect(paste(lab, "reported as empty"), has("three-way intersection was empty"), "0")
  } else {
    expect(lab, has(fmt(n)), fmt(n))
  }
}

writeLines("")
writeLines("== theory object ==")
if (requireNamespace("theoryforge", quietly = TRUE)) {
  th <- theoryforge::tf_read("theory/intract.theory.yaml")
  chk <- theoryforge::tf_check(th)
  expect("aggregate score quoted in the manuscript",
         has(sprintf("%.1f out of 100", chk$aggregate_score)),
         sprintf("%.1f", chk$aggregate_score))
  expect("construct count", has("twelve constructs"), length(th$constructs))
  expect("proposition count", has("eighteen propositions"), length(th$propositions))
  expect("alternatives count", has("six rival accounts"), length(th$alternatives))
} else {
  writeLines("  theoryforge not installed; skipped")
}

writeLines("")
if (length(fail)) {
  writeLines(sprintf("FAILED: %d claim(s) do not match their artefact", length(fail)))
  writeLines(paste0("  - ", fail))
  quit(status = 1)
}
writeLines("All reported numbers match their artefacts.")
