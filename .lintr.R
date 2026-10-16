# lintr configuration for every R script in the repository, read by
# lintr::lint() and lintr::lint_dir() from any folder below this one.
# Run from the repository root: Rscript -e 'lintr::lint_dir(".")'
linters <- lintr::linters_with_defaults(
  # The scripts are written to 100 columns, the width of their long ggplot and
  # simulation calls.
  line_length_linter = lintr::line_length_linter(100),
  # Constants that a script's later lines read are written in capitals
  # (MIN_PT, DESIGN_DIR), everything else in snake_case.
  object_name_linter = lintr::object_name_linter(c("snake_case", "SNAKE_CASE", "symbols")),
  # Two closures update a variable in their enclosing function on purpose: a
  # warning handler sets a flag, and a check records a skipped block.
  assignment_linter = lintr::assignment_linter(operator = c("<-", "<<-")),
  # Every remaining lint from this linter was "no visible binding" for a column
  # name used inside ggplot2::aes() or with(), which the scripts resolve through
  # non-standard evaluation; rewriting them as .data$ would not change behaviour.
  object_usage_linter = NULL
)
encoding <- "UTF-8"
