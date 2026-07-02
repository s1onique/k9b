#!/usr/bin/env bash
# CI-HERMETIC-TOOLCACHE:
# Emit hermetic toolchain provenance summary for CI job diagnostics.
#
# Purpose:
#   Print resolved toolchain versions and paths to help diagnose runner/toolcache drift.
#   Output is visible in GitHub Actions job summaries and stdout.
#
# Usage:
#   scripts/ci/emit_toolchain_provenance.sh "python,node,npm,go,helm,kubectl,docker,buildx"
#   K9B_PROVENANCE_REQUIRE="python,node,npm" scripts/ci/emit_toolchain_provenance.sh
#
# Requirements:
#   - Must not download or install anything
#   - Must not use setup/download actions
#   - Must not print secrets
#   - Must write Markdown to $GITHUB_STEP_SUMMARY when set
#   - Must write key outputs to $GITHUB_OUTPUT when set
#   - Must exit non-zero if a required tool is missing or its smoke command fails
#   - Must record missing non-required tools as 'missing' but not fail
#
# See docs/ci-hermetic-toolchain.md

set -euo pipefail

# =============================================================================
# Tool smoke commands
# Each function:
#   - Checks if tool exists via command -v
#   - Collects version/path info
#   - Returns 0 if tool exists, 1 if not
#   - Prints diagnostics to stdout
# =============================================================================

collect_python() {
    local tool="$1"
    local result=""
    local path version_info ssl_info executable

    if ! path=$(command -v python3 2>/dev/null); then
        echo "python|missing||" >> "${PROVENANCE_TSV}"
        MISSING_TOOLS="${MISSING_TOOLS}${MISSING_TOOLS:+,}python"
        return 1
    fi

    # Collect Python info
    version_info=$(python3 -VV 2>&1 || echo "unknown")
    executable=$(python3 -c 'import sys; print(sys.executable)' 2>/dev/null || echo "unknown")
    ssl_info=$(python3 -c 'import ssl; print(ssl.OPENSSL_VERSION)' 2>/dev/null || echo "ssl-unknown")

    result="${version_info}|${executable}"

    echo "python|ok|${path}|${result}" >> "${PROVENANCE_TSV}"
    echo "  python: ok - ${path}"
    echo "    version: ${version_info}"
    echo "    executable: ${executable}"
    echo "    ssl: ${ssl_info}"
    return 0
}

collect_go() {
    local tool="$1"
    local path version_info

    if ! path=$(command -v go 2>/dev/null); then
        echo "go|missing||" >> "${PROVENANCE_TSV}"
        MISSING_TOOLS="${MISSING_TOOLS}${MISSING_TOOLS:+,}go"
        return 1
    fi

    version_info=$(go version 2>&1 || echo "unknown")

    echo "go|ok|${path}|${version_info}" >> "${PROVENANCE_TSV}"
    echo "  go: ok - ${path}"
    echo "    version: ${version_info}"
    return 0
}

collect_node() {
    local tool="$1"
    local path version_info

    if ! path=$(command -v node 2>/dev/null); then
        echo "node|missing||" >> "${PROVENANCE_TSV}"
        MISSING_TOOLS="${MISSING_TOOLS}${MISSING_TOOLS:+,}node"
        return 1
    fi

    version_info=$(node --version 2>&1 || echo "unknown")

    echo "node|ok|${path}|${version_info}" >> "${PROVENANCE_TSV}"
    echo "  node: ok - ${path}"
    echo "    version: ${version_info}"
    return 0
}

collect_npm() {
    local tool="$1"
    local path version_info

    if ! path=$(command -v npm 2>/dev/null); then
        echo "npm|missing||" >> "${PROVENANCE_TSV}"
        MISSING_TOOLS="${MISSING_TOOLS}${MISSING_TOOLS:+,}npm"
        return 1
    fi

    version_info=$(npm --version 2>&1 || echo "unknown")

    echo "npm|ok|${path}|${version_info}" >> "${PROVENANCE_TSV}"
    echo "  npm: ok - ${path}"
    echo "    version: ${version_info}"
    return 0
}

collect_helm() {
    local tool="$1"
    local path version_info

    if ! path=$(command -v helm 2>/dev/null); then
        echo "helm|missing||" >> "${PROVENANCE_TSV}"
        MISSING_TOOLS="${MISSING_TOOLS}${MISSING_TOOLS:+,}helm"
        return 1
    fi

    version_info=$(helm version --short 2>&1 || echo "unknown")

    echo "helm|ok|${path}|${version_info}" >> "${PROVENANCE_TSV}"
    echo "  helm: ok - ${path}"
    echo "    version: ${version_info}"
    return 0
}

collect_kubectl() {
    local tool="$1"
    local path version_info

    if ! path=$(command -v kubectl 2>/dev/null); then
        echo "kubectl|missing||" >> "${PROVENANCE_TSV}"
        MISSING_TOOLS="${MISSING_TOOLS}${MISSING_TOOLS:+,}kubectl"
        return 1
    fi

    version_info=$(kubectl version --client 2>&1 | head -1 || echo "unknown")

    echo "kubectl|ok|${path}|${version_info}" >> "${PROVENANCE_TSV}"
    echo "  kubectl: ok - ${path}"
    echo "    version: ${version_info}"
    return 0
}

collect_docker() {
    local tool="$1"
    local path version_info

    if ! path=$(command -v docker 2>/dev/null); then
        echo "docker|missing||" >> "${PROVENANCE_TSV}"
        MISSING_TOOLS="${MISSING_TOOLS}${MISSING_TOOLS:+,}docker"
        return 1
    fi

    # Get Docker version safely
    version_info=$(docker version --format '{{.Client.Version}}' 2>&1 || docker version 2>&1 | head -5 || echo "unknown")

    echo "docker|ok|${path}|Docker ${version_info}" >> "${PROVENANCE_TSV}"
    echo "  docker: ok - ${path}"
    echo "    version: Docker ${version_info}"
    return 0
}

collect_buildx() {
    local tool="$1"
    local path version_info builder_info=""

    # Buildx is a Docker plugin, check via docker buildx version
    if ! docker buildx version >/dev/null 2>&1; then
        echo "buildx|missing||" >> "${PROVENANCE_TSV}"
        MISSING_TOOLS="${MISSING_TOOLS}${MISSING_TOOLS:+,}buildx"
        return 1
    fi

    version_info=$(docker buildx version 2>&1 || echo "unknown")

    # Get current builder info if available
    local builder_name="${K9B_BUILDX_BUILDER:-}"
    if [[ -z "${builder_name}" ]]; then
        builder_name=$(docker buildx inspect --bootstrap 2>&1 | head -1 | awk '{print $2}' || echo "default")
    fi

    # Get builder platforms
    local platforms=""
    if [[ -n "${builder_name}" ]]; then
        platforms=$(docker buildx inspect "${builder_name}" 2>&1 | grep -E "Platforms:" | sed 's/.*Platforms: //' || echo "")
    fi

    if [[ -n "${platforms}" ]]; then
        builder_info="${builder_name} / ${platforms}"
    else
        builder_info="${builder_name}"
    fi

    echo "buildx|ok|docker buildx|${builder_info} | ${version_info}" >> "${PROVENANCE_TSV}"
    echo "  buildx: ok - docker buildx"
    echo "    builder: ${builder_info}"
    echo "    version: ${version_info}"
    return 0
}

# =============================================================================
# Main
# =============================================================================

# Parse required tools from argument or environment
REQUIRED_TOOLS="${1:-${K9B_PROVENANCE_REQUIRE:-}}"

if [[ -z "${REQUIRED_TOOLS}" ]]; then
    echo "ERROR: No tools specified. Pass as argument or set K9B_PROVENANCE_REQUIRE env var."
    echo "Usage: scripts/ci/emit_toolchain_provenance.sh \"python,node,npm,go\""
    exit 1
fi

# Validate tools list
VALID_TOOLS="python,node,npm,go,helm,kubectl,kube_cli,docker,buildx"
IFS=',' read -ra TOOLS_ARRAY <<< "${REQUIRED_TOOLS}"
for tool in "${TOOLS_ARRAY[@]}"; do
    if [[ ! ",${VALID_TOOLS}," == *",${tool},"* ]]; then
        echo "ERROR: Unknown tool '${tool}'. Valid tools: ${VALID_TOOLS}"
        exit 1
    fi
done

echo "=== k9b hermetic toolchain provenance ==="
echo "Required tools: ${REQUIRED_TOOLS}"
echo ""

# Initialize provenance temp file
PROVENANCE_TSV="$(mktemp)"
trap 'rm -f "${PROVENANCE_TSV}"' EXIT

# Track failures
FAILED_REQUIRED=0
MISSING_TOOLS=""


# Collect each tool
for tool in "${TOOLS_ARRAY[@]}"; do
    case "${tool}" in
        python)  collect_python "${tool}" || { if [[ $? -eq 1 ]]; then FAILED_REQUIRED=1; fi; } ;;
        go)      collect_go "${tool}" || { if [[ $? -eq 1 ]]; then FAILED_REQUIRED=1; fi; } ;;
        node)    collect_node "${tool}" || { if [[ $? -eq 1 ]]; then FAILED_REQUIRED=1; fi; } ;;
        npm)     collect_npm "${tool}" || { if [[ $? -eq 1 ]]; then FAILED_REQUIRED=1; fi; } ;;
        helm)    collect_helm "${tool}" || { if [[ $? -eq 1 ]]; then FAILED_REQUIRED=1; fi; } ;;
        kubectl|kube_cli) collect_kubectl "${tool}" || { if [[ $? -eq 1 ]]; then FAILED_REQUIRED=1; fi; } ;;
        docker)  collect_docker "${tool}" || { if [[ $? -eq 1 ]]; then FAILED_REQUIRED=1; fi; } ;;
        buildx)  collect_buildx "${tool}" || { if [[ $? -eq 1 ]]; then FAILED_REQUIRED=1; fi; } ;;
    esac
done

echo ""

# =============================================================================
# Generate Markdown summary
# =============================================================================

MARKDOWN_SUMMARY="## k9b hermetic toolchain provenance

| Tool | Status | Path | Version |
|---|---:|---|---|
"

# Read collected data and generate markdown
while IFS='|' read -r t status path version; do
    if [[ -n "${t}" && "${t}" != "Tool" ]]; then
        case "${status}" in
            ok)     status_icon="ok" ;;
            missing) status_icon="missing" ;;
            *)      status_icon="${status}" ;;
        esac
        # Escape pipe characters in version for Markdown table
        escaped_version="${version//|/\\|}"
        # Truncate path if too long for table
        display_path="${path}"
        if [[ ${#display_path} -gt 50 ]]; then
            display_path="...${path: -47}"
        fi
        MARKDOWN_SUMMARY+="| ${t} | ${status_icon} | \`${display_path}\` | ${escaped_version} |
"
    fi
done < "${PROVENANCE_TSV}"

# Add footer
MARKDOWN_SUMMARY+="
_Captured at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")_"

# =============================================================================
# Output to GitHub Step Summary
# =============================================================================

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    echo -e "${MARKDOWN_SUMMARY}" >> "${GITHUB_STEP_SUMMARY}"
    echo "Provenance summary written to GITHUB_STEP_SUMMARY"
fi

# =============================================================================
# Output to GitHub Output (key-value pairs)
# =============================================================================

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    # Write status for each tool
    while IFS='|' read -r t status path version; do
        if [[ -n "${t}" && "${t}" != "Tool" ]]; then
            echo "${t}_status=${status}" >> "${GITHUB_OUTPUT}"
            echo "${t}_path=${path}" >> "${GITHUB_OUTPUT}"
            echo "${t}_version=${version}" >> "${GITHUB_OUTPUT}"
        fi
    done < "${PROVENANCE_TSV}"

    echo "Provenance outputs written to GITHUB_OUTPUT"
fi

# =============================================================================
# Print Markdown summary to stdout
# =============================================================================

echo ""
echo -e "${MARKDOWN_SUMMARY}"
echo ""

# =============================================================================
# Fail if required tools missing
# =============================================================================

if [[ "${FAILED_REQUIRED}" -eq 1 ]]; then
    echo "ERROR: One or more required tools are missing or failed smoke check"
    echo "Missing: ${MISSING_TOOLS:-see table above}"
    exit 1
fi

echo "Provenance capture complete"
