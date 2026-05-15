# Recent Runs Execution State Debugging

## Overview

This document explains how to diagnose the "Recent Runs vs Work List execution-state discrepancy" issue in k9b preprod.

**Symptom:**
- Selected run in Work list shows all candidates as `executed / success` or `executed / failed`
- Recent Runs for the same run still shows `No Executions Yet` and `Execute`

## Debug Endpoints

Preprod exposes debug endpoints when `K9B_ENABLE_DEBUG_ENDPOINTS=true`:

1. **`/api/runs?include_batch_eligibility=true&debug_execution_summary=true`**
   - Returns the Recent Runs list with embedded `_debug_execution_summary` block
   
2. **`/api/debug/runs/{run_id}/execution-summary`**
   - Dedicated diagnostics endpoint for a specific run
   - Provides detailed execution state analysis

## Enabling Debug Endpoints

Set the environment variable before starting the backend:

```bash
K9B_ENABLE_DEBUG_ENDPOINTS=true .venv/bin/python -m k8s_diag_agent
```

Or in Docker Compose:

```yaml
environment:
  - K9B_ENABLE_DEBUG_ENDPOINTS=true
```

## Using the Diagnostic Script

The `scripts/debug_recent_runs_execution_state.sh` script automates evidence collection.

### Prerequisites

The script requires:
- `curl`
- `jq`

Install on macOS:
```bash
brew install curl jq
```

Install on Linux:
```bash
sudo apt install curl jq
```

### Basic Usage

```bash
# Run the diagnostic script
scripts/debug_recent_runs_execution_state.sh \
  --base-url https://preprod.example.com \
  --run-id health-run-20260515T073859Z
```

### With Authentication

```bash
# Using bearer token
K9B_TOKEN="your-token" scripts/debug_recent_runs_execution_state.sh \
  --base-url https://preprod.example.com \
  --run-id health-run-20260515T073859Z

# Or pass token directly (not recommended for production)
scripts/debug_recent_runs_execution_state.sh \
  --base-url https://preprod.example.com \
  --run-id health-run-20260515T073859Z \
  --token "your-token"
```

### With Self-Signed Certificates

```bash
scripts/debug_recent_runs_execution_state.sh \
  --base-url https://preprod.example.com \
  --run-id health-run-20260515T073859Z \
  --insecure
```

### Custom Output Directory

```bash
scripts/debug_recent_runs_execution_state.sh \
  --base-url https://preprod.example.com \
  --run-id health-run-20260515T073859Z \
  --output-dir /tmp/k9b-debug-$(date +%Y%m%d)
```

### Full Options

```
--base-url URL          Backend base URL (required)
--run-id RUN_ID         Target run ID (required)
--worklist-url URL      Work list endpoint (optional, auto-detected)
--output-dir DIR        Output directory (default: runs/debug/recent-runs-execution/<timestamp>-<run_id>)
--insecure              Skip TLS verification
--token TOKEN           Bearer token for auth
--bearer-token TOKEN    Alias for --token
--header 'Name: value'  Additional header (repeatable)
--timeout SECONDS       curl timeout (default: 30)
--verbose               Enable verbose output
--help                  Show help
```

## Output Files

The script produces these files in the output directory:

| File | Description |
|------|-------------|
| `recent-runs-debug.json` | Full /api/runs payload with debug params |
| `recent-runs-row.json` | Row for target run from Recent Runs list |
| `runs-debug-block.json` | `_debug_execution_summary` block from Recent Runs |
| `execution-summary-diagnostics.json` | Dedicated debug endpoint payload |
| `worklist-run-payload.json` | Selected run / Work list payload (if available) |
| `summary.md` | Markdown summary with root-cause hints |

## Interpreting Root-Cause Hints

The `summary.md` file includes a "Root-Cause Hints" section. Check which conditions apply:

### Debug Endpoint Disabled

**Indicator:** `selected_source` is `null` in diagnostics

**Check:** Verify `K9B_ENABLE_DEBUG_ENDPOINTS=true` is set in preprod environment.

### Stale Index Suspected

**Indicator:** `stale_index_detected: true`

**Check:** Compare `ui_index_generated_at` vs `newest_execution_artifact_mtime`

**Fix:** Rebuild the UI index:
```bash
.venv/bin/python scripts/update_ui_index.py --runs-dir runs/health
```

### Plan Data Missing

**Indicator:** `plan_data_in_index: false` or `null`

**Cause:** The next-check plan is not in the UI index. Without plan data, execution summary cannot be computed.

### Execution Indices Missing

**Indicator:** `execution_indices_in_index: false`

**Cause:** Execution artifacts are not indexed. The UI index may be stale or not properly updated after execution.

### Recent Runs Row Missing

**Indicator:** Run ID not found in `recent-runs-row.json`

**Cause:** The run may have been cleaned up or the runs list is stale.

### Backend Summary Correct but Frontend Stale

**Indicator:** `computed_execution_summary` is populated but `executionSummary` in Recent Runs row is `null`

**Cause:** A caching or synchronization issue. The backend has the correct data but the frontend hasn't received it.

## Diagnostic Fields Reference

| Field | Description |
|-------|-------------|
| `selected_source` | Where the execution summary was sourced from (`ui_index`, `runs_list`, etc.) |
| `plan_data_in_index` | Whether plan data exists in the UI index |
| `execution_indices_in_index` | Whether execution indices are indexed |
| `parsed_execution_indices_count` | Number of execution indices parsed |
| `plan_candidate_count` | Total number of next-check candidates |
| `computed_execution_summary` | The computed execution summary |
| `stale_index_detected` | Whether the UI index appears stale |
| `ui_index_generated_at` | When the UI index was generated |
| `ui_index_mtime` | File system modification time of UI index |
| `newest_execution_artifact_mtime` | Modification time of newest execution artifact |
| `reason_execution_summary_missing` | Explanation if summary couldn't be computed |

## Worklist Endpoint Discovery

The Work list / selected run endpoint is auto-detected based on the `--base-url`:

```
${base_url}/api/run?run_id=${run_id}
```

If your deployment uses a different endpoint, specify it explicitly:

```bash
scripts/debug_recent_runs_execution_state.sh \
  --base-url https://preprod.example.com \
  --run-id health-run-20260515T073859Z \
  --worklist-url "https://preprod.example.com/api/v2/run?run_id=health-run-20260515T073859Z"
```

## Attaching to Issues

When filing an issue or requesting help, attach:

1. `summary.md` - The diagnostic summary
2. `recent-runs-debug.json` - Full Recent Runs payload (sanitize any sensitive data)
3. `execution-summary-diagnostics.json` - Debug endpoint response
4. `worklist-run-payload.json` - Work list payload (if available)

**Do NOT attach:**
- Bearer tokens (they are never echoed to output files)
- Internal authentication headers (use `--header` to add custom headers separately)

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success - all diagnostics collected |
| 1 | Missing required tools (curl or jq) |
| 2 | Missing required arguments |
| 3 | Invalid run_id |
| 4 | All API endpoints failed |
| 5 | Partial failure - some endpoints failed |

## Troubleshooting

### Script fails with "curl not found"

Install curl:
```bash
# macOS
brew install curl
# Linux
sudo apt install curl
```

### Script fails with "jq not found"

Install jq:
```bash
# macOS
brew install jq
# Linux
sudo apt install jq
```

### All endpoints return 404

Verify that debug endpoints are enabled:
```bash
K9B_ENABLE_DEBUG_ENDPOINTS=true
```

Check that you're targeting the correct base URL (not a reverse proxy that strips the debug path).

### Run ID not found in Recent Runs

The run may have been cleaned up or archived. Try with a more recent run ID:
```bash
# List available runs
curl -s https://preprod.example.com/api/runs | jq '.runs[].runId'
```

## Related Documentation

- [Beta Operator Guide](./beta-operator-guide.md)
- [Data Model](./data-model.md)
- [Post-Beta Backlog](./post-beta-backlog.md)