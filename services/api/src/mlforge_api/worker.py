"""Job worker: claims queued run jobs from the DB and executes them in the sandbox.

Runs as background threads (embedded mode, default) so HTTP handlers never block
on, or execute, learner code. Jobs are durable rows, so a restart re-queues
nothing silently: in-flight jobs are marked ``failed/worker_restarted`` and
orphan containers are removed.
"""

from __future__ import annotations

import logging
import threading

from mlforge_runner import DockerSandbox
from sqlalchemy import select, update

from .content.schema import MasteryPolicy
from .db import session_factory
from .domain.grading_service import finalize_job, tests_for
from .models import Exercise, RunJob, utcnow

log = logging.getLogger("mlforge.worker")


class JobWorker:
    def __init__(self, sandbox: DockerSandbox, policy: MasteryPolicy, threads: int = 2):
        self.sandbox = sandbox
        self.policy = policy
        self.threads = max(1, threads)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._pool: list[threading.Thread] = []

    # lifecycle ---------------------------------------------------------------
    def recover(self) -> None:
        with session_factory()() as db:
            res = db.execute(
                update(RunJob)
                .where(RunJob.status == "running")
                .values(status="failed", exit_reason="worker_restarted", finished_at=utcnow())
            )
            db.commit()
            if res.rowcount:
                log.warning("marked interrupted jobs as failed", extra={"count": res.rowcount})
        removed = self.sandbox.cleanup_orphans()
        if removed:
            log.warning("removed orphan sandbox containers", extra={"count": removed})

    def start(self) -> None:
        self.recover()
        for i in range(self.threads):
            t = threading.Thread(target=self._loop, name=f"mlforge-worker-{i}", daemon=True)
            t.start()
            self._pool.append(t)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        for t in self._pool:
            t.join(timeout=2)

    def notify(self) -> None:
        self._wake.set()

    # processing ----------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.process_next()
            except Exception:  # noqa: BLE001 - keep the worker alive
                log.exception("worker iteration failed")
                worked = False
            if not worked:
                self._wake.wait(timeout=1.0)
                self._wake.clear()

    def claim(self) -> str | None:
        with session_factory()() as db:
            job_id = db.scalar(select(RunJob.id).where(RunJob.status == "queued").order_by(RunJob.created_at))
            if job_id is None:
                return None
            res = db.execute(
                update(RunJob)
                .where(RunJob.id == job_id, RunJob.status == "queued")
                .values(status="running", started_at=utcnow())
            )
            db.commit()
            return job_id if res.rowcount == 1 else None

    def process_next(self) -> bool:
        job_id = self.claim()
        if job_id is None:
            return False
        self.process(job_id)
        return True

    def process(self, job_id: str) -> None:
        with session_factory()() as db:
            job = db.get(RunJob, job_id)
            if job is None:
                return
            sub = job.submission
            exercise = db.get(Exercise, (sub.exercise_id, sub.exercise_version))
            tests = tests_for(sub, exercise, sub.run_stdin)
            source = sub.source_code
            if job.cancel_requested:
                self.sandbox.cancel(job_id)
        log.info("job started", extra={"job_id": job_id, "kind": sub.kind, "exercise_id": sub.exercise_id})
        outcome = self.sandbox.run(job_id, source, tests)
        with session_factory()() as db:
            job = db.get(RunJob, job_id)
            if job.cancel_requested and outcome.status != "cancelled":
                outcome.status = "cancelled"
            finalize_job(db, job, outcome, tests, self.policy, self.sandbox.limits.memory_mb)
            log.info(
                "job finished",
                extra={
                    "job_id": job_id,
                    "status": job.status,
                    "exit_reason": job.exit_reason,
                    "duration_ms": job.duration_ms,
                },
            )

    def cancel(self, job_id: str) -> None:
        self.sandbox.cancel(job_id)
