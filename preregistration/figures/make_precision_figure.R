# InTRACt Stage 1: the design-analysis figure.
#
# Run from the preregistration directory, after run_design_analysis.R:
#   Rscript figures/make_precision_figure.R
#
# Two panels answering two different questions. The left panel varies the number
# of distinct texts, which is what the text coefficients are identified from and
# what the data controller has not yet settled. The right panel varies readings
# per text at a fixed number of texts, which is the kind of data this platform
# produces most readily. Putting them side by side is the point of the figure:
# the design is short of one of these and not the other.

suppressPackageStartupMessages({
  library(depictr)
  library(ggplot2)
})

OUT <- "figures"
res <- utils::read.csv("design_analysis/precision_sweep.csv", stringsAsFactors = FALSE)

# Five series distinguished by hue alone failed the greyscale check, so the figure
# carries two encodings instead of one: hue for which construct a coefficient
# belongs to, and line type for whether it is a main effect or its interaction
# with the age band. That leaves three hues to separate rather than five.
construct_of <- c(LexPC = "Lexical difficulty", SynPC = "Grammatical load",
                  CohPC = "Referential continuity",
                  SynPC_age = "Grammatical load", CohPC_age = "Referential continuity",
                  LexPC_narr = "Lexical difficulty", CohPC_narr = "Referential continuity",
                  accum = "Accumulated reading")
term_of <- c(LexPC = "Main effect", SynPC = "Main effect", CohPC = "Main effect",
             SynPC_age = "Interaction", CohPC_age = "Interaction",
             LexPC_narr = "Interaction", CohPC_narr = "Interaction",
             accum = "Main effect")

# An empty panel composes into an unreadable figure rather than an error, so the
# subset is checked here where the mistake is still visible.
prep <- function(d, xcol, what) {
  d <- d[!is.na(d[[xcol]]), ]
  if (!nrow(d)) stop("no rows for panel '", what, "' on axis '", xcol, "'", call. = FALSE)
  data.frame(
    x         = d[[xcol]],
    power     = d$p_meaningful,
    lower     = d$p_meaningful_lo,
    upper     = d$p_meaningful_hi,
    construct = factor(unname(construct_of[d$param]),
                       levels = c("Lexical difficulty", "Grammatical load",
                                  "Referential continuity", "Accumulated reading")),
    term      = factor(unname(term_of[d$param]), levels = c("Main effect", "Interaction")),
    stringsAsFactors = FALSE
  )
}

BASE_SIZE <- 14

# The package's default qualitative palette put a light orange on white, which
# check_figure() rejected at 2.25:1 against a threshold of 3. These three are
# taken from the Okabe-Ito set with the light green swapped for a near-black, so
# every series clears the contrast floor and the pair a deuteranope finds hardest
# is separated by lightness as well as by hue.
SERIES_COLOURS <- c("Lexical difficulty"     = "#0072b2",
                    "Grammatical load"       = "#d55e00",
                    "Referential continuity" = "#333333",
                    "Accumulated reading"    = "#8e2c6b")

curve_panel <- function(d, x_lab, subtitle, log_x = TRUE) {
  d$construct <- droplevels(d$construct)
  d$term <- droplevels(d$term)
  p <- ggplot(d, aes(x = x, y = power, colour = construct, fill = construct,
                     linetype = term, shape = term)) +
    geom_hline(yintercept = 0.90, linetype = "dashed", linewidth = 0.5,
               colour = "grey40") +
    geom_ribbon(aes(ymin = lower, ymax = upper, group = interaction(construct, term)),
                alpha = 0.12, colour = NA, show.legend = FALSE) +
    geom_line(linewidth = 0.8) +
    geom_point(size = 2.2, fill = "white", stroke = 0.8) +
    scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25)) +
    scale_shape_manual(values = c("Main effect" = 21, "Interaction" = 24)) +
    scale_linetype_manual(values = c("Main effect" = "solid", "Interaction" = "22")) +
    scale_colour_manual(values = SERIES_COLOURS) +
    scale_fill_manual(values = SERIES_COLOURS) +
    labs(x = x_lab, y = "Probability of a determinate verdict",
         subtitle = subtitle, colour = NULL, fill = NULL,
         linetype = NULL, shape = NULL) +
    theme_depictr(base_size = BASE_SIZE) +
    theme(legend.position = "bottom", legend.box = "horizontal",
          legend.margin = margin(t = 0, b = 0))
  if (log_x) p <- p + scale_x_log10() else p
  p
}

# `truth` is written as a number, so it is compared as one: a string comparison
# silently selects nothing and composes an empty panel.
res$truth <- suppressWarnings(as.numeric(res$truth))
ALT <- 0.10

dev_texts <- prep(res[res$model == "developmental" & res$sweep == "texts" &
                        res$truth == ALT, ], "texts", "texts sweep")
dev_read  <- prep(res[res$model == "developmental" & res$sweep == "readings", ],
                  "per_text", "readings sweep")

pa <- curve_panel(dev_texts, "Distinct texts (log scale)",
                  "Twelve readings of each text")
pb <- curve_panel(dev_read, "Readings per text (log scale)",
                  "250 distinct texts throughout")

# arrange_plots collects the guides into the patchwork's own theme, which would
# otherwise park them to the right of the panels. One horizontal strip along the
# bottom returns that width to the data.
fig <- arrange_plots(pa, pb, ncol = 2, nrow = 1, guides = "collect") &
  theme(legend.position = "bottom", legend.box = "horizontal")

# A figure destined for print is checked rather than eyeballed. The composed
# figure is saved 11 inches wide, so each panel is drawn at 13.97 cm and will be
# printed at about 8.9 cm as half of a double-column figure. Those are the two
# widths the check needs: text that is comfortable on screen can still reach the
# page below the six-point floor.
audit_panel <- function(p, what) {
  chk <- check_figure(p, width_cm = 8.9, render_width_cm = 13.97)
  print(chk)
  failed <- chk[chk$verdict == "fail", , drop = FALSE]
  if (nrow(failed)) {
    print(failed)
    stop("figure check failed for ", what, ": ",
         paste(failed$check, collapse = ", "), call. = FALSE)
  }
  invisible(chk)
}
audit_panel(pa, "main panel a")
audit_panel(pb, "main panel b")

# The manuscript embeds the PDF, where the type stays selectable text; the PNG
# serves the repository preview. cairo_pdf embeds the fonts.
save_plot(file.path(OUT, "fig_precision.png"), fig, width = 11, height = 5, dpi = 300)
save_plot(file.path(OUT, "fig_precision.pdf"), fig, width = 11, height = 5,
          device = grDevices::cairo_pdf)

# The narration and within-child curves go in the supplement, where they are read
# against the design effect for an unbalanced narration flag.
narr <- prep(res[res$model == "narration", ], "texts", "narration")
t2   <- prep(res[res$model == "within_child", ], "children", "within child")
ps_a <- curve_panel(narr, "Distinct texts (log scale)", "Narration model")
ps_b <- curve_panel(t2, "Children in tier 2 (log scale)", "Within-child model, five readings each")
audit_panel(ps_a, "supplement panel a")
audit_panel(ps_b, "supplement panel b")
sup <- arrange_plots(ps_a, ps_b, ncol = 2, nrow = 1, guides = "collect") &
  theme(legend.position = "bottom", legend.box = "horizontal")
save_plot(file.path(OUT, "fig_precision_supplement.png"), sup, width = 11, height = 5, dpi = 300)
save_plot(file.path(OUT, "fig_precision_supplement.pdf"), sup, width = 11, height = 5,
          device = grDevices::cairo_pdf)

writeLines("wrote figures/fig_precision{,_supplement}.{png,pdf}")
