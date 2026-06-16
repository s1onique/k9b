#!/usr/bin/env bash
# Verifies frontend NGINX static serving behavior.
# Tests cache headers and 404 behavior for missing assets.
#
# Usage:
#   scripts/verify_frontend_static_serving.sh              # requires container running at 127.0.0.1:18080
#   FRONTEND_URL=http://127.0.0.1:18080 ./scripts/verify_frontend_static_serving.sh
#
# Prerequisites:
#   kubectl -n k9b-rc port-forward svc/k9b-frontend 18080:80
#   # or run locally: docker compose up frontend

set -uo pipefail

FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:18080}"
FAILED=0

echo "=== Frontend Static Serving Verification ==="
echo "Target: $FRONTEND_URL"
echo ""

# Helper function to check a URL
check() {
    local description="$1"
    local url="$2"
    local expected_status="$3"
    local expected_content_type_prefix="$4"
    local expected_cache_control="$5"
    local expect_404="${6:-false}"

    echo -n "  $description... "

    # Fetch headers and first line of body
    local response
    response=$(curl -sI "$url" 2>&1 | head -20)
    local status
    status=$(echo "$response" | grep -i "^HTTP/" | head -1 | awk '{print $2}')
    local content_type
    content_type=$(echo "$response" | grep -i "^content-type:" | head -1 | awk -F: '{print $2}' | tr -d ' \r')
    local cache_control
    cache_control=$(echo "$response" | grep -i "^cache-control:" | head -1 | awk -F: '{print $2}' | tr -d ' \r')

    # For 404 tests, also check the actual body is not text/html
    if [[ "$expect_404" == "true" ]]; then
        local body
        body=$(curl -s "$url" | head -c 100)
        if [[ "$status" == "404" ]]; then
            echo "PASS (status=404)"
        elif [[ "$status" == "200" && "$body" == *"<html"* ]]; then
            echo "FAIL (status=200 but body is HTML - missing asset returns index.html!)"
            FAILED=1
        else
            echo "FAIL (status=$status, expected 404)"
            FAILED=1
        fi
        return
    fi

    # Check status
    if [[ "$status" != "$expected_status" ]]; then
        echo "FAIL (status=$status, expected $expected_status)"
        FAILED=1
        return
    fi

    # Check content type prefix
    if [[ -n "$expected_content_type_prefix" && "$content_type" != "$expected_content_type_prefix"* ]]; then
        echo "FAIL (content-type=$content_type, expected prefix $expected_content_type_prefix)"
        FAILED=1
        return
    fi

    # Check cache control
    if [[ -n "$expected_cache_control" && "$cache_control" != "$expected_cache_control"* ]]; then
        echo "FAIL (cache-control='$cache_control', expected prefix '$expected_cache_control')"
        FAILED=1
        return
    fi

    echo "PASS (status=$status, content-type=$content_type, cache-control=$cache_control)"
}

# Test 1: Root returns HTML with no-store cache
check "Root (/) returns 200 text/html with no-store" \
    "$FRONTEND_URL/" \
    "200" \
    "text/html" \
    "no-store" \
    "false"

# Test 2: /index.html returns HTML with no-store cache
check "/index.html returns 200 text/html with no-store" \
    "$FRONTEND_URL/index.html" \
    "200" \
    "text/html" \
    "no-store" \
    "false"

# Test 3: Health check returns 200
check "/healthz returns 200" \
    "$FRONTEND_URL/healthz" \
    "200" \
    "text/plain" \
    "" \
    "false"

# Test 4: Find an actual JS asset from the built frontend
# First, try to get a JS file from the dist directory listing or known pattern
# We test with a definitely-missing asset to ensure 404
check "Missing /assets/definitely-missing.js returns 404 (not index.html)" \
    "$FRONTEND_URL/assets/definitely-missing.js" \
    "" \
    "" \
    "" \
    "true"

# Test 5: SPA app route returns HTML with no-store cache
check "SPA app route /runs returns 200 text/html with no-store" \
    "$FRONTEND_URL/runs" \
    "200" \
    "text/html" \
    "no-store" \
    "false"

# Test 6: Extract current JS asset from index.html and verify it's served correctly
echo "  Extracting current JS asset from index.html... "
asset_path=$(curl -s "$FRONTEND_URL/" | grep -o '/assets/index-[^"]*\.js' | head -1)
if [[ -z "$asset_path" ]]; then
    echo "  Current JS asset... FAIL (no /assets/index-*.js found in index.html)"
    FAILED=1
else
    check "Current JS asset ($asset_path) returns application/javascript with immutable cache" \
        "$FRONTEND_URL$asset_path" \
        "200" \
        "application/javascript" \
        "public,max-age=31536000,immutable" \
        "false"
fi

echo ""
echo "=== Summary ==="
if [[ $FAILED -eq 0 ]]; then
    echo "All static serving checks PASSED"
    echo ""
    echo "Verified:"
    echo "  - / returns 200 text/html with no-store cache headers"
    echo "  - /index.html returns 200 text/html with no-store cache headers"
    echo "  - /healthz returns 200 for Kubernetes probes"
    echo "  - Missing /assets/* files return 404 (not HTML fallback)"
    exit 0
else
    echo "Some static serving checks FAILED"
    echo ""
    echo "FAILURE: Frontend NGINX static serving verification failed"
    echo "  - Missing assets are falling through to index.html (should return 404)"
    echo "  - Cache headers may be missing or incorrect"
    exit 1
fi
