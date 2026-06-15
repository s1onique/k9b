#!/usr/bin/env bash
# =============================================================================
# verify_helm_oci_login.sh
# =============================================================================
# Verifies that GitHub Actions Helm chart workflow follows proper Harbor OCI
# authentication for ARC/k3s runners:
#   - Must authenticate to harbor-pve1.spbnix.local (internal hostname)
#   - Must push to oci://harbor-pve1.spbnix.local/... (internal hostname)
#   - No auth mirroring between registry.spbnix.com and harbor-pve1.spbnix.local
#   - No --insecure-skip-tls-verify flags
#   - No secrets echoed or printed
#
# This script fails on:
#   - Pushing to registry.spbnix.com from Harbor workflows
#   - Auth mirroring patterns (.auths["harbor-pve1.spbnix.local"] = ...)
#   - --insecure-skip-tls-verify usage
#   - Direct login to registry.spbnix.com (should use internal hostname)
#   - Secrets echoed or printed in workflow
#   - Near-miss hostnames (ingress.local, harbor-pve1, etc.)
#
# Self-test mode (--self-test):
#   Proves that forbidden patterns fail and correct patterns pass.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Required hostnames for Harbor push workflows
INTERNAL_HOST="harbor-pve1.spbnix.local"
EXPECTED_PUSH_TARGET="oci://harbor-pve1.spbnix.local/k9b"

# Forbidden patterns
FORBIDDEN_EXTERNAL_HOST="registry.spbnix.com"

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
    cat > "${TEST_DIR}/workflow.wrong-host.yml" << 'EOF'
      - name: Log in to Harbor
        uses: docker/login-action@v4
        with:
          registry: registry.spbnix.com
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}
      - name: Push chart to Harbor OCI
        run: |
          helm push "$PACKAGE_FILE" "oci://registry.spbnix.com/k9b"
EOF

    test1_passed=false
    if grep -qE "oci://registry\.spbnix\.com" "${TEST_DIR}/workflow.wrong-host.yml" 2>/dev/null; then
        test1_passed=true
    fi

    if [[ "${test1_passed}" == true ]]; then
        echo "  PASS: Wrong hostname in push target correctly detected"
    else
        echo "  FAIL: Wrong hostname in push target not detected"
        FAILED=1
    fi

    # Test 2: Auth mirroring should FAIL
    echo ""
    echo "=== Test 2: Auth mirroring should FAIL ==="
    cat > "${TEST_DIR}/workflow.auth-mirror.yml" << 'EOF'
      - name: Log in to Harbor
        uses: docker/login-action@v4
        with:
          registry: harbor-pve1.spbnix.local
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}
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
      - name: Push chart to Harbor OCI
        run: |
          helm push "$PACKAGE_FILE" "oci://harbor-pve1.spbnix.local/k9b" --insecure-skip-tls-verify
EOF

    test3_passed=false
    if grep -qE "\-\-insecure-skip-tls-verify" "${TEST_DIR}/workflow.insecure-tls.yml" 2>/dev/null; then
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
      - name: Log in to Harbor
        uses: docker/login-action@v4
        with:
          registry: harbor-pve1.spbnix.local
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}
      - name: Push chart to Harbor OCI
        run: |
          helm push "$PACKAGE_FILE" "oci://harbor-pve1.spbnix.local/k9b"
EOF

    test4_passed=true
    # Check internal hostname login present
    if ! grep -qE "registry:.*harbor-pve1\.spbnix\.local" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test4_passed=false
        echo "  FAIL: Missing internal hostname login"
    fi
    # Check correct push target
    if ! grep -qE "helm push.*oci://harbor-pve1\.spbnix\.local/k9b" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test4_passed=false
        echo "  FAIL: Incorrect push target"
    fi
    # Check no insecure TLS
    if grep -qE "\-\-insecure-skip-tls-verify" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test4_passed=false
        echo "  FAIL: Found insecure TLS flag"
    fi

    if [[ "${test4_passed}" == true ]]; then
        echo "  PASS: Correct patterns correctly allowed"
    else
        FAILED=1
    fi

    # Test 5: Login to registry.spbnix.com should FAIL
    echo ""
    echo "=== Test 5: Login to registry.spbnix.com should FAIL ==="
    cat > "${TEST_DIR}/workflow.external-login.yml" << 'EOF'
      - name: Log in to Harbor (external hostname)
        uses: docker/login-action@v4
        with:
          registry: registry.spbnix.com
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}
EOF

    test5_passed=false
    if grep -qE "registry:.*registry\.spbnix\.com" "${TEST_DIR}/workflow.external-login.yml" 2>/dev/null; then
        test5_passed=true
    fi

    if [[ "${test5_passed}" == true ]]; then
        echo "  PASS: External hostname login correctly detected"
    else
        echo "  FAIL: External hostname login not detected"
        FAILED=1
    fi

    # Test 6: Missing registry hostname in Docker tag should FAIL
    echo ""
    echo "=== Test 6: Missing registry hostname in tag should FAIL ==="
    cat > "${TEST_DIR}/workflow.missing-registry.yml" << 'EOF'
      - name: Build and push backend image
        uses: docker/build-push-action@v6
        with:
          tags: k9b-backend:latest
EOF

    test6_passed=false
    if grep -qE "^\s+tags:\s*k9b-backend" "${TEST_DIR}/workflow.missing-registry.yml" 2>/dev/null; then
        test6_passed=true
    fi

    if [[ "${test6_passed}" == true ]]; then
        echo "  PASS: Missing registry hostname correctly detected"
    else
        echo "  FAIL: Missing registry hostname not detected"
        FAILED=1
    fi

    # Test 7: ingress.local should FAIL
    echo ""
    echo "=== Test 7: ingress.local should FAIL ==="
    cat > "${TEST_DIR}/workflow.ingress-local.yml" << 'EOF'
      - name: Log in to Harbor
        uses: docker/login-action@v4
        with:
          registry: ingress.local
EOF

    test7_passed=false
    if grep -qE "registry:.*ingress\.local" "${TEST_DIR}/workflow.ingress-local.yml" 2>/dev/null; then
        test7_passed=true
    fi

    if [[ "${test7_passed}" == true ]]; then
        echo "  PASS: ingress.local correctly detected"
    else
        echo "  FAIL: ingress.local not detected"
        FAILED=1
    fi

    # Test 8: harbor-pve1 (short form) should FAIL
    echo ""
    echo "=== Test 8: harbor-pve1 (short form) should FAIL ==="
    cat > "${TEST_DIR}/workflow.short-host.yml" << 'EOF'
      - name: Log in to Harbor
        uses: docker/login-action@v4
        with:
          registry: harbor-pve1
EOF

    test8_passed=false
    if grep -qE "registry:.*harbor-pve1\b" "${TEST_DIR}/workflow.short-host.yml" 2>/dev/null; then
        test8_passed=true
    fi

    if [[ "${test8_passed}" == true ]]; then
        echo "  PASS: Short hostname correctly detected"
    else
        echo "  FAIL: Short hostname not detected"
        FAILED=1
    fi

    # Test 9: http:// protocol should FAIL
    echo ""
    echo "=== Test 9: http:// protocol should FAIL ==="
    cat > "${TEST_DIR}/workflow.http-protocol.yml" << 'EOF'
      - name: Log in to Harbor
        uses: docker/login-action@v4
        with:
          registry: http://harbor-pve1.spbnix.local
EOF

    test9_passed=false
    if grep -qE "registry:.*http://" "${TEST_DIR}/workflow.http-protocol.yml" 2>/dev/null; then
        test9_passed=true
    fi

    if [[ "${test9_passed}" == true ]]; then
        echo "  PASS: http:// protocol correctly detected"
    else
        echo "  FAIL: http:// protocol not detected"
        FAILED=1
    fi

    # Test 10: Port :443 should FAIL (unless explicitly required)
    echo ""
    echo "=== Test 10: Port :443 should FAIL ==="
    cat > "${TEST_DIR}/workflow.port-443.yml" << 'EOF'
      - name: Log in to Harbor
        uses: docker/login-action@v4
        with:
          registry: harbor-pve1.spbnix.local:443
EOF

    test10_passed=false
    if grep -qE "registry:.*:443" "${TEST_DIR}/workflow.port-443.yml" 2>/dev/null; then
        test10_passed=true
    fi

    if [[ "${test10_passed}" == true ]]; then
        echo "  PASS: Port :443 correctly detected"
    else
        echo "  FAIL: Port :443 not detected"
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
echo "Helm OCI Login Verification"
echo "=========================================="
echo ""

# Workflow files to check
WORKFLOW_FILES=(
    "${REPO_ROOT}/.github/workflows/helm-chart.yml"
)

# Rules
echo "Rules:"
echo "  1. Must authenticate to ${INTERNAL_HOST} (internal hostname)"
echo "  2. Push target must be oci://${INTERNAL_HOST}/..."
echo "  3. No auth mirroring between registries"
echo "  4. No --insecure-skip-tls-verify flags"
echo "  5. No login to ${FORBIDDEN_EXTERNAL_HOST}"
echo "  6. No near-miss hostnames"
echo "  7. No secrets echoed or printed"
echo ""

for workflow in "${WORKFLOW_FILES[@]}"; do
    if [[ ! -f "${workflow}" ]]; then
        echo "WARNING: ${workflow} not found, skipping"
        continue
    fi

    echo "Checking: ${workflow}"
    WORKFLOW_FAILED=0

    # -------------------------------------------------------------------------
    # Rule 1: Must log in to internal hostname
    # -------------------------------------------------------------------------
    if grep -qE "registry:.*${INTERNAL_HOST}" "${workflow}"; then
        echo "  OK: Login to ${INTERNAL_HOST} found"
    elif grep -q 'registry:.*\${{ env\.REGISTRY }}' "${workflow}"; then
        # Check if REGISTRY is set to internal hostname
        if grep -qE "REGISTRY:.*${INTERNAL_HOST}" "${workflow}"; then
            echo "  OK: Login to ${INTERNAL_HOST} found (via \${{ env.REGISTRY }})"
        else
            echo "  FAIL: Login uses \${{ env.REGISTRY }} but REGISTRY is not set to ${INTERNAL_HOST}"
            WORKFLOW_FAILED=1
            FAILED=1
        fi
    else
        echo "  FAIL: Missing login to ${INTERNAL_HOST}"
        WORKFLOW_FAILED=1
        FAILED=1
    fi

    # -------------------------------------------------------------------------
    # Rule 2: Push target must be internal hostname
    # -------------------------------------------------------------------------
    if grep -qE "helm push.*oci://${INTERNAL_HOST}" "${workflow}"; then
        echo "  OK: Push target uses ${INTERNAL_HOST}"
    elif grep -qE "helm push.*\"\\\${PUSH_TARGET}\"" "${workflow}"; then
        # Check if PUSH_TARGET resolves to internal hostname
        if grep -qE "PUSH_TARGET=.*oci://\\\${REGISTRY}" "${workflow}"; then
            if grep -qE "REGISTRY:.*${INTERNAL_HOST}" "${workflow}"; then
                echo "  OK: Push target uses ${INTERNAL_HOST} (via \$PUSH_TARGET)"
            else
                echo "  FAIL: PUSH_TARGET uses \$REGISTRY but REGISTRY is not set to ${INTERNAL_HOST}"
                WORKFLOW_FAILED=1
                FAILED=1
            fi
        else
            echo "  FAIL: Push target uses \$PUSH_TARGET but PUSH_TARGET does not resolve to ${INTERNAL_HOST}"
            WORKFLOW_FAILED=1
            FAILED=1
        fi
    elif grep -qE 'helm push.*oci://\$\{REGISTRY\}' "${workflow}"; then
        # Check if REGISTRY is set to internal hostname
        if grep -qE "REGISTRY:.*${INTERNAL_HOST}" "${workflow}"; then
            echo "  OK: Push target uses ${INTERNAL_HOST} (via \$REGISTRY)"
        else
            echo "  FAIL: Push target uses \$REGISTRY but REGISTRY is not set to ${INTERNAL_HOST}"
            WORKFLOW_FAILED=1
            FAILED=1
        fi
    else
        echo "  FAIL: Push target does not use ${INTERNAL_HOST}"
        WORKFLOW_FAILED=1
        FAILED=1
    fi

    # -------------------------------------------------------------------------
    # Rule 3: No auth mirroring
    # -------------------------------------------------------------------------
    workflow_lines=$(tr '\n' ' ' < "${workflow}")
    if echo "${workflow_lines}" | grep -qE '\.auths\["harbor-pve1\.spbnix\.local"\]\s*='; then
        echo "  FAIL: Auth mirroring detected (forbidden)"
        WORKFLOW_FAILED=1
        FAILED=1
    else
        echo "  OK: No auth mirroring"
    fi

    # -------------------------------------------------------------------------
    # Rule 4: No --insecure-skip-tls-verify
    # -------------------------------------------------------------------------
    if grep -qE "\-\-insecure-skip-tls-verify" "${workflow}"; then
        echo "  FAIL: --insecure-skip-tls-verify found (must use secure TLS)"
        WORKFLOW_FAILED=1
        FAILED=1
    else
        echo "  OK: No insecure TLS flags"
    fi

    # -------------------------------------------------------------------------
    # Rule 5: No login to forbidden external hostname
    # -------------------------------------------------------------------------
    if grep -qE "registry:.*${FORBIDDEN_EXTERNAL_HOST}" "${workflow}"; then
        echo "  FAIL: Login to ${FORBIDDEN_EXTERNAL_HOST} found (should use ${INTERNAL_HOST})"
        WORKFLOW_FAILED=1
        FAILED=1
    else
        echo "  OK: No login to ${FORBIDDEN_EXTERNAL_HOST}"
    fi

    # -------------------------------------------------------------------------
    # Rule 6: No near-miss hostnames
    # -------------------------------------------------------------------------
    # Check for ingress.local
    if grep -qE "registry:.*ingress\.local" "${workflow}"; then
        echo "  FAIL: Near-miss hostname 'ingress.local' found"
        WORKFLOW_FAILED=1
        FAILED=1
    fi

    # Check for harbor-pve1 without .spbnix.local
    if grep -qE "registry:.*harbor-pve1\b" "${workflow}"; then
        # Make sure it's not followed by .spbnix.local
        if ! grep -qE "registry:.*harbor-pve1\.spbnix\.local" "${workflow}"; then
            echo "  FAIL: Near-miss hostname 'harbor-pve1' found"
            WORKFLOW_FAILED=1
            FAILED=1
        fi
    fi

    # Check for http:// protocol
    if grep -qE "registry:.*http://" "${workflow}"; then
        echo "  FAIL: http:// protocol found (should use https)"
        WORKFLOW_FAILED=1
        FAILED=1
    fi

    # Check for explicit port :443
    if grep -qE "registry:.*:443" "${workflow}"; then
        echo "  FAIL: Explicit port :443 found"
        WORKFLOW_FAILED=1
        FAILED=1
    fi

    if ! grep -qE "(registry:.*ingress\.local|registry:.*harbor-pve1[^.]|registry:.*http://|registry:.*:443)" "${workflow}"; then
        echo "  OK: No near-miss hostnames"
    fi

    # -------------------------------------------------------------------------
    # Rule 7: No secret echo/print
    # -------------------------------------------------------------------------
    if grep -qE "(echo|printenv).*\${{ secrets\.(HARBOR_USERNAME|HARBOR_TOKEN|PASSWORD) }}" "${workflow}"; then
        echo "  FAIL: Found secret echo/print in workflow"
        WORKFLOW_FAILED=1
        FAILED=1
    elif grep -qE "(echo|printenv)\s+['\"]\$\{?(secrets\.)?HARBOR_" "${workflow}"; then
        echo "  FAIL: Found secret echo/print in workflow"
        WORKFLOW_FAILED=1
        FAILED=1
    else
        echo "  OK: No secret echo/print detected"
    fi

    if [[ ${WORKFLOW_FAILED} -eq 1 ]]; then
        echo "  Workflow verification FAILED"
    fi

    echo ""
done

echo "=========================================="
if [[ ${FAILED} -eq 1 ]]; then
    echo "RESULT: FAILED"
    echo ""
    echo "Helm OCI login violations detected. Please fix:"
    echo "  1. Login to ${INTERNAL_HOST}"
    echo "  2. Push target must be oci://${INTERNAL_HOST}/..."
    echo "  3. Remove auth mirroring"
    echo "  4. Remove --insecure-skip-tls-verify"
    echo "  5. No login to ${FORBIDDEN_EXTERNAL_HOST}"
    echo "  6. Use exact hostname ${INTERNAL_HOST}"
    echo "  7. Do not echo or print secrets"
    exit 1
else
    echo "RESULT: PASSED"
    echo ""
    echo "Helm OCI workflow follows correct registry hygiene."
    exit 0
fi
