"""Validate curriculum content and load it into the database (``make seed``).

Versioning rules (spec §4.2):
* a lesson/exercise is identified by ``(id, version)``; rows are never rewritten;
* changing content without bumping ``version`` is an error;
* old versions stay in the DB so earlier attempts keep pointing at them;
* an exercise only becomes active when ``review_status == reviewed`` AND it
  passed sandbox validation (reference passes, wrong solutions fail).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from mlforge_runner import DockerSandbox, harness_digest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import AuditEvent, Exercise, ExerciseSkillLink, Lesson, Skill, SkillPrerequisite
from .loader import ContentError, Curriculum, content_hash
from .validate import validate_diagnostic, validate_exercise, validate_lesson, validate_many

log = logging.getLogger("mlforge.seed")


@dataclass
class SeedReport:
    skills: int = 0
    lessons_new: int = 0
    exercises_new: int = 0
    validated: list[str] = field(default_factory=list)
    failed: dict[str, dict] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)
    lesson_failures: dict[str, dict] = field(default_factory=dict)
    retired: list[str] = field(default_factory=list)
    runner_reason: str = ""

    @property
    def ok(self) -> bool:
        return not self.failed and not self.lesson_failures and not self.pending


def seed_content(db: Session, cur: Curriculum, sandbox: DockerSandbox | None, revalidate: bool = False) -> SeedReport:
    report = SeedReport()
    errors: list[str] = []
    health = sandbox.health(max_age_s=0) if sandbox else None
    runner_ok = bool(health and health.available)
    if not runner_ok:
        report.runner_reason = health.reason if health else "no_sandbox"

    # ---- skills + prerequisite graph (metadata; updated in place)
    for pos, s in enumerate(cur.index.skills):
        row = db.get(Skill, s.id) or Skill(id=s.id)
        row.track, row.title, row.title_en = s.track, s.title, s.title_en
        row.description, row.version, row.status, row.position = s.description, s.version, s.status, pos
        row.content_hash = content_hash(s)
        db.add(row)
        report.skills += 1
    db.flush()
    db.execute(delete(SkillPrerequisite))
    for s in cur.index.skills:
        for p in s.prerequisites:
            db.add(SkillPrerequisite(skill_id=s.id, prerequisite_skill_id=p))

    # ---- lessons
    new_lessons = []
    for lesson in cur.lessons.values():
        h = content_hash(lesson)
        existing = db.get(Lesson, (lesson.id, lesson.version))
        if existing and existing.content_hash != h:
            errors.append(f"lesson {lesson.id} v{lesson.version} changed without a version bump")
            continue
        validation = (existing.content or {}).get("validation") if existing else None
        needs_validation = (
            revalidate or not validation or not validation.get("ok") or validation.get("harness") != harness_digest()
        )
        if existing is None:
            existing = Lesson(id=lesson.id, version=lesson.version, content_hash=h)
            report.lessons_new += 1
        existing.skill_id, existing.title = lesson.skill, lesson.title
        existing.body_md, existing.estimated_minutes = lesson.explanation_md, lesson.estimated_minutes
        existing.content = {**lesson.model_dump(mode="json"), "validation": validation}
        existing.is_current = True
        db.add(existing)
        if needs_validation:
            new_lessons.append((lesson, existing))
        for old in db.scalars(select(Lesson).where(Lesson.id == lesson.id, Lesson.version != lesson.version)):
            old.is_current = False

    # ---- exercises
    to_validate: list = []
    rows: dict[str, Exercise] = {}
    for ex in cur.exercises.values():
        h = content_hash(ex)
        row = db.get(Exercise, (ex.id, ex.version))
        if row and row.content_hash != h:
            errors.append(f"exercise {ex.id} v{ex.version} changed without a version bump")
            continue
        if row is None:
            row = Exercise(id=ex.id, version=ex.version, content_hash=h, spec=ex.model_dump(mode="json"))
            report.exercises_new += 1
        row.skill_id, row.title, row.type, row.role = ex.skill, ex.title, ex.type, ex.role
        row.difficulty, row.estimated_minutes, row.position = ex.difficulty, ex.estimated_minutes, ex.position
        row.review_status, row.is_current = ex.review_status, True
        db.add(row)
        rows[ex.id] = row
        report_ok = (row.validation_report or {}).get("ok")
        stale = (row.validation_report or {}).get("harness") != harness_digest()
        if revalidate or row.validation_status != "validated" or not report_ok or stale:
            to_validate.append(ex)
        for old in db.scalars(select(Exercise).where(Exercise.id == ex.id, Exercise.version != ex.version)):
            old.is_current = False
        db.flush()
        db.execute(
            delete(ExerciseSkillLink).where(
                ExerciseSkillLink.exercise_id == ex.id, ExerciseSkillLink.exercise_version == ex.version
            )
        )
        db.add(ExerciseSkillLink(exercise_id=ex.id, exercise_version=ex.version, skill_id=ex.skill, weight=1.0))
        for extra in ex.extra_skills:
            db.add(ExerciseSkillLink(exercise_id=ex.id, exercise_version=ex.version, skill_id=extra, weight=0.5))

    # retire exercises that disappeared from content
    for row in db.scalars(select(Exercise).where(Exercise.is_current.is_(True))):
        if row.id not in cur.exercises:
            row.is_current = False
            report.retired.append(row.id)

    if errors:
        db.rollback()
        raise ContentError(errors)

    # ---- dynamic validation in the real sandbox
    if runner_ok:
        ex_reports = validate_many(to_validate, validate_exercise, sandbox)
        for ex_id, rep in ex_reports.items():
            row = rows[ex_id]
            row.validation_report = rep
            row.validation_status = "validated" if rep["ok"] else "failed"
            (report.validated.append(ex_id) if rep["ok"] else report.failed.__setitem__(ex_id, rep))
        lesson_reports = validate_many([lsn for lsn, _ in new_lessons], validate_lesson, sandbox)
        for lesson, row in new_lessons:
            rep = lesson_reports[lesson.id]
            row.content = {**row.content, "validation": rep}
            row.status = "published" if rep["ok"] else "invalid"
            if not rep["ok"]:
                report.lesson_failures[lesson.id] = rep
        if cur.diagnostic is not None:
            diag_rep = validate_diagnostic(cur.diagnostic, sandbox)
            if not diag_rep["ok"]:
                report.lesson_failures["diagnostic"] = diag_rep
    else:
        report.pending = [ex.id for ex in to_validate]

    db.add(
        AuditEvent(
            event="content_seed",
            details={
                "skills": report.skills,
                "lessons_new": report.lessons_new,
                "exercises_new": report.exercises_new,
                "validated": report.validated,
                "failed": list(report.failed),
                "pending": report.pending,
                "runner": report.runner_reason or "ok",
            },
        )
    )
    db.commit()
    return report
