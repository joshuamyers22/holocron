"""Independent Python outputs for implemented oracle-parity operations."""

from __future__ import annotations

from typing import Literal, cast

from holocron.design import DataDistribution, DesignSpec, RestrictedCubicSplineSpec
from holocron.models import (
    BinaryLogisticResult,
    InferenceEstimate,
    anova,
    bootstrap_covariance,
    contrast,
    covariance,
    fit_glm,
    fit_lrm,
    fit_ols,
    fit_penalized_lrm,
    fit_penalized_ols,
    likelihood,
    predict,
    residuals,
    robust_covariance,
    summarize,
)
from reference.contracts import JsonValue


def spline_column_names(column_count: int) -> list[str]:
    """Return the normalized rms-style names for a univariate spline basis."""
    return ["x" + "'" * index for index in range(column_count)]


def _inference_output(value: InferenceEstimate) -> dict[str, JsonValue]:
    return {
        "name": value.name,
        "estimate": value.estimate,
        "standard_error": value.standard_error,
        "statistic": value.statistic,
        "distribution": value.distribution,
        "degrees_of_freedom": value.degrees_of_freedom,
        "p_value": value.p_value,
        "lower": value.lower,
        "upper": value.upper,
    }


def build_python_output(case: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Compute an implemented case without invoking or importing the R oracle."""
    operation = case["operation"]
    if operation == "design":
        specification = DesignSpec.from_formula(cast(str, case["formula"]))
        raw_variables = cast(list[JsonValue], case["variables"])
        design_data: dict[str, list[float | str]] = {}
        for raw_variable in raw_variables:
            variable = cast(dict[str, JsonValue], raw_variable)
            design_data[cast(str, variable["name"])] = cast(
                list[float | str], variable["values"]
            )
        matrix = specification.transform(design_data)
        formula_document = specification.formula.to_dict()
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "design",
            "formula": specification.formula.expression,
            "response": formula_document["response"],
            "include_intercept": specification.formula.include_intercept,
            "terms": formula_document["terms"],
            "column_names": cast(JsonValue, list(matrix.column_names)),
            "nonlinear_mask": cast(JsonValue, list(matrix.nonlinear_mask)),
            "term_slices": cast(
                JsonValue, [list(value) for value in matrix.term_slices]
            ),
            "design": cast(JsonValue, [list(row) for row in matrix.rows]),
        }
    if operation == "datadist":
        raw_variables = cast(list[JsonValue], case["variables"])
        data: dict[str, list[float | str | None]] = {}
        levels: dict[str, list[float | str]] = {}
        ordered: list[str] = []
        labels: dict[str, str] = {}
        units: dict[str, str | None] = {}
        for raw_variable in raw_variables:
            variable = cast(dict[str, JsonValue], raw_variable)
            name = cast(str, variable["name"])
            data[name] = cast(list[float | str | None], variable["values"])
            labels[name] = cast(str, variable["label"])
            units[name] = cast(str | None, variable["unit"])
            if variable["kind"] in {"categorical", "ordered"}:
                levels[name] = cast(list[float | str], variable["levels"])
            if variable["kind"] == "ordered":
                ordered.append(name)
        raw_effect = cast(list[float], case["effect_quantiles"])
        raw_display = cast(list[float] | None, case["display_quantiles"])
        distribution = DataDistribution.from_data(
            data,
            levels=levels,
            ordered=ordered,
            labels=labels,
            units=units,
            effect_quantiles=(raw_effect[0], raw_effect[1]),
            display_quantiles=(
                None if raw_display is None else (raw_display[0], raw_display[1])
            ),
            categorical_adjustment=cast(
                Literal["mode", "first"], case["categorical_adjustment"]
            ),
            discrete_threshold=cast(int, case["discrete_threshold"]),
        )
        document = distribution.to_dict()
        document.pop("schema_version")
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "datadist",
            **document,
        }

    if operation == "model_operations":
        x = cast(list[float], case["x"])
        y = cast(list[float], case["y"])
        estimator = cast(str, case["estimator"])
        features = tuple((value,) for value in x)
        if estimator == "ols":
            result = fit_ols(y, features, feature_names=("x",))
        elif estimator == "glm-binomial":
            result = fit_glm(y, features, family="binomial", feature_names=("x",))
        else:
            result = fit_lrm(y, features, feature_names=("x",))
        confidence_level = cast(float, case["confidence_level"])
        fit_likelihood = likelihood(result)
        prediction = predict(
            result,
            tuple((value,) for value in cast(list[float], case["evaluation_x"])),
            scale="linear",
            confidence_level=confidence_level,
        )
        fit_summary = summarize(result, confidence_level=confidence_level)
        fit_anova = anova(result, {"x": ("x",)})
        fit_contrast = contrast(
            result,
            cast(list[float], case["contrast_weights"]),
            name="declared contrast",
            confidence_level=confidence_level,
        )
        residual_output: dict[str, JsonValue] = {
            "ordinary": list(
                residuals(
                    result,
                    response=y if isinstance(result, BinaryLogisticResult) else None,
                ).values
            )
        }
        if isinstance(result, BinaryLogisticResult):
            residual_output["pearson"] = list(
                residuals(result, kind="pearson", response=y).values
            )
            residual_output["deviance"] = list(
                residuals(result, kind="deviance", response=y).values
            )
        else:
            residual_output["standardized"] = list(
                residuals(result, kind="standardized").values
            )
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "model_operations",
            "estimator": estimator,
            "evaluation_x": case["evaluation_x"],
            "contrast_weights": case["contrast_weights"],
            "confidence_level": confidence_level,
            "coefficient_names": cast(JsonValue, list(result.coefficient_names)),
            "covariance": cast(
                JsonValue, [list(row) for row in covariance(result).matrix]
            ),
            "likelihood": {
                "log_likelihood": fit_likelihood.log_likelihood,
                "null_log_likelihood": fit_likelihood.null_log_likelihood,
                "parameter_count": fit_likelihood.parameter_count,
                "aic": fit_likelihood.aic,
                "likelihood_ratio": fit_likelihood.likelihood_ratio,
                "degrees_of_freedom": fit_likelihood.degrees_of_freedom,
                "p_value": fit_likelihood.p_value,
            },
            "residuals": residual_output,
            "prediction": {
                "scale": prediction.scale,
                "interval": prediction.interval,
                "confidence_level": prediction.confidence_level,
                "values": list(prediction.values),
                "standard_errors": list(prediction.standard_errors),
                "lower": list(prediction.lower),
                "upper": list(prediction.upper),
            },
            "summary": cast(
                JsonValue,
                [_inference_output(value) for value in fit_summary.coefficients],
            ),
            "anova": cast(
                JsonValue,
                [
                    {
                        "term": value.term,
                        "coefficient_names": list(value.coefficient_names),
                        "statistic": value.statistic,
                        "distribution": value.distribution,
                        "degrees_of_freedom": value.degrees_of_freedom,
                        "denominator_degrees_of_freedom": (
                            value.denominator_degrees_of_freedom
                        ),
                        "p_value": value.p_value,
                    }
                    for value in fit_anova.tests
                ],
            ),
            "contrast": _inference_output(fit_contrast),
        }

    if operation == "regularization_covariance":
        x = cast(list[float], case["x"])
        y = cast(list[float], case["y"])
        features = tuple((value,) for value in x)
        estimator = cast(str, case["estimator"])
        if estimator == "ols":
            result = fit_ols(y, features, feature_names=("x",))
            penalized = fit_penalized_ols(
                y,
                features,
                feature_names=("x",),
                penalty=cast(list[float], case["penalty_weights"])[0],
            )
        elif estimator == "glm-binomial":
            result = fit_glm(y, features, family="binomial", feature_names=("x",))
            penalized = None
        else:
            result = fit_lrm(y, features, feature_names=("x",))
            penalized = fit_penalized_lrm(
                y,
                features,
                feature_names=("x",),
                penalty=cast(list[float], case["penalty_weights"])[0],
            )
        robust = robust_covariance(
            result,
            y,
            features,
            clusters=cast(list[int], case["clusters"]),
        )
        schedule = cast(list[list[int]], case["resample_indices"])
        bootstrap = bootstrap_covariance(
            result,
            y,
            features,
            replicates=len(schedule),
            seed=cast(int, case["bootstrap_seed"]),
            resample_indices=schedule,
        )
        penalized_output: JsonValue = None
        if penalized is not None:
            penalized_output = {
                "coefficients": list(penalized.coefficients),
                "covariance": [list(row) for row in penalized.covariance],
                "linear_predictors": list(penalized.linear_predictors),
                "fitted_values": list(penalized.fitted_values),
                "residuals": list(penalized.residuals),
                "penalty_weights": list(penalized.penalty_weights),
                "effective_degrees_of_freedom": (
                    penalized.effective_degrees_of_freedom
                ),
                "residual_degrees_of_freedom": (penalized.residual_degrees_of_freedom),
                "residual_scale": penalized.residual_scale,
            }
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "regularization_covariance",
            "estimator": estimator,
            "coefficient_names": list(result.coefficient_names),
            "penalized": penalized_output,
            "robust": {
                "matrix": [list(row) for row in robust.matrix],
                "cluster_count": robust.cluster_count,
                "replicate_count": robust.replicate_count,
                "seed": robust.seed,
                "coefficient_mean": (
                    None
                    if robust.coefficient_mean is None
                    else list(robust.coefficient_mean)
                ),
            },
            "bootstrap": {
                "matrix": [list(row) for row in bootstrap.matrix],
                "cluster_count": bootstrap.cluster_count,
                "replicate_count": bootstrap.replicate_count,
                "seed": bootstrap.seed,
                "coefficient_mean": list(bootstrap.coefficient_mean or ()),
            },
        }

    x = cast(list[float], case["x"])
    knots = tuple(cast(list[float], case.get("knots", [])))
    spec: RestrictedCubicSplineSpec | None = None
    if case.get("basis") == "linear":
        basis = [[value] for value in x]
        design_names = ["x"]
    else:
        spec = RestrictedCubicSplineSpec(knots)
        basis = [list(row) for row in spec.transform(x)]
        design_names = spline_column_names(spec.n_columns)

    if operation == "rcs":
        if spec is None:
            raise ValueError("rcs operation requires a spline specification")
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "rcs",
            "x": cast(JsonValue, x),
            "knots": cast(JsonValue, list(spec.knots)),
            "nonlinear_mask": cast(JsonValue, list(spec.nonlinear_mask)),
            "nonlinear_columns": cast(JsonValue, list(spec.nonlinear_columns)),
            "column_names": cast(JsonValue, design_names),
            "basis": cast(JsonValue, basis),
        }

    if operation == "ols_rcs":
        y = cast(list[float], case["y"])
        result = fit_ols(y, basis, feature_names=design_names)
        predictions = result.predict(basis)
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "ols_rcs",
            "knots": cast(JsonValue, list(knots)),
            "coefficient_names": cast(JsonValue, list(result.coefficient_names)),
            "coefficients": {
                name: value
                for name, value in zip(
                    result.coefficient_names, result.coefficients, strict=True
                )
            },
            "covariance_names": cast(JsonValue, list(result.coefficient_names)),
            "covariance": cast(JsonValue, [list(row) for row in result.covariance]),
            "design_names": cast(JsonValue, design_names),
            "design": cast(JsonValue, basis),
            "fitted": cast(JsonValue, list(predictions)),
            "residuals": cast(JsonValue, list(result.residuals)),
            "degrees_of_freedom": result.residual_degrees_of_freedom,
            "sigma": result.residual_scale,
        }

    if operation == "lrm":
        y = cast(list[float], case["y"])
        result = fit_lrm(y, basis, feature_names=design_names)
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "lrm",
            "basis": case["basis"],
            "knots": cast(JsonValue, list(knots)),
            "coefficient_names": cast(JsonValue, list(result.coefficient_names)),
            "coefficients": {
                name: value
                for name, value in zip(
                    result.coefficient_names, result.coefficients, strict=True
                )
            },
            "covariance_names": cast(JsonValue, list(result.coefficient_names)),
            "covariance": cast(JsonValue, [list(row) for row in result.covariance]),
            "design_names": cast(JsonValue, design_names),
            "design": cast(JsonValue, basis),
            "linear_predictors": cast(JsonValue, list(result.linear_predictors)),
            "deviance": cast(JsonValue, list(result.deviance)),
            "response": cast(JsonValue, [int(value) for value in y]),
            "fitted_probability": cast(JsonValue, list(result.fitted_probabilities)),
        }

    if operation == "glm":
        y = cast(list[float], case["y"])
        family = cast(Literal["gaussian", "binomial"], case["family"])
        result = fit_glm(
            y,
            basis,
            family=family,
            feature_names=design_names,
        )
        if isinstance(result, BinaryLogisticResult):
            linear_predictors = result.linear_predictors
            fitted_mean = result.fitted_probabilities
            deviance = result.deviance
        else:
            linear_predictors = result.fitted_values
            fitted_mean = result.fitted_values
            response_mean = sum(y) / len(y)
            null_deviance = sum((value - response_mean) ** 2 for value in y)
            residual_deviance = sum(value**2 for value in result.residuals)
            deviance = (null_deviance, residual_deviance)
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "glm",
            "basis": case["basis"],
            "knots": cast(JsonValue, list(knots)),
            "family": case["family"],
            "link": case["link"],
            "coefficient_names": cast(JsonValue, list(result.coefficient_names)),
            "coefficients": {
                name: value
                for name, value in zip(
                    result.coefficient_names, result.coefficients, strict=True
                )
            },
            "covariance_names": cast(JsonValue, list(result.coefficient_names)),
            "covariance": cast(JsonValue, [list(row) for row in result.covariance]),
            "design_names": cast(JsonValue, design_names),
            "design": cast(JsonValue, basis),
            "linear_predictors": cast(JsonValue, list(linear_predictors)),
            "deviance": cast(JsonValue, list(deviance)),
            "response": cast(JsonValue, y),
            "fitted_mean": cast(JsonValue, list(fitted_mean)),
        }

    raise ValueError(f"no independent Python parity implementation for {operation}")
