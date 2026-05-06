today <- format(Sys.Date(), "%Y-%m-%d")
prefix <- "InTRACt preregistration draft"

for (ext in c("pdf", "html")) {
  src <- paste0("preregistration.", ext)
  dst <- paste0(prefix, " - ", today, ".", ext)
  if (file.exists(src)) {
    file.rename(src, dst)
    message("Renamed: ", src, " -> ", dst)
  }
}
