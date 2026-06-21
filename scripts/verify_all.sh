#!/usr/bin/env bash
# Canonical verification gate for the k9b repository.
#
# Profile options:
#   --fast        Fast local profile (≤60s, policy + smoke checks) - LOCAL DEFAULT
#   --full        Exhaustive merge-grade verification (preserves current behavior)
#
# Legacy scope options (preserved):
#   --python-only    Run only Python lane steps
#   --frontend-only  Run only Frontend lane steps
#   --helm-only      Run only Helm lane steps
#
# Output modes:
#   --json            Emit only JSON summary to stdout
#   STEP_VERBOSE=1   Stream full step output to console
#
# Every run prints:
#   - Profile name
#   - Elapsed time
#   - Checks run
#   - Checks intentionally skipped
#   - Exact escalation command for merge-grade evidence
#
# Usage:
#   ./scripts/verify_all.sh                    # fast profile (local default)
#   ./scripts/verify_all.sh --fast             # explicit fast profile
#   ./scripts/verify_all.sh --full             # exhaustive merge-grade gate
#   ./scripts/verify_all.sh --json             # fast profile, JSON output
#   ./scripts/verify_all.sh --full --json      # full gate, JSON output
#   ./scripts/verify_all.sh --python-only      # legacy: Python lane only
#
# Policy: Only --full may be called "full gate green".
#         --fast and lane scopes must report with their exact profile name.

set -uo pipefail

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

STEP_JSON_MODE=""
STEP_SCOPE="all"  # Default: all steps
STEP_PROFILE=""   # Current profile (fast, full, or empty for legacy)

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fast)
            STEP_PROFILE="fast"
            shift
            ;;
        --full)
            STEP_PROFILE="full"
            shift
            ;;
        --json)
            STEP_JSON_MODE=1
            export STEP_JSON_MODE
            shift
            ;;
        --python-only)
            STEP_SCOPE="python"
            shift
            ;;
        --frontend-only)
            STEP_SCOPE="frontend"
            shift
            ;;
        --helm-only)
            STEP_SCOPE="helm"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--fast|--full] [--json] [--python-only] [--frontend-only] [--helm-only]"
            echo ""
            echo "Profiles:"
            echo "  --fast       Fast local profile (≤60s, policy + smoke checks) [DEFAULT]"
            echo "  --full       Exhaustive merge-grade verification"
            echo ""
            echo "Output modes:"
            echo "  --json       Emit only JSON summary to stdout"
            echo ""
            echo "Legacy scope options:"
            echo "  --python-only    Run only Python lane steps"
            echo "  --frontend-only  Run only Frontend lane steps"
            echo "  --helm-only      Run only Helm lane steps"
            echo ""
            echo "Without --fast or --full, defaults to --fast for local development."
            echo ""
            echo "Environment variables:"
            echo "  STEP_VERBOSE=1    Stream full step output to console"
            echo ""
            echo "Evidence policy:"
            echo "  Only --full may be called 'full gate green'."
            echo "  --fast and lane scopes must report with their exact profile name."
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 [--fast|--full] [--json] [--python-only] [--frontend-only] [--helm-only]" >&2
            exit 1
            ;;
    esac
done

# Default profile behavior:
# - Lane scope (--python-only, etc.): always use full (legacy-compatible)
# - With --fast or --full: use explicit profile
# - With no flags: default to fast (local development default)
if [[ "$STEP_SCOPE" != "all" ]]; then
    # Lane scope commands always run full to preserve legacy behavior
    STEP_PROFILE="full"
elif [[ -z "$STEP_PROFILE" ]]; then
    # No scope = local default = fast
    STEP_PROFILE="fast"
fi

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"

# Source shared step runner
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/step_runner.sh
source "$SCRIPT_DIR/step_runner.sh"

# ---------------------------------------------------------------------------
# Recursion protection
# ---------------------------------------------------------------------------

if [[ -n "${VERIFY_ALL_ACTIVE:-}" ]]; then
    echo "ERROR: verify_all.sh recursion detected." >&2
    echo "VERIFY_ALL_ACTIVE is already set (value: $VERIFY_ALL_ACTIVE)." >&2
    echo "Do not invoke verify_all.sh from within a verify_all context." >&2
    exit 2
fi
export VERIFY_ALL_ACTIVE=1

# ---------------------------------------------------------------------------
# Single-instance lock (atomic mkdir-based)
# ---------------------------------------------------------------------------
# Uses mkdir for atomic lock acquisition on POSIX systems.
# The lock directory (.lock) is atomically created - if it already exists,
# mkdir fails with EEXIST, preventing race conditions in check-then-write.
#
# Lock structure:
#   .verify_lock/      - lock root directory
#   .verify_lock/.lock - atomic lock indicator (created by winner)
#   .verify_lock/pid    - metadata: PID of lock holder (for stale lock detection)
# ---------------------------------------------------------------------------

_LOCK_DIR="$REPO_ROOT/.verify_lock"
_LOCK_MARKER="$_LOCK_DIR/.lock"
_LOCK_PID_FILE="$_LOCK_DIR/pid"

_acquire_lock() {
    # Ensure lock root exists
    mkdir -p "$_LOCK_DIR" 2>/dev/null || {
        echo "ERROR: Cannot create lock directory '$_LOCK_DIR'." >&2
        exit 3
    }
    
    # Try atomic lock acquisition using mkdir
    # This succeeds ONLY if .lock doesn't already exist (atomic on POSIX)
    if ! mkdir "$_LOCK_MARKER" 2>/dev/null; then
        # Lock exists - check if it's stale (PID not running)
        local stale_pid
        stale_pid=$(cat "$_LOCK_PID_FILE" 2>/dev/null)
        if [[ -n "$stale_pid" ]] && kill -0 "$stale_pid" 2>/dev/null; then
            echo "ERROR: Another verification run is active (PID: $stale_pid)." >&2
            echo "Wait for it to complete or kill it before running again." >&2
            exit 4
        fi
        # Stale lock detected - remove and retry
        rm -rf "$_LOCK_MARKER" 2>/dev/null
        if ! mkdir "$_LOCK_MARKER" 2>/dev/null; then
            # Lost the race to another process - report active lock
            echo "ERROR: Another verification run is active." >&2
            exit 4
        fi
    fi
    
    # Write PID metadata for stale lock detection by future runs
    echo $$ > "$_LOCK_PID_FILE"
}

_release_lock() {
    # Only remove if we own the lock (PID matches)
    local lock_pid
    lock_pid=$(cat "$_LOCK_PID_FILE" 2>/dev/null)
    if [[ "$lock_pid" == "$$" ]]; then
        rm -rf "$_LOCK_DIR" 2>/dev/null
    fi
}

_acquire_lock
trap _release_lock EXIT

# Ensure verification output directory exists
mkdir -p "$REPO_ROOT/runs/verification"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: Required interpreter '$PYTHON' not found or not executable." >&2
    echo "Create it via 'python -m venv .venv' and install dependencies." >&2
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm is not installed or not on PATH." >&2
    echo "Install Node.js/npm before running frontend checks." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Run verification steps in parallel lanes
#
# Two lanes run concurrently:
#   - Python lane: ruff-lint, unit-tests, mypy
#   - Frontend lane: npm-ci, npm-test-ui, npm-build
#
# Each lane is internally sequential.
# Step results are tracked via shared state files for final summary ordering.
# ---------------------------------------------------------------------------

# Shared state file for tracking lane results
_LANE_STATE_FILE="$REPO_ROOT/runs/verification/${_RUN_TIMESTAMP}-lane-state.json"

# Global failure flag file - created when any step fails across both lanes
# This enables early termination signaling to other running steps
_GLOBAL_FAILED_FILE="$REPO_ROOT/runs/verification/${_RUN_TIMESTAMP}-global-failed.flag"

# Initialize lane state
echo '{"python": [], "frontend": [], "helm": []}' > "$_LANE_STATE_FILE"

# Initialize global failure flag as not existing
unset _GLOBAL_FAILED_SET

# Function to mark global failure immediately
_mark_global_failed() {
    # Touch the flag file - this is the signal for other lanes
    touch "$_GLOBAL_FAILED_FILE" 2>/dev/null || true
    _GLOBAL_FAILED_SET=true
}

# ---------------------------------------------------------------------------
# Step metadata for timing inventory
# ---------------------------------------------------------------------------
# Maps step_id -> "lane|command"

declare -A _STEP_META=()

# Register step metadata before running
_register_step() {
    local step_id="$1"
    local lane="$2"
    shift 2
    # Store lane and command for timing inventory
    local cmd_str=""
    for arg in "$@"; do
        if [[ -n "$cmd_str" ]]; then
            cmd_str="$cmd_str $arg"
        else
            cmd_str="$arg"
        fi
    done
    _STEP_META["$step_id"]="$lane|$cmd_str"
}

# Function to check if global failure has been marked
_is_global_failed() {
    [[ -f "$_GLOBAL_FAILED_FILE" ]] && return 0 || return 1
}

# Function to record step result in lane state
_record_step_result() {
    local lane="$1"
    local step_id="$2"
    local result="$3"
    local duration_ms="$4"
    local exit_code="$5"
    local log_file="${STEP_LOG_DIR}/${_RUN_TIMESTAMP}-${step_id}.log"
    
    # If this step failed, mark global failure immediately
    if [[ "$result" == "FAIL" ]]; then
        _mark_global_failed
    fi
    
    # Append to lane state file (simple JSON array append simulation)
    local tmp_file="${_LANE_STATE_FILE}.tmp"
    # Use Python to properly update JSON with file locking for concurrent access
    "$PYTHON" -c "
import json
import fcntl
import os
import time

state_file = '$_LANE_STATE_FILE'
lock_file = state_file + '.lock'
step = {
    'id': '$step_id',
    'status': '$result',
    'duration_ms': $duration_ms,
    'exit_code': $exit_code,
    'log_file': '$log_file'
}

# Retry loop for lock acquisition (handles concurrent access)
for attempt in range(10):
    try:
        with open(lock_file, 'w') as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                try:
                    with open(state_file, 'r') as f:
                        state = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError):
                    # Include all three lanes in default state
                    state = {'python': [], 'frontend': [], 'helm': []}
                state['$lane'].append(step)
                with open(state_file, 'w') as f:
                    json.dump(state, f)
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
            break
    except (IOError, OSError):
        if attempt < 9:
            time.sleep(0.05)  # Brief backoff before retry
        else:
            # Last attempt - try without locking as fallback
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                state = {'python': [], 'frontend': [], 'helm': []}
            state['$lane'].append(step)
            with open(state_file, 'w') as f:
                json.dump(state, f)
"
}

# Run a step and record result to lane state
_run_and_record() {
    local lane="$1"
    local step_id="$2"
    local message="$3"
    shift 3
    
    _STEP_CURRENT="$step_id"
    _STEP_ORDER+=("$step_id")
    
    local log_file="${STEP_LOG_DIR}/${_RUN_TIMESTAMP}-${step_id}.log"
    > "$log_file"
    
    local start_time end_time duration_ms exit_code
    start_time=$(date +%s)
    
    # Check for global failure before starting the step
    # If another lane has already failed, skip this step to avoid noise
    if _is_global_failed; then
        # Mark this step as skipped (no actual run)
        duration_ms=0
        if [[ -z "${STEP_JSON_MODE:-}" ]]; then
            echo "[$step_id] SKIPPED (already failed) - $message"
        fi
        _record_step_result "$lane" "$step_id" "SKIP" "$duration_ms" "0"
        _STEP_RESULTS["$step_id"]="SKIP|${duration_ms}|0"
        return 0
    fi
    
    if [[ -z "${STEP_JSON_MODE:-}" ]] && [[ -z "${STEP_VERBOSE:-}" ]] && _step_needs_hint "$step_id"; then
        _step_emit_hint "$step_id" "$log_file"
    fi
    
    # Run the command (capture output, track time)
    local poll_interval=1
    local _step_last_heartbeat=$(( start_time - STEP_HEARTBEAT_INTERVAL ))
    
    "$@" >> "$log_file" 2>&1 &
    local bg_pid=$!
    
    while kill -0 "$bg_pid" 2>/dev/null; do
        sleep "$poll_interval"
        
        # Check for global failure - suppress heartbeats after first failure
        # DO NOT kill running steps - let them complete truthfully
        # Only prevent unnecessary work by skipping future not-yet-started steps
        if _is_global_failed; then
            # Global failure detected - stop emitting heartbeats
            # But let the step finish naturally to get truthful PASS/FAIL
            # Just break out of heartbeat loop without killing the process
            break
        fi
        
        local current_time=$(date +%s)
        local elapsed=$(( current_time - start_time ))
        local remainder=$(( elapsed % STEP_HEARTBEAT_INTERVAL ))
        # Suppress heartbeats in JSON mode
        if (( remainder == 0 )) && [[ -z "${STEP_JSON_MODE:-}" ]]; then
            echo "[HINT:HEARTBEAT] step=${step_id} elapsed=${elapsed}s log=${log_file}"
        fi
    done
    
    # Wait for subprocess to finish and capture exit code
    # This step may have been running when global failure occurred, but it should
    # complete naturally to report its truthful PASS/FAIL status
    wait "$bg_pid"
    exit_code=$?
    
    end_time=$(date +%s)
    duration_ms=$(_step_duration_ms "$start_time" "$end_time")
    local duration_fmt=$(_step_format_duration "$duration_ms")
    
    local result="PASS"
    if (( exit_code != 0 )); then
        result="FAIL"
        _STEP_FAILED=true
        if [[ -z "${STEP_JSON_MODE:-}" ]]; then
            # Add visual separator before failure block for prominence
            echo "" >&2
            echo "═══════════════════════════════════════════════════════════" >&2
            echo "[$step_id] FAIL (${duration_fmt}) - $message" >&2
            _step_print_failure_info "$step_id" "$exit_code" "$log_file" "$duration_fmt"
            echo "═══════════════════════════════════════════════════════════" >&2
            echo "" >&2
        fi
    else
        if [[ -z "${STEP_JSON_MODE:-}" ]]; then
            echo "[$step_id] PASS (${duration_fmt}) - $message"
        fi
    fi
    
    # Record result to shared state
    _record_step_result "$lane" "$step_id" "$result" "$duration_ms" "$exit_code"
    
    # Also update local step results for compatibility
    _STEP_RESULTS["$step_id"]="${result}|${duration_ms}|${exit_code}"
}

# ---------------------------------------------------------------------------
# Profile-based step filtering
# ---------------------------------------------------------------------------
# Steps to skip for fast profile (expensive/full-suite steps)
_FAST_SKIP_PYTHON=(
    "unit-tests"
    "docs-claim-traceability"
    "docs-claim-candidates"
    "data-model-docs"
    "docs-claim-candidate-coverage"
    "docs-claim-candidate-dispositions"
    "docs-claim-disposition-csv-integrity"
    "docs-claim-disposition-semantic-diff-self-test"
    "docs-claim-candidate-backlog-report-self-test"
)
_FAST_SKIP_FRONTEND=(
    "npm-ci"
    "npm-test-ui"
    "npm-build"
)
_FAST_SKIP_HELM=()

# Check if a step should be skipped for current profile
_should_skip_step() {
    local step_id="$1"
    local lane="$2"
    
    if [[ "$STEP_PROFILE" == "full" ]]; then
        # Full profile: run everything
        return 1
    fi
    
    if [[ "$STEP_PROFILE" == "fast" ]]; then
        # Fast profile: skip expensive steps
        case "$lane" in
            python)
                for skip in "${_FAST_SKIP_PYTHON[@]}"; do
                    [[ "$step_id" == "$skip" ]] && return 0
                done
                ;;
            frontend)
                for skip in "${_FAST_SKIP_FRONTEND[@]}"; do
                    [[ "$step_id" == "$skip" ]] && return 0
                done
                ;;
            helm)
                for skip in "${_FAST_SKIP_HELM[@]}"; do
                    [[ "$step_id" == "$skip" ]] && return 0
                done
                ;;
        esac
    fi
    
    return 1
}

# Run Python lane in background
_run_python_lane() {
    if ! _should_skip_step "doctrine" "python"; then
        _run_and_record "python" "doctrine" "Verifying Factory blockstor-derived doctrine" bash "$SCRIPT_DIR/verify_factory_doctrine.sh"
    fi
    if ! _should_skip_step "dockerhub-base-images" "python"; then
        _run_and_record "python" "dockerhub-base-images" "Verifying Dockerfiles use Harbor proxy cache" bash "$SCRIPT_DIR/verify_dockerhub_base_images.sh"
    fi
    if ! _should_skip_step "docker-workflow-hygiene" "python"; then
        _run_and_record "python" "docker-workflow-hygiene" "Verifying Docker workflow registry hygiene" bash "$SCRIPT_DIR/verify_docker_workflow_hygiene.sh"
    fi
    if ! _should_skip_step "helm-workflow-hygiene" "python"; then
        _run_and_record "python" "helm-workflow-hygiene" "Verifying Helm version pin hygiene" bash "$SCRIPT_DIR/verify_helm_workflow_hygiene.sh"
    fi
    if ! _should_skip_step "docker-build-locality" "python"; then
        _run_and_record "python" "docker-build-locality" "Verifying Docker build locality hygiene" bash "$SCRIPT_DIR/verify_docker_build_locality.sh"
    fi
    if ! _should_skip_step "agent-pipeline" "python"; then
        _run_and_record "python" "agent-pipeline" "Verifying agentic doctrine pipeline" "$PYTHON" scripts/verify_agentic_pipeline.py
    fi
    if ! _should_skip_step "llm-evidence-boundaries" "python"; then
        _run_and_record "python" "llm-evidence-boundaries" "Verifying LLM evidence boundaries" "$PYTHON" scripts/verify_llm_evidence_boundaries.py
    fi
    if ! _should_skip_step "llm-semantic-injection" "python"; then
        _run_and_record "python" "llm-semantic-injection" "Verifying semantic injection detection" "$PYTHON" scripts/verify_llm_semantic_injection_detection.py
    fi
    if ! _should_skip_step "discovery-logging-hygiene" "python"; then
        _run_and_record "python" "discovery-logging-hygiene" "Verifying discovery strategy logging hygiene" "$PYTHON" scripts/verify_discovery_logging_hygiene.py
    fi
    if ! _should_skip_step "pvc-rollout-policy" "python"; then
        _run_and_record "python" "pvc-rollout-policy" "Verifying PVC rollout policy (Recreate for single-writer)" "$PYTHON" scripts/verify_pvc_rollout_policy.py
    fi
    if ! _should_skip_step "shared-pvc-colocation" "python"; then
        _run_and_record "python" "shared-pvc-colocation" "Verifying shared PVC colocation policy" "$PYTHON" scripts/verify_shared_pvc_colocation.py
    fi
    if ! _should_skip_step "next-check-sanitization" "python"; then
        _run_and_record "python" "next-check-sanitization" "Verifying next-check sanitization hygiene" "$PYTHON" scripts/verify_next_check_sanitization_hygiene.py
    fi
    if ! _should_skip_step "operator-projection-hygiene" "python"; then
        _run_and_record "python" "operator-projection-hygiene" "Verifying operator projection sanitization hygiene" "$PYTHON" scripts/verify_operator_projection_hygiene.py
    fi
    if ! _should_skip_step "llm-friendly" "python"; then
        _run_and_record "python" "llm-friendly" "Checking file sizes for LLM-friendly limits" "$PYTHON" scripts/check_llm_friendly_files.py --quiet
    fi
    if ! _should_skip_step "ruff-lint" "python"; then
        _run_and_record "python" "ruff-lint" "Running Ruff lint" "$PYTHON" -m ruff check src tests
    fi
    if ! _should_skip_step "structured-output" "python"; then
        _run_and_record "python" "structured-output" "Verifying health-loop structured output hygiene" bash "$SCRIPT_DIR/verify_health_loop_structured_output.sh"
    fi
    if ! _should_skip_step "unit-tests" "python"; then
        _run_and_record "python" "unit-tests" "Running unit tests" env PYTHON="$PYTHON" VERIFY_ALL_ACTIVE=1 RUN_FULL_VERIFY_TEST= bash "$SCRIPT_DIR/run_unit_tests.sh"
    fi
    if ! _should_skip_step "mypy" "python"; then
        _run_and_record "python" "mypy" "Running mypy" "$PYTHON" -m mypy src/k8s_diag_agent
    fi
    if ! _should_skip_step "mypy-tests" "python"; then
        _run_and_record "python" "mypy-tests" "Running mypy on tests" "$PYTHON" -m mypy tests/__init__.py tests/path_helper.py tests/test_*.py
    fi
    if ! _should_skip_step "ci-gate-drift" "python"; then
        _run_and_record "python" "ci-gate-drift" "Verifying CI workflow gate mappings" "$PYTHON" scripts/verify_ci_gate_drift.py
    fi
    if ! _should_skip_step "data-model-docs" "python"; then
        _run_and_record "python" "data-model-docs" "Verifying data model documentation hygiene" "$PYTHON" scripts/verify_data_model_docs.py
    fi
    if ! _should_skip_step "docs-inventory" "python"; then
        _run_and_record "python" "docs-inventory" "Verifying docs inventory integrity" "$PYTHON" scripts/verify_docs_inventory.py
    fi
    if ! _should_skip_step "docs-claims-registry" "python"; then
        _run_and_record "python" "docs-claims-registry" "Verifying docs claims registry integrity" "$PYTHON" scripts/verify_docs_claims_registry.py
    fi
    if ! _should_skip_step "docs-claim-traceability" "python"; then
        _run_and_record "python" "docs-claim-traceability" "Verifying docs claim traceability matrix" "$PYTHON" scripts/verify_docs_claim_traceability.py
    fi
    if ! _should_skip_step "docs-claim-candidates" "python"; then
        _run_and_record "python" "docs-claim-candidates" "Scanning docs for claim candidates" "$PYTHON" scripts/scan_docs_claim_candidates.py
    fi
    if ! _should_skip_step "docs-claim-candidate-coverage" "python"; then
        _run_and_record "python" "docs-claim-candidate-coverage" "Verifying docs claim candidate coverage" "$PYTHON" scripts/verify_docs_claim_candidate_coverage.py
    fi
    if ! _should_skip_step "docs-claim-candidate-dispositions" "python"; then
        _run_and_record "python" "docs-claim-candidate-dispositions" "Verifying docs claim candidate dispositions" "$PYTHON" scripts/verify_docs_claim_candidate_dispositions.py
    fi
    if ! _should_skip_step "docs-claim-disposition-csv-integrity" "python"; then
        _run_and_record "python" "docs-claim-disposition-csv-integrity" "Verifying disposition shard CSV integrity" "$PYTHON" scripts/verify_docs_claim_disposition_csv_integrity.py
    fi
    if ! _should_skip_step "docs-claim-disposition-semantic-diff-self-test" "python"; then
        _run_and_record "python" "docs-claim-disposition-semantic-diff-self-test" "Verifying disposition semantic diff self-test" "$PYTHON" scripts/diff_docs_claim_dispositions.py --self-test
    fi
    if ! _should_skip_step "docs-claim-candidate-backlog-report-self-test" "python"; then
        _run_and_record "python" "docs-claim-candidate-backlog-report-self-test" "Verifying claim candidate backlog report self-test" "$PYTHON" scripts/run_backlog_report.py --self-test
    fi
    if ! _should_skip_step "incident-report-quality" "python"; then
        _run_and_record "python" "incident-report-quality" "Verifying incident report quality invariants" "$PYTHON" scripts/verify_incident_report_quality.py
    fi
    if ! _should_skip_step "artifact-immutability" "python"; then
        _run_and_record "python" "artifact-immutability" "Verifying artifact immutability enforcement" "$PYTHON" scripts/verify_artifact_immutability.py
    fi
    if ! _should_skip_step "production-readiness-disclaimer" "python"; then
        _run_and_record "python" "production-readiness-disclaimer" "Verifying production readiness disclaimers" "$PYTHON" scripts/verify_production_readiness_disclaimer.py
    fi
}

# Emit gate timings JSON sorted by duration
_emit_gate_timings() {
    local timings_file="$REPO_ROOT/.gate-timings.json"
    
    # Write timing JSON using Python for proper JSON handling
    # Pass state_file and timings_file as arguments to avoid heredoc issues
    "$PYTHON" -c "
import json
from datetime import datetime, timezone

state_file = '$_LANE_STATE_FILE'
timings_file = '$timings_file'

# Step command map (lane|command format - no tuples to avoid quoting issues)
step_commands = {
    'doctrine': 'python|bash verify_factory_doctrine.sh',
    'dockerhub-base-images': 'python|bash verify_dockerhub_base_images.sh',
    'docker-workflow-hygiene': 'python|bash verify_docker_workflow_hygiene.sh',
    'helm-workflow-hygiene': 'python|bash verify_helm_workflow_hygiene.sh',
    'docker-build-locality': 'python|bash verify_docker_build_locality.sh',
    'agent-pipeline': 'python|python scripts/verify_agentic_pipeline.py',
    'llm-evidence-boundaries': 'python|python scripts/verify_llm_evidence_boundaries.py',
    'llm-semantic-injection': 'python|python scripts/verify_llm_semantic_injection_detection.py',
    'discovery-logging-hygiene': 'python|python scripts/verify_discovery_logging_hygiene.py',
    'pvc-rollout-policy': 'python|python scripts/verify_pvc_rollout_policy.py',
    'shared-pvc-colocation': 'python|python scripts/verify_shared_pvc_colocation.py',
    'next-check-sanitization': 'python|python scripts/verify_next_check_sanitization_hygiene.py',
    'operator-projection-hygiene': 'python|python scripts/verify_operator_projection_hygiene.py',
    'llm-friendly': 'python|python scripts/check_llm_friendly_files.py --quiet',
    'ruff-lint': 'python|python -m ruff check src tests',
    'structured-output': 'python|bash verify_health_loop_structured_output.sh',
    'unit-tests': 'python|bash scripts/run_unit_tests.sh',
    'mypy': 'python|python -m mypy src/k8s_diag_agent',
    'mypy-tests': 'python|python -m mypy tests/__init__.py tests/path_helper.py tests/test_*.py',
    'npm-ci': 'frontend|npm ci',
    'npm-test-ui': 'frontend|bash scripts/run_frontend_ui_tests.sh',
    'npm-build': 'frontend|npm run build',
    'helm-chart': 'helm|bash verify_helm_chart.sh',
    'helm-oci-login': 'helm|bash verify_helm_oci_login.sh',
}

try:
    with open(state_file, 'r') as f:
        state = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    state = {'python': [], 'frontend': [], 'helm': []}

# Collect all steps with metadata
timings = []
for lane in ['python', 'frontend', 'helm']:
    for step in state.get(lane, []):
        step_id = step['id']
        # Get command and lane from map
        meta = step_commands.get(step_id, 'unknown|unknown')
        parts = meta.split('|', 1)
        cmd_lane = parts[0]
        command = parts[1] if len(parts) > 1 else meta
        
        timings.append({
            'id': step_id,
            'command': command,
            'lane': cmd_lane,
            'exit_code': step['exit_code'],
            'duration_ms': step['duration_ms'],
            'notes': None
        })

# Sort by duration descending (slowest first)
timings.sort(key=lambda x: x['duration_ms'], reverse=True)

# Calculate total step time (sum of all step durations, not wall-clock)
total_step_duration = sum(t['duration_ms'] for t in timings) if timings else 0

# Build output
output = {
    'generated': datetime.now(timezone.utc).isoformat(),
    'total_step_duration_ms': total_step_duration,
    'step_count': len(timings),
    'steps': timings
}

with open(timings_file, 'w') as f:
    json.dump(output, f, indent=2)

print(timings_file)
"
    
    if [[ -f "$timings_file" ]]; then
        echo ""
        echo "=== Gate Timing Summary (sorted by duration) ==="
        # Print top 10 slowest steps
        "$PYTHON" -c "
import json
with open('$timings_file', 'r') as f:
    data = json.load(f)
print(f'Total steps: {data[\"step_count\"]}')
print(f'Total step time: {data[\"total_step_duration_ms\"]}ms ({data[\"total_step_duration_ms\"]/1000:.1f}s)')
print()
print(f\"{'Step':<35} {'Duration':>10} {'Lane':<10} {'Exit':>5}\")
print('-' * 65)
for step in data['steps'][:10]:
    duration_fmt = f\"{step['duration_ms']}ms\"
    if step['duration_ms'] >= 1000:
        duration_fmt = f\"{step['duration_ms']/1000:.1f}s\"
    print(f\"{step['id']:<35} {duration_fmt:>10} {step['lane']:<10} {step['exit_code']:>5}\")
"
    fi
}

# Run Frontend lane in background
_run_frontend_lane() {
    pushd "$REPO_ROOT/frontend" >/dev/null
    if ! _should_skip_step "npm-ci" "frontend"; then
        _run_and_record "frontend" "npm-ci" "Installing frontend deps (npm ci)" npm ci
    fi
    if ! _should_skip_step "npm-test-ui" "frontend"; then
        _run_and_record "frontend" "npm-test-ui" "Running frontend UI tests" bash "$REPO_ROOT/scripts/run_frontend_ui_tests.sh"
    fi
    if ! _should_skip_step "npm-build" "frontend"; then
        _run_and_record "frontend" "npm-build" "Building frontend" npm run build
    fi
    popd >/dev/null
}

# Run Helm lane
_run_helm_lane() {
    if ! command -v helm >/dev/null 2>&1; then
        # Record helm failure as a FAIL using a command that will fail
        # We use a subshell that exits 1 to trigger the failure path
        _run_and_record "helm" "helm-chart" "Helm chart verification (helm not installed)" bash -c 'echo "ERROR: helm not installed" >&2; exit 1'
        return 0
    fi
    _run_and_record "helm" "helm-chart" "Verifying Helm chart" bash "$SCRIPT_DIR/verify_helm_chart.sh"
    _run_and_record "helm" "helm-oci-login" "Verifying Helm OCI dual-login workaround" bash "$SCRIPT_DIR/verify_helm_oci_login.sh"
}

# Launch lanes based on scope
# - "all": run all lanes concurrently
# - "python": run only Python lane
# - "frontend": run only Frontend lane
# - "helm": run only Helm lane
python_exit=0
frontend_exit=0
helm_exit=0

# Lane semantics:
# - --python-only, --frontend-only, --helm-only: run FULL lane (legacy-compatible)
# - Without scope flags: respect STEP_PROFILE (fast skips expensive, full runs all)
#
# This ensures legacy commands are not silently weakened by fast profile.

case "$STEP_SCOPE" in
    all)
        # Run all lanes concurrently
        # Profile affects step selection within lanes
        _run_python_lane &
        python_pid=$!
        _run_frontend_lane &
        frontend_pid=$!
        _run_helm_lane &
        helm_pid=$!
        
        # Wait for all lanes and capture exit codes
        wait $python_pid
        python_exit=$?
        wait $frontend_pid
        frontend_exit=$?
        wait $helm_pid
        helm_exit=$?
        ;;
    python)
        # Legacy Python lane: always run full Python suite (ignore profile for lane scope)
        _RUN_FULL_LANE=1 _run_python_lane
        python_exit=$?
        ;;
    frontend)
        # Legacy Frontend lane: always run full frontend suite (ignore profile for lane scope)
        _RUN_FULL_LANE=1 _run_frontend_lane
        frontend_exit=$?
        ;;
    helm)
        # Legacy Helm lane: always run full Helm suite (ignore profile for lane scope)
        _RUN_FULL_LANE=1 _run_helm_lane
        helm_exit=$?
        ;;
esac

# Merge lane state into step results for summary
# This ensures final summary reflects canonical ordering (python steps first, then frontend)
if [[ -f "$_LANE_STATE_FILE" ]]; then
    "$PYTHON" -c "
import json
with open('$_LANE_STATE_FILE', 'r') as f:
    state = json.load(f)
for step in state['python']:
    lane = 'python'
for step in state['frontend']:
    lane = 'frontend'
"
    # Import lane results into step runner's internal state
    # Reset _STEP_ORDER to canonical sequence
    _STEP_ORDER=()
    _STEP_RESULTS=()
    # Source the lane state and merge
    eval "$("$PYTHON" -c "
import json
with open('$_LANE_STATE_FILE', 'r') as f:
    state = json.load(f)
# Merge: python lane first, then frontend lane
for step in state['python'] + state['frontend']:
    print(f'_STEP_ORDER+=(\"{step[\"id\"]}\")')
    print(f'_STEP_RESULTS[\"{step[\"id\"]}\"]=\"{step[\"status\"]}|{step[\"duration_ms\"]}|{step[\"exit_code\"]}\"')
    if step['status'] == 'FAIL':
        print('_STEP_FAILED=true')
")"
fi

# Determine overall exit code (non-zero if any lane failed)
if (( python_exit != 0 )) || (( frontend_exit != 0 )) || (( helm_exit != 0 )); then
    _OVERALL_EXIT=1
else
    _OVERALL_EXIT=0
fi

# ---------------------------------------------------------------------------
# Finalize
# ---------------------------------------------------------------------------

# Determine exit code: non-zero if any step failed (tracked via lane results)
final_exit=0
if [[ -f "$_LANE_STATE_FILE" ]]; then
    # Check if any step failed from lane state (include helm lane)
    failed_count=$("$PYTHON" -c "
import json
with open('$_LANE_STATE_FILE', 'r') as f:
    state = json.load(f)
failed = sum(1 for s in state['python'] + state['frontend'] + state.get('helm', []) if s['status'] == 'FAIL')
print(failed)
")
    if (( failed_count > 0 )); then
        final_exit=1
    fi
fi

# Emit gate timings before finalize (unless in JSON mode where we want clean output)
if [[ -z "${STEP_JSON_MODE:-}" ]]; then
    export _LANE_STATE_FILE _TIMINGS_FILE
    _emit_gate_timings
fi

# ---------------------------------------------------------------------------
# Profile-aware finalization
# ---------------------------------------------------------------------------

# Get steps that were run and skipped
if [[ -f "$_LANE_STATE_FILE" ]]; then
    # Count steps that ran
    steps_run=$("$PYTHON" -c "
import json
with open('$_LANE_STATE_FILE', 'r') as f:
    state = json.load(f)
count = len(state['python']) + len(state['frontend']) + len(state.get('helm', []))
print(count)
")
    
    # Get elapsed time
    start_file="$STEP_DATA_DIR/${_RUN_TIMESTAMP}-start.txt"
    if [[ -f "$start_file" ]]; then
        start_ts=$(cat "$start_file")
        elapsed=$("$PYTHON" -c "
from datetime import datetime, timezone
try:
    start = datetime.fromisoformat('$start_ts'.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    elapsed = (now - start).total_seconds()
    print(f'{elapsed:.1f}')
except:
    print('N/A')
")
    else
        elapsed="N/A"
    fi
else
    steps_run=0
    elapsed="N/A"
fi

# Print profile-aware footer (unless JSON mode)
if [[ -z "${STEP_JSON_MODE:-}" ]]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "VERIFICATION PROFILE: ${STEP_PROFILE}"
    echo "═══════════════════════════════════════════════════════════"
    echo "Profile: ${STEP_PROFILE}"
    echo "Steps run: ${steps_run}"
    echo "Elapsed: ${elapsed}s"
    
    # Show skipped steps based on profile
    if [[ "$STEP_PROFILE" == "fast" ]]; then
        echo ""
        echo "Skipped (fast profile excludes expensive suites):"
        echo "  - unit-tests (Python full test suite)"
        echo "  - npm-ci, npm-test-ui, npm-build (Frontend full suite)"
        echo "  - docs-claim-* (Heavy docs scans)"
        echo ""
        echo "For merge-grade verification:"
        echo "  ./scripts/verify_all.sh --full"
    elif [[ "$STEP_PROFILE" == "full" ]]; then
        echo ""
        echo "Full profile: All verification steps executed."
    fi
    echo "═══════════════════════════════════════════════════════════"
fi

# Final exit with profile-specific message
if [[ "$final_exit" == "0" ]]; then
    if [[ -n "${STEP_JSON_MODE:-}" ]]; then
        # JSON mode: handled by step_finalize
        :
    else
        echo ""
        echo "VERIFICATION GATE [${STEP_PROFILE}]: PASSED"
    fi
else
    if [[ -n "${STEP_JSON_MODE:-}" ]]; then
        # JSON mode: handled by step_finalize
        :
    else
        echo ""
        echo "VERIFICATION GATE [${STEP_PROFILE}]: FAILED" >&2
    fi
fi

step_finalize $final_exit
