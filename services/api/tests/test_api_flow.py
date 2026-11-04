"""Integration tests: real HTTP API + real worker + real Docker sandbox."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from mlforge_api.main import create_app
from mlforge_runner import DockerSandbox

from tests.conftest import make_settings, requires_docker
from tests.helpers import solution, submit, wait_job

pytestmark = requires_docker


def test_health_reports_components(client):
    h = client.get("/health").json()
    assert h["database"] == "ok" and h["runner"]["available"] is True
    assert h["runner"]["limits"]["memory_mb"] == 256


def test_profile_lifecycle(client):
    r = client.get("/api/v1/dashboard")
    assert r.status_code == 409 and r.json()["error_code"] == "profile_required"
    assert r.json()["request_id"]
    assert client.post("/api/v1/profile", json={"display_name": "A"}).status_code == 201
    assert client.post("/api/v1/profile", json={"display_name": "B"}).status_code == 409
    p = client.patch("/api/v1/profile", json={"daily_goal_minutes": 90, "locale": "en"}).json()
    assert p["daily_goal_minutes"] == 90 and p["locale"] == "en"


def test_exercise_payload_hides_solution_and_hidden_tests(client, profile):
    import yaml
    from mlforge_api.config import REPO_ROOT

    spec = yaml.safe_load((REPO_ROOT / "content/curriculum/exercises/io.celsius.yaml").read_text())
    body = client.get("/api/v1/exercises/io.celsius").text
    assert "spec" not in json.loads(body)
    assert spec["solution"].strip() not in body
    for t in spec["tests"]:
        if t["visibility"] == "hidden":
            assert t["call"] not in body, t["id"]
    for w in spec["wrong_solutions"]:
        assert w["code"].strip() not in body
    lesson = client.get("/api/v1/lessons/lesson.io_types").json()
    assert all("answer" not in q for q in lesson["content"]["check_questions"])


def test_wrong_then_right_creates_evidence(client, profile):
    job = submit(client, "io.sum_two", "a = input()\nb = input()\nprint(a + b)\n")
    assert job["status"] == "completed" and job["passed"] == 0 and job["exit_reason"] == "wrong_answer"
    hidden = [r for r in job["results"] if r["visibility"] == "hidden"]
    assert hidden and all(
        r.get("input") is None and r.get("expected") is None and r.get("actual") is None for r in hidden
    )
    public = [r for r in job["results"] if r["visibility"] == "public"]
    assert public[0]["actual"] == "23" and public[0]["expected"] == "5"
    assert job["counts_as_evidence"] is False

    job = submit(client, "io.sum_two", solution("io.sum_two"))
    assert job["passed"] == job["total"] == 5 and job["counts_as_evidence"] is True
    skill = client.get("/api/v1/skills/python.io_types").json()
    assert skill["state"] == "in_progress"
    crit = {c["id"]: c for c in skill["criteria"]}
    assert crit["distinct_exercises"]["current"] == 1 and crit["no_hint_solve"]["met"] is True
    assert [e["score"] for e in skill["evidence"]] == [1.0, 0.0]
    assert all(e["verification"] == "verified_by_tests" for e in skill["evidence"])


def test_run_only_checks_public_tests_and_creates_no_evidence(client, profile):
    job = submit(
        client, "io.celsius", "def celsius_to_fahrenheit(c):\n    print('hi')\n    return c * 9 / 5 + 32\n", kind="run"
    )
    assert job["kind"] == "run" and all(r["visibility"] == "public" for r in job["results"])
    assert job["run_output"]["stdout"].strip() == ""  # module-level code printed nothing
    assert client.get("/api/v1/skills/python.io_types").json()["evidence"] == []


def test_double_submit_is_idempotent(client, profile):
    ex = client.get("/api/v1/exercises/io.sum_two").json()
    body = {
        "exercise_id": "io.sum_two",
        "exercise_version": ex["version"],
        "source_code": "print(1)",
        "client_request_id": "same-click",
    }
    a = client.post("/api/v1/submissions", json=body)
    b = client.post("/api/v1/submissions", json=body)
    assert a.status_code == 202 and b.status_code == 200
    assert a.json()["job_id"] == b.json()["job_id"] and b.json()["duplicate"] is True
    wait_job(client, a.json()["job_id"])


def test_locked_skill_and_bad_versions_are_rejected(client, profile):
    ex = client.get("/api/v1/exercises/cond.sign").json()
    assert ex["lock"] == {"reason": "skill_locked"}
    r = client.post("/api/v1/submissions", json={"exercise_id": "cond.sign", "exercise_version": 1, "source_code": "x"})
    assert r.status_code == 409 and r.json()["error_code"] == "skill_locked"
    r = client.post(
        "/api/v1/submissions", json={"exercise_id": "io.sum_two", "exercise_version": 999, "source_code": "x"}
    )
    assert r.status_code == 404 and r.json()["error_code"] == "exercise_version_not_found"


def test_hints_are_progressive_and_lower_evidence(client, profile):
    r = client.post("/api/v1/exercises/io.celsius/hint", json={"level": 2})
    assert r.status_code == 409 and r.json()["error_code"] == "hint_out_of_order"
    assert client.post("/api/v1/exercises/io.celsius/hint", json={"level": 1}).status_code == 200
    job = submit(client, "io.celsius", solution("io.celsius"))
    assert job["passed"] == job["total"]
    skill = client.get("/api/v1/skills/python.io_types").json()
    crit = {c["id"]: c["met"] for c in skill["criteria"]}
    assert crit["no_hint_solve"] is False
    assert skill["evidence"][0]["hint_level"] == 1


def master_io_types(client):
    for ex in ("io.greeting", "io.sum_two"):
        assert submit(client, ex, solution(ex))["counts_as_evidence"]
    a = client.post("/api/v1/assessments", json={"skill_id": "python.io_types"}).json()
    assert a["variant_seen"] is False
    job = submit(client, a["exercise_id"], solution(a["exercise_id"]), mode="independent", assessment_id=a["id"])
    assert job["counts_as_evidence"]
    return a


def test_independent_assessment_rules_and_unlock(client, profile):
    r = client.get("/api/v1/exercises/io.duration")
    assert r.status_code == 403 and r.json()["error_code"] == "assessment_not_started"
    for ex in ("io.greeting", "io.sum_two"):
        submit(client, ex, solution(ex))
    a = client.post("/api/v1/assessments", json={"skill_id": "python.io_types"}).json()
    ex_id = a["exercise_id"]
    assert client.get(f"/api/v1/exercises/{ex_id}").status_code == 200
    r = client.post(f"/api/v1/exercises/{ex_id}/hint", json={"level": 1})
    assert r.status_code == 403 and r.json()["error_code"] == "hints_disabled_independent"
    r = client.post("/api/v1/mentor/message", json={"exercise_id": ex_id, "message": "help"})
    assert r.status_code == 403
    r = client.post(
        "/api/v1/submissions",
        json={"exercise_id": ex_id, "exercise_version": 1, "source_code": "x", "mode": "practice"},
    )
    assert r.status_code == 409 and r.json()["error_code"] == "mode_not_allowed"
    # same assessment returned while active
    assert client.post("/api/v1/assessments", json={"skill_id": "python.io_types"}).json()["id"] == a["id"]
    job = submit(client, ex_id, solution(ex_id), mode="independent", assessment_id=a["id"])
    assert job["skill"]["state"] == "mastered"
    # the attempt is spent: a second independent submit is refused
    r = client.post(
        "/api/v1/submissions",
        json={
            "exercise_id": ex_id,
            "exercise_version": 1,
            "source_code": "x",
            "mode": "independent",
            "assessment_id": a["id"],
        },
    )
    assert r.json()["error_code"] == "assessment_not_active"
    roadmap = {s["id"]: s["state"] for t in client.get("/api/v1/roadmap").json()["tracks"] for s in t["skills"]}
    assert roadmap["python.io_types"] == "mastered" and roadmap["python.conditionals"] == "available"
    assert roadmap["python.loops"] == "locked"
    reviews = client.get("/api/v1/reviews/today").json()
    assert reviews["due"] == [] and len(reviews["upcoming"]) == 1
    assert reviews["upcoming"][0]["interval_days"] == 1


def test_second_assessment_uses_unseen_variant(client, profile):
    a = client.post("/api/v1/assessments", json={"skill_id": "python.io_types"}).json()
    job = submit(client, a["exercise_id"], "print('nope')\n", mode="independent", assessment_id=a["id"])
    assert job["counts_as_evidence"] is False
    b = client.post("/api/v1/assessments", json={"skill_id": "python.io_types"}).json()
    assert b["exercise_id"] != a["exercise_id"] and b["variant_seen"] is False


def test_review_cycle(client, profile, data_dir):
    master_io_types(client)
    conn = sqlite3.connect(data_dir / "mlforge.db")
    past = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None).isoformat(sep=" ")
    conn.execute("UPDATE review_items SET due_at = ? WHERE status = 'pending'", (past,))
    conn.commit()
    conn.close()
    assert client.get("/api/v1/skills/python.io_types").json()["state"] == "needs_review"
    due = client.get("/api/v1/reviews/today").json()["due"]
    assert len(due) == 1
    item = client.post(f"/api/v1/reviews/{due[0]['id']}/start").json()
    ex_id = item["exercise_id"]
    r = client.post(f"/api/v1/exercises/{ex_id}/hint", json={"level": 1})
    assert r.json()["error_code"] == "hints_disabled_review"
    job = submit(client, ex_id, solution(ex_id), mode="review", review_item_id=item["id"])
    assert job["skill"]["state"] == "mastered"
    reviews = client.get("/api/v1/reviews/today").json()
    assert reviews["recent"][0]["last_outcome"] == "passed"
    assert reviews["upcoming"][0]["interval_days"] == 3


def test_infinite_loop_times_out_and_api_stays_responsive(client, profile):
    ex = client.get("/api/v1/exercises/io.celsius").json()
    r = client.post(
        "/api/v1/submissions",
        json={"exercise_id": "io.celsius", "exercise_version": ex["version"], "source_code": "while True:\n    pass\n"},
    )
    job_id = r.json()["job_id"]
    time.sleep(1.0)
    started = time.monotonic()
    assert client.get("/api/v1/dashboard").status_code == 200
    assert time.monotonic() - started < 1.0  # handlers never wait for the sandbox
    job = wait_job(client, job_id)
    assert job["status"] == "timed_out" and job["exit_reason"] == "timeout"
    assert {r["status"] for r in job["results"]} <= {"timeout", "not_run"}


def test_cancel_running_job(client, profile):
    ex = client.get("/api/v1/exercises/io.celsius").json()
    r = client.post(
        "/api/v1/submissions",
        json={
            "exercise_id": "io.celsius",
            "exercise_version": ex["version"],
            "source_code": "while True:\n    pass\n",
            "kind": "run",
        },
    )
    job_id = r.json()["job_id"]
    deadline = time.monotonic() + 10
    while client.get(f"/api/v1/jobs/{job_id}").json()["status"] != "running" and time.monotonic() < deadline:
        time.sleep(0.1)
    client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert wait_job(client, job_id)["status"] == "cancelled"
    leftover = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label=mlforge.job={job_id}"], capture_output=True, text=True
    ).stdout.strip()
    assert leftover == ""


def test_progress_and_draft_survive_api_restart(data_dir):
    settings = make_settings(data_dir)
    with TestClient(create_app(settings, start_worker=True)) as c:
        c.post("/api/v1/profile", json={"display_name": "Persist"})
        submit(c, "io.sum_two", solution("io.sum_two"))
        c.put("/api/v1/exercises/io.celsius/draft", json={"code": "# my draft\n"})
    with TestClient(create_app(settings, start_worker=True)) as c:
        assert c.get("/api/v1/profile").json()["display_name"] == "Persist"
        assert c.get("/api/v1/exercises/io.celsius").json()["draft"]["code"] == "# my draft\n"
        ev = c.get("/api/v1/skills/python.io_types").json()["evidence"]
        assert len(ev) == 1 and ev[0]["score"] == 1.0
        assert c.get("/api/v1/exercises/io.sum_two/attempts").json()["items"][0]["job"]["passed"] == 5


def test_runner_unavailable_is_honest(data_dir):
    broken = DockerSandbox(docker_bin="docker-not-installed-here")
    with TestClient(create_app(make_settings(data_dir), start_worker=True, sandbox=broken)) as c:
        c.post("/api/v1/profile", json={"display_name": "X"})
        assert c.get("/health").json()["runner"] == {**c.get("/health").json()["runner"], "available": False}
        r = c.post(
            "/api/v1/submissions", json={"exercise_id": "io.sum_two", "exercise_version": 1, "source_code": "print(1)"}
        )
        assert r.status_code == 503 and r.json()["error_code"] == "runner_unavailable"
        assert r.json()["details"]["reason"] == "docker_cli_missing"
        # learning content still works without the runner
        assert c.get("/api/v1/lessons/lesson.io_types").status_code == 200
        assert c.get("/api/v1/dashboard").json()["runner"]["available"] is False


def test_ai_unavailable_without_key_and_key_never_leaks(data_dir, caplog):
    with TestClient(create_app(make_settings(data_dir), start_worker=False)) as c:
        c.post("/api/v1/profile", json={"display_name": "X"})
        r = c.post("/api/v1/mentor/message", json={"exercise_id": "io.sum_two", "message": "help"})
        assert r.status_code == 503 and r.json()["error_code"] == "ai_unavailable"
        assert c.get("/api/v1/exercises/io.sum_two").status_code == 200
    secret = "sk-ant-test-SUPERSECRET-123"
    settings = make_settings(data_dir).model_copy(
        update={"anthropic_api_key": __import__("pydantic").SecretStr(secret)}
    )
    with TestClient(create_app(settings, start_worker=False)) as c:
        for path in ("/health", "/api/v1/settings", "/api/v1/ai/status", "/api/v1/export/progress"):
            assert secret not in c.get(path).text
        assert c.get("/api/v1/ai/status").json()["configured"] is True
    assert secret not in caplog.text


def test_diagnostic_flow(client, profile):
    d = client.post("/api/v1/diagnostic/start").json()
    assert d["status"] == "in_progress" and len(d["questions"]) == 8
    assert all("answer" not in q for q in d["questions"])
    client.post(f"/api/v1/diagnostic/{d['id']}/answer", json={"question_id": "predict_io", "answer": "33 7"})
    client.post(f"/api/v1/diagnostic/{d['id']}/answer", json={"question_id": "predict_loops", "answer": "9"})
    client.post(f"/api/v1/diagnostic/{d['id']}/answer", json={"question_id": "self_io", "answer": "confident"})
    job = submit(client, "diag.count_even", solution("diag.count_even"), mode="diagnostic")
    assert job["passed"] == job["total"]
    done = client.post(f"/api/v1/diagnostic/{d['id']}/complete").json()
    assert done["answers"]["predict_io"]["correct"] is True and done["answers"]["predict_loops"]["correct"] is False
    assert done["result"]["practical"]["passed"] == job["passed"]
    recs = {s["skill_id"]: s["recommendation"] for s in done["result"]["skills"]}
    assert recs["python.io_types"] == "try_assessment_early"
    assert recs["python.loops"] == "start_with_lesson"
    assert client.get("/api/v1/profile").json()["onboarding_completed"] is True
    # self-report and diagnostic never create mastery evidence
    skill = client.get("/api/v1/skills/python.loops").json()
    assert all(e["source_type"] == "diagnostic" for e in skill["evidence"])
    assert not any(c["met"] for c in skill["criteria"])


def test_lesson_check_and_complete(client, profile):
    r = client.post("/api/v1/lessons/lesson.io_types/check", json={"question_id": "q1", "answer": " 555 "})
    assert r.json()["correct"] is True
    r = client.post("/api/v1/lessons/lesson.io_types/check", json={"question_id": "q1", "answer": "15"})
    assert r.json()["correct"] is False and r.json()["expected"] == "555"
    assert client.post("/api/v1/lessons/lesson.io_types/complete").json()["completed"] is True
    skill = client.get("/api/v1/skills/python.io_types").json()
    assert skill["lesson_completed"] is True and skill["mastery_score"] == 0  # reading is not mastery


def test_backup_restore_and_export(client, profile):
    submit(client, "io.sum_two", solution("io.sum_two"))
    b = client.post("/api/v1/backup").json()
    assert b["contains_secrets"] is False
    r = client.post("/api/v1/restore", json={"file": b["file"], "confirm": "no"})
    assert r.status_code == 400
    r = client.post("/api/v1/restore", json={"file": "../../etc/passwd", "confirm": "RESTORE"})
    assert r.status_code == 400
    r = client.post("/api/v1/restore", json={"file": b["file"], "confirm": "RESTORE"})
    assert r.status_code == 200 and r.json()["check"]["ok"] is True
    exp = client.get("/api/v1/export/progress").json()
    assert exp["submissions"][0]["job"]["passed"] == 5
    csv = client.get("/api/v1/export/progress?format=csv")
    assert csv.headers["content-type"].startswith("text/csv") and "io.sum_two" in csv.text


@pytest.mark.parametrize("bad", [{"display_name": ""}, {"display_name": "x", "daily_goal_minutes": 5}])
def test_validation_errors_are_uniform(client, bad):
    r = client.post("/api/v1/profile", json=bad)
    assert r.status_code == 422 and r.json()["error_code"] == "validation_error" and r.json()["request_id"]
