#!/usr/bin/env bash
# CI-HERMETIC-TOOLCACHE:
# Wire Python from local runner tool cache.
# Fails fast with diagnostics when Python is not found.
#
# Usage:
#   source scripts/ci/wire_toolcache_python.sh <version>
#
# Exports:
#   PYTHON_BIN_DIR - Python binary directory
#   Adds Python bin to GITHUB_PATH
#   Adds Python lib to LD_LIBRARY_PATH via GITHUB_ENV
#
# See docs/ci-hermetic-toolchain.md

set -euo pipefail

PYTHON_VERSION="${1:-3.13.14}"
# Use AGENT_TOOLSDIRECTORY as fallback (GitHub's internal variable)
TOOL_CACHE="${RUNNER_TOOL_CACHE:-${AGENT_TOOLSDIRECTORY:-/home/runner/_work/_tool}}"

echo "=== Wiring Python ${PYTHON_VERSION} from tool cache ==="
echo "Tool cache root: ${TOOL_CACHE}"

# Python bin paths to check (in order of preference)
PYTHON_PATHS=(
    "${TOOL_CACHE}/Python/${PYTHON_VERSION}/x64/bin"
    "${TOOL_CACHE}/Python/3.13.14/x64/bin"
    "${TOOL_CACHE}/Python/3.13.13/x64/bin"
    "${TOOL_CACHE}/Python/3.13.12/x64/bin"
    "${TOOL_CACHE}/Python/3.13.11/x64/bin"
    "${TOOL_CACHE}/Python/3.13.10/x64/bin"
    "${TOOL_CACHE}/Python/3.13.9/x64/bin"
    "${TOOL_CACHE}/Python/3.13.8/x64/bin"
    "${TOOL_CACHE}/Python/3.13.7/x64/bin"
    "${TOOL_CACHE}/Python/3.13.6/x64/bin"
    "${TOOL_CACHE}/Python/3.13.5/x64/bin"
    "${TOOL_CACHE}/Python/3.13.4/x64/bin"
    "${TOOL_CACHE}/Python/3.13.3/x64/bin"
    "${TOOL_CACHE}/Python/3.13.2/x64/bin"
    "${TOOL_CACHE}/Python/3.13.1/x64/bin"
    "${TOOL_CACHE}/Python/3.13.0/x64/bin"
)

PYTHON_BIN=""
for python_path in "${PYTHON_PATHS[@]}"; do
    if [[ -x "${python_path}/python3" ]]; then
        PYTHON_BIN="${python_path}/python3"
        echo "Found Python at: ${python_path}"
        break
    fi
done

if [[ -z "${PYTHON_BIN}" ]]; then
    echo "ERROR: Python ${PYTHON_VERSION} not found in tool cache"
    echo "=== Available Python in tool cache ==="
    find "${TOOL_CACHE}/Python" -maxdepth 4 -type d -print 2>/dev/null | sort || echo "No Python directory found"
    echo "=== Tool cache root ==="
    ls -la "${TOOL_CACHE}" 2>/dev/null || echo "Tool cache not accessible"
    exit 1
fi

# Export Python bin directory
PYTHON_BIN_DIR="$(dirname "${PYTHON_BIN}")"
echo "python_bin_dir=${PYTHON_BIN_DIR}" >> "$GITHUB_OUTPUT"
echo "python_bin=${PYTHON_BIN}" >> "$GITHUB_OUTPUT"

# Compute PYTHON_LIBDIR from the selected Python, NOT from ambient python3
PYTHON_ROOT="$(dirname "${PYTHON_BIN_DIR}")"
PYTHON_LIBDIR="${PYTHON_ROOT}/lib"

# Export to current step PATH first (before writing to GITHUB_PATH for subsequent steps)
export PATH="${PYTHON_BIN_DIR}:${PATH}"

# Append to PATH via GITHUB_PATH (for subsequent steps)
echo "${PYTHON_BIN_DIR}" >> "$GITHUB_PATH"
echo "PATH extended with: ${PYTHON_BIN_DIR}"

# Set LD_LIBRARY_PATH for shared library linking
if [[ -d "${PYTHON_LIBDIR}" ]]; then
    export LD_LIBRARY_PATH="${PYTHON_LIBDIR}:${LD_LIBRARY_PATH:-}"
    echo "LD_LIBRARY_PATH=${PYTHON_LIBDIR}:${LD_LIBRARY_PATH:-}" >> "$GITHUB_ENV"
    echo "LD_LIBRARY_PATH set to: ${PYTHON_LIBDIR}"
fi

# Verify Python works using the SELECTED Python binary (not ambient python3)
echo "=== Python startup proof (using ${PYTHON_BIN}) ==="
"${PYTHON_BIN}" -VV
"${PYTHON_BIN}" -c "import sys; print('sys.executable:', sys.executable)"
"${PYTHON_BIN}" -c "import ssl; print('SSL OK')"

echo "=== Python wiring complete ==="
