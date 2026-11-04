"""Host-side, deterministic grading of sandbox observations.

Expected values live only here (on the host); the sandbox only reports what
learner code *did*. Every test outcome is classified into a small, stable set
of statuses that the API stores and the UI renders.
"""

from __future__ import annotations

import ast
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TestStatus = Literal[
    "passed",
    "wrong_answer",
    "runtime_error",
    "compile_error",
    "timeout",
    "memory_limit",
    "output_limit",
    "not_run",
    "crashed",
]

MAX_DISPLAY = 2000


@dataclass
class TestOutcome:
    id: str
    visibility: str
    passed: bool
    status: TestStatus
    description: str = ""
    tags: list[str] = field(default_factory=list)
    duration_ms: float | None = None
    error_type: str | None = None
    message: str | None = None
    line: int | None = None
    # Only populated for public tests (never for hidden ones).
    input: str | None = None
    expected: str | None = None
    actual: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    stdout_truncated: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GradeSummary:
    passed: int
    total: int
    edge_cases_passed: int
    edge_cases_total: int
    score: float
    error_type: str | None
    max_test_ms: float | None


def _clip(text: str | None, n: int = MAX_DISPLAY) -> str | None:
    if text is None:
        return None
    return text if len(text) <= n else text[:n] + "…"


def parse_literal(text: str) -> Any:
    if len(text) > 100_000:
        raise ValueError("literal too large")
    return ast.literal_eval(text)


def deep_equal(actual: Any, expected: Any, mode: str = "exact", abs_tol: float = 1e-9, rel_tol: float = 1e-9) -> bool:
    """Type-strict structural equality (``True != 1``, ``2.0 != 2`` in exact mode)."""
    if mode == "unordered" and isinstance(expected, list) and isinstance(actual, list):
        if len(actual) != len(expected):
            return False
        try:
            return sorted(map(repr, actual)) == sorted(map(repr, expected))
        except TypeError:
            return False
    if isinstance(expected, float) or isinstance(actual, float):
        if mode == "float":
            if isinstance(actual, bool) or isinstance(expected, bool):
                return False
            if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
                return False
            if math.isnan(expected):
                return math.isnan(actual)
            return math.isclose(actual, expected, abs_tol=abs_tol, rel_tol=rel_tol)
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(
            deep_equal(a, e, mode, abs_tol, rel_tol) for a, e in zip(actual, expected, strict=True)
        )
    if isinstance(expected, dict):
        if set(actual.keys()) != set(expected.keys()):
            return False
        return all(deep_equal(actual[k], expected[k], mode, abs_tol, rel_tol) for k in expected)
    return actual == expected


def normalize_stdout(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


_FAIL_STATUS = {
    "timeout": "timeout",
    "killed": "memory_limit",
    "output_limit": "output_limit",
    "not_run": "not_run",
    "crashed": "crashed",
}


def grade_test(spec: dict, obs: dict | None) -> TestOutcome:
    public = spec.get("visibility", "public") == "public"
    out = TestOutcome(
        id=spec["id"],
        visibility=spec.get("visibility", "public"),
        passed=False,
        status="crashed",
        description=spec.get("description", ""),
        tags=list(spec.get("tags", [])),
    )
    if public:
        out.input = spec.get("call") if spec["kind"] == "call" else spec.get("stdin", "")
        out.expected = spec.get("expected") if spec["kind"] == "call" else spec.get("expected_stdout")
        if spec.get("raises"):
            out.expected = f"raises {spec['raises']}"
    if obs is None:
        out.status, out.message = "crashed", "no result from sandbox"
        return out

    out.duration_ms = obs.get("duration_ms", obs.get("wall_ms"))
    if public:
        out.stdout = _clip(obs.get("stdout"))
        out.stderr = _clip(obs.get("stderr"), 1000)
        out.stdout_truncated = bool(obs.get("stdout_truncated"))

    status = obs.get("status")
    if status in _FAIL_STATUS:
        out.status = _FAIL_STATUS[status]  # type: ignore[assignment]
        return out

    exc = obs.get("exc")
    if status == "compile_error":
        out.status = "compile_error"
        out.error_type = exc.get("type") if exc else "SyntaxError"
        out.line = exc.get("line") if exc else None
        # Compile errors concern the learner's own text, never test data: safe to show.
        out.message = exc.get("message") if exc else None
        return out

    if status == "exception":
        etype = exc.get("type") if exc else "Exception"
        if spec.get("raises") and etype == spec["raises"] and exc.get("phase") == "call":
            out.passed, out.status = True, "passed"
            out.actual = f"raises {etype}" if public else None
            return out
        out.error_type = etype
        out.line = exc.get("line") if exc else None
        out.status = "memory_limit" if etype == "MemoryError" else "runtime_error"
        if public:  # messages may echo hidden inputs -> only for public tests
            out.message = _clip(exc.get("message"), 500)
            out.actual = f"{etype}: {out.message}"
        return out

    if status != "ok":
        out.status = "crashed"
        return out

    if spec.get("raises"):
        out.status = "wrong_answer"
        out.message = f"expected {spec['raises']} to be raised"
        if public:
            out.actual = obs.get("repr", "no exception")
        return out

    if spec["kind"] == "call":
        actual_repr = obs.get("repr", "")
        if public:
            out.actual = _clip(actual_repr)
        try:
            expected_value = parse_literal(spec["expected"])
        except (ValueError, SyntaxError) as exc_:  # content bug, caught by validation
            out.status, out.message = "crashed", f"invalid expected literal: {exc_}"
            return out
        try:
            actual_value = parse_literal(actual_repr)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            out.status = "wrong_answer"
            out.message = f"returned a value of type {obs.get('type')} that is not a plain literal"
            return out
        ok = deep_equal(
            actual_value,
            expected_value,
            spec.get("compare", "exact"),
            float(spec.get("abs_tol", 1e-9)),
            float(spec.get("rel_tol", 1e-9)),
        )
        if not ok and public and type(actual_value) is not type(expected_value):
            out.message = f"type mismatch: got {type(actual_value).__name__}, expected {type(expected_value).__name__}"
        out.passed = ok
        out.status = "passed" if ok else "wrong_answer"
        return out

    if spec["kind"] == "stdout":
        got = normalize_stdout(obs.get("stdout", ""))
        want = normalize_stdout(spec.get("expected_stdout", ""))
        if public:
            out.actual = _clip(got)
        out.passed = got == want and not obs.get("stdout_truncated")
        out.status = "passed" if out.passed else "wrong_answer"
        return out

    # kind == "script": plain run without expectations (playground "Run").
    out.passed, out.status = True, "passed"
    if public:
        out.actual = None
    return out


def grade(specs: list[dict], observations: list[dict]) -> tuple[list[TestOutcome], GradeSummary]:
    by_id = {o.get("id"): o for o in observations}
    outcomes = [grade_test(spec, by_id.get(spec["id"])) for spec in specs]
    graded = [o for o in outcomes]
    passed = sum(o.passed for o in graded)
    edge = [o for o in graded if "edge_case" in o.tags]
    first_failure = next((o for o in graded if not o.passed), None)
    error_type = None
    if first_failure is not None:
        error_type = first_failure.error_type if first_failure.status == "runtime_error" else first_failure.status
    durations = [o.duration_ms for o in graded if o.duration_ms is not None]
    summary = GradeSummary(
        passed=passed,
        total=len(graded),
        edge_cases_passed=sum(o.passed for o in edge),
        edge_cases_total=len(edge),
        score=(passed / len(graded)) if graded else 0.0,
        error_type=error_type,
        max_test_ms=max(durations) if durations else None,
    )
    return outcomes, summary
