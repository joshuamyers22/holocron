"""Validate the Phase 9 release-candidate and external-beta evidence."""

from __future__ import annotations

import argparse
import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from reference.contracts import (
    JsonValue,
    load_json,
    require_array,
    require_object,
    validate_document,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "governance/phase-9-release-candidate-plan.json"
PROGRAM = ROOT / "governance/phase-9-beta-program.json"
PLAN_SCHEMA = ROOT / "schemas/phase-9-release-candidate-plan.schema.json"
PROGRAM_SCHEMA = ROOT / "schemas/phase-9-beta-program.schema.json"
PYPROJECT = ROOT / "pyproject.toml"


@dataclass(frozen=True, slots=True)
class ProgramSummary:
    """Evaluated Phase 9 program state without personal reviewer information."""

    status: str
    candidate_count: int
    reviewer_count: int
    covered_workflow_count: int
    blocker_count: int
    complete: bool
    incomplete_reasons: tuple[str, ...]


def _objects(value: JsonValue, *, name: str) -> list[dict[str, JsonValue]]:
    return [
        require_object(item, name=f"{name}[{index}]")
        for index, item in enumerate(require_array(value, name=name))
    ]


def _strings(value: JsonValue, *, name: str) -> tuple[str, ...]:
    result: list[str] = []
    for index, item in enumerate(require_array(value, name=name)):
        if not isinstance(item, str):
            raise ValueError(f"{name}[{index}] must be a string")
        result.append(item)
    return tuple(result)


def _unique(values: list[str], *, name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} contains duplicates")


def _version_tuple(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"invalid final release version: {value}")
    return cast(tuple[int, int, int], tuple(int(part) for part in parts))


def project_version(path: Path = PYPROJECT) -> str:
    document = cast(dict[str, object], tomllib.loads(path.read_text(encoding="utf-8")))
    project_value = document.get("project")
    if not isinstance(project_value, dict):
        raise ValueError("pyproject.toml has no project table")
    project = cast(dict[str, object], project_value)
    version = project.get("version")
    if not isinstance(version, str):
        raise ValueError("pyproject.toml has no project version")
    return version


def evaluate_program(
    plan: dict[str, JsonValue],
    program: dict[str, JsonValue],
    *,
    current_version: str,
) -> ProgramSummary:
    """Validate cross-record invariants and evaluate completion criteria."""
    if plan["plan_id"] != program["plan_id"]:
        raise ValueError("release-candidate plan and program IDs differ")
    target_version = cast(str, plan["target_version"])
    if _version_tuple(target_version) <= _version_tuple(current_version):
        raise ValueError("release-candidate target must follow the package version")

    required_checks = set(_strings(plan["required_checks"], name="required_checks"))
    required_workflows = set(
        _strings(plan["required_workflows"], name="required_workflows")
    )
    blocking_severities = set(
        _strings(plan["blocking_severities"], name="blocking_severities")
    )
    minimum_candidates = cast(int, plan["minimum_candidates"])
    minimum_reviewers = cast(int, plan["minimum_external_reviewers"])

    candidates = _objects(program["candidates"], name="candidates")
    candidate_ids = [cast(str, candidate["candidate_id"]) for candidate in candidates]
    revisions = [cast(str, candidate["source_revision"]) for candidate in candidates]
    _unique(candidate_ids, name="candidate IDs")
    _unique(revisions, name="candidate source revisions")
    for expected_ordinal, candidate in enumerate(candidates, start=1):
        ordinal = cast(int, candidate["ordinal"])
        expected_version = f"{target_version}rc{ordinal}"
        if ordinal != expected_ordinal:
            raise ValueError("candidate ordinals must be contiguous and ordered")
        if candidate["candidate_id"] != f"holocron-{expected_version}":
            raise ValueError(f"candidate {ordinal} identifier differs from its version")
        if candidate["version"] != expected_version:
            raise ValueError(f"candidate {ordinal} version differs from its ordinal")
        if candidate["tag"] != f"v{expected_version}":
            raise ValueError(f"candidate {ordinal} tag differs from its version")
        if set(_strings(candidate["checks"], name=f"candidate {ordinal} checks")) != (
            required_checks
        ):
            raise ValueError(
                f"candidate {ordinal} does not retain every required check"
            )
        status = candidate["status"]
        if ordinal < len(candidates) and status != "superseded":
            raise ValueError("every non-final candidate must be superseded")
        if ordinal == len(candidates) and status == "superseded":
            raise ValueError("the final candidate cannot be superseded")

    approvals = _objects(
        program["distribution_approvals"], name="distribution_approvals"
    )
    approval_ids = [cast(str, approval["candidate_id"]) for approval in approvals]
    _unique(approval_ids, name="distribution-approval candidate IDs")
    candidates_by_id = {
        cast(str, candidate["candidate_id"]): candidate for candidate in candidates
    }
    for approval in approvals:
        candidate_id = cast(str, approval["candidate_id"])
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None:
            raise ValueError(f"distribution approval names unknown {candidate_id}")
        if approval["approved_source_revision"] != candidate["source_revision"]:
            raise ValueError(
                f"distribution approval revision differs for {candidate_id}"
            )

    feedback = _objects(program["feedback"], name="feedback")
    feedback_ids = [cast(str, item["feedback_id"]) for item in feedback]
    _unique(feedback_ids, name="feedback IDs")
    finding_ids: list[str] = []
    reviewers: set[str] = set()
    workflows: set[str] = set()
    open_blocking_findings: list[str] = []
    feedback_by_candidate: dict[str, int] = {}
    for item in feedback:
        candidate_id = cast(str, item["candidate_id"])
        if candidate_id not in candidates_by_id:
            raise ValueError(f"feedback names unknown {candidate_id}")
        if candidate_id not in approval_ids:
            raise ValueError(f"feedback exists without approval for {candidate_id}")
        feedback_by_candidate[candidate_id] = (
            feedback_by_candidate.get(candidate_id, 0) + 1
        )
        reviewers.add(cast(str, item["reviewer_id"]))
        workflows.update(_strings(item["workflows"], name="feedback workflows"))
        for finding in _objects(item["findings"], name="feedback findings"):
            finding_id = cast(str, finding["finding_id"])
            finding_ids.append(finding_id)
            disposition = finding["disposition"]
            resolution = finding["resolution"]
            if disposition == "open" and resolution is not None:
                raise ValueError(f"open finding {finding_id} has a resolution")
            if disposition != "open" and not isinstance(resolution, str):
                raise ValueError(f"closed finding {finding_id} lacks a resolution")
            if finding["severity"] in blocking_severities and disposition != "resolved":
                open_blocking_findings.append(finding_id)
    _unique(finding_ids, name="finding IDs")

    blockers = _objects(program["blockers"], name="blockers")
    blocker_ids = [cast(str, blocker["blocker_id"]) for blocker in blockers]
    _unique(blocker_ids, name="blocker IDs")
    reasons: list[str] = []
    if len(candidates) < minimum_candidates:
        reasons.append(f"need {minimum_candidates - len(candidates)} more candidates")
    missing_approvals = sorted(set(candidate_ids) - set(approval_ids))
    if missing_approvals:
        reasons.append(
            f"candidates lack distribution approval: {', '.join(missing_approvals)}"
        )
    if len(reviewers) < minimum_reviewers:
        reasons.append(
            f"need {minimum_reviewers - len(reviewers)} more external reviewers"
        )
    missing_workflows = sorted(required_workflows - workflows)
    if missing_workflows:
        reasons.append(
            f"feedback workflows are missing: {', '.join(missing_workflows)}"
        )
    if open_blocking_findings:
        reasons.append(
            "blocking findings are not resolved: "
            + ", ".join(sorted(open_blocking_findings))
        )
    final_candidate_id = candidate_ids[-1] if candidate_ids else None
    if final_candidate_id is not None:
        if candidates[-1]["status"] != "accepted":
            reasons.append("final candidate is not accepted")
        if feedback_by_candidate.get(final_candidate_id, 0) == 0:
            reasons.append("final candidate has no external feedback")
    if blockers:
        reasons.append(f"{len(blockers)} program blockers remain")

    evidence_complete = not reasons
    status = cast(str, program["status"])
    if status == "complete" and not evidence_complete:
        raise ValueError("beta program claims completion without complete evidence")
    if status != "complete" and evidence_complete:
        raise ValueError(
            "beta program has complete evidence but is not marked complete"
        )
    if status == "blocked" and not blockers:
        raise ValueError("blocked beta program has no blockers")
    if status == "active" and blockers:
        raise ValueError("active beta program still has blockers")

    return ProgramSummary(
        status=status,
        candidate_count=len(candidates),
        reviewer_count=len(reviewers),
        covered_workflow_count=len(workflows),
        blocker_count=len(blockers),
        complete=status == "complete" and evidence_complete,
        incomplete_reasons=tuple(reasons),
    )


def _load_records(
    *, plan_path: Path, program_path: Path
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    plan_value = load_json(plan_path)
    program_value = load_json(program_path)
    validate_document(plan_value, PLAN_SCHEMA)
    validate_document(program_value, PROGRAM_SCHEMA)
    plan = require_object(plan_value, name="release-candidate plan")
    program = require_object(program_value, name="beta program")
    return plan, program


def _validate_approval_records(program: dict[str, JsonValue]) -> None:
    for approval in _objects(
        program["distribution_approvals"], name="distribution_approvals"
    ):
        record = ROOT / cast(str, approval["record"])
        if not record.is_file():
            raise ValueError(f"distribution approval record is missing: {record}")


def check(*, plan_path: Path = PLAN, program_path: Path = PROGRAM) -> ProgramSummary:
    plan, program = _load_records(plan_path=plan_path, program_path=program_path)
    _validate_approval_records(program)
    return evaluate_program(plan, program, current_version=project_version())


def validate_releasable_candidate(
    plan: dict[str, JsonValue],
    program: dict[str, JsonValue],
    tag: str,
    *,
    current_version: str,
) -> None:
    """Require one recorded, approved candidate and an unblocked program."""
    evaluate_program(plan, program, current_version=current_version)
    if program["status"] not in {"active", "complete"}:
        raise ValueError("release-candidate program is not active")
    if require_array(program["blockers"], name="blockers"):
        raise ValueError("release-candidate program still has blockers")
    candidates = _objects(program["candidates"], name="candidates")
    matches = [candidate for candidate in candidates if candidate["tag"] == tag]
    if len(matches) != 1:
        raise ValueError(f"release tag is not a recorded candidate: {tag}")
    candidate = matches[0]
    if candidate["status"] not in {"active", "accepted"}:
        raise ValueError(f"release candidate is not distributable: {tag}")
    approvals = _objects(
        program["distribution_approvals"], name="distribution_approvals"
    )
    candidate_id = candidate["candidate_id"]
    approvals_for_candidate = [
        approval for approval in approvals if approval["candidate_id"] == candidate_id
    ]
    if len(approvals_for_candidate) != 1:
        raise ValueError(f"release candidate lacks exact distribution approval: {tag}")


def validate_candidate_artifacts(
    program: dict[str, JsonValue], tag: str, artifact_directory: Path
) -> None:
    """Match built wheel and sdist bytes to one recorded candidate."""
    candidates = _objects(program["candidates"], name="candidates")
    matches = [candidate for candidate in candidates if candidate["tag"] == tag]
    if len(matches) != 1:
        raise ValueError(f"release tag is not a recorded candidate: {tag}")
    candidate = matches[0]
    version = cast(str, candidate["version"])
    expected = require_object(
        candidate["artifact_sha256"], name=f"{tag}.artifact_sha256"
    )
    paths = {
        "wheel": artifact_directory / f"holocron_rms-{version}-py3-none-any.whl",
        "sdist": artifact_directory / f"holocron_rms-{version}.tar.gz",
    }
    for kind, path in paths.items():
        if not path.is_file():
            raise ValueError(f"{tag} {kind} artifact is missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected[kind]:
            raise ValueError(f"{tag} {kind} artifact digest differs")


def require_releasable_candidate(
    tag: str, *, plan_path: Path = PLAN, program_path: Path = PROGRAM
) -> None:
    plan, program = _load_records(plan_path=plan_path, program_path=program_path)
    _validate_approval_records(program)
    validate_releasable_candidate(plan, program, tag, current_version=project_version())


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--plan", type=Path, default=PLAN)
    command.add_argument("--program", type=Path, default=PROGRAM)
    command.add_argument("--require-complete", action="store_true")
    command.add_argument("--release-tag")
    command.add_argument("--artifact-directory", type=Path)
    return command


def main() -> int:
    args = parser().parse_args()
    summary = check(plan_path=args.plan, program_path=args.program)
    print(
        "Phase 9 release-candidate program verified: "
        f"status={summary.status}, candidates={summary.candidate_count}, "
        f"external_reviewers={summary.reviewer_count}, "
        f"workflow_coverage={summary.covered_workflow_count}, "
        f"blockers={summary.blocker_count}"
    )
    if args.release_tag is not None:
        require_releasable_candidate(
            args.release_tag, plan_path=args.plan, program_path=args.program
        )
        print(f"release candidate is recorded and approved: {args.release_tag}")
        if args.artifact_directory is not None:
            _, program = _load_records(plan_path=args.plan, program_path=args.program)
            validate_candidate_artifacts(
                program, args.release_tag, args.artifact_directory
            )
            print(f"release candidate artifact hashes match: {args.release_tag}")
    elif args.artifact_directory is not None:
        raise ValueError("--artifact-directory requires --release-tag")
    if args.require_complete and not summary.complete:
        for reason in summary.incomplete_reasons:
            print(f"- {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
