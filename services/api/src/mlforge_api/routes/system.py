"""Health, settings, backup/restore/export, activity heartbeat and the AI mentor."""

from __future__ import annotations

import csv
import io
import re
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from .. import ai
from ..backup import backup_sqlite, inspect_backup, restore_sqlite
from ..db import get_engine
from ..deps import DB, RT, CurrentProfile
from ..domain.queries import current_exercise, iso
from ..errors import APIError
from ..models import (
    AppSetting,
    AuditEvent,
    LearningSession,
    ReviewItem,
    RunJob,
    SkillEvidence,
    SkillState,
    Submission,
    utcnow,
)
from .practice import hint_block_reason

router = APIRouter()
api = APIRouter(prefix="/api/v1")


@router.get("/health")
def health(db: DB, rt: RT) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    runner = rt.sandbox.health()
    return {
        "status": "ok" if db_ok else "degraded",
        "backend": "ok",
        "database": "ok" if db_ok else "error",
        "runner": {
            "available": runner.available,
            "reason": runner.reason,
            "image": runner.image,
            "limits": {
                "time_s": rt.sandbox.limits.total_budget_s,
                "memory_mb": rt.sandbox.limits.memory_mb,
                "cpus": rt.sandbox.limits.cpus,
                "pids": rt.sandbox.limits.pids,
            },
        },
        "ai": {"configured": rt.settings.anthropic_api_key is not None},
    }


# ------------------------------------------------------------------ settings
class SettingsPatch(BaseModel):
    ai_enabled: bool | None = None
    ai_daily_request_limit: int | None = Field(default=None, ge=0, le=1000)
    ai_daily_budget_usd: float | None = Field(default=None, ge=0, le=100)
    ai_max_context_chars: int | None = Field(default=None, ge=1000, le=100_000)
    send_code_to_ai: bool | None = None
    ai_pricing: dict[str, dict[str, Any]] | None = None


@api.get("/settings")
def get_settings_route(db: DB, rt: RT) -> dict:
    return {"settings": ai.all_settings(db), "ai": ai.status(rt.settings, db)}


@api.patch("/settings")
def patch_settings(body: SettingsPatch, db: DB, rt: RT) -> dict:
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        row = db.get(AppSetting, key) or AppSetting(key=key, value=value)
        row.value = value
        db.add(row)
    db.add(AuditEvent(event="settings_changed", details={"keys": sorted(changes)}))
    db.commit()
    return get_settings_route(db, rt)


# ----------------------------------------------------------- activity tracking
class HeartbeatIn(BaseModel):
    category: Literal["learn", "practice", "review", "other"] = "practice"
    active_seconds: int = Field(ge=0, le=120)


@api.post("/sessions/heartbeat")
def heartbeat(body: HeartbeatIn, profile: CurrentProfile, db: DB) -> dict:
    """Client reports seconds with real input activity since its last beat.

    Server caps the credit by wall-clock time since the previous beat, so a
    stuck tab cannot inflate study time.
    """
    now = utcnow()
    session = db.scalars(
        select(LearningSession)
        .where(LearningSession.profile_id == profile.id)
        .order_by(LearningSession.last_seen_at.desc())
    ).first()
    if session is None or now - session.last_seen_at > timedelta(minutes=5):
        session = LearningSession(
            profile_id=profile.id, started_at=now, last_seen_at=now, category=body.category, actual_active_seconds=0
        )
        db.add(session)
        credit = min(body.active_seconds, 60)
    else:
        credit = min(body.active_seconds, int((now - session.last_seen_at).total_seconds()) + 5)
    session.actual_active_seconds += credit
    session.last_seen_at = now
    db.commit()
    return {"session_id": session.id, "active_seconds": session.actual_active_seconds}


# ------------------------------------------------------------ backup / export
@api.post("/backup")
def create_backup(rt: RT) -> dict:
    path = backup_sqlite(rt.settings.resolved_database_url, rt.settings.data_dir / "backups")
    return {"file": path.name, "size_bytes": path.stat().st_size, "contains_secrets": False}


@api.get("/backups")
def list_backups(rt: RT) -> dict:
    folder = rt.settings.data_dir / "backups"
    files = sorted(folder.glob("*.db"), reverse=True) if folder.exists() else []
    return {"items": [{"file": f.name, "size_bytes": f.stat().st_size} for f in files]}


class RestoreIn(BaseModel):
    file: str
    confirm: str


@api.post("/restore")
def restore(body: RestoreIn, rt: RT, db: DB) -> dict:
    if body.confirm != "RESTORE":
        raise APIError(400, "confirmation_required", 'send confirm="RESTORE" to overwrite current data')
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.db", body.file):
        raise APIError(400, "invalid_backup_name", "invalid backup file name")
    path = rt.settings.data_dir / "backups" / body.file
    if not path.exists():
        raise APIError(404, "backup_not_found", "backup file not found")
    report = inspect_backup(path)
    if not report["ok"]:
        raise APIError(409, "backup_invalid", "backup failed the schema check", report)
    db.close()
    safety = backup_sqlite(rt.settings.resolved_database_url, rt.settings.data_dir / "backups", label="pre-restore")
    restore_sqlite(rt.settings.resolved_database_url, path)
    get_engine().dispose()
    db.add(AuditEvent(event="restore", details={"file": body.file, "safety_backup": safety.name}))
    db.commit()
    return {"restored": body.file, "safety_backup": safety.name, "check": report}


@api.get("/export/progress")
def export_progress(profile: CurrentProfile, db: DB, format: Literal["json", "csv"] = "json"):
    subs = list(
        db.scalars(select(Submission).where(Submission.profile_id == profile.id).order_by(Submission.submitted_at))
    )
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "submitted_at",
                "exercise_id",
                "exercise_version",
                "kind",
                "mode",
                "hint_level",
                "job_status",
                "passed",
                "total",
                "score",
                "error_type",
            ]
        )
        for s in subs:
            j: RunJob | None = s.job
            w.writerow(
                [
                    iso(s.submitted_at),
                    s.exercise_id,
                    s.exercise_version,
                    s.kind,
                    s.mode,
                    s.hint_level,
                    j.status if j else "",
                    j.passed if j else "",
                    j.total if j else "",
                    j.score if j else "",
                    j.error_type if j else "",
                ]
            )
        return Response(
            buf.getvalue(),
            media_type="text/csv",
            headers={"content-disposition": "attachment; filename=mlforge-progress.csv"},
        )
    return {
        "exported_at": iso(utcnow()),
        "profile": {"display_name": profile.display_name, "locale": profile.locale},
        "skill_states": [
            {
                "skill_id": s.skill_id,
                "state": s.state,
                "criteria": s.criteria,
                "mastered_at": iso(s.mastered_at),
                "next_review_at": iso(s.next_review_at),
            }
            for s in db.scalars(select(SkillState).where(SkillState.profile_id == profile.id))
        ],
        "evidence": [
            {
                "skill_id": e.skill_id,
                "source_type": e.source_type,
                "verification": e.verification,
                "exercise_id": e.exercise_id,
                "score": e.score,
                "hint_level": e.hint_level,
                "created_at": iso(e.created_at),
            }
            for e in db.scalars(select(SkillEvidence).where(SkillEvidence.profile_id == profile.id))
        ],
        "submissions": [
            {
                "id": s.id,
                "exercise_id": s.exercise_id,
                "exercise_version": s.exercise_version,
                "kind": s.kind,
                "mode": s.mode,
                "submitted_at": iso(s.submitted_at),
                "source_code": s.source_code,
                "job": {"status": s.job.status, "passed": s.job.passed, "total": s.job.total, "score": s.job.score}
                if s.job
                else None,
            }
            for s in subs
        ],
        "reviews": [
            {"skill_id": r.skill_id, "due_at": iso(r.due_at), "status": r.status, "last_outcome": r.last_outcome}
            for r in db.scalars(select(ReviewItem).where(ReviewItem.profile_id == profile.id))
        ],
    }


# ------------------------------------------------------------------ AI mentor
@api.get("/ai/status")
def ai_status(db: DB, rt: RT) -> dict:
    return ai.status(rt.settings, db)


class MentorIn(BaseModel):
    exercise_id: str | None = None
    lesson_id: str | None = None
    job_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


def _mentor_context(db, profile, body: MentorIn) -> tuple[str, str | None]:
    parts: list[str] = []
    exercise_id = None
    if body.exercise_id:
        ex = current_exercise(db, body.exercise_id)
        if hint_block_reason(db, profile.id, ex):
            raise APIError(403, "ai_disabled_independent", "the mentor is disabled during independent work")
        exercise_id = ex.id
        parts.append(f"Task: {ex.title}\n{ex.spec['prompt_md']}")
        if ai.get_setting(db, "send_code_to_ai"):
            draft = db.scalars(
                select(Submission)
                .where(Submission.profile_id == profile.id, Submission.exercise_id == ex.id)
                .order_by(Submission.submitted_at.desc())
            ).first()
            if draft is not None:
                parts.append(f"Learner's latest code:\n```python\n{draft.source_code}\n```")
        else:
            parts.append("(The learner has not allowed sending code to the AI.)")
    if body.job_id:
        job = db.get(RunJob, body.job_id)
        if job is not None and job.submission.profile_id == profile.id:
            lines = [f"Test run: {job.status}, passed {job.passed}/{job.total}, error {job.error_type}"]
            for r in job.results:
                if r.visibility == "public":
                    so = r.safe_output or {}
                    lines.append(
                        f"- public test {r.test_id}: {r.status}; input={so.get('input')!r}; "
                        f"expected={so.get('expected')!r}; actual={so.get('actual')!r}"
                    )
                else:
                    lines.append(f"- hidden test: {r.status}" + (f" ({r.error_type})" if r.error_type else ""))
            parts.append("\n".join(lines))
    return "\n\n".join(parts) or "(no task context)", exercise_id


@api.post("/mentor/message")
def mentor_message(body: MentorIn, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    context, exercise_id = _mentor_context(db, profile, body)
    try:
        reply = ai.ask_mentor(
            rt.settings,
            db,
            purpose="hint_coach",
            profile_id=profile.id,
            locale=profile.locale,
            learner_data=context,
            question=body.message,
            lesson_id=body.lesson_id,
            exercise_id=exercise_id,
        )
    except ai.AIUnavailable as exc:
        status = (
            503
            if exc.code in ("ai_unavailable", "ai_request_failed")
            else 429
            if exc.code == "ai_budget_exceeded"
            else 422
        )
        raise APIError(status, exc.code, str(exc)) from exc
    return {
        "text": reply.text,
        "source": "ai_feedback",
        "model": reply.model,
        "usage": {
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
            "cache_read_tokens": reply.cache_read_tokens,
            "estimated_cost_usd": reply.estimated_cost,
        },
        "disclaimer": "ai_feedback_not_verified",
    }


@api.post("/mentor/explain-error")
def mentor_explain_error(body: MentorIn, profile: CurrentProfile, db: DB, rt: RT) -> dict:
    if not body.job_id:
        raise APIError(422, "job_required", "explain-error needs a job_id")
    return mentor_message(body, profile, db, rt)
