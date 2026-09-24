# Quarto post-render hook, called from _quarto.yml after every render.
#
# Renames preregistration.pdf and preregistration.html to
# "InTRACt preregistration draft - YYYY-MM-DD.<ext>", dated by the render
# machine's clock, so each day's render is kept beside the earlier ones.
# supplementary.pdf and supplementary.html are not renamed and are overwritten
# by every render.
#
# A second render on the same day replaces that day's draft. If the dated file
# is locked, for example open in a PDF viewer or held by OneDrive, the rename
# fails and the hook stops with an error. Without the stop, the fresh render
# would sit under its undated name while the dated draft beside it still held
# the earlier one.

today <- format(Sys.Date(), "%Y-%m-%d")
prefix <- "InTRACt preregistration draft"

for (ext in c("pdf", "html")) {
  src <- paste0("preregistration.", ext)
  dst <- paste0(prefix, " - ", today, ".", ext)
  if (file.exists(src)) {
    if (!file.rename(src, dst)) {
      stop("could not rename ", src, " to ", dst,
           " (is the dated draft open in a viewer or locked by OneDrive?)",
           call. = FALSE)
    }
    message("Renamed: ", src, " -> ", dst)
  }
}
