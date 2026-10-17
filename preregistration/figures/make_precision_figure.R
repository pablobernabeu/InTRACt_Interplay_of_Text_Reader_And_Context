# InTRACt Stage 1: the design-analysis figure and its supplementary companion.
#
# Run from the preregistration directory, after run_design_analysis.R:
#   Rscript figures/make_precision_figure.R
# Reads design_analysis/precision_sweep.csv. Writes figures/fig_precision.{png,pdf}
# (Figure 3) and figures/fig_precision_supplement.{png,pdf}, the narration and
# within-child curves.
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

# Both figures are saved at this size, and each panel is half the width. In the
# journal, each half of a double-column figure occupies Nature's single-column
# width of 8.9 cm. The protocol embeds the figures at its full text width of
# 468 pt, which leaves each panel 8.26 cm. The text has to survive the narrower.
FIG_W_IN        <- 11
FIG_H_IN        <- 5
PANEL_RENDER_CM <- FIG_W_IN * 2.54 / 2
PANEL_PRINT_CM  <- min(8.9, 468 / 2 / 72 * 2.54)

# Five series distinguished by hue alone failed the greyscale check, so the figure
# carries two encodings instead of one: hue for which construct a coefficient
# belongs to, and line type for whether it is a main effect or its interaction
# with the age band. That leaves three hues to separate rather than five.
construct_of <- c(LexPC = "Lexical difficulty", SynPC = "Grammatical load",
                  CohPC = "Referential continuity",
                  SynPC_age = "Grammatical load", CohPC_age = "Referential continuity",
                  LexPC_narr = "Lexical difficulty",
                  accum = "Accumulated reading")
term_of <- c(LexPC = "Main effect", SynPC = "Main effect", CohPC = "Main effect",
             SynPC_age = "Interaction", CohPC_age = "Interaction",
             LexPC_narr = "Interaction",
             accum = "Main effect")

# The rows of one sweep. which() keeps a missing value in a filter column from
# selecting a row of NAs.
rows_of <- function(model, sweep, truth = NULL) {
  keep <- res$model == model & res$sweep == sweep
  if (!is.null(truth)) keep <- keep & res$truth == truth
  res[which(keep), , drop = FALSE]
}

# Each subtitle states the value a sweep holds fixed, so the CSV is checked to hold
# it there; a re-run at other settings would otherwise keep the old wording.
held_at <- function(d, col, value, what) {
  if (!all(d[[col]] == value) || anyNA(d[[col]]))
    stop("the ", what, " is labelled as holding ", col, " at ", value, " but the CSV has ",
         paste(sort(unique(d[[col]])), collapse = ", "), call. = FALSE)
  invisible(d)
}

# An empty panel composes into an unreadable figure rather than an error, and a
# coefficient missing from the lookups would be drawn in no series, so both are
# checked here where the mistake is still visible.
prep <- function(d, xcol, what) {
  if (!nrow(d)) stop("no rows for panel '", what, "'", call. = FALSE)
  if (anyNA(d[[xcol]])) stop("missing values on axis '", xcol, "' in panel '", what, "'",
                             call. = FALSE)
  unknown <- setdiff(d$param, names(construct_of))
  if (length(unknown)) stop("no series for ", paste(unknown, collapse = ", "), " in panel '",
                            what, "'", call. = FALSE)
  if (anyDuplicated(d[c("param", xcol)]))
    stop("more than one row per coefficient and grid point in panel '", what, "'",
         call. = FALSE)
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
# check_figure() rejected at 2.25:1 against a threshold of 3. The four series use
# Okabe-Ito blue (#0072b2) and vermilion (#d55e00), a near-black (#333333) in
# place of the set's green, and a dark magenta (#8e2c6b, not an Okabe-Ito colour,
# and its choice is not recorded) for accumulated reading. Every series clears
# the contrast floor, and the pair a deuteranope finds hardest is separated by
# lightness as well as by hue.
SERIES_COLOURS <- c("Lexical difficulty"     = "#0072b2",
                    "Grammatical load"       = "#d55e00",
                    "Referential continuity" = "#333333",
                    "Accumulated reading"    = "#8e2c6b")

curve_panel <- function(d, x_lab, subtitle) {
  d$construct <- droplevels(d$construct)
  d$term <- droplevels(d$term)
  ggplot(d, aes(x = x, y = power, colour = construct, fill = construct,
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
          legend.margin = margin(t = 0, b = 0)) +
    scale_x_log10()
}

# read.csv reads `truth` as a number. A value it could not read as one would
# otherwise drop out of the comparison below, so the conversion is checked.
truth <- suppressWarnings(as.numeric(res$truth))
if (any(is.na(truth) & !is.na(res$truth)))
  stop("precision_sweep.csv has non-numeric truth values: ",
       paste(unique(res$truth[is.na(truth) & !is.na(res$truth)]), collapse = ", "),
       call. = FALSE)
res$truth <- truth
# The sweeps at the alternative, every coefficient at twice the region's
# half-width; the null sweep has truth 0.
ALT <- 0.10

dev_texts <- prep(held_at(rows_of("developmental", "texts", ALT), "per_text", 12,
                          "texts sweep"), "texts", "texts sweep")
dev_read  <- prep(held_at(rows_of("developmental", "readings"), "texts", 250,
                          "readings sweep"), "per_text", "readings sweep")

pa <- curve_panel(dev_texts, "Distinct texts (log scale)",
                  "Twelve readings per text on average")
pb <- curve_panel(dev_read, "Readings per text (log scale)",
                  "250 distinct texts throughout")

# arrange_plots collects the guides into the patchwork's own theme, which would
# otherwise park them to the right of the panels. One horizontal strip along the
# bottom returns that width to the data.
fig <- arrange_plots(pa, pb, ncol = 2, nrow = 1, guides = "collect") &
  theme(legend.position = "bottom", legend.box = "horizontal")

# The narration and within-child curves go in the supplement, where they are read
# against the design effect for an unbalanced narration flag.
narr <- prep(rows_of("narration", "texts"), "texts", "narration")
t2   <- prep(held_at(rows_of("within_child", "children"), "per_child", 5, "within-child sweep"),
             "children", "within child")
ps_a <- curve_panel(narr, "Distinct texts (log scale)", "Narration model")
ps_b <- curve_panel(t2, "Children in tier 2 (log scale)",
                    "Within-child model, five distinct texts each")
sup <- arrange_plots(ps_a, ps_b, ncol = 2, nrow = 1, guides = "collect") &
  theme(legend.position = "bottom", legend.box = "horizontal")

# A figure destined for print is checked rather than eyeballed, at the two widths
# set at the top: the width each panel is drawn at and the width it is printed at.
# Text that is comfortable on screen can still reach the page below the six-point
# floor. Every panel is checked before either figure is saved, so a failure
# cannot leave one figure new and the other old.
audit_panel <- function(p, what) {
  chk <- check_figure(p, width_cm = PANEL_PRINT_CM, render_width_cm = PANEL_RENDER_CM)
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
audit_panel(ps_a, "supplement panel a")
audit_panel(ps_b, "supplement panel b")

# The manuscript embeds the PDF, where the type stays selectable text, and
# cairo_pdf embeds the fonts. Neither document uses the PNG. ggsave() draws a PNG
# with ragg only when ragg is installed and otherwise falls back to a device that
# rasterises text differently, so ragg is named here and the dependency is declared.
save_both <- function(p, name) {
  save_plot(file.path(OUT, paste0(name, ".png")), p, width = FIG_W_IN, height = FIG_H_IN,
            dpi = 300, device = ragg::agg_png)
  save_plot(file.path(OUT, paste0(name, ".pdf")), p, width = FIG_W_IN, height = FIG_H_IN,
            device = grDevices::cairo_pdf)
}
save_both(fig, "fig_precision")
save_both(sup, "fig_precision_supplement")

writeLines("wrote figures/fig_precision{,_supplement}.{png,pdf}")
