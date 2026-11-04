#!/usr/bin/env bash
# One-time setup: checks tools, installs deps, builds the sandbox image, migrates and seeds.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1 — $2" >&2; exit 1; }; }
need uv "https://docs.astral.sh/uv/ (brew install uv)"
need node "Node.js 20+ (brew install node)"
need pnpm "corepack enable  (or: npm i -g pnpm)"
need docker "Docker Desktop: https://docs.docker.com/desktop/"
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)' || { echo "Node 20+ required" >&2; exit 1; }
uv sync
(cd apps/web && pnpm install --frozen-lockfile)
(cd tests/e2e && pnpm install --frozen-lockfile)
if docker info >/dev/null 2>&1; then
  ./scripts/runner_build.sh
else
  echo "WARNING: Docker is not running — start Docker Desktop, then run: make runner-build && make seed" >&2
fi
uv run python -m mlforge_api.cli migrate
uv run python -m mlforge_api.cli seed || echo "seed reported problems (see above)" >&2
[ -f .env ] || cp .env.example .env
echo "Setup complete. Start with: make dev"
