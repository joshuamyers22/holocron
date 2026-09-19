"""Independent Python outputs for implemented oracle-parity operations."""

from __future__ import annotations

from typing import Literal, cast

from holocron.design import DataDistribution, DesignSpec, RestrictedCubicSplineSpec
from holocron.models import (
    BinaryLogisticResult,
    CensoredResponse,
    InferenceEstimate,
    SurvivalResponse,
    anova,
    bootstrap_covariance,
    contrast,
    covariance,
    fit_cph,
    fit_glm,
    fit_lrm,
    fit_npsurv,
    fit_ols,
    fit_orm,
    fit_penalized_lrm,
    fit_penalized_ols,
    fit_psm,
    fit_random_intercept_orm,
    likelihood,
    predict,
    residuals,
    robust_covariance,
    summarize,
    survival_residuals,
    validate_survival_predictions,
)
from holocron.validation import validate_probabilities
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
    if operation == "probability_validation":
        result = validate_probabilities(
            cast(list[int], case["outcomes"]),
            cast(list[float], case["probabilities"]),
        )
        assert result.unreliability_index is not None
        assert result.quality_index is not None
        assert result.unreliability_chi_square is not None
        assert result.unreliability_p_value is not None
        assert result.calibration_intercept is not None
        assert result.calibration_slope is not None
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "probability_validation",
            "auc": result.auc,
            "dxy": result.dxy,
            "brier_score": result.brier_score,
            "scaled_brier_score": result.scaled_brier_score,
            "log_loss": result.log_loss,
            "null_log_loss": result.null_log_loss,
            "nagelkerke_r_squared": result.nagelkerke_r_squared,
            "discrimination_index": result.discrimination_index,
            "unreliability_index": result.unreliability_index,
            "quality_index": result.quality_index,
            "likelihood_ratio_chi_square": result.likelihood_ratio_chi_square,
            "likelihood_ratio_p_value": result.likelihood_ratio_p_value,
            "unreliability_chi_square": result.unreliability_chi_square,
            "unreliability_p_value": result.unreliability_p_value,
            "calibration_intercept": result.calibration_intercept,
            "calibration_slope": result.calibration_slope,
            "spiegelhalter_z": result.spiegelhalter_z,
            "spiegelhalter_p_value": result.spiegelhalter_p_value,
            "prevalence": result.prevalence,
            "mean_prediction": result.mean_prediction,
            "calibration_in_the_large": result.calibration_in_the_large,
            "observations": result.n_observations,
        }
    if operation == "survival_validation":
        result = validate_survival_predictions(
            cast(list[float], case["time"]),
            cast(list[int], case["event"]),
            cast(list[list[float]], case["predicted_survival"]),
            cast(list[float], case["horizons"]),
            weights=cast(list[float] | None, case.get("weights")),
        )
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "survival_validation",
            "horizons": cast(JsonValue, list(result.horizons)),
            "brier_scores": cast(JsonValue, list(result.brier_scores)),
            "aucs": cast(JsonValue, list(result.aucs)),
            "dxy": cast(JsonValue, list(result.dxy)),
            "observed_survival": cast(JsonValue, list(result.observed_survival)),
            "mean_predicted_survival": cast(
                JsonValue, list(result.mean_predicted_survival)
            ),
            "calibration_errors": cast(JsonValue, list(result.calibration_errors)),
            "censoring_survival": cast(JsonValue, list(result.censoring_survival)),
            "case_counts": cast(JsonValue, list(result.case_counts)),
            "control_counts": cast(JsonValue, list(result.control_counts)),
            "integrated_brier_score": result.integrated_brier_score,
            "observations": result.n_observations,
            "total_weight": result.total_weight,
        }
    if operation == "npsurv":
        result = fit_npsurv(
            cast(list[float], case["time"]),
            cast(list[int], case["event"]),
            entry_times=cast(list[float] | None, case.get("entry")),
            strata=cast(list[str] | None, case.get("strata")),
            weights=cast(list[float] | None, case.get("weights")),
        )
        output: dict[str, JsonValue] = {
            "ok": True,
            "protocol_version": "1",
            "operation": "npsurv",
            "estimator": "kaplan-meier",
            "observations": result.n_observations,
            "time": cast(JsonValue, list(result.time)),
            "n_risk": cast(JsonValue, list(result.n_risk)),
            "n_event": cast(JsonValue, list(result.n_event)),
            "n_censor": cast(JsonValue, list(result.n_censor)),
            "survival": cast(JsonValue, list(result.survival)),
            "standard_error": cast(JsonValue, list(result.standard_error)),
            "lower": cast(JsonValue, list(result.lower)),
            "upper": cast(JsonValue, list(result.upper)),
        }
        if any(name in case for name in ("entry", "strata", "weights")):
            output.update(
                entry=case.get("entry"),
                strata=cast(JsonValue, list(result.strata)),
                weights=case.get("weights"),
            )
        if "evaluation_probabilities" in case:
            evaluation_times = cast(list[float], case["evaluation_times"])
            probabilities = cast(list[float], case["evaluation_probabilities"])
            restricted_time = float(cast(int | float, case["restricted_time"]))
            output.update(
                evaluation_times=cast(JsonValue, evaluation_times),
                predicted_survival=cast(
                    JsonValue, [list(result.predict(evaluation_times))]
                ),
                evaluation_probabilities=cast(JsonValue, probabilities),
                restricted_time=restricted_time,
                predicted_quantiles=cast(
                    JsonValue, [list(result.predict_quantile(probabilities)[0])]
                ),
                predicted_mean=cast(
                    JsonValue,
                    list(result.predict_mean(restricted_time=restricted_time)),
                ),
            )
        return output
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

    if operation == "cph":
        entry = cast(list[float] | None, case.get("entry"))
        strata = cast(list[str] | None, case.get("strata"))
        weights = cast(list[float] | None, case.get("weights"))
        offset = cast(list[float] | None, case.get("offset"))
        result = fit_cph(
            cast(list[float], case["time"]),
            cast(list[int], case["event"]),
            basis,
            method=cast(Literal["efron", "breslow"], case["method"]),
            feature_names=design_names,
            entry_times=entry,
            strata=strata,
            weights=weights,
            offsets=offset,
        )
        evaluation_x = cast(list[float], case["evaluation_x"])
        evaluation_basis = (
            [[value] for value in evaluation_x]
            if spec is None
            else [list(row) for row in spec.transform(evaluation_x)]
        )
        evaluation_strata = cast(list[str] | None, case.get("evaluation_strata"))
        evaluation_offset = cast(list[float] | None, case.get("evaluation_offset"))
        evaluation_linear = result.predict_linear(
            evaluation_basis, offsets=evaluation_offset
        )
        survival = result.predict_survival(
            evaluation_basis,
            cast(list[float], case["evaluation_times"]),
            strata=evaluation_strata,
            offsets=evaluation_offset,
        )
        output = {
            "ok": True,
            "protocol_version": "1",
            "operation": "cph",
            "basis": case["basis"],
            "knots": cast(JsonValue, list(knots)),
            "method": result.method,
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
            "log_likelihood": cast(JsonValue, list(result.log_likelihood)),
            "evaluation_x": cast(JsonValue, evaluation_x),
            "evaluation_linear_predictors": cast(JsonValue, list(evaluation_linear)),
            "evaluation_times": case["evaluation_times"],
            "predicted_survival": cast(JsonValue, [list(row) for row in survival]),
        }
        if "evaluation_probabilities" in case:
            probabilities = cast(list[float], case["evaluation_probabilities"])
            restricted_time = float(cast(int | float, case["restricted_time"]))
            output.update(
                evaluation_probabilities=cast(JsonValue, probabilities),
                restricted_time=restricted_time,
                predicted_quantiles=cast(
                    JsonValue,
                    [
                        list(row)
                        for row in result.predict_quantile(
                            evaluation_basis,
                            probabilities,
                            strata=evaluation_strata,
                            offsets=evaluation_offset,
                        )
                    ],
                ),
                predicted_mean=cast(
                    JsonValue,
                    list(
                        result.predict_mean(
                            evaluation_basis,
                            restricted_time=restricted_time,
                            strata=evaluation_strata,
                            offsets=evaluation_offset,
                        )
                    ),
                ),
            )
        if any(
            name in case
            for name in (
                "entry",
                "strata",
                "weights",
                "offset",
                "evaluation_strata",
                "evaluation_offset",
            )
        ):
            output.update(
                entry=case.get("entry"),
                strata=case.get("strata"),
                weights=case.get("weights"),
                offset=case.get("offset"),
                evaluation_strata=case.get("evaluation_strata"),
                evaluation_offset=case.get("evaluation_offset"),
                baseline_strata=cast(JsonValue, list(result.baseline_strata)),
                baseline_times=cast(JsonValue, list(result.baseline_times)),
                baseline_hazard=cast(JsonValue, list(result.baseline_hazard)),
                baseline_cumulative_hazard=cast(
                    JsonValue, list(result.baseline_cumulative_hazard)
                ),
                baseline_survival=cast(JsonValue, list(result.baseline_survival)),
                martingale_residuals=cast(
                    JsonValue,
                    list(
                        survival_residuals(
                            result,
                            cast(list[float], case["time"]),
                            cast(list[int], case["event"]),
                            entry_times=entry,
                            strata=strata,
                        ).values
                    ),
                ),
                deviance_residuals=cast(
                    JsonValue,
                    list(
                        survival_residuals(
                            result,
                            cast(list[float], case["time"]),
                            cast(list[int], case["event"]),
                            kind="deviance",
                            entry_times=entry,
                            strata=strata,
                        ).values
                    ),
                ),
            )
        return output

    if operation == "psm":
        strata = cast(list[str] | None, case.get("strata"))
        weights = cast(list[float] | None, case.get("weights"))
        offset = cast(list[float] | None, case.get("offset"))
        if "lower" in case:

            def endpoint(value: JsonValue) -> float:
                if value == "neg_inf":
                    return float("-inf")
                if value == "pos_inf":
                    return float("inf")
                return float(cast(int | float, value))

            lower = tuple(
                endpoint(value) for value in cast(list[JsonValue], case["lower"])
            )
            upper = tuple(
                endpoint(value) for value in cast(list[JsonValue], case["upper"])
            )
            response = SurvivalResponse.from_intervals(lower, upper)
            result = fit_psm(
                response,
                basis,
                distribution=cast(
                    Literal["weibull", "exponential"], case["distribution"]
                ),
                feature_names=design_names,
                strata=strata,
                weights=weights,
                offsets=offset,
            )
        else:
            response = None
            result = fit_psm(
                cast(list[float], case["time"]),
                cast(list[int], case["event"]),
                basis,
                distribution=cast(
                    Literal["weibull", "exponential"], case["distribution"]
                ),
                feature_names=design_names,
                strata=strata,
                weights=weights,
                offsets=offset,
            )
        evaluation_x = cast(list[float], case["evaluation_x"])
        evaluation_basis = (
            [[value] for value in evaluation_x]
            if spec is None
            else [list(row) for row in spec.transform(evaluation_x)]
        )
        evaluation_strata = cast(list[str] | None, case.get("evaluation_strata"))
        evaluation_offset = cast(list[float] | None, case.get("evaluation_offset"))
        evaluation_linear = result.predict_linear(
            evaluation_basis, offsets=evaluation_offset
        )
        survival = result.predict_survival(
            evaluation_basis,
            cast(list[float], case["evaluation_times"]),
            strata=evaluation_strata,
            offsets=evaluation_offset,
        )
        output = {
            "ok": True,
            "protocol_version": "1",
            "operation": "psm",
            "basis": case["basis"],
            "knots": cast(JsonValue, list(knots)),
            "distribution": result.distribution,
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
            "log_likelihood": cast(JsonValue, list(result.log_likelihood)),
            "scale": result.scale,
            "evaluation_x": cast(JsonValue, evaluation_x),
            "evaluation_linear_predictors": cast(JsonValue, list(evaluation_linear)),
            "evaluation_times": case["evaluation_times"],
            "predicted_survival": cast(JsonValue, [list(row) for row in survival]),
        }
        if response is not None:
            output["censoring_types"] = cast(JsonValue, list(response.censoring_types))
        if "evaluation_probabilities" in case:
            probabilities = cast(list[float], case["evaluation_probabilities"])
            output.update(
                evaluation_probabilities=cast(JsonValue, probabilities),
                predicted_quantiles=cast(
                    JsonValue,
                    [
                        list(row)
                        for row in result.predict_quantile(
                            evaluation_basis,
                            probabilities,
                            strata=evaluation_strata,
                            offsets=evaluation_offset,
                        )
                    ],
                ),
                predicted_mean=cast(
                    JsonValue,
                    list(
                        result.predict_mean(
                            evaluation_basis,
                            strata=evaluation_strata,
                            offsets=evaluation_offset,
                        )
                    ),
                ),
            )
        if any(
            name in case
            for name in (
                "strata",
                "weights",
                "offset",
                "evaluation_strata",
                "evaluation_offset",
            )
        ):
            output.update(
                strata=case.get("strata"),
                weights=case.get("weights"),
                offset=case.get("offset"),
                evaluation_strata=case.get("evaluation_strata"),
                evaluation_offset=case.get("evaluation_offset"),
                scales=cast(JsonValue, list(result.scales)),
                predicted_hazard=cast(
                    JsonValue,
                    [
                        list(row)
                        for row in result.predict_hazard(
                            evaluation_basis,
                            cast(list[float], case["evaluation_times"]),
                            strata=evaluation_strata,
                            offsets=evaluation_offset,
                        )
                    ],
                ),
                normalized_residuals=cast(
                    JsonValue,
                    list(
                        survival_residuals(
                            result,
                            cast(list[float], case["time"]),
                            cast(list[int], case["event"]),
                            kind="normalized",
                            strata=strata,
                        ).values
                    ),
                ),
                response_residuals=cast(
                    JsonValue,
                    list(
                        survival_residuals(
                            result,
                            cast(list[float], case["time"]),
                            cast(list[int], case["event"]),
                            kind="response",
                            strata=strata,
                        ).values
                    ),
                ),
                martingale_residuals=cast(
                    JsonValue,
                    list(
                        survival_residuals(
                            result,
                            cast(list[float], case["time"]),
                            cast(list[int], case["event"]),
                            strata=strata,
                        ).values
                    ),
                ),
                deviance_residuals=cast(
                    JsonValue,
                    list(
                        survival_residuals(
                            result,
                            cast(list[float], case["time"]),
                            cast(list[int], case["event"]),
                            kind="deviance",
                            strata=strata,
                        ).values
                    ),
                ),
            )
        return output

    if operation == "orm":
        y = cast(list[float], case["y"])
        result = fit_orm(
            y,
            basis,
            family=cast(
                Literal["logistic", "probit", "loglog", "cloglog", "cauchit"],
                case["family"],
            ),
            feature_names=design_names,
        )
        threshold_count = len(result.thresholds)
        covariance_indices = (0, *range(threshold_count, len(result.parameter_values)))
        reduced_covariance = [
            [result.covariance[row][column] for column in covariance_indices]
            for row in covariance_indices
        ]
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "orm",
            "basis": case["basis"],
            "knots": cast(JsonValue, list(knots)),
            "coefficient_names": cast(JsonValue, list(result.coefficient_names)),
            "coefficients": {
                name: value
                for name, value in zip(
                    result.coefficient_names, result.parameter_values, strict=True
                )
            },
            "covariance_names": cast(
                JsonValue, [result.threshold_names[0], *result.feature_names]
            ),
            "covariance": cast(JsonValue, reduced_covariance),
            "design_names": cast(JsonValue, design_names),
            "design": cast(JsonValue, basis),
            "linear_predictors": cast(JsonValue, list(result.linear_predictors)),
            "deviance": cast(JsonValue, list(result.deviance)),
            "family": result.family,
            "response": cast(JsonValue, y),
            "response_levels": cast(JsonValue, list(result.response_levels)),
            "probability_names": cast(
                JsonValue, [f"y={level:g}" for level in result.response_levels]
            ),
            "fitted_probabilities": cast(
                JsonValue, [list(row) for row in result.fitted_probabilities]
            ),
        }

    if operation == "orm_censored":

        def endpoint(value: JsonValue) -> float:
            if value == "neg_inf":
                return float("-inf")
            if value == "pos_inf":
                return float("inf")
            return float(cast(int | float, value))

        lower = tuple(endpoint(value) for value in cast(list[JsonValue], case["lower"]))
        upper = tuple(endpoint(value) for value in cast(list[JsonValue], case["upper"]))
        response = CensoredResponse.from_intervals(lower, upper)
        turnbull = response.turnbull()
        result = fit_orm(
            response,
            tuple((float(value),) for value in cast(list[float], case["x"])),
            family=cast(
                Literal["logistic", "probit", "loglog", "cloglog", "cauchit"],
                case["family"],
            ),
            feature_names=("x",),
        )
        threshold_count = len(result.thresholds)
        covariance_indices = (0, *range(threshold_count, len(result.parameter_values)))
        reduced_covariance = [
            [result.covariance[row][column] for column in covariance_indices]
            for row in covariance_indices
        ]
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "orm_censored",
            "basis": "linear",
            "knots": [],
            "coefficient_names": cast(JsonValue, list(result.coefficient_names)),
            "coefficients": {
                name: value
                for name, value in zip(
                    result.coefficient_names, result.parameter_values, strict=True
                )
            },
            "covariance_names": cast(
                JsonValue, [result.threshold_names[0], *result.feature_names]
            ),
            "covariance": cast(JsonValue, reduced_covariance),
            "design_names": ["x"],
            "design": cast(
                JsonValue, [[value] for value in cast(list[float], case["x"])]
            ),
            "linear_predictors": cast(JsonValue, list(result.linear_predictors)),
            "deviance": cast(JsonValue, list(result.deviance)),
            "family": result.family,
            "censoring_types": cast(JsonValue, list(response.censoring_types)),
            "response_levels": cast(JsonValue, list(result.response_levels)),
            "turnbull_lower": cast(JsonValue, list(turnbull.lower)),
            "turnbull_upper": cast(JsonValue, list(turnbull.upper)),
            "turnbull_probabilities": cast(JsonValue, list(turnbull.probabilities)),
            "turnbull_survival": cast(JsonValue, list(turnbull.survival)),
            "probability_names": cast(
                JsonValue, [f"y={level:g}" for level in result.response_levels]
            ),
            "fitted_probabilities": cast(
                JsonValue, [list(row) for row in result.fitted_probabilities]
            ),
        }

    if operation == "orm_random":
        mix_value = case["mix_re"]
        result = fit_random_intercept_orm(
            cast(list[float], case["y"]),
            tuple((float(value),) for value in cast(list[float], case["x"])),
            cast(list[int], case["clusters"]),
            family=cast(
                Literal["logistic", "probit", "loglog", "cloglog", "cauchit"],
                case["family"],
            ),
            feature_names=("x",),
            mix_re=None if mix_value is None else cast(list[float], mix_value),
            quadrature_grid=cast(list[int], case["quadrature_grid"]),
            quadrature_tolerance=float(cast(int | float, case["quadrature_tolerance"])),
            tolerance=2e-5,
        )
        parameter_names = result.fixed.coefficient_names
        parameter_values = result.fixed.parameter_values
        fixed_count = len(parameter_names)
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "orm_random",
            "basis": "linear",
            "family": result.fixed.family,
            "parameter_names": cast(JsonValue, list(parameter_names)),
            "parameters": {
                name: value
                for name, value in zip(parameter_names, parameter_values, strict=True)
            },
            "covariance_names": cast(JsonValue, list(parameter_names)),
            "covariance": cast(
                JsonValue,
                [list(row[:fixed_count]) for row in result.covariance[:fixed_count]],
            ),
            "response_levels": cast(JsonValue, list(result.fixed.response_levels)),
            "linear_predictors": cast(JsonValue, list(result.fixed.linear_predictors)),
            "deviance": cast(JsonValue, list(result.fixed.deviance)),
            "cluster_count": result.cluster_count,
            "sigma": result.sigma,
            "sigma1": result.sigma1,
            "sigma2": result.sigma2,
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
