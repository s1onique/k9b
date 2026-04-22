#!/usr/bin/env bash
# Canonical verification gate for the k9b repository.
# Runs all verification steps and emits VERIFICATION GATE: PASSED on success.
#
# FAILURE BEHAVIOR POLICY: Continue through all steps for maximum diagnostics.
# - Uses step_run_continue to track all step results
# - Uses step_check_failed to determine final exit code
# - This policy prioritizes complete diagnostics over fast failure
#
# Usage:
#   scripts/verify_all.sh          # compact output (default)
#   STEP_VERBOSE=1 scripts/verify_all.sh  # verbose output
#
# Output contract:
#   - Compact mode: one line per step (PASS/FAIL with duration)
#   - Success: VERIFICATION GATE: PASSED
#   - Failure: step name, exit code, log excerpt, log path
#
# Logs are stored in runs/verification/ with timestamped per-step files.

set -uo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"

# Source shared step runner
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/step_runner.sh
source "$SCRIPT_DIR/step_runner.sh"

# Ensure verification output directory exists
mkdir -p "$REPO_ROOT/runs/verification"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: Required interpreter '$PYTHON' not found or not executable." >&2
    echo "Create it via 'python -m venv .venv' and install dependencies." >&2
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm is not installed or not on PATH." >&2
    echo "Install Node.js/npm before running frontend checks." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Run verification steps (use step_run_continue to continue on failure
# and track all results before finalizing)
# ---------------------------------------------------------------------------

step_run_continue "ruff-lint" "Running Ruff lint" "$PYTHON" -m ruff check src tests
step_run_continue "unit-tests" "Running unit tests" "$PYTHON" -m unittest discover tests
step_run_continue "mypy" "Running mypy" "$PYTHON" -m mypy src tests

# Frontend steps (use pushd/popd to stay in same shell context)
pushd "$REPO_ROOT/frontend" >/dev/null
step_run_continue "npm-ci" "Installing frontend deps (npm ci)" npm ci
step_run_continue "npm-test-ui" "Running frontend UI tests" npm run test:ui
step_run_continue "npm-build" "Building frontend" npm run build
popd >/dev/null

# ---------------------------------------------------------------------------
# Finalize
# ---------------------------------------------------------------------------

# Use the tracked failure state to determine exit code
if step_check_failed; then
    step_finalize 1
else
    step_finalize 0
fi
