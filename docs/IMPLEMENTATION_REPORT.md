# Implementation report — M0 + M1

Date: 2026-11-04

## 1. Repository and branch

| Item | Value |
|---|---|
| Repository | https://github.com/SaginbekDaniel/ML-Forge |
| Branches | `main` (default) and `feature/m1-learning-loop` — same commits |
| Merge | `main` was created by fast-forward from `feature/m1-learning-loop` at the owner's request |

At the start of the work the request contained the placeholder `[INSERT GITHUB REPOSITORY URL]`
and no repository was reachable, so the code was built in a new local repository (spec §M0). The
owner then supplied the URL. The GitHub repository was **empty** (no branches or commits) when it
was attached, so there was no existing code to audit or preserve; the branch was pushed and merged
to `main` without rewriting any history.

## 2. Specification analysis

No PDF was provided or found. `ML_FORGE_TECHNICAL_SPEC.md` (v1.0, §1–§18) was read in full and is
traced requirement-by-requirement in [`REQUIREMENTS_MATRIX.md`](REQUIREMENTS_MATRIX.md) (66 rows,
with ambiguities and the interpretation chosen). Core reading of the spec: build one honest,
working vertical slice (M1) where **only executable tests decide correctness**, mastery requires
independent evidence, the AI is optional and bounded, and nothing unbuilt is presented as working.

## 3. Existing architecture assessment

There was no existing implementation. Architecture decisions: [`adr/0001`](adr/0001-stack-and-execution-model.md);
overview: [`ARCHITECTURE.md`](ARCHITECTURE.md); gaps: [`GAP_ANALYSIS.md`](GAP_ANALYSIS.md);
roadmap with measurable criteria: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

## 4. Features implemented (all wired end-to-end, no mocks in the app path)

**Sandbox runner** (`services/runner`) — Docker container per job (no network, read-only rootfs,
non-root 10001, all capabilities dropped, 256 MB, 64 pids, 1 CPU, tmpfs /tmp, no host mounts);
fresh interpreter per test; 2 s/test and 5 s total budget; output caps; cancellation; orphan
cleanup; image tagged by harness digest. **Grading on the host** so hidden expected values never
enter the sandbox; hidden results redacted.

**Content pipeline** — versioned YAML (skills DAG + mastery policy, 4 lessons, 21 exercises,
diagnostic). `make seed` validates schema and graph, then runs every reference solution (must pass
all), every known-wrong solution and starter (must fail), every lesson example output, check-question
answer and diagnostic answer in the sandbox. Content changes without a version bump are rejected.

**Backend** (`services/api`) — FastAPI with uniform errors + `request_id`, SQLite WAL, Alembic,
structured logs. Profile; diagnostic (self-report kept separate from checked answers); roadmap;
lessons with server-checked predict-output questions; exercises; draft autosave; progressive hints
(server-enforced); submissions (idempotent, version-checked, mode-checked) → durable job queue →
embedded worker; jobs with cancel; evidence; mastery policy; independent assessments with unseen
variant selection; spaced repetition; dashboard with one next step; analytics with
"insufficient data" thresholds; settings; backup/restore with schema check; JSON/CSV export;
activity heartbeat (real active time); optional AI mentor with daily request/USD caps, token/cost
telemetry and `ai_unavailable` without a key.

**Frontend** (`apps/web`) — Next.js 16 / React 19 / TS strict / Tailwind tokens (dark default,
light theme), ru/en i18n with parity tests, CodeMirror 6 editor (Ctrl/Cmd+Enter run,
Ctrl/Cmd+Shift+Enter submit). Pages: onboarding, dashboard, roadmap, lesson, practice (42/58 split
≥1200 px, tabbed below, 390 px usable), assessment, review, skills/evidence, settings. All job states
rendered: queued, running (live timer, Stop), passed, partial, failed, timeout, memory, cancelled,
runner failure, runner unavailable, AI unavailable.

## 5. Files changed

Everything is new. `git diff --stat` against the empty tree is in §12; key paths:
`services/runner/src/mlforge_runner/{sandbox,grading}.py`, `…/sandbox_files/{harness,child}.py`,
`services/api/src/mlforge_api/{models,worker,ai,runtime,backup,cli,main}.py`,
`…/domain/{mastery,progress,grading_service,queries}.py`, `…/routes/*.py`, `…/content/*.py`,
`…/migrations/versions/0001_initial_schema.py`, `content/curriculum/**`, `apps/web/src/**`,
`tests/e2e/**`, `infra/docker/runner.Dockerfile`, `Makefile`, `scripts/*`, `docs/*`.

Database: one migration `0001` creating all M1 tables (profiles, skills, skill_prerequisites,
lessons, lesson_progress, exercises, exercise_skill_links, drafts, hint_usages, assessments,
submissions, run_jobs, test_results, skill_evidence, skill_states, review_items, diagnostics,
diagnostic_answers, learning_sessions, ai_interactions, app_settings, audit_events). `alembic check`
confirms models and migration match.

## 6–7. Tests executed and results

See [`TEST_REPORT.md`](TEST_REPORT.md). Summary of the final runs:

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| `make lint` (ruff, ruff format, eslint, tsc) | all | 0 | — |
| Backend `pytest services` (unit, integration, §10.2 security on real Docker) | 62 | 0 | 0 |
| Frontend Vitest | 19 | 0 | 0 |
| `make smoke` | OK | — | — |
| Playwright E2E, 12 MVP scenarios, real stack, fresh DB + build | 12 | 0 | 0 |
| `make seed` content validation | 21/21 exercises, 4/4 lessons, diagnostic | 0 | — |

Measured latency: GET p95 ≤ 21 ms (target 500 ms); Run end-to-end p95 757 ms (target 10 s).

## 8. Remaining limitations

* Not yet verified on **macOS + Docker Desktop + Safari** (environment was Linux/Chromium).
* No live Claude API call (no key); AI is stub-tested.
* CI workflow (`.github/workflows/ci.yml`) is in the repository; its first GitHub Actions run was
  not observed from this environment (GitHub API access here is limited) — check the Actions tab.
* Content: 4 of the planned skills; lesson prose Russian only (UI bilingual); 2 assessment variants per skill.
* Peak memory per run not measured (limit + memory-limit state shown).
* M2–M5 (AI roles/planner, labs, projects, DL, production ML) not started — shown only as planned.
* Single local user; no authentication (localhost only by design).

## 9. Security considerations

[`SECURITY.md`](SECURITY.md): threat table mapped to tests, and explicit limits — hidden test
*inputs* are necessarily inside the sandbox; harness and learner share a UID inside the container;
Docker is not a boundary for hostile public hosting (needs microVM/gVisor + auth + quotas).

## 10. Next milestone

1. Run `make setup && make test && make e2e` on the target MacBook; re-measure latency; Safari pass.
2. Check the first GitHub Actions run and fix anything environment-specific.
3. M2: add python.functions and python.dicts_sets (lessons + 5 validated tasks each), peak-memory
   metric, structured-output AI roles with "needs review" flags, AI drafting pipeline behind human review.

## 11. Local start-up

```bash
cd ml-forge
```

```bash
make setup
```

```bash
make dev
```

Then open http://127.0.0.1:3000 (API health: http://127.0.0.1:8000/health).

## 12. Commits

All on `feature/m1-learning-loop`:

| Commit | Summary |
|---|---|
| `65d32e5` | M0/M1 backend: sandbox runner, content pipeline, FastAPI learning loop |
| `88862e1` | M1 frontend: Next.js workspace wired to the real API |
| `5f87aa7` | Tests and tooling: unit, integration, sandbox security, E2E, Makefile |
| `4ee8ea5` | Docs, UI polish, benchmark, version-guard test |
| (this) | Docs updated after publishing to GitHub — see `git log` |
