#!/usr/bin/env bash
# Local development: FastAPI (with embedded worker) on :8000 and Next.js on :3000.
# Both listen on 127.0.0.1 only. Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
uv run python -m mlforge_api.cli migrate >/dev/null
if ! uv run python -m mlforge_api.cli runner-check >/dev/null 2>&1; then
  echo "WARNING: code runner unavailable (Docker not running or image not built: make runner-build)." >&2
  echo "         Lessons and progress work; Run/Submit will report 'Runner unavailable'." >&2
fi
trap 'kill 0' EXIT INT TERM
uv run uvicorn mlforge_api.asgi:app --host 127.0.0.1 --port 8000 --reload --reload-dir services &
(cd apps/web && NEXT_TELEMETRY_DISABLED=1 pnpm dev) &
echo "ML Forge: http://127.0.0.1:3000  (API http://127.0.0.1:8000/health)"
wait
