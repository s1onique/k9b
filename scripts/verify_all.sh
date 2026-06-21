#!/usr/bin/env bash
# Compatibility shim for verify_all.py.
#
# This shell script is a thin wrapper that delegates to the Python implementation.
# All orchestration logic has been moved to scripts/verify_all.py.
#
# Usage: ./scripts/verify_all.sh [options]
#         → .venv/bin/python scripts/verify_all.py [options]
#
# For direct Python usage:
#     python scripts/verify_all.py [--fast|--full] [--json] [--python-only|--frontend-only|--helm-only]
#
# Policy: Only --full may be called "full gate green".

set -uo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"

# Fallback to system python if venv not available
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="${PYTHON:-python3}"
fi

# Exec the Python implementation
exec "$PYTHON" "$(dirname "$0")/verify_all.py" "$@"