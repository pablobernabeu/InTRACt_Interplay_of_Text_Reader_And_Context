# Render the theory diagram to PNG and PDF for the manuscript.
library(theoryforge)
th  <- tf_read("theory/intract.theory.yaml")
svg <- tf_render_diagram(th, type = "nomological_net", as = "svg")
writeLines(as.character(svg), "figures/fig1_nomological_net.svg")
rsvg::rsvg_png("figures/fig1_nomological_net.svg", "figures/fig1_nomological_net.png",
               width = 2600)
rsvg::rsvg_pdf("figures/fig1_nomological_net.svg", "figures/fig1_nomological_net.pdf")
writeLines(paste("png bytes:", file.size("figures/fig1_nomological_net.png")))
