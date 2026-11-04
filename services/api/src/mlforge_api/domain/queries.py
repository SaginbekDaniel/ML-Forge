"""Read-side helpers shared by routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..content.schema import MasteryPolicy
from ..errors import APIError, not_found
from ..models import (
    Exercise,
    HintUsage,
    Lesson,
    LessonProgress,
    RunJob,
    Skill,
    SkillState,
    Submission,
)
from .progress import refresh_skill_states


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def skill_states(db: Session, profile_id: str, policy: MasteryPolicy) -> dict[str, SkillState]:
    rows = {s.skill_id: s for s in db.scalars(select(SkillState).where(SkillState.profile_id == profile_id))}
    skill_count = db.scalar(select(func.count()).select_from(Skill)) or 0
    if len(rows) < skill_count or any(r.state == "needs_review" or r.next_review_at for r in rows.values()):
        # cheap (few skills); keeps time-based states (due reviews) current
        refresh_skill_states(db, profile_id, policy)
        db.commit()
        rows = {s.skill_id: s for s in db.scalars(select(SkillState).where(SkillState.profile_id == profile_id))}
    return rows


def current_exercise(db: Session, exercise_id: str) -> Exercise:
    ex = db.scalars(select(Exercise).where(Exercise.id == exercise_id, Exercise.is_current.is_(True))).first()
    if ex is None:
        raise not_found("exercise", exercise_id)
    return ex


def require_active(ex: Exercise) -> None:
    if not ex.active:
        raise APIError(
            409,
            "exercise_inactive",
            "this exercise has not passed validation and is not active",
            {"validation_status": ex.validation_status, "review_status": ex.review_status},
        )


def lesson_for_skill(db: Session, skill_id: str) -> Lesson | None:
    return db.scalars(select(Lesson).where(Lesson.skill_id == skill_id, Lesson.is_current.is_(True))).first()


def lesson_completed(db: Session, profile_id: str, lesson_id: str) -> bool:
    return db.get(LessonProgress, (profile_id, lesson_id)) is not None


def active_exercises(db: Session, skill_id: str | None = None, role: str | None = None) -> list[Exercise]:
    q = select(Exercise).where(
        Exercise.is_current.is_(True), Exercise.review_status == "reviewed", Exercise.validation_status == "validated"
    )
    if skill_id:
        q = q.where(Exercise.skill_id == skill_id)
    if role:
        q = q.where(Exercise.role == role)
    return list(db.scalars(q.order_by(Exercise.skill_id, Exercise.position)))


@dataclass
class ExerciseProgress:
    attempts: int
    best_score: float | None
    solved: bool
    solved_without_hints: bool
    hints_used: int
    last_attempt_at: datetime | None


def exercise_progress(db: Session, profile_id: str, threshold: float) -> dict[str, ExerciseProgress]:
    """Per-exercise stats across versions, from graded *submit* attempts only."""
    q = (
        select(Submission.exercise_id, Submission.hint_level, RunJob.score, Submission.submitted_at)
        .join(RunJob, RunJob.submission_id == Submission.id)
        .where(
            Submission.profile_id == profile_id,
            Submission.kind == "submit",
            RunJob.status.in_(("completed", "timed_out", "failed")),
            RunJob.score.is_not(None),
        )
    )
    out: dict[str, ExerciseProgress] = {}
    for ex_id, hint_level, score, at in db.execute(q):
        p = out.setdefault(ex_id, ExerciseProgress(0, None, False, False, 0, None))
        p.attempts += 1
        p.best_score = score if p.best_score is None else max(p.best_score, score)
        if score >= threshold:
            p.solved = True
            if hint_level == 0:
                p.solved_without_hints = True
        p.last_attempt_at = at if p.last_attempt_at is None or at > p.last_attempt_at else p.last_attempt_at
    hints = db.execute(
        select(HintUsage.exercise_id, func.max(HintUsage.level))
        .where(HintUsage.profile_id == profile_id)
        .group_by(HintUsage.exercise_id)
    )
    for ex_id, level in hints:
        out.setdefault(ex_id, ExerciseProgress(0, None, False, False, 0, None)).hints_used = level
    return out
