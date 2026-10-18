# InTRACt Stage 1: a dated, reproducible count of the literature around the study.
#
# Run from the preregistration directory (not with --vanilla, since the API key
# is read from the SCOPUS_API_KEY environment variable, normally set in
# ~/.Renviron and never in a .Renviron inside this repository):
#   Rscript --no-save --no-restore literature/scopus_gap_analysis.R
# Writes literature/scopus_gap_sizes.csv, scopus_topic_trends.csv,
# scopus_search_record.md and scopus_run_stamp.txt, then runs
# replot_scopus_figures.R, which draws the figures from those files.
#
# The Introduction claims that children's reading has been modelled from text
# properties in the laboratory, and that platform log data have been used to
# study reading, but that almost nobody has done both at once. A claim of that
# shape is usually asserted. Here it is measured: three concept sets are sized
# on Scopus, together with their pairwise and three-way intersections, on a
# stated date and with the exact query strings recorded, so a reader can rerun
# it and a reviewer can check it.
#
# Only count queries are issued, one request per cell, so the cost to the API
# quota is a few dozen requests rather than a harvest.

library(scopusflow)

stopifnot(scopus_has_key())
OUT   <- "literature"
YEARS <- 2018:2026

# The three concepts, written as complete field-tagged expressions so that
# scopusflow counts exactly the string recorded here and nothing is wrapped
# implicitly around a compound query.
concepts <- c(
  "Children's reading" = paste(
    'TITLE-ABS-KEY("reading comprehension" OR "text comprehension"',
    'OR "passage comprehension" OR "reading fluency" OR "reading time")',
    'AND TITLE-ABS-KEY(child OR children OR pupils OR "primary school"',
    'OR "elementary school")'
  ),
  "Computational text features" = paste(
    'TITLE-ABS-KEY("word frequency" OR "lexical diversity" OR "syntactic complexity"',
    'OR "dependency distance" OR "text cohesion" OR "text coherence"',
    'OR readability OR surprisal OR "age of acquisition" OR concreteness)',
    'AND TITLE-ABS-KEY(computational OR corpus OR "natural language processing"',
    'OR "language model" OR psycholinguistic)'
  ),
  "Platform log data" = paste(
    'TITLE-ABS-KEY("log data" OR logfile OR "log file" OR "trace data"',
    'OR "learning analytics" OR "app data" OR "mobile application"',
    'OR "digital platform" OR telemetry OR "behavioural logs" OR "behavioral logs")'
  )
)

abbrev <- c("Children's reading" = "Reading",
            "Computational text features" = "Text features",
            "Platform log data" = "Log data")

msg <- function(...) cat(format(Sys.time(), "%H:%M:%S"), " ", ..., "\n", sep = "")

# Counts that are missing, negative or incoherent stop the run before anything
# is archived, since the archive is what the figures and the record are drawn
# from and the API is not queried again to correct it.
check_counts <- function(ok, what) {
  if (!isTRUE(all(ok))) stop("the Scopus counts failed a check: ", what, call. = FALSE)
}

intersections <- list(
  c("Children's reading", "Computational text features"),
  c("Children's reading", "Platform log data"),
  c("Computational text features", "Platform log data"),
  c("Children's reading", "Computational text features", "Platform log data")
)
msg("counting the three concept sets and every intersection")
ints <- scopus_intersections(concepts, intersections = intersections,
                             abbrev = abbrev, years = YEARS, verbose = TRUE)

print(ints)
check_counts(nrow(ints) == length(concepts) + length(intersections),
             "one row per concept set and per intersection")
check_counts(!is.na(ints$n) & ints$n >= 0 & ints$n == round(ints$n),
             "every count a whole number of at least zero")
# An intersection can hold no more records than the smallest of its sets.
members <- strsplit(ints$members, "; ", fixed = TRUE)
check_counts(all(unlist(members) %in% names(concepts)), "members named as the concept sets")
set_n <- ints$n[match(names(concepts), ints$label)]
names(set_n) <- names(concepts)
check_counts(!is.na(set_n), "a row for every concept set")
check_counts(mapply(function(n, m) n <= min(set_n[m]), ints$n, members),
             "no intersection larger than its smallest set")
utils::write.csv(as.data.frame(ints), file.path(OUT, "scopus_gap_sizes.csv"), row.names = FALSE)

# How the surrounding topics have grown over the window, which is the other half
# of the rationale: the materials children now read are increasingly machine
# generated, and the evidence base has not kept pace.
reference_query <- paste('("reading comprehension" OR "text comprehension"',
                         'OR "reading fluency") AND (child OR children',
                         'OR "primary school" OR "elementary school")')
# The comparison queries are kept whole, as scopusflow records them.
# nolint start: line_length_linter.
comparison_terms <- c(
  "AI-generated text"        = '("AI-generated" OR "LLM-generated" OR "machine-generated" OR "generative AI")',
  "reading apps"             = '("reading app" OR "storybook app" OR "e-book" OR "ebook" OR "digital storybook")',
  "text-to-speech narration" = '("text-to-speech" OR "read-aloud" OR "audio narration" OR "reading while listening")'
)
# nolint end
msg("comparing publication trends")
cmp <- scopus_compare_topics(reference_query = reference_query,
                             comparison_terms = comparison_terms,
                             years = YEARS, field = "TITLE-ABS-KEY", verbose = TRUE)

print(cmp)
check_counts(!is.na(cmp$n) & !is.na(cmp$reference_n), "no missing yearly count")
check_counts(table(cmp$abridged_query, cmp$year) == 1,
             "one row per query and year")
check_counts(nrow(cmp) == (1 + length(comparison_terms)) * length(YEARS),
             "every query counted in every year")
# Each comparison query is the reference query narrowed by a further term.
check_counts(cmp$n <= cmp$reference_n, "no comparison count above the reference count")
utils::write.csv(as.data.frame(cmp), file.path(OUT, "scopus_topic_trends.csv"), row.names = FALSE)

# A dated record of exactly what was counted, for the supplement. The counts
# above are the evidence for a claim in the Introduction, so the queries behind
# them are written out verbatim rather than paraphrased.
msg("writing the search-strategy record")

rec <- c(
  "# Scopus search record for the InTRACt literature counts",
  "",
  sprintf("Run on %s with scopusflow %s against the Elsevier Scopus Search API.",
          format(Sys.Date(), "%d %B %Y"), as.character(packageVersion("scopusflow"))),
  sprintf("Publication years %d to %d. Field tag TITLE-ABS-KEY throughout. No document type,",
          min(YEARS), max(YEARS)),
  "language or subject-area limit was applied. Counts are the totals the API reported,",
  "not row counts from a harvest: nothing was downloaded.",
  "",
  "Reporting follows PRISMA-S (Rethlefsen et al., 2021, doi:10.1186/s13643-020-01542-z)",
  "for the items a count-only search can supply: database name, full search strategies,",
  "limits and restrictions, and date of search. The remaining items belong to the",
  "systematic review that accompanies this protocol, not to this search.",
  "",
  "## Concept sets and their intersections",
  "",
  "| Set | Records | Query |",
  "|---|---:|---|",
  sprintf("| %s | %s | `%s` |", ints$label, format(ints$n, big.mark = ",", trim = TRUE),
          ints$query),
  "",
  "## Publication trend, by year",
  "",
  "| Year | Reference set | with narration | with apps or e-books | with AI-generated text |",
  "|---:|---:|---:|---:|---:|"
)

# Each column is matched on its whole query, so a query renamed above cannot
# fall into the wrong column or out of the table.
trend_key <- c(ref  = reference_query,
               ai   = comparison_terms[["AI-generated text"]],
               apps = comparison_terms[["reading apps"]],
               narr = comparison_terms[["text-to-speech narration"]])
trend_lab <- names(trend_key)[match(cmp$abridged_query, trend_key)]
check_counts(!is.na(trend_lab), "every trend query matched to a column of the record")
tw <- stats::reshape(data.frame(year = cmp$year, lab = trend_lab, n = cmp$n),
                     idvar = "year", timevar = "lab", direction = "wide")
names(tw) <- sub("^n[.]", "", names(tw))
tw <- tw[order(tw$year), ]
rec <- c(rec, sprintf("| %d | %d | %d | %d | %d |",
                      tw$year, tw$ref, tw$narr, tw$apps, tw$ai))

# The trend's queries are not the concept sets above, so they are written out
# too, which lets a reader rerun the supplementary trend figure from the record
# alone (register item FL-05).
trend_role <- c(ref = "Reference set", narr = "with narration",
                apps = "with apps or e-books", ai = "with AI-generated text")
tq <- unique(data.frame(lab = trend_lab, query = cmp$query))
check_counts(nrow(tq) == length(trend_role) && setequal(tq$lab, names(trend_role)),
             "one full query per column of the trend table")
tq <- tq[match(names(trend_role), tq$lab), ]
rec <- c(rec, "",
         "Each yearly count is the count of the query below for that publication year. The",
         "reference set is the trend's own query, not the Children's reading concept set above,",
         "and each comparison query is the reference query narrowed by a further term.",
         "",
         "| Column | Query |",
         "|---|---|",
         sprintf("| %s | `%s` |", trend_role[tq$lab], tq$query))

writeLines(rec, file.path(OUT, "scopus_search_record.md"))

writeLines(c(paste("run:", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
             paste("scopusflow:", as.character(packageVersion("scopusflow"))),
             paste("years:", min(YEARS), "-", max(YEARS)),
             "field: TITLE-ABS-KEY"),
           file.path(OUT, "scopus_run_stamp.txt"))

# The figures are drawn from the files just written, by the same script that
# redraws them later, so there is one way of drawing them.
msg("drawing the figures")
source(file.path(OUT, "replot_scopus_figures.R"), local = new.env())
msg("done")
