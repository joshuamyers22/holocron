"""Independent Python outputs for implemented oracle-parity operations."""

from __future__ import annotations

from typing import cast

from holocron.design import RestrictedCubicSplineSpec
from holocron.models import fit_ols
from reference.contracts import JsonValue


def spline_column_names(column_count: int) -> list[str]:
    """Return the normalized rms-style names for a univariate spline basis."""
    return ["x" + "'" * index for index in range(column_count)]


def build_python_output(case: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Compute an implemented case without invoking or importing the R oracle."""
    operation = case["operation"]
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
