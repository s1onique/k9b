#!/usr/bin/env bash
# Run unit tests with timing instrumentation.
# Outputs per-file timing to support profiling and sharding decisions.
#
# Usage:
#   scripts/run_unit_tests.sh              # standard run (unittest)
#   scripts/run_unit_tests.sh --profile    # with per-test timing
#   scripts/run_unit_tests.sh --shard N K  # run shard N of K (0-indexed)
#
# Exit codes:
#   0 - all tests passed
#   1 - tests failed
#   2 - invalid arguments

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
TEST_DIR="$REPO_ROOT/tests"

# Parse arguments
PROFILE_MODE=false
SHARD_MODE=false
SHARD_N=0
SHARD_TOTAL=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            PROFILE_MODE=true
            shift
            ;;
        --shard)
            SHARD_MODE=true
            SHARD_N="${2:-}"
            SHARD_TOTAL="${3:-}"
            # Validate N and K are provided
            if [[ -z "$SHARD_N" || -z "$SHARD_TOTAL" ]]; then
                echo "ERROR: --shard requires two arguments: N K" >&2
                exit 2
            fi
            # Validate they are integers
            if ! [[ "$SHARD_N" =~ ^[0-9]+$ || "$SHARD_N" == "0" ]] || ! [[ "$SHARD_TOTAL" =~ ^[0-9]+$ || "$SHARD_TOTAL" == "0" ]]; then
                echo "ERROR: --shard arguments must be integers" >&2
                exit 2
            fi
            # Validate range
            if (( SHARD_TOTAL <= 0 )); then
                echo "ERROR: --shard K must be > 0" >&2
                exit 2
            fi
            if (( SHARD_N < 0 || SHARD_N >= SHARD_TOTAL )); then
                echo "ERROR: --shard N must satisfy 0 <= N < K" >&2
                exit 2
            fi
            shift 3
            ;;
        -h|--help)
            echo "Usage: $0 [--profile] [--shard N K]"
            echo "  --profile   Enable pytest --durations profiling"
            echo "  --shard N K Run shard N of K parallel shards (0-indexed)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

# Check pytest availability
PYTEST_AVAILABLE=true
if ! "$PYTHON" -c "import pytest" 2>/dev/null; then
    PYTEST_AVAILABLE=false
fi

# Handle profile mode without pytest
if [[ "$PROFILE_MODE" == true && "$PYTEST_AVAILABLE" == false ]]; then
    echo "WARNING: pytest not available, falling back to unittest" >&2
    PROFILE_MODE=false
fi

# Handle shard mode without pytest
if [[ "$SHARD_MODE" == true && "$PYTEST_AVAILABLE" == false ]]; then
    echo "ERROR: --shard requires pytest" >&2
    exit 2
fi

# Create timing output directory
TIMING_DIR="$REPO_ROOT/runs/verification/test-timings"
mkdir -p "$TIMING_DIR"

# Timing file for this run
RUN_TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
TIMING_FILE="$TIMING_DIR/${RUN_TIMESTAMP}-timing.json"

# Collect test files if sharding
if [[ "$SHARD_MODE" == true ]]; then
    # Get all test files, sorted for deterministic sharding
    # Use portable while-read instead of mapfile for macOS compatibility
    TEST_FILES=$("$PYTHON" -m pytest --collect-only -q tests/ 2>/dev/null | \
                 grep "^tests/" | \
                 sed 's/::.*//' | \
                 sort -u)
    
    # Convert to array using portable while-read
    TEST_FILE_ARRAY=()
    while IFS= read -r test_file; do
        [[ -n "$test_file" ]] && TEST_FILE_ARRAY+=("$test_file")
    done <<< "$TEST_FILES"
    
    TOTAL_FILES=${#TEST_FILE_ARRAY[@]}
    
    # Calculate file ranges for this shard
    FILES_PER_SHARD=$(( (TOTAL_FILES + SHARD_TOTAL - 1) / SHARD_TOTAL ))
    START_IDX=$(( SHARD_N * FILES_PER_SHARD ))
    END_IDX=$(( START_IDX + FILES_PER_SHARD - 1 ))
    [[ $END_IDX -ge $TOTAL_FILES ]] && END_IDX=$(( TOTAL_FILES - 1 ))
    
    # Extract files for this shard
    SHARD_FILES=""
    for i in $(seq 0 $((TOTAL_FILES - 1))); do
        if [[ $i -ge $START_IDX && $i -le $END_IDX ]]; then
            SHARD_FILES="$SHARD_FILES ${TEST_FILE_ARRAY[$i]}"
        fi
    done
fi

# Build pytest command
if [[ "$PROFILE_MODE" == true ]]; then
    # Profile mode: use pytest with durations
    if [[ "$SHARD_MODE" == true ]]; then
        "$PYTHON" -m pytest $SHARD_FILES --durations=100 -v --tb=short 2>&1 | tee "$TIMING_FILE.log"
    else
        "$PYTHON" -m pytest tests/ --durations=100 -v --tb=short 2>&1 | tee "$TIMING_FILE.log"
    fi
    PYTEST_EXIT=$?
    
    # Extract timing data from pytest output
    "$PYTHON" -c "
import json
import re

timings = []
with open('$TIMING_FILE.log', 'r') as f:
    in_durations = False
    for line in f:
        if 'slowest' in line.lower() and 'durations' in line.lower():
            in_durations = True
            continue
        if in_durations:
            # Parse lines like: \"60.03s call     tests/unit/test_alertmanager_discovery.py::test_discover_alertmanagers_with_manual_sources\"
            match = re.match(r'([\d.]+)s\s+call\s+(.+)', line.strip())
            if match:
                duration = float(match.group(1))
                test_id = match.group(2).strip()
                timings.append({'test': test_id, 'duration_s': duration})
            elif line.strip() == '' or '=' in line:
                in_durations = False

with open('$TIMING_FILE', 'w') as f:
    json.dump({'timings': timings, 'mode': 'profile'}, f, indent=2)
"
    
    # Exit with pytest's exit code
    exit $PYTEST_EXIT
else
    # Standard mode: use unittest for compatibility
    if [[ "$SHARD_MODE" == true && -n "$SHARD_FILES" ]]; then
        "$PYTHON" -m pytest $SHARD_FILES --tb=short 2>&1 | tee "$TIMING_FILE.log"
    else
        env VERIFY_ALL_ACTIVE=1 RUN_FULL_VERIFY_TEST= "$PYTHON" -m unittest discover tests 2>&1 | tee "$TIMING_FILE.log"
    fi
    exit $?
fi