"""Immutable backend-neutral plot specifications."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from numbers import Real
from typing import Literal, TypeAlias, cast

from holocron._serialization import canonical_json, parse_json_object
from holocron.exceptions import InputValidationError

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
AxisScale: TypeAlias = Literal["linear", "log", "logit", "probability", "categorical"]
PlotKind: TypeAlias = Literal[
    "effect",
    "contrast",
    "anova",
    "validation",
    "calibration",
    "survival",
    "diagnostic",
    "nomogram",
    "custom",
]
LayerRole: TypeAlias = Literal[
    "estimate", "interval", "observed", "reference", "comparison", "diagnostic"
]
Orientation: TypeAlias = Literal["vertical", "horizontal"]

SCHEMA_VERSION = "holocron-plot-spec/v1"
MAX_LAYERS = 256
MAX_ANNOTATIONS = 256
MAX_METADATA = 128
MAX_POINTS_PER_LAYER = 100_000
MAX_TOTAL_POINTS = 1_000_000
MAX_TEXT = 4_096
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _identifier(value: object, *, name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise InputValidationError(
            f"{name} must contain 1-128 letters, digits, dots, underscores, or hyphens"
        )
    return value


def _text(value: object, *, name: str, allow_empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or (not allow_empty and not value)
        or len(value) > MAX_TEXT
    ):
        qualifier = "0" if allow_empty else "1"
        raise InputValidationError(
            f"{name} must contain {qualifier}-{MAX_TEXT} characters"
        )
    return value


def _optional_text(value: object, *, name: str) -> str | None:
    return None if value is None else _text(value, name=name)


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InputValidationError(f"{name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise InputValidationError(f"{name} must be a finite number")
    return normalized


def _finite_tuple(value: object, *, name: str) -> tuple[float, ...]:
    if not isinstance(value, tuple) or not value:
        raise InputValidationError(f"{name} must be a non-empty tuple")
    raw = cast(tuple[object, ...], value)
    if len(raw) > MAX_POINTS_PER_LAYER:
        raise InputValidationError(
            f"{name} exceeds the {MAX_POINTS_PER_LAYER}-point limit"
        )
    return tuple(_finite(item, name=name) for item in raw)


def _categories(value: object, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise InputValidationError(f"{name} must be a non-empty tuple")
    raw = cast(tuple[object, ...], value)
    if len(raw) > MAX_POINTS_PER_LAYER:
        raise InputValidationError(
            f"{name} exceeds the {MAX_POINTS_PER_LAYER}-category limit"
        )
    values = tuple(_text(item, name=name) for item in raw)
    if len(set(values)) != len(values):
        raise InputValidationError(f"{name} must be unique within a layer")
    return values


def _same_length(*values: tuple[object, ...], role: str) -> None:
    if len({len(value) for value in values}) != 1:
        raise InputValidationError(f"{role} coordinate lengths must match")


def _role(value: object) -> LayerRole:
    if value not in (
        "estimate",
        "interval",
        "observed",
        "reference",
        "comparison",
        "diagnostic",
    ):
        raise InputValidationError("unsupported plot layer role")
    return value


def _orientation(value: object) -> Orientation:
    if value not in ("vertical", "horizontal"):
        raise InputValidationError("orientation must be 'vertical' or 'horizontal'")
    return value


@dataclass(frozen=True, slots=True)
class AxisSpec:
    """One semantic plot axis without renderer-specific styling."""

    label: str
    scale: AxisScale = "linear"
    limits: tuple[float, float] | None = None
    ticks: tuple[float, ...] = ()
    tick_labels: tuple[str, ...] = ()
    unit: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _text(self.label, name="axis label"))
        if self.scale not in (
            "linear",
            "log",
            "logit",
            "probability",
            "categorical",
        ):
            raise InputValidationError("unsupported axis scale")
        object.__setattr__(self, "unit", _optional_text(self.unit, name="axis unit"))
        if self.scale == "categorical":
            if self.limits is not None or self.ticks or self.tick_labels:
                raise InputValidationError(
                    "categorical axes do not accept numeric limits or ticks"
                )
            return
        if self.limits is not None:
            if (
                not isinstance(cast(object, self.limits), tuple)
                or len(self.limits) != 2
            ):
                raise InputValidationError("axis limits must contain two values")
            limits = tuple(_finite(value, name="axis limit") for value in self.limits)
            if limits[0] >= limits[1]:
                raise InputValidationError("axis limits must be strictly increasing")
            object.__setattr__(self, "limits", cast(tuple[float, float], limits))
            for value in limits:
                _validate_scale_value(value, self.scale, role="axis limit")
        if not isinstance(cast(object, self.ticks), tuple):
            raise InputValidationError("axis ticks must be a tuple")
        ticks = tuple(_finite(value, name="axis tick") for value in self.ticks)
        if len(ticks) > MAX_POINTS_PER_LAYER or any(
            left >= right for left, right in zip(ticks, ticks[1:], strict=False)
        ):
            raise InputValidationError(
                "axis ticks must be bounded and strictly increasing"
            )
        for value in ticks:
            _validate_scale_value(value, self.scale, role="axis tick")
        object.__setattr__(self, "ticks", ticks)
        if not isinstance(cast(object, self.tick_labels), tuple):
            raise InputValidationError("tick_labels must be a tuple")
        labels = tuple(_text(value, name="tick label") for value in self.tick_labels)
        if labels and len(labels) != len(ticks):
            raise InputValidationError("tick_labels must match axis ticks")
        object.__setattr__(self, "tick_labels", labels)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the data-only axis document."""
        return {
            "label": self.label,
            "scale": self.scale,
            "limits": None if self.limits is None else list(self.limits),
            "ticks": list(self.ticks),
            "tick_labels": list(self.tick_labels),
            "unit": self.unit,
        }


def _validate_scale_value(value: float, scale: AxisScale, *, role: str) -> None:
    if scale == "log" and value <= 0.0:
        raise InputValidationError(f"{role} must be positive on a log axis")
    if scale == "logit" and not 0.0 < value < 1.0:
        raise InputValidationError(f"{role} must be inside (0, 1) on a logit axis")
    if scale == "probability" and not 0.0 <= value <= 1.0:
        raise InputValidationError(
            f"{role} must be inside [0, 1] on a probability axis"
        )


@dataclass(frozen=True, slots=True)
class LineLayer:
    """An ordered numeric line or step series."""

    layer_id: str
    x: tuple[float, ...]
    y: tuple[float, ...]
    label: str | None = None
    role: LayerRole = "estimate"
    interpolation: Literal["linear", "step"] = "linear"

    def __post_init__(self) -> None:
        _identifier(self.layer_id, name="layer_id")
        x = _finite_tuple(self.x, name="line x")
        y = _finite_tuple(self.y, name="line y")
        _same_length(x, y, role="line")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "label", _optional_text(self.label, name="line label"))
        object.__setattr__(self, "role", _role(self.role))
        if self.interpolation not in ("linear", "step"):
            raise InputValidationError("line interpolation must be linear or step")


@dataclass(frozen=True, slots=True)
class PointLayer:
    """A numeric point series."""

    layer_id: str
    x: tuple[float, ...]
    y: tuple[float, ...]
    label: str | None = None
    role: LayerRole = "observed"

    def __post_init__(self) -> None:
        _identifier(self.layer_id, name="layer_id")
        x = _finite_tuple(self.x, name="point x")
        y = _finite_tuple(self.y, name="point y")
        _same_length(x, y, role="point")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(
            self, "label", _optional_text(self.label, name="point label")
        )
        object.__setattr__(self, "role", _role(self.role))


@dataclass(frozen=True, slots=True)
class BandLayer:
    """A numeric lower/upper interval band over ordered x values."""

    layer_id: str
    x: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    label: str | None = None
    role: LayerRole = "interval"

    def __post_init__(self) -> None:
        _identifier(self.layer_id, name="layer_id")
        x = _finite_tuple(self.x, name="band x")
        lower = _finite_tuple(self.lower, name="band lower")
        upper = _finite_tuple(self.upper, name="band upper")
        _same_length(x, lower, upper, role="band")
        if any(low > high for low, high in zip(lower, upper, strict=True)):
            raise InputValidationError("band lower values must not exceed upper values")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(self, "label", _optional_text(self.label, name="band label"))
        object.__setattr__(self, "role", _role(self.role))


@dataclass(frozen=True, slots=True)
class BarLayer:
    """A categorical bar series with a declared orientation."""

    layer_id: str
    categories: tuple[str, ...]
    values: tuple[float, ...]
    label: str | None = None
    role: LayerRole = "estimate"
    orientation: Orientation = "vertical"

    def __post_init__(self) -> None:
        _identifier(self.layer_id, name="layer_id")
        categories = _categories(self.categories, name="bar categories")
        values = _finite_tuple(self.values, name="bar values")
        _same_length(categories, values, role="bar")
        object.__setattr__(self, "categories", categories)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "label", _optional_text(self.label, name="bar label"))
        object.__setattr__(self, "role", _role(self.role))
        object.__setattr__(self, "orientation", _orientation(self.orientation))


@dataclass(frozen=True, slots=True)
class IntervalLayer:
    """Categorical estimates with lower and upper interval endpoints."""

    layer_id: str
    categories: tuple[str, ...]
    estimates: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    label: str | None = None
    role: LayerRole = "comparison"
    orientation: Orientation = "horizontal"

    def __post_init__(self) -> None:
        _identifier(self.layer_id, name="layer_id")
        categories = _categories(self.categories, name="interval categories")
        estimates = _finite_tuple(self.estimates, name="interval estimates")
        lower = _finite_tuple(self.lower, name="interval lower")
        upper = _finite_tuple(self.upper, name="interval upper")
        _same_length(categories, estimates, lower, upper, role="interval")
        if any(
            not low <= estimate <= high
            for estimate, low, high in zip(estimates, lower, upper, strict=True)
        ):
            raise InputValidationError(
                "interval estimates must lie between lower and upper endpoints"
            )
        object.__setattr__(self, "categories", categories)
        object.__setattr__(self, "estimates", estimates)
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(
            self,
            "label",
            _optional_text(self.label, name="interval label"),
        )
        object.__setattr__(self, "role", _role(self.role))
        object.__setattr__(self, "orientation", _orientation(self.orientation))


PlotLayer: TypeAlias = LineLayer | PointLayer | BandLayer | BarLayer | IntervalLayer


@dataclass(frozen=True, slots=True)
class ReferenceLine:
    """A semantic horizontal or vertical reference line."""

    axis: Literal["x", "y"]
    value: float
    label: str | None = None

    def __post_init__(self) -> None:
        if self.axis not in ("x", "y"):
            raise InputValidationError("reference-line axis must be 'x' or 'y'")
        object.__setattr__(self, "value", _finite(self.value, name="reference value"))
        object.__setattr__(
            self,
            "label",
            _optional_text(self.label, name="reference label"),
        )


@dataclass(frozen=True, slots=True)
class TextAnnotation:
    """Text anchored at one pair of numeric data coordinates."""

    x: float
    y: float
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, name="annotation x"))
        object.__setattr__(self, "y", _finite(self.y, name="annotation y"))
        object.__setattr__(self, "text", _text(self.text, name="annotation text"))


PlotAnnotation: TypeAlias = ReferenceLine | TextAnnotation


@dataclass(frozen=True, slots=True)
class PlotMetadata:
    """One bounded string-valued plot provenance or interpretation field."""

    key: str
    value: str

    def __post_init__(self) -> None:
        _identifier(self.key, name="metadata key")
        object.__setattr__(self, "value", _text(self.value, name="metadata value"))


def _layer_points(layer: PlotLayer) -> int:
    return (
        len(layer.categories)
        if isinstance(layer, (BarLayer, IntervalLayer))
        else len(layer.x)
    )


def _layer_dict(layer: PlotLayer) -> dict[str, JsonValue]:
    base: dict[str, JsonValue] = {
        "layer_id": layer.layer_id,
        "label": layer.label,
        "role": layer.role,
    }
    if isinstance(layer, LineLayer):
        return {
            "layer_type": "line",
            **base,
            "x": list(layer.x),
            "y": list(layer.y),
            "interpolation": layer.interpolation,
        }
    if isinstance(layer, PointLayer):
        return {
            "layer_type": "point",
            **base,
            "x": list(layer.x),
            "y": list(layer.y),
        }
    if isinstance(layer, BandLayer):
        return {
            "layer_type": "band",
            **base,
            "x": list(layer.x),
            "lower": list(layer.lower),
            "upper": list(layer.upper),
        }
    if isinstance(layer, BarLayer):
        return {
            "layer_type": "bar",
            **base,
            "categories": list(layer.categories),
            "values": list(layer.values),
            "orientation": layer.orientation,
        }
    return {
        "layer_type": "interval",
        **base,
        "categories": list(layer.categories),
        "estimates": list(layer.estimates),
        "lower": list(layer.lower),
        "upper": list(layer.upper),
        "orientation": layer.orientation,
    }


def _annotation_dict(annotation: PlotAnnotation) -> dict[str, JsonValue]:
    if isinstance(annotation, ReferenceLine):
        return {
            "annotation_type": "reference-line",
            "axis": annotation.axis,
            "value": annotation.value,
            "label": annotation.label,
        }
    return {
        "annotation_type": "text",
        "x": annotation.x,
        "y": annotation.y,
        "text": annotation.text,
    }


@dataclass(frozen=True, slots=True)
class PlotSpec:
    """A bounded renderer-independent plot document with accessible meaning."""

    plot_id: str
    kind: PlotKind
    title: str
    alt_text: str
    x_axis: AxisSpec
    y_axis: AxisSpec
    layers: tuple[PlotLayer, ...]
    subtitle: str | None = None
    caption: str | None = None
    annotations: tuple[PlotAnnotation, ...] = ()
    metadata: tuple[PlotMetadata, ...] = ()
    show_legend: bool = True
    legend_order: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.plot_id, name="plot_id")
        if self.kind not in (
            "effect",
            "contrast",
            "anova",
            "validation",
            "calibration",
            "survival",
            "diagnostic",
            "nomogram",
            "custom",
        ):
            raise InputValidationError("unsupported plot kind")
        object.__setattr__(self, "title", _text(self.title, name="plot title"))
        object.__setattr__(self, "alt_text", _text(self.alt_text, name="alt_text"))
        object.__setattr__(
            self,
            "subtitle",
            _optional_text(self.subtitle, name="plot subtitle"),
        )
        object.__setattr__(
            self,
            "caption",
            _optional_text(self.caption, name="plot caption"),
        )
        if not isinstance(cast(object, self.x_axis), AxisSpec) or not isinstance(
            cast(object, self.y_axis), AxisSpec
        ):
            raise InputValidationError("plot axes must be AxisSpec values")
        if (
            not isinstance(cast(object, self.layers), tuple)
            or not self.layers
            or len(self.layers) > MAX_LAYERS
            or any(
                not isinstance(
                    cast(object, layer),
                    (LineLayer, PointLayer, BandLayer, BarLayer, IntervalLayer),
                )
                for layer in self.layers
            )
        ):
            raise InputValidationError(f"layers must contain 1-{MAX_LAYERS} layers")
        layer_ids = tuple(layer.layer_id for layer in self.layers)
        if len(set(layer_ids)) != len(layer_ids):
            raise InputValidationError("plot layer identifiers must be unique")
        if sum(_layer_points(layer) for layer in self.layers) > MAX_TOTAL_POINTS:
            raise InputValidationError(
                f"plot exceeds the {MAX_TOTAL_POINTS}-point total limit"
            )
        for layer in self.layers:
            self._validate_layer_axes(layer)
        if (
            not isinstance(cast(object, self.annotations), tuple)
            or len(self.annotations) > MAX_ANNOTATIONS
            or any(
                not isinstance(cast(object, item), (ReferenceLine, TextAnnotation))
                for item in self.annotations
            )
        ):
            raise InputValidationError("plot annotations are invalid")
        for annotation in self.annotations:
            self._validate_annotation(annotation)
        if (
            not isinstance(cast(object, self.metadata), tuple)
            or len(self.metadata) > MAX_METADATA
            or any(
                not isinstance(cast(object, item), PlotMetadata)
                for item in self.metadata
            )
            or len({item.key for item in self.metadata}) != len(self.metadata)
        ):
            raise InputValidationError("plot metadata keys must be unique and bounded")
        if not isinstance(cast(object, self.show_legend), bool):
            raise InputValidationError("show_legend must be boolean")
        if not isinstance(cast(object, self.legend_order), tuple):
            raise InputValidationError("legend_order must be a tuple")
        legend_order = tuple(
            _identifier(item, name="legend layer ID")
            for item in cast(tuple[object, ...], cast(object, self.legend_order))
        )
        object.__setattr__(self, "legend_order", legend_order)
        if len(set(legend_order)) != len(legend_order) or any(
            layer_id not in layer_ids for layer_id in legend_order
        ):
            raise InputValidationError("legend_order must contain unique layer IDs")
        labeled = {layer.layer_id for layer in self.layers if layer.label is not None}
        if any(layer_id not in labeled for layer_id in self.legend_order):
            raise InputValidationError("legend_order layers must have labels")
        if not self.show_legend and self.legend_order:
            raise InputValidationError("hidden legends do not accept legend_order")

    def _validate_layer_axes(self, layer: PlotLayer) -> None:
        if isinstance(layer, (LineLayer, PointLayer, BandLayer)):
            if "categorical" in {self.x_axis.scale, self.y_axis.scale}:
                raise InputValidationError(
                    "numeric layers require two non-categorical axes"
                )
            for value in layer.x:
                _validate_scale_value(value, self.x_axis.scale, role="layer x")
            y_values = (
                (*layer.lower, *layer.upper)
                if isinstance(layer, BandLayer)
                else layer.y
            )
            for value in y_values:
                _validate_scale_value(value, self.y_axis.scale, role="layer y")
            return
        category_axis = self.x_axis if layer.orientation == "vertical" else self.y_axis
        value_axis = self.y_axis if layer.orientation == "vertical" else self.x_axis
        if category_axis.scale != "categorical" or value_axis.scale == "categorical":
            raise InputValidationError(
                "categorical layer orientation must match one categorical axis"
            )
        values = (
            (*layer.lower, *layer.estimates, *layer.upper)
            if isinstance(layer, IntervalLayer)
            else layer.values
        )
        for value in values:
            _validate_scale_value(value, value_axis.scale, role="layer value")

    def _validate_annotation(self, annotation: PlotAnnotation) -> None:
        if isinstance(annotation, ReferenceLine):
            axis = self.x_axis if annotation.axis == "x" else self.y_axis
            if axis.scale == "categorical":
                raise InputValidationError(
                    "numeric reference lines cannot target categorical axes"
                )
            _validate_scale_value(annotation.value, axis.scale, role="reference value")
            return
        if "categorical" in {self.x_axis.scale, self.y_axis.scale}:
            raise InputValidationError(
                "numeric text annotations require non-categorical axes"
            )
        _validate_scale_value(annotation.x, self.x_axis.scale, role="annotation x")
        _validate_scale_value(annotation.y, self.y_axis.scale, role="annotation y")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict data-only plot document."""
        return {
            "schema_version": SCHEMA_VERSION,
            "plot_id": self.plot_id,
            "kind": self.kind,
            "title": self.title,
            "subtitle": self.subtitle,
            "caption": self.caption,
            "alt_text": self.alt_text,
            "x_axis": self.x_axis.to_dict(),
            "y_axis": self.y_axis.to_dict(),
            "layers": [_layer_dict(layer) for layer in self.layers],
            "annotations": [
                _annotation_dict(annotation) for annotation in self.annotations
            ],
            "metadata": [
                {"key": item.key, "value": item.value} for item in self.metadata
            ],
            "show_legend": self.show_legend,
            "legend_order": list(self.legend_order),
        }

    def to_json(self) -> str:
        """Return canonical, non-executable JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical plot document."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> PlotSpec:
        """Reconstruct a plot specification from an exact-version document."""
        if not isinstance(document, dict):
            raise InputValidationError("plot specification must be an object")
        raw = cast(dict[str, object], document)
        fields = {
            "schema_version",
            "plot_id",
            "kind",
            "title",
            "subtitle",
            "caption",
            "alt_text",
            "x_axis",
            "y_axis",
            "layers",
            "annotations",
            "metadata",
            "show_legend",
            "legend_order",
        }
        if set(raw) != fields:
            raise InputValidationError("plot specification fields differ")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise InputValidationError("unsupported plot specification version")
        layers_raw = raw["layers"]
        annotations_raw = raw["annotations"]
        metadata_raw = raw["metadata"]
        legend_raw = raw["legend_order"]
        if (
            not isinstance(layers_raw, list)
            or not isinstance(annotations_raw, list)
            or not isinstance(metadata_raw, list)
            or not isinstance(legend_raw, list)
        ):
            raise InputValidationError("plot collections must be arrays")
        return cls(
            plot_id=cast(str, raw["plot_id"]),
            kind=cast(PlotKind, raw["kind"]),
            title=cast(str, raw["title"]),
            subtitle=cast(str | None, raw["subtitle"]),
            caption=cast(str | None, raw["caption"]),
            alt_text=cast(str, raw["alt_text"]),
            x_axis=_axis_from_dict(raw["x_axis"]),
            y_axis=_axis_from_dict(raw["y_axis"]),
            layers=tuple(
                _layer_from_dict(item) for item in cast(list[object], layers_raw)
            ),
            annotations=tuple(
                _annotation_from_dict(item)
                for item in cast(list[object], annotations_raw)
            ),
            metadata=tuple(
                _metadata_from_dict(item) for item in cast(list[object], metadata_raw)
            ),
            show_legend=cast(bool, raw["show_legend"]),
            legend_order=tuple(cast(list[str], legend_raw)),
        )

    @classmethod
    def from_json(cls, value: str) -> PlotSpec:
        """Reconstruct a plot specification from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="plot specification"))


def _exact_dict(value: object, *, fields: set[str], role: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InputValidationError(f"{role} must be an object")
    result = cast(dict[str, object], value)
    if set(result) != fields:
        raise InputValidationError(f"{role} fields differ")
    return result


def _axis_from_dict(value: object) -> AxisSpec:
    raw = _exact_dict(
        value,
        fields={"label", "scale", "limits", "ticks", "tick_labels", "unit"},
        role="axis",
    )
    limits_raw = raw["limits"]
    ticks_raw = raw["ticks"]
    labels_raw = raw["tick_labels"]
    if (
        (limits_raw is not None and not isinstance(limits_raw, list))
        or not isinstance(ticks_raw, list)
        or not isinstance(labels_raw, list)
    ):
        raise InputValidationError("axis numeric collections must be arrays")
    limits = None if limits_raw is None else tuple(cast(list[float], limits_raw))
    return AxisSpec(
        label=cast(str, raw["label"]),
        scale=cast(AxisScale, raw["scale"]),
        limits=cast(tuple[float, float] | None, limits),
        ticks=tuple(cast(list[float], ticks_raw)),
        tick_labels=tuple(cast(list[str], labels_raw)),
        unit=cast(str | None, raw["unit"]),
    )


def _layer_from_dict(value: object) -> PlotLayer:
    if not isinstance(value, dict):
        raise InputValidationError("plot layer must be an object")
    raw = cast(dict[str, object], value)
    layer_type = raw.get("layer_type")
    common = {"layer_type", "layer_id", "label", "role"}
    if layer_type == "line":
        expected = common | {"x", "y", "interpolation"}
    elif layer_type == "point":
        expected = common | {"x", "y"}
    elif layer_type == "band":
        expected = common | {"x", "lower", "upper"}
    elif layer_type == "bar":
        expected = common | {"categories", "values", "orientation"}
    elif layer_type == "interval":
        expected = common | {
            "categories",
            "estimates",
            "lower",
            "upper",
            "orientation",
        }
    else:
        raise InputValidationError("unsupported plot layer type")
    if set(raw) != expected:
        raise InputValidationError("plot layer fields differ")

    def numbers(name: str) -> tuple[float, ...]:
        item = raw[name]
        if not isinstance(item, list):
            raise InputValidationError("plot layer coordinates must be arrays")
        return tuple(cast(list[float], item))

    def strings(name: str) -> tuple[str, ...]:
        item = raw[name]
        if not isinstance(item, list):
            raise InputValidationError("plot layer categories must be arrays")
        return tuple(cast(list[str], item))

    layer_id = cast(str, raw["layer_id"])
    label = cast(str | None, raw["label"])
    role = cast(LayerRole, raw["role"])
    if layer_type == "line":
        return LineLayer(
            layer_id,
            numbers("x"),
            numbers("y"),
            label,
            role,
            cast(Literal["linear", "step"], raw["interpolation"]),
        )
    if layer_type == "point":
        return PointLayer(layer_id, numbers("x"), numbers("y"), label, role)
    if layer_type == "band":
        return BandLayer(
            layer_id,
            numbers("x"),
            numbers("lower"),
            numbers("upper"),
            label,
            role,
        )
    orientation = cast(Orientation, raw["orientation"])
    if layer_type == "bar":
        return BarLayer(
            layer_id,
            strings("categories"),
            numbers("values"),
            label,
            role,
            orientation,
        )
    return IntervalLayer(
        layer_id,
        strings("categories"),
        numbers("estimates"),
        numbers("lower"),
        numbers("upper"),
        label,
        role,
        orientation,
    )


def _annotation_from_dict(value: object) -> PlotAnnotation:
    if not isinstance(value, dict):
        raise InputValidationError("plot annotation must be an object")
    raw = cast(dict[str, object], value)
    annotation_type = raw.get("annotation_type")
    if annotation_type == "reference-line":
        expected = {"annotation_type", "axis", "value", "label"}
        if set(raw) != expected:
            raise InputValidationError("reference-line fields differ")
        return ReferenceLine(
            cast(Literal["x", "y"], raw["axis"]),
            cast(float, raw["value"]),
            cast(str | None, raw["label"]),
        )
    if annotation_type == "text":
        expected = {"annotation_type", "x", "y", "text"}
        if set(raw) != expected:
            raise InputValidationError("text annotation fields differ")
        return TextAnnotation(
            cast(float, raw["x"]),
            cast(float, raw["y"]),
            cast(str, raw["text"]),
        )
    raise InputValidationError("unsupported plot annotation type")


def _metadata_from_dict(value: object) -> PlotMetadata:
    raw = _exact_dict(
        value,
        fields={"key", "value"},
        role="plot metadata",
    )
    return PlotMetadata(cast(str, raw["key"]), cast(str, raw["value"]))


__all__ = [
    "AxisSpec",
    "BandLayer",
    "BarLayer",
    "IntervalLayer",
    "LineLayer",
    "PlotMetadata",
    "PlotSpec",
    "PointLayer",
    "ReferenceLine",
    "TextAnnotation",
]
