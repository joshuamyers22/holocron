"""Immutable predictor-distribution metadata."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from numbers import Real
from typing import Literal, TypeAlias, cast

import numpy as np

from holocron.exceptions import InputValidationError

DistributionValue: TypeAlias = float | str
VariableKind: TypeAlias = Literal["continuous", "discrete", "categorical", "ordered"]
CategoricalAdjustment: TypeAlias = Literal["mode", "first"]
InputValue: TypeAlias = float | str | None
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

SCHEMA_VERSION = "holocron-data-distribution/v1"


def _validate_name(value: object, *, role: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputValidationError(f"{role} must be a non-empty string")
    return value


def _validate_quantiles(value: Iterable[float], *, name: str) -> tuple[float, float]:
    items = tuple(value)
    if any(isinstance(item, bool) for item in items):
        raise InputValidationError(f"{name} must contain numeric probabilities")
    try:
        quantiles = tuple(float(item) for item in items)
    except (TypeError, ValueError) as error:
        raise InputValidationError(
            f"{name} must contain numeric probabilities"
        ) from error
    if len(quantiles) != 2:
        raise InputValidationError(f"{name} must contain exactly two probabilities")
    lower, upper = quantiles
    if not (math.isfinite(lower) and math.isfinite(upper)):
        raise InputValidationError(f"{name} must contain finite probabilities")
    if not 0.0 <= lower < upper <= 1.0:
        raise InputValidationError(f"{name} must satisfy 0 <= lower < upper <= 1")
    return lower, upper


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, Real) and math.isnan(float(value)))


def _normalize_numeric(
    values: tuple[object, ...], *, name: str
) -> tuple[tuple[float, ...], int]:
    normalized: list[float] = []
    missing_count = 0
    for value in values:
        if _is_missing(value):
            missing_count += 1
            continue
        if isinstance(value, bool) or not isinstance(value, Real):
            raise InputValidationError(
                f"numeric variable {name!r} contains a non-numeric value"
            )
        number = float(value)
        if not math.isfinite(number):
            raise InputValidationError(
                f"numeric variable {name!r} contains a non-finite value"
            )
        normalized.append(number)
    if len(normalized) < 2:
        raise InputValidationError(
            f"variable {name!r} requires at least two non-missing observations"
        )
    return tuple(normalized), missing_count


def _normalize_level(value: object, *, name: str) -> DistributionValue:
    if isinstance(value, str):
        if not value:
            raise InputValidationError(f"levels for {name!r} must not be empty")
        return value
    if isinstance(value, bool):
        raise InputValidationError(
            f"levels for {name!r} must be finite numbers or non-empty strings"
        )
    if isinstance(value, Real):
        number = float(value)
        if math.isfinite(number):
            return number
    raise InputValidationError(
        f"levels for {name!r} must be finite numbers or non-empty strings"
    )


@dataclass(frozen=True, slots=True)
class DistributionRange:
    """An inclusive lower and upper metadata range."""

    lower: DistributionValue
    upper: DistributionValue

    def __post_init__(self) -> None:
        lower = _normalize_level(self.lower, name="range")
        upper = _normalize_level(self.upper, name="range")
        if isinstance(lower, str) != isinstance(upper, str):
            raise InputValidationError("range endpoints must use the same value type")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)


@dataclass(frozen=True, slots=True)
class VariableDistribution:
    """Learned distribution metadata for one predictor.

    ``effect_range`` is absent for unordered categorical predictors because an
    unordered pair of levels has no intrinsic low-to-high effect interpretation.
    """

    name: str
    kind: VariableKind
    adjustment: DistributionValue
    effect_range: DistributionRange | None
    display_range: DistributionRange
    overall_range: DistributionRange
    values: tuple[DistributionValue, ...]
    label: str
    unit: str | None
    nonmissing_count: int
    missing_count: int

    def __post_init__(self) -> None:
        _validate_name(self.name, role="variable name")
        _validate_name(self.label, role=f"label for {self.name!r}")
        if self.unit is not None:
            _validate_name(self.unit, role=f"unit for {self.name!r}")
        if self.kind not in {
            "continuous",
            "discrete",
            "categorical",
            "ordered",
        }:
            raise InputValidationError(f"unknown variable kind: {self.kind!r}")
        adjustment = _normalize_level(self.adjustment, name=self.name)
        values = tuple(_normalize_level(item, name=self.name) for item in self.values)
        if len(set(values)) != len(values):
            raise InputValidationError(f"values for {self.name!r} must be unique")
        if self.kind in {"categorical", "ordered"} and adjustment not in values:
            raise InputValidationError(
                f"adjustment for {self.name!r} must be one of its levels"
            )
        if self.kind == "categorical" and self.effect_range is not None:
            raise InputValidationError(
                "unordered categorical variables must not have an effect range"
            )
        if self.kind != "categorical" and self.effect_range is None:
            raise InputValidationError(
                f"{self.kind} variable {self.name!r} requires an effect range"
            )
        if self.kind in {"continuous", "discrete"}:
            if isinstance(adjustment, str):
                raise InputValidationError(
                    f"numeric variable {self.name!r} requires numeric metadata"
                )
            ranges = (self.effect_range, self.display_range, self.overall_range)
            if any(
                value is not None
                and (isinstance(value.lower, str) or isinstance(value.upper, str))
                for value in ranges
            ) or any(isinstance(value, str) for value in values):
                raise InputValidationError(
                    f"numeric variable {self.name!r} requires numeric metadata"
                )
            if self.kind == "continuous" and values:
                raise InputValidationError(
                    f"continuous variable {self.name!r} must not retain values"
                )
            if self.kind == "discrete" and not values:
                raise InputValidationError(
                    f"discrete variable {self.name!r} must retain values"
                )
        if (
            _document_integer(self.nonmissing_count, name="nonmissing_count") < 1
            or _document_integer(self.missing_count, name="missing_count") < 0
        ):
            raise InputValidationError("observation counts must be non-negative")
        object.__setattr__(self, "adjustment", adjustment)
        object.__setattr__(self, "values", values)

    @property
    def observation_count(self) -> int:
        """Return the total number of input rows, including missing values."""
        return self.nonmissing_count + self.missing_count


def _numeric_distribution(
    *,
    name: str,
    raw_values: tuple[object, ...],
    label: str,
    unit: str | None,
    effect_quantiles: tuple[float, float],
    display_quantiles: tuple[float, float] | None,
    discrete_threshold: int,
) -> VariableDistribution:
    values, missing_count = _normalize_numeric(raw_values, name=name)
    unique = tuple(sorted(set(values)))
    overall = DistributionRange(unique[0], unique[-1])
    unique_count = len(unique)
    if unique_count < 4:
        effect = overall
        display = overall
    else:
        array = np.asarray(values, dtype=np.float64)
        effective_display = display_quantiles or (
            10.0 / max(len(values), 200),
            1.0 - 10.0 / max(len(values), 200),
        )
        effect_values = np.quantile(  # pyright: ignore[reportUnknownMemberType]
            array, effect_quantiles, method="linear"
        )
        display_values = np.quantile(  # pyright: ignore[reportUnknownMemberType]
            array, effective_display, method="linear"
        )
        effect = DistributionRange(float(effect_values[0]), float(effect_values[1]))
        display = DistributionRange(float(display_values[0]), float(display_values[1]))
        if effect.lower == effect.upper:
            effect = overall
        if display.lower == display.upper:
            display = overall

    if unique_count < 3:
        adjustment = unique[0]
    elif unique_count == 3:
        adjustment = unique[1]
    else:
        adjustment = float(np.median(np.asarray(values, dtype=np.float64)))

    retained_values: tuple[DistributionValue, ...] = (
        unique if unique_count <= discrete_threshold else ()
    )
    return VariableDistribution(
        name=name,
        kind="discrete" if retained_values else "continuous",
        adjustment=adjustment,
        effect_range=effect,
        display_range=display,
        overall_range=overall,
        values=retained_values,
        label=label,
        unit=unit,
        nonmissing_count=len(values),
        missing_count=missing_count,
    )


def _categorical_distribution(
    *,
    name: str,
    raw_values: tuple[object, ...],
    raw_levels: Iterable[object],
    ordered: bool,
    label: str,
    unit: str | None,
    categorical_adjustment: CategoricalAdjustment,
) -> VariableDistribution:
    levels = tuple(_normalize_level(level, name=name) for level in raw_levels)
    if len(levels) < 2:
        raise InputValidationError(
            f"categorical variable {name!r} requires at least two levels"
        )
    if len(set(levels)) != len(levels):
        raise InputValidationError(f"levels for {name!r} must be unique")
    if any(isinstance(level, str) != isinstance(levels[0], str) for level in levels):
        raise InputValidationError(f"levels for {name!r} must use one value type")
    observed: list[DistributionValue] = []
    missing_count = 0
    for value in raw_values:
        if _is_missing(value):
            missing_count += 1
            continue
        normalized = _normalize_level(value, name=name)
        if normalized not in levels:
            raise InputValidationError(
                f"variable {name!r} contains undeclared level {normalized!r}"
            )
        observed.append(normalized)
    if not observed:
        raise InputValidationError(
            f"categorical variable {name!r} has no non-missing observations"
        )

    if ordered:
        adjustment = levels[(len(levels) - 1) // 2]
        effect_range: DistributionRange | None = DistributionRange(
            levels[0], levels[-1]
        )
    elif categorical_adjustment == "first":
        adjustment = levels[0]
        effect_range = None
    else:
        counts = Counter(observed)
        highest_count = max(counts.values())
        adjustment = next(
            level for level in levels if counts.get(level, 0) == highest_count
        )
        effect_range = None

    full_range = DistributionRange(levels[0], levels[-1])
    return VariableDistribution(
        name=name,
        kind="ordered" if ordered else "categorical",
        adjustment=adjustment,
        effect_range=effect_range,
        display_range=full_range,
        overall_range=full_range,
        values=levels,
        label=label,
        unit=unit,
        nonmissing_count=len(observed),
        missing_count=missing_count,
    )


def _range_document(value: DistributionRange | None) -> JsonValue:
    if value is None:
        return None
    return [value.lower, value.upper]


def _range_from_document(value: object, *, name: str) -> DistributionRange | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise InputValidationError(f"{name} must be null or a two-value array")
    items = cast(list[object], value)
    if len(items) != 2:
        raise InputValidationError(f"{name} must be null or a two-value array")
    return DistributionRange(
        cast(DistributionValue, items[0]), cast(DistributionValue, items[1])
    )


def _required_range_from_document(value: object, *, name: str) -> DistributionRange:
    result = _range_from_document(value, name=name)
    if result is None:
        raise InputValidationError(f"{name} must not be null")
    return result


def _document_integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputValidationError(f"{name} must be an integer")
    return value


@dataclass(frozen=True, slots=True)
class DataDistribution:
    """Immutable metadata learned from a named collection of predictor columns.

    Use :meth:`from_data` to snapshot caller-owned iterables. No process-wide
    option or ambient dataset is consulted. The result contains the adjustment,
    effect, display, and overall ranges needed by later design and prediction
    APIs, plus labels, units, categorical levels, and missingness counts.
    """

    variables: tuple[VariableDistribution, ...]
    observation_count: int
    effect_quantiles: tuple[float, float] = (0.25, 0.75)
    display_quantiles: tuple[float, float] | None = None
    categorical_adjustment: CategoricalAdjustment = "mode"
    discrete_threshold: int = 10

    def __post_init__(self) -> None:
        if not self.variables:
            raise InputValidationError(
                "data distribution requires at least one variable"
            )
        if _document_integer(self.observation_count, name="observation_count") < 1:
            raise InputValidationError("observation_count must be positive")
        names = tuple(variable.name for variable in self.variables)
        if len(set(names)) != len(names):
            raise InputValidationError("variable names must be unique")
        if any(
            variable.observation_count != self.observation_count
            for variable in self.variables
        ):
            raise InputValidationError(
                "all variable observation counts must match observation_count"
            )
        effect_quantiles = _validate_quantiles(
            self.effect_quantiles, name="effect_quantiles"
        )
        display_quantiles = (
            None
            if self.display_quantiles is None
            else _validate_quantiles(self.display_quantiles, name="display_quantiles")
        )
        if self.categorical_adjustment not in {"mode", "first"}:
            raise InputValidationError(
                "categorical_adjustment must be 'mode' or 'first'"
            )
        if _document_integer(self.discrete_threshold, name="discrete_threshold") < 1:
            raise InputValidationError("discrete_threshold must be a positive integer")
        object.__setattr__(self, "effect_quantiles", effect_quantiles)
        object.__setattr__(self, "display_quantiles", display_quantiles)

    @classmethod
    def from_data(
        cls,
        data: Mapping[str, Iterable[InputValue]],
        *,
        levels: Mapping[str, Iterable[DistributionValue]] | None = None,
        ordered: Iterable[str] = (),
        labels: Mapping[str, str] | None = None,
        units: Mapping[str, str | None] | None = None,
        effect_quantiles: tuple[float, float] = (0.25, 0.75),
        display_quantiles: tuple[float, float] | None = None,
        categorical_adjustment: CategoricalAdjustment = "mode",
        discrete_threshold: int = 10,
    ) -> DataDistribution:
        """Summarize named predictor columns without retaining their row values.

        Numeric columns may contain ``None`` or NaN, which are counted and
        excluded from summaries. Non-numeric columns require an explicit
        ``levels`` entry so category order cannot depend on incidental row order.
        Columns listed in ``ordered`` use the lower middle declared level as
        their adjustment value; unordered columns use the mode or first level.
        """
        if not data:
            raise InputValidationError("data must be a non-empty mapping")
        level_map = levels or {}
        label_map = labels or {}
        unit_map = units or {}
        ordered_names = tuple(ordered)
        raw_names = tuple(data.keys())
        names = tuple(_validate_name(name, role="variable name") for name in raw_names)
        if len(set(names)) != len(names):
            raise InputValidationError("variable names must be unique")
        name_set = set(names)
        for role, keys in (
            ("levels", level_map.keys()),
            ("ordered", ordered_names),
            ("labels", label_map.keys()),
            ("units", unit_map.keys()),
        ):
            unknown = sorted(str(key) for key in set(keys) - name_set)
            if unknown:
                raise InputValidationError(
                    f"{role} contains unknown variables: {', '.join(unknown)}"
                )
        if any(name not in level_map for name in ordered_names):
            raise InputValidationError(
                "every ordered variable requires declared levels"
            )
        if categorical_adjustment not in {"mode", "first"}:
            raise InputValidationError(
                "categorical_adjustment must be 'mode' or 'first'"
            )
        if _document_integer(discrete_threshold, name="discrete_threshold") < 1:
            raise InputValidationError("discrete_threshold must be a positive integer")
        validated_effect = _validate_quantiles(
            effect_quantiles, name="effect_quantiles"
        )
        validated_display = (
            None
            if display_quantiles is None
            else _validate_quantiles(display_quantiles, name="display_quantiles")
        )

        columns = {name: tuple(cast(Iterable[object], data[name])) for name in names}
        lengths = {len(values) for values in columns.values()}
        if len(lengths) != 1:
            raise InputValidationError("all variables must have the same row count")
        observation_count = lengths.pop()
        if observation_count < 2:
            raise InputValidationError("data requires at least two rows")

        variables: list[VariableDistribution] = []
        for name in names:
            label = _validate_name(
                label_map.get(name, name), role=f"label for {name!r}"
            )
            unit = unit_map.get(name)
            if unit is not None:
                _validate_name(unit, role=f"unit for {name!r}")
            if name in level_map:
                variable = _categorical_distribution(
                    name=name,
                    raw_values=columns[name],
                    raw_levels=level_map[name],
                    ordered=name in ordered_names,
                    label=label,
                    unit=unit,
                    categorical_adjustment=categorical_adjustment,
                )
            else:
                variable = _numeric_distribution(
                    name=name,
                    raw_values=columns[name],
                    label=label,
                    unit=unit,
                    effect_quantiles=validated_effect,
                    display_quantiles=validated_display,
                    discrete_threshold=discrete_threshold,
                )
            variables.append(variable)
        return cls(
            variables=tuple(variables),
            observation_count=observation_count,
            effect_quantiles=validated_effect,
            display_quantiles=validated_display,
            categorical_adjustment=categorical_adjustment,
            discrete_threshold=discrete_threshold,
        )

    @property
    def names(self) -> tuple[str, ...]:
        """Return variable names in caller-supplied column order."""
        return tuple(variable.name for variable in self.variables)

    @property
    def adjustments(self) -> dict[str, DistributionValue]:
        """Return a new mapping of variable names to adjustment values."""
        return {variable.name: variable.adjustment for variable in self.variables}

    def __getitem__(self, name: str) -> VariableDistribution:
        for variable in self.variables:
            if variable.name == name:
                return variable
        raise KeyError(name)

    def with_adjustment(self, name: str, value: DistributionValue) -> DataDistribution:
        """Return a copy with one validated adjustment value replaced."""
        variable = self[name]
        adjustment = _normalize_level(value, name=name)
        if variable.kind in {"categorical", "ordered"}:
            if adjustment not in variable.values:
                raise InputValidationError(
                    f"adjustment for {name!r} must be one of its levels"
                )
        elif isinstance(adjustment, str):
            raise InputValidationError(
                f"adjustment for numeric variable {name!r} must be numeric"
            )
        updated = replace(variable, adjustment=adjustment)
        return replace(
            self,
            variables=tuple(
                updated if current.name == name else current
                for current in self.variables
            ),
        )

    def with_data(
        self,
        data: Mapping[str, Iterable[InputValue]],
        *,
        levels: Mapping[str, Iterable[DistributionValue]] | None = None,
        ordered: Iterable[str] = (),
        labels: Mapping[str, str] | None = None,
        units: Mapping[str, str | None] | None = None,
    ) -> DataDistribution:
        """Return a copy extended with new columns under the same policies.

        Extension preserves existing metadata and column order. New columns must
        have the original row count and names that do not already exist.
        """
        additions = type(self).from_data(
            data,
            levels=levels,
            ordered=ordered,
            labels=labels,
            units=units,
            effect_quantiles=self.effect_quantiles,
            display_quantiles=self.display_quantiles,
            categorical_adjustment=self.categorical_adjustment,
            discrete_threshold=self.discrete_threshold,
        )
        duplicates = sorted(set(self.names) & set(additions.names))
        if duplicates:
            raise InputValidationError(
                f"variables already exist: {', '.join(duplicates)}"
            )
        if additions.observation_count != self.observation_count:
            raise InputValidationError(
                "new variables must have the original observation count"
            )
        return replace(self, variables=(*self.variables, *additions.variables))

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the versioned, deterministic metadata document."""
        variable_documents: list[JsonValue] = []
        for variable in self.variables:
            variable_documents.append(
                {
                    "name": variable.name,
                    "kind": variable.kind,
                    "adjustment": variable.adjustment,
                    "effect_range": _range_document(variable.effect_range),
                    "display_range": _range_document(variable.display_range),
                    "overall_range": _range_document(variable.overall_range),
                    "values": list(variable.values),
                    "label": variable.label,
                    "unit": variable.unit,
                    "nonmissing_count": variable.nonmissing_count,
                    "missing_count": variable.missing_count,
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "observation_count": self.observation_count,
            "effect_quantiles": list(self.effect_quantiles),
            "display_quantiles": (
                None if self.display_quantiles is None else list(self.display_quantiles)
            ),
            "categorical_adjustment": self.categorical_adjustment,
            "discrete_threshold": self.discrete_threshold,
            "variables": variable_documents,
        }

    def to_json(self) -> str:
        """Serialize the versioned metadata with canonical JSON ordering."""
        return json.dumps(
            self.to_dict(), allow_nan=False, separators=(",", ":"), sort_keys=True
        )

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical serialized metadata."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> DataDistribution:
        """Reconstruct metadata from a strictly versioned document."""
        required = {
            "schema_version",
            "observation_count",
            "effect_quantiles",
            "display_quantiles",
            "categorical_adjustment",
            "discrete_threshold",
            "variables",
        }
        if set(document) != required:
            raise InputValidationError("data-distribution document fields differ")
        if document["schema_version"] != SCHEMA_VERSION:
            raise InputValidationError("unsupported data-distribution schema version")
        raw_variables = document["variables"]
        if not isinstance(raw_variables, list):
            raise InputValidationError("variables must be an array")
        variables: list[VariableDistribution] = []
        variable_fields = {
            "name",
            "kind",
            "adjustment",
            "effect_range",
            "display_range",
            "overall_range",
            "values",
            "label",
            "unit",
            "nonmissing_count",
            "missing_count",
        }
        for item in cast(list[object], raw_variables):
            if not isinstance(item, dict):
                raise InputValidationError("each variable must be an object")
            raw_variable = cast(dict[str, object], item)
            if set(raw_variable) != variable_fields:
                raise InputValidationError("variable document fields differ")
            raw_values = raw_variable["values"]
            if not isinstance(raw_values, list):
                raise InputValidationError("variable values must be an array")
            values = cast(list[object], raw_values)
            kind = raw_variable["kind"]
            if kind not in {"continuous", "discrete", "categorical", "ordered"}:
                raise InputValidationError(f"unknown variable kind: {kind!r}")
            variables.append(
                VariableDistribution(
                    name=cast(str, raw_variable["name"]),
                    kind=cast(VariableKind, kind),
                    adjustment=cast(DistributionValue, raw_variable["adjustment"]),
                    effect_range=_range_from_document(
                        raw_variable["effect_range"], name="effect_range"
                    ),
                    display_range=_required_range_from_document(
                        raw_variable["display_range"], name="display_range"
                    ),
                    overall_range=_required_range_from_document(
                        raw_variable["overall_range"], name="overall_range"
                    ),
                    values=tuple(cast(DistributionValue, value) for value in values),
                    label=cast(str, raw_variable["label"]),
                    unit=cast(str | None, raw_variable["unit"]),
                    nonmissing_count=_document_integer(
                        raw_variable["nonmissing_count"], name="nonmissing_count"
                    ),
                    missing_count=_document_integer(
                        raw_variable["missing_count"], name="missing_count"
                    ),
                )
            )
        display = document["display_quantiles"]
        if display is not None and not isinstance(display, list):
            raise InputValidationError("display_quantiles must be null or an array")
        effect = document["effect_quantiles"]
        if not isinstance(effect, list):
            raise InputValidationError("effect_quantiles must be an array")
        effect_values = cast(list[object], effect)
        display_values = None if display is None else cast(list[object], display)
        return cls(
            variables=tuple(variables),
            observation_count=_document_integer(
                document["observation_count"], name="observation_count"
            ),
            effect_quantiles=_validate_quantiles(
                (cast(float, item) for item in effect_values),
                name="effect_quantiles",
            ),
            display_quantiles=(
                None
                if display_values is None
                else _validate_quantiles(
                    (cast(float, item) for item in display_values),
                    name="display_quantiles",
                )
            ),
            categorical_adjustment=cast(
                CategoricalAdjustment, document["categorical_adjustment"]
            ),
            discrete_threshold=_document_integer(
                document["discrete_threshold"], name="discrete_threshold"
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> DataDistribution:
        """Reconstruct metadata from a canonical or pretty-printed JSON object."""
        try:
            document: object = json.loads(value)
        except (json.JSONDecodeError, TypeError) as error:
            raise InputValidationError("invalid data-distribution JSON") from error
        if not isinstance(document, dict):
            raise InputValidationError("data-distribution JSON must contain an object")
        return cls.from_dict(cast(dict[str, object], document))


__all__ = [
    "DataDistribution",
    "DistributionRange",
    "VariableDistribution",
]
