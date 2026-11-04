# ML Forge

Local, personal learning platform that takes one learner from Python basics toward ML engineering.
Learning loop: **explanation → own attempt → executable tests → error analysis → repetition →
independent check**. Correctness is decided by real tests in an isolated Docker sandbox — never by
an LLM. The AI mentor is optional; everything else works offline and without an API key.

> **Current state: M1 (working learning loop) is implemented and verified on Linux/Chromium.**
> 4 Python Core skills, 4 lessons, 21 sandbox-validated exercises, independent assessments,
> spaced repetition, diagnostic, honest analytics. Labs, projects and ML tracks (M3–M5) are
> **not built yet** and are shown only as "planned" on the roadmap. See
> [`docs/IMPLEMENTATION_REPORT.md`](docs/IMPLEMENTATION_REPORT.md).

## Requirements

| Tool | Version | Notes |
|---|---|---|
| macOS (Apple Silicon or Intel) or Linux | — | Windows untested |
| [Docker Desktop](https://docs.docker.com/desktop/) | 4.x / Engine 24+ | Must be running to execute code |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.5 | Installs Python 3.12 automatically |
| Node.js | ≥ 20 (22 tested) | |
| pnpm | 10 | `corepack enable` |

## Quick start

```bash
make setup
```

```bash
make dev
```

Open **http://127.0.0.1:3000**. First run asks for a name, offers a short diagnostic, then shows the
roadmap. Both servers bind to `127.0.0.1` only.

`make setup` installs dependencies, builds the sandbox image, migrates the database and seeds
content (seeding *runs every reference and wrong solution in the sandbox* — ~30 s the first time).

### Optional: AI mentor

```bash
cp .env.example .env   # then set ANTHROPIC_API_KEY=...
```

Restart `make dev`. Limits (requests/day, USD/day, whether code may be sent) are in **Settings**.
The key stays in the backend process; it is never sent to the browser, logged or backed up.

## Commands

| Command | What it does |
|---|---|
| `make setup` | Check tools, install deps, build sandbox image, migrate, seed |
| `make dev` | API on :8000 (with embedded worker) + web on :3000 |
| `make runner-build` | Build `mlforge-runner:<harness-sha>` |
| `make seed` | Validate content (schema, DAG, sandbox runs) and load it; exit 2 if anything is not validated |
| `make lint` | ruff (check + format) · eslint · tsc |
| `make test` | Backend unit + integration + sandbox security (needs Docker) · frontend unit |
| `make e2e` | Playwright: 12 MVP scenarios on the real stack (fresh DB on ports 8100/3100) |
| `make smoke` | End-to-end smoke on a throwaway DB |
| `make backup` | Consistent SQLite backup to `data/backups/` |
| `uv run python scripts/bench.py` | Latency benchmark against a running API |
| `uv run python -m mlforge_api.cli restore <file>` | Restore with schema check + confirmation |

## How it works

```
apps/web (Next.js) ──/api/v1──► services/api (FastAPI) ──► SQLite (data/mlforge.db)
                                        │ embedded worker
                                        ▼
                     services/runner ──docker run──► mlforge-runner (no network, read-only,
                                                     non-root, 256 MB, 64 pids, 5 s budget)
content/curriculum/*.yaml  ── make seed (validated in the sandbox) ──► DB (versioned rows)
```

* **Mastery** of a skill = 2 different exercises at ≥85 % tests, one of them without hints, plus a
  passed independent assessment on an unseen variant (hints and AI off). Reading lessons or
  self-assessment never counts.
* **Reviews** after 1 → 3 → 7 → 14 → 30 days; a miss restarts the interval but the skill stays
  "mastered earlier".
* **Hidden tests**: their inputs are never shown in the UI or API; expected outputs never even
  enter the sandbox (grading is on the host).

Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/SECURITY.md`](docs/SECURITY.md) ·
[`docs/adr/0001-stack-and-execution-model.md`](docs/adr/0001-stack-and-execution-model.md).

## Repository layout

```
apps/web/              Next.js UI (App Router, TypeScript strict, Tailwind tokens, CodeMirror 6)
services/api/          FastAPI app, SQLAlchemy models, Alembic migrations, domain logic, tests
services/runner/       Docker sandbox driver, in-container harness, host-side grading, tests
content/curriculum/    skills.yaml (DAG + mastery policy), lessons/, exercises/, diagnostic.yaml
infra/docker/          runner.Dockerfile
tests/e2e/             Playwright suite and stack orchestration
scripts/               setup, dev, runner build, smoke, bench
docs/                  requirements matrix, gap analysis, plan, ADRs, architecture, security, reports
```

## Adding an exercise

1. Create `content/curriculum/exercises/<id>.yaml` (copy an existing one): prompt, starter code,
   ≥3 tests (≥1 public, ≥1 hidden, ≥1 tagged `edge_case`), 3 hints, reference `solution`,
   1–3 `wrong_solutions`, `review_status: reviewed` after you have reviewed it.
2. `make seed`. The exercise becomes active only if the reference passes every test and every wrong
   solution and the starter fail at least one.
3. To change a published exercise, bump `version` — earlier attempts stay attached to the old one.

## Troubleshooting

* **"Runner unavailable"** — start Docker Desktop, then `make runner-build`. If the image is
  "outdated", the harness changed: rebuild.
* **Exercises missing** — run `make seed`; it prints which checks failed.
* **Changing `MLFORGE_API_ORIGIN`** requires rebuilding the web app (Next rewrites are build-time).

## Data & privacy

All data stays in `data/` (git-ignored). Export: Settings → Export JSON/CSV. Nothing is sent
anywhere unless you configure the AI key; even then only the current task, test results and — if
you enable it — your exercise code.
