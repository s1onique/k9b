#!/usr/bin/env bash
# Helm chart verification for k9b.
# Runs lint, template rendering, and selector validation.
#
# Usage:
#   scripts/verify_helm_chart.sh              # all checks (lint + render + selector)
#   scripts/verify_helm_chart.sh --lint-only  # helm lint only
#   scripts/verify_helm_chart.sh --render-only # template rendering only (no lint, no selector)
#   scripts/verify_helm_chart.sh --selector-only  # selector validation only

set -uo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
CHART_DIR="$REPO_ROOT/charts/k9b"
FAILED=0

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

_fail() {
    echo "FAIL: $*" >&2
    FAILED=1
}

_info() {
    echo "INFO: $*"
}

_run() {
    local label="$1"
    shift
    echo "=== $label ==="
    if "$@" 2>&1; then
        echo "PASS: $label"
        echo
        return 0
    else
        _fail "$label"
        echo
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

MODE="all"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --lint-only)
            MODE="lint"
            shift
            ;;
        --render-only)
            MODE="render"
            shift
            ;;
        --selector-only)
            MODE="selector"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--lint-only] [--render-only] [--selector-only]"
            echo "  --lint-only      Run only helm lint"
            echo "  --render-only    Run only template rendering checks"
            echo "  --selector-only  Run only selector validation"
            echo "  (no flag)       Run all checks"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Check prerequisites
# ---------------------------------------------------------------------------

if ! command -v helm >/dev/null 2>&1; then
    echo "ERROR: helm is not installed or not on PATH." >&2
    echo "Install Helm v3 before running chart verification." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Lint checks
# ---------------------------------------------------------------------------

if [[ "$MODE" == "all" ]] || [[ "$MODE" == "lint" ]]; then
    _run "helm lint $CHART_DIR" helm lint "$CHART_DIR"
fi

# ---------------------------------------------------------------------------
# Template rendering checks
# ---------------------------------------------------------------------------

if [[ "$MODE" == "all" ]] || [[ "$MODE" == "render" ]]; then
    _run "helm template (default values)" helm template k9b "$CHART_DIR"
    _run "helm template (ingress enabled)" helm template k9b "$CHART_DIR" --set ingress.enabled=true --set ingress.host=k9b.example.com
    _run "helm template (external resources enabled)" helm template k9b "$CHART_DIR" --set kubeconfig.enabled=true --set healthConfig.enabled=true
fi

# ---------------------------------------------------------------------------
# Selector validation checks
# ---------------------------------------------------------------------------

if [[ "$MODE" == "all" ]] || [[ "$MODE" == "selector" ]]; then
    echo "=== Selector validation ==="

    # Render with ingress to get all resources
    rendered=$(helm template k9b "$CHART_DIR" --set ingress.enabled=true --set ingress.host=k9b.example.com 2>&1) || {
        _fail "helm template for selector check"
        echo "$rendered" >&2
    }

    # Count how many times each component label appears in the full output
    # This is a simple presence check - components should appear multiple times
    # Backend/Frontend appear ~5 times (Service labels + Deployment labels/selectors)
    # Scheduler appears ~3 times (no Service, just Deployment labels/selectors)
    
    backend_count=$(echo "$rendered" | grep -c "app.kubernetes.io/component: backend" || echo 0)
    frontend_count=$(echo "$rendered" | grep -c "app.kubernetes.io/component: frontend" || echo 0)
    scheduler_count=$(echo "$rendered" | grep -c "app.kubernetes.io/component: scheduler" || echo 0)
    
    if [[ "$backend_count" -ge 4 ]]; then
        _info "Backend component label: PASS (found $backend_count occurrences)"
    else
        _fail "Backend component label: expected >=4, found $backend_count"
    fi
    
    if [[ "$frontend_count" -ge 4 ]]; then
        _info "Frontend component label: PASS (found $frontend_count occurrences)"
    else
        _fail "Frontend component label: expected >=4, found $frontend_count"
    fi
    
    if [[ "$scheduler_count" -ge 3 ]]; then
        _info "Scheduler component label: PASS (found $scheduler_count occurrences)"
    else
        _fail "Scheduler component label: expected >=3, found $scheduler_count"
    fi
    
    echo
fi

# ---------------------------------------------------------------------------
# Finalize
# ---------------------------------------------------------------------------

if (( FAILED != 0 )); then
    echo "=== HELM CHART VERIFICATION: FAILED ===" >&2
    exit 1
else
    echo "=== HELM CHART VERIFICATION: PASSED ==="
    exit 0
fi
