"""Check human-reviewable golden SVGs for Holocron's supported renderers."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Literal

from holocron.design import DataDistribution, DesignSpec
from holocron.graphics import (
    AxisSpec,
    BandLayer,
    BarLayer,
    IntervalLayer,
    LineLayer,
    PlotSpec,
    PointLayer,
    ReferenceLine,
    TextAnnotation,
    build_nomogram,
    render_nomogram_svg,
    render_svg,
)
from holocron.models import fit_ols
from tools.svg_assurance import require_accessible_svg

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIRECTORY = ROOT / "tests" / "snapshots" / "svg"


def _numeric_plot() -> PlotSpec:
    x = (0.0, 1.0, 2.0, 3.0)
    return PlotSpec(
        "assurance-numeric",
        "custom",
        "Numeric renderer assurance",
        "Estimate and observed series with a confidence band and target reference.",
        AxisSpec("Follow-up", unit="months"),
        AxisSpec("Probability", scale="probability"),
        (
            BandLayer(
                "confidence-band",
                x,
                (0.12, 0.24, 0.39, 0.52),
                (0.28, 0.46, 0.63, 0.78),
                label="95% interval",
            ),
            LineLayer(
                "estimate",
                x,
                (0.20, 0.35, 0.52, 0.66),
                label="Estimate",
            ),
            LineLayer(
                "diagnostic-step",
                x,
                (0.16, 0.31, 0.48, 0.61),
                label="Diagnostic step",
                role="diagnostic",
                interpolation="step",
            ),
            PointLayer(
                "observed",
                x,
                (0.18, 0.38, 0.50, 0.69),
                label="Observed",
            ),
            PointLayer(
                "comparison",
                (0.5, 1.5, 2.5),
                (0.26, 0.44, 0.59),
                label="Comparison",
                role="comparison",
            ),
        ),
        subtitle="All numeric layers and non-color line cues",
        caption="Golden fixture: numeric layers, probability axis, and annotations.",
        annotations=(
            ReferenceLine("y", 0.5, "Decision threshold"),
            TextAnnotation(2.0, 0.52, "estimate"),
        ),
        legend_order=(
            "estimate",
            "observed",
            "comparison",
            "diagnostic-step",
            "confidence-band",
        ),
    )


def _transformed_plot() -> PlotSpec:
    return PlotSpec(
        "assurance-transformed",
        "custom",
        "Transformed-axis assurance",
        "A diagnostic series rendered on logit and logarithmic axes.",
        AxisSpec("Probability", scale="logit", limits=(0.05, 0.95)),
        AxisSpec("Relative measure", scale="log", limits=(0.1, 10.0)),
        (
            LineLayer(
                "transformed-line",
                (0.1, 0.3, 0.6, 0.9),
                (0.2, 0.7, 2.0, 7.0),
                label="Diagnostic",
                role="diagnostic",
            ),
        ),
        caption="Golden fixture: logit x-axis and log y-axis.",
    )


def _categorical_plot(*, orientation: Literal["vertical", "horizontal"]) -> PlotSpec:
    categories = ("Control", "Treatment A", "Treatment B")
    if orientation == "horizontal":
        x_axis = AxisSpec("Effect", limits=(-0.5, 2.5))
        y_axis = AxisSpec("Group", scale="categorical")
    else:
        x_axis = AxisSpec("Group", scale="categorical")
        y_axis = AxisSpec("Effect", limits=(-0.5, 2.5))
    return PlotSpec(
        f"assurance-categorical-{orientation}",
        "custom",
        f"Categorical {orientation} assurance",
        f"Bars and intervals rendered in the {orientation} orientation.",
        x_axis,
        y_axis,
        (
            BarLayer(
                "bars",
                categories,
                (0.2, 1.0, 1.7),
                label="Estimate",
                orientation=orientation,
            ),
            IntervalLayer(
                "intervals",
                categories,
                (0.2, 1.0, 1.7),
                (-0.1, 0.6, 1.2),
                (0.5, 1.4, 2.2),
                label="Comparison interval",
                orientation=orientation,
            ),
        ),
        caption=f"Golden fixture: {orientation} categorical layers.",
        annotations=(ReferenceLine("x" if orientation == "horizontal" else "y", 0.0),),
    )


def _nomogram_svg() -> str:
    dose = tuple(float(index) for index in range(8))
    group = tuple("A" if index % 2 == 0 else "B" for index in range(8))
    response = tuple(
        1.0 + value + (1.0 if level == "B" else 0.0)
        for value, level in zip(dose, group, strict=True)
    )
    design = DesignSpec.from_formula('y ~ dose + catg(group, ["A", "B"])')
    distribution = DataDistribution.from_data(
        {"dose": dose, "group": group},
        levels={"group": ("A", "B")},
        labels={"dose": "Dose level", "group": "Treatment group"},
        units={"dose": "mg"},
    )
    model = fit_ols(response, design.transform({"dose": dose, "group": group}))
    geometry = build_nomogram(
        model,
        design,
        distribution,
        title="Nomogram renderer assurance",
    )
    return render_nomogram_svg(geometry)


def rendered_snapshots() -> dict[str, str]:
    """Return the complete deterministic SVG snapshot corpus."""

    return {
        "nomogram.svg": _nomogram_svg(),
        "plot-categorical-horizontal.svg": render_svg(
            _categorical_plot(orientation="horizontal")
        ),
        "plot-categorical-vertical.svg": render_svg(
            _categorical_plot(orientation="vertical")
        ),
        "plot-numeric.svg": render_svg(_numeric_plot()),
        "plot-transformed.svg": render_svg(_transformed_plot()),
    }


def check_snapshots() -> tuple[str, ...]:
    """Return stable mismatch messages for the committed snapshot corpus."""

    generated = rendered_snapshots()
    errors: list[str] = []
    actual_names: set[str] = set()
    if SNAPSHOT_DIRECTORY.exists():
        actual_names = {path.name for path in SNAPSHOT_DIRECTORY.glob("*.svg")}
    expected_names = set(generated)
    for missing in sorted(expected_names - actual_names):
        errors.append(f"missing snapshot: {missing}")
    for extra in sorted(actual_names - expected_names):
        errors.append(f"unexpected snapshot: {extra}")
    for name, svg in sorted(generated.items()):
        kind = "nomogram" if name == "nomogram.svg" else "plot"
        try:
            require_accessible_svg(svg, expected_kind=kind)
        except ValueError as error:
            errors.append(f"{name}: {error}")
        path = SNAPSHOT_DIRECTORY / name
        if path.exists() and path.read_text(encoding="utf-8").rstrip("\n") != svg:
            digest = hashlib.sha256(svg.encode("utf-8")).hexdigest()[:12]
            errors.append(f"changed snapshot: {name} (generated sha256:{digest})")
    return tuple(errors)


def _update_snapshots() -> None:
    SNAPSHOT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    generated = rendered_snapshots()
    for path in SNAPSHOT_DIRECTORY.glob("*.svg"):
        if path.name not in generated:
            path.unlink()
    for name, svg in generated.items():
        (SNAPSHOT_DIRECTORY / name).write_text(f"{svg}\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="replace the committed golden SVGs with current deterministic output",
    )
    arguments = parser.parse_args()
    if arguments.update:
        _update_snapshots()
        print(f"updated {len(rendered_snapshots())} SVG snapshots")
        return 0
    errors = check_snapshots()
    if errors:
        for error in errors:
            print(error)
        print("run `python -m tools.check_svg_snapshots --update` after review")
        return 1
    print(f"checked {len(rendered_snapshots())} accessible SVG snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
