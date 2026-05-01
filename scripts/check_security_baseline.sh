#!/bin/bash
# Security baseline guardrails script
# Fails fast on patterns that bypass path validation or leak information
set -euo pipefail

ISSUES=0
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Security Baseline Check ==="

# 1. Reject unreviewed bare 'except Exception:'
echo -n "Checking for unreviewed 'except Exception:'... "
if grep -rn --include='*.py' 'except Exception:' "$REPO_ROOT/src/" 2>/dev/null | \
    grep -v 'except Exception as e:' | \
    grep -v '# REVIEWED: bare except' | \
    grep -v 'except Exception:  # REVIEWED' | \
    grep -v '# noqa: BLE' > /tmp/sec_except.txt; then
    if [ -s /tmp/sec_except.txt ]; then
        echo "FOUND (review or add # REVIEWED comment)"
        cat /tmp/sec_except.txt
        ISSUES=$((ISSUES + 1))
    else
        echo "OK"
    fi
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
if [ $ISSUES -eq 0 ]; then
    echo "All security baseline checks passed."
    exit 0
else
    echo "SECURITY BASELINE: $ISSUES issue(s) found"
    exit 1
fi
