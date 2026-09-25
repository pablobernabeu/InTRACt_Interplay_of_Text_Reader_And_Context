# Check that the numbers the protocol quotes match the artefacts they came from.
#
# Run from the preregistration directory:
#   Rscript check_reported_numbers.R
#
# A protocol that reports its own precision analysis and its own literature
# counts makes arithmetic claims a reviewer can check, so they are checked here
# and not trusted to have been copied correctly.
#
# Checked, in preregistration.qmd only: the title and abstract limits recorded in
# journal.json; the 0.90 and 0.95 precision requirements quoted from
# design_analysis/minimum_texts.csv and minimum_texts_095.csv; the Bayes-factor
# requirements quoted to the nearest ten from minimum_texts_bf10.csv; the ordinal
# refusal and projection from minimum_texts_ordinal.csv; the Scopus counts from
# literature/scopus_gap_sizes.csv; and the theory object's rigour score and its
# construct, proposition, auxiliary-assumption and rival counts. The supplement
# and every other quoted number are not checked.
#
# Each number is matched with digit boundaries, so 17 cannot pass inside 117 or
# 1,170. Precision figures, intersections and theory counts are also matched
# inside the phrase that quotes them. The three Scopus concept sizes are matched
# by their digits alone.
#
# Exit status 1 on any mismatch. A block that cannot run (theoryforge not
# installed, an artefact missing) also exits 1, unless INTRACT_ALLOW_SKIP=1 is
# set, in which case the run is reported as INCOMPLETE and exits 0.

qmd_lines <- readLines("preregistration.qmd", warn = FALSE, encoding = "UTF-8")
qmd <- paste(qmd_lines, collapse = "\n")
journal <- jsonlite::read_json("journal.json")
allow_skip <- identical(Sys.getenv("INTRACT_ALLOW_SKIP"), "1")
fail <- character(0)
skipped <- character(0)

# Print one check and record a failure.
expect <- function(label, present, detail = "") {
  writeLines(sprintf("  %-52s %s%s", label, if (present) "ok" else "MISMATCH",
                     if (nzchar(detail)) paste0("   ", detail) else ""))
  if (!present) fail <<- c(fail, label)
  invisible(present)
}

# Print and record a block that could not run.
skip <- function(label, reason) {
  writeLines(sprintf("  %-52s SKIPPED   %s", label, reason))
  skipped <<- c(skipped, label)
}

fmt <- function(x) formatC(round(x), format = "d", big.mark = ",")

# A formatted number as a regular expression that cannot match inside a longer
# number: no digit, comma or point before it, and no digit, ",d" or ".d" after it.
num <- function(x) paste0("(?<![0-9.,])", gsub("[.]", "\\\\.", x),
                          "(?![0-9]|[.,][0-9])")
has <- function(rx) grepl(rx, qmd, perl = TRUE)
has_text <- function(x) grepl(x, qmd, fixed = TRUE)

max_in_note <- function(note) max(as.numeric(regmatches(note, gregexpr("[0-9]+", note))[[1]]))

writeLines("== title and abstract limits ==")
delim <- which(qmd_lines == "---")
if (length(delim) < 2 || delim[1] != 1)
  stop("preregistration.qmd does not open with a YAML front matter block", call. = FALSE)
front <- yaml::yaml.load(paste(qmd_lines[2:(delim[2] - 1)], collapse = "\n"))
title <- front$title
if (!is.character(title) || length(title) != 1)
  stop("no single title in the YAML front matter", call. = FALSE)
title_max <- journal$title_char_limit
expect(sprintf("title at most %d characters", title_max), nchar(title) <= title_max,
       sprintf("%d characters", nchar(title)))
abs_rx <- ".*# Abstract \\{\\.unnumbered\\}\\s*(.*?)\\s*\\{\\{< pagebreak.*"
if (!grepl(abs_rx, qmd))
  stop("no abstract between '# Abstract {.unnumbered}' and the next pagebreak", call. = FALSE)
abs_txt <- sub(abs_rx, "\\1", qmd)
n_words <- length(strsplit(gsub("[*_]", "", abs_txt), "\\s+")[[1]])
abs_max <- journal$abstract_word_limit
expect(sprintf("abstract at most %d words", abs_max), n_words <= abs_max,
       sprintf("%d words", n_words))

writeLines("")
writeLines("== precision analysis ==")

read_solved <- function(path) {
  if (!file.exists(path)) return(NULL)
  utils::read.csv(path, stringsAsFactors = FALSE)
}
row_of <- function(tab, model, param) tab[tab$model == model & tab$param == param, , drop = FALSE]

# The protocol quotes a requirement as "<value> ... (<lo> to <hi>", sometimes with
# "95 per cent interval" inside the bracket.
check_interval <- function(tab, model, param, label) {
  r <- row_of(tab, model, param)
  if (nrow(r) != 1) return(expect(label, FALSE, "absent from the CSV"))
  if (is.na(r$value)) return(expect(label, FALSE, paste("not solved in the CSV:", r$note)))
  rx <- paste0(num(fmt(r$value)), "[^()]{0,80}\\((?:95 per cent interval )?",
               num(fmt(r$lo)), " to ", num(fmt(r$hi)))
  expect(label, has(rx), sprintf("%s (%s to %s)", fmt(r$value), fmt(r$lo), fmt(r$hi)))
}

m90 <- read_solved(file.path("design_analysis", "minimum_texts.csv"))
if (is.null(m90)) {
  skip("0.90 requirements", "minimum_texts.csv is absent")
} else {
  check_interval(m90, "developmental", "LexPC",      "lexical main effect")
  check_interval(m90, "developmental", "SynPC",      "grammatical main effect")
  check_interval(m90, "developmental", "CohPC",      "continuity main effect")
  check_interval(m90, "developmental", "SynPC_age",  "grammatical x age band")
  check_interval(m90, "developmental", "CohPC_age",  "continuity x age band")
  check_interval(m90, "narration",     "LexPC_narr", "narration selectivity")
  check_interval(m90, "within_child",  "accum",      "within-child accumulated reading")
}

m95 <- read_solved(file.path("design_analysis", "minimum_texts_095.csv"))
if (is.null(m95)) {
  skip("0.95 requirements", "minimum_texts_095.csv is absent")
} else {
  main <- vapply(c("LexPC", "SynPC", "CohPC"), function(p) {
    r <- row_of(m95, "developmental", p)
    if (nrow(r) == 1) r$value else NA_real_
  }, numeric(1))
  if (anyNA(main)) {
    expect("0.95 main effects", FALSE, "absent or not solved in the CSV")
  } else {
    expect("0.95 main effects", has(paste0(num(fmt(main[1])), ", ", num(fmt(main[2])),
                                           " and ", num(fmt(main[3])))),
           paste(fmt(main), collapse = ", "))
  }
  check_interval(m95, "developmental", "SynPC_age", "0.95 grammatical x age band")
  ca <- row_of(m95, "developmental", "CohPC_age")
  if (nrow(ca) == 1 && is.na(ca$value)) {
    upper <- fmt(max_in_note(ca$note))
    expect("0.95 continuity x age band reported as not reached",
           has_text(sprintf("the 0.95 target was not reached within the %s texts simulated", upper)),
           paste("not reached within", upper))
  } else {
    check_interval(m95, "developmental", "CohPC_age", "0.95 continuity x age band")
  }
  nr <- row_of(m95, "narration", "LexPC_narr")
  if (nrow(nr) != 1 || is.na(nr$value)) {
    expect("0.95 narration selectivity", FALSE, "absent or not solved in the CSV")
  } else {
    expect("0.95 narration selectivity", has(paste0(num(fmt(nr$value)), " at 0\\.95")),
           fmt(nr$value))
  }
  check_interval(m95, "within_child", "accum", "0.95 within-child accumulated reading")
}

writeLines("")
writeLines("== Bayes-factor criterion, priced by solve_at_bf10.R ==")
mbf <- read_solved(file.path("design_analysis", "minimum_texts_bf10.csv"))
if (is.null(mbf)) {
  skip("Bayes-factor requirements", "minimum_texts_bf10.csv is absent")
} else {
  # The protocol quotes these to the nearest ten, as "about N", for the parameters it
  # registers; the narration model's main effects are not quoted.
  mbf <- mbf[!(mbf$model == "narration" & mbf$param %in% c("LexPC", "CohPC")), ]
  ten <- function(x) fmt(round(x, -1))
  for (i in seq_len(nrow(mbf))) {
    r <- mbf[i, ]
    label <- sprintf("BF10 %s %s at %.2f", r$model, r$param, r$target)
    if (is.na(r$value)) {
      expect(label, has_text("neither reaching 0.95 within the 1,600 texts simulated") ||
                    has_text("not reaching 0.95 within 1,600"), "not reached within the grid")
    } else {
      expect(label, has(num(ten(r$value))), ten(r$value))
    }
  }
}

writeLines("")
writeLines("== ordinal precision projection ==")
mo <- read_solved(file.path("design_analysis", "minimum_texts_ordinal.csv"))
if (is.null(mo)) {
  skip("ordinal projection", "minimum_texts_ordinal.csv is absent")
} else if (!all(c("projected_texts", "projected_qualifying_texts") %in% names(mo))) {
  expect("ordinal projection", FALSE,
         "no projection columns: run design_analysis/summarise_ordinal.R")
} else {
  if (all(is.na(mo$value))) {
    upper <- fmt(max(vapply(mo$note, max_in_note, numeric(1))))
    expect("0.90 target reported as not reached",
           has_text(sprintf("the 0.90 target is not reached within the %s texts simulated", upper)),
           paste("not reached within", upper))
  } else {
    expect("0.90 target reported as not reached", FALSE,
           paste("solved in the CSV for", paste(mo$param[!is.na(mo$value)], collapse = ", ")))
  }
  pr <- range(mo$projected_texts)
  expect("projected generated-text range",
         has(paste0(num(fmt(pr[1])), " to ", num(fmt(pr[2])), " generated texts")),
         sprintf("%s to %s", fmt(pr[1]), fmt(pr[2])))
  qr <- range(mo$projected_qualifying_texts)
  expect("projected qualifying-text range",
         has(paste0(num(fmt(qr[1])), " to ", num(fmt(qr[2])), " carrying at least five ratings")),
         sprintf("%s to %s", fmt(qr[1]), fmt(qr[2])))
}

writeLines("")
writeLines("== literature counts ==")
gp <- utils::read.csv("literature/scopus_gap_sizes.csv", stringsAsFactors = FALSE)
if (anyNA(gp$n) || sum(gp$size == 1) != 3 || sum(gp$size == 2) != 3 || sum(gp$size == 3) != 1)
  stop("scopus_gap_sizes.csv should hold three concept counts, three pairwise counts ",
       "and one three-way count, with none missing", call. = FALSE)
for (i in which(gp$size == 1)) expect(gp$label[i], has(num(fmt(gp$n[i]))), fmt(gp$n[i]))
pair <- fmt(gp$n[gp$size == 2])
pair_rx <- paste0(num(pair[1]), ", ", num(pair[2]), " and ", num(pair[3]), " records")
expect("pairwise intersections, in the text",
       has(paste0("pairwise intersections were ", pair_rx)), paste(pair, collapse = ", "))
expect("pairwise intersections, in the Figure 1 caption",
       has(paste0("pairwise intersections hold ", pair_rx)), paste(pair, collapse = ", "))
three <- gp$n[gp$size == 3]
if (three == 0) {
  expect("three-way intersection, in the text",
         has_text("three-way intersection was empty"), "0")
  expect("three-way intersection, in the Figure 1 caption",
         has_text("three-way intersection holds none"), "0")
} else {
  expect("three-way intersection", has(paste0("three-way intersection[^.]{0,40}", num(fmt(three)))),
         fmt(three))
}

writeLines("")
writeLines("== theory object ==")
NUM_WORDS <- c("one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
               "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
               "seventeen", "eighteen", "nineteen", "twenty")
if (!requireNamespace("theoryforge", quietly = TRUE)) {
  skip("theory object", "theoryforge is not installed")
} else {
  th <- theoryforge::tf_read("theory/intract.theory.yaml")
  chk <- theoryforge::tf_check(th)
  score <- sprintf("%.1f", chk$aggregate_score)
  expect("aggregate score quoted in the manuscript",
         has(paste0("scoring ", num(score), " out of 100")), score)
  for (x in list(list("construct count", th$constructs, "constructs"),
                 list("proposition count", th$propositions, "propositions"),
                 list("auxiliary assumption count", th$auxiliary_assumptions,
                      "auxiliary assumptions"),
                 list("rival account count", th$alternatives, "rival accounts"))) {
    n <- length(x[[2]])
    if (n < 1 || n > length(NUM_WORDS)) {
      expect(x[[1]], FALSE, sprintf("%d has no entry in the number-word lookup", n))
      next
    }
    phrase <- paste(NUM_WORDS[n], x[[3]])
    expect(x[[1]], has(paste0("(?<![A-Za-z-])", phrase)),
           sprintf("%d, quoted as '%s'", n, phrase))
  }
}

writeLines("")
if (length(fail)) {
  writeLines(sprintf("FAILED: %d claim(s) do not match their artefact", length(fail)))
  writeLines(paste0("  - ", fail))
  quit(status = 1)
}
if (length(skipped)) {
  writeLines(sprintf("INCOMPLETE: not checked: %s", paste(skipped, collapse = "; ")))
  if (!allow_skip) quit(status = 1)
  writeLines("INTRACT_ALLOW_SKIP=1 is set, so the incomplete run exits 0.")
  quit(status = 0)
}
writeLines("All checked numbers match their artefacts (the supplement is not checked).")
