#!/usr/bin/env bash
# ============================================================================
# debug_recent_runs_execution_state.sh
#
# Host-runnable diagnostic script for Recent Runs vs Work List execution
# state discrepancies in k9b preprod.
#
# Collects diagnostic evidence from debug endpoints to help identify why
# Recent Runs execution summary lags behind Work list.
#
# Usage:
#   scripts/debug_recent_runs_execution_state.sh --base-url https://preprod... --run-id health-run-...
#
# Options:
#   --base-url URL          Backend base URL (required)
#   --run-id RUN_ID         Target run ID (required)
#   --worklist-url URL      Work list / selected run endpoint (optional, auto-detected from --base-url)
#   --output-dir DIR        Output directory (default: runs/debug/recent-runs-execution/<timestamp>-<run_id>)
#   --insecure              Pass -k to curl (skip TLS verification)
#   --token TOKEN           Bearer token for auth (or via --bearer-token)
#   --bearer-token TOKEN    Alias for --token
#   --header 'Name: value'  Additional header (repeatable)
#   --timeout SECONDS       curl timeout (default: 30)
#   --verbose               Enable verbose curl output
#   --help                  Show this help message
#
# Output files:
#   recent-runs-debug.json           Full /api/runs payload with debug params
#   recent-runs-row.json             Row for target run from Recent Runs list
#   runs-debug-block.json            _debug_execution_summary block from Recent Runs
#   execution-summary-diagnostics.json  Dedicated debug endpoint payload
#   worklist-run-payload.json        Selected run / Work list payload (if available)
#   summary.md                      Concise markdown summary with root-cause hints
#
# Requirements:
#   - curl
#   - jq
#
# Exit codes:
#   0   Success (diagnostics collected)
#   1   Missing required tools (curl/jq)
#   2   Missing required arguments
#   3   Invalid run_id
#   4   API errors (all endpoints failed)
#   5   Partial failure (some endpoints failed, check summary.md)
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Global state (not exported, used directly by functions)
# ---------------------------------------------------------------------------

# Array of custom headers (repeatable --header option)
HEADERS=()

# Auth token (not echoed to summary)
TOKEN=""

# curl timeout in seconds
TIMEOUT="30"

# Verbose mode
VERBOSE="false"

# Skip TLS verification
INSECURE="false"

# Script directory for sourcing helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

usage() {
    sed -n 's/^# //p' "$0" | head -60
    echo ""
    echo "Examples:"
    echo "  # Basic usage with preprod base URL"
    echo "  $0 --base-url https://preprod.example.com --run-id health-run-20260515T073859Z"
    echo ""
    echo "  # With bearer token"
    echo "  $0 --base-url https://preprod.example.com --run-id health-run-... --token \"\$K9B_TOKEN\""
    echo ""
    echo "  # Skip TLS verification (dev/preprod with self-signed certs)"
    echo "  $0 --base-url https://preprod.example.com --run-id health-run-... --insecure"
    echo ""
    echo "  # Custom output directory"
    echo "  $0 --base-url https://preprod.example.com --run-id health-run-... --output-dir /tmp/k9b-debug"
    echo ""
    echo "  # With additional auth headers"
    echo "  $0 --base-url https://preprod.example.com --run-id health-run-... \\"
    echo "       --header 'X-Custom-Auth: some-value' \\"
    echo "       --header 'Authorization: Bearer \$TOKEN'"
}

log() {
    echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] $*" >&2
}

log_verbose() {
    if [[ "${VERBOSE}" == "true" ]]; then
        echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] VERBOSE: $*" >&2
    fi
}

fail() {
    log "ERROR: $*"
    exit 1
}

# Check required tools
check_dependencies() {
    local missing=()

    if ! command -v curl &>/dev/null; then
        missing+=("curl")
    fi

    if ! command -v jq &>/dev/null; then
        missing+=("jq")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        log "Missing required tools: ${missing[*]}"
        log "Install with: brew install ${missing[*]}  # macOS"
        log "           apt install ${missing[*]}    # Debian/Ubuntu"
        exit 1
    fi
}

# Validate run_id to prevent path traversal
validate_run_id() {
    local run_id="$1"

    if [[ -z "$run_id" ]]; then
        echo "ERROR: run_id cannot be empty" >&2
        return 1
    fi

    # Reject path traversal patterns
    if [[ "$run_id" == *".."* ]] || [[ "$run_id" == *"/"* ]] || [[ "$run_id" == *"\\"* ]]; then
        echo "ERROR: run_id contains path traversal pattern: $run_id" >&2
        return 1
    fi

    # Reject null bytes using printf for reliable comparison
    local null_check
    null_check=$(printf '%s' "$run_id" | tr -d '\0')
    if [[ "${#run_id}" -ne "${#null_check}" ]]; then
        echo "ERROR: run_id contains null byte" >&2
        return 1
    fi

    # Allow k9b's health-run IDs and standard run ID patterns
    # Pattern: alphanumeric, hyphens, underscores, timestamps
    if ! [[ "$run_id" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        echo "ERROR: run_id contains invalid characters: $run_id" >&2
        echo "       Allowed: alphanumeric, hyphen, underscore" >&2
        return 1
    fi

    return 0
}

# Build curl arguments array
build_curl_args() {
    local -n args_ref=$1
    args_ref=()

    if [[ "${INSECURE}" == "true" ]]; then
        args_ref+=("-k")
    fi

    if [[ -n "${TIMEOUT}" ]]; then
        args_ref+=("--max-time" "${TIMEOUT}")
    fi

    if [[ "${VERBOSE}" == "true" ]]; then
        args_ref+=("-v")
    else
        args_ref+=("-sS")
    fi

    # Add custom headers from global array
    for header in "${HEADERS[@]:-}"; do
        args_ref+=("-H" "$header")
    done

    # Add auth header if token provided (but don't echo it to logs)
    if [[ -n "${TOKEN}" ]]; then
        args_ref+=("-H" "Authorization: Bearer ${TOKEN}")
    fi
}

# Fetch JSON and save to file
fetch_and_save() {
    local url="$1"
    local output_file="$2"
    local description="$3"

    log "Fetching: $description"
    log_verbose "  URL: $url"
    log_verbose "  Output: $output_file"

    # Build curl args
    local -a curl_args=()
    build_curl_args curl_args

    # Execute curl with HTTP status capture
    local http_code
    local response_body
    local curl_output

    curl_output=$(curl "${curl_args[@]}" "-o" "$output_file" "-w" "%{http_code}" "$url" 2>&1) || {
        local exit_code=$?
        echo "$curl_output" >> "$output_file" 2>&1 || true
        log "  FAILED: curl exited with code $exit_code"
        return 1
    }

    # Extract HTTP status (last line)
    http_code=$(echo "$curl_output" | tail -1)
    log_verbose "  HTTP Status: $http_code"

    if [[ "$http_code" =~ ^[45][0-9][0-9]$ ]]; then
        log "  HTTP Error: $http_code"
        return 1
    fi

    # Verify output is valid JSON (if not empty)
    if [[ -s "$output_file" ]]; then
        if ! jq empty "$output_file" 2>/dev/null; then
            log "  WARNING: Output is not valid JSON, saving raw response"
        fi
    fi

    log "  OK: saved to $output_file"
    return 0
}

# Extract field safely with jq
jq_extract() {
    local input_file="$1"
    local jq_filter="$2"
    local default_value="${3:-null}"

    if [[ ! -s "$input_file" ]]; then
        echo "$default_value"
        return 1
    fi

    local result
    result=$(jq -r "$jq_filter" "$input_file" 2>/dev/null) || {
        echo "$default_value"
        return 1
    }

    echo "$result"
    return 0
}

# Check if file contains a value (not null/empty)
has_value() {
    local value="$1"
    [[ -n "$value" && "$value" != "null" && "$value" != "empty" ]]
}

# Generate summary.md
generate_summary() {
    local run_id="$1"
    local base_url="$2"
    local timestamp="$3"
    local output_dir="$4"

    local summary_file="$output_dir/summary.md"

    # Load data from files
    local recent_runs_debug="$output_dir/recent-runs-debug.json"
    local execution_summary="$output_dir/execution-summary-diagnostics.json"

    # Extract Recent Runs row
    local run_row
    run_row=$(jq -r '.runs[] | select(.runId == $run_id)' "$recent_runs_debug" --arg run_id "$run_id" 2>/dev/null || echo "{}")

    # Extract debug block
    local debug_block
    debug_block=$(jq -r '._debug_execution_summary // null' "$recent_runs_debug" 2>/dev/null || echo "null")

    # Extract diagnostic fields
    local diag_selected_source
    diag_selected_source=$(jq -r '.selected_source // null' "$execution_summary" 2>/dev/null || echo "null")

    local diag_plan_data
    diag_plan_data=$(jq -r '.plan_data_in_index // null' "$execution_summary" 2>/dev/null || echo "null")

    local diag_execution_indices
    diag_execution_indices=$(jq -r '.execution_indices_in_index // false' "$execution_summary" 2>/dev/null || echo "false")

    local diag_parsed_count
    diag_parsed_count=$(jq -r '.parsed_execution_indices_count // 0' "$execution_summary" 2>/dev/null || echo "0")

    local diag_plan_count
    diag_plan_count=$(jq -r '.plan_candidate_count // 0' "$execution_summary" 2>/dev/null || echo "0")

    local diag_computed_summary
    diag_computed_summary=$(jq -r '.computed_execution_summary // null' "$execution_summary" 2>/dev/null || echo "null")

    local diag_stale_index
    diag_stale_index=$(jq -r '.stale_index_detected // false' "$execution_summary" 2>/dev/null || echo "false")

    local diag_ui_index_gen
    diag_ui_index_gen=$(jq -r '.ui_index_generated_at // null' "$execution_summary" 2>/dev/null || echo "null")

    local diag_ui_index_mtime
    diag_ui_index_mtime=$(jq -r '.ui_index_mtime // null' "$execution_summary" 2>/dev/null || echo "null")

    local diag_newest_exec_mtime
    diag_newest_exec_mtime=$(jq -r '.newest_execution_artifact_mtime // null' "$execution_summary" 2>/dev/null || echo "null")

    local diag_missing_reason
    diag_missing_reason=$(jq -r '.reason_execution_summary_missing // null' "$execution_summary" 2>/dev/null || echo "null")

    # Recent Runs row fields
    local rr_run_id
    rr_run_id=$(echo "$run_row" | jq -r '.runId // null' 2>/dev/null || echo "null")

    local rr_review_status
    rr_review_status=$(echo "$run_row" | jq -r '.reviewStatus // null' 2>/dev/null || echo "null")

    local rr_batch_eligible
    rr_batch_eligible=$(echo "$run_row" | jq -r '.batchEligibility // null' 2>/dev/null || echo "null")

    local rr_batch_executable
    rr_batch_executable=$(echo "$run_row" | jq -r '.batchExecutable // null' 2>/dev/null || echo "null")

    local rr_batch_eligible_count
    rr_batch_eligible_count=$(echo "$run_row" | jq -r '.batchEligibleCount // null' 2>/dev/null || echo "null")

    local rr_execution_summary
    rr_execution_summary=$(echo "$run_row" | jq -r '.executionSummary // null' 2>/dev/null || echo "null")

    # Work list availability
    local worklist_file="$output_dir/worklist-run-payload.json"
    local worklist_available_text="(not available)"
    if [[ -f "$worklist_file" ]] && jq empty "$worklist_file" 2>/dev/null; then
        worklist_available_text="(available)"
    fi

    # Write summary
    cat > "$summary_file" << EOF
# Recent Runs Execution State Diagnostic Summary

**Generated:** $(date -Iseconds)
**Run ID:** $run_id
**Base URL:** $base_url

---

## Recent Runs Row

| Field | Value |
|-------|-------|
| runId | \`$rr_run_id\` |
| reviewStatus | \`$rr_review_status\` |
| batchEligibility | \`$rr_batch_eligible\` |
| batchExecutable | \`$rr_batch_executable\` |
| batchEligibleCount | \`$rr_batch_eligible_count\` |
| executionSummary | \`$rr_execution_summary\` |

## Diagnostic Fields (from /api/debug/runs/{run_id}/execution-summary)

| Field | Value |
|-------|-------|
| selected_source | \`$diag_selected_source\` |
| plan_data_in_index | \`$diag_plan_data\` |
| execution_indices_in_index | \`$diag_execution_indices\` |
| parsed_execution_indices_count | \`$diag_parsed_count\` |
| plan_candidate_count | \`$diag_plan_count\` |
| computed_execution_summary | \`$diag_computed_summary\` |
| stale_index_detected | \`$diag_stale_index\` |
| ui_index_generated_at | \`$diag_ui_index_gen\` |
| ui_index_mtime | \`$diag_ui_index_mtime\` |
| newest_execution_artifact_mtime | \`$diag_newest_exec_mtime\` |
| reason_execution_summary_missing | \`$diag_missing_reason\` |

---

## Root-Cause Hints

Check the conditions below that apply to your situation:

EOF

    # Add root-cause hints based on diagnostic fields
    {
        echo "### Likely Causes (check if TRUE)"
        echo ""

        if [[ "$diag_selected_source" == "null" ]] || [[ -z "$diag_selected_source" ]]; then
            echo "- **debug endpoint disabled**: The /api/debug/runs/{run_id}/execution-summary"
            echo "  endpoint returned no data. Verify that K9B_ENABLE_DEBUG_ENDPOINTS=true in preprod."
        fi

        if [[ "$diag_stale_index" == "true" ]]; then
            echo "- **stale index suspected**: The UI index appears to be stale relative to"
            echo "  execution artifacts. Check ui_index_generated_at vs newest_execution_artifact_mtime."
            echo "  Consider running: scripts/update_ui_index.py --runs-dir runs/health"
        fi

        if [[ "$diag_plan_data" == "null" ]] || [[ "$diag_plan_data" == "false" ]]; then
            echo "- **plan data missing**: The next-check plan is not in the UI index."
            echo "  Without plan data, execution summary cannot be computed."
        fi

        if [[ "$diag_execution_indices" == "false" ]] || [[ "$diag_execution_indices" == "null" ]]; then
            echo "- **execution indices missing**: Execution artifacts are not indexed."
            echo "  The UI index may be stale or not properly updated after execution."
        fi

        if [[ "$rr_run_id" == "null" ]] || [[ -z "$rr_run_id" ]]; then
            echo "- **Recent Runs row missing**: The run ID $run_id was not found in Recent Runs."
            echo "  The run may have been cleaned up or the list is stale."
        fi

        if [[ "$diag_computed_summary" != "null" ]] && [[ -n "$diag_computed_summary" ]]; then
            if [[ "$rr_execution_summary" == "null" ]] || [[ -z "$rr_execution_summary" ]]; then
                echo "- **backend summary correct but frontend may be stale**: The debug endpoint"
                echo "  computed a valid execution_summary but Recent Runs row shows null."
                echo "  This suggests a caching or synchronization issue."
            fi
        fi

        echo ""
        echo "### Files Collected"
        echo ""
        echo "| File | Description |"
        echo "|------|-------------|"
        echo "| recent-runs-debug.json | Full /api/runs payload with debug params |"
        echo "| recent-runs-row.json | Row for target run from Recent Runs list |"
        echo "| runs-debug-block.json | _debug_execution_summary block from Recent Runs |"
        echo "| execution-summary-diagnostics.json | Dedicated debug endpoint payload |"
        echo "| worklist-run-payload.json | Selected run / Work list payload ${worklist_available_text} |"
        echo ""

        echo "### Next Steps"
        echo ""
        echo "1. Review the root-cause hints above that apply to your situation"
        echo "2. Check the raw JSON files for detailed field values"
        echo "3. If debug endpoint is disabled, enable it with: K9B_ENABLE_DEBUG_ENDPOINTS=true"
        echo "4. If stale index, consider rebuilding the UI index:"
        echo "   \`\`\`bash"
        echo "   .venv/bin/python scripts/update_ui_index.py --runs-dir runs/health"
        echo "   \`\`\`"
        echo "5. Attach this summary and relevant JSON files to any issue or ACT response"

    } >> "$summary_file"

    log "Summary written to: $summary_file"
}

# ---------------------------------------------------------------------------
# Main script
# ---------------------------------------------------------------------------

main() {
    # Parse arguments
    local base_url=""
    local run_id=""
    local worklist_url=""
    local output_dir=""
    local token_arg=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                usage
                exit 0
                ;;
            --base-url)
                base_url="$2"
                shift 2
                ;;
            --run-id)
                run_id="$2"
                shift 2
                ;;
            --worklist-url)
                worklist_url="$2"
                shift 2
                ;;
            --output-dir)
                output_dir="$2"
                shift 2
                ;;
            --insecure|-k)
                INSECURE="true"
                shift
                ;;
            --token|--bearer-token)
                token_arg="$2"
                shift 2
                ;;
            --header|-H)
                HEADERS+=("$2")
                shift 2
                ;;
            --timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            --verbose|-v)
                VERBOSE="true"
                shift
                ;;
            *)
                echo "Unknown option: $1" >&2
                echo "Use --help for usage information" >&2
                exit 2
                ;;
        esac
    done

    # Store token separately (not exported, not logged)
    TOKEN="$token_arg"

    # Check dependencies
    check_dependencies

    # Validate required arguments
    if [[ -z "$base_url" ]]; then
        log "ERROR: --base-url is required"
        echo "Use --help for usage information" >&2
        exit 2
    fi

    if [[ -z "$run_id" ]]; then
        log "ERROR: --run-id is required"
        echo "Use --help for usage information" >&2
        exit 2
    fi

    # Validate run_id
    if ! validate_run_id "$run_id"; then
        exit 3
    fi

    # Set default worklist URL if not provided
    # Use run_id directly since validation allows only safe chars (alphanumeric, hyphen, underscore)
    if [[ -z "$worklist_url" ]]; then
        worklist_url="${base_url%/}/api/run?run_id=${run_id}"
    fi

    # Create output directory with timestamp
    if [[ -z "$output_dir" ]]; then
        local timestamp
        timestamp=$(date '+%Y%m%dT%H%M%S')
        output_dir="runs/debug/recent-runs-execution/${timestamp}-${run_id}"
    fi

    mkdir -p "$output_dir"
    log "Output directory: $output_dir"

    local timestamp=$(date -Iseconds)
    local failed_count=0
    local partial_failure="false"

    # -------------------------------------------------------------------------
    # Collect: Recent Runs full payload with debug params
    # -------------------------------------------------------------------------
    local recent_runs_url="${base_url%/}/api/runs?include_batch_eligibility=true&debug_execution_summary=true"
    local recent_runs_debug_file="$output_dir/recent-runs-debug.json"

    if ! fetch_and_save "$recent_runs_url" "$recent_runs_debug_file" "Recent Runs debug payload"; then
        failed_count=$((failed_count + 1))
        partial_failure="true"
    fi

    # -------------------------------------------------------------------------
    # Extract and save: Recent Runs row for target run
    # -------------------------------------------------------------------------
    local recent_runs_row_file="$output_dir/recent-runs-row.json"

    if [[ -f "$recent_runs_debug_file" ]] && jq empty "$recent_runs_debug_file" 2>/dev/null; then
        log "Extracting row for run_id: $run_id"
        if ! jq -r --arg run_id "$run_id" '.runs[] | select(.runId == $run_id)' "$recent_runs_debug_file" > "$recent_runs_row_file" 2>/dev/null; then
            echo "{}" > "$recent_runs_row_file"
            log "  WARNING: Run ID not found in Recent Runs list"
        else
            log "  OK: row saved to $recent_runs_row_file"
        fi
    else
        echo "{}" > "$recent_runs_row_file"
    fi

    # -------------------------------------------------------------------------
    # Extract and save: _debug_execution_summary block
    # -------------------------------------------------------------------------
    local runs_debug_block_file="$output_dir/runs-debug-block.json"

    if [[ -f "$recent_runs_debug_file" ]] && jq empty "$recent_runs_debug_file" 2>/dev/null; then
        log "Extracting _debug_execution_summary block"
        if ! jq -r '._debug_execution_summary // null' "$recent_runs_debug_file" > "$runs_debug_block_file" 2>/dev/null; then
            echo "null" > "$runs_debug_block_file"
        fi
    else
        echo "null" > "$runs_debug_block_file"
    fi

    # -------------------------------------------------------------------------
    # Collect: Dedicated diagnostics endpoint
    # -------------------------------------------------------------------------
    local diag_url="${base_url%/}/api/debug/runs/${run_id}/execution-summary"
    local diag_file="$output_dir/execution-summary-diagnostics.json"

    if ! fetch_and_save "$diag_url" "$diag_file" "Execution summary diagnostics"; then
        failed_count=$((failed_count + 1))
        partial_failure="true"
    fi

    # -------------------------------------------------------------------------
    # Collect: Work list / selected run payload
    # -------------------------------------------------------------------------
    local worklist_file="$output_dir/worklist-run-payload.json"
    local worklist_failed="false"

    log "Fetching: Work list / selected run payload"
    log_verbose "  URL: $worklist_url"
    log_verbose "  Output: $worklist_file"

    local -a curl_args=()
    build_curl_args curl_args

    local curl_output
    curl_output=$(curl "${curl_args[@]}" "-o" "$worklist_file" "-w" "%{http_code}" "$worklist_url" 2>&1) || {
        local exit_code=$?
        echo "$curl_output" >> "$worklist_file" 2>&1 || true
        log "  WARNING: Work list fetch failed (exit code $exit_code), continuing..."
        worklist_failed="true"
    }

    local http_code
    http_code=$(echo "$curl_output" | tail -1)
    log_verbose "  HTTP Status: $http_code"

    if [[ "$http_code" =~ ^[45][0-9][0-9]$ ]]; then
        log "  WARNING: Work list returned HTTP $http_code, continuing..."
        worklist_failed="true"
    elif [[ -s "$worklist_file" ]] && ! jq empty "$worklist_file" 2>/dev/null; then
        log "  WARNING: Work list output is not valid JSON"
        worklist_failed="true"
    else
        log "  OK: saved to $worklist_file"
    fi

    # -------------------------------------------------------------------------
    # Generate summary
    # -------------------------------------------------------------------------
    generate_summary "$run_id" "$base_url" "$timestamp" "$output_dir"

    # -------------------------------------------------------------------------
    # Report final status
    # -------------------------------------------------------------------------
    echo ""
    log "=============================================="

    if [[ $failed_count -eq 0 ]]; then
        log "Diagnostics collected successfully"
        log "Summary: $output_dir/summary.md"
        exit 0
    elif [[ $failed_count -lt 4 ]]; then
        log "Partial success: $failed_count endpoint(s) failed"
        log "Summary: $output_dir/summary.md"
        exit 5
    else
        log "All endpoints failed - check connectivity and K9B_ENABLE_DEBUG_ENDPOINTS=true"
        exit 4
    fi
}

# Run main with all arguments
main "$@"