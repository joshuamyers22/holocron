from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

from tools.check_svg_snapshots import check_snapshots, rendered_snapshots
from tools.svg_assurance import audit_svg_accessibility, contrast_ratio

SVG = "{http://www.w3.org/2000/svg}"


class SvgAccessibilityTests(unittest.TestCase):
    def test_all_supported_renderer_fixtures_pass_the_structural_audit(self) -> None:
        snapshots = rendered_snapshots()

        self.assertEqual(
            set(snapshots),
            {
                "nomogram.svg",
                "plot-categorical-horizontal.svg",
                "plot-categorical-vertical.svg",
                "plot-numeric.svg",
                "plot-transformed.svg",
            },
        )
        for name, svg in snapshots.items():
            with self.subTest(name=name):
                expected_kind = "nomogram" if name == "nomogram.svg" else "plot"
                report = audit_svg_accessibility(svg, expected_kind=expected_kind)
                self.assertTrue(report.passed, report.findings)
                self.assertIsNotNone(report.title)
                self.assertIsNotNone(report.description)
                self.assertTrue(report.group_labels)

    def test_audit_rejects_accessible_name_active_content_and_contrast_regressions(
        self,
    ) -> None:
        original = rendered_snapshots()["plot-numeric.svg"]
        mutations = {
            "missing-focus": (
                original.replace(' focusable="false"', "", 1),
                "focus",
            ),
            "dangling-name": (
                original.replace(
                    "assurance-numeric-description",
                    "unknown-description",
                    1,
                ),
                "accessible-name",
            ),
            "script": (
                original.replace("</svg>", "<script>alert(1)</script></svg>"),
                "active-content",
            ),
            "event-handler": (
                original.replace("<svg ", '<svg onclick="alert(1)" ', 1),
                "event-handler",
            ),
            "unlabelled-group": (
                original.replace(
                    'role="group" aria-label="Plot data"',
                    'role="group"',
                    1,
                ),
                "unlabelled-group",
            ),
            "low-text-contrast": (
                original.replace('fill="#111111"', 'fill="#AAAAAA"', 1),
                "text-contrast",
            ),
        }
        for name, (svg, expected_code) in mutations.items():
            with self.subTest(name=name):
                codes = {
                    finding.code for finding in audit_svg_accessibility(svg).findings
                }
                self.assertIn(expected_code, codes)

    def test_palette_and_non_color_cues_remain_reviewable(self) -> None:
        svg = rendered_snapshots()["plot-numeric.svg"]
        root = ET.fromstring(svg)
        layers = {
            group.attrib["data-layer-id"]: group
            for group in root.iter(f"{SVG}g")
            if "data-layer-id" in group.attrib
        }

        estimate = layers["estimate"].find(f"{SVG}path")
        diagnostic = layers["diagnostic-step"].find(f"{SVG}path")
        band = layers["confidence-band"].find(f"{SVG}polygon")
        assert estimate is not None and diagnostic is not None and band is not None
        self.assertEqual(estimate.attrib["stroke-dasharray"], "none")
        self.assertNotEqual(
            estimate.attrib["stroke-dasharray"],
            diagnostic.attrib["stroke-dasharray"],
        )
        self.assertGreaterEqual(contrast_ratio(estimate.attrib["stroke"]), 3.0)
        self.assertGreaterEqual(contrast_ratio(band.attrib["stroke"]), 3.0)


class SvgVisualRegressionTests(unittest.TestCase):
    def test_committed_golden_svgs_match_canonical_output(self) -> None:
        self.assertEqual(check_snapshots(), ())


if __name__ == "__main__":
    unittest.main()
