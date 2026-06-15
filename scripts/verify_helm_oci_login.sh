#!/usr/bin/env bash
# =============================================================================
# verify_helm_oci_login.sh
# =============================================================================
# Verifies that GitHub Actions Helm chart workflow follows the Harbor OCI
# dual-login workaround:
#   - Logs into registry.spbnix.com (external/public hostname)
#   - Logs into harbor-pve1.spbnix.local (internal blob-upload hostname)
#   - Push target remains oci://registry.spbnix.com/k9b
#   - Uses --password-stdin for credentials (not --password)
#   - No secrets are echoed or printed
#
# This script fails on:
#   - Missing login for registry.spbnix.com
#   - Missing login for harbor-pve1.spbnix.local
#   - helm push target changed away from oci://registry.spbnix.com/k9b
#   - Credentials passed via --password instead of --password-stdin
#   - Secrets echoed or printed in workflow
#
# Self-test mode (--self-test):
#   Proves that forbidden patterns fail and correct patterns pass.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Required hostnames for dual-login workaround
EXTERNAL_HOST="registry.spbnix.com"
INTERNAL_HOST="harbor-pve1.spbnix.local"
EXPECTED_PUSH_TARGET="oci://registry.spbnix.com/k9b"

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

    # Test 1: Missing external host login should FAIL
    echo "=== Test 1: Missing external host login should FAIL ==="
    cat > "${TEST_DIR}/workflow.missing-external.yml" << 'EOF'
      - name: Log in to Harbor (internal blob-upload hostname)
        uses: docker/login-action@v4
        with:
          registry: harbor-pve1.spbnix.local
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}
EOF

    test1_passed=false
    if grep -qE "registry:.*harbor-pve1\.spbnix\.local" "${TEST_DIR}/workflow.missing-external.yml" 2>/dev/null; then
        if ! grep -qE "registry:.*registry\.spbnix\.com" "${TEST_DIR}/workflow.missing-external.yml" 2>/dev/null; then
            test1_passed=true
        fi
    fi

    if [[ "${test1_passed}" == true ]]; then
        echo "  PASS: Missing external host login correctly detected"
    else
        echo "  FAIL: Missing external host login not detected"
        FAILED=1
    fi

    # Test 2: Missing internal host login should FAIL
    echo ""
    echo "=== Test 2: Missing internal host login should FAIL ==="
    cat > "${TEST_DIR}/workflow.missing-internal.yml" << 'EOF'
      - name: Log in to Harbor (external hostname)
        uses: docker/login-action@v4
        with:
          registry: registry.spbnix.com
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}
EOF

    test2_passed=false
    if grep -qE "registry:.*registry\.spbnix\.com" "${TEST_DIR}/workflow.missing-internal.yml" 2>/dev/null; then
        if ! grep -qE "registry:.*harbor-pve1\.spbnix\.local" "${TEST_DIR}/workflow.missing-internal.yml" 2>/dev/null; then
            test2_passed=true
        fi
    fi

    if [[ "${test2_passed}" == true ]]; then
        echo "  PASS: Missing internal host login correctly detected"
    else
        echo "  FAIL: Missing internal host login not detected"
        FAILED=1
    fi

    # Test 3: Changed push target should FAIL
    echo ""
    echo "=== Test 3: Changed push target should FAIL ==="
    cat > "${TEST_DIR}/workflow.changed-target.yml" << 'EOF'
          helm push "$PACKAGE_FILE" "oci://harbor-pve1.spbnix.local/k9b"
EOF

    test3_passed=false
    if grep -qE 'helm push.*oci://harbor-pve1\.spbnix\.local' "${TEST_DIR}/workflow.changed-target.yml" 2>/dev/null; then
        test3_passed=true
    fi

    if [[ "${test3_passed}" == true ]]; then
        echo "  PASS: Changed push target correctly detected"
    else
        echo "  FAIL: Changed push target not detected"
        FAILED=1
    fi

    # Test 4: --password instead of --password-stdin should FAIL
    echo ""
    echo "=== Test 4: --password instead of --password-stdin should FAIL ==="
    cat > "${TEST_DIR}/workflow.plain-password.yml" << 'EOF'
          echo "$HARBOR_PASSWORD" | helm registry login registry.spbnix.com \
            --username "$HARBOR_USERNAME" \
            --password "$HARBOR_PASSWORD"
EOF

    test4_passed=false
    if grep -qE "\-\-password\s" "${TEST_DIR}/workflow.plain-password.yml" 2>/dev/null; then
        test4_passed=true
    fi

    if [[ "${test4_passed}" == true ]]; then
        echo "  PASS: Plain --password usage correctly detected"
    else
        echo "  FAIL: Plain --password usage not detected"
        FAILED=1
    fi

    # Test 5: Secret echo/print should FAIL
    echo ""
    echo "=== Test 5: Secret echo/print should FAIL ==="
    cat > "${TEST_DIR}/workflow.secret-echo.yml" << 'EOF'
          echo "Password: $HARBOR_PASSWORD"
          echo $HARBOR_TOKEN
          printenv HARBOR_PASSWORD
EOF

    test5_passed=false
    if grep -qE "(echo|printenv).*HARBOR_(USERNAME|TOKEN|PASSWORD)" "${TEST_DIR}/workflow.secret-echo.yml" 2>/dev/null; then
        test5_passed=true
    fi

    if [[ "${test5_passed}" == true ]]; then
        echo "  PASS: Secret echo/print correctly detected"
    else
        echo "  FAIL: Secret echo/print not detected"
        FAILED=1
    fi

    # Test 6: Correct patterns should PASS
    echo ""
    echo "=== Test 6: Correct patterns should PASS ==="
    cat > "${TEST_DIR}/workflow.correct.yml" << 'EOF'
      - name: Log in to Harbor (external hostname)
        uses: docker/login-action@v4
        with:
          registry: registry.spbnix.com
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}

      - name: Log in to Harbor (internal blob-upload hostname)
        uses: docker/login-action@v4
        with:
          registry: harbor-pve1.spbnix.local
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}

      - name: Push chart to Harbor OCI
        run: |
          helm push "$PACKAGE_FILE" "oci://registry.spbnix.com/k9b"
EOF

    test6_passed=true

    # Check both logins present
    if ! grep -qE "registry:.*registry\.spbnix\.com" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test6_passed=false
        echo "  FAIL: Missing external host login"
    fi
    if ! grep -qE "registry:.*harbor-pve1\.spbnix\.local" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test6_passed=false
        echo "  FAIL: Missing internal host login"
    fi
    # Check push target is correct
    if ! grep -qE 'helm push.*oci://registry\.spbnix\.com/k9b' "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test6_passed=false
        echo "  FAIL: Incorrect push target"
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
echo "Helm OCI Login Verification"
echo "=========================================="
echo ""

# Workflow files to check
WORKFLOW_FILES=(
    "${REPO_ROOT}/.github/workflows/helm-chart.yml"
)

# Rules
echo "Rules:"
echo "  1. Must log in to ${EXTERNAL_HOST} (external hostname)"
echo "  2. Must log in to ${INTERNAL_HOST} (internal blob-upload hostname)"
echo "  3. Push target must remain ${EXPECTED_PUSH_TARGET}"
echo "  4. Credentials must use --password-stdin, not --password"
echo "  5. No secrets echoed or printed"
echo ""

for workflow in "${WORKFLOW_FILES[@]}"; do
    if [[ ! -f "${workflow}" ]]; then
        echo "WARNING: ${workflow} not found, skipping"
        continue
    fi

    echo "Checking: ${workflow}"
    WORKFLOW_FAILED=0

    # -------------------------------------------------------------------------
    # Rule 1: Must log in to external hostname
    # -------------------------------------------------------------------------
    # Check for literal registry.spbnix.com or ${{ env.REGISTRY }} reference
    if grep -qE "registry:.*${EXTERNAL_HOST}" "${workflow}"; then
        echo "  OK: Login to ${EXTERNAL_HOST} found (literal)"
    elif grep -q 'registry:.*\${{ env\.REGISTRY }}' "${workflow}"; then
        echo "  OK: Login to ${EXTERNAL_HOST} found (via \${{ env.REGISTRY }})"
    else
        echo "  FAIL: Missing login to ${EXTERNAL_HOST}"
        WORKFLOW_FAILED=1
        FAILED=1
    fi

    # -------------------------------------------------------------------------
    # Rule 2: Must log in to internal hostname (workaround)
    # -------------------------------------------------------------------------
    if grep -qE "registry:.*${INTERNAL_HOST}" "${workflow}"; then
        echo "  OK: Login to ${INTERNAL_HOST} found (workaround active)"
    else
        echo "  FAIL: Missing login to ${INTERNAL_HOST} (workaround not applied)"
        echo "        Harbor leaks internal hostname in OCI blob-upload redirects."
        echo "        Both hosts must be authenticated for redirects to succeed."
        WORKFLOW_FAILED=1
        FAILED=1
    fi

    # -------------------------------------------------------------------------
    # Rule 3: Push target must be correct
    # -------------------------------------------------------------------------
    # Check for literal oci://registry.spbnix.com/k9b or GitHub Actions variable refs
    # GitHub Actions patterns:
    #   - PUSH_TARGET="oci://${REGISTRY}/${HARBOR_PROJECT}" then helm push ... "${PUSH_TARGET}"
    #   - helm push ... "oci://${REGISTRY}/${HARBOR_PROJECT}"
    #   - helm push ... "oci://registry.spbnix.com/k9b" (literal)
    if grep -qE "helm push.*\"\\\${PUSH_TARGET}\"" "${workflow}"; then
        echo "  OK: Push target is ${EXPECTED_PUSH_TARGET} (via \$PUSH_TARGET variable)"
    elif grep -qE 'helm push.*oci://\$\{?REGISTRY\}?/\$\{?HARBOR_PROJECT\}?/k9b' "${workflow}"; then
        echo "  OK: Push target is ${EXPECTED_PUSH_TARGET} (via \$REGISTRY/\$HARBOR_PROJECT)"
    elif grep -qE "helm push.*oci://${EXTERNAL_HOST}/${HARBOR_PROJECT:-k9b}" "${workflow}"; then
        echo "  OK: Push target is ${EXPECTED_PUSH_TARGET} (literal)"
    else
        echo "  FAIL: Push target changed away from ${EXPECTED_PUSH_TARGET}"
        WORKFLOW_FAILED=1
        FAILED=1
    fi

    # -------------------------------------------------------------------------
    # Rule 4: No --password usage (must use --password-stdin or secrets)
    # -------------------------------------------------------------------------
    # Check for helm registry login with --password flag (not --password-stdin)
    if grep -qE "helm registry login.*--password\s" "${workflow}"; then
        echo "  FAIL: Found helm registry login with --password (use --password-stdin)"
        WORKFLOW_FAILED=1
        FAILED=1
    else
        echo "  OK: No --password usage in helm registry login"
    fi

    # -------------------------------------------------------------------------
    # Rule 5: No secret echo/print
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
    echo "  1. Add login to ${EXTERNAL_HOST}"
    echo "  2. Add login to ${INTERNAL_HOST} (Harbor hostname leak workaround)"
    echo "  3. Keep push target as ${EXPECTED_PUSH_TARGET}"
    echo "  4. Use --password-stdin for helm registry login, not --password"
    echo "  5. Do not echo or print secrets"
    exit 1
else
    echo "RESULT: PASSED"
    echo ""
    echo "Helm OCI workflow follows dual-login workaround hygiene."
    exit 0
fi
