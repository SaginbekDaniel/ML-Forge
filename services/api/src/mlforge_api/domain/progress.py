"""Skill state recomputation and spaced-repetition bookkeeping (DB layer)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..content.schema import MasteryPolicy
from ..models import (
    Assessment,
    ReviewItem,
    RunJob,
    Skill,
    SkillEvidence,
    SkillPrerequisite,
    SkillState,
    Submission,
    TestResult,
    utcnow,
)
from .mastery import EvidenceView, derive_state, evaluate, next_review_step

IGNORED_FAILURE_TAGS = {"edge_case", "basic"}


def topo_order(skills: list[Skill], prereqs: dict[str, list[str]]) -> list[Skill]:
    by_id = {s.id: s for s in skills}
    seen: set[str] = set()
    out: list[Skill] = []

    def visit(sid: str) -> None:
        if sid in seen or sid not in by_id:
            return
        seen.add(sid)
        for p in prereqs.get(sid, []):
            visit(p)
        out.append(by_id[sid])

    for s in sorted(skills, key=lambda s: s.position):
        visit(s.id)
    return out


def prerequisite_map(db: Session) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in db.scalars(select(SkillPrerequisite)):
        out.setdefault(row.skill_id, []).append(row.prerequisite_skill_id)
    return out


def failure_tags_for(db: Session, profile_id: str, skill_id: str) -> dict[str, int]:
    """Recurring error classes from graded submissions (deterministic, from tests)."""
    q = (
        select(RunJob.error_type, TestResult.status, TestResult.error_type, TestResult.safe_output)
        .join(Submission, Submission.id == RunJob.submission_id)
        .join(TestResult, TestResult.job_id == RunJob.id)
        .join(SkillEvidence, SkillEvidence.source_id == Submission.id)
        .where(Submission.profile_id == profile_id, SkillEvidence.skill_id == skill_id, TestResult.passed.is_(False))
    )
    counter: Counter[str] = Counter()
    for _job_err, status, err_type, safe in db.execute(q):
        if status == "runtime_error" and err_type:
            counter[err_type] += 1
        elif status in ("wrong_answer", "timeout", "compile_error", "memory_limit", "output_limit"):
            counter[status] += 1
        for tag in (safe or {}).get("tags", []):
            if tag not in IGNORED_FAILURE_TAGS:
                counter[tag] += 1
    return dict(counter.most_common(8))


def refresh_skill_states(db: Session, profile_id: str, policy: MasteryPolicy, now: datetime | None = None) -> None:
    now = now or utcnow()
    skills = list(db.scalars(select(Skill)))
    prereqs = prerequisite_map(db)
    states: dict[str, SkillState] = {
        s.skill_id: s for s in db.scalars(select(SkillState).where(SkillState.profile_id == profile_id))
    }
    seen_variant = {
        a.id: a.variant_seen for a in db.scalars(select(Assessment).where(Assessment.profile_id == profile_id))
    }
    sub_assessment = dict(
        db.execute(
            select(Submission.id, Submission.assessment_id).where(
                Submission.profile_id == profile_id, Submission.assessment_id.is_not(None)
            )
        ).all()
    )
    attempts = dict(
        db.execute(
            select(SkillEvidence.skill_id, func.count())
            .where(SkillEvidence.profile_id == profile_id)
            .group_by(SkillEvidence.skill_id)
        ).all()
    )

    resolved: dict[str, str] = {}
    for skill in topo_order(skills, prereqs):
        evidence_rows = list(
            db.scalars(
                select(SkillEvidence).where(
                    SkillEvidence.profile_id == profile_id,
                    SkillEvidence.skill_id == skill.id,
                    SkillEvidence.verification == "verified_by_tests",
                )
            )
        )
        views = [
            EvidenceView(
                exercise_id=e.exercise_id,
                source_type=e.source_type,
                score=e.score,
                hint_level=e.hint_level,
                created_at=e.created_at,
                variant_seen=bool(seen_variant.get(sub_assessment.get(e.source_id or ""), False)),
            )
            for e in evidence_rows
        ]
        ev = evaluate(views, policy)
        pending = db.scalars(
            select(ReviewItem)
            .where(ReviewItem.profile_id == profile_id, ReviewItem.skill_id == skill.id, ReviewItem.status == "pending")
            .order_by(ReviewItem.due_at)
        ).first()
        last_done = db.scalars(
            select(ReviewItem)
            .where(ReviewItem.profile_id == profile_id, ReviewItem.skill_id == skill.id, ReviewItem.status == "done")
            .order_by(ReviewItem.completed_at.desc())
        ).first()
        state_name = derive_state(
            skill_status=skill.status,
            prereq_states=[resolved.get(p, "locked") for p in prereqs.get(skill.id, [])],
            evaluation=ev,
            has_any_attempt=attempts.get(skill.id, 0) > 0,
            review_due=bool(pending and pending.due_at <= now),
            last_review_failed=bool(last_done and last_done.last_outcome == "failed"),
        )
        resolved[skill.id] = state_name
        row = states.get(skill.id) or SkillState(profile_id=profile_id, skill_id=skill.id)
        row.state = state_name
        row.mastery_score = ev.mastery_score
        row.criteria = [c.to_dict() for c in ev.criteria]
        row.hint_dependency = ev.hint_dependency
        row.last_evidence_at = max((e.created_at for e in evidence_rows), default=None)
        if ev.all_met and row.mastered_at is None:
            row.mastered_at = ev.met_at or now
            if pending is None:
                pending = schedule_review(db, profile_id, skill.id, 0, policy.review_intervals_days[0], now)
        row.next_review_at = pending.due_at if pending else None
        row.failure_tags = failure_tags_for(db, profile_id, skill.id)
        db.add(row)
    db.flush()


def schedule_review(
    db: Session, profile_id: str, skill_id: str, step: int, interval_days: int, now: datetime
) -> ReviewItem:
    item = ReviewItem(
        profile_id=profile_id,
        skill_id=skill_id,
        step=step,
        interval_days=interval_days,
        due_at=now + timedelta(days=interval_days),
        status="pending",
    )
    db.add(item)
    db.flush()
    return item


def resolve_review(
    db: Session,
    item: ReviewItem,
    *,
    passed: bool,
    used_hints: bool,
    submission_id: str,
    policy: MasteryPolicy,
    now: datetime | None = None,
) -> ReviewItem:
    """Close a review item with a test-verified outcome and schedule the next one."""
    now = now or utcnow()
    item.status = "done"
    item.last_outcome = "passed" if passed else "failed"
    item.completed_at = now
    item.submission_id = submission_id
    new_step, interval = next_review_step(item.step, passed, used_hints, policy.review_intervals_days)
    return schedule_review(db, item.profile_id, item.skill_id, new_step, interval, now)
