"""Bounded generalized-linear and binary lrm entry points."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, overload

from holocron.design import DesignMatrix
from holocron.exceptions import InputValidationError, UnsupportedFeatureError
from holocron.models.linear import OlsResult, fit_ols
from holocron.models.logistic import BinaryLogisticResult, fit_binary_logistic

Family = Literal["gaussian", "binomial"]
Link = Literal["identity", "logit"]


@overload
def fit_glm(
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    family: Literal["gaussian"] = "gaussian",
    link: Literal["identity"] | None = None,
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-8,
) -> OlsResult: ...


@overload
def fit_glm(
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    family: Literal["binomial"],
    link: Literal["logit"] | None = None,
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-8,
) -> BinaryLogisticResult: ...


def fit_glm(
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    family: Family = "gaussian",
    link: Link | None = None,
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-8,
) -> OlsResult | BinaryLogisticResult:
    """Fit the supported Gaussian/identity or binomial/logit GLM envelope."""
    if family == "gaussian":
        if link not in {None, "identity"}:
            raise UnsupportedFeatureError(
                "gaussian Glm currently supports only the identity link"
            )
        if max_iterations != 100 or tolerance != 1e-8:
            raise InputValidationError(
                "iterative controls do not apply to gaussian identity Glm"
            )
        return fit_ols(
            response,
            features,
            feature_names=feature_names,
            include_intercept=include_intercept,
            design_fingerprint=design_fingerprint,
        )
    if family == "binomial":
        if link not in {None, "logit"}:
            raise UnsupportedFeatureError(
                "binomial Glm currently supports only the logit link"
            )
        return fit_binary_logistic(
            response,
            features,
            estimator="glm",
            feature_names=feature_names,
            include_intercept=include_intercept,
            design_fingerprint=design_fingerprint,
            max_iterations=max_iterations,
            tolerance=tolerance,
        )
    raise UnsupportedFeatureError(f"unsupported Glm family: {family!r}")


def fit_lrm(
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-10,
) -> BinaryLogisticResult:
    """Fit the supported unpenalized binary subset of ``rms::lrm``."""
    result = fit_binary_logistic(
        response,
        features,
        estimator="lrm",
        feature_names=feature_names,
        include_intercept=include_intercept,
        design_fingerprint=design_fingerprint,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )
    if not result.includes_intercept:
        raise InputValidationError("binary lrm requires an intercept")
    return result


__all__ = ["fit_glm", "fit_lrm"]
