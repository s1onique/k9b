#!/usr/bin/env bash
# Run unit tests with timing instrumentation.
# Outputs per-file timing to support profiling and sharding decisions.
#
# Usage:
#   scripts/run_unit_tests.sh              # standard run (pytest tests/)
#   scripts/run_unit_tests.sh --profile    # with per-test timing
#   scripts/run_unit_tests.sh --shard N K  # run shard N of K (0-indexed, duration-weighted)
#   scripts/run_unit_tests.sh --verify-shards K  # verify K-way shard partition
#   scripts/run_unit_tests.sh --list-files # list all test files
#   scripts/run_unit_tests.sh --shard N K --list-files  # list files in shard N of K
#
# Exit codes:
#   0 - all tests passed
#   1 - tests failed
#   2 - invalid arguments

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
TEST_DIR="$REPO_ROOT/tests"
SHARD_SCRIPT="$REPO_ROOT/scripts/shard_tests.py"
DURATIONS_FILE="$REPO_ROOT/scripts/python_test_durations.json"

# Parse arguments
PROFILE_MODE=false
SHARD_MODE=false
VERIFY_MODE=false
LIST_FILES_MODE=false
SHARD_N=0
SHARD_TOTAL=1
VERIFY_TOTAL=0
JUNIT_XML=""

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
        --verify-shards)
            VERIFY_MODE=true
            VERIFY_TOTAL="${2:-}"
            if [[ -z "$VERIFY_TOTAL" ]]; then
                echo "ERROR: --verify-shards requires a number of shards" >&2
                exit 2
            fi
            if ! [[ "$VERIFY_TOTAL" =~ ^[0-9]+$ ]] || (( VERIFY_TOTAL <= 0 )); then
                echo "ERROR: --verify-shards argument must be a positive integer" >&2
                exit 2
            fi
            shift 2
            ;;
        --list-files)
            LIST_FILES_MODE=true
            shift
            ;;
        --junitxml)
            JUNIT_XML="${2:-}"
            if [[ -z "$JUNIT_XML" ]]; then
                echo "ERROR: --junitxml requires a path argument" >&2
                exit 2
            fi
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--profile] [--shard N K] [--verify-shards K] [--list-files] [--junitxml PATH]"
            echo "  --profile           Enable pytest --durations profiling"
            echo "  --shard N K         Run shard N of K parallel shards (duration-weighted)"
            echo "  --verify-shards K   Verify K-way shard partition correctness"
            echo "  --list-files        List all test files (or shard files if combined with --shard)"
            echo "  --junitxml PATH     Write JUnit XML report to PATH (for CI aggregation)"
            echo ""
            echo "Examples:"
            echo "  $0                          # Run all tests"
            echo "  $0 --profile                # Run with profiling"
            echo "  $0 --shard 0 4             # Run first quarter of tests (duration-weighted)"
            echo "  $0 --shard 1 4             # Run second quarter of tests (duration-weighted)"
            echo "  $0 --verify-shards 4       # Verify 4-way sharding is correct"
            echo "  $0 --shard 0 4 --list-files # List tests in shard 0 of 4"
            echo "  $0 --shard 0 2 --junitxml artifacts/junit/shard-0.xml"
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

# Function to get all test nodeids (deterministic order)
# NOTE: This collects tests that pass import checks. Some test files may be
# excluded due to import errors in specific test modules.
_get_all_test_nodeids() {
    "$PYTHON" -m pytest --collect-only -q \
        --ignore=tests/test_rollout_classifier_extended.py \
        --ignore=tests/unit/test_property_checks.py \
        tests/ 2>/dev/null | \
        grep "^tests/" | \
        sort
}

# Function to get nodeids for a specific shard using duration-weighted sharding
_get_shard_nodeids() {
    local shard_index=$1
    local shard_count=$2
    
    # Use the duration-weighted sharding script
    # stderr is suppressed - only stdout contains nodeids
    "$PYTHON" "$SHARD_SCRIPT" \
        --shard "$shard_index" \
        --total "$shard_count" \
        --durations "$DURATIONS_FILE" 2>/dev/null
}

# Function to list all nodeids or shard nodeids
_list_nodeids() {
    if [[ "$SHARD_MODE" == true ]]; then
        _get_shard_nodeids "$SHARD_N" "$SHARD_TOTAL"
    else
        _get_all_test_nodeids
    fi
}

# Handle list-files mode
if [[ "$LIST_FILES_MODE" == true ]]; then
    _list_nodeids
    exit 0
fi

# Handle verify-shards mode using the sharding script
if [[ "$VERIFY_MODE" == true ]]; then
    echo "=== Verifying ${VERIFY_TOTAL}-way shard partition ==="
    
    # Use the sharding script's verification
    "$PYTHON" "$SHARD_SCRIPT" \
        --verify \
        --total "$VERIFY_TOTAL" \
        --durations "$DURATIONS_FILE"
    exit $?
fi

# Create timing output directory
TIMING_DIR="$REPO_ROOT/runs/verification/test-timings"
mkdir -p "$TIMING_DIR"

# Timing file for this run
RUN_TIMESTAMP=$(date '+%Y%m%d-%H%M%S')

# Build timing filename with shard identity
if [[ "$SHARD_MODE" == true ]]; then
    TIMING_FILE="$TIMING_DIR/${RUN_TIMESTAMP}-timing-shard-${SHARD_N}-of-${SHARD_TOTAL}.json"
    TIMING_LOG="$TIMING_DIR/${RUN_TIMESTAMP}-timing-shard-${SHARD_N}-of-${SHARD_TOTAL}.log"
else
    TIMING_FILE="$TIMING_DIR/${RUN_TIMESTAMP}-timing.json"
    TIMING_LOG="$TIMING_DIR/${RUN_TIMESTAMP}-timing.log"
fi

# Collect nodeids if sharding
SHARD_NODEIDS=""
if [[ "$SHARD_MODE" == true ]]; then
    # Get nodeids - only stdout is used for nodeid file
    if ! SHARD_NODEIDS=$(_get_shard_nodeids "$SHARD_N" "$SHARD_TOTAL"); then
        echo "ERROR: failed to compute test shard $SHARD_N/$SHARD_TOTAL" >&2
        exit 2
    fi
    
    if [[ -z "$SHARD_NODEIDS" ]]; then
        echo "ERROR: empty shard selection for $SHARD_N/$SHARD_TOTAL" >&2
        exit 2
    fi
    
    NODEID_COUNT=$(echo "$SHARD_NODEIDS" | grep -c "^" || echo "0")
    
    echo "[unit-tests] mode=pytest"
    echo "[unit-tests] suite=tests/"
    echo "[unit-tests] shard_index=$SHARD_N"
    echo "[unit-tests] shard_count=$SHARD_TOTAL"
    echo "[unit-tests] nodeids=$NODEID_COUNT"
    echo "[unit-tests] command=\"python -m pytest @\$NODEID_FILE --durations=50 --durations-min=0.25\""
fi

# Build pytest extra args array (safer than string concatenation for paths with spaces)
PYTEST_EXTRA_ARGS=()
if [[ -n "$JUNIT_XML" ]]; then
    mkdir -p "$(dirname "$JUNIT_XML")"
    PYTEST_EXTRA_ARGS+=("--junitxml=$JUNIT_XML")
fi

# Build pytest command
if [[ "$PROFILE_MODE" == true || "$SHARD_MODE" == true ]]; then
    # Profile or shard mode: use pytest with durations reporting
    if [[ -n "$SHARD_NODEIDS" ]]; then
        # Write nodeids to a file for pytest @file syntax (pytest >= 8.2)
        NODEID_FILE="$TIMING_DIR/${RUN_TIMESTAMP}-shard-${SHARD_N}-nodeids.txt"
        echo "$SHARD_NODEIDS" > "$NODEID_FILE"
        
        if [[ ! -s "$NODEID_FILE" ]]; then
            echo "ERROR: shard $SHARD_N/$SHARD_TOTAL produced no nodeids" >&2
            exit 2
        fi
        
        "$PYTHON" -m pytest @"$NODEID_FILE" \
            "${PYTEST_EXTRA_ARGS[@]}" --durations=50 --durations-min=0.25 -v --tb=short 2>&1 | tee "$TIMING_LOG"
    else
        echo "[unit-tests] mode=pytest"
        echo "[unit-tests] suite=tests/"
        "$PYTHON" -m pytest tests/ \
            "${PYTEST_EXTRA_ARGS[@]}" --durations=50 --durations-min=0.25 -v --tb=short 2>&1 | tee "$TIMING_LOG"
    fi
    PYTEST_EXIT=$?
    
    # Extract timing data from pytest output (profile mode only)
    if [[ "$PROFILE_MODE" == true ]]; then
        "$PYTHON" -c "
import json
import re

timings = []
with open('$TIMING_LOG', 'r') as f:
    in_durations = False
    for line in f:
        if 'slowest' in line.lower() and 'durations' in line.lower():
            in_durations = True
            continue
        if in_durations:
            match = re.match(r'([\d.]+)s\s+call\s+(.+)', line.strip())
            if match:
                duration = float(match.group(1))
                test_id = match.group(2).strip()
                timings.append({'nodeid': test_id, 'duration_s': duration})
            elif line.strip() == '' or '=' in line:
                in_durations = False

with open('$TIMING_FILE', 'w') as f:
    json.dump({'timings': timings, 'mode': 'profile'}, f, indent=2)
"
    fi
    
    exit $PYTEST_EXIT
else
    # Standard mode: run all tests with documented exclusion policy
    # NOTE: Uses same exclusions as sharded mode to maintain consistency.
    # The two excluded files have import errors and cannot be collected.
    echo "[unit-tests] mode=pytest"
    echo "[unit-tests] suite=tests/"
    echo "[unit-tests] exclusions=tests/test_rollout_classifier_extended.py,tests/unit/test_property_checks.py"
    "$PYTHON" -m pytest tests/ \
        --ignore=tests/test_rollout_classifier_extended.py \
        --ignore=tests/unit/test_property_checks.py \
        --tb=short 2>&1 | tee "$TIMING_LOG"
    exit $?
fi
