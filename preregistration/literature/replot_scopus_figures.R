# InTRACt Stage 1: redraw the two Scopus figures from the archived counts.
#
# scopus_gap_analysis.R queries the API and archives its counts as CSV files.
# This script redraws the figures from those archives, so presentation can be
# revised without issuing a single new request or moving the recorded numbers.
#   Rscript literature/replot_scopus_figures.R
#
# The PDF is the copy the manuscript embeds, so that figure text remains text.

library(scopusflow)
OUT <- "literature"

ints <- utils::read.csv(file.path(OUT, "scopus_gap_sizes.csv"),
                        stringsAsFactors = FALSE, check.names = FALSE)
class(ints) <- c("scopus_intersections", "data.frame")
p <- plot_scopus_intersections(ints)
ggplot2::ggsave(file.path(OUT, "scopus_gap_intersections.png"), p,
                width = 7.5, height = 4.6, dpi = 300, bg = "white")
ggplot2::ggsave(file.path(OUT, "scopus_gap_intersections.pdf"), p,
                width = 7.5, height = 4.6, bg = "white", device = grDevices::cairo_pdf)

cmp <- utils::read.csv(file.path(OUT, "scopus_topic_trends.csv"),
                       stringsAsFactors = FALSE, check.names = FALSE)
class(cmp) <- c("scopus_comparison", "data.frame")
pc <- plot_scopus_comparison(cmp)
ggplot2::ggsave(file.path(OUT, "scopus_topic_trends.png"), pc,
                width = 7.5, height = 4.6, dpi = 300, bg = "white")
ggplot2::ggsave(file.path(OUT, "scopus_topic_trends.pdf"), pc,
                width = 7.5, height = 4.6, bg = "white", device = grDevices::cairo_pdf)

writeLines("redrew the Scopus figures (png and pdf) from the archived counts")
