"""Sandbox-side harness (runs as the non-root sandbox user inside the container).

Reads ONE JSON job from stdin, runs every test in a fresh ``child.py``
interpreter with per-test and total time budgets, and prints exactly one
result line ``MLFORGE_RESULT:<nonce>:<json>`` on stdout.

The harness reports raw observations (return-value repr, stdout, exception).
It never receives expected values, so hidden expected outputs never enter the
container; pass/fail is decided on the host.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time

CHILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "child.py")


class BoundedReader(threading.Thread):
    """Drains a pipe, keeps at most ``keep`` bytes, flags floods beyond ``hard``."""

    def __init__(self, stream, keep: int, hard: int, on_flood):
        super().__init__(daemon=True)
        self.stream = stream
        self.keep = keep
        self.hard = hard
        self.on_flood = on_flood
        self.buf = bytearray()
        self.total = 0

    def run(self) -> None:
        while True:
            chunk = self.stream.read(65536)
            if not chunk:
                break
            self.total += len(chunk)
            room = self.keep - len(self.buf)
            if room > 0:
                self.buf.extend(chunk[:room])
            if self.total > self.hard:
                self.on_flood()
                break

    def text(self) -> str:
        return self.buf.decode("utf-8", errors="replace")


def run_one(source: str, test: dict, limits: dict, timeout_s: float) -> dict:
    cmd_r, cmd_w = os.pipe()
    res_r, res_w = os.pipe()
    command = {
        "source": source,
        "kind": test["kind"],
        "call": test.get("call"),
        "limits": {
            "memory_bytes": limits.get("child_memory_bytes", 0),
            "cpu_seconds": max(1, int(timeout_s + 1)),
            "file_size_bytes": limits.get("file_size_bytes", 1_048_576),
        },
    }
    started = time.perf_counter()
    proc = subprocess.Popen(
        [sys.executable, "-I", "-X", "utf8", CHILD, str(cmd_r), str(res_w)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=(cmd_r, res_w),
        cwd="/tmp",
        start_new_session=True,
    )
    os.close(cmd_r)
    os.close(res_w)
    with os.fdopen(cmd_w, "wb") as fh:
        fh.write(json.dumps(command).encode("utf-8"))

    flooded = {"value": False}

    def flood() -> None:
        flooded["value"] = True
        _kill(proc)

    keep = int(limits.get("max_output_bytes", 65536))
    hard = int(limits.get("hard_output_bytes", 4 * 1024 * 1024))
    out_reader = BoundedReader(proc.stdout, keep, hard, flood)
    err_reader = BoundedReader(proc.stderr, keep // 4, hard, flood)
    res_holder: dict = {}

    def read_result() -> None:
        with os.fdopen(res_r, "rb") as fh:
            res_holder["raw"] = fh.read(2 * 1024 * 1024)

    res_thread = threading.Thread(target=read_result, daemon=True)
    for t in (out_reader, err_reader, res_thread):
        t.start()
    try:
        if test.get("stdin"):
            proc.stdin.write(test["stdin"].encode("utf-8"))
        proc.stdin.close()
    except BrokenPipeError:
        pass

    timed_out = False
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill(proc)
        proc.wait()
    for t in (out_reader, err_reader, res_thread):
        t.join(timeout=1)
    wall_ms = round((time.perf_counter() - started) * 1000, 2)

    observation: dict = {
        "id": test["id"],
        "wall_ms": wall_ms,
        "stdout": out_reader.text(),
        "stdout_truncated": out_reader.total > keep,
        "stderr": err_reader.text(),
        "exit_code": proc.returncode,
    }
    payload = None
    raw = res_holder.get("raw")
    if raw:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError:
            payload = None

    if flooded["value"]:
        observation["status"] = "output_limit"
    elif timed_out or (payload is None and proc.returncode == -signal.SIGXCPU):
        observation["status"] = "timeout"
    elif payload is None and proc.returncode == -signal.SIGKILL:
        # Not killed by us -> the kernel OOM killer (cgroup memory limit).
        observation["status"] = "killed"
    elif payload is None:
        observation["status"] = "crashed"
    else:
        observation.update(payload)
    return observation


def _kill(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def main() -> None:
    job = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    nonce = job["nonce"]
    source = job["source"]
    limits = job.get("limits", {})
    per_test = float(limits.get("per_test_timeout_s", 2.0))
    budget = float(limits.get("total_budget_s", 5.0))
    used = 0.0
    results = []
    compile_failure = None
    for test in job["tests"]:
        if compile_failure is not None:
            results.append({"id": test["id"], **compile_failure})
            continue
        remaining = budget - used
        if remaining <= 0.05:
            results.append({"id": test["id"], "status": "not_run", "reason": "time_budget_exhausted"})
            continue
        obs = run_one(source, test, limits, min(per_test, remaining))
        used += obs["wall_ms"] / 1000
        if obs.get("status") == "compile_error":
            compile_failure = {k: v for k, v in obs.items() if k in ("status", "exc")}
        results.append(obs)
    sys.stdout.write("MLFORGE_RESULT:" + nonce + ":" + json.dumps({"tests": results, "used_s": round(used, 3)}) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
