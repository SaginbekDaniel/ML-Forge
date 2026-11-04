from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..deps import DB, RT, CurrentProfile
from ..domain.progress import prerequisite_map
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
    Lesson,
    LessonProgress,
    ReviewItem,
    Skill,
    SkillEvidence,
    utcnow,
)
from .profile import normalize_answer

router = APIRouter(prefix="/api/v1")

TRACK_TITLES = {
    "engineering_basics": ("Engineering basics", "Engineering basics"),
    "python_core": ("Python Core", "Python Core"),
}


def skill_summary(skill: Skill, state, prereqs: list[str], db, profile_id: str, progress) -> dict:
    lesson = lesson_for_skill(db, skill.id)
    exs = active_exercises(db, skill.id, "practice")
    return {
        "id": skill.id,
        "track": skill.track,
        "title": skill.title,
        "title_en": skill.title_en,
        "description": skill.description,
        "status": skill.status,
        "state": state.state if state else ("planned" if skill.status != "active" else "locked"),
        "mastery_score": state.mastery_score if state else 0.0,
        "criteria": state.criteria if state else [],
        "mastered_at": iso(state.mastered_at) if state else None,
        "next_review_at": iso(state.next_review_at) if state else None,
        "prerequisites": prereqs,
        "lesson_id": lesson.id if lesson else None,
        "lesson_completed": lesson_completed(db, profile_id, lesson.id) if lesson else False,
        "exercises_total": len(exs),
        "exercises_solved": sum(1 for e in exs if progress.get(e.id) and progress[e.id].solved),
    }


@router.get("/roadmap")
def roadmap(profile: CurrentProfile, db: DB, rt: RT) -> dict:
    states = skill_states(db, profile.id, rt.policy)
    prereqs = prerequisite_map(db)
    progress = exercise_progress(db, profile.id, rt.policy.pass_threshold)
    skills = list(db.scalars(select(Skill).order_by(Skill.position)))
    tracks: dict[str, dict] = {}
    for s in skills:
        t = tracks.setdefault(s.track, {"id": s.track, "skills": []})
        t["skills"].append(skill_summary(s, states.get(s.id), prereqs.get(s.id, []), db, profile.id, progress))
    return {"tracks": list(tracks.values()), "policy": rt.policy.model_dump()}


@router.get("/skills/{skill_id}")
def skill_detail(skill_id: str, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise not_found("skill", skill_id)
    states = skill_states(db, profile.id, rt.policy)
    prereqs = prerequisite_map(db)
    progress = exercise_progress(db, profile.id, rt.policy.pass_threshold)
    out = skill_summary(skill, states.get(skill_id), prereqs.get(skill_id, []), db, profile.id, progress)
    state = states.get(skill_id)
    out["hint_dependency"] = state.hint_dependency if state else None
    out["failure_tags"] = state.failure_tags if state else {}
    out["prerequisite_details"] = [
        {"id": p, "title": db.get(Skill, p).title, "state": states[p].state if p in states else "locked"}
        for p in prereqs.get(skill_id, [])
    ]
    out["exercises"] = [
        {
            "id": e.id,
            "title": e.title,
            "type": e.type,
            "difficulty": e.difficulty,
            "estimated_minutes": e.estimated_minutes,
            "attempts": progress[e.id].attempts if e.id in progress else 0,
            "best_score": progress[e.id].best_score if e.id in progress else None,
            "solved": bool(progress.get(e.id) and progress[e.id].solved),
            "solved_without_hints": bool(progress.get(e.id) and progress[e.id].solved_without_hints),
            "hints_used": progress[e.id].hints_used if e.id in progress else 0,
        }
        for e in active_exercises(db, skill_id, "practice")
    ]
    out["assessment_variants"] = len(active_exercises(db, skill_id, "assessment"))
    out["assessments"] = [
        {
            "id": a.id,
            "status": a.status,
            "exercise_id": a.exercise_id,
            "variant_seen": a.variant_seen,
            "started_at": iso(a.started_at),
            "finished_at": iso(a.finished_at),
        }
        for a in db.scalars(
            select(Assessment)
            .where(Assessment.profile_id == profile.id, Assessment.skill_id == skill_id)
            .order_by(Assessment.started_at.desc())
        )
    ]
    out["evidence"] = [
        {
            "id": e.id,
            "source_type": e.source_type,
            "verification": e.verification,
            "exercise_id": e.exercise_id,
            "score": e.score,
            "hint_level": e.hint_level,
            "created_at": iso(e.created_at),
            "counts": e.score >= rt.policy.pass_threshold,
        }
        for e in db.scalars(
            select(SkillEvidence)
            .where(SkillEvidence.profile_id == profile.id, SkillEvidence.skill_id == skill_id)
            .order_by(SkillEvidence.created_at.desc())
            .limit(50)
        )
    ]
    out["reviews"] = [
        {
            "id": r.id,
            "status": r.status,
            "due_at": iso(r.due_at),
            "interval_days": r.interval_days,
            "last_outcome": r.last_outcome,
            "completed_at": iso(r.completed_at),
        }
        for r in db.scalars(
            select(ReviewItem)
            .where(ReviewItem.profile_id == profile.id, ReviewItem.skill_id == skill_id)
            .order_by(ReviewItem.due_at.desc())
            .limit(10)
        )
    ]
    return out


# --------------------------------------------------------------------- lessons
def _current_lesson(db, lesson_id: str) -> Lesson:
    lesson = db.scalars(select(Lesson).where(Lesson.id == lesson_id, Lesson.is_current.is_(True))).first()
    if lesson is None:
        raise not_found("lesson", lesson_id)
    return lesson


@router.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: str, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    lesson = _current_lesson(db, lesson_id)
    content = dict(lesson.content)
    validation = content.pop("validation", None)
    # never ship check-question answers before the learner answers
    content["check_questions"] = [
        {k: v for k, v in q.items() if k not in ("answer", "explanation_md")} for q in content["check_questions"]
    ]
    states = skill_states(db, profile.id, rt.policy)
    skill = db.get(Skill, lesson.skill_id)
    progress = exercise_progress(db, profile.id, rt.policy.pass_threshold)
    return {
        "id": lesson.id,
        "version": lesson.version,
        "skill_id": lesson.skill_id,
        "skill_title": skill.title,
        "skill_state": states[lesson.skill_id].state if lesson.skill_id in states else "locked",
        "title": lesson.title,
        "estimated_minutes": lesson.estimated_minutes,
        "content": content,
        "examples_verified": bool(validation and validation.get("ok")),
        "completed": lesson_completed(db, profile.id, lesson.id),
        "exercises": [
            {
                "id": e.id,
                "title": e.title,
                "difficulty": e.difficulty,
                "type": e.type,
                "solved": bool(progress.get(e.id) and progress[e.id].solved),
            }
            for e in active_exercises(db, lesson.skill_id, "practice")
        ],
    }


@router.post("/lessons/{lesson_id}/complete")
def complete_lesson(lesson_id: str, profile: CurrentProfile, db: DB) -> dict:
    """Marks the lesson as read. Reading is NOT mastery; no evidence is created."""
    lesson = _current_lesson(db, lesson_id)
    row = db.get(LessonProgress, (profile.id, lesson.id))
    if row is None:
        db.add(
            LessonProgress(
                profile_id=profile.id, lesson_id=lesson.id, lesson_version=lesson.version, completed_at=utcnow()
            )
        )
        db.commit()
    return {"lesson_id": lesson.id, "completed": True}


class CheckIn(BaseModel):
    question_id: str
    answer: str = Field(max_length=2000)


@router.post("/lessons/{lesson_id}/check")
def check_question(lesson_id: str, body: CheckIn, profile: CurrentProfile, db: DB) -> dict:
    lesson = _current_lesson(db, lesson_id)
    q = next((q for q in lesson.content["check_questions"] if q["id"] == body.question_id), None)
    if q is None:
        raise not_found("question", body.question_id)
    if not body.answer.strip():
        raise APIError(422, "empty_answer", "type what you think the program prints")
    correct = normalize_answer(body.answer) == normalize_answer(q["answer"])
    return {"question_id": q["id"], "correct": correct, "expected": q["answer"], "explanation_md": q["explanation_md"]}
