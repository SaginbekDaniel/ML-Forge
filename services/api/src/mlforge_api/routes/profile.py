from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..deps import DB, RT, CurrentProfile
from ..domain.queries import iso
from ..errors import APIError, not_found
from ..models import Diagnostic, DiagnosticAnswer, Profile, Skill, utcnow

router = APIRouter(prefix="/api/v1")


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    locale: Literal["ru", "en"] = "ru"
    daily_goal_minutes: int = Field(default=120, ge=15, le=600)
    days_per_week: int = Field(default=5, ge=1, le=7)
    timezone: str = Field(default="UTC", max_length=64)


class ProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    locale: Literal["ru", "en"] | None = None
    daily_goal_minutes: int | None = Field(default=None, ge=15, le=600)
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    timezone: str | None = Field(default=None, max_length=64)


def profile_out(p: Profile) -> dict:
    return {
        "id": p.id,
        "display_name": p.display_name,
        "locale": p.locale,
        "daily_goal_minutes": p.daily_goal_minutes,
        "days_per_week": p.days_per_week,
        "timezone": p.timezone,
        "onboarding_completed": p.onboarding_completed_at is not None,
        "created_at": iso(p.created_at),
    }


@router.get("/profile")
def get_profile(profile: CurrentProfile) -> dict:
    return profile_out(profile)


@router.post("/profile", status_code=201)
def create_profile(body: ProfileIn, db: DB) -> dict:
    if db.scalars(select(Profile)).first() is not None:
        raise APIError(409, "profile_exists", "a local profile already exists")
    p = Profile(**body.model_dump())
    db.add(p)
    db.commit()
    return profile_out(p)


@router.patch("/profile")
def patch_profile(body: ProfilePatch, profile: CurrentProfile, db: DB) -> dict:
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(profile, k, v)
    db.commit()
    return profile_out(profile)


# ------------------------------------------------------------------ diagnostic
def _questions_out(rt) -> list[dict]:
    diag = rt.diagnostic
    if diag is None:
        return []
    out = []
    for q in diag.questions:
        item = {"id": q.id, "type": q.type, "skill_id": q.skill, "prompt_md": q.prompt_md}
        if q.type == "predict_output":
            item["code"] = q.code
        if q.options:
            item["options"] = q.options
        out.append(item)
    return out


def _diagnostic_out(d: Diagnostic, db, rt) -> dict:
    answers = {
        a.question_id: a for a in db.scalars(select(DiagnosticAnswer).where(DiagnosticAnswer.diagnostic_id == d.id))
    }
    return {
        "id": d.id,
        "status": d.status,
        "started_at": iso(d.started_at),
        "completed_at": iso(d.completed_at),
        "questions": _questions_out(rt),
        "answers": {k: {"answer": a.answer, "correct": a.correct} for k, a in answers.items()},
        "practical_exercise_id": rt.diagnostic.practical_exercise if rt.diagnostic else None,
        "result": d.result,
    }


@router.post("/diagnostic/start", status_code=201)
def start_diagnostic(profile: CurrentProfile, db: DB, rt: RT) -> dict:
    if rt.diagnostic is None:
        raise APIError(503, "diagnostic_unavailable", "diagnostic content is not configured")
    d = db.scalars(
        select(Diagnostic).where(Diagnostic.profile_id == profile.id, Diagnostic.status == "in_progress")
    ).first()
    if d is None:
        d = Diagnostic(profile_id=profile.id)
        db.add(d)
        db.commit()
    return _diagnostic_out(d, db, rt)


@router.get("/diagnostic/{diag_id}")
def get_diagnostic(diag_id: str, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    d = db.get(Diagnostic, diag_id)
    if d is None or d.profile_id != profile.id:
        raise not_found("diagnostic", diag_id)
    return _diagnostic_out(d, db, rt)


class AnswerIn(BaseModel):
    question_id: str
    answer: str = Field(max_length=2000)


def normalize_answer(text: str) -> str:
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").strip("\n").split("\n")]
    return "\n".join(lines).strip()


@router.post("/diagnostic/{diag_id}/answer")
def answer_diagnostic(diag_id: str, body: AnswerIn, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    d = db.get(Diagnostic, diag_id)
    if d is None or d.profile_id != profile.id:
        raise not_found("diagnostic", diag_id)
    if d.status != "in_progress":
        raise APIError(409, "diagnostic_completed", "this diagnostic is already completed")
    q = next((q for q in rt.diagnostic.questions if q.id == body.question_id), None)
    if q is None:
        raise not_found("question", body.question_id)
    correct = None
    if q.type == "predict_output":
        correct = normalize_answer(body.answer) == normalize_answer(q.answer or "")
    elif q.options and body.answer not in q.options:
        raise APIError(422, "invalid_option", "answer must be one of the options")
    row = db.scalars(
        select(DiagnosticAnswer).where(DiagnosticAnswer.diagnostic_id == d.id, DiagnosticAnswer.question_id == q.id)
    ).first()
    row = row or DiagnosticAnswer(diagnostic_id=d.id, question_id=q.id)
    row.answer, row.correct = body.answer, correct
    db.add(row)
    db.commit()
    # Do not reveal the right answer during the diagnostic; correctness is shown at the end.
    return {"question_id": q.id, "recorded": True}


@router.post("/diagnostic/{diag_id}/complete")
def complete_diagnostic(diag_id: str, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    """Summarise answers into per-skill recommendations.

    Self-assessment is labelled ``user_self_report`` and never unlocks or masters
    anything; predict-output answers are objectively checked but only guide where
    to start. Mastery always comes from tested exercises.
    """
    d = db.get(Diagnostic, diag_id)
    if d is None or d.profile_id != profile.id:
        raise not_found("diagnostic", diag_id)
    answers = {
        a.question_id: a for a in db.scalars(select(DiagnosticAnswer).where(DiagnosticAnswer.diagnostic_id == d.id))
    }
    per_skill: dict[str, dict] = {}
    for q in rt.diagnostic.questions:
        s = per_skill.setdefault(q.skill, {"self_report": None, "checks_correct": 0, "checks_total": 0})
        a = answers.get(q.id)
        if q.type == "self_assessment":
            s["self_report"] = a.answer if a else None
        else:
            s["checks_total"] += 1
            if a and a.correct:
                s["checks_correct"] += 1
    skills = {s.id: s for s in db.scalars(select(Skill))}
    recs = []
    for sid, s in per_skill.items():
        confident = s["self_report"] in ("confident",)
        all_checks = s["checks_total"] > 0 and s["checks_correct"] == s["checks_total"]
        recommendation = "try_assessment_early" if confident and all_checks else "start_with_lesson"
        recs.append(
            {
                "skill_id": sid,
                "skill_title": skills[sid].title if sid in skills else sid,
                "recommendation": recommendation,
                **s,
                "verification": {"self_report": "user_self_report", "checks": "verified_deterministically"},
            }
        )
    order = {s.id: s.position for s in skills.values()}
    recs.sort(key=lambda r: order.get(r["skill_id"], 0))
    start = next(
        (r["skill_id"] for r in recs if r["recommendation"] == "start_with_lesson"),
        recs[0]["skill_id"] if recs else None,
    )
    d.result = {
        "skills": recs,
        "recommended_start_skill": start,
        "answer_key": {q.id: q.answer for q in rt.diagnostic.questions if q.type == "predict_output"},
    }
    d.status, d.completed_at = "completed", utcnow()
    if profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = utcnow()
    db.commit()
    return _diagnostic_out(d, db, rt)


@router.post("/onboarding/skip")
def skip_onboarding(profile: CurrentProfile, db: DB) -> dict:
    if profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = utcnow()
        db.commit()
    return profile_out(profile)
