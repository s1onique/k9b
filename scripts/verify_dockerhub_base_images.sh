#!/usr/bin/env bash
# =============================================================================
# verify_dockerhub_base_images.sh
# =============================================================================
# Verifies that CI-critical Dockerfiles use Harbor proxy cache for DockerHub
# images instead of direct DockerHub pulls.
#
# Required hostname for proxy cache: harbor-pve1.spbnix.local
# Forbidden hostname: registry.spbnix.com (external, not used by ARC runners)
#
# This script fails if any Dockerfile contains:
#   - Direct DockerHub base images (FROM python:, FROM node:, etc.)
#   - Proxy cache references using registry.spbnix.com instead of internal hostname
#
# Background:
#   - Harbor project 'dockerhub-cache' is a proxy-cache, not a push target
#   - DockerHub official images require 'library/' prefix in Harbor
#   - ARC/k3s runners must use harbor-pve1.spbnix.local (internal hostname)
#
# Self-test mode (--self-test):
#   Proves that forbidden patterns fail and Harbor-prefixed equivalents pass.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Required internal hostname for Harbor proxy cache
HARBOR_INTERNAL_HOST="harbor-pve1.spbnix.local"
HARBOR_EXTERNAL_HOST="registry.spbnix.com"

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

# Patterns that indicate wrong external hostname (failure cases)
FORBIDDEN_EXTERNAL_PATTERNS=(
    "^FROM[[:space:]]+${HARBOR_EXTERNAL_HOST}/dockerhub-cache"
)

# Patterns that indicate correct internal hostname (pass cases)
REQUIRED_INTERNAL_PATTERN="^FROM[[:space:]]+${HARBOR_INTERNAL_HOST}/dockerhub-cache"

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
    
    # Test 2: Internal hostname images should PASS
    echo ""
    echo "=== Test 2: Internal hostname images should PASS ==="
    cat > "${TEST_DIR}/Dockerfile.harbor" << 'EOF'
FROM harbor-pve1.spbnix.local/dockerhub-cache/library/python:3.12-slim
FROM harbor-pve1.spbnix.local/dockerhub-cache/library/node:20-slim
FROM harbor-pve1.spbnix.local/dockerhub-cache/nginxinc/nginx-unprivileged:stable-alpine
EOF
    
    test2_passed=true
    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        if grep -qE "${pattern}" "${TEST_DIR}/Dockerfile.harbor" 2>/dev/null; then
            test2_passed=false
            echo "  FAIL: Pattern ${pattern} incorrectly matched internal hostname image"
        fi
    done
    
    # Check no external hostname
    for pattern in "${FORBIDDEN_EXTERNAL_PATTERNS[@]}"; do
        if grep -qE "${pattern}" "${TEST_DIR}/Dockerfile.harbor" 2>/dev/null; then
            test2_passed=false
            echo "  FAIL: Pattern ${pattern} matched external hostname (should use internal)"
        fi
    done
    
    if [[ "${test2_passed}" == true ]]; then
        echo "  PASS: Internal hostname images correctly allowed"
    else
        echo "  FAIL: Internal hostname images incorrectly flagged"
        FAILED=1
    fi
    
    # Test 3: External hostname images should FAIL
    echo ""
    echo "=== Test 3: External hostname images should FAIL ==="
    cat > "${TEST_DIR}/Dockerfile.external" << 'EOF'
FROM registry.spbnix.com/dockerhub-cache/library/python:3.12-slim
FROM registry.spbnix.com/dockerhub-cache/library/node:20-slim
EOF
    
    test3_passed=false
    for pattern in "${FORBIDDEN_EXTERNAL_PATTERNS[@]}"; do
        if grep -qE "${pattern}" "${TEST_DIR}/Dockerfile.external" 2>/dev/null; then
            test3_passed=true
            break
        fi
    done
    
    if [[ "${test3_passed}" == true ]]; then
        echo "  PASS: External hostname correctly detected"
    else
        echo "  FAIL: External hostname not detected"
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
echo "Required Harbor hostname for proxy cache:"
echo "  ${HARBOR_INTERNAL_HOST}/dockerhub-cache"
echo ""
echo "Forbidden hostname:"
echo "  ${HARBOR_EXTERNAL_HOST}/dockerhub-cache"
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
    FILE_FAILED=0
    
    # Check for direct DockerHub usage
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
            FILE_FAILED=1
        fi
    done
    
    # Check for external hostname usage
    for pattern in "${FORBIDDEN_EXTERNAL_PATTERNS[@]}"; do
        matches=$(grep -n -E "${pattern}" "${dockerfile}" 2>/dev/null || true)
        if [[ -n "${matches}" ]]; then
            echo "  FAIL: Found external hostname (must use ${HARBOR_INTERNAL_HOST}): ${pattern}"
            echo "  Found in:"
            while IFS= read -r line; do
                echo "    $line"
            done <<< "$matches"
            FAILED=1
            FILE_FAILED=1
        fi
    done
    
    # Verify that internal hostname proxy cache is used for known images
    if grep -qE "${REQUIRED_INTERNAL_PATTERN}" "${dockerfile}"; then
        echo "  OK: Uses internal hostname proxy cache"
    elif ! grep -qE "^FROM[[:space:]]+" "${dockerfile}"; then
        # No FROM lines found - likely a multi-stage file that only has COPY, etc.
        echo "  OK: No base image (copy-only stage)"
    elif [[ ${FILE_FAILED} -eq 0 ]]; then
        echo "  WARN: Could not verify proxy cache usage"
    fi
    echo ""
done

echo "=========================================="
if [[ ${FAILED} -eq 1 ]]; then
    echo "RESULT: FAILED"
    echo ""
    echo "Dockerfiles must use Harbor proxy cache with internal hostname."
    echo "Required format:"
    echo "  FROM ${HARBOR_INTERNAL_HOST}/dockerhub-cache/library/<image>:<tag>"
    echo ""
    echo "Notes:"
    echo "  - Harbor project 'dockerhub-cache' is proxy-cache, not push target"
    echo "  - DockerHub official images require 'library/' prefix in Harbor"
    echo "  - ARC/k3s runners must use ${HARBOR_INTERNAL_HOST}"
    echo "  - Do not use ${HARBOR_EXTERNAL_HOST} in CI workflows"
    exit 1
else
    echo "RESULT: PASSED"
    echo ""
    echo "All Dockerfiles route through Harbor proxy cache (internal hostname)."
    exit 0
fi
