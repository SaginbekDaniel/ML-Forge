"""Turns a finished sandbox run into stored results, evidence and progress."""

from __future__ import annotations

import logging

from mlforge_runner import SandboxOutcome, TestOutcome, grade
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..content.schema import MasteryPolicy
from ..models import (
    Assessment,
    Exercise,
    HintUsage,
    ReviewItem,
    RunJob,
    SkillEvidence,
    Submission,
    TestResult,
    utcnow,
)
from .progress import refresh_skill_states, resolve_review

log = logging.getLogger("mlforge.grading")

RUN_TEST_ID = "__run__"
SOURCE_TYPE_BY_MODE = {
    "practice": "exercise",
    "independent": "assessment",
    "review": "review",
    "diagnostic": "diagnostic",
}


def tests_for(submission: Submission, exercise: Exercise, stdin: str | None = None) -> list[dict]:
    spec_tests = exercise.spec["tests"]
    if submission.kind == "submit":
        return spec_tests
    # "Run": execute the program as a script (shows prints) + public tests only.
    run_test = {
        "id": RUN_TEST_ID,
        "kind": "script",
        "visibility": "public",
        "stdin": stdin or "",
        "description": "program run",
        "tags": [],
    }
    return [run_test, *[t for t in spec_tests if t.get("visibility") == "public"]]


def max_hint_level(db: Session, profile_id: str, exercise_id: str, version: int) -> int:
    return (
        db.scalar(
            select(func.coalesce(func.max(HintUsage.level), 0)).where(
                HintUsage.profile_id == profile_id,
                HintUsage.exercise_id == exercise_id,
                HintUsage.exercise_version == version,
            )
        )
        or 0
    )


def _safe_output(o: TestOutcome) -> dict:
    data = o.to_dict()
    for key in ("id", "visibility", "passed", "status", "error_type", "duration_ms"):
        data.pop(key, None)
    if o.visibility != "public":  # defence in depth: never persist hidden data
        data = {"tags": o.tags, "line": o.line, "description": ""}
    return data


def finalize_job(
    db: Session, job: RunJob, outcome: SandboxOutcome, tests: list[dict], policy: MasteryPolicy, memory_limit_mb: int
) -> None:
    submission = job.submission
    exercise = db.get(Exercise, (submission.exercise_id, submission.exercise_version))
    now = utcnow()
    job.finished_at = now
    job.duration_ms = outcome.duration_ms
    job.memory_limit_mb = memory_limit_mb

    if outcome.status == "cancelled":
        job.status, job.exit_reason = "cancelled", "cancelled"
        db.commit()
        return
    if outcome.status in ("unavailable", "crashed"):
        job.status = "failed"
        job.exit_reason = "runner_unavailable" if outcome.status == "unavailable" else "runner_crashed"
        db.commit()
        return

    if outcome.status == "completed":
        observations = outcome.observations
    else:  # container-level timeout / memory kill: every test failed the same way
        status = "timeout" if outcome.status == "timeout" else "killed"
        observations = [{"id": t["id"], "status": status} for t in tests]
    results, _ = grade(tests, observations)
    graded_specs = [t for t in tests if t["id"] != RUN_TEST_ID]
    graded_results = [r for r in results if r.id != RUN_TEST_ID]
    _, summary = grade(graded_specs, [o for o in observations if o.get("id") != RUN_TEST_ID])

    for pos, r in enumerate(results):
        db.add(
            TestResult(
                job_id=job.id,
                test_id=r.id,
                position=pos,
                visibility=r.visibility,
                passed=r.passed,
                status=r.status,
                error_type=r.error_type,
                duration_ms=r.duration_ms,
                safe_output=_safe_output(r),
            )
        )
    job.passed, job.total = summary.passed, summary.total
    job.edge_cases_passed, job.edge_cases_total = summary.edge_cases_passed, summary.edge_cases_total
    job.score = summary.score if summary.total else None
    job.error_type = summary.error_type
    job.max_test_ms = summary.max_test_ms
    any_timeout = any(r.status == "timeout" for r in results)
    if outcome.status == "timeout" or (any_timeout and summary.passed < summary.total):
        job.status, job.exit_reason = "timed_out", "timeout"
    elif outcome.status == "memory_limit":
        job.status, job.exit_reason = "failed", "memory_limit"
    else:
        job.status = "completed"
        if summary.total == 0:
            run = next((r for r in results if r.id == RUN_TEST_ID), None)
            job.exit_reason = "ran" if run is None or run.passed else (run.error_type or run.status)
        else:
            job.exit_reason = "all_passed" if summary.passed == summary.total else (summary.error_type or "failed")
        if submission.kind == "run":
            run = next((r for r in results if r.id == RUN_TEST_ID), None)
            if run is not None and not run.passed and summary.passed == summary.total:
                job.exit_reason = run.error_type or run.status

    if submission.kind == "submit" and exercise is not None and summary.total:
        _record_evidence(db, submission, exercise, summary.score, graded_results, policy, now)
    db.commit()


def _record_evidence(
    db: Session,
    submission: Submission,
    exercise: Exercise,
    score: float,
    results: list[TestOutcome],
    policy: MasteryPolicy,
    now,
) -> None:
    source_type = SOURCE_TYPE_BY_MODE[submission.mode]
    hint_level = submission.hint_level
    failing_tags = sorted({t for r in results if not r.passed for t in r.tags})
    db.add(
        SkillEvidence(
            profile_id=submission.profile_id,
            skill_id=exercise.skill_id,
            source_type=source_type,
            verification="verified_by_tests",
            source_id=submission.id,
            exercise_id=exercise.id,
            score=score,
            hint_level=hint_level,
            created_at=now,
            details={"exercise_version": exercise.version, "failing_tags": failing_tags, "mode": submission.mode},
        )
    )
    passed = score >= policy.pass_threshold
    if submission.assessment_id:
        assessment = db.get(Assessment, submission.assessment_id)
        if assessment and assessment.status == "active":
            assessment.status = "passed" if passed else "failed"
            assessment.finished_at = now
            assessment.submission_id = submission.id
    if submission.review_item_id:
        item = db.get(ReviewItem, submission.review_item_id)
        if item and item.status == "pending":
            resolve_review(
                db, item, passed=passed, used_hints=hint_level > 0, submission_id=submission.id, policy=policy, now=now
            )
    db.flush()
    refresh_skill_states(db, submission.profile_id, policy, now)
