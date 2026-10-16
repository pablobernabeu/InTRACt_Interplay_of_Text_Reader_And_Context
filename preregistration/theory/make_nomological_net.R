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
stopifnot(nrow(nodes) == 12, nrow(edges) == 18)

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
writeLines(styled, "figures/nomological_net_styled.gv")

# -- the assertion: restyled content identical to emitted content --------------
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
writeLines("content assertion passed: 12 nodes, 18 edges, wording unchanged")

# -- render --------------------------------------------------------------------
# The layout is computed by the viz.js 1.8.2 engine that DiagrammeR 1.0.12
# bundles, run through V8 by DiagrammeRsvg. A system Graphviz can lay the same
# .gv files out differently.
svg <- DiagrammeRsvg::export_svg(DiagrammeR::grViz(styled))
writeLines(svg, "figures/nomological_net.svg")
raw <- charToRaw(svg)
rsvg::rsvg_pdf(raw, "figures/nomological_net.pdf")
rsvg::rsvg_png(raw, "figures/nomological_net.png", width = 3200)
writeLines("wrote figures/nomological_net.{gv,svg,pdf,png} and the styled .gv")
