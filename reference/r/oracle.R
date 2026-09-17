#!/usr/bin/env Rscript

protocol_version <- "1"

matrix_rows <- function(value) {
  if (is.null(dim(value))) value <- matrix(value, ncol = 1L)
  unname(lapply(seq_len(nrow(value)), function(index) {
    unname(as.numeric(value[index, , drop = TRUE]))
  }))
}

named_numbers <- function(value) {
  values <- as.numeric(value)
  names(values) <- names(value)
  as.list(values)
}

read_request <- function() {
  text <- paste(readLines(file("stdin"), warn = FALSE), collapse = "\n")
  if (!nzchar(text)) stop("oracle request must be a non-empty JSON object")
  jsonlite::fromJSON(text, simplifyVector = TRUE)
}

require_numeric_vector <- function(request, name, minimum_length = 1L) {
  value <- request[[name]]
  if (is.null(value) || !is.numeric(value) || length(value) < minimum_length) {
    stop(sprintf("%s must be a numeric vector with at least %d values", name, minimum_length))
  }
  if (any(!is.finite(value))) stop(sprintf("%s must contain only finite values", name))
  as.numeric(value)
}

run_health <- function() {
  packages <- c(
    "rms", "Hmisc", "survival", "Matrix", "SparseM", "quantreg",
    "ggplot2", "polspline", "multcomp", "jsonlite"
  )
  versions <- stats::setNames(
    lapply(packages, function(package) as.character(utils::packageVersion(package))),
    packages
  )
  list(
    protocol_version = protocol_version,
    operation = "health",
    r_version = R.version.string,
    platform = R.version$platform,
    packages = versions,
    locale = Sys.getlocale(),
    timezone = Sys.timezone()
  )
}

run_rcs <- function(request) {
  x <- require_numeric_vector(request, "x", 1L)
  knots <- require_numeric_vector(request, "knots", 3L)
  if (is.unsorted(knots, strictly = TRUE)) {
    stop("knots must be strictly increasing")
  }
  basis <- rms::rcs(x = x, parms = knots)
  nonlinear <- as.logical(attr(basis, "nonlinear"))
  list(
    protocol_version = protocol_version,
    operation = "rcs",
    x = x,
    knots = as.numeric(attr(basis, "parms")),
    nonlinear_mask = unname(nonlinear),
    nonlinear_columns = as.integer(which(nonlinear) - 1L),
    column_names = colnames(basis),
    basis = matrix_rows(basis)
  )
}

run_ols_rcs <- function(request) {
  x <- require_numeric_vector(request, "x", 3L)
  y <- require_numeric_vector(request, "y", 3L)
  knots <- require_numeric_vector(request, "knots", 3L)
  if (length(x) != length(y)) stop("x and y must have equal lengths")
  if (is.unsorted(knots, strictly = TRUE)) stop("knots must be strictly increasing")

  data <- data.frame(x = x, y = y)
  fit <- rms::ols(y ~ rms::rcs(x, knots), data = data, x = TRUE, y = TRUE)
  covariance <- stats::vcov(fit)
  predictions <- stats::predict(fit, newdata = data, type = "lp")
  list(
    protocol_version = protocol_version,
    operation = "ols_rcs",
    knots = knots,
    coefficient_names = names(stats::coef(fit)),
    coefficients = named_numbers(stats::coef(fit)),
    covariance_names = colnames(covariance),
    covariance = matrix_rows(covariance),
    design_names = colnames(fit$x),
    design = matrix_rows(fit$x),
    fitted = unname(as.numeric(predictions)),
    residuals = unname(as.numeric(stats::residuals(fit))),
    degrees_of_freedom = unname(as.numeric(fit$df.residual)),
    sigma = unname(as.numeric(fit$stats["Sigma"]))
  )
}

dispatch <- function(request) {
  operation <- request$operation
  if (is.null(operation) || length(operation) != 1L || !is.character(operation)) {
    stop("operation must be one string")
  }
  switch(
    operation,
    health = run_health(),
    rcs = run_rcs(request),
    ols_rcs = run_ols_rcs(request),
    stop(sprintf("unsupported operation: %s", operation))
  )
}

status <- 0L
response <- tryCatch(
  {
    request <- read_request()
    c(list(ok = TRUE), dispatch(request))
  },
  error = function(error) {
    status <<- 1L
    list(ok = FALSE, protocol_version = protocol_version, error = conditionMessage(error))
  }
)

jsonlite::write_json(
  response,
  path = stdout(),
  auto_unbox = TRUE,
  digits = 17,
  null = "null",
  pretty = TRUE
)
cat("\n")
quit(status = status, save = "no")
