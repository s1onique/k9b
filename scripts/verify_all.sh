#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"
VERIFICATION_STEP="initialization"

on_error() {
  local exit_code=${1:-1}
  local step="${2:-unknown}"
  trap - ERR
  echo "VERIFICATION GATE: FAILED (step: $step, exit: $exit_code)" >&2
  exit "$exit_code"
}

trap 'on_error $? "$VERIFICATION_STEP"' ERR

fail() {
  echo "ERROR: $*" >&2
  return 1
}

run_step() {
  local step_id="$1"
  local message="$2"
  shift 2
  VERIFICATION_STEP="$step_id"
  echo "$message"
  "$@"
}

VERIFICATION_STEP="python-check"
if [[ ! -x "$PYTHON" ]]; then
  fail "Required interpreter '$PYTHON' not found or not executable. Create it via 'python -m venv .venv' and install dependencies."
fi

VERIFICATION_STEP="npm-check"
if ! command -v npm >/dev/null 2>&1; then
  fail "npm is not installed or not on PATH. Install Node.js/npm before running frontend checks."
fi

run_step "ruff-lint" "Running Ruff lint" "$PYTHON" -m ruff check src tests
run_step "unit-tests" "Running unit tests" "$PYTHON" -m unittest discover tests
run_step "mypy" "Running mypy" "$PYTHON" -m mypy src tests

VERIFICATION_STEP="frontend-dir"
pushd "$REPO_ROOT/frontend" >/dev/null

run_step "npm-ci" "Installing frontend deps (npm ci)" npm ci
run_step "npm-test-ui" "Running frontend UI tests" npm run test:ui
run_step "npm-build" "Building frontend" npm run build

popd >/dev/null
VERIFICATION_STEP="completion"
echo "VERIFICATION GATE: PASSED"
