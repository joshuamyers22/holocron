from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.verify_release import verify_changelog, verify_release


class VerifyReleaseTests(unittest.TestCase):
    def test_tag_must_match_project_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "pyproject.toml"
            manifest.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")

            verify_release(manifest, "v1.2.3")
            with self.assertRaisesRegex(ValueError, "does not match"):
                verify_release(manifest, "v1.2.4")

    def test_changelog_requires_one_exact_dated_heading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changelog = Path(directory) / "CHANGELOG.md"
            changelog.write_text(
                "# Changelog\n\n## [1.2.3] - 2026-09-20\n\n- Ready.\n",
                encoding="utf-8",
            )

            verify_changelog(changelog, "1.2.3")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                verify_changelog(changelog, "1.2.4")

    def test_undated_or_duplicate_heading_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changelog = Path(directory) / "CHANGELOG.md"
            changelog.write_text(
                "## [1.2.3]\n\n## [1.2.3] - 2026-09-20\n\n## [1.2.3] - 2026-09-21\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "exactly one"):
                verify_changelog(changelog, "1.2.3")


if __name__ == "__main__":
    unittest.main()
