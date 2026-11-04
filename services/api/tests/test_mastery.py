"""Unit tests for the mastery policy (spec §3.3) and review scheduling (§3.4)."""

from datetime import UTC, datetime, timedelta

from mlforge_api.content.schema import MasteryPolicy
from mlforge_api.domain.mastery import EvidenceView, derive_state, evaluate, next_review_step

P = MasteryPolicy()
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def ev(ex, score=1.0, hint=0, source="exercise", minutes=0, seen=False):
    return EvidenceView(ex, source, score, hint, T0 + timedelta(minutes=minutes), seen)


def crit(evaluation):
    return {c.id: c.met for c in evaluation.criteria}


def test_no_evidence_nothing_met():
    e = evaluate([], P)
    assert not e.all_met and e.mastery_score == 0 and e.hint_dependency is None


def test_same_exercise_twice_is_not_two_distinct():
    e = evaluate([ev("a"), ev("a", minutes=1)], P)
    assert crit(e)["distinct_exercises"] is False


def test_below_threshold_does_not_count():
    e = evaluate([ev("a", 0.8), ev("b", 0.84)], P)
    assert crit(e)["distinct_exercises"] is False


def test_hints_everywhere_blocks_no_hint_criterion():
    e = evaluate([ev("a", hint=1), ev("b", hint=2), ev("x", source="assessment")], P)
    assert crit(e) == {"distinct_exercises": True, "no_hint_solve": False, "independent_assessment": True}
    assert e.hint_dependency == 1.0


def test_full_mastery_and_met_at_is_last_criterion_time():
    e = evaluate([ev("a", minutes=1), ev("b", hint=1, minutes=5), ev("x", source="assessment", minutes=9)], P)
    assert e.all_met and e.mastery_score == 1.0
    assert e.met_at == T0 + timedelta(minutes=9)


def test_failed_assessment_does_not_count_and_seen_variant_is_flagged():
    e = evaluate([ev("a"), ev("b"), ev("x", 0.5, source="assessment")], P)
    assert crit(e)["independent_assessment"] is False
    e2 = evaluate([ev("a"), ev("b"), ev("x", source="assessment", seen=True)], P)
    note = next(c for c in e2.criteria if c.id == "independent_assessment").note
    assert note == "passed_on_previously_seen_variant"


def test_diagnostic_evidence_never_counts():
    e = evaluate([ev("a", source="diagnostic"), ev("b", source="diagnostic")], P)
    assert crit(e)["distinct_exercises"] is False


def test_derive_state_transitions():
    none = evaluate([], P)
    full = evaluate([ev("a"), ev("b"), ev("x", source="assessment")], P)
    kw = dict(has_any_attempt=False, review_due=False, last_review_failed=False)
    assert derive_state(skill_status="planned", prereq_states=[], evaluation=none, **kw) == "planned"
    assert derive_state(skill_status="active", prereq_states=["in_progress"], evaluation=none, **kw) == "locked"
    assert derive_state(skill_status="active", prereq_states=["needs_review"], evaluation=none, **kw) == "available"
    assert (
        derive_state(skill_status="active", prereq_states=[], evaluation=none, **{**kw, "has_any_attempt": True})
        == "in_progress"
    )
    assert derive_state(skill_status="active", prereq_states=[], evaluation=full, **kw) == "mastered"
    # forgetting never erases mastery: it becomes "mastered earlier, review now"
    assert (
        derive_state(skill_status="active", prereq_states=[], evaluation=full, **{**kw, "review_due": True})
        == "needs_review"
    )
    assert (
        derive_state(skill_status="active", prereq_states=[], evaluation=full, **{**kw, "last_review_failed": True})
        == "needs_review"
    )


def test_review_intervals_adapt():
    iv = [1, 3, 7, 14, 30]
    assert next_review_step(0, True, False, iv) == (1, 3)
    assert next_review_step(1, True, True, iv) == (1, 3)  # hints -> repeat interval
    assert next_review_step(3, False, False, iv) == (0, 1)  # miss -> restart
    assert next_review_step(4, True, False, iv) == (4, 30)  # last interval repeats
