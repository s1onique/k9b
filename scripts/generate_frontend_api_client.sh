#!/bin/bash
# Generate TypeScript frontend API client from OpenAPI schema.
#
# This script:
# 1. Exports the backend OpenAPI schema to build/openapi/k9b-openapi.json
# 2. Generates a TypeScript Fetch client using OpenAPI Generator
# 3. Writes generated output to frontend/src/generated/k9b-api/
#
# The generated client provides typed API operations derived from the
# backend API_ROUTES registry.
#
# Usage:
#   bash scripts/generate_frontend_api_client.sh
#
# Requirements:
#   - Python 3.x with k9b backend installed
#   - Node.js with npx available
#   - Java (for OpenAPI Generator)
#
# Exit codes:
#   0 - Success
#   1 - Schema export failed
#   2 - OpenAPI Generator failed
#   3 - Cleanup failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCHEMA_PATH="build/openapi/k9b-openapi.json"
GENERATED_DIR="frontend/src/generated/k9b-api"

echo "=== Generating frontend API client ==="

# Step 1: Export OpenAPI schema
echo "[1/3] Exporting OpenAPI schema..."
cd "$REPO_ROOT"
.venv/bin/python scripts/export_openapi_schema.py --output "$SCHEMA_PATH"
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to export OpenAPI schema" >&2
    exit 1
fi
echo "Schema exported to $SCHEMA_PATH"

# Step 2: Generate TypeScript client
echo "[2/3] Generating TypeScript client..."

# Check if schema exists
if [ ! -f "$SCHEMA_PATH" ]; then
    echo "ERROR: Schema file not found: $SCHEMA_PATH" >&2
    exit 1
fi

# Ensure output directory exists
mkdir -p "$(dirname "$GENERATED_DIR")"

# Generate TypeScript Fetch client
# Using npx to run OpenAPI Generator CLI
npx --yes @openapitools/openapi-generator-cli generate \
    -g typescript-fetch \
    -i "$SCHEMA_PATH" \
    -o "$GENERATED_DIR" \
    --additional-properties=supportsES6=true,typescriptThreePlus=true \
    --skip-validate-spec \
    2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: OpenAPI Generator failed" >&2
    exit 2
fi

echo "Generated client written to $GENERATED_DIR"

# Step 3: Verify generated files
echo "[3/3] Verifying generated files..."
if [ ! -f "$GENERATED_DIR/index.ts" ]; then
    echo "ERROR: Generated index.ts not found" >&2
    exit 3
fi

echo "=== Frontend API client generation complete ==="
echo ""
echo "Generated files:"
ls -la "$GENERATED_DIR"/*.ts 2>/dev/null | head -20 || echo "  (no .ts files in root)"
echo ""
echo "NOTE: Do not edit files in $GENERATED_DIR manually."
echo "      They are generated from the backend API_ROUTES registry."
