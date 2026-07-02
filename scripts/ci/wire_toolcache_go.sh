#!/usr/bin/env bash
# CI-HERMETIC-TOOLCACHE:
# Wire Go from local runner tool cache or PATH.
# Fails fast with diagnostics when Go is not found.
#
# Usage:
#   source scripts/ci/wire_toolcache_go.sh <version>
#
# Exports:
#   GOROOT - Go root directory
#   Adds Go bin to GITHUB_PATH
#
# See docs/ci-hermetic-toolchain.md

set -euo pipefail

GO_VERSION="${1:-1.25}"
# Use AGENT_TOOLSDIRECTORY as fallback (GitHub's internal variable)
TOOL_CACHE="${RUNNER_TOOL_CACHE:-${AGENT_TOOLSDIRECTORY:-/home/runner/_work/_tool}}"

echo "=== Wiring Go ${GO_VERSION} from tool cache ==="
echo "Tool cache root: ${TOOL_CACHE}"

# Go paths to check (in order of preference)
GO_PATHS=(
    "${TOOL_CACHE}/go/${GO_VERSION}/linux-amd64"
    "${TOOL_CACHE}/go/1.25/linux-amd64"
    "${TOOL_CACHE}/go/1.24/linux-amd64"
    "${TOOL_CACHE}/go/1.23/linux-amd64"
)

GO_ROOT=""
for go_p in "${GO_PATHS[@]}"; do
    if [[ -x "${go_p}/bin/go" ]]; then
        GO_ROOT="${go_p}"
        echo "Found Go at: ${go_p}"
        break
    fi
done

# Also check if go is in PATH already (from pre-installed)
if [[ -z "${GO_ROOT}" ]] && command -v go &>/dev/null; then
    GO_ROOT="$(go env GOROOT 2>/dev/null || dirname "$(dirname "$(command -v go)")")"
    echo "Using pre-installed Go at: ${GO_ROOT}"
fi

if [[ -z "${GO_ROOT}" ]]; then
    echo "ERROR: Go ${GO_VERSION} not found in local runner tool cache"
    echo "Searched paths:"
    printf '  - %s\n' "${GO_PATHS[@]}"
    echo "Go is required. Ensure Go is installed in the runner tool cache."
    echo "=== Available Go in tool cache ==="
    find "${TOOL_CACHE}/go" -maxdepth 4 -type d -print 2>/dev/null | sort || echo "No Go directory found"
    exit 1
fi

GO_BIN="${GO_ROOT}/bin"

# Export to current step PATH first
export PATH="${GO_BIN}:${PATH}"

# Append to GITHUB_PATH for subsequent steps
echo "${GO_BIN}" >> "$GITHUB_PATH"
echo "GOROOT=${GO_ROOT}" >> "$GITHUB_ENV"
echo "GO_ROOT=${GO_ROOT}" >> "$GITHUB_OUTPUT"
echo "go-root=${GO_ROOT}" >> "$GITHUB_OUTPUT"

# Verify Go works using the SELECTED Go binary
echo "=== Go version (${GO_BIN}/go) ==="
"${GO_BIN}/go" version

echo "=== Go wiring complete ==="
