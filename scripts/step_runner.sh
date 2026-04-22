#!/usr/bin/env bash
# Shared step runner for verification scripts.
# Provides compact output, per-step logging, and structured failure reporting.
#
# Usage: source step_runner.sh && step_run <step_id> <message> <command> [args...]
#
# Environment:
#   STEP_VERBOSE     - If set, stream full output to console
#   STEP_LOG_DIR     - Override log directory (default: runs/verification)
#   STEP_LOG_PREFIX  - Override log prefix (default: step)
#   STEP_NO_HEADER   - If set, skip header output
#
# Output format (compact):
#   [step-id] PASS (0.5s)        # success
#   [step-id] FAIL (0.5s)        # failure
#
# Failure output includes:
#   - Failed step name
#   - Exit code
#   - Bounded excerpt from log (last 30 lines)
#   - Full log path
#
# Stores metadata in STEP_DATA_DIR for future JSON summary mode.

# Note: Not using 'set -e' here because step_run needs to capture and report
# failures gracefully, not exit immediately. Individual steps are responsible
# for their own error handling.
set -uo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STEP_DATA_DIR="${STEP_DATA_DIR:-}"
STEP_LOG_DIR="${STEP_LOG_DIR:-}"
STEP_VERBOSE="${STEP_VERBOSE:-}"
STEP_NO_HEADER="${STEP_NO_HEADER:-}"
STEP_LOG_PREFIX="${STEP_LOG_PREFIX:-step}"

# Determine script directory using BASH_SOURCE[0] for reliable sourcing
# This works whether the script is sourced from verify_all.sh or bash -c
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    _STEP_RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    _STEP_RUNNER_DIR="$(cd "$(dirname "$0")" && pwd)"
fi

# Determine repo root relative to step_runner.sh location
_REPO_ROOT="$(cd "$_STEP_RUNNER_DIR/.." && pwd)"

# Use :- to safely handle unset/empty vars with set -u
STEP_LOG_DIR="${STEP_LOG_DIR:-$_REPO_ROOT/runs/verification}"
STEP_DATA_DIR="${STEP_DATA_DIR:-$_REPO_ROOT/runs/verification}"

# Create directories
mkdir -p "$STEP_LOG_DIR"
mkdir -p "$STEP_DATA_DIR"

# Timestamp for this run (captured once at initialization)
_RUN_TIMESTAMP="${STEP_RUN_TIMESTAMP:-$(date '+%Y%m%d-%H%M%S')}"
export STEP_RUN_TIMESTAMP

# Record the actual start time once
_step_record_start_time() {
    local start_time_file="${STEP_DATA_DIR}/${_RUN_TIMESTAMP}-start.txt"
    if [[ ! -f "$start_time_file" ]]; then
        date '+%Y-%m-%dT%H:%M:%S' > "$start_time_file"
    fi
}

# Call on initialization
_step_record_start_time

# Internal state
declare -A _STEP_RESULTS=()
declare -a _STEP_ORDER=()
_STEP_FAILED=false
_STEP_CURRENT=""
_STEP_LOG_FILE=""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_step_timestamp() {
    date '+%Y-%m-%dT%H:%M:%S'
}

_step_duration_ms() {
    local start="$1"
    local end="$2"
    echo $(( (end - start) * 1000 ))
}

_step_format_duration() {
    local ms="$1"
    if (( ms < 1000 )); then
        echo "${ms}ms"
    elif (( ms < 60000 )); then
        local secs=$(( ms / 1000 ))
        local fraction=$(( (ms % 1000) / 100 ))
        echo "${secs}.${fraction}s"
    else
        local mins=$(( ms / 60000 ))
        local secs=$(( (ms % 60000) / 1000 ))
        echo "${mins}m${secs}s"
    fi
}

# Check for verbose mode (can be passed via env or first arg --verbose)
_step_check_verbose() {
    [[ -n "$STEP_VERBOSE" ]] && return 0
    return 1
}

# ---------------------------------------------------------------------------
# Core step runner
# ---------------------------------------------------------------------------

# step_run <step_id> <message> <command> [args...]
# Executes a step with compact logging and output.
step_run() {
    local step_id="$1"
    local message="$2"
    shift 2

    _STEP_CURRENT="$step_id"
    _STEP_ORDER+=("$step_id")

    local log_file="${STEP_LOG_DIR}/${_RUN_TIMESTAMP}-${step_id}.log"
    _STEP_LOG_FILE="$log_file"

    # Clear log file
    > "$log_file"

    local start_time end_time duration_ms exit_code

    start_time=$(date +%s)

    if _step_check_verbose; then
        # Verbose: stream header and output to both console and log
        echo "[$step_id] $message" | tee "$log_file"
        "$@" 2>&1 | tee -a "$log_file"
        exit_code=${PIPESTATUS[0]}
    else
        # Compact: capture to log only, emit single result line
        "$@" >> "$log_file" 2>&1
        exit_code=$?
    fi

    end_time=$(date +%s)
    duration_ms=$(_step_duration_ms "$start_time" "$end_time")
    local duration_fmt=$(_step_format_duration "$duration_ms")

    if (( exit_code == 0 )); then
        # Compact: single line with id, status, duration, and message
        echo "[$step_id] PASS (${duration_fmt}) - $message"
        _STEP_RESULTS["$step_id"]="PASS|$duration_ms|$exit_code"
    else
        echo "[$step_id] FAIL (${duration_fmt}) - $message" >&2
        _STEP_RESULTS["$step_id"]="FAIL|$duration_ms|$exit_code"
        _STEP_FAILED=true
        _step_print_failure_info "$step_id" "$exit_code" "$log_file" "$duration_fmt"
        exit "$exit_code"
    fi
}

# step_run_continue <step_id> <message> <command> [args...]
# Like step_run but continues on failure (captures result, doesn't exit)
step_run_continue() {
    local step_id="$1"
    local message="$2"
    shift 2

    _STEP_CURRENT="$step_id"
    _STEP_ORDER+=("$step_id")

    local log_file="${STEP_LOG_DIR}/${_RUN_TIMESTAMP}-${step_id}.log"
    _STEP_LOG_FILE="$log_file"

    > "$log_file"

    local start_time end_time duration_ms exit_code

    start_time=$(date +%s)

    if _step_check_verbose; then
        # Verbose: stream header and output to both console and log
        echo "[$step_id] $message" | tee "$log_file"
        "$@" 2>&1 | tee -a "$log_file"
        exit_code=${PIPESTATUS[0]}
    else
        # Compact: capture to log only, emit single result line
        "$@" >> "$log_file" 2>&1
        exit_code=$?
    fi

    end_time=$(date +%s)
    duration_ms=$(_step_duration_ms "$start_time" "$end_time")
    local duration_fmt=$(_step_format_duration "$duration_ms")

    if (( exit_code == 0 )); then
        # Compact: single line with id, status, duration, and message
        echo "[$step_id] PASS (${duration_fmt}) - $message"
        _STEP_RESULTS["$step_id"]="PASS|$duration_ms|$exit_code"
    else
        echo "[$step_id] FAIL (${duration_fmt}) - $message" >&2
        _STEP_RESULTS["$step_id"]="FAIL|$duration_ms|$exit_code"
        _STEP_FAILED=true
        _step_print_failure_info "$step_id" "$exit_code" "$log_file" "$duration_fmt"
    fi
}

_step_print_failure_info() {
    local step_id="$1"
    local exit_code="$2"
    local log_file="$3"
    local duration_fmt="$4"

    echo "" >&2
    echo "FAILED STEP: $step_id" >&2
    echo "EXIT CODE: $exit_code" >&2
    echo "LOG FILE: $log_file" >&2
    echo "" >&2
    echo "--- Failure excerpt (last 30 lines) ---" >&2
    tail -30 "$log_file" >&2
    echo "----------------------------------------" >&2
    echo "" >&2
}

# step_emit_summary
# Writes step metadata to STEP_DATA_DIR
step_emit_summary() {
    local summary_file="${STEP_DATA_DIR}/${_RUN_TIMESTAMP}-summary.txt"
    local json_file="${STEP_DATA_DIR}/${_RUN_TIMESTAMP}-summary.json"
    local start_time_file="${STEP_DATA_DIR}/${_RUN_TIMESTAMP}-start.txt"
    
    # Get start time
    local start_ts
    if [[ -f "$start_time_file" ]]; then
        start_ts=$(cat "$start_time_file")
    else
        start_ts=$(date '+%Y-%m-%dT%H:%M:%S')
        echo "$start_ts" > "$start_time_file"
    fi
    
    local failed_count
    failed_count=$(($(_step_failed_count)))
    local overall_status="passed"
    local failed_steps="[]"
    
    if (( failed_count > 0 )); then
        overall_status="failed"
        # Build JSON array of failed step ids
        local failed_ids=""
        for step_id in "${_STEP_ORDER[@]}"; do
            local result="${_STEP_RESULTS[$step_id]}"
            if [[ "${result%%|*}" == "FAIL" ]]; then
                if [[ -n "$failed_ids" ]]; then
                    failed_ids="$failed_ids,"
                fi
                failed_ids="${failed_ids}\"$step_id\""
            fi
        done
        failed_steps="[$failed_ids]"
    fi
    
    # Write text summary
    {
        echo "Run: $_RUN_TIMESTAMP"
        echo "Started: $start_ts"
        echo "Steps: ${#_STEP_ORDER[@]}"
        echo "Failed: $failed_count"
        for step_id in "${_STEP_ORDER[@]}"; do
            local result="${_STEP_RESULTS[$step_id]}"
            echo "${step_id}|${result}"
        done
    } > "$summary_file"
    echo "Summary: $summary_file"
    
    # Write JSON summary
    {
        echo "{"
        echo "  \"run_id\": \"$_RUN_TIMESTAMP\","
        echo "  \"started\": \"$start_ts\","
        echo "  \"status\": \"$overall_status\","
        echo "  \"failed_count\": $failed_count,"
        echo "  \"failed_steps\": $failed_steps,"
        echo "  \"steps\": ["
        local first_step=true
        for step_id in "${_STEP_ORDER[@]}"; do
            local result="${_STEP_RESULTS[$step_id]}"
            local status="${result%%|*}"
            local duration_ms="${result#*|}"
            duration_ms="${duration_ms%|*}"
            local exit_code="${result##*|}"
            local log_file="${STEP_LOG_DIR}/${_RUN_TIMESTAMP}-${step_id}.log"
            
            if [[ "$first_step" == "true" ]]; then
                first_step=false
            else
                echo ","
            fi
            printf '    {"id": "%s", "status": "%s", "duration_ms": %s, "exit_code": %s, "log_file": "%s"}' \
                "$step_id" "$status" "$duration_ms" "$exit_code" "$log_file"
        done
        echo ""
        echo "  ]"
        echo "}"
    } > "$json_file"
    echo "JSON Summary: $json_file"
}

_step_failed_count() {
    local count=0
    for step_id in "${_STEP_ORDER[@]}"; do
        local result="${_STEP_RESULTS[$step_id]}"
        if [[ "${result%%|*}" == "FAIL" ]]; then
            (( count++ ))
        fi
    done
    echo "$count"
}

# step_finalize <exit_code>
# Called at end of verification to emit final status
step_finalize() {
    local exit_code="$1"

    if (( exit_code == 0 )); then
        echo "VERIFICATION GATE: PASSED"
    else
        echo "VERIFICATION GATE: FAILED" >&2
    fi

    step_emit_summary

    return "$exit_code"
}

# step_check_failed
# Returns 0 if any step failed, 1 otherwise
step_check_failed() {
    "$_STEP_FAILED"
}

# step_is_verbose
# Returns 0 if verbose mode is enabled
step_is_verbose() {
    _step_check_verbose
}

# step_enable_verbose
# Enable verbose output mode
step_enable_verbose() {
    STEP_VERBOSE=1
    export STEP_VERBOSE
}

# step_set_log_dir <dir>
# Set custom log directory
step_set_log_dir() {
    STEP_LOG_DIR="$1"
    mkdir -p "$STEP_LOG_DIR"
}

# step_get_log_dir
# Echo the current log directory
step_get_log_dir() {
    echo "$STEP_LOG_DIR"
}

# step_get_run_timestamp
# Echo the current run timestamp
step_get_run_timestamp() {
    echo "$_RUN_TIMESTAMP"
}

# step_get_current
# Echo the current step id
step_get_current() {
    echo "$_STEP_CURRENT"
}

# step_get_log_file
# Echo the current step's log file path
step_get_log_file() {
    echo "$_STEP_LOG_FILE"
}

# step_get_results
# Print all step results (for debugging/testing)
step_get_results() {
    for step_id in "${_STEP_ORDER[@]}"; do
        echo "${step_id}: ${_STEP_RESULTS[$step_id]}"
    done
}
