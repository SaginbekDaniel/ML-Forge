"""Dynamic validation: every exercise and lesson example is executed for real.

* reference solution must pass 100% of tests;
* every known-wrong solution must fail at least one test;
* starter code must not already pass (except for refactor tasks);
* lesson example outputs and predict-output answers must match real output.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from mlforge_runner import DockerSandbox, grade, harness_digest

from .schema import ExerciseSpec, LessonSpec


def _run(sandbox: DockerSandbox, job_id: str, code: str, tests: list[dict]) -> dict:
    outcome = sandbox.run(job_id, code, tests)
    if outcome.status != "completed":
        return {"status": outcome.status, "passed": 0, "total": len(tests), "failures": [outcome.status]}
    results, summary = grade(tests, outcome.observations)
    return {
        "status": "completed",
        "passed": summary.passed,
        "total": summary.total,
        "failures": [f"{r.id}:{r.status}" + (f" {r.message}" if r.message else "") for r in results if not r.passed],
    }


def validate_exercise(ex: ExerciseSpec, sandbox: DockerSandbox) -> dict:
    tests = [t.model_dump() for t in ex.tests]
    checks: list[dict] = []
    ref = _run(sandbox, f"val-{ex.id}-ref", ex.solution, tests)
    checks.append(
        {
            "name": "reference_solution",
            "expect": "all_pass",
            **ref,
            "ok": ref["status"] == "completed" and ref["passed"] == ref["total"],
        }
    )
    for i, wrong in enumerate(ex.wrong_solutions):
        res = _run(sandbox, f"val-{ex.id}-wrong{i}", wrong.code, tests)
        checks.append(
            {
                "name": f"wrong:{wrong.name}",
                "expect": "some_fail",
                **res,
                "ok": res["status"] == "completed" and res["passed"] < res["total"],
            }
        )
    if ex.type != "refactor":
        res = _run(sandbox, f"val-{ex.id}-starter", ex.starter_code, tests)
        checks.append(
            {
                "name": "starter_code",
                "expect": "some_fail",
                **res,
                "ok": res["status"] == "completed" and res["passed"] < res["total"],
            }
        )
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "harness": harness_digest()}


def validate_lesson(lesson: LessonSpec, sandbox: DockerSandbox) -> dict:
    snippets: list[tuple[str, str, str]] = []
    for i, ex in enumerate(lesson.examples):
        if ex.output:
            snippets.append((f"example{i}", ex.code, ex.output))
    if lesson.common_mistake.output is not None:
        snippets.append(("common_mistake", lesson.common_mistake.code, lesson.common_mistake.output))
    for q in lesson.check_questions:
        snippets.append((f"question:{q.id}", q.code, q.answer))
    checks = []
    for name, code, expected in snippets:
        test = {"id": "out", "kind": "stdout", "visibility": "public", "expected_stdout": expected, "stdin": ""}
        res = _run(sandbox, f"val-{lesson.id}-{name}".replace(":", "-"), code, [test])
        checks.append({"name": name, **res, "ok": res["status"] == "completed" and res["passed"] == 1})
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "harness": harness_digest()}


def validate_many(items: list, fn, sandbox: DockerSandbox, workers: int = 4) -> dict[str, dict]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        reports = list(pool.map(lambda it: fn(it, sandbox), items))
    return {it.id: rep for it, rep in zip(items, reports, strict=True)}


def validate_diagnostic(diag, sandbox: DockerSandbox) -> dict:
    """Predict-output answers in the diagnostic must match the real program output."""
    checks = []
    for q in diag.questions:
        if q.type != "predict_output":
            continue
        test = {"id": "out", "kind": "stdout", "visibility": "public", "expected_stdout": q.answer, "stdin": ""}
        res = _run(sandbox, f"val-diag-{q.id}", q.code, [test])
        checks.append({"name": q.id, **res, "ok": res["status"] == "completed" and res["passed"] == 1})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
