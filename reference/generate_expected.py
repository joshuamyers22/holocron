"""Generate reviewable oracle fixtures from declarative cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reference.check_oracle import run_case
from reference.contracts import (
    CASE_SCHEMA,
    CASES,
    EXPECTED,
    OUTPUT_SCHEMA,
    ROOT,
    JsonValue,
    load_json,
    require_object,
    validate_document,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / ".work/candidate-expected",
        help="destination; defaults to a review-only work directory",
    )
    parser.add_argument(
        "--accept",
        action="store_true",
        help="write the generated fixtures to reference/expected",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="generate only this case ID; may be supplied more than once",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = EXPECTED if args.accept else args.output_dir
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    environment = require_object(
        load_json(EXPECTED / "oracle-environment.json"), name="oracle environment"
    )
    reference = require_object(environment["reference"], name="oracle reference")
    health_metadata_keys = (
        "oracle_image",
        "oracle_image_digest",
        "rms_commit",
        "rms_file_manifest_sha256",
        "rms_description_sha256",
        "hmisc_commit",
    )

    case_paths = sorted(CASES.glob("*.json"))
    if args.case_ids:
        requested = set(args.case_ids)
        case_paths = [path for path in case_paths if path.stem in requested]
        missing = requested - {path.stem for path in case_paths}
        if missing:
            raise ValueError(f"unknown case IDs: {', '.join(sorted(missing))}")
    for case_path in case_paths:
        case = require_object(load_json(case_path), name=str(case_path))
        validate_document(case, CASE_SCHEMA)
        actual = run_case(case)
        fixture: dict[str, JsonValue] = {
            "schema_version": "holocron-oracle-output/v1",
            "case_id": case["case_id"],
            "reference": reference,
        }
        if case["operation"] == "health":
            fixture.update({key: environment[key] for key in health_metadata_keys})
            fixture["response"] = actual
        else:
            fixture.update(actual)
        validate_document(fixture, OUTPUT_SCHEMA)
        destination = output_dir / str(case["expected_output"])
        destination.write_text(
            json.dumps(fixture, allow_nan=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"generated {destination.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
