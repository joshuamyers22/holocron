"""Structured failure-rate and partial-resample reporting."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from numbers import Integral
from typing import Literal, TypeAlias, TypeVar, cast

from holocron._serialization import validate_sha256
from holocron.exceptions import InputValidationError
from holocron.validation.resampling import (
    MAX_FAILURE_MESSAGE,
    MAX_RESAMPLES,
    ResampleExecution,
)

ExecutionStatus: TypeAlias = Literal["complete", "partial", "failed"]
AggregationPolicy: TypeAlias = Literal["complete-only", "allow-partial"]

MAX_REPORT_METRICS = 256
_REPORT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ReportT = TypeVar("ReportT")


def _count(value: object, *, name: str, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, Integral)
        or not 0 <= int(value) <= maximum
    ):
        raise InputValidationError(
            f"{name} must be an integer between zero and {maximum}"
        )
    return int(value)


def _rate(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise InputValidationError(f"{name} must be between zero and one")
    try:
        normalized = float(cast(float, value))
    except (TypeError, ValueError) as error:
        raise InputValidationError(f"{name} must be between zero and one") from error
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise InputValidationError(f"{name} must be between zero and one")
    return normalized


def _name(value: object, *, role: str) -> str:
    if not isinstance(value, str) or _REPORT_NAME.fullmatch(value) is None:
        raise InputValidationError(
            f"{role} must contain 1-128 letters, digits, dots, underscores, or hyphens"
        )
    return value


@dataclass(frozen=True, slots=True)
class ResampleFailureReason:
    """One exact exception-type/message category in a resample execution."""

    exception_type: str
    message: str
    count: int
    planned_rate: float
    split_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(cast(object, self.exception_type), str)
            or not self.exception_type
            or len(self.exception_type) > 256
        ):
            raise InputValidationError("exception_type has an unsupported length")
        if (
            not isinstance(cast(object, self.message), str)
            or len(self.message) > MAX_FAILURE_MESSAGE
        ):
            raise InputValidationError("failure message exceeds the supported length")
        if (
            not isinstance(cast(object, self.split_ids), tuple)
            or not self.split_ids
            or len(set(self.split_ids)) != len(self.split_ids)
        ):
            raise InputValidationError("failure-reason split_ids are invalid")
        for split_id in self.split_ids:
            _name(split_id, role="split_id")
        normalized_count = _count(self.count, name="count", maximum=MAX_RESAMPLES)
        if normalized_count != len(self.split_ids):
            raise InputValidationError("failure-reason count must match split_ids")
        object.__setattr__(self, "count", normalized_count)
        object.__setattr__(
            self,
            "planned_rate",
            _rate(self.planned_rate, name="planned_rate"),
        )


@dataclass(frozen=True, slots=True)
class ResampleMetricCoverage:
    """Defined-result coverage for one metric across successful resamples."""

    metric_name: str
    contributing_resamples: int
    omitted_successes: int
    planned_coverage: float
    successful_coverage: float | None

    def __post_init__(self) -> None:
        _name(self.metric_name, role="metric_name")
        contributing = _count(
            self.contributing_resamples,
            name="contributing_resamples",
            maximum=MAX_RESAMPLES,
        )
        omitted = _count(
            self.omitted_successes,
            name="omitted_successes",
            maximum=MAX_RESAMPLES,
        )
        object.__setattr__(self, "contributing_resamples", contributing)
        object.__setattr__(self, "omitted_successes", omitted)
        object.__setattr__(
            self,
            "planned_coverage",
            _rate(self.planned_coverage, name="planned_coverage"),
        )
        if self.successful_coverage is not None:
            object.__setattr__(
                self,
                "successful_coverage",
                _rate(self.successful_coverage, name="successful_coverage"),
            )


@dataclass(frozen=True, slots=True)
class ResampleReport:
    """Exact execution counts, failure reasons, and aggregation disposition."""

    plan_fingerprint: str
    status: ExecutionStatus
    aggregation_policy: AggregationPolicy
    aggregation_permitted: bool
    planned_resamples: int
    successful_resamples: int
    failed_resamples: int
    success_rate: float
    failure_rate: float
    successful_split_ids: tuple[str, ...]
    failed_split_ids: tuple[str, ...]
    failure_reasons: tuple[ResampleFailureReason, ...]
    metric_coverage: tuple[ResampleMetricCoverage, ...]

    def __post_init__(self) -> None:
        validate_sha256(self.plan_fingerprint, role="plan_fingerprint")
        if self.status not in {"complete", "partial", "failed"}:
            raise InputValidationError("unsupported resample report status")
        if self.aggregation_policy not in {"complete-only", "allow-partial"}:
            raise InputValidationError("unsupported aggregation policy")
        if not isinstance(cast(object, self.aggregation_permitted), bool):
            raise InputValidationError("aggregation_permitted must be boolean")
        planned = _count(
            self.planned_resamples,
            name="planned_resamples",
            maximum=MAX_RESAMPLES,
        )
        successful = _count(
            self.successful_resamples,
            name="successful_resamples",
            maximum=MAX_RESAMPLES,
        )
        failed = _count(
            self.failed_resamples,
            name="failed_resamples",
            maximum=MAX_RESAMPLES,
        )
        if planned < 1 or successful + failed != planned:
            raise InputValidationError("resample report counts are inconsistent")
        object.__setattr__(self, "planned_resamples", planned)
        object.__setattr__(self, "successful_resamples", successful)
        object.__setattr__(self, "failed_resamples", failed)
        success_rate = _rate(self.success_rate, name="success_rate")
        failure_rate = _rate(self.failure_rate, name="failure_rate")
        if not math.isclose(success_rate, successful / planned) or not math.isclose(
            failure_rate, failed / planned
        ):
            raise InputValidationError("resample report rates are inconsistent")
        object.__setattr__(self, "success_rate", success_rate)
        object.__setattr__(self, "failure_rate", failure_rate)
        expected_status: ExecutionStatus = (
            "complete" if failed == 0 else "partial" if successful else "failed"
        )
        if self.status != expected_status:
            raise InputValidationError("resample report status is inconsistent")
        expected_permission = self.status == "complete" or (
            self.status == "partial" and self.aggregation_policy == "allow-partial"
        )
        if self.aggregation_permitted != expected_permission:
            raise InputValidationError("aggregation disposition is inconsistent")
        for name, values, count in (
            ("successful_split_ids", self.successful_split_ids, successful),
            ("failed_split_ids", self.failed_split_ids, failed),
        ):
            if (
                not isinstance(cast(object, values), tuple)
                or len(values) != count
                or len(set(values)) != len(values)
            ):
                raise InputValidationError(f"{name} do not match report counts")
            for split_id in values:
                _name(split_id, role="split_id")
        if set(self.successful_split_ids).intersection(self.failed_split_ids):
            raise InputValidationError("successful and failed split IDs overlap")
        if not isinstance(cast(object, self.failure_reasons), tuple) or any(
            not isinstance(cast(object, reason), ResampleFailureReason)
            for reason in self.failure_reasons
        ):
            raise InputValidationError("failure_reasons are invalid")
        reason_ids = tuple(
            split_id for reason in self.failure_reasons for split_id in reason.split_ids
        )
        if len(reason_ids) != len(set(reason_ids)) or set(reason_ids) != set(
            self.failed_split_ids
        ):
            raise InputValidationError("failure reasons must partition failed splits")
        if any(
            not math.isclose(reason.planned_rate, reason.count / planned)
            for reason in self.failure_reasons
        ):
            raise InputValidationError("failure-reason rates are inconsistent")
        if (
            not isinstance(cast(object, self.metric_coverage), tuple)
            or len(self.metric_coverage) > MAX_REPORT_METRICS
            or any(
                not isinstance(cast(object, metric), ResampleMetricCoverage)
                for metric in self.metric_coverage
            )
            or len({metric.metric_name for metric in self.metric_coverage})
            != len(self.metric_coverage)
        ):
            raise InputValidationError("metric_coverage is invalid")
        for metric in self.metric_coverage:
            if (
                metric.contributing_resamples + metric.omitted_successes != successful
                or not math.isclose(
                    metric.planned_coverage,
                    metric.contributing_resamples / planned,
                )
                or (successful == 0 and metric.successful_coverage is not None)
                or (
                    successful > 0
                    and (
                        metric.successful_coverage is None
                        or not math.isclose(
                            metric.successful_coverage,
                            metric.contributing_resamples / successful,
                        )
                    )
                )
            ):
                raise InputValidationError("metric coverage is inconsistent")

    @property
    def is_partial(self) -> bool:
        """Return whether the report covers only a successful subset."""
        return self.status == "partial"


def report_resample_execution(
    execution: ResampleExecution[ReportT],
    *,
    allow_partial: bool = False,
    metric_contributors: Mapping[str, int] | None = None,
) -> ResampleReport:
    """Summarize exact outcomes without treating partial execution as complete.

    Reporting never aggregates callback values. ``allow_partial`` records an
    explicit aggregation disposition for downstream callers; it cannot permit
    aggregation when every resample failed. Optional metric contributor counts
    distinguish undefined successful-pair metrics from failed resamples.
    """
    if not isinstance(cast(object, execution), ResampleExecution):
        raise InputValidationError("execution must be a ResampleExecution")
    if not isinstance(cast(object, allow_partial), bool):
        raise InputValidationError("allow_partial must be boolean")
    raw_contributors: Mapping[str, int]
    if metric_contributors is None:
        raw_contributors = {}
    elif isinstance(cast(object, metric_contributors), Mapping):
        raw_contributors = metric_contributors
    else:
        raise InputValidationError("metric_contributors must be a mapping")
    if len(raw_contributors) > MAX_REPORT_METRICS:
        raise InputValidationError(
            f"metric_contributors exceeds the {MAX_REPORT_METRICS}-metric limit"
        )
    successful_count = len(execution.successes)
    normalized_contributors: dict[str, int] = {}
    for raw_name, raw_count in raw_contributors.items():
        metric_name = _name(raw_name, role="metric_name")
        normalized_contributors[metric_name] = _count(
            raw_count,
            name=f"metric_contributors[{metric_name!r}]",
            maximum=successful_count,
        )
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for failure in execution.failures:
        grouped[(failure.exception_type, failure.message)].append(failure.split_id)
    failure_reasons = tuple(
        ResampleFailureReason(
            exception_type=exception_type,
            message=message,
            count=len(split_ids),
            planned_rate=len(split_ids) / execution.planned_count,
            split_ids=tuple(split_ids),
        )
        for (exception_type, message), split_ids in sorted(grouped.items())
    )
    metric_coverage = tuple(
        ResampleMetricCoverage(
            metric_name=metric_name,
            contributing_resamples=count,
            omitted_successes=successful_count - count,
            planned_coverage=count / execution.planned_count,
            successful_coverage=(
                None if successful_count == 0 else count / successful_count
            ),
        )
        for metric_name, count in sorted(normalized_contributors.items())
    )
    policy: AggregationPolicy = "allow-partial" if allow_partial else "complete-only"
    permitted = execution.status == "complete" or (
        execution.status == "partial" and allow_partial
    )
    return ResampleReport(
        plan_fingerprint=execution.plan_fingerprint,
        status=execution.status,
        aggregation_policy=policy,
        aggregation_permitted=permitted,
        planned_resamples=execution.planned_count,
        successful_resamples=successful_count,
        failed_resamples=len(execution.failures),
        success_rate=successful_count / execution.planned_count,
        failure_rate=execution.failure_rate,
        successful_split_ids=tuple(value.split_id for value in execution.successes),
        failed_split_ids=tuple(value.split_id for value in execution.failures),
        failure_reasons=failure_reasons,
        metric_coverage=metric_coverage,
    )


__all__ = [
    "ResampleFailureReason",
    "ResampleMetricCoverage",
    "ResampleReport",
    "report_resample_execution",
]
