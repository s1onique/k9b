#!/usr/bin/env bash
# CI-HERMETIC-TOOLCACHE:
# Wire Helm from local runner tool cache or PATH.
# Fails fast with diagnostics when Helm is not found.
#
# Usage:
#   source scripts/ci/wire_toolcache_helm.sh <version>
#
# Exports:
#   HELM_PATH - Full path to Helm binary
#   Adds Helm dir to GITHUB_PATH
#
# See docs/ci-hermetic-toolchain.md

set -euo pipefail

HELM_VERSION="${1:-3.16.4}"
# Use AGENT_TOOLSDIRECTORY as fallback (GitHub's internal variable)
TOOL_CACHE="${RUNNER_TOOL_CACHE:-${AGENT_TOOLSDIRECTORY:-/home/runner/_work/_tool}}"

echo "=== Wiring Helm ${HELM_VERSION} from tool cache ==="
echo "Tool cache root: ${TOOL_CACHE}"

# Helm paths to check (in order of preference)
HELM_PATHS=(
    "${TOOL_CACHE}/helm/${HELM_VERSION}/linux-amd64/helm"
    "${TOOL_CACHE}/helm/3.16.3/linux-amd64/helm"
    "${TOOL_CACHE}/helm/3.16.2/linux-amd64/helm"
    "${TOOL_CACHE}/helm/3.16.1/linux-amd64/helm"
    "${TOOL_CACHE}/helm/3.16.0/linux-amd64/helm"
    "${TOOL_CACHE}/helm/3.15.0/linux-amd64/helm"
    "${TOOL_CACHE}/helm/3.14.0/linux-amd64/helm"
    "${TOOL_CACHE}/helm/3.13.0/linux-amd64/helm"
)

HELM_PATH=""
for helm_p in "${HELM_PATHS[@]}"; do
    if [[ -x "${helm_p}" ]]; then
        HELM_PATH="${helm_p}"
        echo "Found Helm at: ${helm_p}"
        break
    fi
done

# Also check if helm is in PATH already (from pre-installed)
if [[ -z "${HELM_PATH}" ]] && command -v helm &>/dev/null; then
    HELM_PATH="$(command -v helm)"
    echo "Using pre-installed Helm at: ${HELM_PATH}"
fi

if [[ -z "${HELM_PATH}" ]]; then
    echo "ERROR: Helm ${HELM_VERSION} not found in local runner tool cache"
    echo "Searched paths:"
    printf '  - %s\n' "${HELM_PATHS[@]}"
    echo "Helm is required. Ensure Helm is installed in the runner tool cache."
    echo "=== Available Helm in tool cache ==="
    find "${TOOL_CACHE}/helm" -maxdepth 4 -type d -print 2>/dev/null | sort || echo "No Helm directory found"
    exit 1
fi

HELM_DIR="$(dirname "${HELM_PATH}")"

# Export to current step PATH first
export PATH="${HELM_DIR}:${PATH}"

# Append to GITHUB_PATH for subsequent steps
echo "${HELM_DIR}" >> "$GITHUB_PATH"
echo "HELM_PATH=${HELM_PATH}" >> "$GITHUB_OUTPUT"
echo "helm_path=${HELM_PATH}" >> "$GITHUB_OUTPUT"

# Verify Helm works using the SELECTED Helm binary
echo "=== Helm version (${HELM_PATH}) ==="
"${HELM_PATH}" version --short

echo "=== Helm wiring complete ==="
