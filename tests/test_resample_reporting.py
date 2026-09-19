from __future__ import annotations

import math
import unittest

from holocron.exceptions import InputValidationError
from holocron.validation import (
    ResampleExecution,
    ResampleFailure,
    ResampleFailureReason,
    ResampleMetricCoverage,
    ResamplePlan,
    ResampleReport,
    ResampleSplit,
    ResampleSuccess,
    report_resample_execution,
    run_resample_plan,
)


class ResampleReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = ResamplePlan.exact(
            5,
            (
                ((0, 1, 2, 3), (4,)),
                ((0, 1, 2, 4), (3,)),
                ((0, 1, 3, 4), (2,)),
                ((0, 2, 3, 4), (1,)),
                ((1, 2, 3, 4), (0,)),
            ),
            plan_id="reporting",
        )

    def test_complete_report_preserves_exact_outcomes(self) -> None:
        execution = run_resample_plan(self.plan, lambda split: split.repeat)
        report = report_resample_execution(
            execution,
            metric_contributors={"score": 5},
        )

        self.assertIsInstance(report, ResampleReport)
        self.assertEqual(report.status, "complete")
        self.assertTrue(report.aggregation_permitted)
        self.assertEqual(report.aggregation_policy, "complete-only")
        self.assertEqual(report.planned_resamples, 5)
        self.assertEqual(report.successful_resamples, 5)
        self.assertEqual(report.failed_resamples, 0)
        self.assertEqual(report.success_rate, 1.0)
        self.assertEqual(report.failure_rate, 0.0)
        self.assertEqual(report.failure_reasons, ())
        self.assertFalse(report.is_partial)
        self.assertEqual(
            report.successful_split_ids,
            tuple(split.split_id for split in self.plan.splits),
        )
        self.assertEqual(
            report.metric_coverage,
            (
                ResampleMetricCoverage(
                    metric_name="score",
                    contributing_resamples=5,
                    omitted_successes=0,
                    planned_coverage=1.0,
                    successful_coverage=1.0,
                ),
            ),
        )

    def test_partial_report_groups_reasons_and_requires_explicit_opt_in(self) -> None:
        def procedure(split: ResampleSplit) -> int:
            if split.repeat in {1, 3}:
                raise ValueError("single class")
            if split.repeat == 4:
                raise RuntimeError("singular fit")
            return split.repeat

        execution = run_resample_plan(
            self.plan,
            procedure,
            failure_policy="record",
        )
        strict = report_resample_execution(
            execution,
            metric_contributors={"auc": 1, "brier_score": 2},
        )
        allowed = report_resample_execution(execution, allow_partial=True)

        self.assertEqual(strict.status, "partial")
        self.assertTrue(strict.is_partial)
        self.assertFalse(strict.aggregation_permitted)
        self.assertEqual(strict.aggregation_policy, "complete-only")
        self.assertTrue(allowed.aggregation_permitted)
        self.assertEqual(allowed.aggregation_policy, "allow-partial")
        self.assertEqual(strict.successful_resamples, 2)
        self.assertEqual(strict.failed_resamples, 3)
        self.assertEqual(strict.success_rate, 0.4)
        self.assertEqual(strict.failure_rate, 0.6)
        self.assertEqual(
            tuple(
                (reason.exception_type, reason.message, reason.count)
                for reason in strict.failure_reasons
            ),
            (
                ("RuntimeError", "singular fit", 1),
                ("ValueError", "single class", 2),
            ),
        )
        self.assertEqual(
            strict.failure_reasons[1],
            ResampleFailureReason(
                exception_type="ValueError",
                message="single class",
                count=2,
                planned_rate=0.4,
                split_ids=("exact-2", "exact-4"),
            ),
        )
        auc = next(
            metric for metric in strict.metric_coverage if metric.metric_name == "auc"
        )
        self.assertEqual(auc.contributing_resamples, 1)
        self.assertEqual(auc.omitted_successes, 1)
        self.assertEqual(auc.planned_coverage, 0.2)
        self.assertEqual(auc.successful_coverage, 0.5)

    def test_all_failed_execution_never_permits_aggregation(self) -> None:
        execution = run_resample_plan(
            self.plan,
            lambda split: (_ for _ in ()).throw(RuntimeError(split.split_id)),
            failure_policy="record",
        )
        report = report_resample_execution(
            execution,
            allow_partial=True,
            metric_contributors={"score": 0},
        )

        self.assertEqual(report.status, "failed")
        self.assertFalse(report.aggregation_permitted)
        self.assertEqual(report.success_rate, 0.0)
        self.assertEqual(report.failure_rate, 1.0)
        self.assertIsNone(report.metric_coverage[0].successful_coverage)

    def test_invalid_reporting_inputs_and_inconsistent_results_fail_closed(
        self,
    ) -> None:
        execution = run_resample_plan(self.plan, lambda split: split.split_id)
        with self.assertRaisesRegex(InputValidationError, "allow_partial"):
            report_resample_execution(execution, allow_partial=1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(InputValidationError, "mapping"):
            report_resample_execution(
                execution,
                metric_contributors=("score", 5),  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(InputValidationError, "between zero and 5"):
            report_resample_execution(
                execution,
                metric_contributors={"score": 6},
            )
        with self.assertRaisesRegex(InputValidationError, "metric_name"):
            report_resample_execution(
                execution,
                metric_contributors={"invalid metric": 5},
            )

        partial = ResampleExecution(
            plan_fingerprint=self.plan.fingerprint,
            planned_count=2,
            successes=(ResampleSuccess("exact-1", 1),),
            failures=(ResampleFailure("exact-2", "ValueError", "failed"),),
        )
        with self.assertRaisesRegex(InputValidationError, "disposition"):
            ResampleReport(
                plan_fingerprint=partial.plan_fingerprint,
                status="partial",
                aggregation_policy="complete-only",
                aggregation_permitted=True,
                planned_resamples=2,
                successful_resamples=1,
                failed_resamples=1,
                success_rate=0.5,
                failure_rate=0.5,
                successful_split_ids=("exact-1",),
                failed_split_ids=("exact-2",),
                failure_reasons=(
                    ResampleFailureReason("ValueError", "failed", 1, 0.5, ("exact-2",)),
                ),
                metric_coverage=(),
            )

        self.assertTrue(math.isclose(partial.failure_rate, 0.5))


if __name__ == "__main__":
    unittest.main()
