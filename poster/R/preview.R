# InTRACt poster: a PNG preview of the rendered PDF, for sharing on screen and for
# checking the layout without opening the A1 file.
#
# Run from the poster directory after `quarto render poster.qmd`:
#   Rscript R/preview.R [dpi]
# Writes poster-preview.png (72 dpi by default: 1,684 x 2,384 pixels). Stops if
# the PDF has more than one page, since an overflowing poster is a layout error
# and not something a preview should hide.

args <- commandArgs(trailingOnly = TRUE)
dpi <- if (length(args)) as.numeric(args[1]) else 72

info <- pdftools::pdf_info("poster.pdf")
if (info$pages != 1) stop("poster.pdf has ", info$pages, " pages; the layout overflows",
                          call. = FALSE)
size <- pdftools::pdf_pagesize("poster.pdf")
mm <- round(c(size$width, size$height) * 25.4 / 72)
if (!identical(mm, c(594, 841))) stop("poster.pdf is ", mm[1], " x ", mm[2], " mm, not A1",
                                      call. = FALSE)

bitmap <- pdftools::pdf_render_page("poster.pdf", page = 1, dpi = dpi)
png::writePNG(bitmap, "poster-preview.png")
cat("wrote poster-preview.png at", dpi, "dpi\n")
