"""Host-side Docker sandbox driver.

The API process never executes learner code. It hands a job to
:class:`DockerSandbox`, which starts a short-lived, network-less, read-only,
non-root container from a prebuilt image and talks to the in-container harness
over stdin/stdout only (no host mounts at all).
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from importlib import resources
from typing import Literal

log = logging.getLogger("mlforge.runner")

SANDBOX_LABEL = "mlforge.sandbox"
HARNESS_LABEL = "mlforge.harness_sha"
IMAGE_REPO = "mlforge-runner"
SANDBOX_UID = "10001:10001"

OutcomeStatus = Literal["completed", "timeout", "cancelled", "memory_limit", "crashed", "unavailable"]


@dataclass(frozen=True)
class SandboxLimits:
    """Defaults follow spec §10.1 (5 s, 256 MB, 1 CPU, 64 processes)."""

    total_budget_s: float = 5.0
    per_test_timeout_s: float = 2.0
    memory_mb: int = 256
    child_memory_mb: int = 192
    cpus: float = 1.0
    pids: int = 64
    tmpfs_mb: int = 16
    max_output_bytes: int = 64 * 1024
    hard_output_bytes: int = 4 * 1024 * 1024
    # Container start-up + harness overhead on top of the learner budget.
    startup_slack_s: float = 15.0

    def harness_limits(self) -> dict:
        return {
            "total_budget_s": self.total_budget_s,
            "per_test_timeout_s": self.per_test_timeout_s,
            "child_memory_bytes": self.child_memory_mb * 1024 * 1024,
            "max_output_bytes": self.max_output_bytes,
            "hard_output_bytes": self.hard_output_bytes,
            "file_size_bytes": 1024 * 1024,
        }


@dataclass
class SandboxOutcome:
    status: OutcomeStatus
    observations: list[dict] = field(default_factory=list)
    duration_ms: int = 0
    exit_code: int | None = None
    oom_killed: bool = False
    detail: str = ""
    used_s: float | None = None


@dataclass
class RunnerHealth:
    available: bool
    docker: bool
    image: str
    image_present: bool
    image_current: bool
    reason: str = ""


def harness_digest() -> str:
    """Hash of the files baked into the runner image; used as the image tag."""
    h = hashlib.sha256()
    pkg = resources.files("mlforge_runner") / "sandbox_files"
    for name in ("harness.py", "child.py"):
        h.update(name.encode())
        h.update((pkg / name).read_bytes())
    return h.hexdigest()[:12]


def default_image() -> str:
    return f"{IMAGE_REPO}:{harness_digest()}"


class DockerSandbox:
    def __init__(self, image: str | None = None, limits: SandboxLimits | None = None, docker_bin: str = "docker"):
        self.image = image or default_image()
        self.limits = limits or SandboxLimits()
        self.docker_bin = docker_bin
        self._active: dict[str, str] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()
        self._health_cache: tuple[float, RunnerHealth] | None = None

    # ------------------------------------------------------------------ health
    def health(self, max_age_s: float = 5.0) -> RunnerHealth:
        now = time.monotonic()
        if self._health_cache and now - self._health_cache[0] < max_age_s:
            return self._health_cache[1]
        result = self._probe()
        self._health_cache = (now, result)
        return result

    def _probe(self) -> RunnerHealth:
        if shutil.which(self.docker_bin) is None:
            return RunnerHealth(False, False, self.image, False, False, "docker_cli_missing")
        try:
            info = subprocess.run(
                [self.docker_bin, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (subprocess.TimeoutExpired, OSError):
            return RunnerHealth(False, False, self.image, False, False, "docker_daemon_unreachable")
        if info.returncode != 0:
            return RunnerHealth(False, False, self.image, False, False, "docker_daemon_unreachable")
        inspect = subprocess.run(
            [self.docker_bin, "image", "inspect", self.image, "--format", "{{json .Config.Labels}}"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if inspect.returncode != 0:
            return RunnerHealth(False, True, self.image, False, False, "runner_image_missing")
        try:
            labels = json.loads(inspect.stdout.strip() or "{}") or {}
        except ValueError:
            labels = {}
        current = labels.get(HARNESS_LABEL) == harness_digest()
        reason = "" if current else "runner_image_outdated"
        return RunnerHealth(current, True, self.image, True, current, reason)

    def invalidate_health(self) -> None:
        self._health_cache = None

    # --------------------------------------------------------------- execution
    def docker_args(self, name: str, job_id: str) -> list[str]:
        lim = self.limits
        return [
            self.docker_bin,
            "run",
            "--name",
            name,
            "-i",
            "--label",
            f"{SANDBOX_LABEL}=1",
            "--label",
            f"mlforge.job={job_id}",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,nodev,size={lim.tmpfs_mb}m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            SANDBOX_UID,
            "--memory",
            f"{lim.memory_mb}m",
            "--memory-swap",
            f"{lim.memory_mb}m",
            "--cpus",
            str(lim.cpus),
            "--pids-limit",
            str(lim.pids),
            "--ulimit",
            "nofile=256:256",
            "--ipc",
            "none",
            "--hostname",
            "sandbox",
            "--log-driver",
            "none",
            self.image,
        ]

    def job_payload(self, nonce: str, source: str, tests: list[dict]) -> bytes:
        """The ONLY data sent into the container: inputs, never expected values."""
        return json.dumps(
            {
                "nonce": nonce,
                "source": source,
                "tests": [{k: t.get(k) for k in ("id", "kind", "call", "stdin")} for t in tests],
                "limits": self.limits.harness_limits(),
            }
        ).encode("utf-8")

    def run(self, job_id: str, source: str, tests: list[dict]) -> SandboxOutcome:
        """Run learner ``source`` against ``tests`` (inputs only, no expectations)."""
        health = self.health()
        if not health.available:
            return SandboxOutcome(status="unavailable", detail=health.reason)

        nonce = secrets.token_hex(16)
        safe_id = "".join(c if c.isalnum() or c in "_.-" else "-" for c in job_id)
        name = f"mlforge-{secrets.token_hex(4)}-{safe_id}"[:63]
        payload = self.job_payload(nonce, source, tests)
        wall_timeout = self.limits.total_budget_s + self.limits.startup_slack_s
        started = time.perf_counter()
        with self._lock:
            if job_id in self._cancelled:
                return SandboxOutcome(status="cancelled")
            self._active[job_id] = name
        proc = subprocess.Popen(
            self.docker_args(name, job_id),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        timed_out = False
        try:
            stdout, stderr = proc.communicate(payload, timeout=wall_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_container(name)
            stdout, stderr = proc.communicate()
        finally:
            with self._lock:
                self._active.pop(job_id, None)
        duration_ms = int((time.perf_counter() - started) * 1000)
        oom = self._oom_killed(name)
        self._remove_container(name)

        if job_id in self._cancelled:
            self._cancelled.discard(job_id)
            return SandboxOutcome(status="cancelled", duration_ms=duration_ms, exit_code=proc.returncode)
        if timed_out:
            return SandboxOutcome(status="timeout", duration_ms=duration_ms, detail="container wall-clock limit")

        marker = f"MLFORGE_RESULT:{nonce}:".encode()
        for line in reversed(stdout.splitlines()):
            if line.startswith(marker):
                try:
                    body = json.loads(line[len(marker) :].decode("utf-8"))
                except ValueError:
                    break
                return SandboxOutcome(
                    status="completed",
                    observations=body.get("tests", []),
                    duration_ms=duration_ms,
                    exit_code=proc.returncode,
                    oom_killed=oom,
                    used_s=body.get("used_s"),
                )
        if oom or proc.returncode == 137:
            return SandboxOutcome(
                status="memory_limit", duration_ms=duration_ms, exit_code=proc.returncode, oom_killed=oom
            )
        log.warning(
            "sandbox produced no result",
            extra={"job_id": job_id, "exit_code": proc.returncode, "stderr": stderr[-500:].decode("utf-8", "replace")},
        )
        if proc.returncode == 125:
            self.invalidate_health()
            return SandboxOutcome(
                status="unavailable", duration_ms=duration_ms, exit_code=125, detail="docker_run_failed"
            )
        return SandboxOutcome(status="crashed", duration_ms=duration_ms, exit_code=proc.returncode)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            self._cancelled.add(job_id)
            name = self._active.get(job_id)
        if name:
            self._kill_container(name)
            return True
        return False

    # ---------------------------------------------------------------- cleanup
    def cleanup_orphans(self) -> int:
        """Remove sandbox containers left behind by a crashed worker/API."""
        if shutil.which(self.docker_bin) is None:
            return 0
        try:
            res = subprocess.run(
                [self.docker_bin, "ps", "-aq", "--filter", f"label={SANDBOX_LABEL}=1"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            return 0
        ids = [i for i in res.stdout.split() if i]
        with self._lock:
            active = set(self._active.values())
        removed = 0
        for cid in ids:
            name = (
                subprocess.run(
                    [self.docker_bin, "inspect", "-f", "{{.Name}}", cid], capture_output=True, text=True, timeout=10
                )
                .stdout.strip()
                .lstrip("/")
            )
            if name in active:
                continue
            subprocess.run([self.docker_bin, "rm", "-f", cid], capture_output=True, timeout=20)
            removed += 1
        return removed

    def _kill_container(self, name: str) -> None:
        subprocess.run([self.docker_bin, "kill", name], capture_output=True, timeout=20)

    def _remove_container(self, name: str) -> None:
        subprocess.run([self.docker_bin, "rm", "-f", name], capture_output=True, timeout=20)

    def _oom_killed(self, name: str) -> bool:
        res = subprocess.run(
            [self.docker_bin, "inspect", "-f", "{{.State.OOMKilled}}", name], capture_output=True, text=True, timeout=10
        )
        return res.stdout.strip() == "true"
