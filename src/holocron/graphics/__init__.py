"""Plot specifications, typed result adapters, and accessible SVG rendering."""

from holocron.graphics.adapters import (
    anova_plot_spec,
    calibration_plot_spec,
    contrast_plot_spec,
    diagnostic_plot_spec,
    effect_plot_spec,
    survival_plot_spec,
    validation_plot_spec,
)
from holocron.graphics.specification import (
    AxisSpec,
    BandLayer,
    BarLayer,
    IntervalLayer,
    LineLayer,
    PlotMetadata,
    PlotSpec,
    PointLayer,
    ReferenceLine,
    TextAnnotation,
)
from holocron.graphics.svg import render_svg

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
    "anova_plot_spec",
    "calibration_plot_spec",
    "contrast_plot_spec",
    "diagnostic_plot_spec",
    "effect_plot_spec",
    "render_svg",
    "survival_plot_spec",
    "validation_plot_spec",
]
