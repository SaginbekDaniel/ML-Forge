"""Executes ONE unit of untrusted learner code inside the sandbox container.

Started by ``harness.py`` as a fresh interpreter per test, so tests cannot leak
state into each other. Protocol:

* argv[1] -> fd with the JSON command (read once, closed before user code runs)
* argv[2] -> fd where a single JSON result object is written at the end
* real stdin/stdout/stderr are pipes owned by the harness (stdout is graded for
  ``stdout`` tests, captured for display otherwise).

This file never sees expected outputs: comparison happens on the host.
"""

from __future__ import annotations

import builtins
import json
import os
import resource
import sys
import time
import traceback

SOLUTION_FILENAME = "solution.py"
MAX_REPR = 10_000


def _limit_resources(limits: dict) -> None:
    mem = int(limits.get("memory_bytes", 0))
    if mem > 0:
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    cpu = int(limits.get("cpu_seconds", 0))
    if cpu > 0:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    fsize = int(limits.get("file_size_bytes", 0))
    if fsize > 0:
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))


def _user_frames(tb, source_lines: list[str]) -> list[dict]:
    frames = []
    for frame in traceback.extract_tb(tb):
        if frame.filename != SOLUTION_FILENAME:
            continue
        line_no = frame.lineno or 0
        text = source_lines[line_no - 1].strip() if 0 < line_no <= len(source_lines) else ""
        frames.append({"line": line_no, "function": frame.name, "text": text[:200]})
    return frames[-8:]


def _describe_exception(exc: BaseException, source_lines: list[str], phase: str) -> dict:
    frames = _user_frames(exc.__traceback__, source_lines)
    return {
        "type": type(exc).__name__,
        "message": str(exc)[:1000],
        "phase": phase,
        "frames": frames,
        "line": frames[-1]["line"] if frames else None,
    }


def main() -> None:
    cmd_fd, res_fd = int(sys.argv[1]), int(sys.argv[2])
    with os.fdopen(cmd_fd, "rb") as fh:
        cmd = json.loads(fh.read().decode("utf-8"))
    result_stream = os.fdopen(res_fd, "w", encoding="utf-8")

    source: str = cmd["source"]
    kind: str = cmd["kind"]
    source_lines = source.splitlines()
    prompts: list[str] = []

    def emit(payload: dict) -> None:
        result_stream.write(json.dumps(payload))
        result_stream.flush()

    # input() must not echo the prompt into graded stdout; record it instead.
    def sandbox_input(prompt: object = "") -> str:
        if prompt:
            prompts.append(str(prompt)[:200])
        line = sys.stdin.readline()
        if line == "":
            raise EOFError("EOF when reading a line (no more input data)")
        return line.rstrip("\n")

    builtins.input = sandbox_input

    try:
        code = compile(source, SOLUTION_FILENAME, "exec")
    except (SyntaxError, ValueError) as exc:  # ValueError: null bytes
        emit(
            {
                "status": "compile_error",
                "exc": {
                    "type": type(exc).__name__,
                    "message": getattr(exc, "msg", str(exc))[:500],
                    "line": getattr(exc, "lineno", None),
                    "offset": getattr(exc, "offset", None),
                    "text": (getattr(exc, "text", "") or "").strip()[:200],
                    "phase": "compile",
                    "frames": [],
                },
            }
        )
        return

    _limit_resources(cmd.get("limits", {}))
    namespace: dict = {"__name__": "__main__" if kind != "call" else "solution", "__builtins__": builtins}
    started = time.perf_counter()
    phase = "module"
    try:
        exec(code, namespace)  # noqa: S102 - this IS the sandboxed learner process
        if kind == "call":
            phase = "call"
            value = eval(cmd["call"], namespace)  # noqa: S307 - test call expression, sandboxed
            elapsed = (time.perf_counter() - started) * 1000
            text = repr(value)
            emit(
                {
                    "status": "ok",
                    "repr": text[:MAX_REPR],
                    "repr_truncated": len(text) > MAX_REPR,
                    "type": type(value).__name__,
                    "duration_ms": round(elapsed, 2),
                    "prompts": prompts,
                }
            )
        else:
            sys.stdout.flush()
            emit({"status": "ok", "duration_ms": round((time.perf_counter() - started) * 1000, 2), "prompts": prompts})
    except SystemExit as exc:
        sys.stdout.flush()
        emit(
            {
                "status": "ok" if exc.code in (None, 0) else "exception",
                "exc": {"type": "SystemExit", "message": str(exc.code), "phase": phase, "frames": [], "line": None},
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "prompts": prompts,
            }
        )
    except BaseException as exc:  # noqa: BLE001 - report everything learner code raises
        try:
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            pass
        emit(
            {
                "status": "exception",
                "exc": _describe_exception(exc, source_lines, phase),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "prompts": prompts,
            }
        )


if __name__ == "__main__":
    main()
