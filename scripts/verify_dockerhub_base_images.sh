#!/usr/bin/env bash
# =============================================================================
# verify_dockerhub_base_images.sh
# =============================================================================
# Verifies that CI-critical Dockerfiles use Harbor proxy cache for DockerHub
# images instead of direct DockerHub pulls.
#
# This script fails if any Dockerfile contains direct DockerHub base images:
#   - FROM node:
#   - FROM python:
#   - FROM nginxinc/nginx-unprivileged:
#   - FROM docker.io/library/node:
#   - FROM docker.io/library/python:
#   - FROM docker.io/library/nginxinc/nginx-unprivileged:
#   - FROM docker.io/node:
#   - FROM docker.io/python:
#   - FROM docker.io/nginxinc/nginx-unprivileged:
#
# Background:
#   - Harbor project 'dockerhub-cache' is a proxy-cache, not a push target
#   - DockerHub official images require 'library/' prefix in Harbor
#   - This fixes DockerHub layer pull instability, not GitHub Actions cache timeouts
#
# Self-test mode (--self-test):
#   Proves that forbidden patterns fail and Harbor-prefixed equivalents pass.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Self-test mode: create temp Dockerfiles and verify detection
SELF_TEST_MODE=false
if [[ "${1:-}" == "--self-test" ]]; then
    SELF_TEST_MODE=true
fi

# Patterns that indicate direct DockerHub usage (failure cases)
# These are CI-critical images that must route through Harbor proxy cache
# Note: Using ERE where + is a quantifier (not literal plus)
FORBIDDEN_PATTERNS=(
    # Direct DockerHub official images (no registry prefix)
    '^FROM[[:space:]]+node:'
    '^FROM[[:space:]]+python:'
    '^FROM[[:space:]]+nginxinc/nginx-unprivileged:'
    # Explicit docker.io/library/ prefix (official images)
    '^FROM[[:space:]]+docker\.io/library/node:'
    '^FROM[[:space:]]+docker\.io/library/python:'
    '^FROM[[:space:]]+docker\.io/library/nginxinc/nginx-unprivileged:'
    # docker.io without library/ prefix
    '^FROM[[:space:]]+docker\.io/node:'
    '^FROM[[:space:]]+docker\.io/python:'
    '^FROM[[:space:]]+docker\.io/nginxinc/nginx-unprivileged:'
)

# Dockerfiles to check (CI-critical ones)
DOCKERFILES=(
    "${REPO_ROOT}/Dockerfile.python"
    "${REPO_ROOT}/frontend/Dockerfile"
)

# Track failures
FAILED=0

# =============================================================================
# Self-test mode
# =============================================================================

if [[ "${SELF_TEST_MODE}" == true ]]; then
    echo "Running self-test mode..."
    echo ""
    
    # Create temp directory for test Dockerfiles
    TEST_DIR=$(mktemp -d)
    trap "rm -rf ${TEST_DIR}" EXIT
    
    # Test 1: Forbidden patterns should FAIL
    echo "=== Test 1: Forbidden patterns should FAIL ==="
    cat > "${TEST_DIR}/Dockerfile.forbidden" << 'EOF'
FROM python:3.12-slim
FROM node:20-slim
FROM nginxinc/nginx-unprivileged:stable-alpine
EOF
    
    test1_passed=false
    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        if grep -qE "${pattern}" "${TEST_DIR}/Dockerfile.forbidden" 2>/dev/null; then
            test1_passed=true
            break
        fi
    done
    
    if [[ "${test1_passed}" == true ]]; then
        echo "  PASS: Forbidden patterns correctly detected"
    else
        echo "  FAIL: Forbidden patterns not detected"
        FAILED=1
    fi
    
    # Test 2: Harbor-prefixed images should PASS
    echo ""
    echo "=== Test 2: Harbor-prefixed images should PASS ==="
    cat > "${TEST_DIR}/Dockerfile.harbor" << 'EOF'
FROM registry.spbnix.com/dockerhub-cache/library/python:3.12-slim
FROM registry.spbnix.com/dockerhub-cache/library/node:20-slim
FROM registry.spbnix.com/dockerhub-cache/nginxinc/nginx-unprivileged:stable-alpine
EOF
    
    test2_passed=true
    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        if grep -qE "${pattern}" "${TEST_DIR}/Dockerfile.harbor" 2>/dev/null; then
            test2_passed=false
            echo "  FAIL: Pattern ${pattern} incorrectly matched Harbor image"
        fi
    done
    
    if [[ "${test2_passed}" == true ]]; then
        echo "  PASS: Harbor-prefixed images correctly allowed"
    else
        echo "  FAIL: Harbor-prefixed images incorrectly flagged"
        FAILED=1
    fi
    
    echo ""
    if [[ ${FAILED} -eq 0 ]]; then
        echo "SELF-TEST: PASSED"
        exit 0
    else
        echo "SELF-TEST: FAILED"
        exit 1
    fi
fi

# =============================================================================
# Normal verification mode
# =============================================================================

echo "=========================================="
echo "DockerHub Base Image Verification"
echo "=========================================="
echo ""
echo "Checking that Dockerfiles route through Harbor proxy cache:"
echo "  registry.spbnix.com/dockerhub-cache"
echo ""
echo "Forbidden patterns (direct DockerHub usage):"
for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    echo "  - ${pattern}"
done
echo ""

for dockerfile in "${DOCKERFILES[@]}"; do
    if [[ ! -f "${dockerfile}" ]]; then
        echo "WARNING: ${dockerfile} not found, skipping"
        continue
    fi

    echo "Checking: ${dockerfile}"
    
    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        # Use grep -E for ERE where + is a quantifier
        matches=$(grep -n -E "${pattern}" "${dockerfile}" 2>/dev/null || true)
        if [[ -n "${matches}" ]]; then
            echo "  FAIL: Found forbidden pattern: ${pattern}"
            echo "  Found in:"
            while IFS= read -r line; do
                echo "    $line"
            done <<< "$matches"
            FAILED=1
        fi
    done
    
    # Also verify that Harbor proxy cache is used for known images
    if grep -q "^FROM registry.spbnix.com/dockerhub-cache" "${dockerfile}"; then
        echo "  OK: Uses Harbor proxy cache"
    fi
    echo ""
done

echo "=========================================="
if [[ ${FAILED} -eq 1 ]]; then
    echo "RESULT: FAILED"
    echo ""
    echo "Dockerfiles must use Harbor proxy cache for DockerHub images."
    echo "Expected format:"
    echo "  FROM registry.spbnix.com/dockerhub-cache/library/<image>:<tag>"
    echo ""
    echo "Notes:"
    echo "  - Harbor project 'dockerhub-cache' is proxy-cache, not push target"
    echo "  - DockerHub official images require 'library/' prefix in Harbor"
    echo "  - This fixes DockerHub layer pull instability"
    exit 1
else
    echo "RESULT: PASSED"
    echo ""
    echo "All Dockerfiles route through Harbor proxy cache."
    exit 0
fi
