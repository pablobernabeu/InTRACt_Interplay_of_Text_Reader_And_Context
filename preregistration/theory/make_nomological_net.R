# Figure 2 of the manuscript, the nomological net, emitted from the theory object
# so that the figure and the hypotheses cannot drift apart.
#
# tf_diagram() fixes the content: which constructs exist, which paths connect
# them and what each path claims. Its default layout, though, labels every one
# of the eighteen paths with a word and lets graphviz place them freely, which
# a reader meets as a tangle. This script therefore restyles the emitted DOT
# without touching its content: the words on the edges become signs on the
# lines, moderation becomes a dashed line, and the constructs are grouped
# into the reader, the text and the reading. A hard assertion at the bottom
# fails the script if the restyled graph carries any node or edge the theory
# object did not emit, or misses one it did.
#
#   Rscript theory/make_nomological_net.R   (from the preregistration directory)

library(theoryforge)

th  <- tf_read("theory/intract.theory.yaml")
dot <- tf_diagram(th, type = "nomological_net", engine = "graphviz")
writeLines(dot, "figures/nomological_net.gv")

# -- parse the emitted DOT into nodes (id, label) and edges (from, to, claim) --
lines <- strsplit(dot, "\n")[[1]]
node_rx <- '^\\s*"([^"]+)"\\s*\\[label="([^"]+)"'
edge_rx <- '^\\s*"([^"]+)"\\s*->\\s*"([^"]+)"\\s*\\[label="([^"]+)"\\]'

node_m <- regmatches(lines, regexec(node_rx, lines))
nodes  <- do.call(rbind, lapply(node_m[lengths(node_m) == 3 & !grepl("->", lines)],
                                function(m) data.frame(id = m[2], label = m[3])))
edge_m <- regmatches(lines, regexec(edge_rx, lines))
edges  <- do.call(rbind, lapply(edge_m[lengths(edge_m) == 4],
                                function(m) data.frame(from = m[2], to = m[3], claim = m[4])))
# One node per construct and one edge per proposition, counted in the object
# itself, so a parse that missed a line cannot pass.
stopifnot(nrow(nodes) == length(th$constructs), nrow(edges) == length(th$propositions))

# Wording comes from the object; only the line breaks are re-fitted.
unwrap <- function(x) gsub("\\\\n", " ", x)
rewrap <- function(x, width = 16) {
  vapply(x, function(s) paste(strwrap(unwrap(s), width = width), collapse = "\\n"), character(1))
}
nodes$label_wrapped <- rewrap(nodes$label)

# -- restyle: groups by role, and one visual code per kind of claim ------------
groups <- list(
  reader  = c("c_accumulated_reading", "c_decoding_automaticity",
              "c_verbal_working_memory", "c_inferential_resource"),
  session = "c_spoken_rendition",
  text    = c("c_text_provenance", "c_lexical_accessibility",
              "c_structural_integration_load", "c_referential_continuity"),
  reading = c("c_processing_effort", "c_experienced_difficulty", "c_situation_model")
)
stopifnot(setequal(unlist(groups), nodes$id))
group_titles <- c(reader = "The reader", session = "The session",
                  text = "The text", reading = "The reading")

# A signed claim carries its sign as a small glyph at the midpoint of its own
# line, where lines are farthest apart, and the colour repeats the sign.
# The Graphviz attribute strings below are kept whole, one per line, so that they
# read as the DOT they write.
# nolint start: line_length_linter.
edge_attr <- function(claim, sign_col_plus = "#d55e00", sign_col_minus = "#0072b2") {
  switch(claim,
    increases = sprintf('[color="%s", label="+", fontcolor="%s", fontsize=16, penwidth=1.2]', sign_col_plus, sign_col_plus),
    decreases = sprintf('[color="%s", label="−", fontcolor="%s", fontsize=16, penwidth=1.2]', sign_col_minus, sign_col_minus),
    moderates = '[color="#8A9BA8", style=dashed, penwidth=1.1]',
    causes    = '[color="#3A4A58", penwidth=1.2]',
    stop("unknown claim: ", claim)
  )
}
# nolint end

node_line <- function(id, label) {
  sprintf('    "%s" [label="%s"]', id, label)
}

cluster <- function(key) {
  ids <- groups[[key]]
  body <- paste(vapply(ids, function(i) {
    node_line(i, nodes$label_wrapped[nodes$id == i])
  }, character(1)), collapse = "\n")
  # nolint start: line_length_linter.
  sprintf('  subgraph cluster_%s {\n    label="%s"; labeljust=l; fontsize=13; fontcolor="#5A6B78";\n    color="#C9D4DC"; style=rounded; margin=14;\n%s\n  }',
          key, group_titles[[key]], body)
  # nolint end
}

edge_lines <- paste(sprintf('  "%s" -> "%s" %s', edges$from, edges$to,
                            vapply(edges$claim, edge_attr, character(1))),
                    collapse = "\n")

# The DOT template is one string, laid out as the file it writes, so it keeps its
# own indentation and its single quotes around double-quoted attributes.
# nolint start: indentation_linter, line_length_linter, quotes_linter.
styled <- paste0(
'digraph nomological_net {
  graph [rankdir=TB, bgcolor="white", fontname="Helvetica", fontsize=12,
         pad="0.25", nodesep="0.4", ranksep="0.7", splines=true, newrank=true]
  node [fontname="Helvetica", fontsize=12, shape=box, style="rounded,filled",
        color="#33567A", fillcolor="#F2F6F9", fontcolor="#12283A", penwidth=1.1,
        margin="0.18,0.11"]
  edge [arrowsize=0.75]
', paste(vapply(names(groups), cluster, character(1)), collapse = "\n"), '
  { rank=same; "c_accumulated_reading"; "c_verbal_working_memory"; "c_inferential_resource" }
  { rank=same; "c_lexical_accessibility"; "c_structural_integration_load"; "c_referential_continuity"; "c_spoken_rendition" }
  { rank=same; "c_experienced_difficulty"; "c_situation_model" }
  "c_experienced_difficulty" -> "c_situation_model" [style=invis]
', edge_lines, '
}
')
# nolint end

# -- the assertion: restyled content identical to emitted content --------------
# Every construct id anywhere in the restyled DOT, the rank hints and the
# invisible edge included, must be one the object emitted: graphviz would draw
# an id it has not met as a node of its own.
dot_ids <- gsub('"', "", regmatches(styled, gregexpr('"c_[^"]+"', styled))[[1]], fixed = TRUE)
stopifnot(all(dot_ids %in% nodes$id))
# Invisible edges are layout hints, not claims, so they are excluded here and
# must stay invisible: an invis edge that became visible would assert a path
# the theory object does not contain.
slines   <- strsplit(styled, "\n")[[1]]
slines   <- slines[!grepl("style=invis", slines, fixed = TRUE)]
s_edge_m <- regmatches(slines, regexec('^\\s*"(c_[^"]+)"\\s*->\\s*"(c_[^"]+)"', slines))
s_edges  <- unique(vapply(s_edge_m[lengths(s_edge_m) == 3],
                          function(m) paste(m[2], m[3], sep = "->"), character(1)))
stopifnot(setequal(s_edges, paste(edges$from, edges$to, sep = "->")))
s_node_m <- regmatches(slines, regexec('^\\s*"(c_[^"]+)"\\s*\\[label="([^"]+)"\\]', slines))
s_nodes  <- do.call(rbind, lapply(s_node_m[lengths(s_node_m) == 3],
                                  function(m) data.frame(id = m[2], label = m[3])))
stopifnot(setequal(s_nodes$id, nodes$id))
stopifnot(all(unwrap(s_nodes$label[order(s_nodes$id)]) ==
                unwrap(nodes$label[order(nodes$id)])))
writeLines(sprintf("content assertion passed: %d nodes, %d edges, wording unchanged",
                   nrow(nodes), nrow(edges)))
writeLines(styled, "figures/nomological_net_styled.gv")

# -- render --------------------------------------------------------------------
# The layout is computed by the viz.js 1.8.2 engine that DiagrammeR 1.0.12
# bundles, run through V8 by DiagrammeRsvg. A system Graphviz can lay the same
# .gv files out differently.
svg <- DiagrammeRsvg::export_svg(DiagrammeR::grViz(styled))

# -- print size ----------------------------------------------------------------
# The other figures are checked by depictr, which reads ggplot objects; this one
# is checked here. The protocol embeds it at the share of the text width given
# in preregistration.qmd, on a text width of 468 pt (US letter with one-inch
# margins, as measured in the rendered PDF), so its smallest type prints at the
# smallest font size in the DOT scaled by that width over the SVG's own. It
# must reach the six-point floor the other figures are held to.
TEXT_WIDTH_PT <- 468
MIN_PRINT_PT  <- 6
qmd   <- paste(readLines("preregistration.qmd", warn = FALSE), collapse = "\n")
embed <- "\\(figures/nomological_net\\.pdf\\)\\{#fig-net width=([0-9.]+)%\\}"
share <- regmatches(qmd, regexec(embed, qmd))[[1]][2]
svg_w <- regmatches(svg, regexec('<svg width="([0-9.]+)pt"', svg))[[1]][2]
fonts <- regmatches(styled, gregexpr("fontsize=[0-9.]+", styled))[[1]]
fonts <- as.numeric(sub("fontsize=", "", fonts, fixed = TRUE))
if (is.na(share) || is.na(svg_w) || !length(fonts))
  stop("could not read the embedding width, the SVG width or the font sizes", call. = FALSE)
printed_pt <- min(fonts) * TEXT_WIDTH_PT * as.numeric(share) / 100 / as.numeric(svg_w)
writeLines(sprintf("smallest type prints at %.2f pt (floor %d pt)", printed_pt, MIN_PRINT_PT))
if (printed_pt < MIN_PRINT_PT)
  stop("Figure 2's smallest type would print at ", round(printed_pt, 2), " pt, below the ",
       MIN_PRINT_PT, "-point floor", call. = FALSE)

# -- colour contrast -----------------------------------------------------------
# The contrast ratios of the colours in the DOT against what they sit on, with
# the floors the other figures are held to: 4.5 for words (node and group
# labels) and 3 for marks (lines, node borders and the sign glyphs). The group
# borders are decorative, since the group titles name the groups. A word below
# its floor stops the script. A mark below it is reported as a warning: the
# dashed moderation lines are at 2.86, and darkening them would change the
# figure, which is the author's decision.
luminance <- function(hex) {
  v <- grDevices::col2rgb(hex)[, 1] / 255
  v <- ifelse(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055)^2.4)
  sum(c(0.2126, 0.7152, 0.0722) * v)
}
contrast <- function(a, b) {
  l <- sort(c(luminance(a), luminance(b)), decreasing = TRUE)
  (l[1] + 0.05) / (l[2] + 0.05)
}
hex_of <- function(s, key) {
  m <- unlist(regmatches(s, gregexpr(paste0("\\b", key, '="#[0-9A-Fa-f]{6}"'), s)))
  unique(sub('.*"(#[0-9A-Fa-f]{6})"', "\\1", m))
}
node_block   <- regmatches(styled, regexpr("node \\[[^]]*\\]", styled))
cluster_head <- unlist(regmatches(styled, gregexpr("subgraph cluster_[a-z]+ \\{\n[^\n]*", styled)))
edge_def     <- slines[grepl("->", slines, fixed = TRUE)]
bg   <- sub('.*bgcolor="([^"]+)".*', "\\1", slines[grepl("bgcolor=", slines, fixed = TRUE)][1])
fill <- hex_of(node_block, "fillcolor")
pairs <- rbind(
  data.frame(role = "word", colour = hex_of(node_block, "fontcolor"), on = fill),
  data.frame(role = "word", colour = hex_of(cluster_head, "fontcolor"), on = bg),
  data.frame(role = "mark", on = bg,
             colour = unique(c(hex_of(edge_def, "color"), hex_of(edge_def, "fontcolor"),
                               hex_of(node_block, "color"))))
)
pairs$ratio <- mapply(contrast, pairs$colour, pairs$on)
pairs$floor <- ifelse(pairs$role == "word", 4.5, 3)
print(pairs, row.names = FALSE, digits = 3)
low <- pairs[pairs$ratio < pairs$floor, , drop = FALSE]
if (any(low$role == "word"))
  stop("Figure 2 has text below 4.5:1 contrast: ",
       paste(low$colour[low$role == "word"], collapse = ", "), call. = FALSE)
if (nrow(low))
  warning("Figure 2 has marks below 3:1 contrast: ",
          paste(sprintf("%s (%.2f)", low$colour, low$ratio), collapse = ", "), call. = FALSE)

writeLines(svg, "figures/nomological_net.svg")
raw <- charToRaw(svg)
rsvg::rsvg_pdf(raw, "figures/nomological_net.pdf")
rsvg::rsvg_png(raw, "figures/nomological_net.png", width = 3200)
writeLines("wrote figures/nomological_net.{gv,svg,pdf,png} and the styled .gv")
