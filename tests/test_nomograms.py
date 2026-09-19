from __future__ import annotations

import json
import unittest
from itertools import product
from pathlib import Path
from xml.etree import ElementTree as ET

from holocron.design import DataDistribution, DesignSpec
from holocron.exceptions import InputValidationError, UnsupportedFeatureError
from holocron.graphics import (
    NomogramGeometry,
    build_nomogram,
    render_nomogram_svg,
)
from holocron.models import fit_lrm, fit_ols
from reference.contracts import validate_document

ROOT = Path(__file__).resolve().parents[1]
NOMOGRAM_SCHEMA = ROOT / "schemas/nomogram-geometry.schema.json"
SVG = "{http://www.w3.org/2000/svg}"


class NomogramGeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.x = tuple(float(index) for index in range(12))
        self.group = tuple("A" if index % 2 == 0 else "B" for index in range(12))
        self.response = tuple(
            1.0
            + 0.4 * value
            + 0.03 * value * value
            + (0.8 if group == "B" else 0.0)
            + 0.1 * ((index % 3) - 1)
            for index, (value, group) in enumerate(zip(self.x, self.group, strict=True))
        )
        self.spec = DesignSpec.from_formula('y ~ pol(x, 2) + catg(group, ["A", "B"])')
        self.distribution = DataDistribution.from_data(
            {"x": self.x, "group": self.group},
            levels={"group": ("A", "B")},
            labels={"x": "Dose < level", "group": "Treatment & group"},
            units={"x": "mg"},
        )
        self.model = fit_ols(
            self.response,
            self.spec.transform({"x": self.x, "group": self.group}),
        )

    def test_additive_geometry_reconstructs_model_predictions(self) -> None:
        geometry = build_nomogram(self.model, self.spec, self.distribution)

        self.assertEqual(geometry.model_family, "ols")
        self.assertEqual(tuple(axis.variable for axis in geometry.axes), ("x", "group"))
        self.assertAlmostEqual(
            max(axis.maximum_points for axis in geometry.axes),
            geometry.maximum_axis_points,
        )
        for x_tick, group_tick in product(
            geometry.axes[0].ticks,
            geometry.axes[1].ticks,
        ):
            design = self.spec.transform(
                {"x": (x_tick.value,), "group": (group_tick.value,)}
            )
            expected = self.model.predict(design)[0]
            total_points = x_tick.points + group_tick.points
            self.assertAlmostEqual(geometry.predict(total_points), expected, places=10)

    def test_geometry_round_trips_and_validates_against_schema(self) -> None:
        geometry = build_nomogram(self.model, self.spec, self.distribution)
        restored = NomogramGeometry.from_json(geometry.to_json())

        self.assertEqual(restored, geometry)
        self.assertEqual(restored.fingerprint, geometry.fingerprint)
        validate_document(geometry.to_dict(), NOMOGRAM_SCHEMA)

        unknown = geometry.to_dict()
        unknown["unknown"] = True
        with self.assertRaisesRegex(InputValidationError, "fields differ"):
            NomogramGeometry.from_dict(unknown)

        malformed = json.loads(geometry.to_json())
        malformed["outcome_axes"][0]["ticks"][0]["linear_predictor"] += 1.0
        with self.assertRaisesRegex(InputValidationError, "identity"):
            NomogramGeometry.from_dict(malformed)

        malformed_axis = json.loads(geometry.to_json())
        malformed_axis["axes"][0]["ticks"][1]["points"] += 0.123
        with self.assertRaisesRegex(InputValidationError, "points identity"):
            NomogramGeometry.from_dict(malformed_axis)

        duplicate = geometry.to_json().replace(
            '"model_family":"ols"',
            '"model_family":"ols","model_family":"ols"',
        )
        with self.assertRaisesRegex(InputValidationError, "invalid nomogram"):
            NomogramGeometry.from_json(duplicate)

    def test_binary_nomogram_uses_probability_outcomes(self) -> None:
        x = tuple(float(index % 10 - 5) for index in range(20))
        z = tuple(float((index * 3) % 7 - 3) for index in range(20))
        response = tuple(float(value) for value in (0, 0, 0, 1, 0, 1, 0, 1, 1, 1) * 2)
        spec = DesignSpec.from_formula("y ~ x + z")
        distribution = DataDistribution.from_data({"x": x, "z": z})
        model = fit_lrm(response, spec.transform({"x": x, "z": z}))

        geometry = build_nomogram(model, spec, distribution)

        self.assertEqual(geometry.model_family, "binary-logistic")
        outcome = geometry.outcome_axes[0]
        self.assertEqual(outcome.scale, "probability")
        self.assertTrue(all(0.0 < tick.value < 1.0 for tick in outcome.ticks))
        for tick in outcome.ticks:
            self.assertAlmostEqual(geometry.predict(tick.total_points), tick.value)

    def test_interactions_and_identity_mismatches_fail_closed(self) -> None:
        interaction_spec = DesignSpec.from_formula("y ~ x + z + ia(x, z)")
        x = tuple(float(index) for index in range(8))
        z = tuple(float(index % 3) for index in range(8))
        response = tuple(
            1.0 + x_value + z_value for x_value, z_value in zip(x, z, strict=True)
        )
        interaction_model = fit_ols(
            response,
            interaction_spec.transform({"x": x, "z": z}),
        )
        distribution = DataDistribution.from_data({"x": x, "z": z})

        with self.assertRaisesRegex(UnsupportedFeatureError, "interaction"):
            build_nomogram(interaction_model, interaction_spec, distribution)

        wrong_spec = DesignSpec.from_formula('y ~ x + catg(group, ["A", "B"])')
        with self.assertRaisesRegex(InputValidationError, "fingerprint"):
            build_nomogram(self.model, wrong_spec, self.distribution)


class NomogramRendererTests(unittest.TestCase):
    def _geometry(self) -> NomogramGeometry:
        x = tuple(float(index) for index in range(8))
        group = tuple("A" if index % 2 == 0 else "B" for index in range(8))
        response = tuple(
            1.0 + value + (1.0 if level == "B" else 0.0)
            for value, level in zip(x, group, strict=True)
        )
        spec = DesignSpec.from_formula('y ~ x + catg(group, ["A", "B"])')
        distribution = DataDistribution.from_data(
            {"x": x, "group": group},
            levels={"group": ("A", "B")},
            labels={"x": "Dose < level", "group": "Treatment & group"},
        )
        model = fit_ols(response, spec.transform({"x": x, "group": group}))
        return build_nomogram(model, spec, distribution, title="Nomogram < one")

    def test_svg_is_accessible_deterministic_and_escapes_labels(self) -> None:
        geometry = self._geometry()
        svg = render_nomogram_svg(geometry)
        root = ET.fromstring(svg)
        title = root.find(f"{SVG}title")
        description = root.find(f"{SVG}desc")
        assert title is not None and description is not None

        self.assertEqual(svg, render_nomogram_svg(geometry))
        self.assertEqual(root.attrib["role"], "img")
        self.assertEqual(title.text, geometry.title)
        self.assertEqual(description.text, geometry.alt_text)
        self.assertIn("Dose &lt; level", svg)
        self.assertIn("Treatment &amp; group", svg)
        self.assertIn("Total points", svg)
        self.assertNotIn("<script", svg.lower())

    def test_svg_dimensions_are_bounded_and_must_fit_geometry(self) -> None:
        geometry = self._geometry()
        with self.assertRaisesRegex(InputValidationError, "width"):
            render_nomogram_svg(geometry, width=400)
        with self.assertRaisesRegex(InputValidationError, "height"):
            render_nomogram_svg(geometry, height=320)


if __name__ == "__main__":
    unittest.main()
