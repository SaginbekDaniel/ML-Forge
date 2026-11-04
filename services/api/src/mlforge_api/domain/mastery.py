"""Mastery policy (spec §3.3) as pure functions over evidence.

No I/O here so the rules are trivially unit-testable. Evidence is
append-only; a skill that was mastered stays "mastered earlier" even when it
needs reinforcement now.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..content.schema import MasteryPolicy

COUNTING_SOURCES = {"exercise", "review"}
SATISFIES_PREREQ = {"mastered", "needs_review"}


@dataclass(frozen=True)
class EvidenceView:
    exercise_id: str | None
    source_type: str  # exercise | assessment | review | diagnostic
    score: float
    hint_level: int
    created_at: datetime
    variant_seen: bool = False


@dataclass(frozen=True)
class Criterion:
    id: str
    met: bool
    current: int
    required: int
    note: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "met": self.met, "current": self.current, "required": self.required, "note": self.note}


@dataclass(frozen=True)
class Evaluation:
    criteria: list[Criterion]
    all_met: bool
    mastery_score: float
    met_at: datetime | None
    hint_dependency: float | None


def evaluate(evidence: list[EvidenceView], policy: MasteryPolicy) -> Evaluation:
    thr = policy.pass_threshold
    passing = sorted(
        (e for e in evidence if e.source_type in COUNTING_SOURCES and e.score >= thr), key=lambda e: e.created_at
    )
    distinct: dict[str, datetime] = {}
    for e in passing:
        if e.exercise_id and e.exercise_id not in distinct:
            distinct[e.exercise_id] = e.created_at
    criteria = [
        Criterion(
            "distinct_exercises",
            len(distinct) >= policy.min_distinct_exercises,
            min(len(distinct), policy.min_distinct_exercises),
            policy.min_distinct_exercises,
        )
    ]
    met_times: list[datetime] = []
    if len(distinct) >= policy.min_distinct_exercises:
        met_times.append(sorted(distinct.values())[policy.min_distinct_exercises - 1])

    if policy.require_no_hint_solve:
        no_hint = [e for e in passing if e.hint_level == 0]
        criteria.append(Criterion("no_hint_solve", bool(no_hint), min(len(no_hint), 1), 1))
        if no_hint:
            met_times.append(no_hint[0].created_at)

    if policy.require_independent_assessment:
        assess = sorted(
            (e for e in evidence if e.source_type == "assessment" and e.score >= thr), key=lambda e: e.created_at
        )
        note = ""
        if assess and all(a.variant_seen for a in assess):
            note = "passed_on_previously_seen_variant"
        criteria.append(Criterion("independent_assessment", bool(assess), min(len(assess), 1), 1, note))
        if assess:
            met_times.append(assess[0].created_at)

    met = sum(c.met for c in criteria)
    all_met = met == len(criteria)
    practice_passes = [e for e in passing]
    hint_dep = (sum(e.hint_level > 0 for e in practice_passes) / len(practice_passes)) if practice_passes else None
    return Evaluation(
        criteria=criteria,
        all_met=all_met,
        mastery_score=met / len(criteria) if criteria else 0.0,
        met_at=max(met_times) if all_met and met_times else None,
        hint_dependency=hint_dep,
    )


def derive_state(
    *,
    skill_status: str,
    prereq_states: list[str],
    evaluation: Evaluation,
    has_any_attempt: bool,
    review_due: bool,
    last_review_failed: bool,
) -> str:
    """planned | locked | available | in_progress | mastered | needs_review."""
    if skill_status != "active":
        return "planned"
    if evaluation.all_met:
        return "needs_review" if (review_due or last_review_failed) else "mastered"
    if any(s not in SATISFIES_PREREQ for s in prereq_states):
        return "locked"
    return "in_progress" if has_any_attempt else "available"


def next_review_step(step: int, passed: bool, used_hints: bool, intervals: list[int]) -> tuple[int, int]:
    """Return ``(new_step, interval_days)`` after a review outcome.

    Clean pass -> advance one step; pass with hints -> repeat the interval;
    fail -> restart from the first interval. The last interval repeats forever.
    """
    if not passed:
        new_step = 0
    elif used_hints:
        new_step = step
    else:
        new_step = min(step + 1, len(intervals) - 1)
    return new_step, intervals[new_step]
