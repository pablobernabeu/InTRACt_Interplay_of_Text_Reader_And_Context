# Figure 1: the nomological net, emitted from the theory object so that the
# figure and the hypotheses cannot drift apart.
library(theoryforge)
th  <- tf_read("theory/intract.theory.yaml")
dot <- tf_diagram(th, type = "nomological_net", engine = "graphviz")
writeLines(dot, "figures/fig1_nomological_net.gv")

svg <- tryCatch(tf_render_diagram(th, type = "nomological_net", as = "svg"),
                error = function(e) { message("render failed: ", conditionMessage(e)); NULL })
if (!is.null(svg)) {
  writeLines(as.character(svg), "figures/fig1_nomological_net.svg")
  writeLines("svg written")
} else writeLines("svg NOT written")
