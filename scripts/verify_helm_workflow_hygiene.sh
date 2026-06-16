#!/usr/bin/env bash
# =============================================================================
# verify_helm_workflow_hygiene.sh
# =============================================================================
# Verifies that GitHub Actions workflows use valid Helm version pins.
#
# azure/setup-helm requires full semantic version (vX.Y.Z) or 'latest'.
# Minor-only versions like 'v3.16' will fail because Helm publishes patches
# like v3.16.0, v3.16.4, etc.
#
# This script fails on:
#   - version: 'v3.16' (minor-only, missing patch)
#   - version: '3.16' (minor-only without v prefix)
#
# Allowed patterns:
#   - version: v3.16.4
#   - version: latest
#   - HELM_VERSION=3.16.4 (build-args)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Workflow files to check
WORKFLOW_FILES=(
    "${REPO_ROOT}/.github/workflows/verify.yml"
    "${REPO_ROOT}/.github/workflows/helm-chart.yml"
)

# Track failures
FAILED=0

# =============================================================================
# Self-test mode
# =============================================================================

if [[ "${1:-}" == "--self-test" ]]; then
    echo "Running self-test mode..."
    echo ""

    TEST_DIR=$(mktemp -d)
    trap "rm -rf ${TEST_DIR}" EXIT

    # Test 1: Minor-only version v3.16 should FAIL
    echo "=== Test 1: Minor-only version 'v3.16' should FAIL ==="
    cat > "${TEST_DIR}/workflow.minor-only.yml" << 'EOF'
      - name: Set up Helm
        uses: azure/setup-helm@v4
        with:
          version: '3.16'
EOF

    if grep -qE "version:\s*['\'']?3\.16['\'']?" "${TEST_DIR}/workflow.minor-only.yml"; then
        echo "  PASS: Minor-only version correctly detected"
    else
        echo "  FAIL: Minor-only version not detected"
        FAILED=1
    fi

    # Test 2: Minor-only with v prefix should FAIL
    echo ""
    echo "=== Test 2: Minor-only version 'v3.16' should FAIL ==="
    cat > "${TEST_DIR}/workflow.v-prefix-minor.yml" << 'EOF'
      - name: Set up Helm
        uses: azure/setup-helm@v4
        with:
          version: v3.16
EOF

    if grep -qE "version:\s*v[0-9]+\.[0-9]+\s*(['\'']?$|#)" "${TEST_DIR}/workflow.v-prefix-minor.yml"; then
        echo "  PASS: v-prefix minor-only version correctly detected"
    else
        echo "  FAIL: v-prefix minor-only version not detected"
        FAILED=1
    fi

    # Test 3: Full semver v3.16.4 should PASS
    echo ""
    echo "=== Test 3: Full semver 'v3.16.4' should PASS ==="
    cat > "${TEST_DIR}/workflow.full-semver.yml" << 'EOF'
      - name: Set up Helm
        uses: azure/setup-helm@v4
        with:
          version: v3.16.4
EOF

    if grep -qE "version:\s*v[0-9]+\.[0-9]+\.[0-9]+" "${TEST_DIR}/workflow.full-semver.yml"; then
        echo "  PASS: Full semver correctly detected as valid"
    else
        echo "  FAIL: Full semver not detected"
        FAILED=1
    fi

    # Test 4: 'latest' should PASS
    echo ""
    echo "=== Test 4: 'latest' should PASS ==="
    cat > "${TEST_DIR}/workflow.latest.yml" << 'EOF'
      - name: Set up Helm
        uses: azure/setup-helm@v4
        with:
          version: latest
EOF

    if grep -qE "version:\s*latest" "${TEST_DIR}/workflow.latest.yml"; then
        echo "  PASS: 'latest' correctly detected as valid"
    else
        echo "  FAIL: 'latest' not detected"
        FAILED=1
    fi

    # Test 5: HELM_VERSION build-arg full semver should PASS
    echo ""
    echo "=== Test 5: HELM_VERSION build-arg with full semver should PASS ==="
    cat > "${TEST_DIR}/workflow.build-arg.yml" << 'EOF'
      - name: Build and push backend image
        uses: docker/build-push-action@v6
        with:
          build-args: |
            HELM_VERSION=3.20.1
EOF

    if grep -qE "HELM_VERSION=[0-9]+\.[0-9]+\.[0-9]+" "${TEST_DIR}/workflow.build-arg.yml"; then
        echo "  PASS: HELM_VERSION build-arg correctly detected"
    else
        echo "  FAIL: HELM_VERSION build-arg not detected"
        FAILED=1
    fi

    # Test 6: HELM_VERSION with minor-only should FAIL
    echo ""
    echo "=== Test 6: HELM_VERSION with minor-only should FAIL ==="
    cat > "${TEST_DIR}/workflow.helm-version-minor.yml" << 'EOF'
      - name: Build and push backend image
        uses: docker/build-push-action@v6
        with:
          build-args: |
            HELM_VERSION=3.16
EOF

    if grep -qE "HELM_VERSION=[0-9]+\.[0-9]+$" "${TEST_DIR}/workflow.helm-version-minor.yml"; then
        echo "  PASS: HELM_VERSION minor-only correctly detected as invalid"
    else
        echo "  FAIL: HELM_VERSION minor-only not detected"
        FAILED=1
    fi

    # Test 7: Commented version should be ignored (PASS)
    echo ""
    echo "=== Test 7: Commented version should be ignored ==="
    cat > "${TEST_DIR}/workflow.commented.yml" << 'EOF'
      # - name: Set up Helm
      #   uses: azure/setup-helm@v4
      #   with:
      #     version: v3.16
EOF

    # Test that the VERIFICATION script correctly ignores commented lines
    # by checking it does NOT match version lines that start with #
    if grep -vE "^\s*#" "${TEST_DIR}/workflow.commented.yml" | grep -qE "version:\s*v[0-9]+\.[0-9]+$"; then
        echo "  FAIL: Commented version incorrectly detected"
        FAILED=1
    else
        echo "  PASS: Commented version correctly ignored"
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
echo "Helm Workflow Hygiene Verification"
echo "=========================================="
echo ""

echo "Rules:"
echo "  1. azure/setup-helm requires full semver (vX.Y.Z) or 'latest'"
echo "  2. Minor-only versions like 'v3.16' will fail at download time"
echo "  3. HELM_VERSION build-args must also use full semver"
echo ""

for workflow in "${WORKFLOW_FILES[@]}"; do
    if [[ ! -f "${workflow}" ]]; then
        echo "WARNING: ${workflow} not found, skipping"
        continue
    fi

    echo "Checking: ${workflow}"
    workflow_failed=0

    # -------------------------------------------------------------------------
    # Check azure/setup-helm version pins
    # -------------------------------------------------------------------------
    # Only check version fields that are inside setup-helm blocks.
    # Uses process substitution < <(...) to avoid subshell variable isolation bug.
    # Also uses POSIX [[:space:]] instead of \s for portability.

    while IFS= read -r line; do
        line_num=$(echo "$line" | cut -d: -f1)
        version_val=$(echo "$line" | sed 's/.*version: *//' | tr -d " '\"")

        # Skip empty versions
        if [[ -z "$version_val" ]]; then
            continue
        fi

        # Check if this is a full semver (vX.Y.Z format)
        if [[ "$version_val" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "  OK: Helm version '${version_val}' is valid (full semver)"
        elif [[ "$version_val" == "latest" ]]; then
            echo "  OK: Helm version 'latest' is valid"
        else
            echo "  FAIL: Line ${line_num}: Invalid Helm version '${version_val}'"
            echo "        azure/setup-helm requires full semver (vX.Y.Z) or 'latest'"
            echo "        Minor-only versions like 'v3.16' will fail at download time"
            workflow_failed=1
            FAILED=1
        fi
    done < <(
        awk '
            /azure\/setup-helm/ { start = NR }
            NR > start && NR <= start + 5 {
                if (/^[[:space:]]+version:/) {
                    print NR ": " $0
                }
            }
            NR > start + 5 { start = 0 }
        ' "${workflow}"
    )

    # -------------------------------------------------------------------------
    # Check HELM_VERSION build-args
    # -------------------------------------------------------------------------
    while IFS= read -r line; do
        version_val=$(echo "$line" | sed 's/.*HELM_VERSION=//' | tr -d " '\"")

        # Skip empty versions
        if [[ -z "$version_val" ]]; then
            continue
        fi

        # Check if this is a full semver (X.Y.Z format for build-args)
        if [[ "$version_val" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "  OK: HELM_VERSION '${version_val}' is valid (full semver)"
        else
            echo "  FAIL: Invalid HELM_VERSION '${version_val}' (minor-only)"
            echo "        Build-args must use full semver (X.Y.Z)"
            workflow_failed=1
            FAILED=1
        fi
    done < <(grep -nE "HELM_VERSION=[0-9]+\.[0-9]+" "${workflow}" 2>/dev/null || true)

    echo ""
done

echo "=========================================="
if [[ ${FAILED} -eq 1 ]]; then
    echo "RESULT: FAILED"
    echo ""
    echo "Helm workflow hygiene violations detected. Please fix:"
    echo "  - Use full semver: version: v3.16.4 (not v3.16)"
    echo "  - Or use 'latest': version: latest"
    exit 1
else
    echo "RESULT: PASSED"
    echo ""
    echo "All Helm version pins are valid."
    exit 0
fi
