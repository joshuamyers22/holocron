from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from holocron.exceptions import InputValidationError
from holocron.graphics import (
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
from reference.contracts import validate_document

ROOT = Path(__file__).resolve().parents[1]
PLOT_SCHEMA = ROOT / "schemas/plot-spec.schema.json"


class PlotSpecificationTests(unittest.TestCase):
    def test_numeric_plot_round_trips_and_validates_against_schema(self) -> None:
        plot = PlotSpec(
            plot_id="calibration-apparent",
            kind="calibration",
            title="Apparent calibration",
            subtitle="Fixed realized design",
            caption="Intervals are illustrative source data.",
            alt_text=(
                "Predicted probability versus observed probability with an estimate "
                "line, point observations, interval band, and ideal diagonal."
            ),
            x_axis=AxisSpec(
                "Predicted probability",
                scale="probability",
                limits=(0.0, 1.0),
                ticks=(0.0, 0.5, 1.0),
                tick_labels=("0%", "50%", "100%"),
            ),
            y_axis=AxisSpec(
                "Observed probability",
                scale="probability",
                limits=(0.0, 1.0),
            ),
            layers=(
                BandLayer(
                    "uncertainty",
                    (0.1, 0.5, 0.9),
                    (0.05, 0.4, 0.8),
                    (0.2, 0.6, 0.95),
                    label="Interval",
                ),
                LineLayer(
                    "estimate",
                    (0.1, 0.5, 0.9),
                    (0.12, 0.48, 0.87),
                    label="Estimate",
                ),
                PointLayer(
                    "observed",
                    (0.1, 0.5, 0.9),
                    (0.15, 0.45, 0.9),
                    label="Grouped observations",
                ),
            ),
            annotations=(
                ReferenceLine("y", 0.5, "Half observed"),
                TextAnnotation(0.5, 0.48, "Middle estimate"),
            ),
            metadata=(
                PlotMetadata("model_family", "binary-logistic"),
                PlotMetadata("source", "apparent calibration"),
            ),
            legend_order=("estimate", "observed", "uncertainty"),
        )

        restored = PlotSpec.from_json(plot.to_json())

        self.assertEqual(restored, plot)
        self.assertEqual(restored.fingerprint, plot.fingerprint)
        self.assertEqual(restored.to_json(), plot.to_json())
        validate_document(plot.to_dict(), PLOT_SCHEMA)

    def test_categorical_layers_encode_bars_and_intervals_without_a_backend(
        self,
    ) -> None:
        intervals = PlotSpec(
            plot_id="contrast-intervals",
            kind="contrast",
            title="Contrasts",
            alt_text="Two named contrasts with point estimates and intervals.",
            x_axis=AxisSpec("Estimate", limits=(-1.0, 2.0)),
            y_axis=AxisSpec("Contrast", scale="categorical"),
            layers=(
                IntervalLayer(
                    "contrasts",
                    ("Treatment A", "Treatment B"),
                    (0.2, 0.8),
                    (-0.1, 0.4),
                    (0.5, 1.2),
                    label="95% interval",
                ),
            ),
            annotations=(ReferenceLine("x", 0.0, "No difference"),),
        )
        bars = PlotSpec(
            plot_id="anova-bars",
            kind="anova",
            title="Term statistics",
            alt_text="Two vertical bars showing term statistics.",
            x_axis=AxisSpec("Term", scale="categorical"),
            y_axis=AxisSpec("Statistic", scale="log"),
            layers=(
                BarLayer(
                    "terms",
                    ("Age", "Treatment"),
                    (2.0, 8.0),
                    label="Wald statistic",
                ),
            ),
        )

        self.assertEqual(PlotSpec.from_dict(intervals.to_dict()), intervals)
        self.assertEqual(PlotSpec.from_dict(bars.to_dict()), bars)
        validate_document(intervals.to_dict(), PLOT_SCHEMA)
        validate_document(bars.to_dict(), PLOT_SCHEMA)

    def test_axis_layer_and_accessibility_invariants_fail_closed(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "alt_text"):
            PlotSpec(
                "missing-alt",
                "custom",
                "Title",
                "",
                AxisSpec("x"),
                AxisSpec("y"),
                (LineLayer("line", (0.0,), (1.0,)),),
            )
        with self.assertRaisesRegex(InputValidationError, "coordinate lengths"):
            LineLayer("line", (0.0, 1.0), (1.0,))
        with self.assertRaisesRegex(InputValidationError, "lower values"):
            BandLayer("band", (0.0,), (0.8,), (0.2,))
        with self.assertRaisesRegex(InputValidationError, "between lower"):
            IntervalLayer("interval", ("A",), (2.0,), (0.0,), (1.0,))
        with self.assertRaisesRegex(InputValidationError, "positive"):
            PlotSpec(
                "invalid-log",
                "custom",
                "Invalid log",
                "A line with a nonpositive log-axis value.",
                AxisSpec("x"),
                AxisSpec("y", scale="log"),
                (LineLayer("line", (0.0,), (0.0,)),),
            )
        with self.assertRaisesRegex(InputValidationError, "categorical layer"):
            PlotSpec(
                "bad-orientation",
                "anova",
                "Bad orientation",
                "A vertical bar with the categorical axis in the wrong position.",
                AxisSpec("Value"),
                AxisSpec("Term", scale="categorical"),
                (BarLayer("bar", ("A",), (1.0,)),),
            )
        with self.assertRaisesRegex(InputValidationError, "unique"):
            PlotSpec(
                "duplicate-layer",
                "custom",
                "Duplicate layers",
                "Two layers with the same identifier.",
                AxisSpec("x"),
                AxisSpec("y"),
                (
                    LineLayer("same", (0.0,), (1.0,)),
                    PointLayer("same", (0.0,), (1.0,)),
                ),
            )
        with self.assertRaisesRegex(InputValidationError, "finite"):
            PointLayer("nonfinite", (0.0,), (math.inf,))

    def test_readers_reject_unknown_duplicate_and_wrong_version_documents(self) -> None:
        plot = PlotSpec(
            "reader-check",
            "diagnostic",
            "Reader check",
            "One diagnostic point.",
            AxisSpec("x"),
            AxisSpec("y"),
            (PointLayer("point", (0.0,), (1.0,)),),
        )
        unknown = plot.to_dict()
        unknown["unknown"] = True
        with self.assertRaisesRegex(InputValidationError, "fields differ"):
            PlotSpec.from_dict(unknown)

        wrong_version = plot.to_dict()
        wrong_version["schema_version"] = "holocron-plot-spec/v2"
        with self.assertRaisesRegex(InputValidationError, "unsupported"):
            PlotSpec.from_dict(wrong_version)

        duplicate = plot.to_json().replace(
            '"plot_id":"reader-check"',
            '"plot_id":"reader-check","plot_id":"duplicate"',
        )
        with self.assertRaisesRegex(InputValidationError, "invalid plot"):
            PlotSpec.from_json(duplicate)

        malformed = json.loads(plot.to_json())
        malformed["layers"][0]["unexpected"] = 1
        with self.assertRaisesRegex(InputValidationError, "layer fields differ"):
            PlotSpec.from_dict(malformed)

    def test_plot_resource_limits_are_enforced_before_rendering(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "100000-point"):
            PointLayer(
                "too-many-points",
                tuple(float(index) for index in range(100_001)),
                (0.0,),
            )
        with self.assertRaisesRegex(InputValidationError, "1-256"):
            PlotSpec(
                "too-many-layers",
                "custom",
                "Too many layers",
                "A plot exceeding the layer limit.",
                AxisSpec("x"),
                AxisSpec("y"),
                tuple(
                    PointLayer(f"point-{index}", (0.0,), (0.0,)) for index in range(257)
                ),
            )
        with self.assertRaisesRegex(InputValidationError, "annotations"):
            PlotSpec(
                "too-many-annotations",
                "custom",
                "Too many annotations",
                "A plot exceeding the annotation limit.",
                AxisSpec("x"),
                AxisSpec("y"),
                (PointLayer("point", (0.0,), (0.0,)),),
                annotations=tuple(ReferenceLine("x", 0.0) for _ in range(257)),
            )


if __name__ == "__main__":
    unittest.main()
