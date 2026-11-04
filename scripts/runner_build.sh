#!/usr/bin/env bash
# Build the sandbox image tagged with the harness digest the API expects.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CTX="$ROOT/services/runner/src/mlforge_runner/sandbox_files"
SHA="$(cd "$ROOT" && uv run --quiet python -c 'from mlforge_runner import harness_digest; print(harness_digest())')"
docker build -f "$ROOT/infra/docker/runner.Dockerfile" --build-arg HARNESS_SHA="$SHA" -t "mlforge-runner:$SHA" "$CTX"
echo "built mlforge-runner:$SHA"
