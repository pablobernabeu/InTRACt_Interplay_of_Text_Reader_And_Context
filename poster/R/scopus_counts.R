# InTRACt poster: a dated, reproducible count of what research on children's
# digital reading has looked at.
#
# Run from the poster directory (not with --vanilla, since scopusflow reads the
# API key from SCOPUS_API_KEY, normally set in ~/.Renviron):
#   Rscript --no-save --no-restore R/scopus_counts.R
# Writes data/scopus_digital_share.csv, data/scopus_focus_trends.csv,
# data/scopus_gap.csv, data/scopus_search_record.md and data/scopus_run_stamp.txt.
# The poster reads only these files, so rendering it issues no API request.
#
# The poster's headline claim is that research on children's digital reading has
# asked about the device and what is added to the text, and seldom about the
# language of the text itself. A claim of that shape is usually asserted. Here it
# is counted, with every query recorded verbatim, so that a reader can rerun it.
# Only count queries are issued, one request per query and year.

suppressPackageStartupMessages(library(scopusflow))
stopifnot(scopus_has_key())

OUT   <- "data"
YEARS <- 2010:2025  # complete publication years only

# Every expression carries its own field tag, so scopusflow counts exactly the
# string recorded here (field = NULL below) and the document-type limit can sit
# outside the TITLE-ABS-KEY wrapper. The limit keeps articles, reviews,
# conference papers and book chapters, and drops whole proceedings volumes,
# which a probe on 14 October 2026 showed matching the log-data terms through
# their tables of contents.
tak <- function(q) paste0("TITLE-ABS-KEY(", q, ")")
DOCTYPES <- "(DOCTYPE(ar) OR DOCTYPE(re) OR DOCTYPE(cp) OR DOCTYPE(ch))"

READING <- tak(paste(
  '("reading comprehension" OR "reading fluency" OR "reading skill*" OR "reading development"',
  'OR "reading achievement" OR "reading ability" OR "reading abilities" OR "learning to read"',
  'OR "early literacy" OR "emergent literacy" OR "story comprehension" OR "word reading"',
  'OR "beginning reader*" OR "struggling reader*")',
  'AND (child* OR pupil* OR "primary school*" OR "elementary school*" OR kindergarten*',
  'OR preschool* OR "first grade*" OR "young reader*")'
))

DIGITAL <- tak(paste(
  '(digital OR "e-book*" OR ebook* OR "electronic book*" OR "electronic storybook*" OR "e-reader*"',
  'OR tablet* OR ipad* OR touchscreen* OR "touch screen*" OR smartphone* OR "mobile app*"',
  'OR "educational app*" OR "reading app*" OR "storybook app*" OR app OR apps',
  'OR "computer-assisted" OR "computer-based" OR "educational technolog*" OR "technology-enhanced"',
  'OR multimedia OR "on screen" OR "on-screen" OR "screen time" OR "screen use" OR "screen-based"',
  'OR "artificial intelligence" OR chatbot* OR "conversational agent*" OR "text-to-speech"',
  'OR "speech synthesis" OR "intelligent tutor*" OR "online reading" OR hypertext)'
))

# What a record on children's digital reading looks at. The first five are the
# device and what is added to the text; the last two are what this study adds.
FOCI <- c(
  "Screen time and media use" = tak(paste(
    '("screen time" OR "screen use" OR "screen exposure" OR "media use" OR "media exposure"',
    'OR "digital media use" OR "technology use" OR "device use")'
  )),
  "Screen versus paper" = tak(paste(
    '("paper-based" OR "on paper" OR "printed book*" OR "print book*" OR "paper book*"',
    'OR "printed text*" OR "print-based" OR "print versus" OR "paper versus" OR "versus print"',
    'OR "versus paper" OR "reading medium" OR "reading media" OR "medium effect*"',
    'OR "mode effect*" OR "screen inferiority")'
  )),
  "Multimedia and games" = tak(paste(
    '(multimedia OR animat* OR hotspot* OR "interactive feature*" OR "enhanced e-book*"',
    'OR "enhanced ebook*" OR "digital enhancement*" OR gamif* OR "game-based"',
    'OR "educational game*" OR "video game*")'
  )),
  "Narration and text-to-speech" = tak(paste(
    '("text-to-speech" OR "speech synthesis" OR "synthetic speech" OR "audio narration"',
    'OR narrated OR "read-aloud tool*" OR "read-aloud feature*" OR "read-aloud function*"',
    'OR audiobook* OR "audio book*" OR "reading while listening" OR "reading-while-listening"',
    'OR "audio support" OR "audio-assisted")'
  )),
  "AI and chatbots" = tak(paste(
    '("artificial intelligence" OR "generative AI" OR "large language model*" OR ChatGPT',
    'OR chatbot* OR "conversational agent*" OR "AI-generated" OR "intelligent tutor*"',
    'OR "machine-generated")'
  )),
  "Language of the text" = tak(paste(
    '("text complexity" OR "text difficulty" OR readability OR "linguistic feature*"',
    'OR "linguistic complexity" OR "linguistic characteristic*" OR "syntactic complexity"',
    'OR "sentence complexity" OR "word frequency" OR "lexical difficulty"',
    'OR "lexical complexity" OR cohesion OR "text characteristic*" OR "text feature*"',
    'OR "text propert*" OR "lexical feature*")'
  )),
  "Log data and learning analytics" = tak(paste(
    '("log data" OR "log file*" OR logfile* OR "learning analytics" OR "trace data"',
    'OR "usage data" OR clickstream* OR "process data" OR telemetry OR "big data"',
    'OR "app data" OR "behavioural logs" OR "behavioral logs" OR "data mining")'
  ))
)

READING_DT <- paste(READING, "AND", DOCTYPES)
DIGITAL_READING_DT <- paste(READING, "AND", DIGITAL, "AND", DOCTYPES)

msg <- function(...) cat(format(Sys.time(), "%H:%M:%S"), " ", ..., "\n", sep = "")

FILES <- file.path(OUT, c(share = "scopus_digital_share.csv", foci = "scopus_focus_trends.csv",
                          gap = "scopus_gap.csv", stamp = "scopus_run_stamp.txt"))
names(FILES) <- c("share", "foci", "gap", "stamp")

# The counts move as Scopus indexes new records, so a rerun is a new dataset
# rather than a repeat of this one. The API is therefore queried only when the
# archived counts are missing or POSTER_SCOPUS_REFRESH=1 asks for a fresh run.
# Either way the search record below is rebuilt from the archived files.
if (identical(Sys.getenv("POSTER_SCOPUS_REFRESH"), "1") || !all(file.exists(FILES))) {

  # 1. How much of children's reading research involves digital technology, by year.
  msg("digital share of children's reading research")
  share <- scopus_compare_topics(
    reference_query = READING_DT,
    comparison_terms = c("Digital technology" = DIGITAL),
    years = YEARS, field = NULL, verbose = TRUE
  )
  utils::write.csv(as.data.frame(share), FILES[["share"]], row.names = FALSE)

  # 2. Within that research, what each record looks at, by year.
  msg("what research on children's digital reading looks at")
  foci <- scopus_compare_topics(
    reference_query = DIGITAL_READING_DT,
    comparison_terms = FOCI,
    years = YEARS, field = NULL, verbose = TRUE
  )
  utils::write.csv(as.data.frame(foci), FILES[["foci"]], row.names = FALSE)

  # 3. The cell this study occupies: the language of the text together with log data.
  msg("the language of the text together with log data")
  gap <- scopus_intersections(
    c("Digital reading" = DIGITAL_READING_DT,
      "Language of the text" = FOCI[["Language of the text"]],
      "Log data" = FOCI[["Log data and learning analytics"]]),
    intersections = list(
      c("Digital reading", "Language of the text"),
      c("Digital reading", "Log data"),
      c("Digital reading", "Language of the text", "Log data")
    ),
    years = YEARS, field = NULL, verbose = TRUE
  )
  utils::write.csv(as.data.frame(gap), FILES[["gap"]], row.names = FALSE)

  writeLines(c(paste("run:", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
               paste("scopusflow:", as.character(packageVersion("scopusflow"))),
               paste("years:", min(YEARS), "-", max(YEARS)),
               "field: TITLE-ABS-KEY, document types ar/re/cp/ch"),
             FILES[["stamp"]])
}

share <- utils::read.csv(FILES[["share"]], stringsAsFactors = FALSE)
foci  <- utils::read.csv(FILES[["foci"]], stringsAsFactors = FALSE)
gap   <- utils::read.csv(FILES[["gap"]], stringsAsFactors = FALSE)
stamp <- readLines(FILES[["stamp"]])

# scopus_compare_topics() labels each series by its query string. The labels the
# poster prints are attached here by exact match, which also guards against a
# query edited above without a refresh: an unmatched series stops the script.
label_series <- function(d, terms, reference_label) {
  lab <- ifelse(d$query_type == "reference", reference_label,
                names(terms)[match(d$abridged_query, terms)])
  if (anyNA(lab)) stop("archived counts do not match the queries above; ",
                       "rerun with POSTER_SCOPUS_REFRESH=1", call. = FALSE)
  d$label <- lab
  d
}
share <- label_series(share, c("Digital technology" = DIGITAL), "Children's reading development")
foci  <- label_series(foci, FOCI, "Children's digital reading")
utils::write.csv(share, FILES[["share"]], row.names = FALSE)
utils::write.csv(foci, FILES[["foci"]], row.names = FALSE)

# A dated record of exactly what was counted. Reporting follows PRISMA-S for the
# items a count-only search can supply.
msg("writing the search record")
fmt <- function(x) format(x, big.mark = ",", trim = TRUE)
tot <- function(d, lab) sum(d$n[d$label == lab])
run_date <- as.Date(sub("^run: (\\S+).*$", "\\1", stamp[1]))
rec <- c(
  "# Scopus search record for the InTRACt poster",
  "",
  sprintf("Run on %s with %s against the Elsevier Scopus Search API.",
          format(run_date, "%d %B %Y"), sub(": ", " ", stamp[2])),
  sprintf("Publication years %d to %d. Field tag TITLE-ABS-KEY on every concept.",
          min(YEARS), max(YEARS)),
  "Document types limited to articles, reviews, conference papers and book chapters.",
  "No language or subject-area limit. Counts are the totals the API reported, not",
  "screened studies: nothing was downloaded, so the counts include false positives.",
  "",
  "Reporting follows PRISMA-S (Rethlefsen et al., 2021, doi:10.1186/s13643-020-01542-z)",
  "for the items a count-only search can supply: database, full search strategies,",
  "limits and restrictions, and date of search.",
  "",
  "## Concepts",
  "",
  sprintf("- **Children's reading development**: `%s`", READING),
  sprintf("- **Digital technology**: `%s`", DIGITAL),
  sprintf("- **Document-type limit**: `%s`", DOCTYPES),
  "",
  "## Foci within children's digital reading",
  "",
  "| Focus | Records | Query |",
  "|---|---:|---|",
  sprintf("| %s | %s | `%s` |", names(FOCI),
          vapply(names(FOCI), function(f) fmt(tot(foci, f)), ""), FOCI),
  "",
  "## Totals",
  "",
  sprintf("- Children's reading development: %s records",
          fmt(tot(share, "Children's reading development"))),
  sprintf("- of which digital technology: %s records", fmt(tot(share, "Digital technology"))),
  sprintf("- %s: %s records", gap$label, fmt(gap$n))
)
writeLines(rec, file.path(OUT, "scopus_search_record.md"))
msg("done")
