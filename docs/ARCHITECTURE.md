# ML Forge — Architecture

```
Browser (Next.js 16, React 19, CodeMirror 6)            127.0.0.1:3000
   │  same-origin fetch /api/v1/*, /health  (Next rewrites → API; no CORS)
   ▼
FastAPI (services/api)                                  127.0.0.1:8000
   ├─ routes/        HTTP only: validation, access rules, serialisation
   ├─ domain/        mastery policy (pure), progress & reviews, grading service, queries
   ├─ content/       YAML schema, loader (+ DAG cycle check), sandbox validation, seeding
   ├─ ai.py          optional mentor adapter (Anthropic SDK), budgets, telemetry
   ├─ worker.py      embedded job worker threads (claim → sandbox → finalize)
   └─ SQLite (WAL)   data/mlforge.db  ← Alembic migrations, backups in data/backups
          │
          ▼ docker run (stdin/stdout only, no mounts)
services/runner (mlforge_runner) — no web/DB dependencies
   ├─ sandbox.py     DockerSandbox: limits, health, cancel, orphan cleanup
   ├─ grading.py     host-side, type-strict comparison → TestOutcome (hidden tests redacted)
   └─ sandbox_files/ harness.py + child.py baked into image mlforge-runner:<sha>
```

## Request → result path (the M1 loop)

1. `GET /api/v1/exercises/{id}` returns the prompt, starter code, public tests, *count* of hidden
   tests, revealed hints and the server draft. Never the reference solution, wrong solutions or
   hidden test data.
2. The editor autosaves (`PUT …/draft`, debounced, plus `keepalive` flush on `pagehide`).
3. `POST /api/v1/submissions {exercise_id, exercise_version, source_code, kind, mode, client_request_id}`
   checks: current version, active (validated), skill unlocked, mode rules (assessment/review/
   diagnostic), runner health → stores submission + `run_job(queued)` → `202 {submission_id, job_id}`.
   A repeated `client_request_id` returns the same job (`200`, double-click safe).
4. Worker claims the job, builds the test list (`run` = program run + public tests; `submit` = all
   tests), runs the sandbox, then `finalize_job`:
   * grades observations on the host, stores `test_results` (hidden ones redacted at write time);
   * for `submit`: appends `skill_evidence` (`verified_by_tests`, score, hint level), resolves an
     active assessment or review, recomputes `skill_states`, schedules the first review on mastery.
5. The UI polls `GET /api/v1/jobs/{id}` (400 ms) and renders one of the states
   queued · running · passed · partial · failed · timeout · memory · cancelled · runner failure.

## Mastery (spec §3.3), `domain/mastery.py`

A skill is **mastered** when, from test-verified evidence only:
1. ≥ `min_distinct_exercises` (2) different practice/review exercises scored ≥ 85 %;
2. at least one of them with **no hints** revealed for that exercise version;
3. an **independent assessment** (separate, initially unseen variant; hints/AI disabled server-side;
   first Submit counts) scored ≥ 85 %.

States: `planned` (no content) · `locked` (a prerequisite is not mastered) · `available` ·
`in_progress` · `mastered` · `needs_review` (mastered earlier, review due/failed — still satisfies
prerequisites). Reading a lesson, self-assessment and diagnostic results never create mastery
evidence. Policy values live in `content/curriculum/skills.yaml`.

## Spaced repetition (§3.4)

Intervals 1 → 3 → 7 → 14 → 30 days. A clean pass advances one step, a pass with hints repeats the
interval, a miss restarts. Starting a review picks the least-recently practised exercise and
disables hints for it until the review is resolved by a graded submission.

## Content pipeline (§4.2, §11)

`make seed` = schema validation → graph checks (unknown refs, cycles, every active skill has a lesson,
≥2 practice tasks and an assessment variant) → **sandbox validation** (reference passes; wrong
solutions and starter fail; lesson example outputs, predict-output answers and diagnostic answers
match real execution) → versioned upsert. Re-validation happens automatically when the harness
digest changes.

## Frontend structure (`apps/web/src`)

* `lib/` — typed API client (`ApiError` with server `error_code`), `useApi` hook, i18n (ru default,
  en; key-parity tested), theme tokens, media hook.
* `components/` — shell (sidebar ≥1024 px / top bar below), UI primitives (all colours/radii from
  CSS tokens in `globals.css`), CodeMirror wrapper, practice result/hint/attempt/mentor panels.
* `app/` — onboarding, dashboard, roadmap, learn, practice (42/58 split ≥1200 px, tabbed below),
  assessment, review, skills, settings.

## Observability

JSON logs on stdout with `request_id` (also returned as `x-request-id`) and `job_id`; fields named
like keys/tokens/secrets/source code are redacted. Every error response carries
`{error_code, message, request_id, details}`.
