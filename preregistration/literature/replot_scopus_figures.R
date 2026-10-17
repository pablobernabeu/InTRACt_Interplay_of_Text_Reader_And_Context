# InTRACt Stage 1: redraw the two Scopus figures from the archived counts.
#
# Run from the preregistration directory, after scopus_gap_analysis.R:
#   Rscript literature/replot_scopus_figures.R
# Reads literature/scopus_gap_sizes.csv and scopus_topic_trends.csv. Writes
# literature/scopus_gap_intersections.{png,pdf} (Figure 1) and
# scopus_topic_trends.{png,pdf} (a supplementary figure).
#
# scopus_gap_analysis.R queries the API and archives its counts as CSV files.
# This script redraws the figures from those archives, so presentation can be
# revised without issuing a single new request or moving the recorded numbers.
#
# The PDF is the copy the manuscript embeds, so that figure text remains text.
# The captions in the manuscript and the supplement carry the titles, the
# search date and the query strings (via scopus_search_record.md), so the
# in-image title, subtitle and footnote that the package draws by default are
# removed here, and the three comparison series get short names in place of
# their full query expressions, which did not fit the plot area.

suppressPackageStartupMessages({
  library(scopusflow)
  library(ggplot2)
  library(depictr)
})
OUT <- "literature"

# Both figures are saved at this size and embedded at 90 per cent of the text
# width, about 14 cm, which is the width the type-size floor is checked at.
FIG_W_IN   <- 7.5
FIG_H_IN   <- 4.6
PRINT_W_CM <- 14

# The archived CSV is never modified: the relabelling happens in memory. The
# names are the archived queries verbatim, so they stay whole on one line each.
# nolint start: line_length_linter.
short_names <- c(
  "(\"AI-generated\" OR \"LLM-generated\" OR \"machine-generated\" OR \"generative AI\")" = "Machine-generated text",
  "(\"reading app\" OR \"storybook app\" OR \"e-book\" OR \"ebook\" OR \"digital storybook\")" = "Reading apps and e-books",
  "(\"text-to-speech\" OR \"read-aloud\" OR \"audio narration\" OR \"reading while listening\")" = "Narration"
)
# nolint end

# The package's default palette (viridis) fails depictr's contrast floor on
# white, so both figures are recoloured with the design-analysis figure's four
# colours (Okabe-Ito blue and vermilion, a near-black and a dark magenta),
# followed by Okabe-Ito green and orange. ggplot takes as many as a scale needs.
PAIR <- c("#0072b2", "#d55e00", "#333333", "#8e2c6b", "#009e73", "#e69f00")

strip_chrome <- function(p) {
  p$labels$title <- NULL
  p$labels$subtitle <- NULL
  p$labels$caption <- NULL
  suppressMessages(
    p + scale_fill_manual(values = PAIR) + scale_colour_manual(values = PAIR) +
      theme(plot.margin = margin(t = 6, r = 12, b = 6, l = 6))
  )
}

# Every check is fatal except one. Colour joined by a second encoding needs a
# change to the package's geoms, so that failure is reported and the run goes
# on; the figures' groups are also labelled in text. Both figures are checked
# before either is saved.
WARN_ONLY <- "redundant_encoding"
audit <- function(p, what) {
  chk <- check_figure(p, width_cm = PRINT_W_CM, render_width_cm = FIG_W_IN * 2.54)
  print(chk)
  failed <- chk[chk$verdict == "fail", , drop = FALSE]
  if (nrow(failed)) {
    print(failed)
    fatal <- setdiff(failed$check, WARN_ONLY)
    if (length(fatal))
      stop("figure check failed for ", what, ": ", paste(fatal, collapse = ", "), call. = FALSE)
    warning("figure check reported failures for ", what, ": ",
            paste(failed$check, collapse = ", "), call. = FALSE)
  }
  invisible(chk)
}

# Reads one archive and stops on a missing value, which the package would
# otherwise drop from the chart or draw as a gap.
read_archive <- function(name) {
  d <- utils::read.csv(file.path(OUT, name), stringsAsFactors = FALSE, check.names = FALSE)
  holes <- names(d)[colSums(is.na(d)) > 0]
  if (!nrow(d) || length(holes))
    stop(name, " is empty or has missing values in: ", paste(holes, collapse = ", "),
         call. = FALSE)
  d
}

# The package drops the intersection with no records from the log axis and says
# so in its caption, which is removed here; the manuscript's caption says it.
ints <- read_archive("scopus_gap_sizes.csv")
class(ints) <- c("scopus_intersections", "data.frame")
p <- strip_chrome(plot_scopus_intersections(ints))

cmp <- read_archive("scopus_topic_trends.csv")
# A comparison query that matches no key would keep its full expression as its
# label, and a key that matches no query would mean the archive has changed.
series <- unique(cmp$abridged_query[cmp$query_type != "reference"])
if (length(setdiff(series, names(short_names))) || length(setdiff(names(short_names), series)))
  stop("the short names do not match the archived comparison queries", call. = FALSE)
cmp$abridged_query <- ifelse(cmp$abridged_query %in% names(short_names),
                             unname(short_names[cmp$abridged_query]), cmp$abridged_query)
class(cmp) <- c("scopus_comparison", "data.frame")
# The series are labelled at their right-hand ends, so the x axis is expanded
# to leave room for the labels inside the panel and clipping is switched off.
pc <- suppressMessages(
  strip_chrome(plot_scopus_comparison(cmp)) +
    coord_cartesian(clip = "off") +
    scale_x_continuous(breaks = as.numeric(seq(min(cmp$year), max(cmp$year), by = 2)),
                       expand = expansion(mult = c(0.02, 0.46)))
)

audit(p, "gap intersections")
audit(pc, "topic trends")

# ragg is named because ggsave() otherwise draws the PNG with whichever device is
# installed, and the fallback rasterises text differently.
save_both <- function(p, name) {
  ggplot2::ggsave(file.path(OUT, paste0(name, ".png")), p, width = FIG_W_IN,
                  height = FIG_H_IN, dpi = 300, bg = "white", device = ragg::agg_png)
  ggplot2::ggsave(file.path(OUT, paste0(name, ".pdf")), p, width = FIG_W_IN,
                  height = FIG_H_IN, bg = "white", device = grDevices::cairo_pdf)
}
save_both(p, "scopus_gap_intersections")
save_both(pc, "scopus_topic_trends")

writeLines("redrew the Scopus figures (png and pdf) from the archived counts")
