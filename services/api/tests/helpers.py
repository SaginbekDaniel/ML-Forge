import time
import uuid


def submit(client, exercise_id, code, kind="submit", mode="practice", **extra):
    ex = client.get(f"/api/v1/exercises/{exercise_id}").json()
    body = {
        "exercise_id": exercise_id,
        "exercise_version": ex["version"],
        "source_code": code,
        "kind": kind,
        "mode": mode,
        "client_request_id": uuid.uuid4().hex,
        **extra,
    }
    r = client.post("/api/v1/submissions", json=body)
    assert r.status_code == 202, r.text
    return wait_job(client, r.json()["job_id"])


def wait_job(client, job_id, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        j = client.get(f"/api/v1/jobs/{job_id}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not finish")


def solution(exercise_id: str) -> str:
    import yaml
    from mlforge_api.config import REPO_ROOT

    path = REPO_ROOT / "content" / "curriculum" / "exercises" / f"{exercise_id}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["solution"]
