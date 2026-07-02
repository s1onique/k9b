#!/usr/bin/env bash
# CI-HERMETIC-TOOLCACHE:
# Wire kubectl from local runner tool cache or PATH.
# Fails fast with diagnostics when kubectl is not found.
#
# Usage:
#   source scripts/ci/wire_toolcache_kubectl.sh <version>
#
# Exports:
#   KUBECTL_PATH - Full path to kubectl binary
#   Adds kubectl dir to GITHUB_PATH
#
# See docs/ci-hermetic-toolchain.md

set -euo pipefail

KUBECTL_VERSION="${1:-v1.31.0}"
# Use AGENT_TOOLSDIRECTORY as fallback (GitHub's internal variable)
TOOL_CACHE="${RUNNER_TOOL_CACHE:-${AGENT_TOOLSDIRECTORY:-/home/runner/_work/_tool}}"

# Derive clean semver (strip leading v) for @actions/tool-cache layout.
KUBECTL_VERSION_CLEAN="${KUBECTL_VERSION#v}"

echo "=== Wiring kubectl ${KUBECTL_VERSION} from tool cache ==="
echo "Tool cache root: ${TOOL_CACHE}"

# kubectl paths to check (in order of preference)
# @actions/tool-cache normalizes semver with semver.clean() so v1.31.0 → 1.31.0
# and uses machine arch default (x64 on linux). It does NOT use linux-amd64/kubectl.
# azure/setup-kubectl returns path.join(cachedToolpath, "kubectl") directly.
KUBECTL_PATHS=(
    # Actions tool-cache / azure/setup-kubectl layout: kubectl/<version>/<arch>/kubectl
    "${TOOL_CACHE}/kubectl/${KUBECTL_VERSION_CLEAN}/x64/kubectl"

    # Defensive fallback if a future cache preserves the v-prefix.
    "${TOOL_CACHE}/kubectl/${KUBECTL_VERSION}/x64/kubectl"

    # Legacy/manual archive-style paths.
    "${TOOL_CACHE}/kubectl/${KUBECTL_VERSION}/linux-amd64/kubectl"
    "${TOOL_CACHE}/kubectl/v1.31.0/linux-amd64/kubectl"
    "${TOOL_CACHE}/kubectl/v1.30.0/linux-amd64/kubectl"
    "${TOOL_CACHE}/kubectl/v1.29.6/linux-amd64/kubectl"
    "${TOOL_CACHE}/kubectl/v1.29.0/linux-amd64/kubectl"
    "${TOOL_CACHE}/kubectl/v1.28.0/linux-amd64/kubectl"
)

KUBECTL_PATH=""
for kubectl_p in "${KUBECTL_PATHS[@]}"; do
    if [[ -x "${kubectl_p}" ]]; then
        KUBECTL_PATH="${kubectl_p}"
        echo "Found kubectl at: ${kubectl_p}"
        break
    fi
done

# Also check if kubectl is in PATH already (from pre-installed)
if [[ -z "${KUBECTL_PATH}" ]] && command -v kubectl &>/dev/null; then
    KUBECTL_PATH="$(command -v kubectl)"
    echo "Using pre-installed kubectl at: ${KUBECTL_PATH}"
fi

if [[ -z "${KUBECTL_PATH}" ]]; then
    echo "ERROR: kubectl ${KUBECTL_VERSION} not found in local runner tool cache"
    echo "Searched paths:"
    printf '  - %s\n' "${KUBECTL_PATHS[@]}"
    echo "kubectl is required. Ensure kubectl is installed in the runner tool cache."
    echo "=== kubectl tool-cache files ==="
    find "${TOOL_CACHE}/kubectl" -maxdepth 5 -print 2>/dev/null | sort || echo "No kubectl directory found"
    exit 1
fi

KUBECTL_DIR="$(dirname "${KUBECTL_PATH}")"

# Export to current step PATH first
export PATH="${KUBECTL_DIR}:${PATH}"

# Append to GITHUB_PATH for subsequent steps
echo "${KUBECTL_DIR}" >> "$GITHUB_PATH"
echo "KUBECTL_PATH=${KUBECTL_PATH}" >> "$GITHUB_OUTPUT"
echo "kubectl_path=${KUBECTL_PATH}" >> "$GITHUB_OUTPUT"

# Verify kubectl works using the SELECTED kubectl binary
echo "=== kubectl version (${KUBECTL_PATH}) ==="
"${KUBECTL_PATH}" version --client

echo "=== kubectl wiring complete ==="
