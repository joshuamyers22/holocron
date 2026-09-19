"""Backend-neutral nomogram geometry and dependency-free SVG rendering."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Literal, TypeAlias, cast
from xml.etree import ElementTree as ET

from holocron._serialization import canonical_json, parse_json_object
from holocron.design import DataDistribution, DesignMatrix, DesignSpec
from holocron.design.distributions import VariableDistribution
from holocron.exceptions import InputValidationError, UnsupportedFeatureError
from holocron.models.linear import OlsResult
from holocron.models.logistic import BinaryLogisticResult

NomogramValue: TypeAlias = float | str
NomogramModelFamily: TypeAlias = Literal["ols", "binary-logistic"]
NomogramOutcomeScale: TypeAlias = Literal["response", "probability"]
NomogramModel: TypeAlias = OlsResult | BinaryLogisticResult
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

SCHEMA_VERSION = "holocron-nomogram-geometry/v1"
MAX_AXES = 32
MAX_TICKS_PER_AXIS = 128
MAX_OUTCOME_AXES = 16
MAX_TEXT = 4_096
_SVG = "http://www.w3.org/2000/svg"


def _text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT:
        raise InputValidationError(f"{name} must contain 1-{MAX_TEXT} characters")
    return value


def _optional_text(value: object, *, name: str) -> str | None:
    return None if value is None else _text(value, name=name)


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InputValidationError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise InputValidationError(f"{name} must be a finite number")
    return result


def _value(value: object, *, name: str) -> NomogramValue:
    if isinstance(value, str):
        return _text(value, name=name)
    return _finite(value, name=name)


def _expit(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def _format_number(value: float) -> str:
    return f"{value:.6g}"


@dataclass(frozen=True, slots=True)
class NomogramTick:
    """One displayed predictor value and its points contribution."""

    value: NomogramValue
    label: str
    linear_predictor: float
    points: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _value(self.value, name="nomogram value"))
        object.__setattr__(self, "label", _text(self.label, name="tick label"))
        object.__setattr__(
            self,
            "linear_predictor",
            _finite(self.linear_predictor, name="tick linear_predictor"),
        )
        points = _finite(self.points, name="tick points")
        if points < 0.0:
            raise InputValidationError("tick points must be non-negative")
        object.__setattr__(self, "points", points)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return this tick's data-only document."""
        return {
            "value": self.value,
            "label": self.label,
            "linear_predictor": self.linear_predictor,
            "points": self.points,
        }


@dataclass(frozen=True, slots=True)
class NomogramAxis:
    """One predictor axis evaluated with every other predictor adjusted."""

    variable: str
    label: str
    unit: str | None
    adjustment: NomogramValue
    adjustment_linear_predictor: float
    ticks: tuple[NomogramTick, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable", _text(self.variable, name="variable"))
        object.__setattr__(self, "label", _text(self.label, name="axis label"))
        object.__setattr__(self, "unit", _optional_text(self.unit, name="axis unit"))
        object.__setattr__(
            self,
            "adjustment",
            _value(self.adjustment, name="axis adjustment"),
        )
        object.__setattr__(
            self,
            "adjustment_linear_predictor",
            _finite(
                self.adjustment_linear_predictor,
                name="adjustment_linear_predictor",
            ),
        )
        if (
            not isinstance(cast(object, self.ticks), tuple)
            or not 2 <= len(self.ticks) <= MAX_TICKS_PER_AXIS
            or any(
                not isinstance(cast(object, tick), NomogramTick) for tick in self.ticks
            )
        ):
            raise InputValidationError(
                f"axis ticks must contain 2-{MAX_TICKS_PER_AXIS} ticks"
            )
        if len({tick.value for tick in self.ticks}) != len(self.ticks):
            raise InputValidationError("nomogram tick values must be unique")

    @property
    def maximum_points(self) -> float:
        """Return the largest points contribution on this axis."""
        return max(tick.points for tick in self.ticks)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return this axis's data-only document."""
        return {
            "variable": self.variable,
            "label": self.label,
            "unit": self.unit,
            "adjustment": self.adjustment,
            "adjustment_linear_predictor": self.adjustment_linear_predictor,
            "ticks": [tick.to_dict() for tick in self.ticks],
        }


@dataclass(frozen=True, slots=True)
class NomogramOutcomeTick:
    """One outcome value located on the total-points scale."""

    total_points: float
    linear_predictor: float
    value: float
    label: str

    def __post_init__(self) -> None:
        points = _finite(self.total_points, name="outcome total_points")
        if points < 0.0:
            raise InputValidationError("outcome total_points must be non-negative")
        object.__setattr__(self, "total_points", points)
        object.__setattr__(
            self,
            "linear_predictor",
            _finite(self.linear_predictor, name="outcome linear_predictor"),
        )
        object.__setattr__(self, "value", _finite(self.value, name="outcome value"))
        object.__setattr__(self, "label", _text(self.label, name="outcome label"))

    def to_dict(self) -> dict[str, JsonValue]:
        """Return this outcome tick's data-only document."""
        return {
            "total_points": self.total_points,
            "linear_predictor": self.linear_predictor,
            "value": self.value,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class NomogramOutcomeAxis:
    """A response transformation aligned to total points."""

    label: str
    scale: NomogramOutcomeScale
    ticks: tuple[NomogramOutcomeTick, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _text(self.label, name="outcome axis label"))
        if self.scale not in {"response", "probability"}:
            raise InputValidationError("unsupported nomogram outcome scale")
        if (
            not isinstance(cast(object, self.ticks), tuple)
            or not 2 <= len(self.ticks) <= MAX_TICKS_PER_AXIS
            or any(
                not isinstance(cast(object, tick), NomogramOutcomeTick)
                for tick in self.ticks
            )
        ):
            raise InputValidationError("outcome axis ticks are invalid")
        if any(
            left.total_points >= right.total_points
            for left, right in zip(self.ticks, self.ticks[1:], strict=False)
        ):
            raise InputValidationError(
                "outcome total-points ticks must be strictly increasing"
            )
        if self.scale == "probability" and any(
            not 0.0 <= tick.value <= 1.0 for tick in self.ticks
        ):
            raise InputValidationError("probability outcomes must lie inside [0, 1]")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return this outcome axis's data-only document."""
        return {
            "label": self.label,
            "scale": self.scale,
            "ticks": [tick.to_dict() for tick in self.ticks],
        }


@dataclass(frozen=True, slots=True)
class NomogramGeometry:
    """Strict additive points geometry independent of a rendering backend."""

    model_family: NomogramModelFamily
    title: str
    alt_text: str
    maximum_axis_points: float
    linear_predictor_units_per_point: float
    minimum_linear_predictor: float
    maximum_total_points: float
    axes: tuple[NomogramAxis, ...]
    outcome_axes: tuple[NomogramOutcomeAxis, ...]
    design_fingerprint: str
    distribution_fingerprint: str

    def __post_init__(self) -> None:
        if self.model_family not in {"ols", "binary-logistic"}:
            raise InputValidationError("unsupported nomogram model_family")
        object.__setattr__(self, "title", _text(self.title, name="nomogram title"))
        object.__setattr__(
            self,
            "alt_text",
            _text(self.alt_text, name="nomogram alt_text"),
        )
        maximum_axis_points = _finite(
            self.maximum_axis_points, name="maximum_axis_points"
        )
        units = _finite(
            self.linear_predictor_units_per_point,
            name="linear_predictor_units_per_point",
        )
        minimum = _finite(
            self.minimum_linear_predictor, name="minimum_linear_predictor"
        )
        maximum_total = _finite(self.maximum_total_points, name="maximum_total_points")
        if maximum_axis_points <= 0.0 or units <= 0.0 or maximum_total <= 0.0:
            raise InputValidationError("nomogram scales must be positive")
        if (
            not isinstance(cast(object, self.axes), tuple)
            or not 1 <= len(self.axes) <= MAX_AXES
            or any(
                not isinstance(cast(object, axis), NomogramAxis) for axis in self.axes
            )
        ):
            raise InputValidationError(f"nomogram axes must contain 1-{MAX_AXES} axes")
        if len({axis.variable for axis in self.axes}) != len(self.axes):
            raise InputValidationError("nomogram variables must be unique")
        tolerance = max(1e-10, maximum_axis_points * 1e-10)
        if any(
            min(tick.points for tick in axis.ticks) > tolerance
            or axis.maximum_points > maximum_axis_points + tolerance
            for axis in self.axes
        ):
            raise InputValidationError("predictor-axis points violate the shared scale")
        base_linear = self.axes[0].adjustment_linear_predictor
        if any(
            not math.isclose(
                axis.adjustment_linear_predictor,
                base_linear,
                rel_tol=1e-10,
                abs_tol=1e-10,
            )
            for axis in self.axes
        ):
            raise InputValidationError(
                "predictor axes must share one adjustment linear predictor"
            )
        for axis in self.axes:
            axis_minimum = min(tick.linear_predictor for tick in axis.ticks)
            for tick in axis.ticks:
                expected_points = (tick.linear_predictor - axis_minimum) / units
                if not math.isclose(
                    tick.points,
                    expected_points,
                    rel_tol=1e-10,
                    abs_tol=1e-10,
                ):
                    raise InputValidationError(
                        "predictor ticks violate the shared points identity"
                    )
        expected_minimum = base_linear + sum(
            min(tick.linear_predictor for tick in axis.ticks) - base_linear
            for axis in self.axes
        )
        if not math.isclose(
            minimum,
            expected_minimum,
            rel_tol=1e-10,
            abs_tol=1e-10,
        ):
            raise InputValidationError(
                "minimum_linear_predictor violates the additive-axis identity"
            )
        if not math.isclose(
            max(axis.maximum_points for axis in self.axes),
            maximum_axis_points,
            rel_tol=1e-10,
            abs_tol=1e-10,
        ):
            raise InputValidationError(
                "one predictor axis must span maximum_axis_points"
            )
        expected_total = sum(axis.maximum_points for axis in self.axes)
        if not math.isclose(
            maximum_total,
            expected_total,
            rel_tol=1e-10,
            abs_tol=1e-10,
        ):
            raise InputValidationError(
                "maximum_total_points must equal the sum of axis maxima"
            )
        if (
            not isinstance(cast(object, self.outcome_axes), tuple)
            or not 1 <= len(self.outcome_axes) <= MAX_OUTCOME_AXES
            or any(
                not isinstance(cast(object, axis), NomogramOutcomeAxis)
                for axis in self.outcome_axes
            )
        ):
            raise InputValidationError(
                f"outcome_axes must contain 1-{MAX_OUTCOME_AXES} axes"
            )
        expected_outcome_scale: NomogramOutcomeScale = (
            "response" if self.model_family == "ols" else "probability"
        )
        for axis in self.outcome_axes:
            if axis.scale != expected_outcome_scale:
                raise InputValidationError(
                    "outcome scale must match the nomogram model family"
                )
            if not math.isclose(
                axis.ticks[0].total_points,
                0.0,
                abs_tol=1e-10,
            ) or not math.isclose(
                axis.ticks[-1].total_points,
                maximum_total,
                rel_tol=1e-10,
                abs_tol=1e-10,
            ):
                raise InputValidationError(
                    "outcome axes must span the full total-points range"
                )
            for tick in axis.ticks:
                expected_linear = minimum + tick.total_points * units
                if tick.total_points > maximum_total + tolerance or not math.isclose(
                    tick.linear_predictor,
                    expected_linear,
                    rel_tol=1e-10,
                    abs_tol=1e-10,
                ):
                    raise InputValidationError(
                        "outcome ticks violate the total-points identity"
                    )
                expected_value = (
                    tick.linear_predictor
                    if axis.scale == "response"
                    else _expit(tick.linear_predictor)
                )
                if not math.isclose(
                    tick.value,
                    expected_value,
                    rel_tol=1e-10,
                    abs_tol=1e-10,
                ):
                    raise InputValidationError(
                        "outcome values violate their declared transformation"
                    )
        for value, name in (
            (self.design_fingerprint, "design_fingerprint"),
            (self.distribution_fingerprint, "distribution_fingerprint"),
        ):
            if (
                not isinstance(cast(object, value), str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise InputValidationError(f"{name} must be a lowercase SHA-256 digest")

    def linear_predictor(self, total_points: float) -> float:
        """Convert an in-range total-points value to the model linear predictor."""
        points = _finite(total_points, name="total_points")
        if not 0.0 <= points <= self.maximum_total_points:
            raise InputValidationError("total_points is outside the nomogram range")
        return self.minimum_linear_predictor + (
            points * self.linear_predictor_units_per_point
        )

    def predict(self, total_points: float) -> float:
        """Convert total points to the model's response-scale prediction."""
        linear = self.linear_predictor(total_points)
        return linear if self.model_family == "ols" else _expit(linear)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned geometry document."""
        return {
            "schema_version": SCHEMA_VERSION,
            "model_family": self.model_family,
            "title": self.title,
            "alt_text": self.alt_text,
            "maximum_axis_points": self.maximum_axis_points,
            "linear_predictor_units_per_point": (self.linear_predictor_units_per_point),
            "minimum_linear_predictor": self.minimum_linear_predictor,
            "maximum_total_points": self.maximum_total_points,
            "axes": [axis.to_dict() for axis in self.axes],
            "outcome_axes": [axis.to_dict() for axis in self.outcome_axes],
            "design_fingerprint": self.design_fingerprint,
            "distribution_fingerprint": self.distribution_fingerprint,
        }

    def to_json(self) -> str:
        """Return canonical non-executable geometry JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical geometry."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> NomogramGeometry:
        """Reconstruct geometry from an exact-version document."""
        if not isinstance(document, dict):
            raise InputValidationError("nomogram geometry must be an object")
        raw = cast(dict[str, object], document)
        fields = {
            "schema_version",
            "model_family",
            "title",
            "alt_text",
            "maximum_axis_points",
            "linear_predictor_units_per_point",
            "minimum_linear_predictor",
            "maximum_total_points",
            "axes",
            "outcome_axes",
            "design_fingerprint",
            "distribution_fingerprint",
        }
        if set(raw) != fields:
            raise InputValidationError("nomogram geometry fields differ")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise InputValidationError("unsupported nomogram geometry version")
        axes = raw["axes"]
        outcomes = raw["outcome_axes"]
        if not isinstance(axes, list) or not isinstance(outcomes, list):
            raise InputValidationError("nomogram axes must be arrays")
        return cls(
            model_family=cast(NomogramModelFamily, raw["model_family"]),
            title=cast(str, raw["title"]),
            alt_text=cast(str, raw["alt_text"]),
            maximum_axis_points=cast(float, raw["maximum_axis_points"]),
            linear_predictor_units_per_point=cast(
                float, raw["linear_predictor_units_per_point"]
            ),
            minimum_linear_predictor=cast(float, raw["minimum_linear_predictor"]),
            maximum_total_points=cast(float, raw["maximum_total_points"]),
            axes=tuple(_axis_from_dict(value) for value in cast(list[object], axes)),
            outcome_axes=tuple(
                _outcome_axis_from_dict(value) for value in cast(list[object], outcomes)
            ),
            design_fingerprint=cast(str, raw["design_fingerprint"]),
            distribution_fingerprint=cast(str, raw["distribution_fingerprint"]),
        )

    @classmethod
    def from_json(cls, value: str) -> NomogramGeometry:
        """Reconstruct geometry from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="nomogram geometry"))


def _exact_fields(value: object, fields: set[str], *, role: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InputValidationError(f"{role} fields differ")
    raw = cast(dict[object, object], value)
    if set(raw) != fields:
        raise InputValidationError(f"{role} fields differ")
    return cast(dict[str, object], value)


def _tick_from_dict(value: object) -> NomogramTick:
    raw = _exact_fields(
        value,
        {"value", "label", "linear_predictor", "points"},
        role="nomogram tick",
    )
    return NomogramTick(
        value=cast(NomogramValue, raw["value"]),
        label=cast(str, raw["label"]),
        linear_predictor=cast(float, raw["linear_predictor"]),
        points=cast(float, raw["points"]),
    )


def _axis_from_dict(value: object) -> NomogramAxis:
    raw = _exact_fields(
        value,
        {
            "variable",
            "label",
            "unit",
            "adjustment",
            "adjustment_linear_predictor",
            "ticks",
        },
        role="nomogram axis",
    )
    ticks = raw["ticks"]
    if not isinstance(ticks, list):
        raise InputValidationError("nomogram axis ticks must be an array")
    return NomogramAxis(
        variable=cast(str, raw["variable"]),
        label=cast(str, raw["label"]),
        unit=cast(str | None, raw["unit"]),
        adjustment=cast(NomogramValue, raw["adjustment"]),
        adjustment_linear_predictor=cast(float, raw["adjustment_linear_predictor"]),
        ticks=tuple(_tick_from_dict(item) for item in cast(list[object], ticks)),
    )


def _outcome_tick_from_dict(value: object) -> NomogramOutcomeTick:
    raw = _exact_fields(
        value,
        {"total_points", "linear_predictor", "value", "label"},
        role="nomogram outcome tick",
    )
    return NomogramOutcomeTick(
        total_points=cast(float, raw["total_points"]),
        linear_predictor=cast(float, raw["linear_predictor"]),
        value=cast(float, raw["value"]),
        label=cast(str, raw["label"]),
    )


def _outcome_axis_from_dict(value: object) -> NomogramOutcomeAxis:
    raw = _exact_fields(
        value,
        {"label", "scale", "ticks"},
        role="nomogram outcome axis",
    )
    ticks = raw["ticks"]
    if not isinstance(ticks, list):
        raise InputValidationError("nomogram outcome ticks must be an array")
    return NomogramOutcomeAxis(
        label=cast(str, raw["label"]),
        scale=cast(NomogramOutcomeScale, raw["scale"]),
        ticks=tuple(
            _outcome_tick_from_dict(item) for item in cast(list[object], ticks)
        ),
    )


def _predict_linear(model: NomogramModel, design: DesignMatrix) -> tuple[float, ...]:
    if isinstance(model, OlsResult):
        return model.predict(design)
    return model.predict_linear(design)


def _tick_values(
    variable: VariableDistribution,
    *,
    continuous_ticks: int,
) -> tuple[NomogramValue, ...]:
    if variable.kind == "continuous":
        lower = cast(float, variable.display_range.lower)
        upper = cast(float, variable.display_range.upper)
        if lower >= upper:
            raise InputValidationError("continuous display range must increase")
        return tuple(
            lower + index * (upper - lower) / (continuous_ticks - 1)
            for index in range(continuous_ticks)
        )
    if not variable.values:
        raise InputValidationError("discrete and categorical axes require values")
    return variable.values


def build_nomogram(
    model: NomogramModel,
    design: DesignSpec,
    distribution: DataDistribution,
    *,
    maximum_axis_points: float = 100.0,
    continuous_ticks: int = 5,
    outcome_ticks: int = 6,
    title: str = "Nomogram",
    outcome_label: str | None = None,
) -> NomogramGeometry:
    """Build additive points geometry for an identity-bound OLS or logit model.

    Every predictor is varied across its declared display values while all other
    predictors remain at their explicit distribution adjustment. Interactions
    are rejected because they do not admit one unconditional predictor axis.
    """
    if not isinstance(cast(object, model), (OlsResult, BinaryLogisticResult)):
        raise InputValidationError("model must be an OlsResult or BinaryLogisticResult")
    if not isinstance(cast(object, design), DesignSpec):
        raise InputValidationError("design must be a DesignSpec")
    if not isinstance(cast(object, distribution), DataDistribution):
        raise InputValidationError("distribution must be a DataDistribution")
    maximum = _finite(maximum_axis_points, name="maximum_axis_points")
    if maximum <= 0.0:
        raise InputValidationError("maximum_axis_points must be positive")
    for count, name, upper in (
        (continuous_ticks, "continuous_ticks", 25),
        (outcome_ticks, "outcome_ticks", 25),
    ):
        if (
            isinstance(cast(object, count), bool)
            or not isinstance(cast(object, count), Integral)
            or not 2 <= count <= upper
        ):
            raise InputValidationError(f"{name} must be an integer from 2 to {upper}")
    predictors = design.formula.predictor_names
    if any(design.interactions_containing(name) for name in predictors):
        raise UnsupportedFeatureError(
            "nomogram axes do not support interaction terms; conditional axes are "
            "not yet implemented"
        )
    if model.design_fingerprint != design.fingerprint:
        raise InputValidationError(
            "model design fingerprint must match the nomogram DesignSpec"
        )
    expected_names = (
        ("Intercept",) if model.includes_intercept else ()
    ) + design.column_names
    if model.coefficient_names != expected_names:
        raise InputValidationError(
            "model coefficient names do not match the nomogram DesignSpec"
        )
    try:
        variables = tuple(distribution[name] for name in predictors)
    except KeyError as error:
        raise InputValidationError(
            f"distribution is missing predictor {error.args[0]!r}"
        ) from error

    adjustments = {name: distribution[name].adjustment for name in predictors}
    base_data = {name: (adjustments[name],) for name in predictors}
    base_linear = _predict_linear(model, design.transform(base_data))[0]
    raw_axes: list[
        tuple[VariableDistribution, tuple[NomogramValue, ...], tuple[float, ...]]
    ] = []
    for variable in variables:
        values = _tick_values(variable, continuous_ticks=continuous_ticks)
        count = len(values)
        data = {
            name: values if name == variable.name else (adjustments[name],) * count
            for name in predictors
        }
        linear = _predict_linear(model, design.transform(data))
        raw_axes.append((variable, values, linear))

    ranges = tuple(max(linear) - min(linear) for _, _, linear in raw_axes)
    largest_range = max(ranges)
    if largest_range <= 1e-14:
        raise InputValidationError(
            "nomogram requires predictor variation on the linear-predictor scale"
        )
    units_per_point = largest_range / maximum
    axes: list[NomogramAxis] = []
    minimum_linear = base_linear
    for (variable_raw, values, linear), effect_range in zip(
        raw_axes, ranges, strict=True
    ):
        variable = variable_raw
        minimum = min(linear)
        minimum_linear += minimum - base_linear
        ticks = tuple(
            NomogramTick(
                value=value,
                label=value if isinstance(value, str) else _format_number(value),
                linear_predictor=prediction,
                points=max(0.0, (prediction - minimum) / units_per_point),
            )
            for value, prediction in zip(values, linear, strict=True)
        )
        axes.append(
            NomogramAxis(
                variable=variable.name,
                label=variable.label,
                unit=variable.unit,
                adjustment=variable.adjustment,
                adjustment_linear_predictor=base_linear,
                ticks=ticks,
            )
        )
        if effect_range <= 1e-14 and any(tick.points != 0.0 for tick in ticks):
            raise InputValidationError("zero-range axis produced nonzero points")

    maximum_total = sum(axis.maximum_points for axis in axes)
    outcome_scale: NomogramOutcomeScale = (
        "response" if isinstance(model, OlsResult) else "probability"
    )
    effective_outcome_label = outcome_label or (
        "Predicted value" if outcome_scale == "response" else "Event probability"
    )
    outcome_values: list[NomogramOutcomeTick] = []
    for index in range(outcome_ticks):
        points = index * maximum_total / (outcome_ticks - 1)
        linear = minimum_linear + points * units_per_point
        value = linear if outcome_scale == "response" else _expit(linear)
        outcome_values.append(
            NomogramOutcomeTick(
                total_points=points,
                linear_predictor=linear,
                value=value,
                label=_format_number(value),
            )
        )
    family: NomogramModelFamily = (
        "ols" if isinstance(model, OlsResult) else "binary-logistic"
    )
    return NomogramGeometry(
        model_family=family,
        title=title,
        alt_text=(
            f"Nomogram for a {family} model with {len(axes)} predictor axes, "
            "a shared points scale, total points, and one predicted outcome axis."
        ),
        maximum_axis_points=maximum,
        linear_predictor_units_per_point=units_per_point,
        minimum_linear_predictor=minimum_linear,
        maximum_total_points=maximum_total,
        axes=tuple(axes),
        outcome_axes=(
            NomogramOutcomeAxis(
                label=effective_outcome_label,
                scale=outcome_scale,
                ticks=tuple(outcome_values),
            ),
        ),
        design_fingerprint=design.fingerprint,
        distribution_fingerprint=distribution.fingerprint,
    )


def _element(
    parent: ET.Element,
    tag: str,
    attributes: dict[str, str] | None = None,
    text: str | None = None,
) -> ET.Element:
    child = ET.SubElement(parent, f"{{{_SVG}}}{tag}", attributes or {})
    child.text = text
    return child


def _coordinate(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _projector(maximum: float, left: float, right: float) -> Callable[[float], float]:
    def project(value: float) -> float:
        return left + value / maximum * (right - left)

    return project


def _draw_scale(
    root: ET.Element,
    *,
    label: str,
    ticks: tuple[tuple[float, str], ...],
    project: Callable[[float], float],
    left: float,
    right: float,
    y: float,
    rotate_labels: bool = False,
) -> None:
    group = _element(
        root,
        "g",
        {"role": "group", "aria-label": label},
    )
    _element(
        group,
        "text",
        {
            "x": _coordinate(left - 16.0),
            "y": _coordinate(y + 4.0),
            "text-anchor": "end",
            "font-size": "12",
            "font-weight": "600",
            "fill": "#111111",
        },
        label,
    )
    _element(
        group,
        "line",
        {
            "x1": _coordinate(left),
            "x2": _coordinate(right),
            "y1": _coordinate(y),
            "y2": _coordinate(y),
            "stroke": "#222222",
            "stroke-width": "1.4",
        },
    )
    for value, tick_label in ticks:
        x = project(value)
        _element(
            group,
            "line",
            {
                "x1": _coordinate(x),
                "x2": _coordinate(x),
                "y1": _coordinate(y - 5.0),
                "y2": _coordinate(y + 5.0),
                "stroke": "#222222",
            },
        )
        attributes = {
            "x": _coordinate(x),
            "y": _coordinate(y + 19.0),
            "text-anchor": "middle",
            "font-size": "10",
            "fill": "#222222",
        }
        if rotate_labels:
            attributes["text-anchor"] = "end"
            attributes["transform"] = (
                f"rotate(-35 {_coordinate(x)} {_coordinate(y + 19.0)})"
            )
        _element(group, "text", attributes, tick_label)


def render_nomogram_svg(
    geometry: NomogramGeometry,
    *,
    width: int = 1000,
    height: int | None = None,
) -> str:
    """Render nomogram geometry as deterministic accessible inline SVG."""
    if not isinstance(cast(object, geometry), NomogramGeometry):
        raise InputValidationError("geometry must be a NomogramGeometry")
    if (
        isinstance(cast(object, width), bool)
        or not isinstance(cast(object, width), Integral)
        or not 640 <= width <= 4096
    ):
        raise InputValidationError("width must be an integer from 640 to 4096")
    natural_height = 190 + 78 * len(geometry.axes) + 70 * len(geometry.outcome_axes)
    effective_height = natural_height if height is None else height
    if (
        isinstance(cast(object, effective_height), bool)
        or not isinstance(cast(object, effective_height), Integral)
        or not 320 <= effective_height <= 4096
        or effective_height < natural_height
    ):
        raise InputValidationError(
            f"height must be an integer from {max(320, natural_height)} to 4096"
        )
    ET.register_namespace("", _SVG)
    title_id = f"nomogram-{geometry.fingerprint[:12]}-title"
    description_id = f"nomogram-{geometry.fingerprint[:12]}-description"
    root = ET.Element(
        f"{{{_SVG}}}svg",
        {
            "width": str(width),
            "height": str(effective_height),
            "viewBox": f"0 0 {width} {effective_height}",
            "role": "img",
            "aria-roledescription": "nomogram",
            "aria-labelledby": f"{title_id} {description_id}",
            "focusable": "false",
        },
    )
    _element(root, "title", {"id": title_id}, geometry.title)
    _element(root, "desc", {"id": description_id}, geometry.alt_text)
    _element(
        root,
        "metadata",
        text=f"{SCHEMA_VERSION} sha256:{geometry.fingerprint}",
    )
    _element(
        root,
        "rect",
        {"width": "100%", "height": "100%", "fill": "#FFFFFF"},
    )
    _element(
        root,
        "text",
        {
            "x": "24",
            "y": "30",
            "font-size": "19",
            "font-weight": "600",
            "fill": "#111111",
        },
        geometry.title,
    )
    left = min(230.0, max(150.0, max(len(axis.label) for axis in geometry.axes) * 7.0))
    right = float(width) - 40.0
    if right - left < 320.0:
        raise InputValidationError("width leaves no usable nomogram plotting area")
    points_project = _projector(geometry.maximum_axis_points, left, right)
    points_ticks = tuple(
        (
            index * geometry.maximum_axis_points / 5.0,
            _format_number(index * geometry.maximum_axis_points / 5.0),
        )
        for index in range(6)
    )
    y = 64.0
    _draw_scale(
        root,
        label="Points",
        ticks=points_ticks,
        project=points_project,
        left=left,
        right=right,
        y=y,
    )
    for axis in geometry.axes:
        y += 78.0
        axis_label = axis.label if axis.unit is None else f"{axis.label} ({axis.unit})"
        _draw_scale(
            root,
            label=axis_label,
            ticks=tuple((tick.points, tick.label) for tick in axis.ticks),
            project=points_project,
            left=left,
            right=right,
            y=y,
            rotate_labels=len(axis.ticks) > 8,
        )
    y += 82.0
    total_project = _projector(geometry.maximum_total_points, left, right)
    total_ticks = tuple(
        (
            index * geometry.maximum_total_points / 5.0,
            _format_number(index * geometry.maximum_total_points / 5.0),
        )
        for index in range(6)
    )
    _draw_scale(
        root,
        label="Total points",
        ticks=total_ticks,
        project=total_project,
        left=left,
        right=right,
        y=y,
    )
    for outcome in geometry.outcome_axes:
        y += 70.0
        _draw_scale(
            root,
            label=outcome.label,
            ticks=tuple((tick.total_points, tick.label) for tick in outcome.ticks),
            project=total_project,
            left=left,
            right=right,
            y=y,
        )
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)
