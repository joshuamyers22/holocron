#!/usr/bin/env Rscript

protocol_version <- "1"

matrix_rows <- function(value) {
  if (is.null(dim(value))) value <- matrix(value, ncol = 1L)
  unname(lapply(seq_len(nrow(value)), function(index) {
    unname(as.list(as.numeric(value[index, , drop = TRUE])))
  }))
}

name_vector <- function(value) unname(as.list(as.character(value)))

covariance_names <- function(fit, covariance) {
  value <- colnames(covariance)
  if (is.null(value) && ncol(covariance) == length(stats::coef(fit))) {
    value <- names(stats::coef(fit))
  }
  name_vector(value)
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

require_choice <- function(request, name, choices) {
  value <- request[[name]]
  if (is.null(value) || length(value) != 1L || !is.character(value) ||
      !value %in% choices) {
    stop(sprintf("%s must be one of: %s", name, paste(choices, collapse = ", ")))
  }
  value
}

require_binary_vector <- function(request, name) {
  value <- require_numeric_vector(request, name, 3L)
  if (any(!value %in% c(0, 1)) || length(unique(value)) != 2L) {
    stop(sprintf("%s must contain both 0 and 1", name))
  }
  as.integer(value)
}

require_equal_lengths <- function(values, names) {
  lengths <- vapply(values, length, integer(1L))
  if (length(unique(lengths)) != 1L) {
    stop(sprintf("%s must have equal lengths", paste(names, collapse = ", ")))
  }
}

model_formula <- function(response, basis, survival = FALSE) {
  left <- if (survival) "survival::Surv(time, event)" else response
  right <- if (basis == "linear") "x" else "rms::rcs(x, knots)"
  stats::as.formula(sprintf("%s ~ %s", left, right), env = parent.frame())
}

model_knots <- function(request, basis) {
  if (basis == "linear") return(numeric())
  knots <- require_numeric_vector(request, "knots", 3L)
  if (is.unsorted(knots, strictly = TRUE)) stop("knots must be strictly increasing")
  knots
}

fit_contract <- function(fit, operation, basis, knots) {
  covariance <- stats::vcov(fit)
  list(
    protocol_version = protocol_version,
    operation = operation,
    basis = basis,
    knots = knots,
    coefficient_names = name_vector(names(stats::coef(fit))),
    coefficients = named_numbers(stats::coef(fit)),
    covariance_names = covariance_names(fit, covariance),
    covariance = matrix_rows(covariance),
    design_names = name_vector(colnames(fit$x)),
    design = matrix_rows(fit$x),
    linear_predictors = unname(as.numeric(fit$linear.predictors)),
    deviance = unname(as.numeric(fit$deviance))
  )
}

run_health <- function() {
  installed <- utils::installed.packages()
  packages <- sort(rownames(installed))
  versions <- stats::setNames(
    lapply(packages, function(package) as.character(installed[package, "Version"])),
    packages
  )
  external <- base::extSoftVersion()
  loadNamespace("rms")
  fortran <- getDLLRegisteredRoutines("rms")[[".Fortran"]]
  registered_fortran <- stats::setNames(
    lapply(fortran, function(routine) as.integer(routine$numParameters)),
    names(fortran)
  )
  list(
    protocol_version = protocol_version,
    operation = "health",
    r_version = R.version.string,
    platform = R.version$platform,
    packages = versions,
    package_repository = Sys.getenv("RSPM"),
    repositories = as.list(getOption("repos")),
    external_libraries = as.list(unname(external)),
    external_library_names = names(external),
    rng_kind = unname(as.list(RNGkind())),
    registered_fortran = registered_fortran,
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
    nonlinear_columns = unname(as.list(as.integer(which(nonlinear) - 1L))),
    column_names = name_vector(colnames(basis)),
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
    coefficient_names = name_vector(names(stats::coef(fit))),
    coefficients = named_numbers(stats::coef(fit)),
    covariance_names = covariance_names(fit, covariance),
    covariance = matrix_rows(covariance),
    design_names = name_vector(colnames(fit$x)),
    design = matrix_rows(fit$x),
    fitted = unname(as.numeric(predictions)),
    residuals = unname(as.numeric(stats::residuals(fit))),
    degrees_of_freedom = unname(as.numeric(fit$df.residual)),
    sigma = unname(as.numeric(fit$stats["Sigma"]))
  )
}

distribution_specs <- function(value) {
  if (!is.data.frame(value)) return(value)
  lapply(seq_len(nrow(value)), function(index) {
    lapply(value, function(column) column[[index]])
  })
}

distribution_scalar <- function(value) {
  if (length(value) != 1L || is.na(value)) return(NA)
  if (is.factor(value) || is.character(value)) as.character(value) else as.numeric(value)
}

distribution_range <- function(limits, lower, upper) {
  unname(list(distribution_scalar(limits[lower]), distribution_scalar(limits[upper])))
}

run_datadist <- function(request) {
  specs <- distribution_specs(request$variables)
  if (!length(specs)) stop("variables must not be empty")
  columns <- list()
  seen <- character()
  for (spec in specs) {
    name <- spec$name
    kind <- require_choice(spec, "kind", c("numeric", "categorical", "ordered"))
    if (is.null(name) || length(name) != 1L || !is.character(name) || !nzchar(name)) {
      stop("distribution variable name must be one non-empty string")
    }
    if (name %in% seen) stop(sprintf("duplicate distribution variable: %s", name))
    seen <- c(seen, name)
    values <- spec$values
    if (kind == "numeric") {
      if (!is.numeric(values)) stop(sprintf("%s values must be numeric", name))
      columns[[name]] <- as.numeric(values)
    } else {
      levels <- unlist(spec$levels, use.names = FALSE)
      if (length(levels) < 2L) stop(sprintf("%s requires at least two levels", name))
      columns[[name]] <- factor(
        unlist(values, use.names = FALSE),
        levels = levels,
        ordered = kind == "ordered"
      )
    }
  }
  require_equal_lengths(columns, names(columns))
  data <- as.data.frame(columns, check.names = FALSE, optional = TRUE)
  effect <- require_numeric_vector(request, "effect_quantiles", 2L)
  if (length(effect) != 2L) stop("effect_quantiles must contain two values")
  adjustment <- require_choice(request, "categorical_adjustment", c("mode", "first"))
  threshold <- request$discrete_threshold
  if (is.null(threshold) || length(threshold) != 1L || !is.numeric(threshold) ||
      threshold < 1L || threshold != as.integer(threshold)) {
    stop("discrete_threshold must be a positive integer")
  }
  arguments <- list(
    data,
    q.effect = effect,
    adjto.cat = adjustment,
    n.unique = as.integer(threshold)
  )
  display <- request$display_quantiles
  if (!is.null(display)) {
    if (!is.numeric(display) || length(display) != 2L) {
      stop("display_quantiles must be null or contain two values")
    }
    arguments$q.display <- as.numeric(display)
  }
  result <- do.call(rms::datadist, arguments)
  variables <- lapply(seq_along(specs), function(index) {
    spec <- specs[[index]]
    name <- spec$name
    input_kind <- spec$kind
    limits <- result$limits[[name]]
    retained <- result$values[[name]]
    kind <- if (input_kind == "numeric") {
      if (is.null(retained)) "continuous" else "discrete"
    } else input_kind
    list(
      name = name,
      kind = kind,
      adjustment = distribution_scalar(limits[2]),
      effect_range = if (kind == "categorical") NA else distribution_range(limits, 1, 3),
      display_range = distribution_range(limits, 4, 5),
      overall_range = distribution_range(limits, 6, 7),
      values = if (is.null(retained)) list() else unname(as.list(retained)),
      label = spec$label,
      unit = if (is.null(spec$unit)) NA_character_ else spec$unit,
      nonmissing_count = as.integer(sum(!is.na(columns[[name]]))),
      missing_count = as.integer(sum(is.na(columns[[name]])))
    )
  })
  list(
    protocol_version = protocol_version,
    operation = "datadist",
    observation_count = as.integer(nrow(data)),
    effect_quantiles = unname(as.list(effect)),
    display_quantiles = if (is.null(display)) NA else unname(as.list(display)),
    categorical_adjustment = adjustment,
    discrete_threshold = as.integer(threshold),
    variables = variables
  )
}

design_term_specs <- function(value) {
  if (!is.data.frame(value)) return(value)
  lapply(seq_len(nrow(value)), function(index) {
    lapply(value, function(column) column[[index]])
  })
}

design_variable_name <- function(value) {
  if (grepl("^[[:alpha:]_][[:alnum:]_]*$", value) &&
      !value %in% c("asis", "pol", "lsp", "rcs")) return(value)
  paste0("`", gsub("`", "``", value, fixed = TRUE), "`")
}

design_number_name <- function(value) {
  if (value == as.integer(value)) paste0(as.integer(value), ".0")
  else format(value, digits = 17, scientific = FALSE, trim = TRUE)
}

run_design <- function(request) {
  variable_specs <- distribution_specs(request$variables)
  if (!length(variable_specs)) stop("design variables must not be empty")
  variables <- list()
  for (spec in variable_specs) {
    name <- spec$name
    if (is.null(name) || length(name) != 1L || !is.character(name) || !nzchar(name)) {
      stop("design variable name must be one non-empty string")
    }
    if (name %in% names(variables)) stop(sprintf("duplicate design variable: %s", name))
    values <- spec$values
    if (!is.numeric(values) || !length(values) || any(!is.finite(values))) {
      stop(sprintf("%s values must be a non-empty finite numeric vector", name))
    }
    variables[[name]] <- as.numeric(values)
  }
  require_equal_lengths(variables, names(variables))
  terms <- design_term_specs(request$terms)
  if (!length(terms)) stop("design terms must not be empty")
  blocks <- list()
  normalized_terms <- list()
  column_names <- character()
  nonlinear <- logical()
  term_slices <- list()
  start <- 0L
  for (index in seq_along(terms)) {
    term <- terms[[index]]
    kind <- require_choice(
      term, "kind", c("identity", "polynomial", "linear_spline", "restricted_cubic_spline")
    )
    variable <- term$variable
    if (is.null(variable) || length(variable) != 1L || !is.character(variable) ||
        !variable %in% names(variables)) {
      stop("design term references an unknown variable")
    }
    x <- variables[[variable]]
    displayed <- design_variable_name(variable)
    if (kind == "identity") {
      block <- matrix(as.numeric(rms::asis(x)), ncol = 1L)
      names <- sprintf("asis(%s)", displayed)
      flags <- FALSE
      normalized <- list(kind = kind, variable = variable)
    } else if (kind == "polynomial") {
      degree <- term$degree
      if (is.null(degree) || length(degree) != 1L || !is.numeric(degree) ||
          degree != as.integer(degree) || degree < 2L) stop("invalid polynomial degree")
      block <- unclass(rms::pol(x, as.integer(degree)))
      attributes(block) <- list(dim = dim(block))
      names <- sprintf("pol(%s,%d)", displayed, seq_len(as.integer(degree)))
      flags <- seq_len(as.integer(degree)) > 1L
      normalized <- list(kind = kind, variable = variable, degree = as.integer(degree))
    } else {
      knots <- unlist(term$knots, use.names = FALSE)
      minimum <- if (kind == "linear_spline") 1L else 3L
      if (!is.numeric(knots) || length(knots) < minimum || any(!is.finite(knots)) ||
          is.unsorted(knots, strictly = TRUE)) stop("invalid spline knots")
      if (kind == "linear_spline") {
        block <- unclass(rms::lsp(x, knots))
        attributes(block) <- list(dim = dim(block))
        names <- c(
          sprintf("lsp(%s,linear)", displayed),
          vapply(knots, function(knot) sprintf(
            "lsp(%s,knot=%s)", displayed, design_number_name(knot)
          ), character(1L))
        )
      } else {
        block <- unclass(rms::rcs(x, knots))
        attributes(block) <- list(dim = dim(block))
        names <- c(
          sprintf("rcs(%s,linear)", displayed),
          sprintf("rcs(%s,nonlinear=%d)", displayed, seq_len(ncol(block) - 1L))
        )
      }
      flags <- c(FALSE, rep(TRUE, ncol(block) - 1L))
      normalized <- list(kind = kind, variable = variable, knots = unname(as.list(knots)))
    }
    blocks[[index]] <- block
    normalized_terms[[index]] <- normalized
    column_names <- c(column_names, names)
    nonlinear <- c(nonlinear, flags)
    stop_column <- start + ncol(block)
    term_slices[[index]] <- unname(list(start, stop_column))
    start <- stop_column
  }
  design <- do.call(cbind, blocks)
  list(
    protocol_version = protocol_version,
    operation = "design",
    formula = request$formula,
    response = request$response,
    include_intercept = request$include_intercept,
    terms = normalized_terms,
    column_names = name_vector(column_names),
    nonlinear_mask = unname(as.list(nonlinear)),
    term_slices = term_slices,
    design = matrix_rows(design)
  )
}

run_lrm <- function(request) {
  x <- require_numeric_vector(request, "x", 3L)
  y <- require_binary_vector(request, "y")
  require_equal_lengths(list(x, y), c("x", "y"))
  basis <- require_choice(request, "basis", c("linear", "rcs"))
  knots <- model_knots(request, basis)
  data <- data.frame(x = x, y = y)
  fit <- rms::lrm(model_formula("y", basis), data = data, x = TRUE, y = TRUE)
  if (isTRUE(fit$fail)) stop("lrm failed to converge")
  c(
    fit_contract(fit, "lrm", basis, knots),
    list(
      response = y,
      fitted_probability = unname(as.numeric(stats::predict(
        fit, newdata = data, type = "fitted"
      )))
    )
  )
}

run_orm <- function(request) {
  x <- require_numeric_vector(request, "x", 3L)
  y <- require_numeric_vector(request, "y", 3L)
  require_equal_lengths(list(x, y), c("x", "y"))
  if (length(unique(y)) < 3L) stop("ordinal y must contain at least three levels")
  basis <- require_choice(request, "basis", c("linear", "rcs"))
  family <- require_choice(
    request, "family", c("logistic", "probit", "loglog", "cloglog", "cauchit")
  )
  knots <- model_knots(request, basis)
  data <- data.frame(x = x, y = y)
  fit <- rms::orm(
    model_formula("y", basis), data = data, family = family, x = TRUE, y = TRUE
  )
  if (isTRUE(fit$fail)) stop("orm failed to converge")
  probabilities <- stats::predict(fit, newdata = data, type = "fitted.ind")
  c(
    fit_contract(fit, "orm", basis, knots),
    list(
      family = family,
      response = y,
      response_levels = unname(as.numeric(fit$yunique)),
      probability_names = name_vector(colnames(probabilities)),
      fitted_probabilities = matrix_rows(probabilities)
    )
  )
}

run_cph <- function(request) {
  x <- require_numeric_vector(request, "x", 3L)
  time <- require_numeric_vector(request, "time", 3L)
  event <- require_binary_vector(request, "event")
  evaluation_x <- require_numeric_vector(request, "evaluation_x", 1L)
  evaluation_times <- require_numeric_vector(request, "evaluation_times", 1L)
  require_equal_lengths(list(x, time, event), c("x", "time", "event"))
  if (any(time <= 0) || any(evaluation_times <= 0)) stop("survival times must be positive")
  basis <- require_choice(request, "basis", c("linear", "rcs"))
  method <- require_choice(request, "method", c("efron", "breslow"))
  knots <- model_knots(request, basis)
  data <- data.frame(x = x, time = time, event = event)
  fit <- rms::cph(
    model_formula("", basis, survival = TRUE),
    data = data,
    method = method,
    x = TRUE,
    y = TRUE,
    surv = TRUE
  )
  if (isTRUE(fit$fail)) stop("cph failed to converge")
  new_data <- data.frame(x = evaluation_x)
  evaluation_lp <- unname(as.numeric(stats::predict(fit, newdata = new_data, type = "lp")))
  survival_function <- rms::Survival(fit)
  predicted_survival <- lapply(evaluation_lp, function(lp) {
    unname(as.numeric(survival_function(evaluation_times, lp)))
  })
  covariance <- stats::vcov(fit)
  list(
    protocol_version = protocol_version,
    operation = "cph",
    basis = basis,
    knots = knots,
    method = method,
    coefficient_names = name_vector(names(stats::coef(fit))),
    coefficients = named_numbers(stats::coef(fit)),
    covariance_names = covariance_names(fit, covariance),
    covariance = matrix_rows(covariance),
    design_names = name_vector(colnames(fit$x)),
    design = matrix_rows(fit$x),
    linear_predictors = unname(as.numeric(fit$linear.predictors)),
    log_likelihood = unname(as.numeric(fit$loglik)),
    evaluation_x = evaluation_x,
    evaluation_linear_predictors = evaluation_lp,
    evaluation_times = evaluation_times,
    predicted_survival = predicted_survival
  )
}

run_psm <- function(request) {
  x <- require_numeric_vector(request, "x", 3L)
  time <- require_numeric_vector(request, "time", 3L)
  event <- require_binary_vector(request, "event")
  evaluation_x <- require_numeric_vector(request, "evaluation_x", 1L)
  evaluation_times <- require_numeric_vector(request, "evaluation_times", 1L)
  require_equal_lengths(list(x, time, event), c("x", "time", "event"))
  if (any(time <= 0) || any(evaluation_times <= 0)) stop("survival times must be positive")
  basis <- require_choice(request, "basis", c("linear", "rcs"))
  distribution <- require_choice(request, "distribution", c("weibull", "exponential"))
  knots <- model_knots(request, basis)
  data <- data.frame(x = x, time = time, event = event)
  fit <- rms::psm(
    model_formula("", basis, survival = TRUE),
    data = data,
    dist = distribution,
    x = TRUE,
    y = TRUE
  )
  if (isTRUE(fit$fail)) stop("psm failed to converge")
  new_data <- data.frame(x = evaluation_x)
  evaluation_lp <- unname(as.numeric(stats::predict(fit, newdata = new_data, type = "lp")))
  survival_function <- rms::Survival(fit)
  predicted_survival <- lapply(evaluation_lp, function(lp) {
    unname(as.numeric(survival_function(evaluation_times, lp)))
  })
  covariance <- stats::vcov(fit)
  list(
    protocol_version = protocol_version,
    operation = "psm",
    basis = basis,
    knots = knots,
    distribution = distribution,
    coefficient_names = name_vector(names(stats::coef(fit))),
    coefficients = named_numbers(stats::coef(fit)),
    covariance_names = covariance_names(fit, covariance),
    covariance = matrix_rows(covariance),
    design_names = name_vector(colnames(fit$x)),
    design = matrix_rows(fit$x),
    linear_predictors = unname(as.numeric(fit$linear.predictors)),
    log_likelihood = unname(as.numeric(fit$loglik)),
    scale = unname(as.numeric(fit$scale)),
    evaluation_x = evaluation_x,
    evaluation_linear_predictors = evaluation_lp,
    evaluation_times = evaluation_times,
    predicted_survival = predicted_survival
  )
}

run_npsurv <- function(request) {
  time <- require_numeric_vector(request, "time", 3L)
  event <- require_binary_vector(request, "event")
  require_equal_lengths(list(time, event), c("time", "event"))
  if (any(time <= 0)) stop("survival times must be positive")
  estimator <- require_choice(request, "estimator", c("kaplan-meier"))
  data <- data.frame(time = time, event = event)
  fit <- rms::npsurv(
    survival::Surv(time, event) ~ 1, data = data
  )
  list(
    protocol_version = protocol_version,
    operation = "npsurv",
    estimator = estimator,
    observations = unname(as.numeric(fit$n)),
    time = unname(as.numeric(fit$time)),
    n_risk = unname(as.numeric(fit$n.risk)),
    n_event = unname(as.numeric(fit$n.event)),
    n_censor = unname(as.numeric(fit$n.censor)),
    survival = unname(as.numeric(fit$surv)),
    standard_error = unname(as.numeric(fit$std.err)),
    lower = unname(as.numeric(fit$lower)),
    upper = unname(as.numeric(fit$upper))
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
    datadist = run_datadist(request),
    design = run_design(request),
    lrm = run_lrm(request),
    orm = run_orm(request),
    cph = run_cph(request),
    psm = run_psm(request),
    npsurv = run_npsurv(request),
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
