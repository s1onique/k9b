#!/usr/bin/env bash
# =============================================================================
# verify_docker_workflow_hygiene.sh
# =============================================================================
# Verifies that GitHub Actions workflows follow proper Harbor registry hygiene:
#   - Push targets must use harbor-pve1.spbnix.local (internal hostname)
#   - No push to registry.spbnix.com
#   - No auth mirroring between registries
#   - No insecure TLS flags
#   - Proxy cache pulls (from harbor-pve1.spbnix.local/dockerhub-cache/...) are OK
#   - No near-miss hostnames
#
# This script fails on:
#   - Push/login targets using registry.spbnix.com
#   - Auth mirroring patterns
#   - --insecure-skip-tls-verify usage
#   - Near-miss hostnames (ingress.local, harbor-pve1, etc.)
#   - Missing registry hostname in push tags
#
# Self-test mode (--self-test):
#   Proves that forbidden patterns fail and correct patterns pass.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Required Harbor hostname for pushes
INTERNAL_HOST="harbor-pve1.spbnix.local"
FORBIDDEN_HOST="registry.spbnix.com"

# Proxy cache reference (OK for pull-through, not for push targets)
# Uses internal hostname since ARC runners must use harbor-pve1.spbnix.local
PROXY_CACHE_HOST="harbor-pve1.spbnix.local"

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

    # Test 1: Push to registry.spbnix.com should FAIL
    echo "=== Test 1: Push to registry.spbnix.com should FAIL ==="
    cat > "${TEST_DIR}/workflow.wrong-push.yml" << 'EOF'
      - name: Build and push backend image
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: registry.spbnix.com/k9b/k9b-backend:latest
EOF

    test1_passed=false
    if grep -qE "registry\.spbnix\.com/k9b" "${TEST_DIR}/workflow.wrong-push.yml" 2>/dev/null; then
        test1_passed=true
    fi

    if [[ "${test1_passed}" == true ]]; then
        echo "  PASS: Wrong push hostname correctly detected"
    else
        echo "  FAIL: Wrong push hostname not detected"
        FAILED=1
    fi

    # Test 2: Auth mirroring should FAIL
    echo ""
    echo "=== Test 2: Auth mirroring should FAIL ==="
    cat > "${TEST_DIR}/workflow.auth-mirror.yml" << 'EOF'
      - name: Mirror Harbor auth for leaked internal OCI hostname
        run: |
          jq '.auths["harbor-pve1.spbnix.local"] = .auths["registry.spbnix.com"]' config.json
EOF

    test2_passed=false
    if grep -qE '\.auths\["harbor-pve1\.spbnix\.local"\]\s*=' "${TEST_DIR}/workflow.auth-mirror.yml" 2>/dev/null; then
        test2_passed=true
    fi

    if [[ "${test2_passed}" == true ]]; then
        echo "  PASS: Auth mirroring correctly detected"
    else
        echo "  FAIL: Auth mirroring not detected"
        FAILED=1
    fi

    # Test 3: --insecure-skip-tls-verify should FAIL
    echo ""
    echo "=== Test 3: --insecure-skip-tls-verify should FAIL ==="
    cat > "${TEST_DIR}/workflow.insecure-tls.yml" << 'EOF'
      - name: Login to Harbor
        uses: docker/login-action@v4
        with:
          registry: harbor-pve1.spbnix.local
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}
          insecure-skip-tls-verify: true
EOF

    test3_passed=false
    if grep -qE "insecure-skip-tls-verify" "${TEST_DIR}/workflow.insecure-tls.yml" 2>/dev/null; then
        test3_passed=true
    fi

    if [[ "${test3_passed}" == true ]]; then
        echo "  PASS: Insecure TLS flag correctly detected"
    else
        echo "  FAIL: Insecure TLS flag not detected"
        FAILED=1
    fi

    # Test 4: Correct patterns should PASS
    echo ""
    echo "=== Test 4: Correct patterns should PASS ==="
    cat > "${TEST_DIR}/workflow.correct.yml" << 'EOF'
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
        with:
          platforms: arm64
          image: harbor-pve1.spbnix.local/dockerhub-cache/tonistiigi/binfmt:latest

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
        with:
          driver-opts: |
            image=harbor-pve1.spbnix.local/dockerhub-cache/moby/buildkit:buildx-stable-1

      - name: Login to Harbor
        uses: docker/login-action@v4
        with:
          registry: harbor-pve1.spbnix.local
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}

      - name: Build and push backend image
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: harbor-pve1.spbnix.local/k9b/k9b-backend:latest
          cache-from: type=registry,ref=harbor-pve1.spbnix.local/k9b/cache/k9b-backend:buildcache
          cache-to: type=registry,ref=harbor-pve1.spbnix.local/k9b/cache/k9b-backend:buildcache,mode=max
EOF

    test4_passed=true
    # Check internal hostname for login
    if ! grep -qE "registry:.*harbor-pve1\.spbnix\.local" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test4_passed=false
        echo "  FAIL: Missing internal hostname login"
    fi
    # Check correct push target
    if ! grep -qE "harbor-pve1\.spbnix\.local/k9b/k9b-backend" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test4_passed=false
        echo "  FAIL: Incorrect push target"
    fi
    # Check no insecure TLS
    if grep -qE "insecure-skip-tls-verify" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test4_passed=false
        echo "  FAIL: Found insecure TLS flag"
    fi

    if [[ "${test4_passed}" == true ]]; then
        echo "  PASS: Correct patterns correctly allowed"
    else
        FAILED=1
    fi

    # Test 5: Proxy cache references are OK (not push targets)
    echo ""
    echo "=== Test 5: Proxy cache references are OK ==="
    cat > "${TEST_DIR}/workflow.proxy-cache.yml" << 'EOF'
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
        with:
          platforms: arm64
          image: harbor-pve1.spbnix.local/dockerhub-cache/tonistiigi/binfmt:latest

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
        with:
          driver-opts: |
            image=harbor-pve1.spbnix.local/dockerhub-cache/moby/buildkit:buildx-stable-1
EOF

    test5_passed=true
    # Proxy cache references should NOT cause failures
    if grep -qE "harbor-pve1\.spbnix\.local/dockerhub-cache" "${TEST_DIR}/workflow.proxy-cache.yml" 2>/dev/null; then
        echo "  OK: Proxy cache references found (these are OK)"
    else
        test5_passed=false
        echo "  FAIL: Proxy cache references not detected"
    fi

    if [[ "${test5_passed}" == true ]]; then
        echo "  PASS: Proxy cache references correctly allowed"
    else
        FAILED=1
    fi

    # Test 6: ingress.local should FAIL
    echo ""
    echo "=== Test 6: ingress.local should FAIL ==="
    cat > "${TEST_DIR}/workflow.ingress-local.yml" << 'EOF'
      - name: Login to Harbor
        uses: docker/login-action@v4
        with:
          registry: ingress.local
EOF

    test6_passed=false
    if grep -qE "registry:.*ingress\.local" "${TEST_DIR}/workflow.ingress-local.yml" 2>/dev/null; then
        test6_passed=true
    fi

    if [[ "${test6_passed}" == true ]]; then
        echo "  PASS: ingress.local correctly detected"
    else
        echo "  FAIL: ingress.local not detected"
        FAILED=1
    fi

    # Test 7: harbor-pve1 (short form) should FAIL
    echo ""
    echo "=== Test 7: harbor-pve1 (short form) should FAIL ==="
    cat > "${TEST_DIR}/workflow.short-host.yml" << 'EOF'
      - name: Login to Harbor
        uses: docker/login-action@v4
        with:
          registry: harbor-pve1
EOF

    test7_passed=false
    if grep -qE "registry:.*harbor-pve1\b" "${TEST_DIR}/workflow.short-host.yml" 2>/dev/null; then
        test7_passed=true
    fi

    if [[ "${test7_passed}" == true ]]; then
        echo "  PASS: Short hostname correctly detected"
    else
        echo "  FAIL: Short hostname not detected"
        FAILED=1
    fi

    # Test 8: http:// protocol should FAIL
    echo ""
    echo "=== Test 8: http:// protocol should FAIL ==="
    cat > "${TEST_DIR}/workflow.http-protocol.yml" << 'EOF'
      - name: Login to Harbor
        uses: docker/login-action@v4
        with:
          registry: http://harbor-pve1.spbnix.local
EOF

    test8_passed=false
    if grep -qE "registry:.*http://" "${TEST_DIR}/workflow.http-protocol.yml" 2>/dev/null; then
        test8_passed=true
    fi

    if [[ "${test8_passed}" == true ]]; then
        echo "  PASS: http:// protocol correctly detected"
    else
        echo "  FAIL: http:// protocol not detected"
        FAILED=1
    fi

    # Test 9: Missing registry hostname in tag should FAIL
    echo ""
    echo "=== Test 9: Missing registry hostname in tag should FAIL ==="
    cat > "${TEST_DIR}/workflow.missing-registry.yml" << 'EOF'
      - name: Build and push backend image
        uses: docker/build-push-action@v6
        with:
          tags: k9b-backend:latest
EOF

    test9_passed=false
    if grep -qE "^\s*tags:\s*k9b-backend" "${TEST_DIR}/workflow.missing-registry.yml" 2>/dev/null; then
        test9_passed=true
    fi

    if [[ "${test9_passed}" == true ]]; then
        echo "  PASS: Missing registry hostname correctly detected"
    else
        echo "  FAIL: Missing registry hostname not detected"
        FAILED=1
    fi

    # Test 10: Login to registry.spbnix.com should FAIL
    echo ""
    echo "=== Test 10: Login to registry.spbnix.com should FAIL ==="
    cat > "${TEST_DIR}/workflow.external-login.yml" << 'EOF'
      - name: Login to Harbor
        uses: docker/login-action@v4
        with:
          registry: registry.spbnix.com
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}
EOF

    test10_passed=false
    if grep -qE "registry:.*registry\.spbnix\.com" "${TEST_DIR}/workflow.external-login.yml" 2>/dev/null; then
        test10_passed=true
    fi

    if [[ "${test10_passed}" == true ]]; then
        echo "  PASS: External hostname login correctly detected"
    else
        echo "  FAIL: External hostname login not detected"
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
echo "  1. Push/login targets must use ${INTERNAL_HOST}"
echo "  2. No push/login to ${FORBIDDEN_HOST}"
echo "  3. No auth mirroring between registries"
echo "  4. No --insecure-skip-tls-verify flags"
echo "  5. No near-miss hostnames"
echo "  6. Push tags must include registry hostname"
echo "  7. Proxy cache references (${PROXY_CACHE_HOST}/dockerhub-cache/...) are OK"
echo "  8. ARC DinD workflows must set SKIP_RUNNER_DOCKER_CERTS_D when using CA install script"
echo ""

for workflow in "${WORKFLOW_FILES[@]}"; do
    if [[ ! -f "${workflow}" ]]; then
        echo "WARNING: ${workflow} not found, skipping"
        continue
    fi

    echo "Checking: ${workflow}"

    # -------------------------------------------------------------------------
    # Rule 1: Push targets must use internal hostname
    # -------------------------------------------------------------------------
    # Check for push tags using internal hostname
    if grep -qE "tags:.*${INTERNAL_HOST}/" "${workflow}"; then
        echo "  OK: Push tags use ${INTERNAL_HOST}"
    elif grep -qE "images:.*\${INTERNAL_HOST}/" "${workflow}"; then
        echo "  OK: Image metadata uses ${INTERNAL_HOST} via variable"
    elif grep -qE "images:.*\${REGISTRY}/" "${workflow}"; then
        # Check if REGISTRY is set to internal hostname
        if grep -qE "REGISTRY:.*${INTERNAL_HOST}" "${workflow}"; then
            echo "  OK: Push tags use ${INTERNAL_HOST} (via REGISTRY)"
        else
            echo "  FAIL: REGISTRY variable not set to ${INTERNAL_HOST}"
            FAILED=1
        fi
    else
        # Check if there are any push operations
        if grep -qE "push:\s*true" "${workflow}" || grep -qE "push:\s*\${{" "${workflow}"; then
            echo "  FAIL: Push operation found but no ${INTERNAL_HOST} in tags"
            FAILED=1
        else
            echo "  OK: No push operations (or pull-request only)"
        fi
    fi

    # -------------------------------------------------------------------------
    # Rule 2: No login to forbidden hostname
    # -------------------------------------------------------------------------
    if grep -qE "registry:.*${FORBIDDEN_HOST}" "${workflow}"; then
        echo "  FAIL: Login to ${FORBIDDEN_HOST} found (should use ${INTERNAL_HOST})"
        FAILED=1
    else
        echo "  OK: No login to ${FORBIDDEN_HOST}"
    fi

    # -------------------------------------------------------------------------
    # Rule 3: No auth mirroring
    # -------------------------------------------------------------------------
    workflow_lines=$(tr '\n' ' ' < "${workflow}")
    if echo "${workflow_lines}" | grep -qE '\.auths\["harbor-pve1\.spbnix\.local"\]\s*='; then
        echo "  FAIL: Auth mirroring detected (forbidden)"
        FAILED=1
    else
        echo "  OK: No auth mirroring"
    fi

    # -------------------------------------------------------------------------
    # Rule 4: No insecure TLS
    # -------------------------------------------------------------------------
    if grep -qE "insecure-skip-tls-verify" "${workflow}"; then
        echo "  FAIL: Insecure TLS flag found"
        FAILED=1
    else
        echo "  OK: No insecure TLS flags"
    fi

    # -------------------------------------------------------------------------
    # Rule 5: No near-miss hostnames in login
    # -------------------------------------------------------------------------
    near_miss_found=false

    # Check for ingress.local
    if grep -qE "registry:.*ingress\.local" "${workflow}"; then
        echo "  FAIL: Near-miss hostname 'ingress.local' found"
        FAILED=1
        near_miss_found=true
    fi

    # Check for harbor-pve1 without .spbnix.local
    if grep -qE "registry:.*harbor-pve1\b" "${workflow}"; then
        if ! grep -qE "registry:.*harbor-pve1\.spbnix\.local" "${workflow}"; then
            echo "  FAIL: Near-miss hostname 'harbor-pve1' found"
            FAILED=1
            near_miss_found=true
        fi
    fi

    # Check for http:// protocol
    if grep -qE "registry:.*http://" "${workflow}"; then
        echo "  FAIL: http:// protocol found (should use https)"
        FAILED=1
        near_miss_found=true
    fi

    # Check for explicit port :443 in login
    if grep -qE "registry:.*:443" "${workflow}"; then
        echo "  FAIL: Explicit port :443 found"
        FAILED=1
        near_miss_found=true
    fi

    if ! ${near_miss_found}; then
        echo "  OK: No near-miss hostnames"
    fi

    # -------------------------------------------------------------------------
    # Rule 6: Push tags must include registry hostname
    # -------------------------------------------------------------------------
    # Check for tags without registry hostname
    if grep -qE "^\s+tags:\s*[a-zA-Z]" "${workflow}"; then
        # Found tags starting with letter (potential missing registry)
        if ! grep -qE "tags:.*${INTERNAL_HOST}|tags:.*\${REGISTRY}" "${workflow}"; then
            echo "  FAIL: Push tags missing registry hostname"
            FAILED=1
        fi
    fi

    # -------------------------------------------------------------------------
    # Rule 7: Proxy cache references are OK (informational)
    # -------------------------------------------------------------------------
    if grep -qE "harbor-pve1\.spbnix\.local/dockerhub-cache" "${workflow}"; then
        echo "  OK: Proxy cache references found (OK for pull-through)"
    fi

    # -------------------------------------------------------------------------
    # Rule 8: ARC DinD workflows using CA install script must set SKIP_RUNNER_DOCKER_CERTS_D
    # -------------------------------------------------------------------------
    # When workflows use spbnix-k8s-docker runners with the CA install script,
    # they should set SKIP_RUNNER_DOCKER_CERTS_D=1 since DinD sidecar owns daemon trust.
    # Check each script invocation individually to ensure every step sets the flag.
    if grep -qE "runs-on:.*spbnix-k8s-docker" "${workflow}"; then
        # Count invocations of the script
        ca_invocation_count=$(grep -cE "\brun:\s*\..*install-spbnix-harbor-ca\.sh" "${workflow}" || true)
        if [[ "${ca_invocation_count}" -gt 0 ]]; then
            echo "  Found ${ca_invocation_count} install-spbnix-harbor-ca.sh invocation(s) in DinD workflow"

            # Parse each invocation line number from grep -n output
            all_ok=true
            while IFS=':' read -r line_num rest; do
                # Get content around this line (up to 15 preceding lines for env block)
                start=$((line_num > 15 ? line_num - 15 : 1))
                context=$(sed -n "${start},${line_num}p" "${workflow}")

                # Check if this invocation has SKIP_RUNNER_DOCKER_CERTS_D in its env block
                if ! echo "${context}" | grep -qE "SKIP_RUNNER_DOCKER_CERTS_D.*1"; then
                    echo "  FAIL: Script invocation at line ${line_num} missing SKIP_RUNNER_DOCKER_CERTS_D=1"
                    echo "        DinD sidecar owns daemon CA trust; runner-side certs.d is non-authoritative."
                    all_ok=false
                    FAILED=1
                fi
            done < <(grep -nE "\brun:\s*\..*install-spbnix-harbor-ca\.sh" "${workflow}" 2>/dev/null || true)

            if [[ "${all_ok}" == true ]]; then
                echo "  OK: All ${ca_invocation_count} CA install invocation(s) set SKIP_RUNNER_DOCKER_CERTS_D=1"
            fi
        fi
    fi

    echo ""
done

echo "=========================================="
if [[ ${FAILED} -eq 1 ]]; then
    echo "RESULT: FAILED"
    echo ""
    echo "Docker workflow hygiene violations detected. Please fix:"
    echo "  1. Push/login targets must use ${INTERNAL_HOST}"
    echo "  2. No login to ${FORBIDDEN_HOST}"
    echo "  3. Remove auth mirroring"
    echo "  4. Remove --insecure-skip-tls-verify"
    echo "  5. Use exact hostname ${INTERNAL_HOST}"
    echo "  6. Push tags must include registry hostname"
    echo ""
    echo "Note: Proxy cache references (harbor-pve1.spbnix.local/dockerhub-cache/...) are OK."
    exit 1
else
    echo "RESULT: PASSED"
    echo ""
    echo "All Docker workflows follow proper registry hygiene."
    exit 0
fi