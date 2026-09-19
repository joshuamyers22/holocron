from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from holocron.exceptions import InputValidationError, NumericalError
from holocron.models import fit_ols
from holocron.validation import (
    ResamplePlan,
    ResampleSplit,
    run_resample_plan,
    take_rows,
)
from reference.contracts import validate_document

ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA = ROOT / "schemas/resample-plan.schema.json"


class ResamplingTests(unittest.TestCase):
    def test_bootstrap_plan_is_exact_reproducible_and_serializable(self) -> None:
        first = ResamplePlan.bootstrap(
            12, replicates=8, seed=90210, plan_id="bootstrap-example"
        )
        second = ResamplePlan.bootstrap(
            12, replicates=8, seed=90210, plan_id="bootstrap-example"
        )

        self.assertEqual(first, second)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first, ResamplePlan.from_json(first.to_json()))
        self.assertTrue(
            all(len(split.analysis_indices) == 12 for split in first.splits)
        )
        self.assertTrue(
            all(split.assessment_indices == tuple(range(12)) for split in first.splits)
        )
        self.assertNotEqual(
            first,
            ResamplePlan.bootstrap(
                12, replicates=8, seed=90211, plan_id="bootstrap-example"
            ),
        )
        validate_document(first.to_dict(), PLAN_SCHEMA)

    def test_repeated_k_fold_partitions_rows_exactly(self) -> None:
        plan = ResamplePlan.k_fold(
            11, folds=4, repeats=3, seed=44, plan_id="repeated-four-fold"
        )

        self.assertEqual(len(plan.splits), 12)
        self.assertEqual(plan, ResamplePlan.from_dict(plan.to_dict()))
        for repeat in range(3):
            splits = [split for split in plan.splits if split.repeat == repeat]
            assessed = [index for split in splits for index in split.assessment_indices]
            self.assertEqual(sorted(assessed), list(range(11)))
            for split in splits:
                self.assertFalse(
                    set(split.analysis_indices) & set(split.assessment_indices)
                )
                self.assertEqual(
                    set(split.analysis_indices) | set(split.assessment_indices),
                    set(range(11)),
                )

    def test_exact_plan_preserves_declared_order_and_multiplicity(self) -> None:
        plan = ResamplePlan.exact(
            5,
            (
                ((4, 4, 1, 0), (2, 3)),
                ((2, 1, 3), (4, 0)),
            ),
            plan_id="declared-splits",
            row_ids=("a", "b", "c", "d", "e"),
        )

        self.assertEqual(plan.splits[0].analysis_indices, (4, 4, 1, 0))
        self.assertEqual(plan.splits[0].assessment_indices, (2, 3))
        self.assertEqual(
            take_rows(
                ("a", "b", "c", "d", "e"),
                plan.splits[0].analysis_indices,
                plan=plan,
                row_ids=("a", "b", "c", "d", "e"),
            ),
            ("e", "e", "b", "a"),
        )
        with self.assertRaisesRegex(InputValidationError, "row identity"):
            take_rows(
                ("a", "b", "c", "d", "e"),
                plan.splits[0].analysis_indices,
                plan=plan,
                row_ids=("b", "a", "c", "d", "e"),
            )

    def test_executor_refits_inside_each_split_and_binds_plan(self) -> None:
        x = tuple(float(value) for value in range(12))
        y = tuple(1.5 + 0.7 * value + 0.05 * ((value % 3) - 1) for value in x)
        features = tuple((value,) for value in x)
        plan = ResamplePlan.k_fold(12, folds=3, repeats=2, seed=71)
        fits: list[object] = []

        def procedure(split: ResampleSplit) -> tuple[int, int, float]:
            analysis_y = take_rows(y, split.analysis_indices, plan=plan)
            analysis_x = take_rows(
                features,
                split.analysis_indices,
                plan=plan,
            )
            assessment_y = take_rows(y, split.assessment_indices, plan=plan)
            assessment_x = take_rows(
                features,
                split.assessment_indices,
                plan=plan,
            )
            fitted = fit_ols(analysis_y, analysis_x, feature_names=("x",))
            fits.append(fitted)
            predictions = fitted.predict(assessment_x)
            mse = float(
                np.mean((np.asarray(predictions) - np.asarray(assessment_y)) ** 2)
            )
            return fitted.n_observations, len(assessment_y), mse

        result = run_resample_plan(plan, procedure)

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.failure_rate, 0.0)
        self.assertEqual(result.plan_fingerprint, plan.fingerprint)
        self.assertEqual(len(result.successes), len(plan.splits))
        self.assertEqual(len({id(fit) for fit in fits}), len(plan.splits))
        self.assertTrue(all(success.value[2] < 0.02 for success in result.successes))

    def test_partial_failures_are_explicit_and_raise_policy_fails_closed(self) -> None:
        plan = ResamplePlan.exact(
            4,
            (
                ((0, 1, 2), (3,)),
                ((0, 1, 3), (2,)),
                ((0, 2, 3), (1,)),
            ),
        )

        def sometimes_fails(split: ResampleSplit) -> str:
            if split.split_id == "exact-2":
                raise ValueError("declared test failure")
            return split.split_id

        recorded = run_resample_plan(plan, sometimes_fails, failure_policy="record")
        self.assertEqual(recorded.status, "partial")
        self.assertEqual(recorded.failure_rate, 1.0 / 3.0)
        self.assertEqual(len(recorded.successes), 2)
        self.assertEqual(recorded.failures[0].exception_type, "ValueError")
        self.assertEqual(recorded.failures[0].message, "declared test failure")

        failed = run_resample_plan(
            plan,
            lambda split: (_ for _ in ()).throw(RuntimeError(split.split_id)),
            failure_policy="record",
        )
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.failure_rate, 1.0)

        with self.assertRaisesRegex(NumericalError, "exact-2") as caught:
            run_resample_plan(plan, sometimes_fails)
        self.assertIsInstance(caught.exception.__cause__, ValueError)

    def test_invalid_plans_and_row_alignment_fail_closed(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "observation_count"):
            ResamplePlan.bootstrap(True, replicates=2)  # type: ignore[arg-type]
        with self.assertRaisesRegex(InputValidationError, "folds"):
            ResamplePlan.k_fold(4, folds=5)
        with self.assertRaisesRegex(InputValidationError, "total index"):
            ResamplePlan.k_fold(1_000_000, folds=11, repeats=1)
        with self.assertRaisesRegex(InputValidationError, "outside"):
            ResamplePlan.exact(4, (((0, 1, 4), (2, 3)),))
        with self.assertRaisesRegex(InputValidationError, "iterable pairs"):
            ResamplePlan.exact(4, ((0, 1, 2),))  # type: ignore[arg-type]
        aligned_plan = ResamplePlan.exact(4, (((0, 1), (2, 3)),))
        with self.assertRaisesRegex(InputValidationError, "observation count"):
            take_rows((1, 2, 3), (0, 1), plan=aligned_plan)
        with self.assertRaisesRegex(InputValidationError, "outside"):
            take_rows((1, 2, 3, 4), (-1,), plan=aligned_plan)
        with self.assertRaisesRegex(InputValidationError, "partition"):
            ResamplePlan(
                plan_id="bad-k-fold",
                strategy="k-fold",
                observation_count=4,
                row_ids=("0", "1", "2", "3"),
                seed=1,
                splits=(
                    ResampleSplit("repeat-1-fold-1", 0, 0, (0, 1, 2), (2, 3)),
                    ResampleSplit("repeat-1-fold-2", 0, 1, (2, 3), (0, 1)),
                ),
            )
        with self.assertRaisesRegex(InputValidationError, "failure_policy"):
            run_resample_plan(
                ResamplePlan.exact(2, (((0,), (1,)),)),
                lambda split: split.split_id,
                failure_policy="ignore",  # type: ignore[arg-type]
            )

    def test_readers_reject_unknown_duplicate_and_inconsistent_documents(self) -> None:
        plan = ResamplePlan.k_fold(6, folds=3, seed=4)
        document = plan.to_dict()
        document["unknown"] = True
        with self.assertRaisesRegex(InputValidationError, "fields differ"):
            ResamplePlan.from_dict(document)

        duplicate = plan.to_json().replace(
            '"plan_id":"k-fold"',
            '"plan_id":"k-fold","plan_id":"duplicate"',
        )
        with self.assertRaisesRegex(InputValidationError, "invalid resample plan JSON"):
            ResamplePlan.from_json(duplicate)

        malformed = json.loads(plan.to_json())
        malformed["splits"][0]["analysis_indices"] = [0, 1]
        with self.assertRaisesRegex(InputValidationError, "partition"):
            ResamplePlan.from_dict(malformed)


if __name__ == "__main__":
    unittest.main()
