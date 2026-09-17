"""Check the live Docker oracle against the committed reference fixtures."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "reference/r/run-oracle.sh"
CASES = ROOT / "reference/cases"
EXPECTED = ROOT / "reference/expected"


def compare(actual: object, expected: object, path: str = "response") -> None:
    """Recursively compare JSON values with a tight numeric tolerance."""
    if isinstance(actual, bool) or isinstance(expected, bool):
        if actual is not expected:
            raise AssertionError(f"{path}: {actual!r} != {expected!r}")
        return
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if not math.isclose(
            float(actual), float(expected), rel_tol=1e-13, abs_tol=1e-14
        ):
            raise AssertionError(f"{path}: {actual!r} != {expected!r}")
        return
    if isinstance(actual, dict) and isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise AssertionError(f"{path}: keys {sorted(actual)} != {sorted(expected)}")
        for key in actual:
            compare(actual[key], expected[key], f"{path}.{key}")
        return
    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            raise AssertionError(f"{path}: length {len(actual)} != {len(expected)}")
        for index, (actual_item, expected_item) in enumerate(
            zip(actual, expected, strict=True)
        ):
            compare(actual_item, expected_item, f"{path}[{index}]")
        return
    if actual != expected:
        raise AssertionError(f"{path}: {actual!r} != {expected!r}")


def load_json(path: Path) -> object:
    """Load one JSON document without weakening its dynamic boundary."""
    return json.loads(path.read_text())


def run_case(case_name: str) -> object:
    """Execute one case through the constrained oracle runner."""
    completed = subprocess.run(
        [str(RUNNER)],
        input=(CASES / case_name).read_text(),
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"oracle failed for {case_name} with status {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    return json.loads(completed.stdout)


def main() -> None:
    """Verify environment identity and deterministic method fixtures."""
    health_expected = load_json(EXPECTED / "oracle-environment.json")
    if not isinstance(health_expected, dict):
        raise TypeError("oracle environment fixture must be an object")
    compare(run_case("health.json"), health_expected["response"])

    for case_name in ("rcs-explicit.json", "ols-rcs-explicit.json"):
        compare(run_case(case_name), load_json(EXPECTED / case_name))
        print(f"oracle fixture verified: {case_name}")
    print("oracle environment verified")


if __name__ == "__main__":
    main()
