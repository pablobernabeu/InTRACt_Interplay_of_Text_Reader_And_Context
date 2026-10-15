# The language on the screen: InTRACt poster

An A1 portrait conference poster (594 x 841 mm) on the InTRACt study, part of the
[LiFT project](https://www.education.ox.ac.uk/project/lift-learning-in-families-through-technology/)
at the Department of Education, University of Oxford. The left half sets out what meta-analyses
and a bibliometric count show about digital technology and children's reading. The right half
presents the study: the gap it addresses, the *Let's Story* logs, the six confirmatory
hypotheses, the design analysis and the Registered Report safeguards. The poster reports no data
from the study itself.

[`poster.pdf`](poster.pdf) is the print file and [`poster-preview.png`](poster-preview.png) a
72 dpi preview. The reference list is [at the end of this page](#references). The poster's QR
code opens this folder, and so does the short address printed above it,
[tinyurl.com/intract-poster](https://tinyurl.com/intract-poster).

## Building it

From this folder:

```bash
quarto render poster.qmd
Rscript R/preview.R                                 # poster-preview.png, 72 dpi
Rscript --no-save --no-restore R/scopus_counts.R   # only to refresh the Scopus counts
```

Rendering needs R (4.6.1 here) with ggplot2, patchwork, svglite, systemfonts, ragg, qrcode,
scales, jsonlite, rmarkdown and depictr, and Quarto (1.10.19 here, which bundles Typst 0.15.1 and Pandoc
3.10). Set `QUARTO_R` to R's `bin` folder if Quarto cannot find R. The render makes no network
request. Everything it reads is in this folder except the protocol's citation style,
`../preregistration/apa7.csl`, so it runs in a clone of the repository on any branch. `R/preview.R`
needs pdftools and png, and it stops on a PDF that is not a single A1 page, so an overflowing
layout cannot pass unnoticed. `R/scopus_counts.R` needs scopusflow 0.4.0 and a Scopus API key
in the `SCOPUS_API_KEY` environment variable, normally set in `~/.Renviron`, which the
repository ignores.

## How it is built

Quarto runs the R chunk at the top of `poster.qmd`. The chunk calls `build_figures()` in
`R/figures.R`, which writes every figure to `figures/` as SVG, and `write_references()` in
`R/references.R`, which renders the reference list below with Pandoc's citeproc from the
bibliography and style the poster cites with. Typst then lays out the sheet.
`typst-template.typ` holds the page geometry, the type scale and the blocks the body calls, and
`typst-show.typ` passes the YAML metadata to it. Captions are written as Markdown divs
(`::: {.caption}`), which `typst-blocks.lua` turns into calls to the template's blocks, so that
their citations pass through citeproc.

In the PDF, every citation opens its work's DOI, or its URL where it has none. Quarto runs
citeproc after every Lua filter, too late to link what citeproc writes, so `cite-links.lua`
runs citeproc itself and wraps each formatted citation in a link. The citations on the evidence
map are SVG text, which keeps no links once Typst draws it. `R/figures.R` therefore writes
`figures/evidence-links.json` beside the figure, giving each row's position in mm and its DOI,
and the template lays an invisible link over each row. The links carry no colour or underline,
so the printed sheet is unchanged. The QR code is a link to the folder it encodes.

Each figure is drawn at the width it is printed (269 mm, one column), so a point size in R is a
point size on paper. Before a figure is written, `depictr::check_figure()` audits it at that
width. It checks the smallest text (a 21 pt floor), colour separability with and without
simulated colour-vision deficiency, greyscale separability, contrast, and any distinction that
colour alone carries. A figure that fails is not written, and the render stops. Nothing on the
sheet is set below 21 pt. Ragged lines are broken for each paragraph as a whole, and a last line
of a single word is penalised, so a paragraph rewraps before it strands a word.

The two theme colours come from the department's lockup: Oxford blue (#002147) and the green of
the department's tree (#1dad89). That green clears only 2.8:1 against white, so it draws rules
and bars, and a darker shade of the same hue (#127b61, 5.2:1) carries text and data. On the
evidence map, crimson and blue mark the two directions of an effect, because they stay apart
under every common colour-vision deficiency.

The typeface is Figtree, kept in `fonts/` under the SIL Open Font License
(`fonts/LICENSE-Figtree.txt`). It stands in for Abadi, which is licensed for Microsoft 365 apps
only and so cannot be shared with the source. systemfonts finds the files in the working
directory for the figures, and Typst reads them through `font-paths`, so the figures and the
text use the same files on any machine.

## Where the content comes from

| Element | Source |
|---|---|
| Evidence map | `data/evidence.csv`. Each row holds a pooled effect from a published meta-analysis, or a finding that cannot share the g/d axis (a review's conclusion, or a correlation), read from the paper's full text in October 2026. The `location` column names the table or page of each value and records where a paper's text and tables disagree. |
| Scopus figure and the '0 of 1,536' box | `data/scopus_*.csv`, written by `R/scopus_counts.R` with scopusflow 0.4.0 on 14 October 2026. `data/scopus_search_record.md` holds every query verbatim, the limits and the totals, which are the PRISMA-S items a count-only search can supply. |
| Precision figure, its numbers and its assumptions | `data/design_analysis/`: `precision_sweep.csv`, `minimum_texts.csv` and `minimum_texts_bf10.csv`, copied on 15 October 2026 from the protocol's `../preregistration/design_analysis/`, so that the poster builds on a branch that lacks the protocol's latest files. Copy them again if the design analysis is re-run. The assumptions are those of the deposited specification (`tier1_developmental.json`) and of `run_design_analysis.R`, as the protocol's Design and precision analysis describes them. |
| Hypotheses diagram | The protocol's six confirmatory hypotheses and their predicted signs, in `../preregistration/`. |
| Logos | `img/`: the Department of Education and University of Oxford lockup, unaltered, in the header, where it stands in for a printed affiliation. In the footer, the LiFT project's logo, and the funder's Kinder and Ferrero logos stacked at one width, each trimmed to its artwork. |
| References | `references.bib`, which holds only the works the poster cites. Most entries are copied from the protocol's `InTRACt references.bib`, whose fields were checked against Crossref. The rest are four meta-analyses the protocol does not cite and the CRAN releases of pilotr and scopusflow, checked against Crossref and CRAN. |

## Choices behind the content

The evidence map shows where screens and apps cost children comprehension and where they help.
It also shows the conditions that decide which way an effect goes: the genre of the text, an
adult reading along, an add-on that serves the story, and a researcher-made or a standardised
test. Each effect is
coloured by its direction, and an interval that includes zero is grey. Correlational evidence
on everyday screen time sits in a group of its own, because a correlation cannot share an axis
with an experimental effect.

The rows come from a search for meta-analyses and systematic reviews of digital technology and
children's reading, run in October 2026. Where several syntheses overlap, the map keeps the most
recent one or the one with a child-specific estimate. It leaves out subgroup values that rest on
two or three studies or could not be checked against the published paper. The search found no
meta-analysis of generative AI and children's reading, language or literacy. The closest ones
pool mostly university students, so the poster states the gap and plots nothing for AI.

The Scopus figures count the records that match a search, false positives included, and the
'0 of 1,536' box counts the records that match two searches at once. Neither is a count of
screened studies. The precision curves are the protocol's own simulation, and the caption also
gives the requirement under the registered Bayes-factor rule, so that the poster agrees with
Table 1 of the protocol. Nothing on the sheet is computed from the app's logs or from its story
texts.

## References

<!-- references:start -->

Bernabeu, P. (2026a). *pilotr: Simulate experimental and behavioural data from a portable design specification* (Version 0.3.0) \[Computer software\]. Comprehensive R Archive Network. <https://doi.org/10.32614/CRAN.package.pilotr>

Bernabeu, P. (2026b). *scopusflow: A reproducible workflow layer for Scopus bibliographic searches* (Version 0.4.0) \[Computer software\]. Comprehensive R Archive Network. <https://doi.org/10.32614/CRAN.package.scopusflow>

Booton, S. A., Hodgkiss, A., & Murphy, V. A. (2023). The impact of mobile application features on children’s language and literacy learning: A systematic review. *Computer Assisted Language Learning*, *36*(3), 400–429. <https://doi.org/10.1080/09588221.2021.1930057>

Bus, A., Kucirkova, N., Ten Braak, D., & Ciesielska, M. (2026). Which interactive features in children’s digital picture books promote reading comprehension? A meta-analysis. *Early Education and Development*, *37*(2), 269–288. <https://doi.org/10.1080/10409289.2025.2571978>

Clinton-Lisell, V. (2023). Does reading while listening to text improve comprehension compared to reading only? A systematic review and meta-analysis. *Educational Research: Theory and Practice*, *34*(3), 133–155. <https://eric.ed.gov/?id=EJ1403866>

Delgado, P., Vargas, C., Ackerman, R., & Salmerón, L. (2018). Don’t throw away your printed books: A meta-analysis on the effects of reading media on reading comprehension. *Educational Research Review*, *25*, 23–38. <https://doi.org/10.1016/j.edurev.2018.09.003>

Furenes, M. I., Kucirkova, N., & Bus, A. G. (2021). A comparison of children’s reading on paper versus screen: A meta-analysis. *Review of Educational Research*, *91*(4), 483–517. <https://doi.org/10.3102/0034654321998074>

Madigan, S., McArthur, B. A., Anhorn, C., Eirich, R., & Christakis, D. A. (2020). Associations between screen use and child language skills: A systematic review and meta-analysis. *JAMA Pediatrics*, *174*(7), 665–675. <https://doi.org/10.1001/jamapediatrics.2020.0327>

Picton, I., & Clark, C. (2026). *Trends in children and young people’s reading in print and digital formats*. National Literacy Trust. <https://literacytrust.org.uk/research-services/research-reports/trends-in-children-and-young-peoples-reading-in-print-and-digital-formats/>

Ratner, S., & Murphy, V. A. (2026). Productive struggle in children’s app-based digital reading. *Frontiers in Developmental Psychology*, *4*, 1816559. <https://doi.org/10.3389/fdpys.2026.1816559>

Ratner, S., Ong, C., Mathers, S., & Murphy, V. A. (2025). ‘Did a robot write that?’: AI-generated digital storybooks. *ELT Journal*, *79*(4), 595–604. <https://doi.org/10.1093/elt/ccaf034>

Silverman, R. D., Keane, K., Darling-Hammond, E., & Khanna, S. (2025). The effects of educational technology interventions on literacy in elementary school: A meta-analysis. *Review of Educational Research*, *95*(5), 972–1012. <https://doi.org/10.3102/00346543241261073>

Takacs, Z. K., Swart, E. K., & Bus, A. G. (2015). Benefits and pitfalls of multimedia and interactive features in technology-enhanced storybooks: A meta-analysis. *Review of Educational Research*, *85*(4), 698–739. <https://doi.org/10.3102/0034654314566989>

Wood, S. G., Moxley, J. H., Tighe, E. L., & Wagner, R. K. (2018). Does use of text-to-speech and related read-aloud tools improve reading comprehension for students with reading disabilities? A meta-analysis. *Journal of Learning Disabilities*, *51*(1), 73–84. <https://doi.org/10.1177/0022219416688170>

<!-- references:end -->
