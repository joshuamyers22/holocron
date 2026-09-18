#!/usr/bin/env Rscript

protocol_version <- "1"

suppressPackageStartupMessages(library(rms))

matrix_rows <- function(value) {
  if (is.null(dim(value))) value <- matrix(value, ncol = 1L)
  unname(lapply(seq_len(nrow(value)), function(index) {
    unname(as.list(as.numeric(value[index, , drop = TRUE])))
  }))
}

name_vector <- function(value) unname(as.list(as.character(value)))
numeric_vector <- function(value) unname(as.list(as.numeric(value)))

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

require_censor_endpoint <- function(request, name, lower = TRUE) {
  value <- request[[name]]
  if (is.null(value) || length(value) < 3L) {
    stop(sprintf("%s must contain at least three censoring endpoints", name))
  }
  text <- as.character(value)
  sentinel <- if (lower) "neg_inf" else "pos_inf"
  parsed <- suppressWarnings(as.numeric(text))
  parsed[text == sentinel] <- if (lower) -Inf else Inf
  if (any(is.na(parsed)) || any(text == if (lower) "pos_inf" else "neg_inf")) {
    stop(sprintf("%s contains an invalid censoring endpoint", name))
  }
  parsed
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
    lapply(value, function(column) {
      if (is.data.frame(column)) {
        lapply(column[index, , drop = FALSE], function(item) item[[1L]])
      } else column[[index]]
    })
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

design_level_name <- function(value) {
  if (is.character(value)) as.character(jsonlite::toJSON(value, auto_unbox = TRUE))
  else design_number_name(value)
}

design_one_term <- function(value) {
  if (!is.data.frame(value)) return(value)
  lapply(value, function(column) column[[1L]])
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
    values <- unlist(spec$values, use.names = FALSE)
    if (!length(values) || (!is.numeric(values) && !is.character(values)) ||
        (is.numeric(values) && any(!is.finite(values))) ||
        (is.character(values) && any(!nzchar(values)))) {
      stop(sprintf("%s values must be a non-empty finite numeric or string vector", name))
    }
    variables[[name]] <- values
  }
  require_equal_lengths(variables, names(variables))
  terms <- design_term_specs(request$terms)
  if (!length(terms)) stop("design terms must not be empty")
  transform_main <- function(raw_term) {
    term <- design_one_term(raw_term)
    kind <- require_choice(
      term, "kind", c(
        "identity", "polynomial", "linear_spline", "restricted_cubic_spline",
        "categorical", "ordered"
      )
    )
    variable <- term$variable
    if (is.null(variable) || length(variable) != 1L || !is.character(variable) ||
        !variable %in% names(variables)) {
      stop("design term references an unknown variable")
    }
    x <- unlist(variables[[variable]], use.names = FALSE)
    displayed <- design_variable_name(variable)
    if (kind == "identity") {
      if (!is.numeric(x)) stop("identity values must be numeric")
      transformed <- rms::asis(x)
      block <- matrix(as.numeric(transformed), ncol = 1L)
      names <- sprintf("asis(%s)", displayed)
      flags <- FALSE
      normalized <- list(kind = kind, variable = variable)
    } else if (kind == "polynomial") {
      if (!is.numeric(x)) stop("polynomial values must be numeric")
      degree <- term$degree
      if (is.null(degree) || length(degree) != 1L || !is.numeric(degree) ||
          degree != as.integer(degree) || degree < 2L) stop("invalid polynomial degree")
      transformed <- rms::pol(x, as.integer(degree))
      block <- unclass(transformed)
      attributes(block) <- list(dim = dim(block))
      names <- sprintf("pol(%s,%d)", displayed, seq_len(as.integer(degree)))
      flags <- seq_len(as.integer(degree)) > 1L
      normalized <- list(kind = kind, variable = variable, degree = as.integer(degree))
    } else if (kind %in% c("linear_spline", "restricted_cubic_spline")) {
      if (!is.numeric(x)) stop("spline values must be numeric")
      knots <- unlist(term$knots, use.names = FALSE)
      minimum <- if (kind == "linear_spline") 1L else 3L
      if (!is.numeric(knots) || length(knots) < minimum || any(!is.finite(knots)) ||
          is.unsorted(knots, strictly = TRUE)) stop("invalid spline knots")
      if (kind == "linear_spline") {
        transformed <- rms::lsp(x, knots)
        block <- unclass(transformed)
        attributes(block) <- list(dim = dim(block))
        names <- c(
          sprintf("lsp(%s,linear)", displayed),
          vapply(knots, function(knot) sprintf(
            "lsp(%s,knot=%s)", displayed, design_number_name(knot)
          ), character(1L))
        )
      } else {
        transformed <- rms::rcs(x, knots)
        block <- unclass(transformed)
        attributes(block) <- list(dim = dim(block))
        names <- c(
          sprintf("rcs(%s,linear)", displayed),
          sprintf("rcs(%s,nonlinear=%d)", displayed, seq_len(ncol(block) - 1L))
        )
      }
      flags <- c(FALSE, rep(TRUE, ncol(block) - 1L))
      normalized <- list(kind = kind, variable = variable, knots = unname(as.list(knots)))
    } else {
      levels <- unlist(term$levels, use.names = FALSE)
      policy <- require_choice(term, "unknown_level", c("error"))
      if (kind == "categorical") {
        transformed <- rms::catg(x, levels)
        codes <- unclass(transformed)
        attributes(codes) <- NULL
        block <- vapply(
          seq.int(2L, length(levels)),
          function(level) as.numeric(codes == level),
          numeric(length(codes))
        )
        if (is.null(dim(block))) block <- matrix(block, ncol = 1L)
        names <- vapply(
          levels[-1L],
          function(level) sprintf(
            "catg(%s,level=%s)", displayed, design_level_name(level)
          ),
          character(1L)
        )
        flags <- rep(FALSE, ncol(block))
      } else {
        if (!is.numeric(x) || !is.numeric(levels)) {
          stop("ordered values and levels must be numeric")
        }
        transformed <- rms::scored(x, levels)
        block <- cbind(
          as.numeric(x),
          vapply(
            levels[-c(1L, 2L)],
            function(level) as.numeric(x == level),
            numeric(length(x))
          )
        )
        names <- c(
          sprintf("scored(%s,linear)", displayed),
          vapply(
            levels[-c(1L, 2L)],
            function(level) sprintf(
              "scored(%s,level=%s)", displayed, design_number_name(level)
            ),
            character(1L)
          )
        )
        flags <- c(FALSE, rep(TRUE, ncol(block) - 1L))
      }
      normalized <- list(
        kind = kind,
        variable = variable,
        levels = unname(as.list(levels)),
        unknown_level = policy
      )
    }
    list(
      block = block,
      names = names,
      nonlinear = flags,
      normalized = normalized,
      source = transformed
    )
  }

  transform_term <- function(raw_term) {
    term <- design_one_term(raw_term)
    if (!identical(term$kind, "restricted_interaction")) return(transform_main(term))
    left <- transform_main(term$left)
    right <- transform_main(term$right)
    names <- character()
    flags <- logical()
    column <- 0L
    for (left_index in seq_len(ncol(left$block))) {
      for (right_index in seq_len(ncol(right$block))) {
        if (left$nonlinear[left_index] && right$nonlinear[right_index]) next
        column <- column + 1L
        names[column] <- sprintf(
          "ia(%s,%s)", left$names[left_index], right$names[right_index]
        )
        flags[column] <- left$nonlinear[left_index] || right$nonlinear[right_index]
      }
    }
    block <- unclass(rms::`%ia%`(left$source, right$source))
    attributes(block) <- list(dim = dim(block))
    if (ncol(block) != column) stop("rms restricted interaction width differs")
    list(
      block = block,
      names = names,
      nonlinear = flags,
      normalized = list(
        kind = "restricted_interaction",
        left = left$normalized,
        right = right$normalized
      )
    )
  }

  blocks <- list()
  normalized_terms <- list()
  column_names <- character()
  nonlinear <- logical()
  term_slices <- list()
  start <- 0L
  for (index in seq_along(terms)) {
    transformed <- transform_term(terms[[index]])
    block <- transformed$block
    blocks[[index]] <- block
    normalized_terms[[index]] <- transformed$normalized
    column_names <- c(column_names, transformed$names)
    nonlinear <- c(nonlinear, transformed$nonlinear)
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

run_glm <- function(request) {
  x <- require_numeric_vector(request, "x", 3L)
  y <- require_numeric_vector(request, "y", 3L)
  require_equal_lengths(list(x, y), c("x", "y"))
  basis <- require_choice(request, "basis", c("linear", "rcs"))
  family_name <- require_choice(request, "family", c("gaussian", "binomial"))
  link <- require_choice(request, "link", c("identity", "logit"))
  if (family_name == "gaussian" && link != "identity") {
    stop("gaussian Glm requires identity link")
  }
  if (family_name == "binomial") {
    if (link != "logit") stop("binomial Glm requires logit link")
    y <- require_binary_vector(request, "y")
  }
  knots <- model_knots(request, basis)
  data <- data.frame(x = x, y = y)
  family <- if (family_name == "gaussian") {
    stats::gaussian(link = link)
  } else {
    stats::binomial(link = link)
  }
  fit <- rms::Glm(
    model_formula("y", basis), data = data, family = family, x = TRUE, y = TRUE
  )
  if (!isTRUE(fit$converged)) stop("Glm failed to converge")
  covariance <- stats::vcov(fit)
  list(
    protocol_version = protocol_version,
    operation = "glm",
    basis = basis,
    knots = knots,
    family = family_name,
    link = link,
    coefficient_names = name_vector(names(stats::coef(fit))),
    coefficients = named_numbers(stats::coef(fit)),
    covariance_names = covariance_names(fit, covariance),
    covariance = matrix_rows(covariance),
    design_names = name_vector(colnames(fit$x)),
    design = matrix_rows(fit$x),
    linear_predictors = unname(as.numeric(fit$linear.predictors)),
    deviance = unname(as.numeric(c(fit$null.deviance, fit$deviance))),
    response = unname(as.numeric(y)),
    fitted_mean = unname(as.numeric(fit$fitted.values))
  )
}

inference_contract <- function(name, estimate, variance, distribution,
                               degrees_of_freedom, confidence_level) {
  standard_error <- sqrt(variance)
  statistic <- estimate / standard_error
  probability <- (1 + confidence_level) / 2
  if (distribution == "t") {
    critical <- stats::qt(probability, degrees_of_freedom)
    p_value <- 2 * stats::pt(-abs(statistic), degrees_of_freedom)
    reported_degrees <- as.integer(degrees_of_freedom)
  } else {
    critical <- stats::qnorm(probability)
    p_value <- 2 * stats::pnorm(-abs(statistic))
    reported_degrees <- NULL
  }
  list(
    name = name,
    estimate = unname(as.numeric(estimate)),
    standard_error = unname(as.numeric(standard_error)),
    statistic = unname(as.numeric(statistic)),
    distribution = distribution,
    degrees_of_freedom = reported_degrees,
    p_value = unname(as.numeric(p_value)),
    lower = unname(as.numeric(estimate - critical * standard_error)),
    upper = unname(as.numeric(estimate + critical * standard_error))
  )
}

run_model_operations <- function(request) {
  x <- require_numeric_vector(request, "x", 3L)
  y <- require_numeric_vector(request, "y", 3L)
  evaluation_x <- require_numeric_vector(request, "evaluation_x", 1L)
  require_equal_lengths(list(x, y), c("x", "y"))
  estimator <- require_choice(
    request, "estimator", c("ols", "glm-binomial", "lrm-binary")
  )
  if (estimator != "ols") y <- require_binary_vector(request, "y")
  confidence_level <- request$confidence_level
  if (is.null(confidence_level) || length(confidence_level) != 1L ||
      !is.numeric(confidence_level) || !is.finite(confidence_level) ||
      confidence_level <= 0 || confidence_level >= 1) {
    stop("confidence_level must be between 0 and 1")
  }
  weights <- require_numeric_vector(request, "contrast_weights", 2L)
  if (length(weights) != 2L || !identical(as.numeric(weights), c(0, 1))) {
    stop("contrast_weights must declare the one-unit x contrast [0, 1]")
  }
  data <- data.frame(x = x, y = y)
  fit <- switch(
    estimator,
    ols = rms::ols(y ~ x, data = data, x = TRUE, y = TRUE),
    `glm-binomial` = rms::Glm(
      y ~ x, data = data, family = stats::binomial(), x = TRUE, y = TRUE
    ),
    `lrm-binary` = rms::lrm(y ~ x, data = data, x = TRUE, y = TRUE)
  )
  coefficients <- stats::coef(fit)
  covariance <- stats::vcov(fit)
  coefficient_names <- name_vector(names(coefficients))
  maximum <- unname(as.numeric(stats::logLik(fit)))
  if (estimator == "ols") {
    null_maximum <- unname(as.numeric(stats::logLik(stats::lm(y ~ 1, data = data))))
    null_parameters <- 2L
  } else if (estimator == "glm-binomial") {
    null_maximum <- -0.5 * unname(as.numeric(fit$null.deviance))
    null_parameters <- 1L
  } else {
    null_maximum <- -0.5 * unname(as.numeric(fit$deviance[1]))
    null_parameters <- 1L
  }
  parameter_count <- as.integer(attr(stats::logLik(fit), "df"))
  likelihood_degrees <- parameter_count - null_parameters
  likelihood_ratio <- max(0, 2 * (maximum - null_maximum))
  likelihood <- list(
    log_likelihood = maximum,
    null_log_likelihood = null_maximum,
    parameter_count = parameter_count,
    aic = 2 * parameter_count - 2 * maximum,
    likelihood_ratio = likelihood_ratio,
    degrees_of_freedom = likelihood_degrees,
    p_value = stats::pchisq(
      likelihood_ratio, likelihood_degrees, lower.tail = FALSE
    )
  )

  if (estimator == "ols") {
    ordinary <- unname(as.numeric(stats::residuals(fit)))
    residual_output <- list(
      ordinary = ordinary,
      standardized = ordinary / unname(as.numeric(fit$stats["Sigma"]))
    )
  } else if (estimator == "glm-binomial") {
    residual_output <- list(
      ordinary = unname(as.numeric(stats::residuals(fit, type = "response"))),
      pearson = unname(as.numeric(stats::residuals(fit, type = "pearson"))),
      deviance = unname(as.numeric(stats::residuals(fit, type = "deviance")))
    )
  } else {
    residual_output <- list(
      ordinary = unname(as.numeric(stats::residuals(fit, type = "ordinary"))),
      pearson = unname(as.numeric(stats::residuals(fit, type = "pearson"))),
      deviance = unname(as.numeric(stats::residuals(fit, type = "deviance")))
    )
  }

  predicted <- stats::predict(
    fit,
    newdata = data.frame(x = evaluation_x),
    type = "lp",
    se.fit = TRUE,
    conf.int = confidence_level
  )
  prediction <- list(
    scale = "linear",
    interval = "mean",
    confidence_level = confidence_level,
    values = unname(as.numeric(predicted$linear.predictors)),
    standard_errors = unname(as.numeric(predicted$se.fit)),
    lower = unname(as.numeric(predicted$lower)),
    upper = unname(as.numeric(predicted$upper))
  )

  distribution <- if (estimator == "lrm-binary") "normal" else "t"
  inference_degrees <- if (distribution == "t") fit$df.residual else NULL
  coefficient_summary <- lapply(seq_along(coefficients), function(index) {
    inference_contract(
      names(coefficients)[index], coefficients[index], covariance[index, index],
      distribution, inference_degrees, confidence_level
    )
  })

  slope_indices <- seq.int(2L, length(coefficients))
  anova_reference <- stats::anova(fit, x)
  if (estimator == "ols") {
    anova_statistic <- unname(as.numeric(anova_reference[1, "F"]))
    anova_distribution <- "f"
    denominator_degrees <- as.integer(fit$df.residual)
  } else {
    anova_statistic <- unname(as.numeric(anova_reference[1, "Chi-Square"]))
    anova_distribution <- "chi-square"
    denominator_degrees <- NULL
  }
  anova_p <- unname(as.numeric(anova_reference[1, "P"]))
  anova_output <- list(list(
    term = "x",
    coefficient_names = name_vector(names(coefficients)[slope_indices]),
    statistic = anova_statistic,
    distribution = anova_distribution,
    degrees_of_freedom = length(slope_indices),
    denominator_degrees_of_freedom = denominator_degrees,
    p_value = unname(as.numeric(anova_p))
  ))

  contrast_reference <- rms::contrast(
    fit, list(x = 1), list(x = 0), conf.int = confidence_level
  )
  contrast_output <- list(
    name = "declared contrast",
    estimate = unname(as.numeric(contrast_reference$Contrast)),
    standard_error = unname(as.numeric(contrast_reference$SE)),
    statistic = unname(as.numeric(
      contrast_reference$Contrast / contrast_reference$SE
    )),
    distribution = distribution,
    degrees_of_freedom = if (distribution == "t") {
      as.integer(contrast_reference$df.residual)
    } else NULL,
    p_value = unname(as.numeric(contrast_reference$Pvalue)),
    lower = unname(as.numeric(contrast_reference$Lower)),
    upper = unname(as.numeric(contrast_reference$Upper))
  )

  list(
    protocol_version = protocol_version,
    operation = "model_operations",
    estimator = estimator,
    evaluation_x = evaluation_x,
    contrast_weights = weights,
    confidence_level = confidence_level,
    coefficient_names = coefficient_names,
    covariance = matrix_rows(covariance),
    likelihood = likelihood,
    residuals = residual_output,
    prediction = prediction,
    summary = coefficient_summary,
    anova = anova_output,
    contrast = contrast_output
  )
}

run_regularization_covariance <- function(request) {
  x <- require_numeric_vector(request, "x", 3L)
  y <- require_numeric_vector(request, "y", 3L)
  require_equal_lengths(list(x, y), c("x", "y"))
  estimator <- require_choice(
    request, "estimator", c("ols", "glm-binomial", "lrm-binary")
  )
  if (estimator != "ols") y <- require_binary_vector(request, "y")
  clusters <- request$clusters
  if (is.null(clusters) || !is.numeric(clusters) || length(clusters) != length(y) ||
      any(!is.finite(clusters))) stop("clusters must match the analysis rows")
  seed <- request$bootstrap_seed
  if (is.null(seed) || length(seed) != 1L || !is.numeric(seed) || seed < 0) {
    stop("bootstrap_seed must be a non-negative scalar")
  }
  schedule <- request$resample_indices
  if (is.matrix(schedule)) {
    schedule <- lapply(seq_len(nrow(schedule)), function(index) schedule[index, ])
  }
  if (!is.list(schedule) || length(schedule) < 2L ||
      any(vapply(schedule, length, integer(1)) != length(y))) {
    stop("resample_indices must be a bootstrap schedule")
  }
  if (any(unlist(schedule) < 0) || any(unlist(schedule) >= length(y))) {
    stop("resample index is outside the analysis rows")
  }
  data <- data.frame(x = x, y = y)
  fit_model <- function(x_values, y_values) {
    sample_data <- data.frame(x = x_values, y = y_values)
    switch(
      estimator,
      ols = rms::ols(y ~ x, data = sample_data, x = TRUE, y = TRUE),
      `glm-binomial` = rms::Glm(
        y ~ x, data = sample_data, family = stats::binomial(), x = TRUE, y = TRUE
      ),
      `lrm-binary` = rms::lrm(y ~ x, data = sample_data, x = TRUE, y = TRUE)
    )
  }
  fit <- fit_model(x, y)
  coefficient_names <- name_vector(names(stats::coef(fit)))

  penalty_weights <- request$penalty_weights
  penalized_output <- NULL
  if (estimator != "glm-binomial") {
    if (is.null(penalty_weights) || !is.numeric(penalty_weights) ||
        length(penalty_weights) != 1L || any(penalty_weights <= 0)) {
      stop("penalty_weights must contain one positive slope penalty")
    }
    penalty_matrix <- matrix(penalty_weights, nrow = 1L, ncol = 1L)
    penalized_fit <- if (estimator == "ols") {
      rms::ols(
        y ~ x, data = data, x = TRUE, y = TRUE, penalty = 1,
        penalty.matrix = penalty_matrix, var.penalty = "simple"
      )
    } else {
      rms::lrm(
        y ~ x, data = data, x = TRUE, y = TRUE, penalty = 1,
        penalty.matrix = penalty_matrix
      )
    }
    penalized_linear <- unname(as.numeric(penalized_fit$linear.predictors))
    penalized_fitted <- if (estimator == "ols") {
      penalized_linear
    } else stats::plogis(penalized_linear)
    penalized_residuals <- if (estimator == "ols") {
      unname(as.numeric(penalized_fit$residuals))
    } else y - penalized_fitted
    penalized_output <- list(
      coefficients = unname(as.numeric(stats::coef(penalized_fit))),
      covariance = matrix_rows(stats::vcov(penalized_fit)),
      linear_predictors = penalized_linear,
      fitted_values = unname(as.numeric(penalized_fitted)),
      residuals = unname(as.numeric(penalized_residuals)),
      penalty_weights = numeric_vector(penalty_weights),
      effective_degrees_of_freedom = unname(as.numeric(
        sum(penalized_fit$effective.df.diagonal)
      )),
      residual_degrees_of_freedom = if (estimator == "ols") {
        unname(as.numeric(penalized_fit$df.residual))
      } else NULL,
      residual_scale = if (estimator == "ols") {
        unname(as.numeric(penalized_fit$stats["Sigma"]))
      } else NULL
    )
  }

  robust_fit <- rms::robcov(fit, cluster = clusters)
  robust_output <- list(
    matrix = matrix_rows(stats::vcov(robust_fit)),
    cluster_count = length(unique(clusters)),
    replicate_count = NULL,
    seed = NULL,
    coefficient_mean = NULL
  )

  bootstrap_coefficients <- t(vapply(schedule, function(indices) {
    positions <- as.integer(unlist(indices)) + 1L
    unname(as.numeric(stats::coef(fit_model(x[positions], y[positions]))))
  }, numeric(length(stats::coef(fit)))))
  bootstrap_output <- list(
    matrix = matrix_rows(stats::cov(bootstrap_coefficients)),
    cluster_count = NULL,
    replicate_count = length(schedule),
    seed = as.integer(seed),
    coefficient_mean = unname(as.numeric(colMeans(bootstrap_coefficients)))
  )

  list(
    protocol_version = protocol_version,
    operation = "regularization_covariance",
    estimator = estimator,
    coefficient_names = coefficient_names,
    penalized = penalized_output,
    robust = robust_output,
    bootstrap = bootstrap_output
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

run_orm_censored <- function(request) {
  x <- require_numeric_vector(request, "x", 3L)
  lower <- require_censor_endpoint(request, "lower", TRUE)
  upper <- require_censor_endpoint(request, "upper", FALSE)
  require_equal_lengths(list(x, lower, upper), c("x", "lower", "upper"))
  if (any(lower > upper) || any(lower == Inf) || any(upper == -Inf)) {
    stop("censoring intervals are invalid")
  }
  family <- require_choice(
    request, "family", c("logistic", "probit", "loglog", "cloglog", "cauchit")
  )
  y <- rms::Ocens(lower, upper)
  converted <- rms::Ocens2ord(y)
  data <- data.frame(x = x)
  fit <- rms::orm(y ~ x, data = data, family = family, x = TRUE, y = TRUE)
  if (isTRUE(fit$fail)) stop("censored orm failed to converge")
  probabilities <- stats::predict(fit, newdata = data, type = "fitted.ind")
  npsurv <- attr(converted, "npsurv")
  support_lower <- unname(as.numeric(attr(converted, "levels")))
  support_upper <- attr(converted, "upper")
  if (is.null(support_upper)) support_upper <- support_lower
  support_upper <- unname(as.numeric(support_upper))
  survival <- unname(as.numeric(npsurv$surv))
  masses <- survival - c(survival[-1L], 0)
  kinds <- ifelse(
    lower == upper, "exact",
    ifelse(is.infinite(lower), "left", ifelse(is.infinite(upper), "right", "interval"))
  )
  c(
    fit_contract(fit, "orm_censored", "linear", numeric()),
    list(
      family = family,
      censoring_types = name_vector(kinds),
      response_levels = unname(as.numeric(fit$yunique)),
      turnbull_lower = support_lower,
      turnbull_upper = support_upper,
      turnbull_probabilities = unname(as.numeric(masses)),
      turnbull_survival = survival,
      probability_names = name_vector(colnames(probabilities)),
      fitted_probabilities = matrix_rows(probabilities)
    )
  )
}

run_orm_random <- function(request) {
  x <- require_numeric_vector(request, "x", 3L)
  y <- require_numeric_vector(request, "y", 3L)
  clusters <- require_numeric_vector(request, "clusters", 3L)
  require_equal_lengths(list(x, y, clusters), c("x", "y", "clusters"))
  family <- require_choice(
    request, "family", c("logistic", "probit", "loglog", "cloglog", "cauchit")
  )
  grid <- as.integer(require_numeric_vector(request, "quadrature_grid", 2L))
  tolerance <- as.numeric(request$quadrature_tolerance)
  if (length(tolerance) != 1L || !is.finite(tolerance) || tolerance <= 0) {
    stop("quadrature_tolerance must be a positive number")
  }
  mix <- request$mix_re
  data <- data.frame(x = x, y = y, cluster_id = clusters)
  if (is.null(mix)) {
    formula <- y ~ x + cluster(cluster_id)
  } else {
    mix <- as.numeric(mix)
    require_equal_lengths(list(x, mix), c("x", "mix_re"))
    data$mix_value <- mix
    formula <- y ~ x + cluster(cluster_id) + mix_re(mix_value)
  }
  fit <- rms::orm(
    formula, data = data, family = family, x = TRUE, y = TRUE,
    nAGQ.grid = grid, nAGQ.tol = tolerance
  )
  if (isTRUE(fit$fail)) stop("random-effects orm failed to converge")
  parameters <- stats::coef(fit)
  parameter_names <- names(parameters)
  if (!is.null(mix)) parameter_names[parameter_names == "log(sigma)"] <- "log(sigma1)"
  names(parameters) <- parameter_names
  covariance <- stats::vcov(fit, intercepts = "all")
  covariance_names_value <- colnames(covariance)
  if (!is.null(mix)) covariance_names_value[covariance_names_value == "log(sigma)"] <- "log(sigma1)"
  list(
    protocol_version = protocol_version,
    operation = "orm_random",
    basis = "linear",
    family = family,
    parameter_names = name_vector(parameter_names),
    parameters = named_numbers(parameters),
    covariance_names = name_vector(covariance_names_value),
    covariance = matrix_rows(covariance),
    response_levels = unname(as.numeric(fit$yunique)),
    linear_predictors = unname(as.numeric(fit$linear.predictors)),
    deviance = unname(tail(as.numeric(fit$deviance), 2L)),
    cluster_count = length(unique(clusters)),
    sigma = if (is.null(mix)) unname(as.numeric(fit$sigma)) else NULL,
    sigma1 = if (is.null(mix)) NULL else unname(as.numeric(fit$sigma1)),
    sigma2 = if (is.null(mix)) NULL else unname(as.numeric(fit$sigma2))
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
    glm = run_glm(request),
    model_operations = run_model_operations(request),
    regularization_covariance = run_regularization_covariance(request),
    orm = run_orm(request),
    orm_censored = run_orm_censored(request),
    orm_random = run_orm_random(request),
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
