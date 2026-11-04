"""Reviews, dashboard and analytics: everything here is computed from stored evidence."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from ..deps import DB, RT, CurrentProfile
from ..domain.progress import prerequisite_map, refresh_skill_states, resolve_review, topo_order
from ..domain.queries import (
    active_exercises,
    exercise_progress,
    iso,
    lesson_completed,
    lesson_for_skill,
    skill_states,
)
from ..errors import APIError, not_found
from ..models import (
    Assessment,
    LearningSession,
    ReviewItem,
    RunJob,
    Skill,
    SkillEvidence,
    Submission,
    utcnow,
)

router = APIRouter(prefix="/api/v1")

MIN_SAMPLE = 3  # below this, rates are reported as "insufficient data"


def rate(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": (numerator / denominator) if denominator else None,
        "sufficient": denominator >= MIN_SAMPLE,
    }


# -------------------------------------------------------------------- reviews
def review_out(db, r: ReviewItem) -> dict:
    skill = db.get(Skill, r.skill_id)
    return {
        "id": r.id,
        "skill_id": r.skill_id,
        "skill_title": skill.title if skill else r.skill_id,
        "due_at": iso(r.due_at),
        "interval_days": r.interval_days,
        "step": r.step,
        "status": r.status,
        "exercise_id": r.exercise_id,
        "started_at": iso(r.started_at),
        "last_outcome": r.last_outcome,
    }


@router.get("/reviews/today")
def reviews_today(profile: CurrentProfile, db: DB) -> dict:
    now = utcnow()
    pending = list(
        db.scalars(
            select(ReviewItem)
            .where(ReviewItem.profile_id == profile.id, ReviewItem.status == "pending")
            .order_by(ReviewItem.due_at)
        )
    )
    return {
        "due": [review_out(db, r) for r in pending if r.due_at <= now],
        "upcoming": [review_out(db, r) for r in pending if r.due_at > now][:10],
        "recent": [
            review_out(db, r)
            for r in db.scalars(
                select(ReviewItem)
                .where(ReviewItem.profile_id == profile.id, ReviewItem.status == "done")
                .order_by(ReviewItem.completed_at.desc())
                .limit(5)
            )
        ],
    }


@router.post("/reviews/{item_id}/start")
def start_review(item_id: int, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    """Choose the exercise to recall: the one practised least recently.

    While a review is started, hints for that exercise are disabled server-side.
    """
    item = db.get(ReviewItem, item_id)
    if item is None or item.profile_id != profile.id:
        raise not_found("review", str(item_id))
    if item.status != "pending":
        raise APIError(409, "review_done", "this review item is already completed")
    if item.exercise_id is None:
        exercises = active_exercises(db, item.skill_id, "practice")
        if not exercises:
            raise APIError(409, "no_review_exercise", "no validated exercise for this skill")
        progress = exercise_progress(db, profile.id, rt.policy.pass_threshold)
        epoch = utcnow() - timedelta(days=36500)
        choice = min(exercises, key=lambda e: progress[e.id].last_attempt_at if e.id in progress else epoch)
        item.exercise_id = choice.id
    item.started_at = item.started_at or utcnow()
    db.commit()
    return review_out(db, item)


class ReviewResultIn(BaseModel):
    submission_id: str


@router.post("/reviews/{item_id}/result")
def review_result(item_id: int, body: ReviewResultIn, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    """Idempotently resolve a review from a test-verified submission.

    Normally the grader resolves it automatically; this endpoint exists for
    explicit clients and only accepts a finished, graded review-mode submission.
    """
    item = db.get(ReviewItem, item_id)
    if item is None or item.profile_id != profile.id:
        raise not_found("review", str(item_id))
    if item.status == "done":
        return review_out(db, item)
    sub = db.get(Submission, body.submission_id)
    if sub is None or sub.profile_id != profile.id or sub.review_item_id != item.id or sub.kind != "submit":
        raise APIError(409, "invalid_review_submission", "submission does not belong to this review")
    if sub.job is None or sub.job.score is None:
        raise APIError(409, "submission_not_graded", "the submission has not been graded yet")
    resolve_review(
        db,
        item,
        passed=sub.job.score >= rt.policy.pass_threshold,
        used_hints=sub.hint_level > 0,
        submission_id=sub.id,
        policy=rt.policy,
    )
    refresh_skill_states(db, profile.id, rt.policy)
    db.commit()
    return review_out(db, item)


# ------------------------------------------------------------------ dashboard
def next_step(db, profile, rt, states) -> dict | None:
    """One clear next action (spec §6.3)."""
    due = db.scalars(
        select(ReviewItem)
        .where(ReviewItem.profile_id == profile.id, ReviewItem.status == "pending", ReviewItem.due_at <= utcnow())
        .order_by(ReviewItem.due_at)
    ).first()
    if due:
        return {"type": "review", "review_id": due.id, "skill_id": due.skill_id}
    skills = topo_order(list(db.scalars(select(Skill))), prerequisite_map(db))
    progress = exercise_progress(db, profile.id, rt.policy.pass_threshold)
    for skill in skills:
        st = states.get(skill.id)
        if st is None or st.state not in ("available", "in_progress"):
            continue
        lesson = lesson_for_skill(db, skill.id)
        if lesson and not lesson_completed(db, profile.id, lesson.id):
            return {"type": "lesson", "lesson_id": lesson.id, "skill_id": skill.id, "title": lesson.title}
        for ex in active_exercises(db, skill.id, "practice"):
            if not (progress.get(ex.id) and progress[ex.id].solved):
                return {"type": "exercise", "exercise_id": ex.id, "skill_id": skill.id, "title": ex.title}
        crit = {c["id"]: c for c in st.criteria}
        if not crit.get("no_hint_solve", {}).get("met", True):
            unsolved_clean = (
                next(
                    (e for e in active_exercises(db, skill.id, "practice") if not progress[e.id].solved_without_hints),
                    None,
                )
                if progress
                else None
            )
            if unsolved_clean:
                return {
                    "type": "exercise_no_hints",
                    "exercise_id": unsolved_clean.id,
                    "skill_id": skill.id,
                    "title": unsolved_clean.title,
                }
        if not crit.get("independent_assessment", {}).get("met", True):
            return {"type": "assessment", "skill_id": skill.id, "title": skill.title}
    return None


def today_bounds(profile):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        tz = ZoneInfo(profile.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    local_now = utcnow().astimezone(tz)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(utcnow().tzinfo)


@router.get("/dashboard")
def dashboard(profile: CurrentProfile, db: DB, rt: RT) -> dict:
    states = skill_states(db, profile.id, rt.policy)
    start = today_bounds(profile)
    active_seconds = (
        db.scalar(
            select(func.coalesce(func.sum(LearningSession.actual_active_seconds), 0)).where(
                LearningSession.profile_id == profile.id, LearningSession.last_seen_at >= start
            )
        )
        or 0
    )
    today_subs = list(
        db.scalars(
            select(Submission).where(
                Submission.profile_id == profile.id, Submission.submitted_at >= start, Submission.kind == "submit"
            )
        )
    )
    solved_today = {
        s.exercise_id
        for s in today_subs
        if s.job and s.job.score is not None and s.job.score >= rt.policy.pass_threshold
    }
    recent = list(
        db.scalars(
            select(Submission)
            .where(Submission.profile_id == profile.id)
            .order_by(Submission.submitted_at.desc())
            .limit(6)
        )
    )
    due_reviews = (
        db.scalar(
            select(func.count())
            .select_from(ReviewItem)
            .where(ReviewItem.profile_id == profile.id, ReviewItem.status == "pending", ReviewItem.due_at <= utcnow())
        )
        or 0
    )
    skills = {s.id: s for s in db.scalars(select(Skill))}
    current = next(
        (
            states[s.id]
            for s in sorted(skills.values(), key=lambda s: s.position)
            if s.id in states and states[s.id].state in ("in_progress", "available", "needs_review")
        ),
        None,
    )
    health = rt.sandbox.health()
    counts = Counter(st.state for st in states.values())
    return {
        "profile": {
            "display_name": profile.display_name,
            "daily_goal_minutes": profile.daily_goal_minutes,
            "onboarding_completed": profile.onboarding_completed_at is not None,
        },
        "today": {
            "active_minutes": int(active_seconds // 60),
            "goal_minutes": profile.daily_goal_minutes,
            "submissions": len(today_subs),
            "exercises_solved": len(solved_today),
        },
        "current_skill": {
            "id": current.skill_id,
            "title": skills[current.skill_id].title,
            "state": current.state,
            "criteria": current.criteria,
        }
        if current
        else None,
        "next_step": next_step(db, profile, rt, states),
        "reviews_due": due_reviews,
        "skill_counts": dict(counts),
        "recent_attempts": [
            {
                "submission_id": s.id,
                "exercise_id": s.exercise_id,
                "kind": s.kind,
                "mode": s.mode,
                "submitted_at": iso(s.submitted_at),
                "status": s.job.status if s.job else None,
                "passed": s.job.passed if s.job else None,
                "total": s.job.total if s.job else None,
            }
            for s in recent
        ],
        "insights": insights(db, profile, rt),
        "runner": {"available": health.available, "reason": health.reason},
    }


def insights(db, profile, rt) -> dict:
    assessments = list(
        db.scalars(
            select(Assessment).where(Assessment.profile_id == profile.id, Assessment.status.in_(("passed", "failed")))
        )
    )
    passing = list(
        db.scalars(
            select(SkillEvidence).where(
                SkillEvidence.profile_id == profile.id,
                SkillEvidence.source_type.in_(("exercise", "review")),
                SkillEvidence.score >= rt.policy.pass_threshold,
            )
        )
    )
    reviews = list(
        db.scalars(select(ReviewItem).where(ReviewItem.profile_id == profile.id, ReviewItem.status == "done"))
    )
    return {
        "independent_accuracy": rate(sum(a.status == "passed" for a in assessments), len(assessments)),
        "hint_dependency": rate(sum(e.hint_level > 0 for e in passing), len(passing)),
        "review_recall": rate(sum(r.last_outcome == "passed" for r in reviews), len(reviews)),
        "top_errors": error_classes(db, profile.id)[:5],
    }


def error_classes(db, profile_id: str) -> list[dict]:
    q = (
        select(RunJob.error_type, func.count())
        .join(Submission, Submission.id == RunJob.submission_id)
        .where(Submission.profile_id == profile_id, Submission.kind == "submit", RunJob.error_type.is_not(None))
        .group_by(RunJob.error_type)
        .order_by(func.count().desc())
    )
    return [{"error_type": et, "count": n} for et, n in db.execute(q)]


# ------------------------------------------------------------------ analytics
@router.get("/analytics/skills")
def analytics_skills(profile: CurrentProfile, db: DB, rt: RT) -> dict:
    states = skill_states(db, profile.id, rt.policy)
    skills = sorted(db.scalars(select(Skill)), key=lambda s: s.position)
    out = []
    for s in skills:
        st = states.get(s.id)
        ev = list(
            db.scalars(
                select(SkillEvidence).where(SkillEvidence.profile_id == profile.id, SkillEvidence.skill_id == s.id)
            )
        )
        by_source = Counter(e.source_type for e in ev)
        out.append(
            {
                "id": s.id,
                "title": s.title,
                "status": s.status,
                "state": st.state if st else None,
                "criteria": st.criteria if st else [],
                "mastered_at": iso(st.mastered_at) if st else None,
                "hint_dependency": st.hint_dependency if st else None,
                "failure_tags": st.failure_tags if st else {},
                "evidence": {
                    "total": len(ev),
                    "passing": sum(e.score >= rt.policy.pass_threshold for e in ev),
                    "by_source": dict(by_source),
                },
                "confirmation": confirmation_level(st),
            }
        )
    return {"skills": out, "insights": insights(db, profile, rt)}


def confirmation_level(st) -> str:
    """confirmed | partially_confirmed | insufficient_data (spec §13)."""
    if st is None or not st.criteria:
        return "insufficient_data"
    met = sum(c["met"] for c in st.criteria)
    if met == len(st.criteria):
        return "confirmed"
    return "partially_confirmed" if met else "insufficient_data"


@router.get("/analytics/errors")
def analytics_errors(profile: CurrentProfile, db: DB, rt: RT) -> dict:
    states = skill_states(db, profile.id, rt.policy)
    tags: Counter[str] = Counter()
    per_skill = []
    for sid, st in states.items():
        if st.failure_tags:
            tags.update(st.failure_tags)
            per_skill.append({"skill_id": sid, "failure_tags": st.failure_tags})
    return {
        "error_types": error_classes(db, profile.id),
        "failure_tags": dict(tags.most_common()),
        "per_skill": per_skill,
    }
