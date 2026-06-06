#!/usr/bin/env bash
# Runtime gate verifier for health-loop structured output hygiene.
#
# This script captures stdout and stderr from a representative health-loop path
# and verifies that all output lines are valid JSON objects (structured output).
#
# Scope: Verifies that health-loop execution does not leak arbitrary stdout/stderr
# lines like raw "Forbidden" errors, tracebacks, or default logger output.
#
# Required behavior:
# - Must fail if captured stdout/stderr contains unstructured lines
# - Must fail if the offline health-loop runtime command exits non-zero
# - Structured-output checking runs regardless of command exit status
#
# Usage:
#   ./scripts/verify_health_loop_structured_output.sh
#
# Exit codes:
#   0 - all output lines are structured AND runtime command succeeded (PASS)
#   non-zero - either unstructured output detected or runtime command failed (FAIL)

set -euo pipefail

# Get the repository root (parent of scripts/)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${REPO_ROOT}/.venv/bin/python"
SCRIPTS_DIR="${REPO_ROOT}/scripts"

# Change to repo root for consistent paths
cd "$REPO_ROOT"

# Create temp directory for capturing output
tmpdir="$(mktemp -d)"
_cleanup() {
    rm -rf "$tmpdir"
}
trap '_cleanup' EXIT

stdout_file="$tmpdir/health-loop.stdout"
stderr_file="$tmpdir/health-loop.stderr"
combined_file="$tmpdir/health-loop.combined"

echo "=== Structured Output Health Loop Verification ==="
echo "Repo root: $REPO_ROOT"
echo "Python: $PYTHON"
echo "Temp dir: $tmpdir"

# Run the offline health loop fixture that exercises real logging plumbing
# This uses a minimal fake cluster to avoid requiring a live Kubernetes cluster
echo ""
echo "Running offline health loop fixture..."
echo "---"

# Capture both stdout and stderr separately.
# Use set +e around the command to capture its actual exit code without masking.
# The structured-output check runs regardless of command status to reveal any
# raw stderr/tracebacks that would otherwise be hidden.
set +e
"$PYTHON" "$SCRIPTS_DIR/run_health_loop_offline.py" \
    --output-dir "$tmpdir/health-output" \
    >"$stdout_file" \
    2>"$stderr_file"
command_status=$?
set -e

echo "---"
echo "Command completed with exit code: $command_status"

# Combine stdout and stderr for unified checking
cat "$stdout_file" "$stderr_file" >"$combined_file"

echo ""
echo "=== Captured Output Analysis ==="
echo ""
echo "--- stdout (first 10 lines) ---"
head -n 10 "$stdout_file" || true
echo ""
echo "--- stderr (first 10 lines) ---"
head -n 10 "$stderr_file" || true
echo ""
echo "--- combined line count ---"
total_lines=$(wc -l < "$combined_file")
echo "Total lines: $total_lines"

# Check the output with the structured output checker
echo ""
echo "=== Running Structured Output Checker ==="

# Run the checker - always run it regardless of command_status so we get
# diagnostics on failures even when the command itself fails
checker_status=0
"$PYTHON" "$SCRIPTS_DIR/check_structured_output_lines.py" "$combined_file" || checker_status=$?

if [[ "$checker_status" -ne 0 ]]; then
    echo ""
    echo "=============================================="
    echo "FAIL: health-loop stdout/stderr contains unstructured output"
    echo "=============================================="
    echo ""
    echo "Rejected lines from combined output:"
    # Re-run checker to show diagnostics
    "$PYTHON" "$SCRIPTS_DIR/check_structured_output_lines.py" "$combined_file" 2>&1 || true
    exit "$checker_status"
fi

if [[ "$command_status" -ne 0 ]]; then
    echo ""
    echo "=============================================="
    echo "FAIL: offline health-loop command exited with status $command_status"
    echo "=============================================="
    exit "$command_status"
fi

echo ""
echo "=============================================="
echo "PASS: health-loop stdout/stderr remained structured"
echo "=============================================="
exit 0
