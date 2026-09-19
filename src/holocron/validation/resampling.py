"""Exact resample plans and model-independent whole-procedure execution."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from numbers import Integral
from typing import Generic, Literal, TypeAlias, TypeVar, cast

import numpy as np

from holocron._serialization import canonical_json, parse_json_object, validate_sha256
from holocron.exceptions import InputValidationError, NumericalError

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
ResampleStrategy: TypeAlias = Literal["bootstrap", "k-fold", "exact"]
FailurePolicy: TypeAlias = Literal["raise", "record"]
ResultT = TypeVar("ResultT")
RowT = TypeVar("RowT")

SCHEMA_VERSION = "holocron-resample-plan/v1"
MAX_OBSERVATIONS = 1_000_000
MAX_RESAMPLES = 10_000
MAX_INDEX_REFERENCES = 10_000_000
MAX_FAILURE_MESSAGE = 1_024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _is_integer(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, Integral)


def _bounded_integer(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if not _is_integer(value) or not minimum <= int(cast(Integral, value)) <= maximum:
        raise InputValidationError(
            f"{name} must be an integer between {minimum} and {maximum}"
        )
    return int(cast(Integral, value))


def _identifier(value: object, *, name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise InputValidationError(
            f"{name} must contain 1-128 letters, digits, dots, underscores, or hyphens"
        )
    return value


def _indices(value: object, *, name: str) -> tuple[int, ...]:
    if not isinstance(value, tuple) or not value:
        raise InputValidationError(f"{name} must be a non-empty tuple of indices")
    raw = cast(tuple[object, ...], value)
    if any(not _is_integer(item) or int(cast(Integral, item)) < 0 for item in raw):
        raise InputValidationError(f"{name} must contain nonnegative integer indices")
    return tuple(int(cast(Integral, item)) for item in raw)


def _row_ids(values: object, *, count: int) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise InputValidationError("row_ids must match the observation count")
    raw = cast(tuple[object, ...], values)
    if len(raw) != count:
        raise InputValidationError("row_ids must match the observation count")
    if any(
        not isinstance(value, str) or not value or len(value) > 256 for value in raw
    ):
        raise InputValidationError(
            "row_ids must be non-empty strings of at most 256 characters"
        )
    normalized = tuple(cast(str, value) for value in raw)
    if len(set(normalized)) != count:
        raise InputValidationError("row_ids must be unique")
    return normalized


def _declared_row_ids(values: Iterable[str] | None, *, count: int) -> tuple[str, ...]:
    return (
        tuple(str(index) for index in range(count)) if values is None else tuple(values)
    )


@dataclass(frozen=True, slots=True)
class ResampleSplit:
    """One exact analysis/assessment split with stable identity."""

    split_id: str
    repeat: int
    fold: int | None
    analysis_indices: tuple[int, ...]
    assessment_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        _identifier(self.split_id, name="split_id")
        repeat = _bounded_integer(
            self.repeat, name="repeat", minimum=0, maximum=MAX_RESAMPLES
        )
        object.__setattr__(self, "repeat", repeat)
        if self.fold is not None:
            fold = _bounded_integer(
                self.fold, name="fold", minimum=0, maximum=MAX_RESAMPLES
            )
            object.__setattr__(self, "fold", fold)
        object.__setattr__(
            self,
            "analysis_indices",
            _indices(self.analysis_indices, name="analysis_indices"),
        )
        object.__setattr__(
            self,
            "assessment_indices",
            _indices(self.assessment_indices, name="assessment_indices"),
        )

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the data-only split document."""
        return {
            "split_id": self.split_id,
            "repeat": self.repeat,
            "fold": self.fold,
            "analysis_indices": list(self.analysis_indices),
            "assessment_indices": list(self.assessment_indices),
        }


@dataclass(frozen=True, slots=True)
class ResamplePlan:
    """An immutable, fully materialized resampling schedule.

    Seeded constructors store every generated index. Replaying serialized plans
    therefore does not depend on a random-number generator implementation.
    """

    plan_id: str
    strategy: ResampleStrategy
    observation_count: int
    row_ids: tuple[str, ...]
    seed: int | None
    splits: tuple[ResampleSplit, ...]

    def __post_init__(self) -> None:
        _identifier(self.plan_id, name="plan_id")
        if self.strategy not in {"bootstrap", "k-fold", "exact"}:
            raise InputValidationError("unsupported resample strategy")
        count = _bounded_integer(
            self.observation_count,
            name="observation_count",
            minimum=2,
            maximum=MAX_OBSERVATIONS,
        )
        object.__setattr__(self, "observation_count", count)
        object.__setattr__(self, "row_ids", _row_ids(self.row_ids, count=count))
        if self.seed is not None:
            seed = _bounded_integer(
                self.seed, name="seed", minimum=0, maximum=2**63 - 1
            )
            object.__setattr__(self, "seed", seed)
        if not isinstance(cast(object, self.splits), tuple) or not self.splits:
            raise InputValidationError("splits must be a non-empty tuple")
        if len(self.splits) > MAX_RESAMPLES:
            raise InputValidationError(
                f"resample plan exceeds the {MAX_RESAMPLES}-split limit"
            )
        raw_splits = cast(tuple[object, ...], cast(object, self.splits))
        if any(not isinstance(split, ResampleSplit) for split in raw_splits):
            raise InputValidationError("splits must contain ResampleSplit values")
        if len({split.split_id for split in self.splits}) != len(self.splits):
            raise InputValidationError("split identifiers must be unique")
        references = sum(
            len(split.analysis_indices) + len(split.assessment_indices)
            for split in self.splits
        )
        if references > MAX_INDEX_REFERENCES:
            raise InputValidationError(
                f"resample plan exceeds the {MAX_INDEX_REFERENCES}-index limit"
            )
        if any(
            index >= count
            for split in self.splits
            for index in (*split.analysis_indices, *split.assessment_indices)
        ):
            raise InputValidationError("resample indices are outside the row range")
        if self.strategy == "bootstrap":
            self._validate_bootstrap()
        elif self.strategy == "k-fold":
            self._validate_k_fold()

    def _validate_bootstrap(self) -> None:
        if self.seed is None:
            raise InputValidationError("bootstrap plans require a seed")
        expected_assessment = tuple(range(self.observation_count))
        for position, split in enumerate(self.splits):
            if (
                split.repeat != position
                or split.fold is not None
                or len(split.analysis_indices) != self.observation_count
                or split.assessment_indices != expected_assessment
            ):
                raise InputValidationError(
                    "bootstrap splits must contain one full-size analysis resample "
                    "and the original assessment rows"
                )

    def _validate_k_fold(self) -> None:
        if self.seed is None:
            raise InputValidationError("k-fold plans require a seed")
        all_rows = set(range(self.observation_count))
        by_repeat: dict[int, list[ResampleSplit]] = defaultdict(list)
        for split in self.splits:
            if split.fold is None:
                raise InputValidationError("k-fold splits require fold identifiers")
            analysis = set(split.analysis_indices)
            assessment = set(split.assessment_indices)
            if (
                len(analysis) != len(split.analysis_indices)
                or len(assessment) != len(split.assessment_indices)
                or analysis & assessment
                or analysis | assessment != all_rows
            ):
                raise InputValidationError(
                    "k-fold analysis and assessment rows must uniquely partition data"
                )
            by_repeat[split.repeat].append(split)
        if set(by_repeat) != set(range(len(by_repeat))):
            raise InputValidationError("k-fold repeats must be contiguous from zero")
        fold_count: int | None = None
        for repeat_splits in by_repeat.values():
            folds = {cast(int, split.fold) for split in repeat_splits}
            if folds != set(range(len(repeat_splits))):
                raise InputValidationError("k-fold identifiers must be contiguous")
            if fold_count is None:
                fold_count = len(folds)
            elif len(folds) != fold_count:
                raise InputValidationError("each repeat must have the same fold count")
            assessments = [
                index for split in repeat_splits for index in split.assessment_indices
            ]
            if sorted(assessments) != list(range(self.observation_count)):
                raise InputValidationError(
                    "k-fold assessment rows must cover each observation once per repeat"
                )

    @classmethod
    def bootstrap(
        cls,
        observation_count: int,
        *,
        replicates: int = 200,
        seed: int = 1,
        plan_id: str = "bootstrap",
        row_ids: Iterable[str] | None = None,
    ) -> ResamplePlan:
        """Generate an exact iid bootstrap plan with original-data assessment."""
        count = _bounded_integer(
            observation_count,
            name="observation_count",
            minimum=2,
            maximum=MAX_OBSERVATIONS,
        )
        repetitions = _bounded_integer(
            replicates,
            name="replicates",
            minimum=2,
            maximum=MAX_RESAMPLES,
        )
        normalized_seed = _bounded_integer(
            seed, name="seed", minimum=0, maximum=2**63 - 1
        )
        if repetitions * count * 2 > MAX_INDEX_REFERENCES:
            raise InputValidationError("bootstrap plan exceeds the total index limit")
        generator = np.random.default_rng(normalized_seed)
        assessment = tuple(range(count))
        splits = tuple(
            ResampleSplit(
                split_id=f"bootstrap-{replicate + 1}",
                repeat=replicate,
                fold=None,
                analysis_indices=tuple(
                    int(value) for value in generator.integers(0, count, size=count)
                ),
                assessment_indices=assessment,
            )
            for replicate in range(repetitions)
        )
        return cls(
            plan_id=plan_id,
            strategy="bootstrap",
            observation_count=count,
            row_ids=_declared_row_ids(row_ids, count=count),
            seed=normalized_seed,
            splits=splits,
        )

    @classmethod
    def k_fold(
        cls,
        observation_count: int,
        *,
        folds: int = 10,
        repeats: int = 1,
        seed: int = 1,
        plan_id: str = "k-fold",
        row_ids: Iterable[str] | None = None,
    ) -> ResamplePlan:
        """Generate an exact seeded repeated K-fold plan."""
        count = _bounded_integer(
            observation_count,
            name="observation_count",
            minimum=2,
            maximum=MAX_OBSERVATIONS,
        )
        fold_count = _bounded_integer(folds, name="folds", minimum=2, maximum=count)
        repeat_count = _bounded_integer(
            repeats, name="repeats", minimum=1, maximum=MAX_RESAMPLES
        )
        if fold_count * repeat_count > MAX_RESAMPLES:
            raise InputValidationError("folds times repeats exceeds the split limit")
        if fold_count * repeat_count * count > MAX_INDEX_REFERENCES:
            raise InputValidationError("k-fold plan exceeds the total index limit")
        normalized_seed = _bounded_integer(
            seed, name="seed", minimum=0, maximum=2**63 - 1
        )
        generator = np.random.default_rng(normalized_seed)
        all_rows = tuple(range(count))
        splits: list[ResampleSplit] = []
        for repeat in range(repeat_count):
            assignment = generator.permutation(  # pyright: ignore[reportUnknownMemberType]
                count
            )
            fold_sizes = [count // fold_count] * fold_count
            for fold in range(count % fold_count):
                fold_sizes[fold] += 1
            start = 0
            for fold, size in enumerate(fold_sizes):
                assessment = tuple(
                    sorted(int(value) for value in assignment[start : start + size])
                )
                assessment_set = set(assessment)
                analysis = tuple(row for row in all_rows if row not in assessment_set)
                splits.append(
                    ResampleSplit(
                        split_id=f"repeat-{repeat + 1}-fold-{fold + 1}",
                        repeat=repeat,
                        fold=fold,
                        analysis_indices=analysis,
                        assessment_indices=assessment,
                    )
                )
                start += size
        return cls(
            plan_id=plan_id,
            strategy="k-fold",
            observation_count=count,
            row_ids=_declared_row_ids(row_ids, count=count),
            seed=normalized_seed,
            splits=tuple(splits),
        )

    @classmethod
    def exact(
        cls,
        observation_count: int,
        splits: Iterable[tuple[Iterable[int], Iterable[int]]],
        *,
        plan_id: str = "exact",
        row_ids: Iterable[str] | None = None,
    ) -> ResamplePlan:
        """Snapshot caller-declared analysis and assessment indices exactly."""
        count = _bounded_integer(
            observation_count,
            name="observation_count",
            minimum=2,
            maximum=MAX_OBSERVATIONS,
        )
        try:
            snapshot = tuple(
                (tuple(analysis), tuple(assessment)) for analysis, assessment in splits
            )
        except (TypeError, ValueError) as error:
            raise InputValidationError(
                "exact splits must contain analysis/assessment iterable pairs"
            ) from error
        if not snapshot:
            raise InputValidationError("exact plan must contain at least one split")
        return cls(
            plan_id=plan_id,
            strategy="exact",
            observation_count=count,
            row_ids=_declared_row_ids(row_ids, count=count),
            seed=None,
            splits=tuple(
                ResampleSplit(
                    split_id=f"exact-{position + 1}",
                    repeat=position,
                    fold=None,
                    analysis_indices=analysis,
                    assessment_indices=assessment,
                )
                for position, (analysis, assessment) in enumerate(snapshot)
            ),
        )

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the exact versioned resample-plan document."""
        return {
            "schema_version": SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "strategy": self.strategy,
            "observation_count": self.observation_count,
            "row_ids": list(self.row_ids),
            "seed": self.seed,
            "splits": [split.to_dict() for split in self.splits],
        }

    def to_json(self) -> str:
        """Serialize the exact plan as canonical non-executable JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the exact serialized schedule."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> ResamplePlan:
        """Reconstruct and revalidate an exact-version resample plan."""
        if not isinstance(document, dict):
            raise InputValidationError("resample plan document must be an object")
        raw = cast(dict[str, object], document)
        required = {
            "schema_version",
            "plan_id",
            "strategy",
            "observation_count",
            "row_ids",
            "seed",
            "splits",
        }
        if set(raw) != required:
            raise InputValidationError("resample plan document fields differ")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise InputValidationError("unsupported resample plan schema version")
        raw_splits = raw["splits"]
        raw_row_ids = raw["row_ids"]
        if not isinstance(raw_splits, list) or not isinstance(raw_row_ids, list):
            raise InputValidationError("resample plan rows and splits must be arrays")
        splits: list[ResampleSplit] = []
        split_fields = {
            "split_id",
            "repeat",
            "fold",
            "analysis_indices",
            "assessment_indices",
        }
        for raw_split in cast(list[object], raw_splits):
            if not isinstance(raw_split, dict):
                raise InputValidationError("resample split fields differ")
            split = cast(dict[str, object], raw_split)
            if set(split) != split_fields:
                raise InputValidationError("resample split fields differ")
            analysis = split["analysis_indices"]
            assessment = split["assessment_indices"]
            if not isinstance(analysis, list) or not isinstance(assessment, list):
                raise InputValidationError("resample indices must be arrays")
            splits.append(
                ResampleSplit(
                    split_id=cast(str, split["split_id"]),
                    repeat=cast(int, split["repeat"]),
                    fold=cast(int | None, split["fold"]),
                    analysis_indices=tuple(cast(list[int], analysis)),
                    assessment_indices=tuple(cast(list[int], assessment)),
                )
            )
        return cls(
            plan_id=cast(str, raw["plan_id"]),
            strategy=cast(ResampleStrategy, raw["strategy"]),
            observation_count=cast(int, raw["observation_count"]),
            row_ids=tuple(cast(list[str], raw_row_ids)),
            seed=cast(int | None, raw["seed"]),
            splits=tuple(splits),
        )

    @classmethod
    def from_json(cls, value: str) -> ResamplePlan:
        """Reconstruct a plan from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="resample plan"))


@dataclass(frozen=True, slots=True)
class ResampleSuccess(Generic[ResultT]):
    """One successful whole-procedure resample result."""

    split_id: str
    value: ResultT

    def __post_init__(self) -> None:
        _identifier(self.split_id, name="split_id")


@dataclass(frozen=True, slots=True)
class ResampleFailure:
    """A bounded failure record for one resample."""

    split_id: str
    exception_type: str
    message: str

    def __post_init__(self) -> None:
        _identifier(self.split_id, name="split_id")
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


@dataclass(frozen=True, slots=True)
class ResampleExecution(Generic[ResultT]):
    """Explicit completed and failed outcomes from an exact plan."""

    plan_fingerprint: str
    planned_count: int
    successes: tuple[ResampleSuccess[ResultT], ...]
    failures: tuple[ResampleFailure, ...]

    def __post_init__(self) -> None:
        validate_sha256(self.plan_fingerprint, role="plan_fingerprint")
        planned_count = _bounded_integer(
            self.planned_count,
            name="planned_count",
            minimum=1,
            maximum=MAX_RESAMPLES,
        )
        object.__setattr__(self, "planned_count", planned_count)
        raw_successes = cast(tuple[object, ...], cast(object, self.successes))
        raw_failures = cast(tuple[object, ...], cast(object, self.failures))
        if not isinstance(cast(object, self.successes), tuple) or any(
            not isinstance(value, ResampleSuccess) for value in raw_successes
        ):
            raise InputValidationError("successes must contain ResampleSuccess values")
        if not isinstance(cast(object, self.failures), tuple) or any(
            not isinstance(value, ResampleFailure) for value in raw_failures
        ):
            raise InputValidationError("failures must contain ResampleFailure values")
        if len(self.successes) + len(self.failures) != self.planned_count:
            raise InputValidationError("resample outcomes must match planned_count")
        identifiers = [value.split_id for value in self.successes] + [
            value.split_id for value in self.failures
        ]
        if len(set(identifiers)) != len(identifiers):
            raise InputValidationError("resample outcome identifiers must be unique")

    @property
    def status(self) -> Literal["complete", "partial", "failed"]:
        """Return whether all, some, or no resamples completed."""
        if not self.failures:
            return "complete"
        return "partial" if self.successes else "failed"

    @property
    def failure_rate(self) -> float:
        """Return failed resamples divided by planned resamples."""
        return len(self.failures) / self.planned_count


def take_rows(
    values: Iterable[RowT],
    indices: Iterable[int],
    *,
    plan: ResamplePlan,
    row_ids: Iterable[str] | None = None,
) -> tuple[RowT, ...]:
    """Select exact rows after enforcing alignment with the parent plan."""
    if not isinstance(cast(object, plan), ResamplePlan):
        raise InputValidationError("plan must be a ResamplePlan")
    count = plan.observation_count
    rows = tuple(values)
    if len(rows) != count:
        raise InputValidationError("values must match the plan observation count")
    if row_ids is not None and tuple(row_ids) != plan.row_ids:
        raise InputValidationError("row_ids must match the exact plan row identity")
    selected = tuple(indices)
    if not selected or any(not _is_integer(index) for index in selected):
        raise InputValidationError("indices must contain nonnegative integers")
    normalized = tuple(int(cast(Integral, index)) for index in selected)
    if any(index < 0 or index >= count for index in normalized):
        raise InputValidationError("indices are outside the row range")
    return tuple(rows[index] for index in normalized)


def run_resample_plan(
    plan: ResamplePlan,
    procedure: Callable[[ResampleSplit], ResultT],
    *,
    failure_policy: FailurePolicy = "raise",
) -> ResampleExecution[ResultT]:
    """Run a fresh caller-owned procedure once for every exact split.

    The callback receives indices rather than a pre-fitted model so all learned
    transformations, selection, fitting, and assessment can occur inside the
    resample. ``record`` preserves bounded failure details and never labels a
    partial execution complete; ``raise`` fails on the first unsuccessful split.
    """
    if not isinstance(cast(object, plan), ResamplePlan):
        raise InputValidationError("plan must be a ResamplePlan")
    if not callable(procedure):
        raise InputValidationError("procedure must be callable")
    if failure_policy not in {"raise", "record"}:
        raise InputValidationError("failure_policy must be 'raise' or 'record'")
    successes: list[ResampleSuccess[ResultT]] = []
    failures: list[ResampleFailure] = []
    for split in plan.splits:
        try:
            value = procedure(split)
        except Exception as error:
            if failure_policy == "raise":
                raise NumericalError(
                    f"whole-procedure resample {split.split_id!r} failed"
                ) from error
            failures.append(
                ResampleFailure(
                    split_id=split.split_id,
                    exception_type=type(error).__name__,
                    message=str(error)[:MAX_FAILURE_MESSAGE],
                )
            )
        else:
            successes.append(ResampleSuccess(split_id=split.split_id, value=value))
    return ResampleExecution(
        plan_fingerprint=plan.fingerprint,
        planned_count=len(plan.splits),
        successes=tuple(successes),
        failures=tuple(failures),
    )


__all__ = [
    "ResampleExecution",
    "ResampleFailure",
    "ResamplePlan",
    "ResampleSplit",
    "ResampleSuccess",
    "run_resample_plan",
    "take_rows",
]
