# OpenAPI Contract Policy

**Status**: Current  
**Owner**: Platform Team  
**Last Updated**: 2026-07-01

## Overview

k9b maintains a machine-readable API contract for its backend HTTP endpoints. This document describes how the contract is defined, exported, verified, and updated.

## Canonical Registry

`API_ROUTES` in `src/k8s_diag_agent/ui/api_routes_registry.py` is the single source of truth for:

- HTTP method/path matching
- Handler dispatch
- OpenAPI schema generation
- Route completeness tests

## Schema Export

The OpenAPI schema is exported from the registry:

```bash
.venv/bin/python scripts/export_openapi_schema.py --output build/openapi/k9b-openapi.json
```

## Frontend API Client Generation

A TypeScript Fetch client is generated from the exported schema:

```bash
bash scripts/generate_frontend_api_client.sh
```

This script:
1. Exports the backend OpenAPI schema to `build/openapi/k9b-openapi.json`
2. Generates a TypeScript Fetch client using OpenAPI Generator
3. Writes generated output to `frontend/src/generated/k9b-api/`

## Breaking-Change Gate

The breaking-change gate compares the current OpenAPI schema against a committed baseline and fails CI on accidental breaking changes.

### Files

| Purpose | Path |
|---------|------|
| OpenAPI baseline (committed) | `docs/api/openapi/k9b-openapi-baseline.json` |
| Current schema (generated) | `build/openapi/k9b-openapi.json` |
| Operation ID baseline (committed) | `docs/api/openapi/operation-ids-baseline.txt` |
| Current operation IDs (generated) | `build/openapi/operation-ids-current.txt` |
| Breaking changes report | `build/openapi/openapi-breaking-report.txt` |
| Changelog report | `build/openapi/openapi-changelog-report.txt` |

### What is Checked

The gate detects:
- Removed endpoints (paths)
- Changed HTTP methods
- Removed response fields
- Changed response types
- Removed parameters
- Renamed operation IDs
- Changed request requirements

### What is NOT Breaking

- Adding new endpoints
- Adding new optional parameters
- Adding new response fields (non-required)

## Operation ID Policy

Operation IDs (`operationId` in OpenAPI) uniquely identify operations. Changes to operation IDs are treated as breaking because:

- Generated frontend clients depend on operation IDs for method names
- Operation ID churn requires frontend updates

## Tooling

The breaking-change gate uses `oasdiff` (v1.21.0) via `go run`:

```bash
go run github.com/oasdiff/oasdiff@v1.21.0 breaking --fail-on ERR <baseline> <current>
```

Go must be installed. See: https://go.dev/doc/install

## Verification Command

```bash
.venv/bin/python scripts/verify_openapi_breaking_changes.py
```

Exit codes:
- `0` - No breaking changes
- `1` - Breaking changes detected or baseline missing
- `2` - oasdiff unavailable
- `3` - Schema export failed

## Intentionally Accepting Breaking Changes

To intentionally accept a breaking API change:

1. Make the API change in the backend
2. Update frontend/client/callers as needed
3. Run the generated client freshness gate
4. Run the breaking-change verifier and inspect the report
5. Run `--update-baseline` to accept the new contract:

   ```bash
   .venv/bin/python scripts/verify_openapi_breaking_changes.py --update-baseline
   ```

6. Include a summary of the breaking changes in commit/PR notes

Do NOT run `--update-baseline` in CI without human review. A baseline update is a compatibility decision that requires explicit approval.

## Verification Profiles

The breaking-change gate is wired into `scripts/verify_profile_model.py` as `openapi-breaking-change`. It runs after:

1. `openapi-contract` - Validates registry/schema metadata
2. `frontend-api-client` - Ensures generated client is fresh
3. `openapi-breaking-change` - Compares current schema to baseline

## Test Coverage

Tests for the breaking-change gate are in:
- `tests/test_openapi_breaking_change_gate.py`

## Related Documentation

- [API Routes Registry](../../src/k8s_diag_agent/ui/api_routes_registry.py)
- [OpenAPI Schema Builder](../../src/k8s_diag_agent/ui/api_contract.py)
- [Breaking-Change Verifier Script](../../scripts/verify_openapi_breaking_changes.py)
- [Frontend Client Generator Script](../../scripts/generate_frontend_api_client.sh)
