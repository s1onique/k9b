#!/usr/bin/env bash
# Coverage reporting script for k9b
# Generates coverage reports for both backend (Python) and frontend (TypeScript/React)
#
# Artifacts produced:
#   - coverage/backend/coverage.xml       (machine-readable, CI-friendly)
#   - coverage/backend/coverage.json      (machine-readable, CI-friendly)
#   - coverage/backend/coverage.info      (lcov format, CI-friendly)
#   - coverage/backend/coverage_html/     (human-readable HTML report)
#   - coverage/frontend/coverage-final.json  (machine-readable)
#   - coverage/frontend/index.html          (human-readable HTML report)
#
# Usage:
#   ./scripts/run_coverage.sh           # Run both backend and frontend coverage
#   ./scripts/run_coverage.sh backend  # Run backend only
#   ./scripts/run_coverage.sh frontend # Run frontend only

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"
BACKEND_COVERAGE_DIR="$REPO_ROOT/coverage/backend"
FRONTEND_COVERAGE_DIR="$REPO_ROOT/coverage/frontend"

run_backend_coverage() {
    echo "=== Backend Coverage (Python/pytest) ==="
    mkdir -p "$BACKEND_COVERAGE_DIR"

    $PYTHON -m pytest \
        --cov=src/k8s_diag_agent \
        --cov-report=term-missing \
        --cov-report=xml:"$BACKEND_COVERAGE_DIR/coverage.xml" \
        --cov-report=json:"$BACKEND_COVERAGE_DIR/coverage.json" \
        --cov-report=lcov:"$BACKEND_COVERAGE_DIR/coverage.info" \
        --cov-report=html:"$BACKEND_COVERAGE_DIR/coverage_html" \
        tests/
}

run_frontend_coverage() {
    echo ""
    echo "=== Frontend Coverage (TypeScript/vitest) ==="
    mkdir -p "$FRONTEND_COVERAGE_DIR"

    pushd "$REPO_ROOT/frontend" >/dev/null
    npm run test:ui -- --coverage
    popd >/dev/null
}

echo "Coverage Report Generator for k9b"
echo "================================="
echo ""

MODE="${1:-both}"

case "$MODE" in
    backend)
        run_backend_coverage
        ;;
    frontend)
        run_frontend_coverage
        ;;
    both)
        run_backend_coverage
        run_frontend_coverage
        ;;
    *)
        echo "ERROR: Unknown mode '$MODE'" >&2
        echo "Usage: $0 [backend|frontend|both]" >&2
        exit 1
        ;;
esac

echo ""
echo "=== Coverage Artifacts ==="
echo "Backend:  $BACKEND_COVERAGE_DIR"
echo "Frontend: $FRONTEND_COVERAGE_DIR"
echo ""
echo "Run complete."