"""Exercises, drafts, hints, submissions, jobs and independent assessments."""

from __future__ import annotations

import hashlib
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..deps import DB, RT, CurrentProfile
from ..domain.grading_service import RUN_TEST_ID, max_hint_level
from ..domain.queries import (
    active_exercises,
    current_exercise,
    exercise_progress,
    iso,
    lesson_for_skill,
    require_active,
    skill_states,
)
from ..errors import APIError, not_found
from ..models import (
    Assessment,
    Draft,
    Exercise,
    HintUsage,
    ReviewItem,
    RunJob,
    Skill,
    Submission,
    utcnow,
)

router = APIRouter(prefix="/api/v1")

MAX_SOURCE_BYTES = 64 * 1024
UNLOCKED = {"available", "in_progress", "mastered", "needs_review"}


# -------------------------------------------------------------- access rules
def active_assessment_for(db, profile_id: str, exercise_id: str) -> Assessment | None:
    return db.scalars(
        select(Assessment).where(
            Assessment.profile_id == profile_id, Assessment.exercise_id == exercise_id, Assessment.status == "active"
        )
    ).first()


def started_review_for(db, profile_id: str, exercise_id: str) -> ReviewItem | None:
    return db.scalars(
        select(ReviewItem).where(
            ReviewItem.profile_id == profile_id,
            ReviewItem.exercise_id == exercise_id,
            ReviewItem.status == "pending",
            ReviewItem.started_at.is_not(None),
        )
    ).first()


def check_view_access(db, profile_id: str, ex: Exercise) -> None:
    """Assessment variants stay unseen until an assessment for them is started."""
    if ex.role == "assessment":
        seen = db.scalars(
            select(Assessment).where(Assessment.profile_id == profile_id, Assessment.exercise_id == ex.id)
        ).first()
        if seen is None:
            raise APIError(
                403, "assessment_not_started", "independent-assessment tasks open only through an assessment"
            )


def lock_info(state: str) -> dict | None:
    if state in UNLOCKED:
        return None
    return {"reason": "skill_locked" if state == "locked" else "skill_planned"}


def hint_block_reason(db, profile_id: str, ex: Exercise) -> str | None:
    if ex.role in ("assessment", "diagnostic"):
        return "hints_disabled_independent"
    if started_review_for(db, profile_id, ex.id):
        return "hints_disabled_review"
    return None


# ------------------------------------------------------------------ exercise
def public_test(t: dict) -> dict:
    out = {"id": t["id"], "kind": t["kind"], "description": t.get("description", ""), "tags": t.get("tags", [])}
    if t["kind"] == "call":
        out["call"] = t["call"]
        out["expected"] = f"raises {t['raises']}" if t.get("raises") else t["expected"]
    else:
        out["stdin"] = t.get("stdin") or ""
        out["expected_stdout"] = t["expected_stdout"]
    return out


def exercise_out(db, profile, ex: Exercise, rt) -> dict:
    spec = ex.spec
    states = skill_states(db, profile.id, rt.policy)
    state = states[ex.skill_id].state if ex.skill_id in states else "locked"
    revealed_level = max_hint_level(db, profile.id, ex.id, ex.version)
    draft = db.get(Draft, (profile.id, ex.id))
    skill = db.get(Skill, ex.skill_id)
    lesson = lesson_for_skill(db, ex.skill_id)
    progress = exercise_progress(db, profile.id, rt.policy.pass_threshold).get(ex.id)
    siblings = [e.id for e in active_exercises(db, ex.skill_id, "practice")]
    nxt = None
    if ex.id in siblings and siblings.index(ex.id) + 1 < len(siblings):
        nxt = siblings[siblings.index(ex.id) + 1]
    tests = spec["tests"]
    return {
        "id": ex.id,
        "version": ex.version,
        "title": ex.title,
        "type": ex.type,
        "role": ex.role,
        "difficulty": ex.difficulty,
        "estimated_minutes": ex.estimated_minutes,
        "skill_id": ex.skill_id,
        "skill_title": skill.title if skill else ex.skill_id,
        "skill_state": state,
        "lesson_id": lesson.id if lesson else None,
        "active": ex.active,
        "lock": lock_info(state) if ex.role != "diagnostic" else None,
        "execution_mode": spec.get("execution_mode", "function"),
        "prompt_md": spec["prompt_md"],
        "starter_code": spec["starter_code"],
        "public_examples": spec.get("public_examples", []),
        "public_tests": [public_test(t) for t in tests if t.get("visibility") == "public"],
        "hidden_tests_count": sum(1 for t in tests if t.get("visibility") == "hidden"),
        "hints_total": len(spec["hints"]),
        "hints_revealed": [{"level": i + 1, "text": spec["hints"][i]} for i in range(revealed_level)],
        "hints_blocked": hint_block_reason(db, profile.id, ex),
        "explain_prompt": spec.get("explain_prompt"),
        "draft": {"code": draft.code, "updated_at": iso(draft.updated_at)} if draft else None,
        "progress": {
            "attempts": progress.attempts,
            "best_score": progress.best_score,
            "solved": progress.solved,
            "solved_without_hints": progress.solved_without_hints,
        }
        if progress
        else {"attempts": 0, "best_score": None, "solved": False, "solved_without_hints": False},
        "next_exercise_id": nxt,
        "source": spec.get("source"),
        "license": spec.get("license"),
    }


@router.get("/exercises")
def list_exercises(profile: CurrentProfile, db: DB, rt: RT, skill_id: str | None = None) -> dict:
    progress = exercise_progress(db, profile.id, rt.policy.pass_threshold)
    return {
        "items": [
            {
                "id": e.id,
                "title": e.title,
                "skill_id": e.skill_id,
                "difficulty": e.difficulty,
                "type": e.type,
                "solved": bool(progress.get(e.id) and progress[e.id].solved),
            }
            for e in active_exercises(db, skill_id, "practice")
        ]
    }


@router.get("/exercises/{exercise_id}")
def get_exercise(exercise_id: str, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    ex = current_exercise(db, exercise_id)
    check_view_access(db, profile.id, ex)
    return exercise_out(db, profile, ex, rt)


class DraftIn(BaseModel):
    code: str = Field(max_length=MAX_SOURCE_BYTES)


@router.put("/exercises/{exercise_id}/draft")
def save_draft(exercise_id: str, body: DraftIn, profile: CurrentProfile, db: DB) -> dict:
    ex = current_exercise(db, exercise_id)
    check_view_access(db, profile.id, ex)
    draft = db.get(Draft, (profile.id, ex.id)) or Draft(profile_id=profile.id, exercise_id=ex.id, code="")
    draft.code = body.code
    draft.updated_at = utcnow()
    db.add(draft)
    db.commit()
    return {"exercise_id": ex.id, "updated_at": iso(draft.updated_at)}


class HintIn(BaseModel):
    level: int = Field(ge=1, le=3)


@router.post("/exercises/{exercise_id}/hint")
def reveal_hint(exercise_id: str, body: HintIn, profile: CurrentProfile, db: DB) -> dict:
    """Progressive hints: direction -> algorithm -> partial pseudocode.

    Server-enforced: no hints for assessment/diagnostic variants or a started
    review; levels must be revealed in order; usage lowers evidence quality.
    """
    ex = current_exercise(db, exercise_id)
    check_view_access(db, profile.id, ex)
    reason = hint_block_reason(db, profile.id, ex)
    if reason:
        raise APIError(403, reason, "hints are disabled in independent mode")
    hints = ex.spec["hints"]
    revealed = max_hint_level(db, profile.id, ex.id, ex.version)
    if body.level > revealed + 1:
        raise APIError(409, "hint_out_of_order", "reveal earlier hints first", {"next_level": revealed + 1})
    if body.level > len(hints):
        raise not_found("hint", str(body.level))
    if body.level == revealed + 1:
        db.add(HintUsage(profile_id=profile.id, exercise_id=ex.id, exercise_version=ex.version, level=body.level))
        db.commit()
    return {"level": body.level, "text": hints[body.level - 1], "total": len(hints)}


@router.get("/exercises/{exercise_id}/attempts")
def list_attempts(exercise_id: str, profile: CurrentProfile, db: DB) -> dict:
    rows = db.scalars(
        select(Submission)
        .where(Submission.profile_id == profile.id, Submission.exercise_id == exercise_id)
        .order_by(Submission.submitted_at.desc())
        .limit(50)
    )
    return {"items": [submission_out(s) for s in rows]}


# --------------------------------------------------------------- submissions
class SubmissionIn(BaseModel):
    exercise_id: str
    exercise_version: int
    source_code: str
    kind: Literal["run", "submit"] = "submit"
    mode: Literal["practice", "independent", "review", "diagnostic"] = "practice"
    client_request_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    assessment_id: str | None = None
    review_item_id: int | None = None
    stdin: str | None = Field(default=None, max_length=8192)
    explanation: str | None = Field(default=None, max_length=4000)


def job_summary(job: RunJob | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "status": job.status,
        "exit_reason": job.exit_reason,
        "passed": job.passed,
        "total": job.total,
        "score": job.score,
        "error_type": job.error_type,
        "edge_cases_passed": job.edge_cases_passed,
        "edge_cases_total": job.edge_cases_total,
        "duration_ms": job.duration_ms,
        "max_test_ms": job.max_test_ms,
    }


def submission_out(s: Submission, include_code: bool = False) -> dict:
    out = {
        "id": s.id,
        "exercise_id": s.exercise_id,
        "exercise_version": s.exercise_version,
        "kind": s.kind,
        "mode": s.mode,
        "hint_level": s.hint_level,
        "submitted_at": iso(s.submitted_at),
        "code_hash": s.code_hash,
        "job": job_summary(s.job),
    }
    if include_code:
        out["source_code"] = s.source_code
        out["explanation"] = s.explanation
    return out


def _validate_mode(db, profile, ex: Exercise, body: SubmissionIn, rt) -> tuple[str | None, int | None]:
    states = skill_states(db, profile.id, rt.policy)
    state = states[ex.skill_id].state if ex.skill_id in states else "locked"
    if body.mode == "diagnostic":
        if ex.role != "diagnostic":
            raise APIError(409, "mode_not_allowed", "diagnostic mode is only for the diagnostic task")
        return None, None
    if ex.role == "diagnostic":
        raise APIError(409, "mode_not_allowed", "the diagnostic task only accepts diagnostic mode")
    if state not in UNLOCKED:
        raise APIError(409, "skill_locked", "master the prerequisite skills first", {"skill_id": ex.skill_id})
    if body.mode == "practice":
        if ex.role != "practice":
            raise APIError(409, "mode_not_allowed", "assessment variants require independent mode")
        return None, None
    if body.mode == "independent":
        a = db.get(Assessment, body.assessment_id) if body.assessment_id else None
        if a is None or a.profile_id != profile.id or a.exercise_id != ex.id or a.status != "active":
            raise APIError(409, "assessment_not_active", "start an independent assessment first")
        return a.id, None
    # review
    item = db.get(ReviewItem, body.review_item_id) if body.review_item_id else None
    if item is None or item.profile_id != profile.id or item.status != "pending" or item.exercise_id != ex.id:
        raise APIError(409, "review_not_active", "start the review item first")
    return None, item.id


@router.post("/submissions", status_code=202)
def create_submission(body: SubmissionIn, response: Response, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    if body.client_request_id:
        existing = db.scalars(
            select(Submission).where(
                Submission.profile_id == profile.id, Submission.client_request_id == body.client_request_id
            )
        ).first()
        if existing is not None:  # double click / retry: same attempt, no new job
            response.status_code = 200
            return {
                "submission_id": existing.id,
                "job_id": existing.job.id,
                "status": existing.job.status,
                "duplicate": True,
            }
    if len(body.source_code.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise APIError(413, "source_too_large", "source code exceeds 64 KB")
    ex = db.get(Exercise, (body.exercise_id, body.exercise_version))
    if ex is None:
        raise APIError(404, "exercise_version_not_found", "this exercise version does not exist")
    if not ex.is_current:
        raise APIError(
            409,
            "exercise_version_outdated",
            "the exercise was updated; reload to get the new version",
            {"current": True},
        )
    require_active(ex)
    check_view_access(db, profile.id, ex)
    assessment_id, review_item_id = _validate_mode(db, profile, ex, body, rt)

    health = rt.sandbox.health()
    if not health.available:
        raise APIError(503, "runner_unavailable", "the code runner is unavailable", {"reason": health.reason})

    hint_level = max_hint_level(db, profile.id, ex.id, ex.version) if body.mode == "practice" else 0
    sub = Submission(
        profile_id=profile.id,
        exercise_id=ex.id,
        exercise_version=ex.version,
        kind=body.kind,
        mode=body.mode,
        code_hash=hashlib.sha256(body.source_code.encode("utf-8")).hexdigest(),
        source_code=body.source_code,
        client_request_id=body.client_request_id,
        assessment_id=assessment_id,
        review_item_id=review_item_id,
        hint_level=hint_level,
        explanation=body.explanation,
        run_stdin=body.stdin if body.kind == "run" else None,
    )
    db.add(sub)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise APIError(409, "duplicate_request", "duplicate client_request_id") from exc
    job = RunJob(submission_id=sub.id, status="queued")
    db.add(job)
    draft = db.get(Draft, (profile.id, ex.id)) or Draft(profile_id=profile.id, exercise_id=ex.id, code="")
    draft.code, draft.updated_at = body.source_code, utcnow()
    db.add(draft)
    db.commit()
    if rt.worker is not None:
        rt.worker.notify()
    return {"submission_id": sub.id, "job_id": job.id, "status": job.status, "duplicate": False}


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: str, profile: CurrentProfile, db: DB) -> dict:
    s = db.get(Submission, submission_id)
    if s is None or s.profile_id != profile.id:
        raise not_found("submission", submission_id)
    return submission_out(s, include_code=True)


# ----------------------------------------------------------------------- jobs
def _job_for(db, profile, job_id: str) -> RunJob:
    job = db.get(RunJob, job_id)
    if job is None or job.submission.profile_id != profile.id:
        raise not_found("job", job_id)
    return job


@router.get("/jobs/{job_id}")
def get_job(job_id: str, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    job = _job_for(db, profile, job_id)
    sub = job.submission
    out = job_summary(job) | {
        "submission_id": sub.id,
        "exercise_id": sub.exercise_id,
        "kind": sub.kind,
        "mode": sub.mode,
        "created_at": iso(job.created_at),
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
        "memory_limit_mb": job.memory_limit_mb,
        "time_budget_s": rt.sandbox.limits.total_budget_s,
        "results": [],
        "run_output": None,
    }
    for r in job.results:
        item = {
            "test_id": r.test_id,
            "visibility": r.visibility,
            "passed": r.passed,
            "status": r.status,
            "error_type": r.error_type,
            "duration_ms": r.duration_ms,
            **(r.safe_output or {}),
        }
        if r.test_id == RUN_TEST_ID:
            out["run_output"] = item
        else:
            out["results"].append(item)
    if job.status in ("completed", "timed_out", "failed") and sub.kind == "submit":
        ex = db.get(Exercise, (sub.exercise_id, sub.exercise_version))
        states = skill_states(db, profile.id, rt.policy)
        st = states.get(ex.skill_id) if ex else None
        out["skill"] = (
            {"id": ex.skill_id, "state": st.state if st else None, "criteria": st.criteria if st else []}
            if ex
            else None
        )
        out["counts_as_evidence"] = job.score is not None and job.score >= rt.policy.pass_threshold
    return out


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    job = _job_for(db, profile, job_id)
    if job.status == "queued":
        job.status, job.exit_reason, job.finished_at = "cancelled", "cancelled", utcnow()
        db.commit()
    elif job.status == "running":
        job.cancel_requested = True
        db.commit()
        if rt.worker is not None:
            rt.worker.cancel(job.id)
    return {"id": job.id, "status": job.status, "cancel_requested": job.cancel_requested}


# --------------------------------------------------------------- assessments
class AssessmentIn(BaseModel):
    skill_id: str


def assessment_out(a: Assessment) -> dict:
    return {
        "id": a.id,
        "skill_id": a.skill_id,
        "exercise_id": a.exercise_id,
        "exercise_version": a.exercise_version,
        "variant_seen": a.variant_seen,
        "status": a.status,
        "started_at": iso(a.started_at),
        "finished_at": iso(a.finished_at),
        "submission_id": a.submission_id,
    }


@router.post("/assessments", status_code=201)
def start_assessment(body: AssessmentIn, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    """Pick an assessment variant the learner has never opened (if any remain)."""
    skill = db.get(Skill, body.skill_id)
    if skill is None:
        raise not_found("skill", body.skill_id)
    states = skill_states(db, profile.id, rt.policy)
    if body.skill_id not in states or states[body.skill_id].state not in UNLOCKED:
        raise APIError(409, "skill_locked", "master the prerequisite skills first")
    active = db.scalars(
        select(Assessment).where(
            Assessment.profile_id == profile.id, Assessment.skill_id == skill.id, Assessment.status == "active"
        )
    ).first()
    if active is not None:
        return assessment_out(active)
    variants = active_exercises(db, skill.id, "assessment")
    if not variants:
        raise APIError(409, "no_assessment_variant", "this skill has no validated assessment variant yet")
    history = list(
        db.scalars(
            select(Assessment)
            .where(Assessment.profile_id == profile.id, Assessment.skill_id == skill.id)
            .order_by(Assessment.started_at)
        )
    )
    seen = {a.exercise_id for a in history}
    unseen = [v for v in variants if v.id not in seen]
    if unseen:
        choice, variant_seen = unseen[0], False
    else:
        last_used = {a.exercise_id: a.started_at for a in history}
        choice, variant_seen = min(variants, key=lambda v: last_used.get(v.id)), True
    a = Assessment(
        profile_id=profile.id,
        skill_id=skill.id,
        exercise_id=choice.id,
        exercise_version=choice.version,
        variant_seen=variant_seen,
    )
    db.add(a)
    db.commit()
    return assessment_out(a)


@router.get("/assessments/{assessment_id}")
def get_assessment(assessment_id: str, profile: CurrentProfile, db: DB) -> dict:
    a = db.get(Assessment, assessment_id)
    if a is None or a.profile_id != profile.id:
        raise not_found("assessment", assessment_id)
    return assessment_out(a)


@router.post("/assessments/{assessment_id}/abandon")
def abandon_assessment(assessment_id: str, profile: CurrentProfile, db: DB) -> dict:
    a = db.get(Assessment, assessment_id)
    if a is None or a.profile_id != profile.id:
        raise not_found("assessment", assessment_id)
    if a.status == "active":
        a.status, a.finished_at = "abandoned", utcnow()
        db.commit()
    return assessment_out(a)
