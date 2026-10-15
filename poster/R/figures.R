# InTRACt poster: every figure on the poster, built from archived data.
#
# poster.qmd sources this file and calls build_figures(), which writes one SVG
# per figure into figures/. Each figure is drawn at the size it is printed, so a
# point size here is a point size on the A1 sheet, and depictr::check_figure()
# audits it at that size before it is written. Nothing here issues a network
# request: the Scopus counts come from R/scopus_counts.R, the precision curves
# from a copy of the protocol's design-analysis outputs, and the pooled effects
# from data/evidence.csv, each row of which names the page or table it came from.

suppressPackageStartupMessages({
  library(ggplot2)
  library(patchwork)
})

# The protocol's design-analysis outputs, copied from
# ../preregistration/design_analysis/ on 15 October 2026, so that the poster
# builds on a branch that lacks the protocol's latest files. Copy them again if
# the design analysis is re-run.
DESIGN_DIR <- "data/design_analysis"

# The palette is the poster's theme: Oxford blue, and the green of the
# department's tree (#1dad89), darkened in the same hue to clear 4.5:1 against
# white wherever it carries text or data. The third text property keeps the
# Okabe-Ito blue, and the fourth the neutral dark of the protocol's figures.
PAL <- c(
  ox_blue = "#002147", ox_mid = "#0b3a6f", ink = "#16202b", ink_soft = "#4a5966",
  ink_faint = "#7f8a95", grid = "#e3e8ee", paper = "#ffffff",
  lexical = "#0072b2", grammatical = "#127b61", continuity = "#3f4a55",
  accent = "#127b61"
)

# The evidence map's three directions. Crimson against blue stays distinct under
# every common colour-vision deficiency, the grey is lighter than both so that
# greyscale keeps the three apart, and all three clear 4.5:1 against white for
# the text drawn in them.
DIR <- c(negative = "#a4133c", neutral = "#68737d", positive = "#0068a8")

# Figtree (SIL Open Font License) stands in for Abadi, which is licensed for
# Microsoft 365 apps only and so cannot travel with the source.
FONT <- "Figtree"
FONT_DIR <- "fonts"

# svglite measures text with systemfonts, and Typst draws it from the same files
# through the poster's font-paths, so the two agree on every width. systemfonts
# (1.3.2 here) already lists the files in a ./fonts folder of the working
# directory, so the family is registered by hand only where it has not done so.
register_poster_fonts <- function(dir = FONT_DIR) {
  if (FONT %in% systemfonts::system_fonts()$family) return(invisible(TRUE))
  f <- function(x) normalizePath(file.path(dir, x), mustWork = TRUE)
  systemfonts::register_font(
    FONT,
    plain = f("Figtree-Regular.ttf"), bold = f("Figtree-Bold.ttf"),
    italic = f("Figtree-Italic.ttf"), bolditalic = f("Figtree-BoldItalic.ttf"))
  invisible(TRUE)
}

# Text sizes on an A1 sheet read at one to two metres. Body text on the poster is
# 26 pt; nothing in a figure is drawn below 22 pt.
BASE_PT <- 26
MIN_PT  <- 22
pt_mm   <- function(pt) pt / ggplot2::.pt  # geom_text() sizes are in mm

# Width of a label as drawn, in mm, so a label column can be sized to its
# longest entry instead of to a guess. `widest = FALSE` returns every width.
text_mm <- function(x, pt, bold = FALSE, italic = FALSE, widest = TRUE) {
  w <- systemfonts::string_width(x, family = FONT, size = pt, res = 72, italic = italic,
                                 weight = if (bold) "bold" else "normal") * 25.4 / 72
  if (widest) max(w) else w
}

# Typographic marks in figure text, which Typst sets for the body but R does
# not: a curly apostrophe for a straight one, and a minus sign on axis labels.
curly <- function(x) gsub("'", "’", x, fixed = TRUE)
signed <- function(x) sub("^-", "−", format(x, trim = TRUE, drop0trailing = TRUE))

theme_poster <- function(base_size = BASE_PT) {
  theme_minimal(base_size = base_size, base_family = FONT) +
    theme(
      text = element_text(colour = PAL[["ink"]]),
      axis.text = element_text(colour = PAL[["ink_soft"]], size = rel(0.87)),
      axis.title = element_text(colour = PAL[["ink_soft"]], size = rel(0.87)),
      plot.title = element_text(face = "bold", size = rel(1), colour = PAL[["ox_blue"]],
                                margin = margin(b = 4)),
      plot.title.position = "plot",
      plot.subtitle = element_text(colour = PAL[["ink_soft"]], size = rel(0.87),
                                   margin = margin(b = 8)),
      panel.grid.minor = element_blank(),
      panel.grid.major = element_line(colour = PAL[["grid"]], linewidth = 0.5),
      legend.position = "none",
      legend.text = element_text(colour = PAL[["ink"]], size = rel(0.87)),
      legend.key.width = unit(14, "mm"),
      legend.background = element_rect(fill = PAL[["paper"]], colour = NA),
      plot.background = element_rect(fill = PAL[["paper"]], colour = NA),
      plot.margin = margin(4, 6, 4, 4)
    )
}

# A figure that fails the audit is not written. The check measures the smallest
# text, colour separability with and without simulated colour-vision deficiency,
# greyscale separability and contrast, at the width the figure is printed.
audit <- function(p, width_mm, what) {
  # check_figure() builds the plot on the current device. Without one, R opens
  # its default PDF device, whose PostScript font table knows nothing of the
  # poster's typeface, so a throwaway ragg device (which reads fonts through
  # systemfonts, as svglite does) is opened for the duration of the check.
  tmp <- tempfile(fileext = ".png")
  ragg::agg_png(tmp, width = width_mm, height = 100, units = "mm", res = 72)
  on.exit({ grDevices::dev.off(); unlink(tmp) }, add = TRUE)
  chk <- depictr::check_figure(p, width_cm = width_mm / 10, render_width_cm = width_mm / 10,
                               min_text_pt = MIN_PT)
  bad <- chk[chk$verdict == "fail", , drop = FALSE]
  if (nrow(bad)) {
    print(bad)
    stop("figure check failed for ", what, ": ", paste(bad$check, collapse = ", "),
         call. = FALSE)
  }
  invisible(chk)
}

save_svg <- function(p, file, width_mm, height_mm) {
  # Build the figure, audits included, before the SVG device opens: R evaluates
  # arguments lazily, and an audit that opens and closes a device of its own
  # while this one is current leaves the SVG empty.
  force(p)
  svglite::svglite(file, width = width_mm / 25.4, height = height_mm / 25.4,
                   bg = PAL[["paper"]], fix_text_size = FALSE)
  on.exit(grDevices::dev.off())
  print(p)
  invisible(file)
}

# ---------------------------------------------------------------------------
# What meta-analyses report about screens and add-ons (data/evidence.csv)
# ---------------------------------------------------------------------------

# One row per finding, grouped by the comparison it makes. A row with an
# estimate is a pooled effect, drawn as a point and its 95% interval. A row
# without one reports a finding that cannot share the g/d axis (a review's
# conclusion, or a correlation), and its `verdict` is printed across the zero
# line, so it cannot be mistaken for an effect size. A verdict has one or more
# parts separated by semicolons, and `verdict_dir` gives each part's direction
# in the same order. Each row carries its source and the place in the source it
# was read from; the figure prints nothing that is not in the file.
read_evidence <- function(file = "data/evidence.csv") {
  ev <- utils::read.csv(file, stringsAsFactors = FALSE, encoding = "UTF-8")
  need <- c("group", "label", "source", "estimate", "lo", "hi", "verdict", "verdict_dir",
            "bibkey", "location")
  if (!all(need %in% names(ev))) stop("evidence.csv lacks: ",
                                      paste(setdiff(need, names(ev)), collapse = ", "))
  ev$verdict[is.na(ev$verdict)] <- ""
  ev$verdict_dir[is.na(ev$verdict_dir)] <- ""
  pooled <- !is.na(ev$estimate)
  if (any(is.na(ev$lo[pooled]) | is.na(ev$hi[pooled])))
    stop("a pooled row in evidence.csv lacks its interval", call. = FALSE)
  if (any(ev$lo[pooled] > ev$estimate[pooled] | ev$hi[pooled] < ev$estimate[pooled]))
    stop("an estimate in evidence.csv lies outside its own interval", call. = FALSE)
  if (any(!pooled & !nzchar(ev$verdict)))
    stop("a row of evidence.csv has neither an estimate nor a verdict", call. = FALSE)
  for (i in which(!pooled)) {
    parts <- strsplit(ev$verdict[i], ";", fixed = TRUE)[[1]]
    dirs  <- trimws(strsplit(ev$verdict_dir[i], ";", fixed = TRUE)[[1]])
    if (length(parts) != length(dirs) || !all(dirs %in% names(DIR)))
      stop("row ", i, " of evidence.csv does not give one direction (",
           paste(names(DIR), collapse = ", "), ") per part of its verdict", call. = FALSE)
  }
  if (any(!nzchar(ev$location)))
    stop("a row of evidence.csv does not say where in its source it was read",
         call. = FALSE)
  ev
}

# Rows and group headings take fixed heights in mm, so the figure grows with the
# file instead of squeezing its rows; poster.qmd asks for this height.
EV_ROW_MM <- 16; EV_HEAD_MM <- 19; EV_FRAME_MM <- 39
evidence_height_mm <- function(file = "data/evidence.csv") {
  ev <- read_evidence(file)
  EV_FRAME_MM + EV_ROW_MM * nrow(ev) + EV_HEAD_MM * length(unique(ev$group))
}

fig_evidence <- function(width_mm, height_mm, file = "data/evidence.csv") {
  ev <- read_evidence(file)
  for (v in c("group", "label", "source", "verdict")) ev[[v]] <- curly(ev[[v]])

  # Rows run top to bottom in file order, with a heading above each group. The
  # label and its source form a column of their own inside the panel, left of
  # the intervals, sized to the longest entry; the intervals share one axis.
  # A heading keeps its group's rows close below it and the previous group's
  # rows further above, so each heading reads as the start of what follows.
  groups <- unique(ev$group)
  ROW <- 1.08; HEAD <- ROW * EV_HEAD_MM / EV_ROW_MM
  LAB_DY <- 0.22; SRC_DY <- -0.27         # a row's label and citation, about its line
  y <- 0; ev$y <- NA_real_; heads <- data.frame(group = groups, y = NA_real_)
  for (g in groups) {
    y <- y + HEAD; heads$y[heads$group == g] <- -(y + ROW) + 0.95
    for (i in which(ev$group == g)) { y <- y + ROW; ev$y[i] <- -y }
  }

  # Each pooled effect takes the colour of its direction: crimson where the
  # interval lies below zero, blue where it lies above, grey where it includes
  # zero. The grey point is also open, so the null rows stand apart in
  # greyscale and to readers who cannot separate the hues.
  pooled <- ev[!is.na(ev$estimate), ]
  pooled$direction <- factor(ifelse(pooled$hi < 0, "negative",
                                    ifelse(pooled$lo > 0, "positive", "neutral")),
                             levels = names(DIR))

  # The axis runs further left than the lowest interval needs, so that a verdict
  # centred on zero clears the label column.
  xr <- c(-0.7, 0.75)
  # The group headings have rows of their own, so they may run past the label
  # column; only the labels and sources set its width.
  lab_mm <- max(text_mm(ev$label, MIN_PT + 1), text_mm(ev$source, MIN_PT)) + 6
  panel_mm <- width_mm - 8
  if (text_mm(groups, MIN_PT + 3, bold = TRUE) > panel_mm)
    stop("a group heading in evidence.csv is wider than the panel", call. = FALSE)
  xlab_end <- xr[1] - 0.02
  xmin <- xr[1] - diff(xr) * lab_mm / (panel_mm - lab_mm)
  per_mm <- diff(xr) / (panel_mm - lab_mm)          # data units per printed mm
  top <- max(heads$y) + 0.75
  bottom <- min(ev$y) - 0.55

  # A verdict is set as a run of parts, each in its direction's colour, centred
  # on the zero line. The parts are placed from their measured widths, and each
  # sits on a white label so that the zero line does not run through its words.
  told <- ev[is.na(ev$estimate), ]
  parts <- do.call(rbind, lapply(seq_len(nrow(told)), function(i) {
    txt  <- trimws(strsplit(told$verdict[i], ";", fixed = TRUE)[[1]])
    dirs <- trimws(strsplit(told$verdict_dir[i], ";", fixed = TRUE)[[1]])
    txt  <- paste0(txt, ifelse(seq_along(txt) < length(txt), ";", ""))
    w    <- text_mm(txt, MIN_PT, italic = TRUE, widest = FALSE)
    # A word space and a little more between the parts' words. Each part's text
    # starts 0.8 mm inside its white label, which may overlap its neighbour's.
    gap  <- text_mm(" ", MIN_PT, italic = TRUE) + 0.4
    total <- sum(w) + gap * (length(w) - 1)
    if (total / 2 > (0 - xr[1]) / per_mm - 2)
      stop("the verdict '", told$verdict[i], "' is too wide to centre on zero",
           call. = FALSE)
    left <- -total / 2 + c(0, cumsum(w + gap))[seq_along(w)]
    data.frame(y = told$y[i], x = left * per_mm, label = txt,
               direction = factor(dirs, levels = names(DIR)))
  }))

  p <- ggplot(ev, aes(y = y)) +
    annotate("rect", xmin = xr[1], xmax = 0, ymin = bottom, ymax = top - 0.38,
             fill = PAL[["grid"]], alpha = 0.45) +
    geom_vline(xintercept = 0, colour = PAL[["ink_soft"]], linewidth = 0.8) +
    geom_segment(data = pooled, aes(x = lo, xend = hi, yend = y, colour = direction),
                 linewidth = 1.8) +
    geom_point(data = pooled, aes(x = estimate, colour = direction, shape = direction),
               size = 6, stroke = 1.8, fill = PAL[["paper"]]) +
    geom_label(data = parts, aes(x = x, y = y, label = label, colour = direction),
               hjust = 0, family = FONT, fontface = "italic", size = pt_mm(MIN_PT),
               fill = PAL[["paper"]], linewidth = 0, label.padding = unit(0.8, "mm")) +
    geom_text(aes(x = xlab_end, y = y + LAB_DY, label = label), hjust = 1, family = FONT,
              size = pt_mm(MIN_PT + 1), colour = PAL[["ink"]]) +
    # The citation line is set lighter than the finding it credits, at 3.5:1
    # against white, which clears the 3:1 that text of this size needs.
    geom_text(aes(x = xlab_end, y = y + SRC_DY, label = source), hjust = 1, family = FONT,
              size = pt_mm(MIN_PT), colour = PAL[["ink_faint"]]) +
    geom_text(data = heads, aes(x = xmin + 0.005, y = y, label = group), hjust = 0,
              family = FONT, size = pt_mm(MIN_PT + 3), fontface = "bold",
              colour = PAL[["ox_blue"]]) +
    # The direction labels double as the key to the colours. Each takes two lines,
    # because the space right of zero is narrower than one line of the key.
    annotate("text", x = -0.015, y = top + 0.15, label = "← favours paper\nor no add-on",
             hjust = 1, family = FONT, size = pt_mm(MIN_PT), colour = DIR[["negative"]],
             lineheight = 0.95) +
    annotate("text", x = 0.015, y = top + 0.15, label = "favours the screen\nor add-on →",
             hjust = 0, family = FONT, size = pt_mm(MIN_PT), colour = DIR[["positive"]],
             lineheight = 0.95) +
    scale_colour_manual(values = DIR, guide = "none") +
    scale_shape_manual(values = c(negative = 16, neutral = 21, positive = 16), guide = "none") +
    scale_x_continuous(breaks = c(-0.4, -0.2, 0, 0.2, 0.4, 0.6), labels = signed,
                       expand = expansion(add = 0)) +
    scale_y_continuous(limits = c(bottom, top + 0.75), expand = expansion(add = 0)) +
    coord_cartesian(xlim = c(xmin, xr[2]), clip = "off") +
    labs(x = "Pooled effect in standard deviations (g or d), with 95% interval", y = NULL) +
    theme_poster() +
    # The coloured direction labels above the panel are the key, which keeps a
    # legend from sitting over the lowest intervals.
    theme(axis.text.y = element_blank(), panel.grid.major.y = element_blank())
  audit(p, width_mm, "evidence map")

  # A link box over each row's label and citation, which the poster lays over
  # the printed figure to open the source's DOI.
  url <- bib_urls()[ev$bibkey]
  if (anyNA(url)) stop("references.bib gives no DOI or URL for ",
                       paste(unique(ev$bibkey[is.na(url)]), collapse = ", "), call. = FALSE)
  pm <- panel_mm(p, width_mm, height_mm)
  xlim <- c(xmin, xr[2]); ylim <- c(bottom, top + 0.75)
  x_mm <- function(x) pm$left + (x - xlim[1]) / diff(xlim) * pm$width
  y_mm <- function(y) pm$top + (ylim[2] - y) / diff(ylim) * pm$height
  w <- pmax(text_mm(ev$label, MIN_PT + 1, widest = FALSE),
            text_mm(ev$source, MIN_PT, widest = FALSE))
  half_line <- 0.5 * (MIN_PT + 1) * 25.4 / 72
  y0 <- y_mm(ev$y + LAB_DY) - half_line
  y1 <- y_mm(ev$y + SRC_DY) + half_line
  links <- data.frame(x = x_mm(xlab_end) - w, y = y0, w = w, h = y1 - y0, url = unname(url))
  list(plot = p, links = links)
}

# The DOI of each entry in the poster's bibliography as a URL, or the entry's
# URL where it has no DOI, named by citation key.
bib_urls <- function(file = "references.bib") {
  x <- readLines(file, encoding = "UTF-8", warn = FALSE)
  starts <- grep("^@[A-Za-z]+\\{", x)
  ends <- c(starts[-1] - 1, length(x))
  field <- function(lines, name) {
    pat <- paste0("^\\s*", name, "\\s*=\\s*\\{(.*)\\},?\\s*$")
    hit <- grep(pat, lines, value = TRUE)
    if (length(hit)) sub(pat, "\\1", hit[1]) else NA_character_
  }
  urls <- vapply(seq_along(starts), function(i) {
    e <- x[starts[i]:ends[i]]
    doi <- field(e, "doi")
    if (!is.na(doi)) paste0("https://doi.org/", doi) else field(e, "url")
  }, "")
  stats::setNames(urls, sub("^@[A-Za-z]+\\{([^,]+),.*$", "\\1", x[starts]))
}

# Where a plot's panel sits in the printed figure, in mm from its top-left
# corner, read from the built plot's layout at the size the figure is drawn.
panel_mm <- function(p, width_mm, height_mm) {
  tmp <- tempfile(fileext = ".png")
  ragg::agg_png(tmp, width = width_mm, height = height_mm, units = "mm", res = 72)
  on.exit({ grDevices::dev.off(); unlink(tmp) }, add = TRUE)
  g <- ggplot2::ggplotGrob(p)
  w <- grid::convertWidth(g$widths, "mm", valueOnly = TRUE)
  h <- grid::convertHeight(g$heights, "mm", valueOnly = TRUE)
  pan <- g$layout[g$layout$name == "panel", ]
  # The panel's own row and column are null units, which convert to zero here;
  # the panel takes what the fixed rows and columns leave.
  list(left = sum(w[seq_len(pan$l - 1)]), top = sum(h[seq_len(pan$t - 1)]),
       width = width_mm - sum(w), height = height_mm - sum(h))
}

# ---------------------------------------------------------------------------
# Where research on children's digital reading has looked (scopusflow counts)
# ---------------------------------------------------------------------------

scopus_periods <- function(foci, split = 2017) {
  d <- foci[foci$query_type == "comparison", ]
  d$period <- ifelse(d$year <= split, "early", "late")
  a <- stats::aggregate(cbind(n, reference_n) ~ label + period, data = d, FUN = sum)
  a$pct <- 100 * a$n / a$reference_n
  w <- stats::reshape(a[c("label", "period", "n", "pct")], idvar = "label",
                      timevar = "period", direction = "wide")
  w[order(w$pct.late), ]
}

fig_scopus <- function(width_mm, height_mm, foci_file = "data/scopus_focus_trends.csv") {
  foci  <- utils::read.csv(foci_file, stringsAsFactors = FALSE, encoding = "UTF-8")

  # One row per topic, ordered by its recent share. The two topics this study
  # brings together are drawn in the accent colour and the rest in grey, so the
  # comparison the poster makes is the one the eye makes first. The labels form
  # a column of their own, sized to the longest, to the left of the shares.
  w <- scopus_periods(foci)
  w$ours <- w$label %in% c("Language of the text", "Log data and learning analytics")
  w$row <- seq_len(nrow(w))
  w$name <- ifelse(w$label == "Log data and learning analytics", "Log data", w$label)
  w$group <- ifelse(w$ours, "ours", "other")
  col <- c(ours = PAL[["accent"]], other = PAL[["ink_soft"]])
  # The label column sits inside the panel, to the left of zero, so the panel
  # starts at the figure's left edge like the evidence map above it. Its width in
  # data units is the longest label's printed width, scaled by the panel's width
  # in mm (the figure less its margins; this panel draws no y-axis text).
  xmax <- 21.5
  lab_mm <- text_mm(w$name, MIN_PT + 1, bold = TRUE) + 5
  panel_mm <- width_mm - 16
  xmin <- -xmax * lab_mm / (panel_mm - lab_mm)

  pb <- ggplot(w, aes(y = row, colour = group)) +
    # The accent is carried by line type as well as hue (solid against dashed),
    # so the two highlighted rows survive greyscale printing and colour-vision
    # deficiency.
    geom_segment(aes(x = pct.early, xend = pct.late, yend = row, linetype = group),
                 linewidth = 1.6) +
    geom_point(aes(x = pct.early), shape = 21, fill = PAL[["paper"]], size = 5.2, stroke = 1.6) +
    geom_point(aes(x = pct.late, fill = group), shape = 21, size = 5.2, stroke = 1.6) +
    geom_text(aes(x = -0.6, label = name, fontface = ifelse(ours, "bold", "plain")),
              hjust = 1, family = FONT, size = pt_mm(MIN_PT + 1)) +
    geom_text(aes(x = pmax(pct.late, pct.early) + 0.7, label = sprintf("%.0f%%", pct.late),
                  fontface = ifelse(ours, "bold", "plain")),
              hjust = 0, family = FONT, size = pt_mm(MIN_PT + 1)) +
    # A key in the empty lower right, where the recent shares are smallest. Two
    # single-fill annotations, because one annotation with two fills reads to
    # check_figure() as a colour encoding, and its white as white on white.
    annotate("point", x = 14.2, y = 2.25, shape = 21, size = 5.2, stroke = 1.6,
             colour = PAL[["ink_soft"]], fill = PAL[["paper"]]) +
    annotate("point", x = 14.2, y = 1.25, shape = 21, size = 5.2, stroke = 1.6,
             colour = PAL[["ink_soft"]], fill = PAL[["ink_soft"]]) +
    annotate("text", x = 15, y = c(2.25, 1.25), label = c("2010–17", "2018–25"), hjust = 0,
             family = FONT, size = pt_mm(MIN_PT), colour = PAL[["ink_soft"]]) +
    scale_linetype_manual(values = c(ours = "solid", other = "22")) +
    scale_colour_manual(values = col) +
    scale_fill_manual(values = col) +
    scale_y_continuous(limits = c(0.5, nrow(w) + 0.5), expand = expansion(add = 0)) +
    scale_x_continuous(breaks = seq(0, 20, 5), labels = function(x) paste0(x, "%"),
                       expand = expansion(add = 0)) +
    coord_cartesian(xlim = c(xmin, xmax), clip = "off") +
    labs(title = "Share of digital-reading records on each topic", x = NULL, y = NULL) +
    theme_poster() +
    theme(axis.text.y = element_blank(), panel.grid.major.y = element_blank())

  audit(pb, width_mm, "Scopus foci")
  pb
}

scopus_gap <- function(gap_file = "data/scopus_gap.csv") {
  g <- utils::read.csv(gap_file, stringsAsFactors = FALSE, encoding = "UTF-8")
  stats::setNames(g$n, g$label)
}

# ---------------------------------------------------------------------------
# Precision comes from stories, not sessions (the protocol's design analysis)
# ---------------------------------------------------------------------------

fig_precision <- function(width_mm, height_mm,
                          file = file.path(DESIGN_DIR, "precision_sweep.csv")) {
  res <- utils::read.csv(file, stringsAsFactors = FALSE)
  res$truth <- suppressWarnings(as.numeric(res$truth))
  term <- ifelse(grepl("_age$", res$param), "int", "main")
  res$term <- factor(term, levels = c("main", "int"))
  cols <- c(main = PAL[["ox_mid"]], int = PAL[["grammatical"]])
  ltys <- c(main = "solid", int = "22")
  shps <- c(main = 21, int = 24)

  texts <- res[res$model == "developmental" & res$sweep == "texts" & res$truth == 0.10, ]
  reads <- res[res$model == "developmental" & res$sweep == "readings", ]
  if (!nrow(texts) || !nrow(reads)) stop("precision sweep is missing a panel", call. = FALSE)
  # The key names how many lines each kind draws, so a reader who counts three
  # blue lines and two green ones finds them accounted for.
  n_line <- tapply(texts$param, texts$term, function(x) length(unique(x)))
  words <- c("One", "Two", "Three", "Four", "Five", "Six")
  key_lab <- c(main = sprintf("%s main effects (H1)", words[n_line[["main"]]]),
               int  = sprintf("%s age-band interactions (H2, H3)", words[n_line[["int"]]]))

  panel <- function(d, x, title, xlab, breaks) {
    p <- ggplot(d, aes(.data[[x]], p_meaningful, colour = term, linetype = term,
                       shape = term, group = param)) +
      # The 90% target is drawn in grey, apart from the two series' colours.
      annotate("rect", xmin = 0, xmax = Inf, ymin = 0.9, ymax = 1,
               fill = PAL[["grid"]], alpha = 0.8) +
      geom_hline(yintercept = 0.9, colour = PAL[["ink_soft"]], linewidth = 0.8,
                 linetype = "dashed") +
      geom_line(linewidth = 1.2) +
      geom_point(size = 3.4, fill = PAL[["paper"]], stroke = 1.2) +
      scale_x_log10(breaks = breaks, labels = scales::label_comma(),
                    expand = expansion(mult = c(0.04, 0.06))) +
      scale_y_continuous(limits = c(0, 1), breaks = c(0, 0.5, 0.9),
                         labels = c("0", "50%", "90%")) +
      scale_colour_manual(values = cols, name = NULL) +
      scale_linetype_manual(values = ltys, name = NULL) +
      scale_shape_manual(values = shps, name = NULL) +
      labs(title = title, x = xlab, y = NULL) +
      theme_poster() +
      theme(panel.grid.major.x = element_blank())
    p
  }
  pa <- panel(texts, "texts", "More distinct stories", "Distinct stories", c(50, 200, 800))
  pb <- panel(reads, "per_text", "More readings of 250 stories", "Readings per story",
              c(2, 5, 12, 30, 60))
  audit(pa, width_mm / 2, "precision panel a")
  audit(pb, width_mm / 2, "precision panel b")

  # One key for both panels, above them: inside either panel it would cover a
  # curve somewhere along its rise. It is drawn by hand, one entry to a line, so
  # that each sample line sits hard against its own label, with no neighbouring
  # label to be read as its caption, and each label takes its series' colour.
  # The labels are set in regular weight and stand clear of the panel titles
  # below, which are bold, so that the key is not read as a title.
  key_pt <- MIN_PT + 1
  key_mm <- 30                                  # height of the two-line key
  sample_mm <- 16; pad_mm <- 3
  key_y <- c(main = 0.80, int = 0.38)           # 12.6 mm apart
  key <- ggplot() +
    coord_cartesian(xlim = c(0, width_mm), ylim = c(0, 1), expand = FALSE, clip = "off") +
    theme_void() + theme(plot.background = element_rect(fill = PAL[["paper"]], colour = NA))
  for (k in names(key_y)) {
    y0 <- key_y[[k]]
    key <- key +
      annotate("segment", x = 2, xend = 2 + sample_mm, y = y0, yend = y0,
               colour = cols[[k]], linetype = ltys[[k]], linewidth = 1.4) +
      annotate("point", x = 2 + sample_mm / 2, y = y0, shape = shps[[k]], size = 4.2,
               stroke = 1.4, colour = cols[[k]], fill = PAL[["paper"]]) +
      annotate("text", x = 2 + sample_mm + pad_mm, y = y0, label = key_lab[[k]],
               hjust = 0, family = FONT, size = pt_mm(key_pt), colour = cols[[k]])
  }
  key / (pa | pb) + plot_layout(heights = c(key_mm, height_mm - key_mm)) &
    theme(legend.position = "none")
}

precision_requirements <- function(file = file.path(DESIGN_DIR, "minimum_texts.csv"),
                                   bf_file = file.path(DESIGN_DIR, "minimum_texts_bf10.csv")) {
  m <- utils::read.csv(file, stringsAsFactors = FALSE)
  b <- utils::read.csv(bf_file, stringsAsFactors = FALSE)
  dev <- m[m$model == "developmental", ]
  bdev <- b[b$model == "developmental" & b$target == 0.9, ]
  main <- !grepl("_age$", dev$param)
  bmain <- !grepl("_age$", bdev$param)
  r10 <- function(x) format(round(x, -1), big.mark = ",")
  list(
    main_lo = r10(min(dev$value[main])), main_hi = r10(max(dev$value[main])),
    int_lo  = r10(min(dev$value[!main])), int_hi = r10(max(dev$value[!main])),
    bf_main = r10(mean(bdev$value[bmain])), bf_int = r10(mean(bdev$value[!bmain]))
  )
}

# ---------------------------------------------------------------------------
# The six registered hypotheses, drawn as one diagram
# ---------------------------------------------------------------------------

# Each text property runs to a common bus and from there to the two outcomes.
# A property's path carries its predicted sign (H1) and a tag for each
# hypothesis that qualifies it: narration on the lexical and continuity paths
# (H4 sets one against the other), the age band on the grammatical (H2) and
# continuity (H3) paths.
fig_model <- function(width_mm, height_mm) {
  W <- width_mm; H <- height_mm
  bx <- function(x0, x1, y0, y1, fill, colour = NA)
    annotate("rect", xmin = x0, xmax = x1, ymin = y0, ymax = y1, fill = fill,
             colour = colour, linewidth = 0.9)
  txt <- function(x, y, label, size = MIN_PT + 3, colour = "white", face = "bold",
                  hjust = 0.5, lineheight = 0.92)
    annotate("text", x = x, y = y, label = label, family = FONT, size = pt_mm(size),
             colour = colour, fontface = face, hjust = hjust, lineheight = lineheight)
  tag <- function(x, y, label, colour)
    annotate("label", x = x, y = y, label = label, family = FONT, size = pt_mm(MIN_PT),
             colour = colour, fill = "white", linewidth = 0.7, lineheight = 0.95,
             label.padding = unit(2, "mm"), label.r = unit(2.5, "mm"))

  fx1 <- 0.405 * W                    # right edge of the property boxes
  bus <- 0.745 * W                    # where the three paths meet
  ox0 <- 0.782 * W                    # left edge of the outcome boxes
  fh  <- 0.22 * H
  fy  <- c(0.78, 0.47, 0.16) * H      # centres of the three property boxes
  feat <- data.frame(
    y = fy,
    fill = c(PAL[["lexical"]], PAL[["grammatical"]], PAL[["continuity"]]),
    title = c("Lexical difficulty", "Grammatical load", "Referential continuity"),
    sub = c("rare, long, unexpected words", "long, embedded sentences",
            "sentences that state their links"),
    sign = c("+", "+", "−"),
    tags = I(list("× narration  H4", "× age band  H2",
                  c("× age band  H3", "× narration  H4")))
  )

  p <- ggplot() + coord_cartesian(xlim = c(0, W), ylim = c(0, H), expand = FALSE, clip = "off") +
    theme_void() + theme(plot.background = element_rect(fill = PAL[["paper"]], colour = NA))

  sx <- fx1 + 0.06 * W                # the sign discs
  p <- p + txt(sx, 0.975 * H, "H1: predicted sign", size = MIN_PT, colour = PAL[["ink_soft"]],
               face = "bold")
  for (i in seq_len(nrow(feat))) {
    f <- feat[i, ]
    p <- p + bx(0, fx1, f$y - fh / 2, f$y + fh / 2, f$fill) +
      txt(fx1 / 2, f$y + 0.038 * H, f$title, size = MIN_PT + 4) +
      txt(fx1 / 2, f$y - 0.05 * H, f$sub, size = MIN_PT, face = "plain") +
      annotate("segment", x = fx1, xend = bus, y = f$y, yend = f$y, colour = f$fill,
               linewidth = 1.8) +
      annotate("point", x = sx, y = f$y, size = 14, shape = 21, fill = "white",
               colour = f$fill, stroke = 1.8) +
      txt(sx, f$y, f$sign, size = MIN_PT + 9, colour = f$fill)
    tg <- f$tags[[1]]
    tx <- if (length(tg) == 1) (sx + bus) / 2 + 0.02 * W else
      c(sx + 0.16 * W, sx + 0.16 * W)
    ty <- if (length(tg) == 1) f$y else f$y + c(0.075, -0.075) * H
    for (k in seq_along(tg)) p <- p + tag(tx[k], ty[k], tg[k], f$fill)
  }

  # The bus and the two outcomes: reading pace carries H1 to H4 and H6, the
  # child's own rating H5.
  pace <- c(0.46, 0.80) * H
  rate <- c(0.05, 0.34) * H
  p <- p +
    annotate("segment", x = bus, xend = bus, y = min(fy), yend = max(fy),
             colour = PAL[["ox_blue"]], linewidth = 2.2) +
    annotate("segment", x = bus, xend = ox0, y = mean(pace), yend = mean(pace),
             colour = PAL[["ox_blue"]], linewidth = 1.8,
             arrow = arrow(length = unit(4.5, "mm"), type = "closed")) +
    annotate("segment", x = bus, xend = ox0, y = mean(rate), yend = mean(rate),
             colour = PAL[["ox_mid"]], linewidth = 1.4, linetype = "22",
             arrow = arrow(length = unit(4.5, "mm"), type = "closed")) +
    bx(ox0, W, pace[1], pace[2], PAL[["ox_blue"]]) +
    txt((ox0 + W) / 2, mean(pace) + 0.075 * H, "Reading\npace", size = MIN_PT + 4) +
    txt((ox0 + W) / 2, mean(pace) - 0.09 * H, "log seconds\nper word", size = MIN_PT,
        face = "plain") +
    bx(ox0, W, rate[1], rate[2], "white", colour = PAL[["ox_mid"]]) +
    txt((ox0 + W) / 2, mean(rate) + 0.04 * H, curly("Child's\ndifficulty\nrating"),
        size = MIN_PT + 2, colour = PAL[["ox_mid"]]) +
    txt((ox0 + W) / 2, mean(rate) - 0.105 * H, "H5", size = MIN_PT,
        colour = PAL[["ox_mid"]]) +
    # Centred over the outcome column, unless it would then run past the
    # figure's right edge, where the SVG would cut it.
    txt(min((ox0 + W) / 2, W - text_mm("H6: more reading,", MIN_PT) / 2 - 1), 0.935 * H,
        "H6: more reading,\nfaster pace", size = MIN_PT, colour = PAL[["ox_blue"]],
        face = "plain") +
    annotate("segment", x = (ox0 + W) / 2, xend = (ox0 + W) / 2, y = 0.865 * H,
             yend = pace[2] + 0.004 * H, colour = PAL[["ox_blue"]], linewidth = 1.1,
             arrow = arrow(length = unit(3.5, "mm"), type = "closed"))
  p
}

# ---------------------------------------------------------------------------
# QR code to the poster's folder on GitHub, whose README carries the references
# ---------------------------------------------------------------------------

make_qr <- function(url, file) {
  q <- qrcode::qr_code(url, ecl = "M")
  qrcode::generate_svg(q, filename = file, size = 600, foreground = PAL[["ox_blue"]],
                       background = "white", show = FALSE)
  invisible(file)
}

# ---------------------------------------------------------------------------

build_figures <- function(dims, qr_url, out = "figures") {
  register_poster_fonts()
  dir.create(out, showWarnings = FALSE)
  save_svg(fig_scopus(dims$scopus[1], dims$scopus[2]), file.path(out, "scopus.svg"),
           dims$scopus[1], dims$scopus[2])
  save_svg(fig_precision(dims$precision[1], dims$precision[2]),
           file.path(out, "precision.svg"), dims$precision[1], dims$precision[2])
  save_svg(fig_model(dims$model[1], dims$model[2]), file.path(out, "model.svg"),
           dims$model[1], dims$model[2])
  ev <- fig_evidence(dims$evidence[1], dims$evidence[2])
  save_svg(ev$plot, file.path(out, "evidence.svg"), dims$evidence[1], dims$evidence[2])
  jsonlite::write_json(ev$links, file.path(out, "evidence-links.json"), digits = 2)
  make_qr(qr_url, file.path(out, "qr.svg"))
  invisible(TRUE)
}
