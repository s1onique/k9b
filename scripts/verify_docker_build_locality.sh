#!/usr/bin/env bash
# =============================================================================
# verify_docker_build_locality.sh
# =============================================================================
# Verifies that GitHub Actions Docker build workflows follow local-first hygiene:
#   - setup-qemu-action must use Harbor proxy cache for binfmt image (not default)
#   - setup-qemu-action restricts QEMU platforms to non-native targets only
#   - setup-buildx-action must use Harbor proxy cache for BuildKit builder image
#   - docker/build-push-action must use registry cache, not GHA cache
#   - Python Dockerfiles use BuildKit pip cache mounts, not --no-cache-dir
#   - Python Dockerfiles install third-party deps before copying high-churn src/
#
# This script fails on:
#   - setup-qemu-action missing Harbor image override (silently uses DockerHub default)
#   - setup-qemu-action with docker.io/tonistiigi/binfmt (explicit DockerHub pull)
#   - setup-qemu-action with platforms including native architecture
#   - setup-buildx-action missing Harbor BuildKit image override
#   - setup-buildx-action with explicit unproxied BuildKit images
#   - docker/build-push-action missing registry cache (hard fail)
#   - docker/build-push-action using type=gha cache
#   - Python Dockerfile with pip install --no-cache-dir after COPY src/scripts
#   - Python Dockerfile missing BuildKit pip cache mounts
#
# Self-test mode (--self-test):
#   Proves that forbidden patterns fail and correct patterns pass.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Required Harbor proxy cache hostname
PROXY_CACHE_HOST="harbor-pve1.spbnix.local"

# Required Harbor binfmt image (from Harbor proxy cache)
HARBOR_BINFMT_IMAGE="${PROXY_CACHE_HOST}/dockerhub-cache/tonistiigi/binfmt:latest"

# Required Harbor BuildKit builder image (from Harbor proxy cache)
HARBOR_BUILDKIT_IMAGE="${PROXY_CACHE_HOST}/dockerhub-cache/moby/buildkit:buildx-stable-1"

# Self-test mode: create temp workflows and verify detection
SELF_TEST_MODE=false
if [[ "${1:-}" == "--self-test" ]]; then
    SELF_TEST_MODE=true
fi

# Track failures
FAILED=0

# Track which specific checks failed (for targeted remediation output)
FAILED_QEMU_IMAGE=0
FAILED_BUILDX_IMAGE=0
FAILED_GHA_CACHE=0
FAILED_REGISTRY_CACHE=0
FAILED_PIP_NO_CACHE=0
FAILED_PIP_CACHE_MOUNT=0
FAILED_PIP_ORDER=0
FAILED_SSOT_STALE=0
FAILED_SSOT_HARDCODED=0

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
    echo "=== Test 1: Native platform in QEMU should FAIL ==="
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
    if grep -qE "uses:[[:space:]]+docker/setup-qemu-action@v[0-9]+" "${TEST_DIR}/workflow.missing-override.yml" 2>/dev/null; then
        if ! grep -qE "^[[:space:]]*image:.*binfmt" "${TEST_DIR}/workflow.missing-override.yml" 2>/dev/null; then
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
    if grep -qE "type=gha" "${TEST_DIR}/workflow.missing-cache.yml" 2>/dev/null; then
        if ! grep -qE "type=registry,ref=${PROXY_CACHE_HOST}/k9b/cache" "${TEST_DIR}/workflow.missing-cache.yml" 2>/dev/null; then
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
          image: harbor-pve1.spbnix.local/dockerhub-cache/tonistiigi/binfmt:latest
          cache-image: false

          cache-from: type=registry,ref=harbor-pve1.spbnix.local/k9b/cache/k9b-frontend:buildcache
          cache-to: type=registry,ref=harbor-pve1.spbnix.local/k9b/cache/k9b-frontend:buildcache,mode=max
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

    # Test 7: Buildx with no driver-opts image override should FAIL
    echo ""
    echo "=== Test 7: Buildx with no driver-opts image override should FAIL ==="
    cat > "${TEST_DIR}/workflow.buildx-no-override.yml" << 'EOF'
      - name: Set up Docker Buildx
        id: buildx
        uses: docker/setup-buildx-action@v3
EOF

    test7_passed=false
    if grep -qE "uses:[[:space:]]+docker/setup-buildx-action@v[0-9]+" "${TEST_DIR}/workflow.buildx-no-override.yml" 2>/dev/null; then
        if ! grep -qE "^[[:space:]]*image=${PROXY_CACHE_HOST}/dockerhub-cache/moby/buildkit" "${TEST_DIR}/workflow.buildx-no-override.yml" 2>/dev/null; then
            test7_passed=true
        fi
    fi

    if [[ "${test7_passed}" == true ]]; then
        echo "  PASS: Buildx missing driver-opts image override correctly detected"
    else
        echo "  FAIL: Buildx missing driver-opts image override not detected"
        FAILED=1
    fi

    # Test 8: Buildx with explicit unproxied BuildKit image should FAIL
    echo ""
    echo "=== Test 8: Buildx with explicit unproxied BuildKit image should FAIL ==="
    cat > "${TEST_DIR}/workflow.buildx-unproxied.yml" << 'EOF'
      - name: Set up Docker Buildx
        id: buildx
        uses: docker/setup-buildx-action@v3
        with:
          driver-opts: |
            image=moby/buildkit:buildx-stable-1
EOF

    test8_passed=false
    if grep -qE "image=moby/buildkit:buildx-stable-1" "${TEST_DIR}/workflow.buildx-unproxied.yml" 2>/dev/null; then
        test8_passed=true
    fi

    if [[ "${test8_passed}" == true ]]; then
        echo "  PASS: Buildx unproxied BuildKit image correctly detected"
    else
        echo "  FAIL: Buildx unproxied BuildKit image not detected"
        FAILED=1
    fi

    # Test 9: Buildx with Harbor proxy BuildKit image should PASS
    echo ""
    echo "=== Test 9: Buildx with Harbor proxy BuildKit image should PASS ==="
    cat > "${TEST_DIR}/workflow.buildx-correct.yml" << 'EOF'
      - name: Set up Docker Buildx
        id: buildx
        uses: docker/setup-buildx-action@v3
        with:
          driver-opts: |
            image=harbor-pve1.spbnix.local/dockerhub-cache/moby/buildkit:buildx-stable-1
EOF

    test9_passed=true
    if grep -qE "image=moby/buildkit:buildx-stable-1" "${TEST_DIR}/workflow.buildx-correct.yml" 2>/dev/null; then
        test9_passed=false
        echo "  FAIL: Incorrectly flagged Harbor proxy BuildKit image"
    fi
    if grep -qE "image: moby/buildkit:buildx-stable-1" "${TEST_DIR}/workflow.buildx-correct.yml" 2>/dev/null; then
        test9_passed=false
        echo "  FAIL: Incorrectly flagged Harbor proxy BuildKit image (with space)"
    fi
    if grep -qE "docker\.io/moby/buildkit:buildx-stable-1" "${TEST_DIR}/workflow.buildx-correct.yml" 2>/dev/null; then
        test9_passed=false
        echo "  FAIL: Incorrectly flagged Harbor proxy BuildKit image (docker.io)"
    fi

    if [[ "${test9_passed}" == true ]]; then
        echo "  PASS: Buildx with Harbor proxy BuildKit image correctly allowed"
    else
        FAILED=1
    fi

    # Test 10: Buildx with docker.io/moby BuildKit should FAIL
    echo ""
    echo "=== Test 10: Buildx with docker.io/moby BuildKit should FAIL ==="
    cat > "${TEST_DIR}/workflow.buildx-dockerhub.yml" << 'EOF'
      - name: Set up Docker Buildx
        id: buildx
        uses: docker/setup-buildx-action@v3
        with:
          driver-opts: |
            image=docker.io/moby/buildkit:buildx-stable-1
EOF

    test10_passed=false
    if grep -qE "docker\.io/moby/buildkit:buildx-stable-1" "${TEST_DIR}/workflow.buildx-dockerhub.yml" 2>/dev/null; then
        test10_passed=true
    fi

    if [[ "${test10_passed}" == true ]]; then
        echo "  PASS: Buildx docker.io/moby BuildKit correctly detected"
    else
        echo "  FAIL: Buildx docker.io/moby BuildKit not detected"
        FAILED=1
    fi

    # Test 11: Comments containing setup-buildx-action should NOT inflate count
    echo ""
    echo "=== Test 11: setup-buildx-action in comments should not inflate count ==="
    cat > "${TEST_DIR}/workflow.buildx-comment.yml" << 'EOF'
      # Patch BuildKit containers after they are created by setup-buildx-action
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
        with:
          driver-opts: |
            image=harbor-pve1.spbnix.local/dockerhub-cache/moby/buildkit:buildx-stable-1
EOF

    test11_passed=true
    buildx_count=$(grep -cE "uses:[[:space:]]+docker/setup-buildx-action@v[0-9]+" "${TEST_DIR}/workflow.buildx-comment.yml" 2>/dev/null || echo 0)
    harbor_buildkit_count=$(grep -cE "^[[:space:]]*image=${PROXY_CACHE_HOST}/dockerhub-cache/moby/buildkit" "${TEST_DIR}/workflow.buildx-comment.yml" 2>/dev/null || echo 0)

    if [[ "${buildx_count}" -ne 1 ]]; then
        test11_passed=false
        echo "  FAIL: Comment inflated Buildx count (${buildx_count})"
    fi

    if [[ "${harbor_buildkit_count}" -ne 1 ]]; then
        test11_passed=false
        echo "  FAIL: Harbor BuildKit override not counted (${harbor_buildkit_count})"
    fi

    if [[ "${test11_passed}" == true ]]; then
        echo "  PASS: Comment mention did not inflate Buildx count"
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
echo "Docker Build Locality Verification"
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
echo "  3. setup-buildx-action must use Harbor proxy cache for BuildKit builder image"
echo "  4. docker/build-push-action must use registry cache, not GHA cache"
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
    if grep -qE "uses:[[:space:]]+docker/setup-qemu-action@v[0-9]+" "${workflow}"; then
        qemu_count=$(grep -cE "uses:[[:space:]]+docker/setup-qemu-action@v[0-9]+" "${workflow}" 2>/dev/null || echo 0)
        harbor_image_count=$(grep -cE "^[[:space:]]*image:[[:space:]]*${PROXY_CACHE_HOST}/dockerhub-cache/tonistiigi/binfmt" "${workflow}" 2>/dev/null || echo 0)

        if [[ ${qemu_count} -gt 0 ]] && [[ ${harbor_image_count} -lt ${qemu_count} ]]; then
            echo "  FAIL: QEMU section missing Harbor image override (${harbor_image_count}/${qemu_count} have it)"
            echo "        Expected: image: ${HARBOR_BINFMT_IMAGE}"
            echo "        QEMU silently falls back to DockerHub default without this override"
            FAILED=1
            FAILED_QEMU_IMAGE=1
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
    # Rule 3: Buildx must have Harbor BuildKit image override
    # -------------------------------------------------------------------------
    if grep -qE "uses:[[:space:]]+docker/setup-buildx-action@v[0-9]+" "${workflow}"; then
        buildx_count=$(grep -cE "uses:[[:space:]]+docker/setup-buildx-action@v[0-9]+" "${workflow}" 2>/dev/null || echo 0)
        harbor_buildkit_count=$(grep -cE "^[[:space:]]*image=${PROXY_CACHE_HOST}/dockerhub-cache/moby/buildkit" "${workflow}" 2>/dev/null || echo 0)

        if [[ ${buildx_count} -gt 0 ]] && [[ ${harbor_buildkit_count} -lt ${buildx_count} ]]; then
            echo "  FAIL: Buildx section missing Harbor BuildKit image override (${harbor_buildkit_count}/${buildx_count} have it)"
            echo "        Expected: driver-opts with image=${HARBOR_BUILDKIT_IMAGE}"
            echo "        Buildx silently pulls default moby/buildkit without this override"
            FAILED=1
        else
            echo "  OK: All Buildx sections use Harbor BuildKit image override"
        fi
    fi

    # -------------------------------------------------------------------------
    # Rule 4: No explicit unproxied BuildKit images
    # -------------------------------------------------------------------------
    if grep -qE "image=moby/buildkit:buildx-stable-1" "${workflow}"; then
        echo "  FAIL: Found explicit unproxied BuildKit image (should use Harbor proxy)"
        FAILED=1
    fi
    if grep -qE "image: moby/buildkit:buildx-stable-1" "${workflow}"; then
        echo "  FAIL: Found explicit unproxied BuildKit image (should use Harbor proxy)"
        FAILED=1
    fi
    if grep -qE "docker\.io/moby/buildkit:buildx-stable-1" "${workflow}"; then
        echo "  FAIL: Found explicit DockerHub BuildKit image (should use Harbor proxy)"
        FAILED=1
    fi

    # -------------------------------------------------------------------------
    # Rule 5: No GHA cache usage
    # -------------------------------------------------------------------------
    if grep -qE "type=gha" "${workflow}"; then
        echo "  FAIL: Found GHA cache usage (must use Harbor registry cache)"
        FAILED=1
    else
        echo "  OK: No GHA cache usage"
    fi

    # -------------------------------------------------------------------------
    # Rule 6: Must have registry cache for build-push-action (hard fail)
    # -------------------------------------------------------------------------
    if grep -qE "docker/build-push-action" "${workflow}"; then
        if grep -qE "type=registry,ref=${PROXY_CACHE_HOST}/k9b/cache" "${workflow}"; then
            echo "  OK: Uses Harbor registry cache"
        else
            echo "  FAIL: build-push-action missing registry cache (hard fail)"
            echo "        Required: cache-from/cache-to with type=registry,ref=${PROXY_CACHE_HOST}/k9b/cache/..."
            FAILED=1
        fi
    fi

    echo ""
done

# =============================================================================
# Python Dockerfile checks
# =============================================================================

# Python Dockerfiles to check
PYTHON_DOCKERFILES=(
    "${REPO_ROOT}/Dockerfile.python"
)

# Additional rules for Python Dockerfiles
echo "----------------------------------------"
echo "Python Dockerfile Checks:"
echo "  7. pip install must not use --no-cache-dir for dependency installs"
echo "  8. Python Dockerfiles should use BuildKit pip cache mounts"
echo "  9. pip dependency install should precede high-churn COPY src/"
echo ""

for dockerfile in "${PYTHON_DOCKERFILES[@]}"; do
    if [[ ! -f "${dockerfile}" ]]; then
        echo "WARNING: ${dockerfile} not found, skipping"
        continue
    fi

    echo "Checking: ${dockerfile}"

    # -------------------------------------------------------------------------
    # Rule 7: No pip install --no-cache-dir for dependency installs
    # -------------------------------------------------------------------------
    # Pattern: pip install --no-cache-dir followed by COPY src or COPY scripts
    # This is the anti-pattern that causes layer invalidation on code changes
    if grep -qE "pip install.*--no-cache-dir" "${dockerfile}"; then
        # Check if the no-cache-dir pip install appears after COPY src/scripts
        # (within 20 lines) - this is the anti-pattern
        no_cache_lines=$(grep -nE "pip install.*--no-cache-dir" "${dockerfile}" 2>/dev/null | cut -d: -f1 || true)
        src_copy_lines=$(grep -nE "COPY src|COPY scripts" "${dockerfile}" 2>/dev/null | cut -d: -f1 || true)

        detected=false
        for no_cache_line in ${no_cache_lines}; do
            for src_line in ${src_copy_lines}; do
                # If src/scripts COPY appears before (line number lower) than no-cache-dir pip install
                if [[ ${src_line} -lt ${no_cache_line} ]] && [[ $((no_cache_line - src_line)) -lt 30 ]]; then
                    detected=true
                    break 2
                fi
            done
        done

        if [[ "${detected}" == true ]]; then
            echo "  FAIL: pip install --no-cache-dir found after COPY src/scripts"
            echo "        This causes layer invalidation on every code change."
            echo "        Move pip install to before COPY src/ and use BuildKit cache mounts instead."
            FAILED=1
            FAILED_PIP_NO_CACHE=1
        else
            echo "  OK: No anti-pattern pip install --no-cache-dir detected"
        fi
    else
        echo "  OK: No pip install --no-cache-dir found"
    fi

    # -------------------------------------------------------------------------
    # Rule 8: Must have BuildKit pip cache mounts
    # -------------------------------------------------------------------------
    if grep -qE '\-\-mount=type=cache.*target=/root/.cache/pip' "${dockerfile}"; then
        echo "  OK: BuildKit pip cache mounts present"
    else
        echo "  FAIL: Missing BuildKit pip cache mounts (--mount=type=cache,target=/root/.cache/pip)"
        echo "        Add pip cache mounts to avoid re-downloading packages on rebuilds."
        FAILED=1
    fi

    # -------------------------------------------------------------------------
    # Rule 9: pip dependency install should precede COPY src/
    # -------------------------------------------------------------------------
    # Find line numbers for pip install (excluding --no-deps) and COPY src
    # Use grep -v to exclude --no-deps reinstalls which are expected after COPY src
    # Use [[:space:]] for BSD/macOS portability (not \s which is GNU only)
    pip_dep_install_line=$(grep -nE "pip install.*[^n][^o]-[d][e][p][s]" "${dockerfile}" 2>/dev/null | grep -v "\-\-no-deps" | head -1 | cut -d: -f1 || true)
    # Also check for explicit package installs (requests ijson, etc.) which install deps
    pip_explicit_install_line=$(grep -nE "pip[[:space:]]+install[[:space:]]+[a-z]" "${dockerfile}" 2>/dev/null | head -1 | cut -d: -f1 || true)
    src_copy_line=$(grep -nE "COPY src" "${dockerfile}" 2>/dev/null | head -1 | cut -d: -f1 || true)

    # Use the first valid dependency install line
    first_dep_install=""
    if [[ -n "${pip_dep_install_line}" ]]; then
        first_dep_install="${pip_dep_install_line}"
    elif [[ -n "${pip_explicit_install_line}" ]]; then
        first_dep_install="${pip_explicit_install_line}"
    fi

    if [[ -n "${first_dep_install}" ]] && [[ -n "${src_copy_line}" ]]; then
        if [[ ${first_dep_install} -lt ${src_copy_line} ]]; then
            echo "  OK: pip dependency install (line ${first_dep_install}) precedes COPY src (line ${src_copy_line})"
        else
            echo "  FAIL: pip dependency install (line ${first_dep_install}) comes after COPY src (line ${src_copy_line})"
            echo "        This invalidates the dependency layer on every code change."
            echo "        Move pip install to before COPY src/ to enable warm-cache rebuilds."
            FAILED=1
        fi
    fi

    # -------------------------------------------------------------------------
    # Rule 10: SSOT compliance - must use requirements.docker.txt not hardcoded deps
    # -------------------------------------------------------------------------
    # Check if Dockerfile uses requirements.docker.txt (SSOT compliance)
    if grep -qE "requirements\.docker\.txt" "${dockerfile}"; then
        echo "  OK: Dockerfile uses requirements.docker.txt (SSOT compliant)"

        # Check that requirements.docker.txt is fresh relative to pyproject.toml
        if ! bash "${SCRIPT_DIR}/sync-docker-requirements.sh" --check > /dev/null 2>&1; then
            echo "  FAIL: requirements.docker.txt is stale (out of sync with pyproject.toml)"
            echo "        Run: bash scripts/sync-docker-requirements.sh"
            FAILED=1
            FAILED_SSOT_STALE=1
        else
            echo "  OK: requirements.docker.txt is fresh (matches pyproject.toml)"
        fi
    elif grep -qE "pip[[:space:]]+install[[:space:]]+[a-z]" "${dockerfile}" 2>/dev/null; then
        echo "  FAIL: Dockerfile has hardcoded pip packages instead of requirements.docker.txt"
        echo "        This creates SSOT drift risk. Use requirements.docker.txt and sync from pyproject.toml."
        echo "        Run: bash scripts/sync-docker-requirements.sh"
        FAILED=1
    else
        echo "  OK: No hardcoded pip packages detected"
    fi

    echo ""
done

echo "=========================================="
if [[ ${FAILED} -eq 1 ]]; then
    echo "RESULT: FAILED"
    echo ""
    echo "Build locality violations detected. Please fix:"
    
    # Only show relevant remediation items based on what actually failed
    # This avoids showing a wall of irrelevant fixes when only one check failed
    
    if [[ ${FAILED_SSOT_STALE} -eq 1 ]]; then
        echo ""
        echo "  [SSOT] requirements.docker.txt is stale:"
        echo "    Run: bash scripts/sync-docker-requirements.sh"
    fi
    
    if [[ ${FAILED_QEMU_IMAGE} -eq 1 ]]; then
        echo ""
        echo "  [QEMU] Missing Harbor image override:"
        echo "    image: ${HARBOR_BINFMT_IMAGE}"
    fi
    
    if [[ ${FAILED_BUILDX_IMAGE} -eq 1 ]]; then
        echo ""
        echo "  [Buildx] Missing Harbor BuildKit image override:"
        echo "    driver-opts: |"
        echo "      image=${HARBOR_BUILDKIT_IMAGE}"
    fi
    
    if [[ ${FAILED_GHA_CACHE} -eq 1 ]]; then
        echo ""
        echo "  [Cache] GHA cache usage detected (must use Harbor registry cache):"
        echo "    cache-from: type=registry,ref=${PROXY_CACHE_HOST}/k9b/cache/<image>:buildcache"
        echo "    cache-to: type=registry,ref=${PROXY_CACHE_HOST}/k9b/cache/<image>:buildcache,mode=max"
    fi
    
    if [[ ${FAILED_REGISTRY_CACHE} -eq 1 ]]; then
        echo ""
        echo "  [Cache] Missing registry cache for build-push-action:"
        echo "    cache-from: type=registry,ref=${PROXY_CACHE_HOST}/k9b/cache/<image>:buildcache"
        echo "    cache-to: type=registry,ref=${PROXY_CACHE_HOST}/k9b/cache/<image>:buildcache,mode=max"
    fi
    
    if [[ ${FAILED_PIP_NO_CACHE} -eq 1 ]]; then
        echo ""
        echo "  [Dockerfile] pip install --no-cache-dir anti-pattern:"
        echo "    Remove --no-cache-dir, use BuildKit pip cache mounts instead"
    fi
    
    if [[ ${FAILED_PIP_CACHE_MOUNT} -eq 1 ]]; then
        echo ""
        echo "  [Dockerfile] Missing BuildKit pip cache mounts:"
        echo "    Add: --mount=type=cache,target=/root/.cache/pip"
    fi
    
    if [[ ${FAILED_PIP_ORDER} -eq 1 ]]; then
        echo ""
        echo "  [Dockerfile] pip install order issue:"
        echo "    Move pip install to before COPY src/"
    fi
    
    if [[ ${FAILED_SSOT_HARDCODED} -eq 1 ]]; then
        echo ""
        echo "  [SSOT] Dockerfile has hardcoded pip packages:"
        echo "    Use requirements.docker.txt and sync from pyproject.toml"
    fi
    
    echo ""
    exit 1
else
    echo "RESULT: PASSED"
    echo ""
    echo "All Docker builds follow local-first hygiene."
    exit 0
fi
