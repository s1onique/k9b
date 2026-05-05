#!/bin/bash
# Security baseline guardrails script
# Fails fast on patterns that bypass path validation or leak information
#
# Modes:
#   baseline (default) - permits documented reviewed-safe findings, fails on new unreviewed patterns
#   strict              - fails on all broad except Exception, including reviewed-safe
#
# Usage:
#   bash scripts/check_security_baseline.sh           # baseline mode (default)
#   bash scripts/check_security_baseline.sh --mode baseline
#   bash scripts/check_security_baseline.sh --mode strict
set -euo pipefail

ISSUES=0
REVIEWED_COUNT=0
UNREVIEWED_COUNT=0
UNREVIEWED_FINDINGS=""

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALLOWLIST="$SCRIPT_DIR/security_baseline_allowlist.txt"

# Mode: default to baseline
MODE="${SECURITY_BASELINE_MODE:-baseline}"
if [[ "${1:-}" == "--mode" && "$#" -ge 2 ]]; then
    MODE="$2"
elif [[ "${1:-}" == "--mode="* ]]; then
    MODE="${1#--mode=}"
elif [[ "${1:-}" == "--help" ]]; then
    echo "Usage: $0 [--mode baseline|strict]"
    echo "  baseline (default): permits reviewed-safe findings, fails on new unreviewed"
    echo "  strict: fails on all broad except Exception"
    exit 0
fi

echo "=== Security Baseline Check (mode: $MODE) ==="

# Helper: normalize file path to relative k8s_diag_agent/ path
normalize_path() {
    local file="$1"
    # Strip REPO_ROOT prefix
    local rel="${file#$REPO_ROOT/}"
    # Remove leading slash
    rel="${rel#/}"
    # Normalize double slashes
    rel=$(echo "$rel" | sed 's|///*|/|g')
    # Strip src/ prefix
    rel="${rel#src/}"
    # Strip k8s_diag_agent/ prefix if present
    rel="${rel#k8s_diag_agent/}"
    echo "$rel"
}

# Helper: check if a finding is in the allowlist
# Requires EXACT file match + context pattern match
in_allowlist() {
    local file="$1"
    local context="$2"
    if [[ ! -f "$ALLOWLIST" ]]; then
        return 1
    fi

    # Normalize file path to relative (k8s_diag_agent/...)
    local rel_file
    rel_file=$(normalize_path "$file")

    while IFS= read -r line; do
        [[ "$line" =~ ^# ]] && continue
        [[ -z "$line" ]] && continue

        # Extract allowlist entry components
        local allow_file
        allow_file=$(echo "$line" | awk '{print $1}')

        # Exact file match required (not substring)
        if [[ "$rel_file" != "$allow_file" ]]; then
            continue
        fi

        # Extract context pattern (second field)
        local pattern
        pattern=$(echo "$line" | awk '{print $2}')

        # Context pattern must be found in surrounding lines
        if [[ "$context" == *"$pattern"* ]]; then
            return 0
        fi
    done < "$ALLOWLIST"
    return 1
}

# Helper: get function name from context lines (400 lines before to 10 lines after)
get_function_context() {
    local file="$1"
    local line="$2"
    # Include at least one function definition line before the except
    local start=$((line >= 400 ? line - 400 : 1))
    sed -n "${start},$((line + 10))p" "$file" 2>/dev/null | head -410
}

# Helper: process a single except Exception finding
process_except_finding() {
    local finding="$1"
    local file_line
    local file
    local linenum
    file_line=$(echo "$finding" | sed 's/:[[:space:]]*/:/')
    file=$(echo "$file_line" | cut -d: -f1)
    linenum=$(echo "$file_line" | cut -d: -f2)

    local context
    context=$(get_function_context "$file" "$linenum")

    if in_allowlist "$file" "$context"; then
        if [[ "$MODE" == "strict" ]]; then
            echo "FOUND (reviewed-safe but strict mode)"
            echo "$finding"
            ISSUES=$((ISSUES + 1))
            UNREVIEWED_COUNT=$((UNREVIEWED_COUNT + 1))
        else
            REVIEWED_COUNT=$((REVIEWED_COUNT + 1))
        fi
    else
        echo "FOUND (review or add to allowlist)"
        echo "$finding"
        ISSUES=$((ISSUES + 1))
        UNREVIEWED_COUNT=$((UNREVIEWED_COUNT + 1))
        UNREVIEWED_FINDINGS="${UNREVIEWED_FINDINGS}${finding}"$'\n'
    fi
}

# 1. Reject unreviewed broad 'except Exception'
# Catch all forms: except Exception:, except Exception as exc:, except Exception as e:
echo -n "Checking for broad 'except Exception:'... "
# Find all broad except Exception patterns (all forms with optional whitespace)
grep -Ern --include='*.py' 'except[[:space:]]+Exception([[:space:]]+as[[:space:]]+[A-Za-z_][A-Za-z0-9_]*)?[[:space:]]*:' "$REPO_ROOT/src/" 2>/dev/null > /tmp/sec_except.txt

if [ -s /tmp/sec_except.txt ]; then
    while IFS= read -r finding; do
        process_except_finding "$finding"
    done < /tmp/sec_except.txt
else
    echo "OK"
fi

# 2. Reject diagnostic stderr=DEVNULL (hides subprocess failures)
echo -n "Checking for subprocess stderr=DEVNULL... "
if grep -rn 'stderr=DEVNULL' "$REPO_ROOT/src/" 2>/dev/null | \
    grep -v '# REVIEWED: DEVNULL' > /tmp/sec_devnull.txt; then
    if [ -s /tmp/sec_devnull.txt ]; then
        echo "FOUND (diagnostics should capture stderr)"
        cat /tmp/sec_devnull.txt
        ISSUES=$((ISSUES + 1))
    else
        echo "OK"
    fi
else
    echo "OK"
fi

# 3. Flag unsafe f-string glob interpolation (run_id in glob without validation)
echo -n "Checking for unsafe glob interpolation... "
if grep -rn 'glob.*f["'"'"']' "$REPO_ROOT/src/" 2>/dev/null | \
    grep -v 'validate_' | \
    grep -v 'safe_glob' | \
    grep -v 'safe_run_artifact' | \
    grep -v '# REVIEWED: safe' > /tmp/sec_glob.txt; then
    if [ -s /tmp/sec_glob.txt ]; then
        echo "FOUND (ensure run_id is validated before glob)"
        cat /tmp/sec_glob.txt
        ISSUES=$((ISSUES + 1))
    else
        echo "OK"
    fi
else
    echo "OK"
fi

# 4. Reject frontend String(payload.error) pattern (information leakage)
echo -n "Checking for frontend error leakage patterns... "
if grep -rn 'String(payload.error)' "$REPO_ROOT/frontend/" 2>/dev/null | \
    grep -v '# REVIEWED: safe' > /tmp/sec_frontend.txt; then
    if [ -s /tmp/sec_frontend.txt ]; then
        echo "FOUND (avoid exposing raw error messages)"
        cat /tmp/sec_frontend.txt
        ISSUES=$((ISSUES + 1))
    else
        echo "OK"
    fi
else
    echo "OK"
fi

# 5. Check for hardcoded secrets/credentials
echo -n "Checking for potential hardcoded secrets... "
if grep -rn --include='*.py' -E '(password|secret|api_key|token)\s*=\s*["'"'"'][^"'"'"']{8,}' "$REPO_ROOT/src/" 2>/dev/null | \
    grep -v '# REVIEWED' | \
    grep -v 'os.environ' | \
    grep -v 'os.getenv' > /tmp/sec_secrets.txt; then
    if [ -s /tmp/sec_secrets.txt ]; then
        echo "FOUND (use environment variables instead)"
        cat /tmp/sec_secrets.txt
        ISSUES=$((ISSUES + 1))
    else
        echo "OK"
    fi
else
    echo "OK"
fi

echo ""
echo "=== Summary ==="
if [[ "$MODE" == "baseline" ]]; then
    echo "Mode: baseline"
    echo "Reviewed-safe findings: $REVIEWED_COUNT"
    echo "Unreviewed findings: $UNREVIEWED_COUNT"
fi
if [ $ISSUES -eq 0 ]; then
    echo "All security baseline checks passed."
    exit 0
else
    echo "SECURITY BASELINE: $ISSUES issue(s) found"
    if [[ "$MODE" == "strict" ]]; then
        echo "Note: strict mode reports ALL broad except Exception as failures"
        echo "Run with --mode baseline to allow reviewed-safe findings"
    fi
    exit 1
fi
