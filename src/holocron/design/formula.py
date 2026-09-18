"""Deterministic numeric design construction from the owned formula AST."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from numbers import Real
from typing import TypeAlias, cast

import numpy as np
import numpy.typing as npt

from holocron.design.splines import RestrictedCubicSplineSpec
from holocron.exceptions import InputValidationError
from holocron.formula import (
    Formula,
    IdentityTerm,
    LinearSplineTerm,
    PolynomialTerm,
)

FloatMatrix: TypeAlias = npt.NDArray[np.float64]
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

SCHEMA_VERSION = "holocron-design-spec/v1"


def _numeric_vector(values: Iterable[object], *, name: str) -> npt.NDArray[np.float64]:
    snapshot = tuple(values)
    if not snapshot:
        raise InputValidationError(f"variable {name!r} must not be empty")
    normalized: list[float] = []
    for value in snapshot:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise InputValidationError(
                f"variable {name!r} must contain only numeric values"
            )
        number = float(value)
        if not math.isfinite(number):
            raise InputValidationError(
                f"variable {name!r} must contain only finite values"
            )
        normalized.append(number)
    return np.asarray(normalized, dtype=np.float64)


def _number_name(value: float) -> str:
    return repr(float(value))


@dataclass(frozen=True, slots=True)
class GeneratedColumn:
    """Stable identity and ownership metadata for one generated column."""

    name: str
    variable: str
    transformation: str
    term_index: int
    within_term_index: int
    nonlinear: bool

    def __post_init__(self) -> None:
        if not self.name or not self.variable or not self.transformation:
            raise InputValidationError("generated-column names must not be empty")
        if self.term_index < 0 or self.within_term_index < 0:
            raise InputValidationError("generated-column indices must be non-negative")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical metadata document for this column."""
        return {
            "name": self.name,
            "variable": self.variable,
            "transformation": self.transformation,
            "term_index": self.term_index,
            "within_term_index": self.within_term_index,
            "nonlinear": self.nonlinear,
        }


def _columns_for_formula(formula: Formula) -> tuple[GeneratedColumn, ...]:
    columns: list[GeneratedColumn] = []
    for term_index, term in enumerate(formula.terms):
        variable = term.variable.expression
        if isinstance(term, IdentityTerm):
            specifications = ((f"asis({variable})", False),)
        elif isinstance(term, PolynomialTerm):
            specifications = tuple(
                (f"pol({variable},{power})", power > 1)
                for power in range(1, term.degree + 1)
            )
        elif isinstance(term, LinearSplineTerm):
            specifications = (
                (f"lsp({variable},linear)", False),
                *(
                    (f"lsp({variable},knot={_number_name(knot)})", True)
                    for knot in term.knots
                ),
            )
        else:
            specifications = (
                (f"rcs({variable},linear)", False),
                *(
                    (f"rcs({variable},nonlinear={index})", True)
                    for index in range(1, term.n_columns)
                ),
            )
        for within_term_index, (name, nonlinear) in enumerate(specifications):
            columns.append(
                GeneratedColumn(
                    name=name,
                    variable=term.variable.name,
                    transformation=term.kind,
                    term_index=term_index,
                    within_term_index=within_term_index,
                    nonlinear=nonlinear,
                )
            )
    names = [column.name for column in columns]
    if len(names) != len(set(names)):
        raise InputValidationError("formula generates duplicate column names")
    return tuple(columns)


@dataclass(frozen=True, slots=True)
class DesignMatrix:
    """An immutable numeric design matrix plus generated-column identity."""

    column_names: tuple[str, ...]
    nonlinear_mask: tuple[bool, ...]
    term_slices: tuple[tuple[int, int], ...]
    rows: tuple[tuple[float, ...], ...]
    specification_fingerprint: str

    def __post_init__(self) -> None:
        width = len(self.column_names)
        if width == 0 or len(set(self.column_names)) != width:
            raise InputValidationError(
                "design column names must be non-empty and unique"
            )
        if len(self.nonlinear_mask) != width:
            raise InputValidationError("nonlinear mask must match design columns")
        if not self.rows:
            raise InputValidationError("design matrix must contain at least one row")
        if any(len(row) != width for row in self.rows):
            raise InputValidationError("design rows must match design columns")
        if any(not math.isfinite(value) for row in self.rows for value in row):
            raise InputValidationError("design matrix must contain finite values")
        expected_start = 0
        for start, stop in self.term_slices:
            if start != expected_start or stop <= start or stop > width:
                raise InputValidationError("term slices must partition design columns")
            expected_start = stop
        if expected_start != width:
            raise InputValidationError("term slices must partition design columns")

    @property
    def shape(self) -> tuple[int, int]:
        """Return ``(rows, columns)``."""
        return len(self.rows), len(self.column_names)

    def to_numpy(self) -> FloatMatrix:
        """Return an independent float64 NumPy array."""
        return np.asarray(self.rows, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class DesignSpec:
    """A reconstructible numeric design specification derived from a formula."""

    formula: Formula
    columns: tuple[GeneratedColumn, ...]

    def __post_init__(self) -> None:
        expected = _columns_for_formula(self.formula)
        if self.columns != expected:
            raise InputValidationError("design columns do not match the formula AST")

    @classmethod
    def from_formula(cls, formula: Formula | str) -> DesignSpec:
        """Compile a formula object or restricted formula string."""
        parsed = Formula.parse(formula) if isinstance(formula, str) else formula
        if not isinstance(cast(object, parsed), Formula):
            raise InputValidationError("formula must be a Formula or string")
        return cls(formula=parsed, columns=_columns_for_formula(parsed))

    @property
    def column_names(self) -> tuple[str, ...]:
        """Return generated columns in stable design order."""
        return tuple(column.name for column in self.columns)

    @property
    def nonlinear_mask(self) -> tuple[bool, ...]:
        """Identify nonlinear columns in stable design order."""
        return tuple(column.nonlinear for column in self.columns)

    @property
    def term_slices(self) -> tuple[tuple[int, int], ...]:
        """Return half-open column slices owned by each formula term."""
        result: list[tuple[int, int]] = []
        start = 0
        for term in self.formula.terms:
            stop = start + term.n_columns
            result.append((start, stop))
            start = stop
        return tuple(result)

    def transform(self, data: Mapping[str, Iterable[object]]) -> DesignMatrix:
        """Snapshot and transform numeric predictors under the compiled design."""
        missing = [name for name in self.formula.predictor_names if name not in data]
        if missing:
            raise InputValidationError(
                f"design data is missing variables: {', '.join(missing)}"
            )
        vectors = {
            name: _numeric_vector(data[name], name=name)
            for name in self.formula.predictor_names
        }
        lengths = {vector.size for vector in vectors.values()}
        if len(lengths) != 1:
            raise InputValidationError("design variables must have equal row counts")

        blocks: list[FloatMatrix] = []
        for term in self.formula.terms:
            values = vectors[term.variable.name]
            if isinstance(term, IdentityTerm):
                block = values[:, None]
            elif isinstance(term, PolynomialTerm):
                with np.errstate(over="ignore", invalid="ignore"):
                    block = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
                        tuple(values**power for power in range(1, term.degree + 1))
                    )
            elif isinstance(term, LinearSplineTerm):
                block = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
                    (
                        values,
                        *(np.maximum(values - knot, 0.0) for knot in term.knots),
                    )
                )
            else:
                block = RestrictedCubicSplineSpec(term.knots).transform(values)
            if not bool(
                np.all(  # pyright: ignore[reportUnknownMemberType]
                    np.isfinite(block)
                )
            ):
                raise InputValidationError(
                    f"transformation for {term.variable.name!r} produced "
                    "non-finite values"
                )
            blocks.append(block)
        matrix = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            tuple(blocks)
        )
        rows = tuple(tuple(float(value) for value in row) for row in matrix)
        return DesignMatrix(
            column_names=self.column_names,
            nonlinear_mask=self.nonlinear_mask,
            term_slices=self.term_slices,
            rows=rows,
            specification_fingerprint=self.fingerprint,
        )

    def response_values(
        self, data: Mapping[str, Iterable[object]]
    ) -> tuple[float, ...]:
        """Snapshot the declared numeric response for estimator input."""
        if self.formula.response is None:
            raise InputValidationError("formula does not declare a response")
        name = self.formula.response.name
        if name not in data:
            raise InputValidationError(f"design data is missing response {name!r}")
        return tuple(float(value) for value in _numeric_vector(data[name], name=name))

    def to_dict(self) -> dict[str, JsonValue]:
        """Return versioned reconstruction metadata."""
        return {
            "schema_version": SCHEMA_VERSION,
            "formula": self.formula.to_dict(),
            "columns": [column.to_dict() for column in self.columns],
        }

    def to_json(self) -> str:
        """Serialize reconstruction metadata as canonical JSON."""
        return json.dumps(
            self.to_dict(), allow_nan=False, separators=(",", ":"), sort_keys=True
        )

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the design specification."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> DesignSpec:
        """Reconstruct and verify a design specification document."""
        if not isinstance(document, dict):
            raise InputValidationError("design specification must be an object")
        raw = cast(dict[str, object], document)
        if set(raw) != {"schema_version", "formula", "columns"}:
            raise InputValidationError("design specification fields differ")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise InputValidationError("unsupported design specification version")
        formula = Formula.from_dict(raw["formula"])
        expected = cls.from_formula(formula)
        raw_columns = raw["columns"]
        if not isinstance(raw_columns, list):
            raise InputValidationError("design columns must be an array")
        if raw_columns != [column.to_dict() for column in expected.columns]:
            raise InputValidationError("serialized design columns do not match formula")
        return expected

    @classmethod
    def from_json(cls, value: str) -> DesignSpec:
        """Reconstruct a design specification from JSON."""
        try:
            document: object = json.loads(value)
        except (json.JSONDecodeError, TypeError) as error:
            raise InputValidationError("invalid design specification JSON") from error
        return cls.from_dict(document)


__all__ = ["DesignMatrix", "DesignSpec", "GeneratedColumn"]
