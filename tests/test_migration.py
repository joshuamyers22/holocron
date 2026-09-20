from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from holocron.exceptions import InputValidationError
from holocron.migration import (
    HolocronDeprecationWarning,
    MigrationPlan,
    deprecation_notices,
    deprecation_policy,
    lookup_rms_capability,
    migration_catalog,
    plan_rms_migration,
)
from reference.contracts import JsonValue, validate_document
from tools.check_migration_policy import validate_notice
from tools.generate_migration_catalog import OUTPUT, render
from tools.plan_rms_migration import render_markdown

ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA = ROOT / "schemas/migration-plan.schema.json"


class MigrationTests(unittest.TestCase):
    def test_installed_catalog_covers_every_reviewed_disposition(self) -> None:
        entries = migration_catalog()

        self.assertEqual(len(entries), 281)
        self.assertEqual(len({entry.identifier for entry in entries}), 281)
        self.assertEqual(
            Counter(entry.disposition for entry in entries),
            {"experimental": 50, "mapped": 125, "unsupported": 106},
        )
        self.assertEqual(OUTPUT.read_text(encoding="utf-8"), render())

    def test_exact_lookup_distinguishes_path_and_stop_boundary(self) -> None:
        ols = lookup_rms_capability("export:ols")
        unsupported = lookup_rms_capability("export:Newlabels")

        self.assertEqual(ols.disposition, "experimental")
        self.assertEqual(ols.python_entry_point, "holocron.models.fit_ols")
        self.assertEqual(unsupported.disposition, "unsupported")
        self.assertIsNone(unsupported.python_entry_point)
        with self.assertRaisesRegex(InputValidationError, "unknown rms capability"):
            lookup_rms_capability("export:not-a-real-name")

    def test_plan_retains_ambiguous_matches_unknowns_and_readiness(self) -> None:
        plan = plan_rms_migration(
            ("ols", "Gls", "Newlabels", "plot.contrast.rms", "not-a-symbol")
        )

        self.assertEqual(len(plan.matches), 5)
        self.assertEqual(
            tuple(
                match.entry.identifier
                for match in plan.matches
                if match.query == "plot.contrast.rms"
            ),
            ("export:plot.contrast.rms", "s3_method:plot.contrast.rms"),
        )
        self.assertEqual(
            plan.disposition_counts,
            {"implemented": 0, "experimental": 1, "mapped": 3, "unsupported": 1},
        )
        self.assertEqual(plan.unknown_symbols, ("not-a-symbol",))
        self.assertFalse(plan.ready)
        markdown = render_markdown(plan)
        self.assertIn("— stop boundary —", markdown)
        self.assertIn("No catalog match", markdown)

        ready = plan_rms_migration(("export:ols", "export:Gls"))
        self.assertTrue(ready.ready)

    def test_plan_round_trip_schema_and_tamper_rejection(self) -> None:
        plan = plan_rms_migration(("ols", "Newlabels"))
        restored = MigrationPlan.from_json(plan.to_json())

        self.assertEqual(restored, plan)
        validate_document(plan.to_dict(), PLAN_SCHEMA)
        tampered = json.loads(plan.to_json())
        tampered["summary"]["ready"] = True
        with self.assertRaisesRegex(InputValidationError, "summary"):
            MigrationPlan.from_dict(tampered)
        with self.assertRaisesRegex(InputValidationError, "unique"):
            plan_rms_migration(("ols", "ols"))
        with self.assertRaisesRegex(InputValidationError, "1-1000"):
            plan_rms_migration(())

    def test_deprecation_policy_is_explicit_even_with_empty_registry(self) -> None:
        policy = deprecation_policy()

        self.assertEqual(policy.minimum_minor_releases, 2)
        self.assertEqual(policy.minimum_days, 90)
        self.assertTrue(policy.runtime_warning_required)
        self.assertTrue(policy.changelog_required)
        self.assertTrue(policy.migration_replacement_required)
        self.assertEqual(deprecation_notices(), ())
        self.assertEqual(HolocronDeprecationWarning.__bases__, (FutureWarning,))

    def test_deprecation_notices_enforce_version_and_date_windows(self) -> None:
        notice: dict[str, JsonValue] = {
            "api": "holocron.models.fit_ols",
            "deprecated_in": "0.1.0",
            "deprecated_on": "2026-01-01",
            "removal_not_before_version": "0.3.0",
            "removal_not_before_date": "2026-04-01",
            "replacement": "holocron.models.fit_gls",
            "status": "active",
        }
        validate_notice(notice, minimum_releases=2, minimum_days=90)

        too_soon = dict(notice)
        too_soon["removal_not_before_version"] = "0.2.0"
        with self.assertRaisesRegex(ValueError, "version window"):
            validate_notice(too_soon, minimum_releases=2, minimum_days=90)

        too_early = dict(notice)
        too_early["removal_not_before_date"] = "2026-03-31"
        with self.assertRaisesRegex(ValueError, "date window"):
            validate_notice(too_early, minimum_releases=2, minimum_days=90)


if __name__ == "__main__":
    unittest.main()
