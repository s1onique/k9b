#!/usr/bin/env bash
# Package k9b Helm chart for publishing.
#
# Usage:
#   scripts/package_helm_chart.sh [--version <version>]
#
# Creates a packaged chart in the dist/ directory.

set -uo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
CHART_DIR="$REPO_ROOT/charts/k9b"
DIST_DIR="$REPO_ROOT/dist"

# Parse arguments
VERSION=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--version <version>]"
            echo "  --version    Override chart version (defaults to Chart.yaml version)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Check prerequisites
if ! command -v helm >/dev/null 2>&1; then
    echo "ERROR: helm is not installed or not on PATH." >&2
    exit 1
fi

# Create dist directory
mkdir -p "$DIST_DIR"

# Package chart
if [[ -n "$VERSION" ]]; then
    echo "Packaging chart with version: $VERSION"
    helm package "$CHART_DIR" --destination "$DIST_DIR" --version "$VERSION"
else
    echo "Packaging chart with version from Chart.yaml"
    helm package "$CHART_DIR" --destination "$DIST_DIR"
fi

if [[ $? -eq 0 ]]; then
    echo ""
    echo "Packaged chart:"
    ls -la "$DIST_DIR"/*.tgz 2>/dev/null || echo "No chart package found"
    echo ""
    echo "To publish to OCI registry:"
    echo "  helm registry login <registry>"
    echo "  helm push $DIST_DIR/k9b-<version>.tgz oci://<registry>/<org>/k9b"
else
    echo "ERROR: Chart packaging failed" >&2
    exit 1
fi
