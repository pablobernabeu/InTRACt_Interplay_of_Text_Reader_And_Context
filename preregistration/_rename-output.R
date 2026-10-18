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
#
# Once the new draft is in place, any older dated draft beside it is moved into
# drafts/, so this folder holds the current draft only. Every dated draft is
# kept as the record of that version (README, "Every dated draft is kept"). An
# HTML draft loads Quarto's libraries by relative path, so the library files it
# names are copied into drafts/preregistration_files/ first. An archived draft is
# never overwritten: if drafts/ already holds a file of the same name, the hook
# stops and leaves both where they are.

today <- format(Sys.Date(), "%Y-%m-%d")
prefix <- "InTRACt preregistration draft"
archive <- "drafts"

renamed <- FALSE
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
    renamed <- TRUE
  }
}

# The library files an HTML draft loads, as paths relative to this folder: what
# its href and src attributes name under preregistration_files/, and what those
# stylesheets name in turn through url() (the icon font).
draft_libraries <- function(html) {
  page <- paste(readLines(html, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
  attrs <- regmatches(page, gregexpr("(href|src)=\"preregistration_files/[^\"]+\"", page))[[1]]
  libs <- unique(sub("^(href|src)=\"([^\"]+)\"$", "\\2", attrs))
  for (css in libs[grepl("[.]css$", libs) & file.exists(libs)]) {
    sheet <- paste(readLines(css, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
    urls <- regmatches(sheet, gregexpr("url\\([\"']?[^)\"'#?]+", sheet))[[1]]
    urls <- sub("^url\\([\"']?", "", urls)
    urls <- urls[!grepl("^(data:|https?:|/)", urls)]
    libs <- c(libs, file.path(dirname(css), sub("^[.]/", "", urls)))
  }
  unique(libs)
}

# Only a render of the protocol produces a new draft, so a render of the
# supplement alone archives nothing.
if (renamed) {
  pattern <- paste0("^", prefix, " - [0-9]{4}-[0-9]{2}-[0-9]{2}[.](pdf|html)$")
  older <- list.files(".", pattern = pattern)
  older <- older[!startsWith(older, paste0(prefix, " - ", today, "."))]
  clash <- older[file.exists(file.path(archive, older))]
  if (length(clash)) {
    stop("drafts/ already holds ", paste(clash, collapse = ", "),
         "; an archived draft is never overwritten, so both copies were left in place",
         call. = FALSE)
  }
  for (html in older[grepl("[.]html$", older)]) {
    for (lib in draft_libraries(html)) {
      to <- file.path(archive, lib)
      if (file.exists(to)) next
      if (!file.exists(lib)) {
        stop(html, " loads ", lib, ", which is missing, so it was not archived",
             call. = FALSE)
      }
      dir.create(dirname(to), recursive = TRUE, showWarnings = FALSE)
      if (!file.copy(lib, to)) stop("could not copy ", lib, " to ", to, call. = FALSE)
    }
  }
  dir.create(archive, showWarnings = FALSE)
  for (f in older) {
    if (!file.rename(f, file.path(archive, f))) {
      stop("could not move ", f, " into drafts/ (is it open in a viewer or locked by ",
           "OneDrive?); move it by hand", call. = FALSE)
    }
    message("Archived: ", f, " -> ", file.path(archive, f))
  }
}
