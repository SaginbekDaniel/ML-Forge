# ADR 0001 — Stack, code-execution model, data model, offline mode, secrets

Status: accepted · Date: 2026-11-04 · Scope: M0/M1

## Context

Spec §7 proposes Next.js + FastAPI + SQLite + a Docker sandbox, local-first on a MacBook,
with AI optional. No existing repository was available (see `IMPLEMENTATION_REPORT.md`), so this
is a greenfield monorepo following §7.3.

## Decisions

### 1. Stack (versions pinned by lockfiles: `uv.lock`, `pnpm-lock.yaml`)

| Layer | Choice | Why |
|---|---|---|
| Web | Next.js 16.4 (App Router), React 19.3, TypeScript 5.9 strict, Tailwind 4.3 | Spec §7.1. TypeScript 7 (native) was available but younger; 5.9 chosen for ecosystem stability. |
| Editor | CodeMirror 6 | Modular, ~10× lighter than Monaco, accessible (`Esc` then `Tab` leaves the editor), works on iOS. |
| API | Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2.0, Alembic | Spec §7.1. |
| DB | SQLite (WAL, `foreign_keys=ON`, `busy_timeout`) | Local-first; schema is portable to PostgreSQL later. |
| Sandbox | Docker CLI driving short-lived containers from a prebuilt image | Available on Mac (Docker Desktop) and Linux; no SDK dependency. |
| AI | Official `anthropic` Python SDK, server-side only | Spec §5.2; optional. |
| Tests | pytest, Vitest, Playwright 1.63 | Spec §7.1. |

### 2. Code execution model

* HTTP handlers **never** execute or wait for learner code. `POST /submissions` writes a
  `submission` + a `run_job` row (`queued`) and returns `202`.
* A worker (threads inside the API process by default — "embedded worker") claims jobs with an
  atomic `UPDATE … WHERE status='queued'` and calls `mlforge_runner.DockerSandbox`.
* One container per job: `--network none --read-only --cap-drop ALL --security-opt no-new-privileges
  --user 10001 --memory 256m --pids-limit 64 --cpus 1 --ipc none`, tmpfs `/tmp` (16 MB, noexec).
  **No host mounts at all**: code and test inputs go in over stdin, results come back on stdout.
* Inside, `harness.py` runs **each test in a fresh interpreter** (`child.py`) with per-test and
  total time budgets, `RLIMIT_AS`/`RLIMIT_CPU`/`RLIMIT_FSIZE`, bounded output capture.
* **Grading happens on the host.** The container receives inputs only; expected outputs and the
  reference solution never enter it, so learner code cannot read them.
* The image tag is the SHA of the harness files; the API reports `runner_image_outdated` instead of
  running a stale harness.
* Crash safety: on start-up, jobs left `running` become `failed/worker_restarted` and labelled
  orphan containers are removed.

Rejected: `exec` in-process (forbidden by §10), `subprocess` on the host (no FS/network isolation),
gVisor/Firecracker (not available on Docker Desktop for Mac; documented as the path for public hosting).

### 3. Data model and versioning

* Content lives in Git (`content/curriculum/*.yaml`) and is validated by Pydantic schemas.
* `exercises` and `lessons` use a composite key `(id, version)`. Rows are **never rewritten**;
  changing content without bumping `version` fails `make seed`. Submissions reference the exact
  version, so old attempts stay meaningful.
* An exercise is **active** only if `review_status == reviewed` **and** sandbox validation passed:
  reference solution 100%, every known-wrong solution and the starter code fail ≥1 test.
* Mastery is **derived** from append-only `skill_evidence`; `skill_states` is a cache recomputed by
  a pure policy function (`domain/mastery.py`).
* No assumption of a single `id=1` profile: the "current profile" is a dependency that a future
  auth layer replaces.

### 4. Offline / no-AI

Lessons, exercises, grading, progress and reviews have zero network dependencies (system fonts,
no CDN). The AI adapter returns `ai_unavailable` (503) without a key; nothing else changes.

### 5. Secrets

`ANTHROPIC_API_KEY` is read from the environment / `.env` (git-ignored) by the backend only. It is a
`SecretStr`, never stored in `app_settings`, never serialised, never logged (the JSON log formatter
redacts key/token/secret fields), and backups are DB-only. Tests assert the key does not appear in
API responses or logs.

## Consequences

* Docker is a hard requirement for *running* code; without it the UI shows an honest
  "Runner unavailable" state with the fix (`make runner-build`).
* Container start-up adds ~0.4–0.6 s per run (measured, see `TEST_REPORT.md`).
* Next.js rewrites are resolved at build time (`MLFORGE_API_ORIGIN` requires a rebuild).
