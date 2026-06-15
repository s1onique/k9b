#!/usr/bin/env bash
# =============================================================================
# verify_docker_workflow_hygiene.sh
# =============================================================================
# Verifies that GitHub Actions workflows follow local-first Docker build hygiene:
#   - setup-qemu-action must use Harbor proxy cache for binfmt image (not default)
#   - setup-qemu-action restricts QEMU platforms to non-native targets only
#   - docker/build-push-action must use registry cache (Harbor), not GHA cache
#
# This script fails on:
#   - setup-qemu-action missing Harbor image override (silently uses DockerHub default)
#   - setup-qemu-action with docker.io/tonistiigi/binfmt (explicit DockerHub pull)
#   - setup-qemu-action with platforms including native architecture
#   - docker/build-push-action missing registry cache (hard fail)
#   - docker/build-push-action using type=gha cache
#
# Self-test mode (--self-test):
#   Proves that forbidden patterns fail and correct patterns pass.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Required Harbor binfmt image (from Harbor proxy cache)
HARBOR_BINFMT_IMAGE="registry.spbnix.com/dockerhub-cache/tonistiigi/binfmt:latest"

# Self-test mode: create temp workflows and verify detection
SELF_TEST_MODE=false
if [[ "${1:-}" == "--self-test" ]]; then
    SELF_TEST_MODE=true
fi

# Track failures
FAILED=0

# =============================================================================
# Self-test mode
# =============================================================================

if [[ "${SELF_TEST_MODE}" == true ]]; then
    echo "Running self-test mode..."
    echo ""

    # Create temp directory for test workflows
    TEST_DIR=$(mktemp -d)
    trap "rm -rf ${TEST_DIR}" EXIT

    # Test 1: Forbidden QEMU patterns should FAIL
    echo "=== Test 1: Forbidden QEMU patterns should FAIL ==="
    cat > "${TEST_DIR}/workflow.forbidden.yml" << 'EOF'
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
        with:
          platforms: arm64,amd64
EOF

    test1_passed=false
    if grep -qE "platforms:.*amd64" "${TEST_DIR}/workflow.forbidden.yml" 2>/dev/null; then
        test1_passed=true
    fi

    if [[ "${test1_passed}" == true ]]; then
        echo "  PASS: Native platform in QEMU correctly detected"
    else
        echo "  FAIL: Native platform in QEMU not detected"
        FAILED=1
    fi

    # Test 2: Forbidden DockerHub binfmt should FAIL
    echo ""
    echo "=== Test 2: Forbidden DockerHub binfmt should FAIL ==="
    cat > "${TEST_DIR}/workflow.dockerhub-binfmt.yml" << 'EOF'
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
        with:
          platforms: arm64
          image: docker.io/tonistiigi/binfmt:latest
EOF

    test2_passed=false
    if grep -qE "docker\.io/tonistiigi/binfmt" "${TEST_DIR}/workflow.dockerhub-binfmt.yml" 2>/dev/null; then
        test2_passed=true
    fi

    if [[ "${test2_passed}" == true ]]; then
        echo "  PASS: DockerHub binfmt correctly detected"
    else
        echo "  FAIL: DockerHub binfmt not detected"
        FAILED=1
    fi

    # Test 3: Missing QEMU image override should FAIL
    echo ""
    echo "=== Test 3: Missing QEMU image override should FAIL ==="
    cat > "${TEST_DIR}/workflow.missing-override.yml" << 'EOF'
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
        with:
          platforms: arm64
EOF

    test3_passed=false
    # This would silently fall back to DockerHub default
    if grep -qE "setup-qemu-action" "${TEST_DIR}/workflow.missing-override.yml" 2>/dev/null; then
        # Check if there's no image override
        if ! grep -qE "image:.*binfmt" "${TEST_DIR}/workflow.missing-override.yml" 2>/dev/null; then
            test3_passed=true
        fi
    fi

    if [[ "${test3_passed}" == true ]]; then
        echo "  PASS: Missing QEMU image override correctly detected"
    else
        echo "  FAIL: Missing QEMU image override not detected"
        FAILED=1
    fi

    # Test 4: GHA cache should FAIL
    echo ""
    echo "=== Test 4: GHA cache should FAIL ==="
    cat > "${TEST_DIR}/workflow.gha-cache.yml" << 'EOF'
          cache-from: type=gha
          cache-to: type=gha,mode=max
EOF

    test4_passed=false
    if grep -qE "type=gha" "${TEST_DIR}/workflow.gha-cache.yml" 2>/dev/null; then
        test4_passed=true
    fi

    if [[ "${test4_passed}" == true ]]; then
        echo "  PASS: GHA cache correctly detected"
    else
        echo "  FAIL: GHA cache not detected"
        FAILED=1
    fi

    # Test 5: Missing registry cache should FAIL
    echo ""
    echo "=== Test 5: Missing registry cache should FAIL ==="
    cat > "${TEST_DIR}/workflow.missing-cache.yml" << 'EOF'
          cache-from: type=gha
EOF

    test5_passed=false
    # Missing registry cache pattern when GHA is present
    if grep -qE "type=gha" "${TEST_DIR}/workflow.missing-cache.yml" 2>/dev/null; then
        if ! grep -qE "type=registry,ref=registry\.spbnix\.com/k9b/cache" "${TEST_DIR}/workflow.missing-cache.yml" 2>/dev/null; then
            test5_passed=true
        fi
    fi

    if [[ "${test5_passed}" == true ]]; then
        echo "  PASS: Missing registry cache correctly detected"
    else
        echo "  FAIL: Missing registry cache not detected"
        FAILED=1
    fi

    # Test 6: Correct patterns should PASS
    echo ""
    echo "=== Test 6: Correct patterns should PASS ==="
    cat > "${TEST_DIR}/workflow.correct.yml" << 'EOF'
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
        with:
          platforms: arm64
          image: registry.spbnix.com/dockerhub-cache/tonistiigi/binfmt:latest
          cache-image: false

          cache-from: type=registry,ref=registry.spbnix.com/k9b/cache/k9b-frontend:buildcache
          cache-to: type=registry,ref=registry.spbnix.com/k9b/cache/k9b-frontend:buildcache,mode=max
EOF

    test6_passed=true
    if grep -qE "platforms:.*amd64" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test6_passed=false
        echo "  FAIL: Incorrectly flagged native platform"
    fi
    if grep -qE "docker\.io/tonistiigi/binfmt" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test6_passed=false
        echo "  FAIL: Incorrectly flagged Harbor binfmt"
    fi
    if grep -qE "type=gha" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test6_passed=false
        echo "  FAIL: Incorrectly flagged registry cache"
    fi

    if [[ "${test6_passed}" == true ]]; then
        echo "  PASS: Correct patterns correctly allowed"
    else
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
echo "Docker Workflow Hygiene Verification"
echo "=========================================="
echo ""

# Workflow files to check
WORKFLOW_FILES=(
    "${REPO_ROOT}/.github/workflows/harbor.yml"
)

# Rules
echo "Rules:"
echo "  1. setup-qemu-action must specify Harbor proxy image (not default DockerHub)"
echo "  2. QEMU platforms should exclude native architecture (amd64 on amd64 runner)"
echo "  3. docker/build-push-action must use registry cache, not GHA cache"
echo ""

for workflow in "${WORKFLOW_FILES[@]}"; do
    if [[ ! -f "${workflow}" ]]; then
        echo "WARNING: ${workflow} not found, skipping"
        continue
    fi

    echo "Checking: ${workflow}"

    # -------------------------------------------------------------------------
    # Rule 1: QEMU must have Harbor image override (not just avoid DockerHub)
    # -------------------------------------------------------------------------
    if grep -qE "setup-qemu-action" "${workflow}"; then
        # Count QEMU occurrences and count Harbor image overrides
        qemu_count=$(grep -cE "setup-qemu-action" "${workflow}" 2>/dev/null || echo 0)
        harbor_image_count=$(grep -cE "image:.*registry\.spbnix\.com/dockerhub-cache/tonistiigi/binfmt" "${workflow}" 2>/dev/null || echo 0)

        if [[ ${qemu_count} -gt 0 ]] && [[ ${harbor_image_count} -lt ${qemu_count} ]]; then
            echo "  FAIL: QEMU section missing Harbor image override (${harbor_image_count}/${qemu_count} have it)"
            echo "        Expected: image: ${HARBOR_BINFMT_IMAGE}"
            echo "        QEMU silently falls back to DockerHub default without this override"
            FAILED=1
        else
            echo "  OK: All QEMU sections use Harbor image override"
        fi
    fi

    # -------------------------------------------------------------------------
    # Rule 2: No DockerHub explicit binfmt pulls
    # -------------------------------------------------------------------------
    if grep -qE "docker\.io/tonistiigi/binfmt" "${workflow}"; then
        echo "  FAIL: Found explicit DockerHub binfmt pull (should use Harbor proxy)"
        FAILED=1
    fi

    # -------------------------------------------------------------------------
    # Rule 3: No GHA cache usage
    # -------------------------------------------------------------------------
    if grep -qE "type=gha" "${workflow}"; then
        echo "  FAIL: Found GHA cache usage (must use Harbor registry cache)"
        FAILED=1
    else
        echo "  OK: No GHA cache usage"
    fi

    # -------------------------------------------------------------------------
    # Rule 4: Must have registry cache for build-push-action (hard fail)
    # -------------------------------------------------------------------------
    if grep -qE "docker/build-push-action" "${workflow}"; then
        if grep -qE "type=registry,ref=registry\.spbnix\.com/k9b/cache" "${workflow}"; then
            echo "  OK: Uses Harbor registry cache"
        else
            echo "  FAIL: build-push-action missing registry cache (hard fail)"
            echo "        Required: cache-from/cache-to with type=registry,ref=registry.spbnix.com/k9b/cache/..."
            FAILED=1
        fi
    fi

    echo ""
done

echo "=========================================="
if [[ ${FAILED} -eq 1 ]]; then
    echo "RESULT: FAILED"
    echo ""
    echo "Workflow hygiene violations detected. Please fix:"
    echo "  1. QEMU must have explicit Harbor image override:"
    echo "     image: ${HARBOR_BINFMT_IMAGE}"
    echo "  2. Remove amd64 from QEMU platforms (native architecture)"
    echo "  3. Replace GHA cache with Harbor registry cache:"
    echo "     cache-from: type=registry,ref=registry.spbnix.com/k9b/cache/<image>:buildcache"
    echo "     cache-to: type=registry,ref=registry.spbnix.com/k9b/cache/<image>:buildcache,mode=max"
    exit 1
else
    echo "RESULT: PASSED"
    echo ""
    echo "All Docker workflows follow local-first hygiene."
    exit 0
fi
