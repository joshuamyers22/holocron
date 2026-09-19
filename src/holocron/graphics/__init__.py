"""Plot and nomogram geometry, typed adapters, and accessible SVG rendering."""

from holocron.graphics.adapters import (
    anova_plot_spec,
    calibration_plot_spec,
    contrast_plot_spec,
    diagnostic_plot_spec,
    effect_plot_spec,
    survival_plot_spec,
    validation_plot_spec,
)
from holocron.graphics.nomogram import (
    NomogramAxis,
    NomogramGeometry,
    NomogramOutcomeAxis,
    NomogramOutcomeTick,
    NomogramTick,
    build_nomogram,
    render_nomogram_svg,
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
    "NomogramAxis",
    "NomogramGeometry",
    "NomogramOutcomeAxis",
    "NomogramOutcomeTick",
    "NomogramTick",
    "PlotMetadata",
    "PlotSpec",
    "PointLayer",
    "ReferenceLine",
    "TextAnnotation",
    "anova_plot_spec",
    "build_nomogram",
    "calibration_plot_spec",
    "contrast_plot_spec",
    "diagnostic_plot_spec",
    "effect_plot_spec",
    "render_svg",
    "render_nomogram_svg",
    "survival_plot_spec",
    "validation_plot_spec",
]
