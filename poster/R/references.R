# InTRACt poster: the parts of README.md written from the poster's sources.
#
# The sheet carries author-date citations only, and the QR code opens this
# folder on GitHub, where README.md shows the full APA 7 list and a table of the
# evidence map's numbers. The list is rendered by Pandoc's citeproc from the
# bibliography files and style the poster itself cites with, and the table from
# data/evidence.csv, so the README and the sheet cannot disagree. poster.qmd
# calls write_references() and write_evidence_table() on every render.

# Every key cited in poster.qmd, plus the source of every row on the evidence
# map. Strings that look like keys but are not in the bibliography (the "@" of
# an email address) are dropped; a key on the evidence map that is missing from
# the bibliography stops the render.
cited_keys <- function(bib, qmd = "poster.qmd", evidence = "data/evidence.csv") {
  bib_keys <- unlist(lapply(bib, function(f) {
    x <- readLines(f, encoding = "UTF-8", warn = FALSE)
    sub("^@[A-Za-z]+\\{([^,]+),.*$", "\\1", grep("^@[A-Za-z]+\\{", x, value = TRUE))
  }))
  txt <- readLines(qmd, encoding = "UTF-8", warn = FALSE)
  in_text <- unlist(regmatches(txt, gregexpr("(?<=@)[A-Za-z][A-Za-z0-9_:-]*[A-Za-z0-9]",
                                             txt, perl = TRUE)))
  ev <- utils::read.csv(evidence, stringsAsFactors = FALSE, encoding = "UTF-8")
  on_map <- unique(ev$bibkey)
  missing <- setdiff(on_map, bib_keys)
  if (length(missing)) stop("evidence.csv cites keys not in the bibliography: ",
                            paste(missing, collapse = ", "), call. = FALSE)
  unique(c(intersect(in_text, bib_keys), on_map))
}

# Renders the list for `keys` as GitHub Markdown and splices it into the README
# between its two marker comments, leaving the rest of the file as it is.
write_references <- function(bib, csl, readme = "README.md",
                             start = "<!-- references:start -->",
                             end = "<!-- references:end -->") {
  keys <- cited_keys(bib)
  quarto <- Sys.which("quarto")
  if (!nzchar(quarto)) stop("quarto is not on the PATH, so the README's reference list ",
                            "cannot be rendered", call. = FALSE)
  src <- tempfile(fileext = ".md")
  out <- tempfile(fileext = ".md")
  on.exit(unlink(c(src, out)), add = TRUE)
  writeLines(c("---",
               paste0("nocite: \"", paste0("@", keys, collapse = ", "), "\""),
               "lang: en-GB",
               "---", "", "::: {#refs}", ":::"), src)
  # The bibliography and style go on the command line, not in the YAML: Pandoc
  # reads metadata strings as Markdown, whose smart punctuation would turn a
  # "--" in a path into a dash.
  opt_path <- function(flag, p)
    shQuote(paste0(flag, normalizePath(p, winslash = "/", mustWork = TRUE)))
  # gfm without raw HTML drops citeproc's wrapping <div>s, which GitHub would
  # otherwise show as clutter, and keeps the italics and the DOI links.
  status <- system2(quarto, c("pandoc", shQuote(src), "--citeproc", "--wrap=none",
                              vapply(bib, function(b) opt_path("--bibliography=", b), ""),
                              opt_path("--csl=", csl),
                              "-t", "gfm-raw_html", "-o", shQuote(out)))
  if (status != 0) stop("pandoc could not render the reference list", call. = FALSE)
  refs <- readLines(out, encoding = "UTF-8", warn = FALSE)
  refs <- refs[nzchar(trimws(refs))]
  splice_readme(as.vector(rbind(refs, "")), start, end, readme)
  invisible(keys)
}

# Writes the evidence map's numbers into the README as a table, between its two
# marker comments, so that a reader can check every row without opening the
# data file. Each source links to its DOI, or its URL where it has none.
write_evidence_table <- function(readme = "README.md", file = "data/evidence.csv",
                                 start = "<!-- evidence:start -->",
                                 end = "<!-- evidence:end -->") {
  ev <- read_evidence(file)
  for (v in c("group", "label", "verdict")) ev[[v]] <- curly(ev[[v]])
  url <- bib_urls()[ev$bibkey]
  num <- function(x) sub("^-", "−", formatC(x, format = "f", digits = 2))
  # A source line reads 'Authors, year · ages · k = n'; its parts become
  # columns.
  parts <- strsplit(ev$source, " · ", fixed = TRUE)
  is_count <- function(x) grepl("^(k = [0-9]+|[0-9]+ studies)$", x)
  who <- vapply(parts, `[`, "", 1)
  cite <- sub("^(.*), ([0-9]{4}[a-z]?)$", "\\1 (\\2)", who)
  ages <- vapply(parts, function(p) paste(p[-1][!is_count(p[-1])], collapse = ", "), "")
  pooled <- vapply(parts, function(p) paste(p[-1][is_count(p[-1])], collapse = ""), "")
  # A source that gives no ages (they are in the finding's label) or no count
  # shows a dash, so that an empty cell is not read as missing data.
  ages[!nzchar(ages)] <- "–"; pooled[!nzchar(pooled)] <- "–"
  effect <- ifelse(is.na(ev$estimate), paste0("*", ev$verdict, "*"),
                   sprintf("%s [%s, %s]", num(ev$estimate), num(ev$lo), num(ev$hi)))
  rows <- character(0)
  for (g in unique(ev$group)) {
    rows <- c(rows, sprintf("| **%s** | | | | |", g))
    for (i in which(ev$group == g))
      rows <- c(rows, sprintf("| %s | [%s](%s) | %s | %s | %s |", ev$label[i], cite[i],
                              url[i], ages[i], effect[i], pooled[i]))
  }
  splice_readme(c("| Finding | Source | Children | Effect [95% CI] | Pooled |",
                  "|---|---|---|---|---|", rows, ""), start, end, readme)
  invisible(nrow(ev))
}

# Replaces what lies between two marker comments in the README with `body`,
# leaving the rest of the file as it is.
splice_readme <- function(body, start, end, readme = "README.md") {
  md <- readLines(readme, encoding = "UTF-8", warn = FALSE)
  i <- match(start, md); j <- match(end, md)
  if (is.na(i) || is.na(j) || j < i)
    stop(readme, " lacks the markers ", start, " and ", end, call. = FALSE)
  md <- c(md[seq_len(i)], "", body, md[j:length(md)])
  # Written as bytes, so the file stays UTF-8 with LF line ends on Windows too.
  writeBin(charToRaw(enc2utf8(paste0(paste(md, collapse = "\n"), "\n"))), readme)
}
