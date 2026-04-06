#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

if [[ ! -x "$PYTHON" ]]; then
  fail "Required interpreter '$PYTHON' not found or not executable. Create it via 'python -m venv .venv' and install dependencies."
fi

if ! command -v npm >/dev/null 2>&1; then
  fail "npm is not installed or not on PATH. Install Node.js/npm before running frontend checks."
fi

echo "Running Ruff lint"
"$PYTHON" -m ruff check src tests

echo "Running unit tests"
"$PYTHON" -m unittest discover tests

echo "Running mypy"
"$PYTHON" -m mypy src tests

pushd "$REPO_ROOT/frontend" >/dev/null
echo "Installing frontend deps (npm ci)"
npm ci

echo "Running frontend UI tests"
npm run test:ui

echo "Building frontend"
npm run build
popd >/dev/null

echo "All checks passed"
