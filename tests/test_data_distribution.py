from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import cast

import numpy as np

from holocron.design import DataDistribution, DistributionRange
from holocron.exceptions import InputValidationError
from reference.contracts import (
    CASES,
    EXPECTED,
    JsonValue,
    compare_json,
    output_payload,
    validate_case_pair,
    validate_document,
)
from reference.python_parity import build_python_output


class DataDistributionTests(unittest.TestCase):
    def test_numeric_rules_match_documented_datadist_semantics(self) -> None:
        distribution = DataDistribution.from_data(
            {
                "binary": (1, 0, 1, 0, 1) * 4,
                "three": (30, 10, 20, 30, 20) * 4,
                "continuous": tuple(range(1, 21)),
                "constant": (4,) * 20,
            },
            labels={"continuous": "Continuous predictor"},
            units={"continuous": "years"},
        )

        self.assertEqual(distribution.names, tuple(distribution.adjustments))
        self.assertEqual(distribution.adjustments["binary"], 0.0)
        self.assertEqual(distribution.adjustments["three"], 20.0)
        self.assertEqual(distribution.adjustments["continuous"], 10.5)
        self.assertEqual(distribution["constant"].effect_range, DistributionRange(4, 4))
        self.assertEqual(distribution["continuous"].kind, "continuous")
        self.assertEqual(distribution["binary"].kind, "discrete")
        self.assertEqual(distribution["binary"].values, (0.0, 1.0))
        self.assertEqual(
            distribution["continuous"].effect_range, DistributionRange(5.75, 15.25)
        )
        display = distribution["continuous"].display_range
        self.assertAlmostEqual(cast(float, display.lower), 1.95)
        self.assertAlmostEqual(cast(float, display.upper), 19.05)
        self.assertEqual(distribution["continuous"].label, "Continuous predictor")
        self.assertEqual(distribution["continuous"].unit, "years")

    def test_explicit_quantiles_and_discrete_threshold(self) -> None:
        distribution = DataDistribution.from_data(
            {"x": tuple(range(10))},
            effect_quantiles=(0.1, 0.9),
            display_quantiles=(0.0, 1.0),
            discrete_threshold=20,
        )
        self.assertEqual(distribution["x"].kind, "discrete")
        self.assertEqual(distribution["x"].effect_range, DistributionRange(0.9, 8.1))
        self.assertEqual(distribution["x"].display_range, DistributionRange(0, 9))
        self.assertEqual(distribution["x"].values, tuple(float(x) for x in range(10)))

    def test_categorical_mode_ties_and_order_are_explicit(self) -> None:
        data = {
            "group": ("B", "A", "B", "A", None, "C"),
            "stage": (1, 2, 3, 2, 1, None),
        }
        distribution = DataDistribution.from_data(
            data,
            levels={"group": ("A", "B", "C"), "stage": (1, 2, 3)},
            ordered=("stage",),
            labels={"group": "Treatment group", "stage": "Disease stage"},
        )

        group = distribution["group"]
        self.assertEqual(group.kind, "categorical")
        self.assertEqual(group.adjustment, "A")
        self.assertIsNone(group.effect_range)
        self.assertEqual(group.values, ("A", "B", "C"))
        self.assertEqual(group.missing_count, 1)
        self.assertEqual(distribution["stage"].kind, "ordered")
        self.assertEqual(distribution["stage"].adjustment, 2.0)
        self.assertEqual(distribution["stage"].effect_range, DistributionRange(1, 3))

        first = DataDistribution.from_data(
            data,
            levels={"group": ("C", "B", "A"), "stage": (1, 2, 3)},
            ordered=("stage",),
            categorical_adjustment="first",
        )
        self.assertEqual(first["group"].adjustment, "C")

    def test_missing_values_are_counted_and_excluded(self) -> None:
        distribution = DataDistribution.from_data({"x": (1.0, None, 2.0, np.nan, 3.0)})
        variable = distribution["x"]
        self.assertEqual(variable.nonmissing_count, 3)
        self.assertEqual(variable.missing_count, 2)
        self.assertEqual(variable.observation_count, 5)
        self.assertEqual(variable.adjustment, 2.0)

    def test_input_is_snapshotted_and_adjustment_replacement_is_immutable(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0]
        original = DataDistribution.from_data({"x": values})
        values[0] = 100.0
        updated = original.with_adjustment("x", 3.25)

        self.assertEqual(original["x"].overall_range, DistributionRange(1, 4))
        self.assertEqual(original["x"].adjustment, 2.5)
        self.assertEqual(updated["x"].adjustment, 3.25)
        self.assertIsNot(original, updated)

    def test_extension_preserves_policies_and_rejects_duplicates(self) -> None:
        original = DataDistribution.from_data(
            {"x": (1, 2, 3, 4)},
            effect_quantiles=(0.1, 0.9),
            display_quantiles=(0, 1),
            discrete_threshold=3,
        )
        extended = original.with_data(
            {"group": ("A", "B", "A", "B")},
            levels={"group": ("A", "B")},
        )
        self.assertEqual(extended.names, ("x", "group"))
        self.assertEqual(extended.effect_quantiles, (0.1, 0.9))
        self.assertEqual(extended.display_quantiles, (0.0, 1.0))
        self.assertEqual(extended.discrete_threshold, 3)
        with self.assertRaises(InputValidationError):
            original.with_data({"x": (5, 6, 7, 8)})
        with self.assertRaises(InputValidationError):
            original.with_data({"y": (5, 6, 7)})

    def test_serialization_round_trip_is_canonical_and_schema_valid(self) -> None:
        distribution = DataDistribution.from_data(
            {"age": (30, 40, 50, 60), "group": ("A", "B", "A", "B")},
            levels={"group": ("A", "B")},
            labels={"age": "Age"},
            units={"age": "years"},
        )
        document = distribution.to_dict()
        validate_document(
            cast(JsonValue, document),
            Path("schemas/data-distribution.schema.json").resolve(),
        )
        restored = DataDistribution.from_json(distribution.to_json())

        self.assertEqual(restored, distribution)
        self.assertEqual(restored.fingerprint, distribution.fingerprint)
        self.assertEqual(
            json.loads(distribution.to_json()),
            distribution.to_dict(),
        )

    def test_rejects_ambiguous_or_invalid_inputs(self) -> None:
        invalid_calls = (
            lambda: DataDistribution.from_data({}),
            lambda: DataDistribution.from_data({"x": (1,)}),
            lambda: DataDistribution.from_data({"x": (1, 2), "y": (1, 2, 3)}),
            lambda: DataDistribution.from_data({"x": (1, float("inf"))}),
            lambda: DataDistribution.from_data({"group": ("A", "B")}),
            lambda: DataDistribution.from_data(
                {"group": ("A", "C")}, levels={"group": ("A", "B")}
            ),
            lambda: DataDistribution.from_data(
                {"x": (1, 2)}, effect_quantiles=(0.9, 0.1)
            ),
            lambda: DataDistribution.from_data(
                {"x": (1, 2)}, labels={"missing": "Unknown"}
            ),
            lambda: DataDistribution.from_data(
                {"x": (1, 2)}, discrete_threshold=cast(int, 1.5)
            ),
            lambda: DataDistribution.from_data(
                {"group": ("A", "B")},
                levels={"group": cast(tuple[str, ...], ("A", 2))},
            ),
        )
        for invalid_call in invalid_calls:
            with (
                self.subTest(call=invalid_call),
                self.assertRaises(InputValidationError),
            ):
                invalid_call()

    def test_rejects_invalid_serialized_documents(self) -> None:
        distribution = DataDistribution.from_data({"x": (1, 2, 3)})
        document = cast(dict[str, object], distribution.to_dict())
        document["schema_version"] = "future"
        with self.assertRaises(InputValidationError):
            DataDistribution.from_dict(document)
        with self.assertRaises(InputValidationError):
            DataDistribution.from_json("[]")

    def test_matches_all_datadist_oracle_fixtures(self) -> None:
        case_paths = sorted(CASES.glob("datadist-*.json"))
        self.assertEqual(len(case_paths), 4)
        for case_path in case_paths:
            with self.subTest(case_id=case_path.stem):
                case, expected, policy = validate_case_pair(
                    case_path, EXPECTED / case_path.name
                )
                actual = build_python_output(case)
                compare_json(actual, output_payload(expected), policy).require_match()


if __name__ == "__main__":
    unittest.main()
