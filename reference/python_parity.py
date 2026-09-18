"""Independent Python outputs for implemented oracle-parity operations."""

from __future__ import annotations

from typing import Literal, cast

from holocron.design import DataDistribution, DesignSpec, RestrictedCubicSplineSpec
from holocron.models import fit_ols
from reference.contracts import JsonValue


def spline_column_names(column_count: int) -> list[str]:
    """Return the normalized rms-style names for a univariate spline basis."""
    return ["x" + "'" * index for index in range(column_count)]


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

    x = cast(list[float], case["x"])
    knots = tuple(cast(list[float], case["knots"]))
    spec = RestrictedCubicSplineSpec(knots)
    basis = spec.transform(x)
    design_names = spline_column_names(spec.n_columns)

    if operation == "rcs":
        return {
            "ok": True,
            "protocol_version": "1",
            "operation": "rcs",
            "x": cast(JsonValue, x),
            "knots": cast(JsonValue, list(spec.knots)),
            "nonlinear_mask": cast(JsonValue, list(spec.nonlinear_mask)),
            "nonlinear_columns": cast(JsonValue, list(spec.nonlinear_columns)),
            "column_names": cast(JsonValue, design_names),
            "basis": cast(JsonValue, basis.tolist()),
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
            "design": cast(JsonValue, basis.tolist()),
            "fitted": cast(JsonValue, list(predictions)),
            "residuals": cast(JsonValue, list(result.residuals)),
            "degrees_of_freedom": result.residual_degrees_of_freedom,
            "sigma": result.residual_scale,
        }

    raise ValueError(f"no independent Python parity implementation for {operation}")
