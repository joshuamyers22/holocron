"""Dependency-free accessible SVG rendering for :class:`PlotSpec`."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from numbers import Integral
from typing import Literal, cast
from xml.etree import ElementTree as ET

from holocron.exceptions import InputValidationError
from holocron.graphics.specification import (
    AxisScale,
    AxisSpec,
    BandLayer,
    BarLayer,
    IntervalLayer,
    LineLayer,
    PlotLayer,
    PlotSpec,
    PointLayer,
    ReferenceLine,
    TextAnnotation,
)

_SVG = "http://www.w3.org/2000/svg"
_COLORS = {
    "estimate": "#0072B2",
    "interval": "#56B4E9",
    "observed": "#009E73",
    "reference": "#4D4D4D",
    "comparison": "#D55E00",
    "diagnostic": "#CC79A7",
}


@dataclass(frozen=True, slots=True)
class _Frame:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


def _element(
    parent: ET.Element,
    tag: str,
    attributes: dict[str, str] | None = None,
    text: str | None = None,
) -> ET.Element:
    child = ET.SubElement(parent, f"{{{_SVG}}}{tag}", attributes or {})
    child.text = text
    return child


def _number(value: float) -> str:
    return f"{value:.6g}"


def _coordinate(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _transform(value: float, scale: AxisScale) -> float:
    if scale == "log":
        return math.log(value)
    if scale == "logit":
        return math.log(value / (1.0 - value))
    return value


def _axis_values(spec: PlotSpec, axis: Literal["x", "y"]) -> tuple[float, ...]:
    values: list[float] = []
    for layer in spec.layers:
        if isinstance(layer, (LineLayer, PointLayer)):
            values.extend(layer.x if axis == "x" else layer.y)
        elif isinstance(layer, BandLayer):
            values.extend(layer.x if axis == "x" else (*layer.lower, *layer.upper))
        elif isinstance(layer, BarLayer):
            value_axis = "y" if layer.orientation == "vertical" else "x"
            if axis == value_axis:
                values.extend(layer.values)
                axis_spec = spec.y_axis if axis == "y" else spec.x_axis
                if axis_spec.scale in {"linear", "probability"}:
                    values.append(0.0)
        else:
            value_axis = "y" if layer.orientation == "vertical" else "x"
            if axis == value_axis:
                values.extend((*layer.lower, *layer.estimates, *layer.upper))
    for annotation in spec.annotations:
        if isinstance(annotation, ReferenceLine) and annotation.axis == axis:
            values.append(annotation.value)
        elif isinstance(annotation, TextAnnotation):
            values.append(annotation.x if axis == "x" else annotation.y)
    return tuple(values)


def _domain(axis: AxisSpec, values: tuple[float, ...]) -> tuple[float, float]:
    if axis.limits is not None:
        return axis.limits
    if not values:
        return (0.0, 1.0)
    if axis.scale == "probability":
        return (0.0, 1.0)
    low = min(values)
    high = max(values)
    if low == high:
        delta = max(abs(low) * 0.1, 0.5)
        if axis.scale == "log":
            return (low / 2.0, high * 2.0)
        if axis.scale == "logit":
            return (max(1e-6, low - 0.05), min(1.0 - 1e-6, high + 0.05))
        return (low - delta, high + delta)
    transformed_low = _transform(low, axis.scale)
    transformed_high = _transform(high, axis.scale)
    padding = 0.04 * (transformed_high - transformed_low)
    if axis.scale == "log":
        return (
            math.exp(transformed_low - padding),
            math.exp(transformed_high + padding),
        )
    if axis.scale == "logit":

        def inverse(item: float) -> float:
            return 1.0 / (1.0 + math.exp(-item))

        return (inverse(transformed_low - padding), inverse(transformed_high + padding))
    return (low - padding, high + padding)


def _projector(
    axis: AxisSpec,
    domain: tuple[float, float],
    start: float,
    end: float,
) -> Callable[[float], float]:
    low = _transform(domain[0], axis.scale)
    high = _transform(domain[1], axis.scale)

    def project(value: float) -> float:
        normalized = (_transform(value, axis.scale) - low) / (high - low)
        return start + normalized * (end - start)

    return project


def _ticks(axis: AxisSpec, domain: tuple[float, float]) -> tuple[float, ...]:
    if axis.ticks:
        return tuple(value for value in axis.ticks if domain[0] <= value <= domain[1])
    if axis.scale == "probability":
        return tuple(
            value
            for value in (0.0, 0.25, 0.5, 0.75, 1.0)
            if domain[0] <= value <= domain[1]
        )
    low = _transform(domain[0], axis.scale)
    high = _transform(domain[1], axis.scale)
    transformed = tuple(low + index * (high - low) / 4.0 for index in range(5))
    if axis.scale == "log":
        return tuple(math.exp(value) for value in transformed)
    if axis.scale == "logit":
        return tuple(1.0 / (1.0 + math.exp(-value)) for value in transformed)
    return transformed


def _tick_label(axis: AxisSpec, value: float, index: int) -> str:
    if axis.tick_labels and index < len(axis.tick_labels):
        return axis.tick_labels[index]
    if axis.scale == "probability":
        return f"{100.0 * value:g}%"
    return _number(value)


def _categories(spec: PlotSpec) -> tuple[str, ...]:
    ordered: list[str] = []
    for layer in spec.layers:
        if isinstance(layer, (BarLayer, IntervalLayer)):
            for category in layer.categories:
                if category not in ordered:
                    ordered.append(category)
    return tuple(ordered)


def _path_points(
    x: tuple[float, ...],
    y: tuple[float, ...],
    project_x: Callable[[float], float],
    project_y: Callable[[float], float],
    *,
    step: bool,
) -> str:
    points: list[tuple[float, float]] = []
    for index, (x_value, y_value) in enumerate(zip(x, y, strict=True)):
        projected = (project_x(x_value), project_y(y_value))
        if step and index:
            points.append((projected[0], points[-1][1]))
        points.append(projected)
    return " ".join(
        f"{'M' if index == 0 else 'L'} {_coordinate(px)} {_coordinate(py)}"
        for index, (px, py) in enumerate(points)
    )


def _layer_group(root: ET.Element, layer: PlotLayer) -> ET.Element:
    label = layer.label or layer.layer_id.replace("-", " ")
    return _element(
        root,
        "g",
        {
            "data-layer-id": layer.layer_id,
            "data-role": layer.role,
            "role": "group",
            "aria-label": label,
        },
    )


def _draw_numeric_layers(
    root: ET.Element,
    spec: PlotSpec,
    project_x: Callable[[float], float],
    project_y: Callable[[float], float],
) -> None:
    for layer in spec.layers:
        color = _COLORS[layer.role]
        group = _layer_group(root, layer)
        if isinstance(layer, BandLayer):
            upper = tuple(
                (project_x(x), project_y(y))
                for x, y in zip(layer.x, layer.upper, strict=True)
            )
            lower = tuple(
                (project_x(x), project_y(y))
                for x, y in reversed(tuple(zip(layer.x, layer.lower, strict=True)))
            )
            points = " ".join(
                f"{_coordinate(x)},{_coordinate(y)}" for x, y in (*upper, *lower)
            )
            _element(
                group,
                "polygon",
                {"points": points, "fill": color, "fill-opacity": "0.24"},
            )
        elif isinstance(layer, LineLayer):
            _element(
                group,
                "path",
                {
                    "d": _path_points(
                        layer.x,
                        layer.y,
                        project_x,
                        project_y,
                        step=layer.interpolation == "step",
                    ),
                    "fill": "none",
                    "stroke": color,
                    "stroke-width": "2.25",
                    "stroke-dasharray": "6 4" if layer.role == "reference" else "none",
                },
            )
        elif isinstance(layer, PointLayer):
            for x_value, y_value in zip(layer.x, layer.y, strict=True):
                _element(
                    group,
                    "circle",
                    {
                        "cx": _coordinate(project_x(x_value)),
                        "cy": _coordinate(project_y(y_value)),
                        "r": "4" if layer.role == "comparison" else "3.25",
                        "fill": color,
                        "stroke": "#FFFFFF",
                        "stroke-width": "0.8",
                    },
                )


def _draw_categorical_layers(
    root: ET.Element,
    spec: PlotSpec,
    frame: _Frame,
    categories: tuple[str, ...],
    project_value: Callable[[float], float],
    baseline_value: float,
) -> None:
    horizontal = spec.y_axis.scale == "categorical"
    category_span = frame.height if horizontal else frame.width
    band = category_span / len(categories)
    bar_layers = tuple(layer for layer in spec.layers if isinstance(layer, BarLayer))
    interval_layers = tuple(
        layer for layer in spec.layers if isinstance(layer, IntervalLayer)
    )
    for layer in spec.layers:
        color = _COLORS[layer.role]
        group = _layer_group(root, layer)
        if isinstance(layer, BarLayer):
            count = len(bar_layers)
            offset_index = bar_layers.index(layer)
            thickness = band * 0.72 / max(1, count)
            for category, value in zip(layer.categories, layer.values, strict=True):
                index = categories.index(category)
                center = (
                    frame.top + (index + 0.5) * band
                    if horizontal
                    else frame.left + (index + 0.5) * band
                )
                offset = (offset_index - (count - 1) / 2.0) * thickness
                baseline = project_value(baseline_value)
                endpoint = project_value(value)
                if horizontal:
                    attrs = {
                        "x": _coordinate(min(baseline, endpoint)),
                        "y": _coordinate(center + offset - thickness * 0.42),
                        "width": _coordinate(max(0.5, abs(endpoint - baseline))),
                        "height": _coordinate(thickness * 0.84),
                    }
                else:
                    attrs = {
                        "x": _coordinate(center + offset - thickness * 0.42),
                        "y": _coordinate(min(baseline, endpoint)),
                        "width": _coordinate(thickness * 0.84),
                        "height": _coordinate(max(0.5, abs(endpoint - baseline))),
                    }
                _element(
                    group, "rect", {**attrs, "fill": color, "fill-opacity": "0.82"}
                )
        elif isinstance(layer, IntervalLayer):
            count = len(interval_layers)
            offset_index = interval_layers.index(layer)
            offset = (offset_index - (count - 1) / 2.0) * min(10.0, band * 0.18)
            for category, estimate, low, high in zip(
                layer.categories,
                layer.estimates,
                layer.lower,
                layer.upper,
                strict=True,
            ):
                index = categories.index(category)
                center = (
                    frame.top + (index + 0.5) * band
                    if horizontal
                    else frame.left + (index + 0.5) * band
                ) + offset
                if horizontal:
                    x1, x2, point = (
                        project_value(low),
                        project_value(high),
                        project_value(estimate),
                    )
                    _element(
                        group,
                        "line",
                        {
                            "x1": _coordinate(x1),
                            "x2": _coordinate(x2),
                            "y1": _coordinate(center),
                            "y2": _coordinate(center),
                            "stroke": color,
                            "stroke-width": "2",
                        },
                    )
                    _element(
                        group,
                        "circle",
                        {
                            "cx": _coordinate(point),
                            "cy": _coordinate(center),
                            "r": "4",
                            "fill": color,
                        },
                    )
                else:
                    y1, y2, point = (
                        project_value(low),
                        project_value(high),
                        project_value(estimate),
                    )
                    _element(
                        group,
                        "line",
                        {
                            "x1": _coordinate(center),
                            "x2": _coordinate(center),
                            "y1": _coordinate(y1),
                            "y2": _coordinate(y2),
                            "stroke": color,
                            "stroke-width": "2",
                        },
                    )
                    _element(
                        group,
                        "circle",
                        {
                            "cx": _coordinate(center),
                            "cy": _coordinate(point),
                            "r": "4",
                            "fill": color,
                        },
                    )


def _draw_annotations(
    root: ET.Element,
    spec: PlotSpec,
    frame: _Frame,
    project_x: Callable[[float], float],
    project_y: Callable[[float], float],
) -> None:
    for annotation in spec.annotations:
        if isinstance(annotation, ReferenceLine):
            if annotation.axis == "x":
                position = project_x(annotation.value)
                attrs = {
                    "x1": _coordinate(position),
                    "x2": _coordinate(position),
                    "y1": _coordinate(frame.top),
                    "y2": _coordinate(frame.bottom),
                }
            else:
                position = project_y(annotation.value)
                attrs = {
                    "x1": _coordinate(frame.left),
                    "x2": _coordinate(frame.right),
                    "y1": _coordinate(position),
                    "y2": _coordinate(position),
                }
            line = _element(
                root,
                "line",
                {
                    **attrs,
                    "stroke": _COLORS["reference"],
                    "stroke-width": "1.25",
                    "stroke-dasharray": "5 4",
                    "data-role": "reference",
                },
            )
            if annotation.label:
                _element(line, "title", text=annotation.label)
        else:
            _element(
                root,
                "text",
                {
                    "x": _coordinate(project_x(annotation.x) + 4.0),
                    "y": _coordinate(project_y(annotation.y) - 4.0),
                    "font-size": "11",
                    "fill": "#222222",
                },
                annotation.text,
            )


def _draw_legend(root: ET.Element, spec: PlotSpec, frame: _Frame) -> None:
    if not spec.show_legend:
        return
    labeled = {
        layer.layer_id: layer for layer in spec.layers if layer.label is not None
    }
    ordered = (
        *spec.legend_order,
        *(key for key in labeled if key not in spec.legend_order),
    )
    if not ordered:
        return
    group = _element(root, "g", {"role": "group", "aria-label": "Legend"})
    x = frame.right + 20.0
    y = frame.top + 4.0
    for index, layer_id in enumerate(ordered):
        layer = labeled[layer_id]
        row_y = y + index * 22.0
        _element(
            group,
            "line",
            {
                "x1": _coordinate(x),
                "x2": _coordinate(x + 18.0),
                "y1": _coordinate(row_y),
                "y2": _coordinate(row_y),
                "stroke": _COLORS[layer.role],
                "stroke-width": "4",
            },
        )
        _element(
            group,
            "text",
            {
                "x": _coordinate(x + 25.0),
                "y": _coordinate(row_y + 4.0),
                "font-size": "12",
                "fill": "#222222",
            },
            cast(str, layer.label),
        )


def render_svg(spec: PlotSpec, *, width: int = 800, height: int = 520) -> str:
    """Render a plot specification as deterministic, accessible inline SVG.

    The renderer owns a fixed semantic palette and emits no scripts, external
    resources, event handlers, or backend-specific state.
    """
    if not isinstance(cast(object, spec), PlotSpec):
        raise InputValidationError("spec must be a PlotSpec")
    for value, name in ((width, "width"), (height, "height")):
        if (
            isinstance(cast(object, value), bool)
            or not isinstance(cast(object, value), Integral)
            or not 320 <= value <= 4096
        ):
            raise InputValidationError(f"{name} must be an integer from 320 to 4096")

    ET.register_namespace("", _SVG)
    title_id = f"{spec.plot_id}-title"
    description_id = f"{spec.plot_id}-description"
    root = ET.Element(
        f"{{{_SVG}}}svg",
        {
            "width": str(width),
            "height": str(height),
            "viewBox": f"0 0 {width} {height}",
            "role": "img",
            "aria-labelledby": f"{title_id} {description_id}",
        },
    )
    _element(root, "title", {"id": title_id}, spec.title)
    _element(root, "desc", {"id": description_id}, spec.alt_text)
    _element(
        root,
        "metadata",
        text=f"holocron-plot-spec/v1 sha256:{spec.fingerprint}",
    )
    _element(root, "rect", {"width": "100%", "height": "100%", "fill": "#FFFFFF"})
    _element(
        root,
        "text",
        {
            "x": "70",
            "y": "28",
            "font-size": "18",
            "font-weight": "600",
            "fill": "#111111",
        },
        spec.title,
    )
    top = 62.0 if spec.subtitle else 48.0
    if spec.subtitle:
        _element(
            root,
            "text",
            {"x": "70", "y": "48", "font-size": "12", "fill": "#555555"},
            spec.subtitle,
        )
    legend_width = (
        190.0
        if spec.show_legend and any(layer.label for layer in spec.layers)
        else 20.0
    )
    bottom = float(height) - (52.0 if spec.caption else 42.0)
    category_labels = _categories(spec)
    category_margin = min(
        180.0, max((len(item) for item in category_labels), default=0) * 7.0
    )
    left = (
        max(70.0, category_margin + 24.0)
        if spec.y_axis.scale == "categorical"
        else 70.0
    )
    frame = _Frame(left, top, float(width) - legend_width, bottom)
    if frame.width < 80.0 or frame.height < 80.0:
        raise InputValidationError("render dimensions leave no usable plotting area")

    x_domain = (
        None
        if spec.x_axis.scale == "categorical"
        else _domain(spec.x_axis, _axis_values(spec, "x"))
    )
    y_domain = (
        None
        if spec.y_axis.scale == "categorical"
        else _domain(spec.y_axis, _axis_values(spec, "y"))
    )
    project_x = (
        None
        if x_domain is None
        else _projector(spec.x_axis, x_domain, frame.left, frame.right)
    )
    project_y = (
        None
        if y_domain is None
        else _projector(spec.y_axis, y_domain, frame.bottom, frame.top)
    )

    axes = _element(root, "g", {"aria-hidden": "true"})
    _element(
        axes,
        "line",
        {
            "x1": _coordinate(frame.left),
            "x2": _coordinate(frame.right),
            "y1": _coordinate(frame.bottom),
            "y2": _coordinate(frame.bottom),
            "stroke": "#333333",
        },
    )
    _element(
        axes,
        "line",
        {
            "x1": _coordinate(frame.left),
            "x2": _coordinate(frame.left),
            "y1": _coordinate(frame.top),
            "y2": _coordinate(frame.bottom),
            "stroke": "#333333",
        },
    )

    if spec.x_axis.scale == "categorical":
        band = frame.width / len(category_labels)
        for index, label in enumerate(category_labels):
            x = frame.left + (index + 0.5) * band
            _element(
                axes,
                "text",
                {
                    "x": _coordinate(x),
                    "y": _coordinate(frame.bottom + 18.0),
                    "text-anchor": "middle",
                    "font-size": "11",
                    "fill": "#333333",
                },
                label,
            )
    else:
        assert x_domain is not None and project_x is not None
        for index, value in enumerate(_ticks(spec.x_axis, x_domain)):
            x = project_x(value)
            _element(
                axes,
                "line",
                {
                    "x1": _coordinate(x),
                    "x2": _coordinate(x),
                    "y1": _coordinate(frame.top),
                    "y2": _coordinate(frame.bottom),
                    "stroke": "#E6E6E6",
                },
            )
            _element(
                axes,
                "text",
                {
                    "x": _coordinate(x),
                    "y": _coordinate(frame.bottom + 18.0),
                    "text-anchor": "middle",
                    "font-size": "11",
                    "fill": "#333333",
                },
                _tick_label(spec.x_axis, value, index),
            )
    if spec.y_axis.scale == "categorical":
        band = frame.height / len(category_labels)
        for index, label in enumerate(category_labels):
            y = frame.top + (index + 0.5) * band
            _element(
                axes,
                "text",
                {
                    "x": _coordinate(frame.left - 8.0),
                    "y": _coordinate(y + 4.0),
                    "text-anchor": "end",
                    "font-size": "11",
                    "fill": "#333333",
                },
                label,
            )
    else:
        assert y_domain is not None and project_y is not None
        for index, value in enumerate(_ticks(spec.y_axis, y_domain)):
            y = project_y(value)
            _element(
                axes,
                "line",
                {
                    "x1": _coordinate(frame.left),
                    "x2": _coordinate(frame.right),
                    "y1": _coordinate(y),
                    "y2": _coordinate(y),
                    "stroke": "#E6E6E6",
                },
            )
            _element(
                axes,
                "text",
                {
                    "x": _coordinate(frame.left - 8.0),
                    "y": _coordinate(y + 4.0),
                    "text-anchor": "end",
                    "font-size": "11",
                    "fill": "#333333",
                },
                _tick_label(spec.y_axis, value, index),
            )

    _element(
        axes,
        "text",
        {
            "x": _coordinate((frame.left + frame.right) / 2.0),
            "y": _coordinate(frame.bottom + 36.0),
            "text-anchor": "middle",
            "font-size": "12",
            "fill": "#111111",
        },
        spec.x_axis.label,
    )
    y_label = _element(
        axes,
        "text",
        {
            "x": _coordinate(-(frame.top + frame.bottom) / 2.0),
            "y": "16",
            "text-anchor": "middle",
            "font-size": "12",
            "fill": "#111111",
            "transform": "rotate(-90)",
        },
        spec.y_axis.label,
    )
    del y_label

    data = _element(root, "g", {"role": "group", "aria-label": "Plot data"})
    if spec.x_axis.scale == "categorical" or spec.y_axis.scale == "categorical":
        value_projector = project_y if spec.x_axis.scale == "categorical" else project_x
        assert value_projector is not None
        value_domain = y_domain if spec.x_axis.scale == "categorical" else x_domain
        value_axis = spec.y_axis if spec.x_axis.scale == "categorical" else spec.x_axis
        assert value_domain is not None
        baseline_value = (
            min(max(0.0, value_domain[0]), value_domain[1])
            if value_axis.scale in {"linear", "probability"}
            else value_domain[0]
        )
        _draw_categorical_layers(
            data,
            spec,
            frame,
            category_labels,
            value_projector,
            baseline_value,
        )
    else:
        assert project_x is not None and project_y is not None
        _draw_numeric_layers(data, spec, project_x, project_y)
        _draw_annotations(data, spec, frame, project_x, project_y)
    if spec.x_axis.scale == "categorical" or spec.y_axis.scale == "categorical":
        if project_x is not None and project_y is None:

            def dummy_y(_value: float) -> float:
                return frame.top

            _draw_annotations(data, spec, frame, project_x, dummy_y)
        elif project_y is not None and project_x is None:

            def dummy_x(_value: float) -> float:
                return frame.left

            _draw_annotations(data, spec, frame, dummy_x, project_y)
    _draw_legend(root, spec, frame)
    if spec.caption:
        _element(
            root,
            "text",
            {
                "x": "70",
                "y": _coordinate(float(height) - 12.0),
                "font-size": "11",
                "fill": "#555555",
            },
            spec.caption,
        )
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)
