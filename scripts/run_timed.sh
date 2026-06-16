#!/usr/bin/env bash
# Timing wrapper that captures per-step duration and emits machine-readable timing data.
#
# Usage:
#   run_timed.sh [--output FILE] <step_id> [--] <command> [args...]
#   run_timed.sh --self-test              # Run self-test suite
#
# Output:
#   - Human: "[step_id] PASS (duration) - command args" or FAIL
#   - Machine: JSON to --output file (or stdout if not specified)
#   - Exit code: preserves wrapped command exit code
#
# JSON fields per step:
#   - id: step identifier
#   - command: full command line as string
#   - lane: category (default: "general")
#   - exit_code: wrapped command exit code
#   - duration_ms: elapsed time in milliseconds
#   - notes: optional additional context

set -uo pipefail

# ---------------------------------------------------------------------------
# Self-test suite
# ---------------------------------------------------------------------------

run_self_test() {
    local test_name="$1"
    local expected_exit="$2"
    shift 2
    # Remaining args are the command to run
    
    echo "  Testing: $test_name"
    
    local output
    local actual_exit
    
    # Run timing wrapper with a test step
    output=$(cd "$(dirname "$0")" && bash run_timed.sh "test-$test_name" "$@" 2>&1)
    actual_exit=$?
    
    local passed=true
    
    # Check exit code
    if [[ "$actual_exit" -ne "$expected_exit" ]]; then
        echo "    FAIL: Expected exit $expected_exit, got $actual_exit"
        passed=false
    fi
    
    # Check output mentions duration
    if ! echo "$output" | grep -qE '[0-9]+(\.[0-9])?s|[0-9]+ms'; then
        echo "    FAIL: No duration in output"
        passed=false
    fi
    
    # Check JSON was produced
    if ! echo "$output" | grep -q '"duration_ms"'; then
        echo "    FAIL: No duration_ms in output"
        passed=false
    fi
    
    if $passed; then
        echo "    PASS"
    else
        echo "    Output: $output"
    fi
    echo "$passed|$test_name"
}

self_test_exit_code_propagation() {
    echo "=== Timing Wrapper Self-Test Suite ==="
    echo ""
    
    echo "Test 1: Successful command returns 0"
    run_self_test "success-zero" 0 true
    
    echo ""
    echo "Test 2: Failing command returns nonzero"
    run_self_test "fail-nonzero" 1 false
    
    echo ""
    echo "Test 3: Command with real work completes"
    run_self_test "real-work" 0 bash -c 'sum=0; for i in $(seq 1000); do sum=$((sum + i)); done'
    
    echo ""
    echo "Test 4: Multiple arguments preserved"
    run_self_test "multi-args" 0 bash -c 'echo test && exit 0'
    
    echo ""
    echo "Test 5: Failing command with specific exit code"
    run_self_test "fail-specific" 42 bash -c 'exit 42'
    
    echo ""
    echo "=== Self-Test Summary ==="
    local failures=0
    
    # Results were printed by run_self_test, now just count
    # Run tests again and capture results
    results=$(cd "$(dirname "$0")" && {
        echo "$(run_self_test s1 0 true | tail -1)"
        echo "$(run_self_test s2 1 false | tail -1)"
        echo "$(run_self_test s3 0 bash -c 'sum=0; for i in $(seq 1000); do sum=$((sum + i)); done' | tail -1)"
        echo "$(run_self_test s4 0 bash -c 'echo test' | tail -1)"
        echo "$(run_self_test s5 42 bash -c 'exit 42' | tail -1)"
    } 2>&1)
    
    while IFS='|' read -r status name; do
        if [[ "$status" == "false" ]]; then
            echo "  FAIL: $name"
            (( failures++ ))
        elif [[ "$status" == "true" ]]; then
            echo "  PASS: $name"
        fi
    done <<< "$results"
    
    echo ""
    if (( failures > 0 )); then
        echo "SELF-TEST: FAILED ($failures failures)"
        exit 1
    else
        echo "SELF-TEST: PASSED (all tests)"
        exit 0
    fi
}

# Check for self-test mode first (before any other parsing)
for arg in "$@"; do
    if [[ "$arg" == "--self-test" ]]; then
        self_test_exit_code_propagation
        exit $?
    fi
done

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

OUTPUT_FILE=""
STEP_ID=""
COMMAND=()

while [[ $# -gt 0 ]]; do
    # Handle -- separator to stop option parsing
    if [[ "$1" == "--" ]]; then
        shift
        break
    fi
    
    # If step_id is already set, all remaining args are command args
    if [[ -n "$STEP_ID" ]]; then
        COMMAND+=("$1")
        shift
        continue
    fi
    
    # If this looks like an option (starts with -) and we haven't set step_id yet
    if [[ "$1" =~ ^- ]]; then
        case "$1" in
            --output)
                OUTPUT_FILE="$2"
                shift 2
                ;;
            --self-test)
                self_test_exit_code_propagation
                exit $?
                ;;
            --help|-h)
                echo "Usage: $0 [--output FILE] <step_id> [--] <command> [args...]"
                echo "   or: $0 --self-test"
                exit 0
                ;;
            -*)
                echo "Unknown option: $1" >&2
                exit 1
                ;;
        esac
    else
        # First non-option arg is the step_id
        STEP_ID="$1"
    fi
    shift
done

# Any remaining args are command + args
if [[ $# -gt 0 ]]; then
    COMMAND+=("$@")
fi

# ---------------------------------------------------------------------------
# Validate required arguments
# ---------------------------------------------------------------------------

if [[ -z "$STEP_ID" ]] || [[ ${#COMMAND[@]} -eq 0 ]]; then
    echo "Usage: $0 [--output FILE] <step_id> [--] <command> [args...]" >&2
    echo "   or: $0 --self-test" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Timing wrapper core
# ---------------------------------------------------------------------------

TIMING_FILE="${OUTPUT_FILE:-/dev/stdout}"
TEMP_TIMING=""

# Use temp file if output is stdout
if [[ "$TIMING_FILE" == "/dev/stdout" ]]; then
    TEMP_TIMING=$(mktemp)
    TIMING_FILE="$TEMP_TIMING"
fi

# Initialize timing JSON array
echo "[" > "$TIMING_FILE"

# Record start time (Python for macOS portability - %N is GNU-specific)
start_ms=$("$PYTHON" -c 'import time; print(int(time.time() * 1000))')

# Build command string for logging
COMMAND_STR=""
for arg in "${COMMAND[@]}"; do
    if [[ -n "$COMMAND_STR" ]]; then
        COMMAND_STR="$COMMAND_STR "
    fi
    # Quote args with spaces or special characters
    if [[ "$arg" =~ [[:space:]] || "$arg" == *\'* || "$arg" == *\"* ]]; then
        COMMAND_STR="$COMMAND_STR'$(echo "$arg" | sed "s/'/'\\\\''/g")'"
    else
        COMMAND_STR="$COMMAND_STR$arg"
    fi
done

# Execute wrapped command
"${COMMAND[@]}"
EXIT_CODE=$?

# Record end time (Python for macOS portability)
end_ms=$("$PYTHON" -c 'import time; print(int(time.time() * 1000))')

# Calculate duration in milliseconds
duration_ms=$(( end_ms - start_ms ))

# Format duration for human output
if (( duration_ms < 1000 )); then
    DURATION_FMT="${duration_ms}ms"
else
    secs=$(( duration_ms / 1000 ))
    fraction=$(( (duration_ms % 1000) / 100 ))
    DURATION_FMT="${secs}.${fraction}s"
fi

# Determine status
if (( EXIT_CODE == 0 )); then
    STATUS="PASS"
else
    STATUS="FAIL"
fi

# Emit human-readable output
echo "[$STEP_ID] $STATUS ($DURATION_FMT) - $COMMAND_STR"

# Emit JSON entry (append to array)
printf '  {"id": "%s", "command": %s, "lane": "general", "exit_code": %d, "duration_ms": %d, "notes": null}\n' \
    "$STEP_ID" \
    "$(python3 -c "import json; print(json.dumps('$COMMAND_STR'))")" \
    "$EXIT_CODE" \
    "$duration_ms" >> "$TIMING_FILE"

# Close JSON array
echo "]" >> "$TIMING_FILE"

# Output to stdout if we used a temp file
if [[ -n "$TEMP_TIMING" ]]; then
    cat "$TEMP_TIMING"
    rm -f "$TEMP_TIMING"
fi

# Preserve exit code
exit $EXIT_CODE
