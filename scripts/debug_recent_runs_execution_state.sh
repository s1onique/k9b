#!/usr/bin/env bash
# ============================================================================
# debug_recent_runs_execution_state.sh
#
# DEPRECATED: This script has been migrated to Python.
# Please use: scripts/debug_recent_runs_execution_state.py
#
# This shim exists only for backward compatibility and delegates to Python.
#
# Usage: Same as Python implementation
#   scripts/debug_recent_runs_execution_state.sh --base-url https://preprod... --run-id health-run-...
# ============================================================================

set -euo pipefail

# Script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Choose Python interpreter (.venv preferred)
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
else
    PYTHON="python3"
fi

# Delegate to Python implementation
exec "$PYTHON" "$SCRIPT_DIR/debug_recent_runs_execution_state.py" "$@"
