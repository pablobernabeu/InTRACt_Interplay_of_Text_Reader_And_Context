# InTRACt Stage 1: the evidence map in Supplementary Section S4.
#
# Run from the preregistration directory:
#   Rscript literature/make_evidence_figure.R
# Reads literature/evidence_map.csv, compiled by hand from the sources it names.
# Writes literature/evidence_map.{png,pdf}.
#
# The map sets side by side the pooled estimates and review conclusions closest to
# two conditions of this study's setting, paged reading on a touchscreen and narration
# that a family can switch off. Every outcome on it is comprehension, on which the
# confirmatory results will say nothing, so no registered decision depends on it.
#
# read_evidence(), the DIR palette, the rule that colours a point by its interval
# and the open and filled shapes come from poster/R/figures.R. That file is frozen
# (tools/frozen.txt), so they are copied into this script. The poster's layout in
# millimetres, its typeface and its link boxes are left behind.

suppressPackageStartupMessages({
  library(depictr)
  library(ggplot2)
})

IN  <- "literature/evidence_map.csv"
OUT <- "literature"

# The figure is drawn at the supplement's text width, US Letter less two margins of
# 2.54 cm, so the PDF is embedded at its own size. The same margins leave 15.9 cm
# on A4, and the audit uses the narrower of the two widths.
FIG_W_IN  <- 6.5
RENDER_CM <- FIG_W_IN * 2.54
PRINT_CM  <- min(RENDER_CM, 21 - 2 * 2.54)

# All text is set at 7.5 pt, which prints at 7.2 pt on A4.
TEXT_PT <- 7.5
MIN_PT  <- 6

# The map's three directions, as in poster/R/figures.R. Crimson against blue stays
# distinct under every common colour-vision deficiency, the grey is lighter than
# both so that greyscale keeps the three apart, and all three clear 4.5:1 against
# white for the text drawn in them (checked below).
DIR <- c(negative = "#a4133c", neutral = "#68737d", positive = "#0068a8")
INK <- "#16202b"

# A row is a two-line label and the gap below it, and the frame is the x axis, the
# gap between the groups and the margins. The axis runs further than the widest
# interval needs, so that a verdict centred on zero and the direction key fit.
ROW_MM     <- 8.5
FRAME_MM   <- 24
XLIM       <- c(-0.6, 0.8)
EXPAND     <- 0.55  # space above and below each group's rows, in rows
KEY_DY     <- 0.95  # the direction key sits this far above the first row
KEY_GAP    <- 0.02  # and this far either side of zero
VERDICT_DY <- 0.24  # the two parts of a verdict sit this far above and below its row
PAD_MM     <- 0.4   # the white backing around each part of a verdict
GAP_HALF_W <- 0.01  # half-width, in axis units, of the backing between a verdict's two parts

# One row per finding, grouped by the comparison it makes. A row with an estimate is
# a pooled effect, drawn as a point and its 95% interval. A row without one reports
# a finding that cannot share the axis (a review's conclusion, or a range of
# estimates), and its `verdict` is printed across the zero line, so it cannot be
# mistaken for an effect size. A verdict has one or two parts separated by
# semicolons, and `verdict_dir` gives each part's direction in the same order. Each
# row names the place in its source it was read from (`location`) and the copy of
# the source it was checked against (`checked_against`). The last check is the one
# addition to the poster's function.
read_evidence <- function(file = IN) {
  what <- basename(file)
  ev <- utils::read.csv(file, stringsAsFactors = FALSE, encoding = "UTF-8")
  need <- c("group", "label", "source", "estimate", "lo", "hi", "verdict", "verdict_dir",
            "bibkey", "location", "checked_against")
  if (!all(need %in% names(ev))) {
    stop(what, " lacks: ", paste(setdiff(need, names(ev)), collapse = ", "), call. = FALSE)
  }
  ev$verdict[is.na(ev$verdict)] <- ""
  ev$verdict_dir[is.na(ev$verdict_dir)] <- ""
  pooled <- !is.na(ev$estimate)
  if (any(is.na(ev$lo[pooled]) | is.na(ev$hi[pooled]))) {
    stop("a pooled row in ", what, " lacks its interval", call. = FALSE)
  }
  if (any(ev$lo[pooled] > ev$estimate[pooled] | ev$hi[pooled] < ev$estimate[pooled])) {
    stop("an estimate in ", what, " lies outside its own interval", call. = FALSE)
  }
  if (any(!pooled & !nzchar(ev$verdict))) {
    stop("a row of ", what, " has neither an estimate nor a verdict", call. = FALSE)
  }
  for (i in which(!pooled)) {
    parts <- strsplit(ev$verdict[i], ";", fixed = TRUE)[[1]]
    dirs  <- trimws(strsplit(ev$verdict_dir[i], ";", fixed = TRUE)[[1]])
    if (length(parts) != length(dirs) || !all(dirs %in% names(DIR))) {
      stop("row ", i, " of ", what, " does not give one direction (",
           paste(names(DIR), collapse = ", "), ") per part of its verdict", call. = FALSE)
    }
  }
  if (any(!nzchar(ev$location))) {
    stop("a row of ", what, " does not say where in its source it was read", call. = FALSE)
  }
  if (any(!nzchar(ev$checked_against))) {
    stop("a row of ", what, " does not say which copy of its source was checked",
         call. = FALSE)
  }
  ev
}

ev <- read_evidence()
ev$group <- factor(ev$group, levels = unique(ev$group))
if (is.unsorted(as.integer(ev$group))) {
  stop("the rows of each group in ", IN, " must be contiguous", call. = FALSE)
}
# Rows run top to bottom in file order, numbered across the whole figure, so that
# each break of the y axis, and so each label, belongs to one row of one group.
ev$y <- -seq_len(nrow(ev))
ev$axis_label <- paste(ev$label, ev$source, sep = "\n")

# Each pooled effect takes the colour of its direction: crimson where the interval
# lies below zero, blue where it lies above, grey where it includes zero. The grey
# point is also open, so the null rows stand apart in greyscale and to readers who
# cannot separate the hues.
pooled <- ev[!is.na(ev$estimate), ]
pooled$direction <- factor(ifelse(pooled$hi < 0, "negative",
                                  ifelse(pooled$lo > 0, "positive", "neutral")),
                           levels = names(DIR))

# A verdict is centred on the zero line, one part to a line, each part in its
# direction's colour and on a white backing so that the zero line does not run
# through its words.
told <- ev[is.na(ev$estimate), ]
parts <- do.call(rbind, lapply(seq_len(nrow(told)), function(i) {
  txt  <- trimws(strsplit(told$verdict[i], ";", fixed = TRUE)[[1]])
  dirs <- trimws(strsplit(told$verdict_dir[i], ";", fixed = TRUE)[[1]])
  if (length(txt) > 2) {
    stop("the verdict '", told$verdict[i], "' has more than two parts", call. = FALSE)
  }
  dy <- if (length(txt) == 2) c(VERDICT_DY, -VERDICT_DY) else 0
  data.frame(group = told$group[i], y = told$y[i] + dy, label = txt,
             direction = factor(dirs, levels = names(DIR)))
}))
if (is.null(parts)) {
  parts <- data.frame(group = ev$group[0], y = numeric(0), label = character(0),
                      direction = factor(character(0), levels = names(DIR)))
}
# Each part's backing stops at its own text, so the zero line would still show in the
# gap between the two parts of a verdict and seem, at print size, to run through the
# words. A narrow white band over the zero line fills that gap.
two_part <- grepl(";", told$verdict, fixed = TRUE)
gaps <- data.frame(group = told$group[two_part],
                   ymin = told$y[two_part] - VERDICT_DY, ymax = told$y[two_part] + VERDICT_DY)

# The direction labels above the first group double as the key to the colours.
key <- data.frame(
  group = factor(levels(ev$group)[1], levels = levels(ev$group)),
  x = c(-KEY_GAP, KEY_GAP),
  y = max(ev$y) + KEY_DY,
  label = c("← better on paper\nor without audio", "better on screen →\nor with audio"),
  hjust = c(1, 0),
  direction = factor(c("negative", "positive"), levels = names(DIR))
)

# Axis labels take a true minus sign (U+2212).
signed <- function(x) sub("^-", "−", format(x, trim = TRUE, drop0trailing = TRUE))

p <- ggplot(ev, aes(y = y)) +
  geom_blank(aes(x = 0)) +
  geom_vline(xintercept = 0, colour = "grey45", linewidth = 0.4) +
  geom_rect(data = gaps, aes(xmin = -GAP_HALF_W, xmax = GAP_HALF_W, ymin = ymin, ymax = ymax),
            fill = "white", colour = NA, inherit.aes = FALSE) +
  geom_segment(data = pooled, aes(x = lo, xend = hi, yend = y, colour = direction),
               linewidth = 0.6) +
  geom_point(data = pooled, aes(x = estimate, colour = direction, shape = direction),
             size = 2, stroke = 0.7, fill = "white") +
  geom_label(data = parts, aes(x = 0, label = label, colour = direction),
             fontface = "italic", size = TEXT_PT / .pt, fill = "white", linewidth = 0,
             label.padding = unit(PAD_MM, "mm")) +
  geom_text(data = key, aes(x = x, label = label, colour = direction, hjust = hjust),
            size = TEXT_PT / .pt, lineheight = 0.9) +
  facet_grid(group ~ ., scales = "free_y", space = "free_y", switch = "y",
             labeller = labeller(group = label_wrap_gen(width = 22))) +
  scale_colour_manual(values = DIR, guide = "none") +
  scale_shape_manual(values = c(negative = 16, neutral = 21, positive = 16), guide = "none") +
  scale_x_continuous(limits = XLIM, breaks = seq(-0.4, 0.6, 0.2), labels = signed,
                     expand = expansion(0)) +
  scale_y_continuous(breaks = ev$y,
                     labels = function(b) ev$axis_label[match(round(b), ev$y)],
                     expand = expansion(add = EXPAND)) +
  labs(x = "Standardised mean difference with 95% CI", y = NULL) +
  theme_depictr(base_size = 9, grid = "x") +
  theme(
    axis.text.y = element_text(size = TEXT_PT, colour = INK, hjust = 1, lineheight = 0.9),
    axis.text.x = element_text(size = TEXT_PT, colour = INK),
    axis.title.x = element_text(size = TEXT_PT, colour = INK),
    axis.ticks.y = element_blank(),
    strip.placement = "outside",
    strip.text.y.left = element_text(size = TEXT_PT, colour = INK, face = "bold", angle = 90),
    panel.spacing.y = unit(3, "mm"),
    plot.margin = margin(4, 8, 4, 2)
  )

# The height follows the rows, so a longer file makes a taller figure and every row
# keeps its height. With space = "free_y", each group's panel is as tall as the span
# of its rows plus the expansion above and below.
ys <- rbind(ev[c("group", "y")], parts[c("group", "y")], key[c("group", "y")])
span <- tapply(ys$y, ys$group, function(v) diff(range(v))) + 2 * EXPAND
FIG_H_IN <- (sum(span) * ROW_MM + FRAME_MM) / 25.4

text_mm <- function(x, italic = FALSE) {
  systemfonts::string_width(x, family = "sans", size = TEXT_PT, res = 72,
                            italic = italic) * 25.4 / 72
}

# check_figure() lays the figure out on the current device, and with none open R
# would open its default PDF device and leave Rplots.pdf behind. A throwaway ragg
# device of the figure's size measures text as the saved PNG does. The panel's
# width and the height of one row are read from the same layout, in millimetres.
audit <- function(p) {
  tmp <- tempfile(fileext = ".png")
  ragg::agg_png(tmp, width = FIG_W_IN, height = FIG_H_IN, units = "in", res = 72)
  on.exit({
    grDevices::dev.off()
    unlink(tmp)
  }, add = TRUE)
  chk <- check_figure(p, width_cm = PRINT_CM, render_width_cm = RENDER_CM)
  gt <- ggplot_gtable(ggplot_build(p))
  panel <- gt$layout[grepl("^panel", gt$layout$name), ]
  cols <- unique(panel$l)
  rows <- unique(panel$t)
  fixed_w <- sum(grid::convertWidth(gt$widths[-cols], "mm", valueOnly = TRUE))
  fixed_h <- sum(grid::convertHeight(gt$heights[-rows], "mm", valueOnly = TRUE))
  list(chk = chk,
       mm_per_x = (FIG_W_IN * 25.4 - fixed_w) / diff(XLIM),
       mm_per_y = (FIG_H_IN * 25.4 - fixed_h) / sum(as.numeric(gt$heights[rows])))
}
m <- audit(p)
print(m$chk)
failed <- m$chk[m$chk$verdict == "fail", , drop = FALSE]
if (nrow(failed)) {
  print(failed)
  stop("figure check failed for the evidence map: ", paste(failed$check, collapse = ", "),
       call. = FALSE)
}

# check_figure() reads only the text outside the panel: the row labels, the group
# strips and the axis. The verdicts and the key are drawn inside it, so their size
# at the print width and their contrast against white are checked here, as is
# their fit beside zero and between the rows.
contrast_on_white <- function(hex) {
  rgb <- grDevices::col2rgb(hex) / 255
  lin <- ifelse(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055)^2.4)
  1.05 / (colSums(lin * c(0.2126, 0.7152, 0.0722)) + 0.05)
}
if (TEXT_PT * PRINT_CM / RENDER_CM < MIN_PT) {
  stop("text inside the panel would print below ", MIN_PT, " pt", call. = FALSE)
}
if (any(contrast_on_white(DIR) < 4.5)) {
  stop("a direction colour is below 4.5:1 against white", call. = FALSE)
}
half <- text_mm(parts$label, italic = TRUE) / 2 + PAD_MM
if (any(half > -XLIM[1] * m$mm_per_x | half > XLIM[2] * m$mm_per_x)) {
  stop("a verdict is too wide to centre on zero, so widen XLIM or shorten it", call. = FALSE)
}
key_lines <- strsplit(key$label, "\n", fixed = TRUE)
if (max(text_mm(key_lines[[1]])) > (-KEY_GAP - XLIM[1]) * m$mm_per_x ||
      max(text_mm(key_lines[[2]])) > (XLIM[2] - KEY_GAP) * m$mm_per_x) {
  stop("the direction key does not fit beside zero", call. = FALSE)
}
if (2 * VERDICT_DY * m$mm_per_y < TEXT_PT * 25.4 / 72 + 2 * PAD_MM) {
  stop("the two parts of a verdict would overlap, so raise VERDICT_DY or ROW_MM",
       call. = FALSE)
}

# The supplement embeds the PDF, where the type stays selectable text, and
# cairo_pdf embeds the fonts. The PNG is drawn with ragg, named here because
# ggsave() falls back to a device that rasterises text differently without it.
save_plot(file.path(OUT, "evidence_map.png"), p, width = FIG_W_IN, height = FIG_H_IN,
          dpi = 300, device = ragg::agg_png)
save_plot(file.path(OUT, "evidence_map.pdf"), p, width = FIG_W_IN, height = FIG_H_IN,
          device = grDevices::cairo_pdf)

writeLines("wrote literature/evidence_map.{png,pdf}")
