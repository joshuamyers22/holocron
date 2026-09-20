from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from reference.contracts import validate_document
from tools.check_phase_9_supply_chain import (
    MANIFEST_SCHEMA,
    check,
    check_policy,
    parse_checksums,
)
from tools.prepare_release_artifacts import (
    build_manifest,
    sha256,
    validate_sbom,
    write_checksums,
)


class PhaseNineSupplyChainTests(unittest.TestCase):
    def test_committed_policy_and_workflow_are_fail_closed(self) -> None:
        policy = check_policy()
        check()

        self.assertEqual(policy["status"], "implemented")

    def test_manifest_binds_artifacts_revision_workflow_and_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel = root / "holocron_rms-0.1.0-py3-none-any.whl"
            sdist = root / "holocron_rms-0.1.0.tar.gz"
            sbom = root / "release-sbom.cdx.json"
            wheel.write_bytes(b"wheel")
            sdist.write_bytes(b"sdist")
            sbom.write_text(
                json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.6"}),
                encoding="utf-8",
            )
            with (
                patch(
                    "tools.prepare_release_artifacts.verify_changelog"
                ) as changelog_check,
                patch(
                    "tools.prepare_release_artifacts.repository_file",
                    return_value="governance/approval.md",
                ),
            ):
                manifest = build_manifest(
                    wheel=wheel,
                    sdist=sdist,
                    sbom=sbom,
                    source_revision="a" * 40,
                    release_tag="v0.1.0",
                    approval_record="governance/approval.md",
                    generated_at="2026-09-20T12:00:00Z",
                    workflow_ref="joshuamyers22/holocron/.github/workflows/release.yml@refs/tags/v0.1.0",
                    run_url="https://github.com/joshuamyers22/holocron/actions/runs/1",
                )

            changelog_check.assert_called_once()
            validate_document(manifest, MANIFEST_SCHEMA)
            self.assertEqual(manifest["source_revision"], "a" * 40)
            records = cast(list[object], manifest["artifacts"])
            self.assertEqual(len(records), 3)

    def test_checksum_index_has_exact_sorted_membership_and_detects_tampering(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            second = root / "b.json"
            first = root / "a.whl"
            second.write_bytes(b"second")
            first.write_bytes(b"first")
            index = root / "SHA256SUMS"

            write_checksums(index, (second, first))
            parsed = parse_checksums(index)

            self.assertEqual(parsed, {"a.whl": sha256(first), "b.json": sha256(second)})
            first.write_bytes(b"tampered")
            self.assertNotEqual(parsed["a.whl"], sha256(first))

    def test_sbom_must_be_supported_cyclonedx_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sbom.json"
            path.write_text(
                json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.6"}),
                encoding="utf-8",
            )
            validate_sbom(path)
            path.write_text(
                json.dumps({"bomFormat": "SPDX", "specVersion": "1.6"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "not CycloneDX"):
                validate_sbom(path)

    def test_manifest_rejects_short_source_revision(self) -> None:
        dummy = Path("unused")
        with (
            self.assertRaisesRegex(ValueError, "full lowercase"),
            patch(
                "tools.prepare_release_artifacts.project_identity",
                return_value=("holocron-rms", "0.1.0"),
            ),
        ):
            build_manifest(
                wheel=dummy,
                sdist=dummy,
                sbom=dummy,
                source_revision="abc",
                release_tag="v0.1.0",
                approval_record="unused",
                generated_at="2026-09-20T12:00:00Z",
                workflow_ref="workflow@ref",
                run_url=None,
            )


if __name__ == "__main__":
    unittest.main()
