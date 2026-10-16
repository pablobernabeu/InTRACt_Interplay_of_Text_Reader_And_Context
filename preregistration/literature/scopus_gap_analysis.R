# InTRACt Stage 1: a dated, reproducible count of the literature around the study.
#
# Run from the preregistration directory (not with --vanilla, since the API key
# is read from the SCOPUS_API_KEY environment variable, normally set in
# ~/.Renviron and never in a .Renviron inside this repository):
#   Rscript --no-save --no-restore literature/scopus_gap_analysis.R
# Writes literature/scopus_gap_sizes.csv, scopus_topic_trends.csv,
# scopus_search_record.md, scopus_run_stamp.txt and default-styled PNGs of both
# figures. Run replot_scopus_figures.R afterwards for the styled PNG and PDF
# figures the manuscript uses.
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

msg("counting the three concept sets and every intersection")
ints <- scopus_intersections(
  concepts,
  intersections = list(
    c("Children's reading", "Computational text features"),
    c("Children's reading", "Platform log data"),
    c("Computational text features", "Platform log data"),
    c("Children's reading", "Computational text features", "Platform log data")
  ),
  abbrev = abbrev, years = YEARS, verbose = TRUE
)

print(ints)
utils::write.csv(as.data.frame(ints), file.path(OUT, "scopus_gap_sizes.csv"), row.names = FALSE)

p <- plot_scopus_intersections(ints)
ggplot2::ggsave(file.path(OUT, "scopus_gap_intersections.png"), p,
                width = 7.5, height = 4.6, dpi = 300, bg = "white")

# How the surrounding topics have grown over the window, which is the other half
# of the rationale: the materials children now read are increasingly machine
# generated, and the evidence base has not kept pace.
msg("comparing publication trends")
cmp <- scopus_compare_topics(
  reference_query = paste('("reading comprehension" OR "text comprehension"',
                          'OR "reading fluency") AND (child OR children',
                          'OR "primary school" OR "elementary school")'),
  # The comparison queries are kept whole, as scopusflow records them.
  # nolint start: line_length_linter.
  comparison_terms = c(
    "AI-generated text"        = '("AI-generated" OR "LLM-generated" OR "machine-generated" OR "generative AI")',
    "reading apps"             = '("reading app" OR "storybook app" OR "e-book" OR "ebook" OR "digital storybook")',
    "text-to-speech narration" = '("text-to-speech" OR "read-aloud" OR "audio narration" OR "reading while listening")'
  ),
  # nolint end
  years = YEARS, field = "TITLE-ABS-KEY", verbose = TRUE
)

print(cmp)
utils::write.csv(as.data.frame(cmp), file.path(OUT, "scopus_topic_trends.csv"), row.names = FALSE)

pc <- plot_scopus_comparison(cmp)
ggplot2::ggsave(file.path(OUT, "scopus_topic_trends.png"), pc,
                width = 7.5, height = 4.6, dpi = 300, bg = "white")

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
  "| Year | Children's reading | with narration | with apps or e-books | with AI-generated text |",
  "|---:|---:|---:|---:|---:|"
)

trend_lab <- ifelse(grepl("AI-generated", cmp$abridged_query), "ai",
                    ifelse(grepl("reading app", cmp$abridged_query), "apps",
                           ifelse(grepl("text-to-speech", cmp$abridged_query), "narr", "ref")))
tw <- stats::reshape(data.frame(year = cmp$year, lab = trend_lab, n = cmp$n),
                     idvar = "year", timevar = "lab", direction = "wide")
names(tw) <- sub("^n[.]", "", names(tw))
tw <- tw[order(tw$year), ]
rec <- c(rec, sprintf("| %d | %d | %d | %d | %d |",
                      tw$year, tw$ref, tw$narr, tw$apps, tw$ai))

writeLines(rec, file.path(OUT, "scopus_search_record.md"))

writeLines(c(paste("run:", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
             paste("scopusflow:", as.character(packageVersion("scopusflow"))),
             paste("years:", min(YEARS), "-", max(YEARS)),
             "field: TITLE-ABS-KEY"),
           file.path(OUT, "scopus_run_stamp.txt"))
msg("done")
