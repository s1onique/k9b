#!/usr/bin/env bash
# =============================================================================
# verify_helm_oci_login.sh
# =============================================================================
# Verifies that GitHub Actions Helm chart workflow follows the Harbor OCI
# auth-mirroring workaround:
#   - Authenticates to registry.spbnix.com (external/public hostname)
#   - Mirrors auth entry to harbor-pve1.spbnix.local via Docker config
#   - Push target remains oci://registry.spbnix.com/k9b
#   - Uses --insecure-skip-tls-verify only on helm push (for leaked blob transport)
#   - No secrets are echoed or printed
#
# This script fails on:
#   - Missing authentication for registry.spbnix.com
#   - Missing auth mirroring to harbor-pve1.spbnix.local
#   - helm push target changed away from oci://registry.spbnix.com/k9b
#   - Direct helm/docker login to internal hostname
#   - --password usage (credentials should be in Docker config via login-action)
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

    # Test 6: Correct patterns should PASS (auth-mirroring contract)
    echo ""
    echo "=== Test 6: Correct auth-mirroring patterns should PASS ==="
    cat > "${TEST_DIR}/workflow.correct.yml" << 'EOF'
      - name: Log in to Harbor (external hostname)
        uses: docker/login-action@v4
        with:
          registry: registry.spbnix.com
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}

      - name: Mirror Harbor auth for leaked internal OCI hostname
        shell: bash
        run: |
          jq '.auths["harbor-pve1.spbnix.local"] = .auths["registry.spbnix.com"]' config.json

      - name: Push chart to Harbor OCI
        run: |
          helm push "$PACKAGE_FILE" "oci://registry.spbnix.com/k9b" --insecure-skip-tls-verify
EOF

    test6_passed=true

    # Check external login present
    if ! grep -qE "registry:.*registry\.spbnix\.com" "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test6_passed=false
        echo "  FAIL: Missing external host login"
    fi
    # Check auth mirroring present (new contract)
    workflow_lines=$(tr '\n' ' ' < "${TEST_DIR}/workflow.correct.yml")
    if ! echo "${workflow_lines}" | grep -qE '\.auths\["harbor-pve1\.spbnix\.local"\]'; then
        test6_passed=false
        echo "  FAIL: Missing auth mirroring to internal hostname"
    fi
    # Check push target is correct
    if ! grep -qE 'helm push.*oci://registry\.spbnix\.com/k9b' "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test6_passed=false
        echo "  FAIL: Incorrect push target"
    fi
    # Check --insecure-skip-tls-verify present on helm push
    if ! grep -qE 'helm push.*--insecure-skip-tls-verify' "${TEST_DIR}/workflow.correct.yml" 2>/dev/null; then
        test6_passed=false
        echo "  FAIL: Missing --insecure-skip-tls-verify on helm push"
    fi

    if [[ "${test6_passed}" == true ]]; then
        echo "  PASS: Correct auth-mirroring patterns correctly allowed"
    else
        FAILED=1
    fi

    # Test 7: Missing auth mirror should FAIL
    echo ""
    echo "=== Test 7: Missing auth mirroring should FAIL ==="
    cat > "${TEST_DIR}/workflow.missing-mirror.yml" << 'EOF'
      - name: Log in to Harbor (external hostname)
        uses: docker/login-action@v4
        with:
          registry: registry.spbnix.com
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_TOKEN }}

      - name: Push chart to Harbor OCI
        run: |
          helm push "$PACKAGE_FILE" "oci://registry.spbnix.com/k9b" --insecure-skip-tls-verify
EOF

    test7_passed=false
    workflow_lines=$(tr '\n' ' ' < "${TEST_DIR}/workflow.missing-mirror.yml")
    if ! echo "${workflow_lines}" | grep -qE '\.auths\["harbor-pve1\.spbnix\.local"\]'; then
        test7_passed=true
    fi

    if [[ "${test7_passed}" == true ]]; then
        echo "  PASS: Missing auth mirroring correctly detected"
    else
        echo "  FAIL: Missing auth mirroring not detected"
        FAILED=1
    fi

    # Test 8: Direct internal login should FAIL
    echo ""
    echo "=== Test 8: Direct internal docker login should FAIL ==="
    cat > "${TEST_DIR}/workflow.direct-internal.yml" << 'EOF'
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
EOF

    test8_passed=false
    # This should fail because there's direct login to internal hostname
    if grep -qE "registry:.*harbor-pve1\.spbnix\.local" "${TEST_DIR}/workflow.direct-internal.yml" 2>/dev/null; then
        test8_passed=true
    fi

    if [[ "${test8_passed}" == true ]]; then
        echo "  PASS: Direct internal login correctly detected"
    else
        echo "  FAIL: Direct internal login not detected"
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
echo "  1. Must authenticate to ${EXTERNAL_HOST} (external hostname via docker/login-action)"
echo "  2. Must mirror auth entry to ${INTERNAL_HOST} (auth-mirroring workaround)"
echo "  3. Push target must remain ${EXPECTED_PUSH_TARGET}"
echo "  4. No direct helm/docker login to internal hostname"
echo "  5. --insecure-skip-tls-verify allowed only on helm push"
echo "  6. No secrets echoed or printed"
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
    # Rule 2: Must mirror auth entry to internal hostname (auth-mirroring workaround)
    # -------------------------------------------------------------------------
    # Check for auth mirroring pattern:
    #   .auths["harbor-pve1.spbnix.local"] = .auths["registry.spbnix.com"]
    # This is the expected workaround since internal hostname is not a first-class
    # login endpoint and Harbor rejects login probes.
    workflow_lines=$(tr '\n' ' ' < "${workflow}")
    if echo "${workflow_lines}" | grep -qE '\.auths\["'"${INTERNAL_HOST}"'"\]'; then
        echo "  OK: Auth mirroring to ${INTERNAL_HOST} found (workaround active)"
    else
        echo "  FAIL: Missing auth mirroring to ${INTERNAL_HOST} (workaround not applied)"
        echo "        Harbor leaks internal hostname in OCI blob-upload redirects."
        echo "        Auth entry must be mirrored from ${EXTERNAL_HOST} for redirects to succeed."
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
    # Rule 4: No direct helm/docker login to internal hostname
    # -------------------------------------------------------------------------
    # Direct login to internal hostname should fail; use auth mirroring instead
    # Extract each step and check if it's a login-action with internal hostname
    # This avoids false positives from jq auth mirroring in run blocks
    if grep -qE "uses: docker/login-action" "${workflow}"; then
        # Use awk to find steps with login-action and check their registry
        internal_login_found=$(
            awk '
                /^[[:space:]]*- name:/ { name=$0 }
                /uses: docker\/login-action/ {
                    in_login_step=1
                }
                /with:/ && in_login_step {
                    in_with_block=1
                }
                /registry:/ && in_with_block {
                    if ($2 ~ /'"${INTERNAL_HOST}"'/) {
                        print "FOUND"
                        exit 0
                    }
                }
                /^[[:space:]]*- name:/ && name != "" {
                    in_login_step=0
                    in_with_block=0
                    name=""
                }
            ' "${workflow}"
        )
        
        if [[ "${internal_login_found}" == "FOUND" ]]; then
            echo "  FAIL: Direct docker/login-action to ${INTERNAL_HOST} found"
            echo "        Use auth mirroring instead (internal host is not a login endpoint)"
            WORKFLOW_FAILED=1
            FAILED=1
        else
            echo "  OK: No direct docker/login-action to internal hostname"
        fi
    fi
    
    # Also check for helm registry login to internal hostname
    if grep -qE "helm registry login" "${workflow}"; then
        workflow_lines=$(tr '\n' ' ' < "${workflow}")
        if echo "${workflow_lines}" | grep -qE "helm registry login.*${INTERNAL_HOST}"; then
            echo "  FAIL: Direct helm registry login to ${INTERNAL_HOST} found"
            echo "        Use auth mirroring instead (internal host is not a login endpoint)"
            WORKFLOW_FAILED=1
            FAILED=1
        fi
    fi

    # -------------------------------------------------------------------------
    # Rule 5: --insecure-skip-tls-verify only allowed on helm push
    # -------------------------------------------------------------------------
    # Check for --insecure-skip-tls-verify outside helm push context
    if grep -qE "\-\-insecure-skip-tls-verify" "${workflow}"; then
        # Check if it's on helm push command
        workflow_lines=$(tr '\n' ' ' < "${workflow}")
        if echo "${workflow_lines}" | grep -qE "helm push.*\-\-insecure-skip-tls-verify"; then
            echo "  OK: --insecure-skip-tls-verify on helm push (allowed for blob transport)"
        else
            echo "  FAIL: --insecure-skip-tls-verify outside helm push context"
            WORKFLOW_FAILED=1
            FAILED=1
        fi
    else
        echo "  OK: No --insecure-skip-tls-verify (or using proper TLS)"
    fi

    # -------------------------------------------------------------------------
    # Rule 6: No secret echo/print
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
    echo "  1. Add login to ${EXTERNAL_HOST} via docker/login-action"
    echo "  2. Mirror auth entry to ${INTERNAL_HOST} in Docker config"
    echo "  3. Keep push target as ${EXPECTED_PUSH_TARGET}"
    echo "  4. No direct helm/docker login to internal hostname"
    echo "  5. Use --insecure-skip-tls-verify only on helm push"
    echo "  6. Do not echo or print secrets"
    exit 1
else
    echo "RESULT: PASSED"
    echo ""
    echo "Helm OCI workflow follows auth-mirroring workaround hygiene."
    exit 0
fi
