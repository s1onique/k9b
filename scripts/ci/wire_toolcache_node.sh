#!/usr/bin/env bash
# CI-HERMETIC-TOOLCACHE:
# Wire Node.js from local runner tool cache or PATH.
# Fails fast with diagnostics when Node is not found.
#
# Usage:
#   source scripts/ci/wire_toolcache_node.sh <version>
#
# Exports:
#   NODE_PATH - Full path to Node.js binary directory
#   Adds Node.js bin to GITHUB_PATH
#
# See docs/ci-hermetic-toolchain.md

set -euo pipefail

NODE_VERSION="${1:-22.12.0}"
# Use AGENT_TOOLSDIRECTORY as fallback (GitHub's internal variable)
TOOL_CACHE="${RUNNER_TOOL_CACHE:-${AGENT_TOOLSDIRECTORY:-/home/runner/_work/_tool}}"

echo "=== Wiring Node.js ${NODE_VERSION} from tool cache ==="
echo "Tool cache root: ${TOOL_CACHE}"

# Node.js paths to check (in order of preference)
NODE_PATHS=(
    "${TOOL_CACHE}/node/${NODE_VERSION}/x64/bin"
    "${TOOL_CACHE}/node/22.12.0/x64/bin"
    "${TOOL_CACHE}/node/22.11.0/x64/bin"
    "${TOOL_CACHE}/node/22.10.0/x64/bin"
    "${TOOL_CACHE}/node/22.9.0/x64/bin"
    "${TOOL_CACHE}/node/22.8.0/x64/bin"
    "${TOOL_CACHE}/node/20.18.0/x64/bin"
    "${TOOL_CACHE}/node/20.17.0/x64/bin"
    "${TOOL_CACHE}/node/20.16.0/x64/bin"
)

NODE_BIN=""
for node_p in "${NODE_PATHS[@]}"; do
    if [[ -x "${node_p}/node" ]]; then
        NODE_BIN="${node_p}/node"
        NODE_DIR="${node_p}"
        echo "Found Node.js at: ${node_p}"
        break
    fi
done

# Also check if node is in PATH already (from pre-installed)
if [[ -z "${NODE_BIN}" ]] && command -v node &>/dev/null; then
    NODE_DIR="$(dirname "$(command -v node)")"
    NODE_BIN="$(command -v node)"
    echo "Using pre-installed Node.js at: ${NODE_BIN}"
fi

if [[ -z "${NODE_BIN}" ]]; then
    echo "ERROR: Node.js ${NODE_VERSION} not found in local runner tool cache"
    echo "Searched paths:"
    printf '  - %s\n' "${NODE_PATHS[@]}"
    echo "Node.js is required. Ensure Node.js is installed in the runner tool cache."
    echo "=== Available Node.js in tool cache ==="
    find "${TOOL_CACHE}/node" -maxdepth 4 -type d -print 2>/dev/null | sort || echo "No Node.js directory found"
    exit 1
fi

# Export to current step PATH first
export PATH="${NODE_DIR}:${PATH}"

# Append to GITHUB_PATH for subsequent steps
echo "${NODE_DIR}" >> "$GITHUB_PATH"
echo "NODE_PATH=${NODE_DIR}" >> "$GITHUB_OUTPUT"
echo "node_path=${NODE_DIR}" >> "$GITHUB_OUTPUT"

# Verify Node.js works using the SELECTED Node binary
echo "=== Node.js version (${NODE_BIN}) ==="
"${NODE_BIN}" --version
npm --version

echo "=== Node.js wiring complete ==="
