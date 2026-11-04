# ML Forge — reproducible developer commands (spec §16.1).
.PHONY: setup dev runner-build seed migrate lint typecheck test test-backend test-frontend e2e smoke backup

setup:          ## install & verify dependencies, build sandbox, migrate, seed
	./scripts/setup.sh

dev:            ## API :8000 + web :3000 (127.0.0.1 only)
	./scripts/dev.sh

runner-build:   ## build the sandbox Docker image (tag = harness digest)
	./scripts/runner_build.sh

seed:           ## validate content (statically + in the sandbox) and load it
	uv run python -m mlforge_api.cli seed

migrate:
	uv run python -m mlforge_api.cli migrate

lint:           ## ruff + eslint + tsc
	uv run ruff check services scripts
	uv run ruff format --check services scripts
	cd apps/web && pnpm lint && pnpm typecheck

typecheck:
	cd apps/web && pnpm typecheck

test: test-backend test-frontend  ## unit + integration + sandbox security

test-backend:
	uv run pytest services -q

test-frontend:
	cd apps/web && pnpm test

e2e:            ## Playwright on the real stack (fresh DB, isolated ports 8100/3100)
	cd tests/e2e && pnpm exec playwright test

smoke:          ## end-to-end smoke on a throwaway DB + sandbox health
	uv run python scripts/smoke.py

backup:         ## consistent SQLite backup into data/backups (no secrets)
	uv run python -m mlforge_api.cli backup
