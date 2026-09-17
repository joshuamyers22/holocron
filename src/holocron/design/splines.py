"""Restricted cubic spline design matrices."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from holocron.exceptions import InputValidationError


def _validated_vector(values: Iterable[float]) -> npt.NDArray[np.float64]:
    items = tuple(float(value) for value in values)
    array = np.asarray(items, dtype=np.float64)
    if array.ndim != 1:
        raise InputValidationError("values must be one-dimensional")
    if not all(math.isfinite(value) for value in items):
        raise InputValidationError("values must contain only finite numbers")
    return array


@dataclass(frozen=True)
class RestrictedCubicSplineSpec:
    """An immutable restricted cubic spline basis specification.

    Parameters
    ----------
    knots
        At least three finite, strictly increasing knot locations. The first and
        last knots define the linear tails. Knots are explicit in this initial
        API; automatic knot placement will be added only after separate parity
        qualification.
    """

    knots: tuple[float, ...]

    def __post_init__(self) -> None:
        knots = _validated_vector(self.knots)
        if knots.size < 3:
            raise InputValidationError(
                "restricted cubic splines require at least three knots"
            )
        knot_values = tuple(float(value) for value in knots)
        if any(
            right <= left
            for left, right in zip(knot_values[:-1], knot_values[1:], strict=True)
        ):
            raise InputValidationError("knots must be strictly increasing")
        object.__setattr__(self, "knots", knot_values)

    @property
    def n_columns(self) -> int:
        """Return the number of columns, including the linear term."""
        return len(self.knots) - 1

    @property
    def nonlinear_columns(self) -> tuple[int, ...]:
        """Return zero-based indices of nonlinear basis columns."""
        return tuple(range(1, self.n_columns))

    @property
    def nonlinear_mask(self) -> tuple[bool, ...]:
        """Identify nonlinear columns in the same shape as the basis."""
        return (False, *(True for _ in self.nonlinear_columns))

    def transform(self, values: Iterable[float]) -> npt.NDArray[np.float64]:
        """Construct the linear-tail-restricted cubic basis.

        The normalization divides nonlinear terms by the squared distance
        between the boundary knots. This matches the scale used by the `rms`
        restricted-cubic-spline design for explicit knots while retaining the
        original predictor as the first column.
        """
        x = _validated_vector(values)
        knots = np.asarray(self.knots, dtype=np.float64)
        lower = knots[0]
        penultimate = knots[-2]
        upper = knots[-1]
        boundary_span = upper - lower
        final_span = upper - penultimate

        truncated = np.maximum(x[:, None] - knots[None, :], 0.0) ** 3
        nonlinear: list[npt.NDArray[np.float64]] = []
        for index in range(knots.size - 2):
            knot = knots[index]
            upper_weight = (penultimate - knot) / final_span
            penultimate_weight = (upper - knot) / final_span
            column = (
                truncated[:, index]
                - penultimate_weight * truncated[:, -2]
                + upper_weight * truncated[:, -1]
            ) / (boundary_span**2)
            nonlinear.append(column)

        result: npt.NDArray[np.float64] = np.empty(
            (x.size, self.n_columns), dtype=np.float64
        )
        result[:, 0] = x
        for column_index, column in enumerate(nonlinear, start=1):
            result[:, column_index] = column
        return result
