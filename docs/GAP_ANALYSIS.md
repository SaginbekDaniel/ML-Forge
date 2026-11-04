# Gap analysis

## Starting point (evidence)

* Working directory `/home/user` was empty and not a Git repository.
* The GitHub URL in the request was the literal placeholder `[INSERT GITHUB REPOSITORY URL]`.
* The session's GitHub connector listed **0 repositories**; `gh auth status` reported an invalid
  `GH_TOKEN`. No existing ML Forge code could be inspected.
* No PDF was attached or present on disk; the specification was available as
  `ML_FORGE_TECHNICAL_SPEC.md` and was read in full.

**Consequence:** there was no existing implementation to audit, preserve or regress. Per spec §M0
("if there is no repository, create a monorepo"), a new repository was created on branch
`feature/m1-learning-loop`. The owner later supplied https://github.com/SaginbekDaniel/ML-Forge,
which was empty; the work was pushed there and fast-forwarded into `main`.

## Progress overview (criteria-based, not a guessed percentage)

| Milestone | Acceptance criteria (spec) | Met | Notes |
|---|---|---|---|
| M0 | repo, ADR, frontend/backend/DB/migrations/health, pinned env | 6 / 6 | |
| M1 | §15.4: 8 acceptance conditions | 7 / 8 met, 1 partial | Reproducible start "from scratch per README" verified in this Linux container, **not yet on a Mac** |
| M1 E2E | §15.2: 12 scenarios | 12 / 12 automated & passing (Chromium) | Safari not tested |
| M2 | AI roles, planner, 30–40 tasks, 8 lessons, cost controls | cost controls + adapter only | |
| M3–M5 | labs, projects, DL, production | 0 | roadmap only, no fake UI |

## Gaps by status

### BLOCKED

| Gap | Current | Desired | Root cause | Next step |
|---|---|---|---|---|
| Real Claude API call | Adapter + stub tests | Verified live call with cost telemetry | No `ANTHROPIC_API_KEY` in this environment (by design optional) | Put the key in `.env`, ask a question in Practice → Mentor; check `ai_interactions` |
| Safari / macOS verification | Chromium on Linux | Safari + Docker Desktop on Mac | Environment is Linux, no WebKit | Run `make setup && make e2e` on the Mac; add a WebKit project to Playwright |

### PARTIAL

| Gap | Evidence | Files | Approach | Acceptance test |
|---|---|---|---|---|
| Per-run peak memory metric (§4.3) | Only limit + memory-limit state | `sandbox.py`, `harness.py` | Read `ru_maxrss` of each child via `resource.getrusage(RUSAGE_CHILDREN)` in the harness and report it | Test asserting `peak_kb` grows with a 50 MB allocation |
| Exercise types (§4.1) | write_code, debug, predict-output | `content/schema.py` | Add `refactor` (behaviour-preserving tests + metric), math (float tolerance already exists), SQL (sqlite3 in sandbox) | Seed validation per type |
| AI roles (§5.1) | hint coach / error explainer | `ai.py`, `routes/system.py` | Structured outputs (`output_config.format`) for rubric grading & planner; "needs review" when uncertain | Stub tests for schema validation; one live smoke test |
| Analytics trends (§13) | totals + insufficient-data flags | `routes/progress.py` | Rolling 7/30-day windows with n shown | API tests on synthetic evidence |
| English lesson content | UI fully bilingual; lessons Russian with English terms | `content/curriculum/lessons` | `title_en/…_en` fields or per-locale files | i18n parity test for content |
| Assessment variants | 2 per skill | `content/curriculum/exercises` | M2 AI drafting pipeline + human review | Seed validation |

### MISSING (planned, intentionally not faked)

Labs and Projects (§6.1 items 5–6, §12), datasets with licences and SHA-256, DL/CV/LLM tracks,
production-ML track, oral defense, GitHub-ready project export. They appear on the roadmap only as
`planned` skills with "content does not exist yet".

## Technical debt / risks noticed

* Embedded worker runs in the API process: fine locally; a standalone worker process is a small
  change (`JobWorker` has no HTTP dependency) if isolation or scaling is needed.
* `skill_states` are recomputed on reads when reviews exist (cheap for tens of skills; revisit at
  hundreds).
* Hidden test *inputs* are inside the sandbox (inherent); see `SECURITY.md`.
* Next rewrites are build-time; a runtime proxy route would allow changing the API origin without
  rebuilding.
