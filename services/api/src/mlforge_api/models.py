"""SQLAlchemy models (spec §8). Content versions and attempts are append-only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


class UTCDateTime(TypeDecorator):
    """Stores naive UTC, always returns timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


# --------------------------------------------------------------------- profile
class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(String(80))
    locale: Mapped[str] = mapped_column(String(8), default="ru")
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=120)
    days_per_week: Mapped[int] = mapped_column(Integer, default=5)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


# ------------------------------------------------------------------ curriculum
class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    track: Mapped[str] = mapped_column(String(40))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("skills.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    title_en: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | planned
    position: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), default="")


class SkillPrerequisite(Base):
    __tablename__ = "skill_prerequisites"
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    prerequisite_skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    body_md: Mapped[str] = mapped_column(Text)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=20)
    status: Mapped[str] = mapped_column(String(16), default="published")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    lesson_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    lesson_version: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Exercise(Base):
    """One immutable version of an exercise. ``spec`` holds hidden tests and the
    reference solution; it is never serialised to the browser as-is."""

    __tablename__ = "exercises"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"))
    title: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(24))  # write_code | debug | refactor
    role: Mapped[str] = mapped_column(String(16), default="practice")  # practice | assessment | diagnostic
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=10)
    position: Mapped[int] = mapped_column(Integer, default=0)
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(16), default="draft")
    validation_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|validated|failed
    validation_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (Index("ix_exercises_current_skill", "is_current", "skill_id"),)

    @property
    def active(self) -> bool:
        return self.is_current and self.review_status == "reviewed" and self.validation_status == "validated"


class ExerciseSkillLink(Base):
    __tablename__ = "exercise_skill_links"
    exercise_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    exercise_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    __table_args__ = (
        ForeignKeyConstraint(
            ["exercise_id", "exercise_version"], ["exercises.id", "exercises.version"], ondelete="CASCADE"
        ),
    )


# ----------------------------------------------------------------- attempting
class Draft(Base):
    __tablename__ = "drafts"
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    code: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class HintUsage(Base):
    __tablename__ = "hint_usages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    exercise_id: Mapped[str] = mapped_column(String(80))
    exercise_version: Mapped[int] = mapped_column(Integer)
    level: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("profile_id", "exercise_id", "exercise_version", "level", name="uq_hint_usage"),
        Index("ix_hint_usages_profile_exercise", "profile_id", "exercise_id"),
    )


class Assessment(Base):
    """An independent-assessment attempt on a (preferably) unseen variant."""

    __tablename__ = "assessments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"))
    exercise_id: Mapped[str] = mapped_column(String(80))
    exercise_version: Mapped[int] = mapped_column(Integer)
    variant_seen: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active|passed|failed|abandoned
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    submission_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[str] = mapped_column(String(80), index=True)
    exercise_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(8))  # run | submit
    mode: Mapped[str] = mapped_column(String(16))  # practice | independent | review | diagnostic
    code_hash: Mapped[str] = mapped_column(String(64))
    source_code: Mapped[str] = mapped_column(Text)
    client_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assessment_id: Mapped[str | None] = mapped_column(ForeignKey("assessments.id"), nullable=True)
    review_item_id: Mapped[int | None] = mapped_column(ForeignKey("review_items.id"), nullable=True)
    hint_level: Mapped[int] = mapped_column(Integer, default=0)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_stdin: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    job: Mapped[RunJob | None] = relationship(back_populates="submission", uselist=False)

    __table_args__ = (
        UniqueConstraint("profile_id", "client_request_id", name="uq_submission_idempotency"),
        ForeignKeyConstraint(["exercise_id", "exercise_version"], ["exercises.id", "exercises.version"]),
    )


class RunJob(Base):
    __tablename__ = "run_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    # queued | running | completed | failed | timed_out | cancelled
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    passed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edge_cases_passed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edge_cases_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    max_test_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_limit_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)

    submission: Mapped[Submission] = relationship(back_populates="job")
    results: Mapped[list[TestResult]] = relationship(
        back_populates="job", order_by="TestResult.position", cascade="all, delete-orphan"
    )


class TestResult(Base):
    __tablename__ = "test_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("run_jobs.id", ondelete="CASCADE"), index=True)
    test_id: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer)
    visibility: Mapped[str] = mapped_column(String(8))
    passed: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20))
    error_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Already redacted for hidden tests at write time.
    safe_output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    job: Mapped[RunJob] = relationship(back_populates="results")


# -------------------------------------------------------------------- mastery
class SkillEvidence(Base):
    __tablename__ = "skill_evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"))
    source_type: Mapped[str] = mapped_column(String(20))  # exercise | assessment | review | diagnostic
    verification: Mapped[str] = mapped_column(String(24))  # verified_by_tests | user_self_report | ai_feedback
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exercise_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    score: Mapped[float] = mapped_column(Float)
    hint_level: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    __table_args__ = (Index("ix_skill_evidence_profile_skill", "profile_id", "skill_id"),)


class SkillState(Base):
    __tablename__ = "skill_states"
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(16))
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0)
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    mastered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_evidence_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    next_review_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    hint_dependency: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure_tags: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ReviewItem(Base):
    __tablename__ = "review_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"))
    due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    interval_days: Mapped[int] = mapped_column(Integer)
    step: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)  # pending | done
    last_outcome: Mapped[str | None] = mapped_column(String(12), nullable=True)  # passed | failed
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    submission_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exercise_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    __table_args__ = (Index("ix_review_items_profile_due", "profile_id", "due_at"),)


# ----------------------------------------------------------------- diagnostic
class Diagnostic(Base):
    __tablename__ = "diagnostics"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="in_progress")  # in_progress | completed
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class DiagnosticAnswer(Base):
    __tablename__ = "diagnostic_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    diagnostic_id: Mapped[str] = mapped_column(ForeignKey("diagnostics.id", ondelete="CASCADE"))
    question_id: Mapped[str] = mapped_column(String(60))
    answer: Mapped[Any] = mapped_column(JSON)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("diagnostic_id", "question_id", name="uq_diagnostic_answer"),)


# ------------------------------------------------------------------ telemetry
class LearningSession(Base):
    __tablename__ = "learning_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    actual_active_seconds: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(20), default="practice")


class AIInteraction(Base):
    __tablename__ = "ai_interactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str | None] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32))
    lesson_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    exercise_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20))  # ok | error | unavailable | budget_exceeded
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
