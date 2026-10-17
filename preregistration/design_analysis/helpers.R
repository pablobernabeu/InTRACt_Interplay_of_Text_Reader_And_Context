# Helpers shared by the design-analysis scripts, which source this file from the
# preregistration directory. Keeping one copy of each stops the copies drifting
# apart, as the solver's note once did between scripts.

# The ordinal sweep's region of practical equivalence, an odds ratio between
# 1/1.05 and 1.05, and its true effect, about twice the region's half-width on
# the log-odds scale. run_ordinal_analysis.R simulates with them and
# summarise_ordinal.R projects from them.
ORD_ROPE   <- log(1.05)
ORD_TRUE_B <- 0.10

# Stops at once if a package that a script needs only indirectly is missing.
# pilotr fits every replicate with lme4 but lists it only as a suggested
# package, so nothing would otherwise load it before the first fit, and renv
# would leave it out of the lockfile. The literal requireNamespace() calls in
# the scripts are what renv reads.
need_package <- function(ok, pkg, why) {
  if (!ok) stop(pkg, " is required: ", why, call. = FALSE)
  invisible(TRUE)
}

# Timestamped progress line on stdout.
msg <- function(...) {
  cat(format(Sys.time(), "%H:%M:%S"), " ", ..., "\n", sep = "")
  flush.console()
}

# A setting read from an environment variable. A mistyped value stops the run
# with its name, instead of becoming NA and surfacing later as a sweep of NA
# rows that reads as 'not reached'.
env_number <- function(name, default, integer = TRUE, min = 1, max = Inf) {
  raw <- Sys.getenv(name, default)
  pattern <- if (integer) "^[0-9]+$" else "^[0-9]*[.]?[0-9]+$"
  if (!grepl(pattern, raw))
    stop(name, " must be a ", if (integer) "whole number" else "number", ", not '", raw, "'",
         call. = FALSE)
  x <- as.numeric(raw)
  if (x < min || x > max) stop(name, " must lie between ", min, " and ", max, call. = FALSE)
  if (integer) as.integer(x) else x
}

# A comma-separated list of numbers from an environment variable.
env_numbers <- function(name, default, min = 0, max = Inf) {
  raw <- strsplit(Sys.getenv(name, default), ",")[[1]]
  if (!length(raw) || !all(grepl("^[0-9]*[.]?[0-9]+$", trimws(raw))))
    stop(name, " must be a comma-separated list of numbers, not '", Sys.getenv(name, default),
         "'", call. = FALSE)
  x <- as.numeric(trimws(raw))
  if (any(x < min | x > max)) stop(name, " values must lie between ", min, " and ", max,
                                   call. = FALSE)
  x
}

# Wilson score 95 per cent interval for the proportion k/n, the Monte Carlo
# uncertainty of a decision probability, clamped to [0, 1] against rounding.
wilson <- function(k, n, z = 1.959964) {
  if (n == 0) return(c(NA_real_, NA_real_))
  p <- k / n
  centre <- p + z^2 / (2 * n)
  half <- z * sqrt(p * (1 - p) / n + z^2 / (4 * n^2))
  pmin(1, pmax(0, c(centre - half, centre + half) / (1 + z^2 / n)))
}

# Solves one curve of decision probabilities for the swept value at which it
# reaches `target`, with pilotr::solve_curve, which fits a probit curve on the
# square root of the swept value and never extrapolates. A curve that fails to
# solve has one of two statuses. 'not reached' means no grid point reaches the
# target. 'not determined' means some point does but the fit cannot place the
# crossing, which happens with too few replicates per point; the note then
# carries pilotr's reason and a warning is raised, so the failure is never
# reported as 'not reached'.
solve_at <- function(x, p, n_returned, target) {
  frame <- data.frame(x = x, p_meaningful = p, n_returned = n_returned)
  frame <- frame[order(frame$x), ]
  out <- tryCatch(pilotr::solve_curve(frame, target = target), error = function(e) e)
  if (!inherits(out, "error"))
    return(list(value = out$value, lo = out$lo, hi = out$hi, note = "", status = "solved"))
  if (max(p, na.rm = TRUE) < target)
    return(list(value = NA_real_, lo = NA_real_, hi = NA_real_,
                note = paste0("not reached within ", min(x), " to ", max(x)),
                status = "not reached"))
  warning("a curve reaches ", target, " but could not be solved: ", conditionMessage(out),
          call. = FALSE)
  list(value = NA_real_, lo = NA_real_, hi = NA_real_,
       note = paste0("not determined: ", conditionMessage(out)), status = "not determined")
}

# Each sweep runs every coefficient at one size, keeping the specification's
# signs. A zero coefficient has no sign to keep, so it would silently stay zero
# while the sweep is labelled with the effect size; it stops the run instead.
at_effect <- function(spec, value, keep_sign = TRUE) {
  co <- spec$fixed$coefficients
  if (keep_sign && any(unlist(co) == 0))
    stop("a coefficient is zero in the specification, so it has no sign to keep: ",
         paste(names(co)[unlist(co) == 0], collapse = ", "), call. = FALSE)
  for (nm in names(co)) co[[nm]] <- if (keep_sign) sign(co[[nm]]) * value else value
  spec$fixed$coefficients <- co
  spec
}

# The focal parameters of a sweep, with their true values taken from the
# (modified) specification. pilotr names an interaction column with an
# underscore where the specification uses a colon.
focal_from <- function(spec, params) {
  co <- unlist(spec$fixed$coefficients)
  names(co) <- gsub(":", "_", names(co), fixed = TRUE)
  if (!all(params %in% names(co)))
    stop("not in the specification: ", paste(setdiff(params, names(co)), collapse = ", "),
         call. = FALSE)
  co[params]
}

# Grid points expressed as whole `units` objects, because a sweep over the
# number of texts has to move the number of readers with it to hold readings
# per text.
units_by_texts <- function(texts, per_text) {
  lapply(texts, function(k) {
    list(subject = list(n = k * per_text), item = list(n = k, per_subject = 1))
  })
}

# Labels each row of a sweep_spec() result with its grid value. pilotr's lead
# column holds the grid point: its index when the grid is a list of `units`
# objects, and the value itself when it is a vector. The shape is checked
# exactly, so a grid point that returned fewer rows cannot shift the labels.
label_grid <- function(res, values, axis_values, focal) {
  stopifnot(nrow(res) == length(values) * length(focal),
            all(table(res[[1]]) == length(focal)))
  if (is.list(values)) axis_values[res[[1]]] else res[[1]]
}

# Probes once whether a PSOCK cluster starts, since one can fail on Windows and
# losing an hour of fitting to that is not acceptable; if it fails, every sweep
# runs serially. After a successful probe, pilotr starts a fresh cluster at each
# grid point, and a failure there is not caught.
make_worker_probe <- function(workers) {
  checked <- NULL
  function() {
    if (!is.null(checked)) return(checked)
    if (workers <= 1) {
      checked <<- 1L
      return(1L)
    }
    ok <- tryCatch({
      cl <- parallel::makePSOCKcluster(workers)
      parallel::stopCluster(cl)
      TRUE
    }, error = function(e) {
      msg("cluster setup failed, running serially: ", conditionMessage(e))
      FALSE
    })
    checked <<- if (ok) workers else 1L
    checked
  }
}

# A cached result is reused only if the settings that produced it match the
# current ones. Each cache file has a key file beside it, <name>.key.json,
# recording those settings: the specification, the grid, the focal effects, the
# formula, the region and the replicate count. Package versions are not part of
# the key; the session records written with the results give them. A cache with
# a different key stops the run, and one with no key stops it too, unless
# INTRACT_ADOPT_CACHE=1 says it was produced with the current settings.
cache_key <- function(...) {
  as.character(jsonlite::toJSON(list(...), auto_unbox = TRUE, digits = NA, null = "null",
                                pretty = TRUE))
}

key_path <- function(path) sub("[.]csv$", ".key.json", path)

cache_read <- function(path, key) {
  if (!file.exists(path)) return(NULL)
  kf <- key_path(path)
  if (!file.exists(kf)) {
    if (!identical(Sys.getenv("INTRACT_ADOPT_CACHE"), "1"))
      stop(basename(path), " has no key file, so the settings behind it are unknown. ",
           "Delete it to re-run that step, or set INTRACT_ADOPT_CACHE=1 if it was produced ",
           "with the current settings.", call. = FALSE)
    writeLines(key, kf)
    msg("recorded the key of ", basename(path))
  } else if (!identical(readLines(kf, warn = FALSE), strsplit(key, "\n", fixed = TRUE)[[1]])) {
    stop(basename(path), " was produced with other settings than the current ones (see ",
         basename(kf), "). Delete both files to re-run that step.", call. = FALSE)
  }
  msg("cached: ", basename(path))
  utils::read.csv(path, stringsAsFactors = FALSE)
}

# Returns the result as read back from the file, so that a run which computes a
# sweep passes on exactly what a later run reading it from cache would: the
# string "0.10" in memory becomes the number 0.1 on reading, and the outputs
# would otherwise depend on whether the cache existed.
cache_write <- function(x, path, key) {
  utils::write.csv(x, path, row.names = FALSE)
  writeLines(key, key_path(path))
  msg("  wrote ", path)
  utils::read.csv(path, stringsAsFactors = FALSE)
}

# The session record, written only by a run that computed something, so that a
# run reading every result from cache cannot overwrite the record of the run
# that produced them.
write_session <- function(path, header) {
  writeLines(c(paste("run:", format(Sys.time(), "%Y-%m-%d %H:%M:%S")), header, "",
               utils::capture.output(utils::sessionInfo())), path)
  msg("wrote ", path)
}
