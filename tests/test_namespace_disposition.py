from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "compatibility/rms-8.2.0.yaml"
GOVERNANCE = ROOT / "governance/PHASE_8_NAMESPACE_DISPOSITION.md"


class NamespaceDispositionTests(unittest.TestCase):
    def setUp(self) -> None:
        raw: object = json.loads(MANIFEST.read_text())
        assert isinstance(raw, dict)
        self.manifest = cast(dict[str, object], raw)
        capabilities = self.manifest["capabilities"]
        assert isinstance(capabilities, list)
        self.capabilities = cast(list[dict[str, object]], capabilities)

    def test_every_pinned_entry_has_a_final_reviewed_disposition(self) -> None:
        review = self.manifest["namespace_disposition"]
        self.assertEqual(
            review,
            {
                "completed_on": "2026-09-19",
                "decision": "complete",
                "reviewed_capabilities": 281,
                "governance_record": "governance/PHASE_8_NAMESPACE_DISPOSITION.md",
            },
        )
        self.assertEqual(len(self.capabilities), 281)
        counts = {
            status: sum(item["status"] == status for item in self.capabilities)
            for status in ("experimental", "mapped", "unsupported")
        }
        self.assertEqual(
            counts,
            {"experimental": 50, "mapped": 125, "unsupported": 106},
        )
        self.assertFalse(
            any(item["status"] == "deferred" for item in self.capabilities)
        )
        self.assertFalse(
            any(
                item["known_differences"] == "Not yet implemented."
                for item in self.capabilities
            )
        )

    def test_mapped_paths_resolve_from_public_namespaces(self) -> None:
        for capability in self.capabilities:
            if capability["status"] != "mapped":
                continue
            path = capability["python_entry_point"]
            self.assertIsInstance(path, str)
            parts = cast(str, path).split(".")
            self.assertGreaterEqual(len(parts), 3)
            value: object = importlib.import_module(".".join(parts[:2]))
            for part in parts[2:]:
                value = getattr(value, part)

    def test_unsupported_entries_are_explicit_non_mappings(self) -> None:
        governance = GOVERNANCE.read_text()
        for capability in self.capabilities:
            if capability["status"] != "unsupported":
                continue
            self.assertIsNone(capability["python_entry_point"])
            rationale = capability["known_differences"]
            self.assertIsInstance(rationale, str)
            self.assertGreaterEqual(len(cast(str, rationale)), 40)
            if cast(str, rationale).startswith(
                "Reviewed for Phase 8 namespace completion:"
            ):
                self.assertIn(f"`{capability['r_symbol']}`", governance)


if __name__ == "__main__":
    unittest.main()
