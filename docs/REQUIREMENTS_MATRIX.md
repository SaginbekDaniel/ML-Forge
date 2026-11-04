# Requirements traceability matrix

**Source:** `ML_FORGE_TECHNICAL_SPEC.md` v1.0 (04.11.2026), read in full (§1–§18). The request
mentioned a PDF; **no PDF was supplied** in the session or found on disk — the Markdown version was
the only specification available. References below are spec section numbers, not PDF pages.

Status: **COMPLETE** (implemented and verified by the named check) · **PARTIAL** · **MISSING** ·
**BLOCKED** (needs something unavailable here). Priority: P0 = M1 acceptance, P1 = M2, P2 = M3+.

| ID | Requirement | § | Status | Code | Validation | Missing work | Pri |
|---|---|---|---|---|---|---|---|
| R-01 | Profile + configurable daily load (default 120 min, 5–6 days) | 1.1, 8 | COMPLETE | `routes/profile.py`, `app/onboarding`, `app/settings` | `test_profile_lifecycle`, E2E #1 | — | P0 |
| R-02 | Works without Claude API | 1.1, 5.2, 14 | COMPLETE | `ai.py` | `test_ai_unavailable…`, E2E #8 | — | P0 |
| R-03 | Diagnostic: survey + practical task → personal route | 1.2(1), M1 | COMPLETE | `routes/profile.py`, `diagnostic.yaml`, `diag.count_even` | `test_diagnostic_flow`, E2E #1 | Route is a per-skill recommendation; adaptive planner is M2 | P0 |
| R-04 | Correctness only from executable tests | 1.2(2), 4.3 | COMPLETE | `mlforge_runner/grading.py`, `grading_service.py` | runner + API tests | — | P0 |
| R-05 | Progress survives browser/server/computer restart | 1.2(3), 14 | COMPLETE | SQLite WAL, drafts | `test_progress_and_draft_survive_api_restart`, E2E #5, #6 | — | P0 |
| R-06 | Stepwise hints, no full answer first | 1.2(4), 5.1 | COMPLETE | 3-level static hints, ordered server-side | `test_hints_are_progressive…` | AI hint coach (M2) | P0 |
| R-07 | Unseen task without help (independent assessment) | 1.2(5), 3.3, 4.3 | COMPLETE | `routes/practice.py` assessments | `test_independent_assessment…`, `test_second_assessment_uses_unseen_variant`, E2E #10 | 2 variants/skill; more variants needed long-term | P0 |
| R-08 | Advanced modules end with reproducible projects | 1.2(6), 12 | MISSING | — | — | M3+ | P2 |
| R-09 | Transparent report: mastered / evidence / review / errors / next | 1.2(7), 13 | PARTIAL | `app/skills`, dashboard insights, export | E2E #4, API tests | Rolling-window trends; project evidence | P1 |
| R-10 | Vertical slice first (lesson→code→run→tests→score→skill→review) | 2 M1 | COMPLETE | whole stack | E2E #1–#10 | — | P0 |
| R-11 | ≥12 quality Python tasks with multiple tests incl. edge cases | 2 M1 | COMPLETE (21) | `content/curriculum/exercises` | `make seed` validation, `test_real_curriculum…` | — | P0 |
| R-12 | ≥4 topic explanations (I/O & types, branching, loops, strings/lists) | 2 M1 | COMPLETE | `content/curriculum/lessons` | seed validation of examples & answers | English translations of lesson text | P0 |
| R-13 | Basic review plan without AI | 2 M1, 3.4 | COMPLETE | `domain/progress.py` | `test_review_cycle`, unit tests | — | P0 |
| R-14 | Automated backend/frontend/E2E tests | 2 M1, 15 | COMPLETE | `services/*/tests`, `apps/web/src/**/*.test.ts`, `tests/e2e` | `TEST_REPORT.md` | First CI run on GitHub not observed | P0 |
| R-15 | Versioned DAG of competencies with skill IDs | 3, 3.1 | COMPLETE | `skills.yaml`, `loader.find_cycle` | `test_prerequisite_graph…`, `test_cycle_in_content_is_rejected` | Only Python Core track has content | P0 |
| R-16 | Per-skill status, mastery_score, last_evidence_at, next_review_at, evidence, hint_dependency, failure_tags | 3.3 | COMPLETE | `models.SkillState`, `domain/progress.py` | API tests | — | P0 |
| R-17 | Mastery rule (2 tasks ≥85 %, one hint-free, independent check) | 3.3 | COMPLETE | `domain/mastery.py` | `test_mastery.py` (10 cases) | Concept explanations graded by rubric (M2) | P0 |
| R-18 | AI cannot unlock skills alone; viewing theory ≠ progress | 3.3 | COMPLETE | evidence filter `verified_by_tests` | `test_lesson_check_and_complete` | — | P0 |
| R-19 | Reviews 1/3/7/14/30 days, adaptive; keep "mastered earlier" | 3.4 | COMPLETE | `next_review_step`, `needs_review` state | unit + `test_review_cycle` | — | P0 |
| R-20 | Exercise types: write, debug, predict output | 4.1 | PARTIAL | `type: write_code/debug`; predict-output in lessons & diagnostic | seed | refactor, math, EDA/SQL, experiment, evaluation, architecture, defense | P1/P2 |
| R-21 | Task contract (id, version, prompt, starter, tests, hints, solution, license, review_status…) | 4.2 | COMPLETE | `content/schema.py` | schema tests | — | P0 |
| R-22 | Solution & hidden tests never in lesson API | 4.2 | COMPLETE | `routes/practice.exercise_out` | API test, E2E #9 | — | P0 |
| R-23 | Version bump on change; old attempts keep their version | 4.2 | COMPLETE | `seed.py` guard, composite PKs | manual check + seed guard | Automated test for the guard | P0 |
| R-24 | Reference solution + 1–2 wrong solutions validated; inactive until validated | 4.2 | COMPLETE | `content/validate.py` | `make seed` (21/21) | — | P0 |
| R-25 | Result: passed/total, edge cases, runtime, memory, error_type | 4.3 | PARTIAL | `RunJob` fields | API tests | Peak memory is not measured (limit is shown) | P0 |
| R-26 | Attempt count not negative; track recurring error concepts | 4.3, 13 | COMPLETE | `failure_tags` from test tags & error classes | API tests | — | P0 |
| R-27 | Independent mode disables hints/AI | 4.3 | COMPLETE | `hint_block_reason`, mentor guard | API test, E2E #10 | — | P0 |
| R-28 | Error display: status, duration, truncated stdout/stderr, hidden without inputs, next step | 4.4 | COMPLETE | `components/practice/results.tsx` | E2E #3, #7 | — | P0 |
| R-29 | AI roles: tutor, hint coach, reviewer, interviewer, planner, research guide | 5.1 | PARTIAL | `ai.py` (hint coach / error explainer) | `test_ai.py` (stub) | Other roles; real-key run (BLOCKED: no key) | P1 |
| R-30 | Key server-only; never in bundle/logs | 5.2 | COMPLETE | `config.py`, log redaction | `test_ai_unavailable…key_never_leaks` | — | P0 |
| R-31 | Structured outputs, timeouts, retries, fallback | 5.2 | PARTIAL | SDK timeout 30 s, 2 retries, server-side refusal fallback | stub tests | JSON-schema outputs for rubric/planner (M2) | P1 |
| R-32 | `verified_by_tests` / `ai_feedback` / `user_self_report` separation | 5.2 | COMPLETE | `SkillEvidence.verification`, UI tags | API tests | — | P0 |
| R-33 | Untrusted learner content; no AI tools/FS | 5.2 | COMPLETE | `ai.SYSTEM_PROMPT`, no tools | `test_ai.py` | — | P1 |
| R-34 | "Send code to AI" toggle, off by default | 5.2 | COMPLETE | `send_code_to_ai` setting | settings UI | — | P1 |
| R-35 | AI budget: enable, model, requests/day, USD/day, context; token+cost telemetry | 5.3 | COMPLETE | `ai.py`, `ai_interactions` | `test_ai.py` | Model picker in UI (env only) | P1 |
| R-36 | Professional dark UI, light optional | 6 | COMPLETE | `globals.css` tokens | screenshots | — | P0 |
| R-37 | Navigation: Dashboard, Roadmap, Learn, Practice, Review, Skills, Settings | 6.1 | COMPLETE | `app/*` | E2E | — | P0 |
| R-38 | Labs, Projects, AI Mentor pages | 6.1 | PARTIAL | Mentor is contextual in Practice | — | Labs/Projects are M3 (not faked in nav) | P2 |
| R-39 | Practice 42/58 ≥1200 px; tabs below; 390 px usable | 6.2 | COMPLETE | `practice/[exerciseId]/page.tsx` | E2E #12 (390 + 768) | — | P0 |
| R-40 | All UI states incl. unavailable AI/runner | 6.2 | COMPLETE | `displayState`, `RunnerUnavailable` | vitest, `test_runner_unavailable_is_honest` | — | P0 |
| R-41 | Draft saved before run and on reload | 6.2 | COMPLETE | autosave + `pagehide` keepalive + submit stores draft | E2E #5 | — | P0 |
| R-42 | Keyboard-first: Tab, Ctrl/Cmd+Enter, labels, focus, contrast | 6.3 | COMPLETE | skip link, roving tabs, editor help | E2E #11 | Formal contrast audit tool not run | P0 |
| R-43 | Show source of evaluation | 6.3 | COMPLETE | "Проверено тестами", AI tag | E2E | — | P0 |
| R-44 | Monorepo structure §7.3; modules separated | 7.3 | COMPLETE | repo layout | — | `projects`, `analytics` as separate modules are thin | P0 |
| R-45 | Browser never talks to Claude/Docker; backend is source of truth | 7.2 | COMPLETE | Next rewrites → API only | architecture | — | P0 |
| R-46 | Data model §8 with FKs, indexes, migrations | 8 | PARTIAL | `models.py`, `0001_initial_schema.py` | `alembic check` | `projects`, `project_artifacts` tables (M3) | P0 |
| R-47 | Secrets not in `app_settings`; backups exclude secrets | 8 | COMPLETE | `backup.py` | test | — | P0 |
| R-48 | API contracts §9 with uniform errors + request_id | 9 | PARTIAL | `routes/*`, `errors.py` | `test_validation_errors_are_uniform` | `/projects*` (M3) | P0 |
| R-49 | Idempotent submit; reject non-existent versions | 9 | COMPLETE | `client_request_id` | `test_double_submit_is_idempotent`, `test_locked_skill_and_bad_versions…` | — | P0 |
| R-50 | Sandbox policy §10.1 | 10.1 | COMPLETE | `sandbox.py`, `runner.Dockerfile` | `test_sandbox_security.py` | Custom seccomp/AppArmor profile | P0 |
| R-51 | Sandbox security tests §10.2 (7 cases) | 10.2 | COMPLETE | `services/runner/tests/test_sandbox_security.py` | 10 tests pass on real Docker | — | P0 |
| R-52 | Listen on 127.0.0.1 only | 10.2 | COMPLETE | `scripts/dev.sh`, `package.json` | — | — | P0 |
| R-53 | Content in Git with schema; lesson structure (analogy, definition, 2 examples, mistake, 2–4 tasks, recap) | 11 | COMPLETE | `LessonSpec` | `test_lessons_…`, seed | — | P0 |
| R-54 | AI drafting pipeline generate→check→run→mutate→review→publish | 11 | PARTIAL | validation stages exist | — | AI generation step (M2) | P1 |
| R-55 | English terms next to Russian | 11 | COMPLETE | `terms` per lesson | UI | — | P0 |
| R-56 | ML labs, datasets with license + SHA-256, project ladder | 12 | MISSING | — | — | M3–M5 | P2 |
| R-57 | Anti-illusion analytics; no fake percentages; insufficient data labelling | 13 | COMPLETE | `rate()` with `MIN_SAMPLE`, confirmation levels | UI | Rolling trends | P1 |
| R-58 | Local first / offline | 14 | COMPLETE | no CDNs, system fonts | build | — | P0 |
| R-59 | GET p95 < 500 ms; Run < 10 s | 14 | COMPLETE (measured) | — | `scripts/bench.py`, `TEST_REPORT.md` | Re-measure on target Mac | P0 |
| R-60 | Compatibility Chrome/Safari on Mac; 390/768/1440 | 14 | PARTIAL | — | Chromium E2E at 390/768/1440 | **Safari/WebKit not tested** (BLOCKED: no WebKit here) | P0 |
| R-61 | Structured logs with request/job id | 14 | COMPLETE | `logging_setup.py` | logs | — | P0 |
| R-62 | Backups, test restore, backup before destructive migration | 14 | COMPLETE | `backup.py`, `runtime.migrate` | `test_backup_restore_and_export` | — | P0 |
| R-63 | Make targets §16.1 | 16.1 | COMPLETE | `Makefile` | used in report | — | P0 |
| R-64 | Docs: README, ARCHITECTURE, SECURITY, TEST_REPORT, .env.example, ADR, plan | 16 | COMPLETE | `docs/` | — | — | P0 |
| R-65 | GitHub repo, workflow, merge | 16 | PARTIAL | `.github/workflows/ci.yml`, pushed to `SaginbekDaniel/ML-Forge`, merged to `main` | push verified | First Actions run not observed from this environment | P0 |
| R-66 | PyTorch/DL, CV, LLM, production ML tracks | M4–M5 | MISSING | planned skills only | — | M4–M5 | P2 |

## Ambiguities and interpretations

* **"Timeout 5 seconds"** (§10.1) is applied to *learner code execution* (sum over tests, 2 s per
  test), not to container start-up; the container has an additional hard wall clock (budget + 15 s).
* **"Independent check on an unseen variant"** (§3.3): each skill has 2 assessment variants; once all
  were opened, a further pass is accepted but flagged `passed_on_previously_seen_variant`, shown in
  the UI. Strictly refusing would dead-end the learner until more variants exist.
* **Diagnostic → "personal route"** (§1.2): the diagnostic produces per-skill recommendations
  (start with the lesson vs. try the assessment early); it does not unlock skills, because §3.3
  forbids progress from self-report.
* **"Explanation in own words"** (§3.3.4): debug tasks collect an explanation stored with the attempt
  and labelled as not graded; rubric grading is M2 and will be marked "needs review" when uncertain.
* **Memory metric** (§4.3): peak memory is not measured per run (Docker does not report it cheaply
  after exit); the UI reports the limit and an explicit memory-limit state.
