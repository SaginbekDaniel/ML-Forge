# Test report

Date: 2026-11-04 · Branch: `feature/m1-learning-loop` (merged to `main`)
Environment: Linux container (x86_64), Docker Engine 29.9.2 (cgroup v1, default seccomp),
Python 3.12.3 (uv 0.11.32), Node 22.23.4, pnpm 10.28, Chromium (Playwright 1.63.0).
**Not yet run on macOS / Docker Desktop / Safari.**

Every number below comes from an actual run in this environment; nothing was skipped.

## Summary

| Suite | Command | Passed | Failed | Skipped |
|---|---|---|---|---|
| Lint (ruff check, ruff format, eslint, tsc) | `make lint` | all | 0 | — |
| Backend unit + integration + sandbox security | `make test-backend` (`pytest services`) | **62** | 0 | 0 |
| Frontend unit | `make test-frontend` (Vitest) | **19** | 0 | 0 |
| Smoke (throwaway DB) | `make smoke` | OK | — | — |
| E2E on the real stack | `make e2e` (fresh DB, fresh build) | **12** | 0 | 0 |
| Content validation | `make seed` | 21 / 21 exercises validated; 4 / 4 lessons; diagnostic answers verified | 0 | — |
| Migrations vs models | `alembic check` | "No new upgrade operations detected" | — | — |

## Backend (62)

| File | Tests | What it proves |
|---|---|---|
| `services/runner/tests/test_grading.py` | 10 | Type-strict comparison, float/unordered modes, stdout normalisation, expected exceptions, **hidden tests never expose input/expected/actual/stdout/message**, infra statuses, summary counts |
| `services/runner/tests/test_sandbox_security.py` | 10 | Spec §10.2 on real Docker: infinite loop timeout · network (TCP + DNS) blocked · non-root, no host env secrets, no `/root/.ssh`, `/home`, docker socket, read-only rootfs · fork bomb capped · stdout flood truncated · 1 GB allocation fails safely · cancel leaves no orphan containers · neighbouring runs isolated · fresh process per test · expected values never in payload |
| `services/api/tests/test_mastery.py` | 9 | Mastery policy edge cases (same task twice, threshold, hints, failed/seen assessment, diagnostic never counts), state transitions incl. "mastered earlier", adaptive review intervals |
| `services/api/tests/test_content.py` | 7 | Real curriculum meets M1 minimums; DAG acyclic; cycles rejected; schema rejects bad literals/missing hidden & edge tests; lesson structure; **content change without version bump rejected**; no sandbox → exercises stay pending |
| `services/api/tests/test_ai.py` | 5 | Stub client: cost from pricing table, unknown price not invented, daily limit blocks before calling, refusal & missing key, context truncation, prompt caching on system prompt |
| `services/api/tests/test_api_flow.py` | 21 | Real HTTP + worker + sandbox: wrong→right with evidence; run vs submit; idempotent double submit; locked skill & bad version; progressive hints lower evidence; assessment rules + unlock + review scheduled; unseen variant on retry; full review cycle; infinite loop with responsive API (<1 s); cancel; restart persistence; runner unavailable honest 503; AI unavailable + key never leaks; diagnostic; lesson check; backup/restore/export; uniform validation errors |

## Frontend unit (19)

`i18n.test.ts` (4: ru/en key parity, placeholder parity, interpolation, no empty strings) ·
`results.test.ts` (12: every job → UI state mapping) · `api.test.ts` (3: error envelope,
proxy/network failures, request shape).

## E2E — spec §15.2 scenarios (12/12)

| # | Scenario | Result |
|---|---|---|
| 1 | Clean DB → profile → diagnostic (incl. practical task in sandbox) → roadmap | ✓ |
| 2 | Topic → lesson (run-verified check question) → mark read → exercise | ✓ |
| 3 | Wrong solution → real failing tests; hidden tests shown without inputs | ✓ |
| 4 | Fix → pass → attempt list and skill evidence updated | ✓ |
| 5 | Reload → draft and progress kept | ✓ |
| 6 | API process restart → progress kept | ✓ |
| 7 | Infinite loop → timeout; tabs stay usable while running | ✓ |
| 8 | AI without key → clear message; exercise still gradable | ✓ |
| 9 | Hidden tests/solutions not retrievable via API; assessment variant 403 before start | ✓ |
| 10 | Independent assessment: no hints/mentor (UI + API 403); pass → mastered → next topic unlocked, later one still locked; review scheduled | ✓ |
| 11 | Keyboard: skip link, Ctrl/Cmd+Enter runs, arrow-key tabs, editor escape help | ✓ |
| 12 | 390 px: no horizontal overflow on 6 pages; Run/Submit in viewport; 768 px: no overflow | ✓ |

## Performance (spec §14) — `scripts/bench.py`, 40 samples per endpoint, local API

| Endpoint | p50 ms | p95 ms |
|---|---|---|
| `GET /api/v1/dashboard` | 10.8 | 13.7 |
| `GET /api/v1/roadmap` | 14.6 | 20.3 |
| `GET /api/v1/exercises/io.celsius` | 9.9 | 14.1 |
| `GET /api/v1/lessons/lesson.loops` | 7.6 | 10.0 |
| `GET /api/v1/skills/python.io_types` | 12.0 | 14.7 |
| `GET /api/v1/analytics/skills` | 9.6 | 13.0 |
| Run (submit → graded result, 3 tests, incl. container start) | 605 | 757 |

Targets: GET p95 < 500 ms ✓; Run < 10 s ✓. Infinite-loop submissions finish in ≈5.3 s (budget).
Numbers on Docker Desktop for Mac will differ (VM overhead) and must be re-measured there.

## Not covered / known gaps

* Safari/WebKit and macOS Docker Desktop: not available in this environment.
* Live Claude API call: no key (stub-tested only).
* GitHub Actions workflow (`.github/workflows/ci.yml`) is pushed; its first run was not observed
  from this environment — all numbers above come from local runs.
* No automated colour-contrast audit (tokens were chosen for contrast; manual review only).

## Reproduce

```bash
make lint
```

```bash
make test
```

```bash
make smoke
```

```bash
make e2e
```
