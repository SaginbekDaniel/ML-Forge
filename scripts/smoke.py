"""End-to-end smoke test on a throwaway database (never touches ./data).

1. sandbox health, 2. seed + validate content, 3. API: profile -> wrong submit
-> correct submit -> evidence, 4. infinite loop is stopped.
"""

from __future__ import annotations

import sys
import tempfile
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from mlforge_api.config import REPO_ROOT, Settings
from mlforge_api.content.loader import load_curriculum
from mlforge_api.content.seed import seed_content
from mlforge_api.db import init_engine, session_scope
from mlforge_api.main import create_app
from mlforge_api.runtime import build_sandbox, migrate


def wait(c: TestClient, job_id: str) -> dict:
    for _ in range(200):
        j = c.get(f"/api/v1/jobs/{job_id}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.2)
    raise SystemExit("job did not finish")


def submit(c: TestClient, code: str) -> dict:
    r = c.post(
        "/api/v1/submissions",
        json={
            "exercise_id": "io.sum_two",
            "exercise_version": 1,
            "source_code": code,
            "client_request_id": uuid.uuid4().hex,
        },
    )
    assert r.status_code == 202, r.text
    return wait(c, r.json()["job_id"])


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="mlforge-smoke-"))
    settings = Settings(
        data_dir=tmp,
        database_url=f"sqlite:///{tmp / 'smoke.db'}",
        content_dir=REPO_ROOT / "content" / "curriculum",
        anthropic_api_key=None,
    )
    sandbox = build_sandbox(settings)
    health = sandbox.health(max_age_s=0)
    print(f"[1] sandbox: available={health.available} reason={health.reason or '-'} image={health.image}")
    if not health.available:
        return 1
    init_engine(settings.resolved_database_url)
    migrate(settings)
    with session_scope() as db:
        rep = seed_content(db, load_curriculum(settings.content_dir), sandbox)
    print(
        f"[2] content: validated={len(rep.validated)} failed={len(rep.failed)}",
        f"lessons_failed={len(rep.lesson_failures)}",
    )
    if not rep.ok:
        return 1
    with TestClient(create_app(settings, start_worker=True, sandbox=sandbox)) as c:
        c.post("/api/v1/profile", json={"display_name": "smoke"})
        wrong = submit(c, "a = input()\nb = input()\nprint(a + b)\n")
        right = submit(c, "a = int(input())\nb = int(input())\nprint(a + b)\n")
        loop = submit(c, "while True:\n    pass\n")
        print(
            f"[3] wrong: {wrong['passed']}/{wrong['total']}  right: {right['passed']}/{right['total']}  "
            f"evidence={right['counts_as_evidence']}"
        )
        print(f"[4] infinite loop: status={loop['status']} duration_ms={loop['duration_ms']}")
        ok = wrong["passed"] == 0 and right["passed"] == right["total"] and loop["status"] == "timed_out"
    print("SMOKE OK" if ok else "SMOKE FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
