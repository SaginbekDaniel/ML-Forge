"""Latency benchmark against a RUNNING local API (spec §14).

Usage: uv run python scripts/bench.py [http://127.0.0.1:8000]
Measures p50/p95 of read endpoints and end-to-end Run latency (submit -> terminal job).
Needs an existing profile (complete onboarding once). Creates `run` attempts only (no evidence).
"""

from __future__ import annotations

import statistics
import sys
import time
import uuid

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
GETS = [
    "/api/v1/dashboard",
    "/api/v1/roadmap",
    "/api/v1/exercises/io.celsius",
    "/api/v1/lessons/lesson.loops",
    "/api/v1/skills/python.io_types",
    "/api/v1/analytics/skills",
    "/health",
]


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=30) as c:
        if c.get("/api/v1/profile").status_code != 200:
            print("no profile: complete onboarding first")
            return 1
        print(f"{'endpoint':38} {'p50 ms':>8} {'p95 ms':>8}")
        worst = 0.0
        for path in GETS:
            c.get(path)  # warm-up
            samples = []
            for _ in range(40):
                t = time.perf_counter()
                assert c.get(path).status_code == 200, path
                samples.append((time.perf_counter() - t) * 1000)
            worst = max(worst, pct(samples, 95))
            print(f"{path:38} {statistics.median(samples):8.1f} {pct(samples, 95):8.1f}")
        ex = c.get("/api/v1/exercises/io.celsius").json()
        runs = []
        for _ in range(8):
            t = time.perf_counter()
            r = c.post(
                "/api/v1/submissions",
                json={
                    "exercise_id": "io.celsius",
                    "exercise_version": ex["version"],
                    "kind": "run",
                    "source_code": "def celsius_to_fahrenheit(c):\n    return c * 9 / 5 + 32\n",
                    "client_request_id": uuid.uuid4().hex,
                },
            )
            job = r.json()["job_id"]
            while c.get(f"/api/v1/jobs/{job}").json()["status"] in ("queued", "running"):
                time.sleep(0.05)
            runs.append((time.perf_counter() - t) * 1000)
        print(f"{'Run (submit -> result, 3 tests)':38} {statistics.median(runs):8.1f} {pct(runs, 95):8.1f}")
        print(f"GET p95 worst: {worst:.1f} ms (target < 500); Run p95: {pct(runs, 95):.0f} ms (target < 10000)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
