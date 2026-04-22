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
#   scripts/verify_all.sh --json   # JSON output to stdout only
#   STEP_VERBOSE=1 scripts/verify_all.sh  # verbose output
#
# Output contract:
#   - Compact mode: one line per step (PASS/FAIL with duration)
#   - Success: VERIFICATION GATE: PASSED
#   - Failure: step name, exit code, log excerpt, log path
#   - JSON mode: pure JSON summary on stdout (no progress output)
#
# Logs are stored in runs/verification/ with timestamped per-step files.

set -uo pipefail

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

STEP_JSON_MODE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)
            STEP_JSON_MODE=1
            export STEP_JSON_MODE
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--json]"
            echo "  --json   Emit only JSON summary to stdout"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 [--json]" >&2
            exit 1
            ;;
    esac
done

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"

# Source shared step runner
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/step_runner.sh
source "$SCRIPT_DIR/step_runner.sh"

# ---------------------------------------------------------------------------
# Recursion protection
# ---------------------------------------------------------------------------

if [[ -n "${VERIFY_ALL_ACTIVE:-}" ]]; then
    echo "ERROR: verify_all.sh recursion detected." >&2
    echo "VERIFY_ALL_ACTIVE is already set (value: $VERIFY_ALL_ACTIVE)." >&2
    echo "Do not invoke verify_all.sh from within a verify_all context." >&2
    exit 2
fi
export VERIFY_ALL_ACTIVE=1

# ---------------------------------------------------------------------------
# Single-instance lock
# ---------------------------------------------------------------------------

_LOCK_DIR="$REPO_ROOT/.verify_lock"
_LOCK_FILE="$_LOCK_DIR/pid"

_acquire_lock() {
    mkdir -p "$_LOCK_DIR" 2>/dev/null || {
        echo "ERROR: Cannot create lock directory '$_LOCK_DIR'." >&2
        exit 3
    }
    
    if [[ -f "$_LOCK_FILE" ]]; then
        local pid
        pid=$(cat "$_LOCK_FILE" 2>/dev/null)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "ERROR: Another verification run is active (PID: $pid)." >&2
            echo "Wait for it to complete or kill it before running again." >&2
            exit 4
        fi
        # Stale lock - remove it
        rm -f "$_LOCK_FILE"
    fi
    
    echo $$ > "$_LOCK_FILE"
}

_release_lock() {
    rm -f "$_LOCK_FILE"
}

_acquire_lock
trap _release_lock EXIT

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
step_run_continue "unit-tests" "Running unit tests" env VERIFY_ALL_ACTIVE=1 RUN_FULL_VERIFY_TEST= "$PYTHON" -m unittest discover tests
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
