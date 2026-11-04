# Implementation plan

Rule from spec §2: **M1 fully works before decoration or programme expansion.** M2–M5 are a roadmap.
Status as of 2026-11-04.

## M0 — Discovery & skeleton — **Done**

- [x] Environment check (Node 22, Python 3.12 via uv, Docker 29, Playwright 1.63)
- [x] Monorepo per §7.3, lockfiles, ADR 0001
- [x] FastAPI + SQLite (WAL) + Alembic + `/health`; Next.js app; Makefile

## M1 — Working learning loop — **Done (pending Mac/Safari confirmation)**

Completion criteria (§15.4) and status:

| Criterion | Status | Evidence |
|---|---|---|
| Reproducible local start per README | Done on Linux; **to confirm on Mac** | `make setup`, `make dev` |
| ≥4 lessons, ≥12 validated exercises | Done: 4 lessons, 21 exercises (20 + diagnostic) | `make seed` → validated 21, failed 0 |
| Python runs in a separate sandbox | Done | `test_sandbox_security.py` |
| Wrong fails, right passes, infinite loop limited | Done | API tests, E2E #3, #4, #7 |
| UI shows attempt log and real states | Done | E2E #4, #7, vitest `displayState` |
| Progress survives restart | Done | E2E #5, #6, API restart test |
| Works without Claude API | Done | E2E #8 |
| Unit/integration/E2E/security run with honest report | Done | `TEST_REPORT.md` |

Risks: Docker Desktop resource limits on Mac (memory/pids flags behave the same, but measure
start-up latency there); WebKit-specific editor/keyboard behaviour.

## M2 — Personal adaptation & AI mentor — **Not started (foundations in place)**

Measurable completion criteria:
1. 30–40 validated exercises and ≥8 lessons (`make seed` reports them validated).
2. AI hint coach / reviewer / interviewer roles with JSON-schema outputs; AI grading of explanations
   stored as `ai_feedback` with an uncertainty flag; **never** changes mastery (test).
3. AI drafting pipeline: generate → schema check → reference run → wrong-solution mutation check →
   human review flag → publish; drafts stay `review_status: draft` until approved (test).
4. Planner proposes the next lesson from the DAG + skill state + available minutes (unit tests).
5. Budget/telemetry: per-request tokens + cost visible in Settings (done), monthly view (new).
6. Two independent assessment variants minimum per skill → target 3.
7. Peak memory reported per run.

Dependencies: an Anthropic API key for live verification; content authoring time.

## M3 — Practical ML labs — **Not started**

Criteria: NumPy/Pandas/sklearn lab image with pinned versions; datasets with licence + SHA-256;
separate sandbox policy (longer time, more RAM); lab results stored as artifacts (code, report,
plots, config, dataset version, seed); first two projects (CLI utility, EDA report) with rubrics
and acceptance tests.

## M4 — Deep learning & specialisation — **Not started**

Criteria: PyTorch CPU image; long-running experiments with checkpoints and resource limits;
CNN/Transformer labs; error-analysis tasks; standardised technical interviews.

## M5 — Production ML & finals — **Not started**

Criteria: FastAPI inference service project, Docker, CI, latency/p95 benchmarking, drift monitoring,
rollback exercise; capstone with independent defense; GitHub-ready export without auto-publishing.

## Immediate next narrow priority

1. Run `make setup && make test && make e2e` on the target MacBook (Docker Desktop, Safari smoke).
2. Check the first GitHub Actions run on `main`.
3. Start M2 with content: python.functions and python.dicts_sets (lessons + 5 tasks each).
