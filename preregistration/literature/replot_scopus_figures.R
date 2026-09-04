# InTRACt Stage 1: redraw the two Scopus figures from the archived counts.
#
# scopus_gap_analysis.R queries the API and archives its counts as CSV files.
# This script redraws the figures from those archives, so presentation can be
# revised without issuing a single new request or moving the recorded numbers.
#   Rscript literature/replot_scopus_figures.R
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

# The archived CSV is never modified: the relabelling happens in memory.
short_names <- c(
  "(\"AI-generated\" OR \"LLM-generated\" OR \"machine-generated\" OR \"generative AI\")" = "Machine-generated text",
  "(\"reading app\" OR \"storybook app\" OR \"e-book\" OR \"ebook\" OR \"digital storybook\")" = "Reading apps and e-books",
  "(\"text-to-speech\" OR \"read-aloud\" OR \"audio narration\" OR \"reading while listening\")" = "Narration"
)

# The package's default palette (viridis) fails depictr's contrast floor on
# white, so both figures are recoloured from the Okabe-Ito set that the
# design-analysis figure already uses; ggplot takes as many as a scale needs.
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

# Both figures are embedded at 90 to 100 per cent of the text width, about
# 14 cm, which is the width the type-size floor is checked at. A failure is
# printed and reported rather than fatal here, because the plot geometry is the
# package's and the remaining check (colour joined by a second encoding) needs a
# change to the package's geoms; the figures' groups are also labelled in text.
audit <- function(p, what) {
  chk <- check_figure(p, width_cm = 14, render_width_cm = 19.05)
  print(chk)
  failed <- chk[chk$verdict == "fail", , drop = FALSE]
  if (nrow(failed)) {
    print(failed)
    warning("figure check reported failures for ", what, ": ",
            paste(failed$check, collapse = ", "), call. = FALSE)
  }
  invisible(chk)
}

ints <- utils::read.csv(file.path(OUT, "scopus_gap_sizes.csv"),
                        stringsAsFactors = FALSE, check.names = FALSE)
class(ints) <- c("scopus_intersections", "data.frame")
p <- strip_chrome(plot_scopus_intersections(ints))
audit(p, "gap intersections")
ggplot2::ggsave(file.path(OUT, "scopus_gap_intersections.png"), p,
                width = 7.5, height = 4.6, dpi = 300, bg = "white")
ggplot2::ggsave(file.path(OUT, "scopus_gap_intersections.pdf"), p,
                width = 7.5, height = 4.6, bg = "white", device = grDevices::cairo_pdf)

cmp <- utils::read.csv(file.path(OUT, "scopus_topic_trends.csv"),
                       stringsAsFactors = FALSE, check.names = FALSE)
hit <- cmp$abridged_query %in% names(short_names)
cmp$abridged_query[hit] <- unname(short_names[cmp$abridged_query[hit]])
class(cmp) <- c("scopus_comparison", "data.frame")
# The series are labelled at their right-hand ends, so the x axis is expanded
# to leave room for the labels inside the panel and clipping is switched off.
pc <- suppressMessages(
  strip_chrome(plot_scopus_comparison(cmp)) +
    coord_cartesian(clip = "off") +
    scale_x_continuous(breaks = seq(2018, 2026, 2),
                       expand = expansion(mult = c(0.02, 0.46)))
)
audit(pc, "topic trends")
ggplot2::ggsave(file.path(OUT, "scopus_topic_trends.png"), pc,
                width = 7.5, height = 4.6, dpi = 300, bg = "white")
ggplot2::ggsave(file.path(OUT, "scopus_topic_trends.pdf"), pc,
                width = 7.5, height = 4.6, bg = "white", device = grDevices::cairo_pdf)

writeLines("redrew the Scopus figures (png and pdf) from the archived counts")
