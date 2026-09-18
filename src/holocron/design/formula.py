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

from holocron._serialization import (
    canonical_json,
    parse_json_object,
    validate_sha256,
)
from holocron.design.splines import RestrictedCubicSplineSpec
from holocron.exceptions import InputValidationError
from holocron.formula import (
    CategoricalTerm,
    Formula,
    IdentityTerm,
    LinearSplineTerm,
    OrderedTerm,
    PolynomialTerm,
    RestrictedCubicSplineTerm,
    RestrictedInteractionTerm,
)

FloatMatrix: TypeAlias = npt.NDArray[np.float64]
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

SPEC_SCHEMA_VERSION = "holocron-design-spec/v2"
MATRIX_SCHEMA_VERSION = "holocron-design-matrix/v1"
MAX_DESIGN_ROWS = 1_000_000
MAX_DESIGN_COLUMNS = 256


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


def _is_integer_pair(value: object) -> bool:
    if not isinstance(value, tuple):
        return False
    items = cast(tuple[object, ...], value)
    return len(items) == 2 and all(
        not isinstance(item, bool) and isinstance(item, int) for item in items
    )


def _factor_codes(
    values: Iterable[object],
    *,
    name: str,
    levels: tuple[str | float, ...],
) -> npt.NDArray[np.int64]:
    snapshot = tuple(values)
    if not snapshot:
        raise InputValidationError(f"variable {name!r} must not be empty")
    expected_strings = isinstance(levels[0], str)
    lookup = {level: index for index, level in enumerate(levels)}
    codes: list[int] = []
    for value in snapshot:
        if expected_strings:
            if not isinstance(value, str):
                raise InputValidationError(
                    f"variable {name!r} must contain only declared string levels"
                )
            normalized: str | float = value
        else:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise InputValidationError(
                    f"variable {name!r} must contain only declared numeric levels"
                )
            normalized = float(value)
            if not math.isfinite(normalized):
                raise InputValidationError(
                    f"variable {name!r} must contain only finite levels"
                )
        if normalized not in lookup:
            raise InputValidationError(
                f"variable {name!r} contains unknown level {normalized!r}"
            )
        codes.append(lookup[normalized])
    return np.asarray(codes, dtype=np.int64)


@dataclass(frozen=True, slots=True)
class GeneratedColumn:
    """Stable identity and ownership metadata for one generated column."""

    name: str
    variables: tuple[str, ...]
    transformation: str
    term_index: int
    within_term_index: int
    nonlinear: bool
    component_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name or not self.variables or not self.transformation:
            raise InputValidationError("generated-column names must not be empty")
        if any(not variable for variable in self.variables):
            raise InputValidationError("generated-column variables must not be empty")
        if len(set(self.variables)) != len(self.variables):
            raise InputValidationError("generated-column variables must be unique")
        if self.transformation == "restricted_interaction":
            if len(self.variables) != 2 or len(self.component_columns) != 2:
                raise InputValidationError(
                    "interaction columns require two variables and two components"
                )
        elif len(self.variables) != 1 or self.component_columns:
            raise InputValidationError(
                "main-effect columns require one variable and no components"
            )
        if self.term_index < 0 or self.within_term_index < 0:
            raise InputValidationError("generated-column indices must be non-negative")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical metadata document for this column."""
        return {
            "name": self.name,
            "variables": list(self.variables),
            "transformation": self.transformation,
            "term_index": self.term_index,
            "within_term_index": self.within_term_index,
            "nonlinear": self.nonlinear,
            "component_columns": list(self.component_columns),
        }


def _level_name(value: str | float) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        if isinstance(value, str)
        else _number_name(value)
    )


def _main_column_specs(term: object) -> tuple[tuple[str, bool], ...]:
    if not isinstance(
        term,
        (
            IdentityTerm,
            PolynomialTerm,
            LinearSplineTerm,
            RestrictedCubicSplineTerm,
            CategoricalTerm,
            OrderedTerm,
        ),
    ):
        raise InputValidationError("interaction components must be main-effect terms")
    variable = term.variable.expression
    if isinstance(term, IdentityTerm):
        return ((f"asis({variable})", False),)
    if isinstance(term, PolynomialTerm):
        return tuple(
            (f"pol({variable},{power})", power > 1)
            for power in range(1, term.degree + 1)
        )
    if isinstance(term, LinearSplineTerm):
        return (
            (f"lsp({variable},linear)", False),
            *(
                (f"lsp({variable},knot={_number_name(knot)})", True)
                for knot in term.knots
            ),
        )
    if isinstance(term, RestrictedCubicSplineTerm):
        return (
            (f"rcs({variable},linear)", False),
            *(
                (f"rcs({variable},nonlinear={index})", True)
                for index in range(1, term.n_columns)
            ),
        )
    if isinstance(term, CategoricalTerm):
        return tuple(
            (f"catg({variable},level={_level_name(level)})", False)
            for level in term.levels[1:]
        )
    return (
        (f"scored({variable},linear)", False),
        *(
            (f"scored({variable},level={_number_name(level)})", True)
            for level in term.levels[2:]
        ),
    )


def _main_block(term: object, values: Iterable[object]) -> FloatMatrix:
    if not isinstance(
        term,
        (
            IdentityTerm,
            PolynomialTerm,
            LinearSplineTerm,
            RestrictedCubicSplineTerm,
            CategoricalTerm,
            OrderedTerm,
        ),
    ):
        raise InputValidationError("interaction components must be main-effect terms")
    if isinstance(term, CategoricalTerm):
        codes = _factor_codes(values, name=term.variable.name, levels=term.levels)
        return np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            tuple(
                (codes == index).astype(np.float64)
                for index in range(1, len(term.levels))
            )
        )
    if isinstance(term, OrderedTerm):
        codes = _factor_codes(values, name=term.variable.name, levels=term.levels)
        numeric = np.asarray(tuple(values), dtype=np.float64)
        return np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            (
                numeric,
                *(
                    (codes == index).astype(np.float64)
                    for index in range(2, len(term.levels))
                ),
            )
        )
    numeric = _numeric_vector(values, name=term.variable.name)
    if isinstance(term, IdentityTerm):
        return numeric[:, None]
    if isinstance(term, PolynomialTerm):
        with np.errstate(over="ignore", invalid="ignore"):
            return np.column_stack(  # pyright: ignore[reportUnknownMemberType]
                tuple(numeric**power for power in range(1, term.degree + 1))
            )
    if isinstance(term, LinearSplineTerm):
        return np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            (
                numeric,
                *(np.maximum(numeric - knot, 0.0) for knot in term.knots),
            )
        )
    return RestrictedCubicSplineSpec(term.knots).transform(numeric)


def _columns_for_formula(formula: Formula) -> tuple[GeneratedColumn, ...]:
    columns: list[GeneratedColumn] = []
    for term_index, term in enumerate(formula.terms):
        if isinstance(term, RestrictedInteractionTerm):
            specifications = tuple(
                (
                    f"ia({left_name},{right_name})",
                    left_nonlinear or right_nonlinear,
                    (left_name, right_name),
                )
                for left_name, left_nonlinear in _main_column_specs(term.left)
                for right_name, right_nonlinear in _main_column_specs(term.right)
                if not (left_nonlinear and right_nonlinear)
            )
            variables = (term.left.variable.name, term.right.variable.name)
        else:
            specifications = tuple(
                (name, nonlinear, ()) for name, nonlinear in _main_column_specs(term)
            )
            variables = (term.variable.name,)
        for within_term_index, (name, nonlinear, components) in enumerate(
            specifications
        ):
            columns.append(
                GeneratedColumn(
                    name=name,
                    variables=variables,
                    transformation=term.kind,
                    term_index=term_index,
                    within_term_index=within_term_index,
                    nonlinear=nonlinear,
                    component_columns=components,
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
    include_intercept: bool

    def __post_init__(self) -> None:
        raw_names = cast(object, self.column_names)
        if not isinstance(raw_names, tuple):
            raise InputValidationError("design column names must be non-empty strings")
        names = cast(tuple[object, ...], raw_names)
        if any(not isinstance(name, str) or not name for name in names):
            raise InputValidationError("design column names must be non-empty strings")
        width = len(self.column_names)
        if width == 0 or len(set(self.column_names)) != width:
            raise InputValidationError(
                "design column names must be non-empty and unique"
            )
        if width > MAX_DESIGN_COLUMNS:
            raise InputValidationError(
                f"design matrix exceeds the {MAX_DESIGN_COLUMNS}-column limit"
            )
        raw_nonlinear = cast(object, self.nonlinear_mask)
        if not isinstance(raw_nonlinear, tuple):
            raise InputValidationError("nonlinear mask must contain booleans")
        nonlinear = cast(tuple[object, ...], raw_nonlinear)
        if any(not isinstance(value, bool) for value in nonlinear):
            raise InputValidationError("nonlinear mask must contain booleans")
        if len(self.nonlinear_mask) != width:
            raise InputValidationError("nonlinear mask must match design columns")
        if not isinstance(cast(object, self.rows), tuple) or not self.rows:
            raise InputValidationError("design matrix must contain at least one row")
        if len(self.rows) > MAX_DESIGN_ROWS:
            raise InputValidationError(
                f"design matrix exceeds the {MAX_DESIGN_ROWS}-row limit"
            )
        if any(not isinstance(cast(object, row), tuple) for row in self.rows):
            raise InputValidationError("design rows must be tuples")
        if any(len(row) != width for row in self.rows):
            raise InputValidationError("design rows must match design columns")
        if any(
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            for row in self.rows
            for value in row
        ):
            raise InputValidationError("design matrix must contain finite values")
        raw_slices = cast(object, self.term_slices)
        if not isinstance(raw_slices, tuple):
            raise InputValidationError("term slices must contain integer pairs")
        slices = cast(tuple[object, ...], raw_slices)
        if any(not _is_integer_pair(item) for item in slices):
            raise InputValidationError("term slices must contain integer pairs")
        expected_start = 0
        for start, stop in self.term_slices:
            if start != expected_start or stop <= start or stop > width:
                raise InputValidationError("term slices must partition design columns")
            expected_start = stop
        if expected_start != width:
            raise InputValidationError("term slices must partition design columns")
        validate_sha256(
            self.specification_fingerprint, role="specification_fingerprint"
        )
        if not isinstance(cast(object, self.include_intercept), bool):
            raise InputValidationError("include_intercept must be boolean")

    @property
    def shape(self) -> tuple[int, int]:
        """Return ``(rows, columns)``."""
        return len(self.rows), len(self.column_names)

    def to_numpy(self) -> FloatMatrix:
        """Return an independent float64 NumPy array."""
        return np.asarray(self.rows, dtype=np.float64)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the versioned design-matrix document."""
        return {
            "schema_version": MATRIX_SCHEMA_VERSION,
            "column_names": list(self.column_names),
            "nonlinear_mask": list(self.nonlinear_mask),
            "term_slices": [list(value) for value in self.term_slices],
            "rows": [list(row) for row in self.rows],
            "specification_fingerprint": self.specification_fingerprint,
            "include_intercept": self.include_intercept,
        }

    def to_json(self) -> str:
        """Serialize the design matrix as canonical JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the serialized design matrix."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> DesignMatrix:
        """Reconstruct a design matrix from a strictly versioned document."""
        if not isinstance(document, dict):
            raise InputValidationError("design matrix document must be an object")
        raw = cast(dict[str, object], document)
        required = {
            "schema_version",
            "column_names",
            "nonlinear_mask",
            "term_slices",
            "rows",
            "specification_fingerprint",
            "include_intercept",
        }
        if set(raw) != required:
            raise InputValidationError("design matrix document fields differ")
        if raw["schema_version"] != MATRIX_SCHEMA_VERSION:
            raise InputValidationError("unsupported design matrix schema version")
        names = raw["column_names"]
        nonlinear = raw["nonlinear_mask"]
        slices = raw["term_slices"]
        rows = raw["rows"]
        if not all(
            isinstance(value, list) for value in (names, nonlinear, slices, rows)
        ):
            raise InputValidationError("design matrix arrays are malformed")
        raw_names = cast(list[object], names)
        raw_nonlinear = cast(list[object], nonlinear)
        raw_slices = cast(list[object], slices)
        raw_rows = cast(list[object], rows)
        if any(not isinstance(value, str) for value in raw_names):
            raise InputValidationError("design column names must be strings")
        if any(not isinstance(value, bool) for value in raw_nonlinear):
            raise InputValidationError("nonlinear mask must contain booleans")
        if any(not isinstance(value, list) for value in (*raw_slices, *raw_rows)):
            raise InputValidationError("design matrix rows and slices must be arrays")
        if any(len(cast(list[object], value)) != 2 for value in raw_slices):
            raise InputValidationError("term slices must contain pairs")
        return cls(
            column_names=tuple(cast(str, value) for value in raw_names),
            nonlinear_mask=tuple(cast(bool, value) for value in raw_nonlinear),
            term_slices=tuple(
                (
                    cast(int, cast(list[object], item)[0]),
                    cast(int, cast(list[object], item)[1]),
                )
                for item in raw_slices
            ),
            rows=tuple(
                tuple(cast(float, value) for value in cast(list[object], item))
                for item in raw_rows
            ),
            specification_fingerprint=cast(str, raw["specification_fingerprint"]),
            include_intercept=cast(bool, raw["include_intercept"]),
        )

    @classmethod
    def from_json(cls, value: str) -> DesignMatrix:
        """Reconstruct a design matrix from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="design matrix"))


@dataclass(frozen=True, slots=True)
class DesignSpec:
    """A reconstructible design specification derived from a formula."""

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
        """Snapshot and transform predictors under the compiled design."""
        missing = [name for name in self.formula.predictor_names if name not in data]
        if missing:
            raise InputValidationError(
                f"design data is missing variables: {', '.join(missing)}"
            )
        vectors = {name: tuple(data[name]) for name in self.formula.predictor_names}
        if any(not values for values in vectors.values()):
            raise InputValidationError("design variables must not be empty")
        lengths = {len(vector) for vector in vectors.values()}
        if len(lengths) != 1:
            raise InputValidationError("design variables must have equal row counts")

        blocks: list[FloatMatrix] = []
        for term in self.formula.terms:
            if isinstance(term, RestrictedInteractionTerm):
                left = _main_block(term.left, vectors[term.left.variable.name])
                right = _main_block(term.right, vectors[term.right.variable.name])
                left_flags = tuple(flag for _, flag in _main_column_specs(term.left))
                right_flags = tuple(flag for _, flag in _main_column_specs(term.right))
                block = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
                    tuple(
                        left[:, left_index] * right[:, right_index]
                        for left_index, left_nonlinear in enumerate(left_flags)
                        for right_index, right_nonlinear in enumerate(right_flags)
                        if not (left_nonlinear and right_nonlinear)
                    )
                )
                variable_name = f"{term.left.variable.name}:{term.right.variable.name}"
            else:
                block = _main_block(term, vectors[term.variable.name])
                variable_name = term.variable.name
            if not bool(
                np.all(  # pyright: ignore[reportUnknownMemberType]
                    np.isfinite(block)
                )
            ):
                raise InputValidationError(
                    f"transformation for {variable_name!r} produced non-finite values"
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
            include_intercept=self.formula.include_intercept,
        )

    def interactions_containing(self, variable: str) -> tuple[int, ...]:
        """Return zero-based restricted-interaction term indices using ``variable``."""
        if not variable:
            raise InputValidationError("interaction lookup variable must be non-empty")
        return tuple(
            index
            for index, term in enumerate(self.formula.terms)
            if isinstance(term, RestrictedInteractionTerm)
            and variable in {term.left.variable.name, term.right.variable.name}
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
            "schema_version": SPEC_SCHEMA_VERSION,
            "formula": self.formula.to_dict(),
            "columns": [column.to_dict() for column in self.columns],
        }

    def to_json(self) -> str:
        """Serialize reconstruction metadata as canonical JSON."""
        return canonical_json(self.to_dict())

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
        if raw["schema_version"] != SPEC_SCHEMA_VERSION:
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
        return cls.from_dict(parse_json_object(value, role="design specification"))


__all__ = ["DesignMatrix", "DesignSpec", "GeneratedColumn"]
