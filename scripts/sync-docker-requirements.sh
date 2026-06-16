#!/usr/bin/env bash
# =============================================================================
# sync-docker-requirements.sh
# =============================================================================
# Generates requirements.docker.txt from pyproject.toml dependencies.
# Run this whenever pyproject.toml dependencies change.
#
# Usage:
#   bash scripts/sync-docker-requirements.sh        # Generate/update requirements.docker.txt
#   bash scripts/sync-docker-requirements.sh --check  # Verify requirements.docker.txt is fresh
#
# This script is the single source of truth (SSOT) for Docker dependency
# installation. The Dockerfile.python MUST use requirements.docker.txt
# rather than hardcoding package names.
#
# SSOT doctrine:
#   - pyproject.toml is the canonical source for Python dependencies
#   - requirements.docker.txt is a generated artifact, never edited manually
#   - verify_docker_build_locality.sh enforces SSOT compliance via --check mode
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYPROJECT="${REPO_ROOT}/pyproject.toml"
OUTPUT="${REPO_ROOT}/requirements.docker.txt"

# Header comment
HEADER="# Auto-generated from pyproject.toml - DO NOT EDIT DIRECTLY
# Regenerate with: bash scripts/sync-docker-requirements.sh
# SSOT: pyproject.toml

"

# Check mode: verify requirements.docker.txt is fresh
CHECK_MODE=false
if [[ "${1:-}" == "--check" ]]; then
    CHECK_MODE=true
fi

generate_requirements() {
    # Extract dependencies from pyproject.toml using grep/sed
    # Looks for the [project] section and extracts the dependencies array
    DEPS=$(grep -A20 '^\[project\]' "${PYPROJECT}" | \
           grep -A10 '^dependencies' | \
           sed -n '2,/]/p' | \
           sed 's/^[ ]*"\(.*\)",*/\1/' | \
           sed 's/^[ ]*"\(.*\)"/\1/' | \
           grep -v '^$' | \
           tr -d '"' | \
           tr -d ',' | \
           grep -v '^]$')

    if [[ -z "${DEPS}" ]]; then
        echo "ERROR: No dependencies found in pyproject.toml" >&2
        return 1
    fi

    # Write to stdout
    echo -n "${HEADER}"
    echo "${DEPS}"
}

if [[ "${CHECK_MODE}" == true ]]; then
    # Check mode: verify requirements.docker.txt matches pyproject.toml
    TMP=$(mktemp)
    trap "rm -f ${TMP}" EXIT

    generate_requirements > "${TMP}"

    if diff -u "${OUTPUT}" "${TMP}" > /dev/null 2>&1; then
        echo "PASS: requirements.docker.txt is fresh (matches pyproject.toml)"
        exit 0
    else
        echo "FAIL: requirements.docker.txt is stale (does not match pyproject.toml)"
        echo ""
        echo "Diff:"
        diff -u "${OUTPUT}" "${TMP}" || true
        echo ""
        echo "Run: bash scripts/sync-docker-requirements.sh"
        exit 1
    fi
else
    # Generate mode
    echo "Generating requirements.docker.txt from ${PYPROJECT}..."

    generate_requirements > "${OUTPUT}"

    echo "Generated ${OUTPUT} with:"
    cat "${OUTPUT}"
    echo ""
    echo "Done. Commit requirements.docker.txt along with pyproject.toml changes."
fi
