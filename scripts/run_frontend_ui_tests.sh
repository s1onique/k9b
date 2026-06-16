#!/usr/bin/env bash
# Run frontend UI tests with timing instrumentation.
# Outputs per-file timing to support profiling and sharding decisions.
#
# Usage:
#   scripts/run_frontend_ui_tests.sh              # standard run (npm test:ui)
#   scripts/run_frontend_ui_tests.sh --profile    # with verbose output and file timings
#   scripts/run_frontend_ui_tests.sh --shard N K  # run shard N of K parallel shards (0-indexed)
#
# Exit codes:
#   0 - all tests passed
#   1 - tests failed
#   2 - invalid arguments

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"
PYTHON="${PYTHON:-python3}"

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
            echo "  --profile   Enable verbose reporter for per-test timing"
            echo "  --shard N K Run shard N of K parallel shards (0-indexed)"
            echo ""
            echo "Examples:"
            echo "  $0                    # Run all tests"
            echo "  $0 --profile         # Run with verbose output"
            echo "  $0 --shard 0 2       # Run first half of test files"
            echo "  $0 --shard 1 2       # Run second half of test files"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

# Check mutually exclusive modes
if [[ "$PROFILE_MODE" == true && "$SHARD_MODE" == true ]]; then
    echo "ERROR: --profile and --shard are not supported together yet" >&2
    exit 2
fi

# Check frontend directory exists
if [[ ! -d "$FRONTEND_DIR" ]]; then
    echo "ERROR: Frontend directory not found at $FRONTEND_DIR" >&2
    exit 2
fi

# Check npm availability
if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm is not installed or not on PATH" >&2
    exit 2
fi

# Create timing output directory
TIMING_DIR="$REPO_ROOT/runs/verification/frontend-test-timings"
mkdir -p "$TIMING_DIR"

# Timing file for this run
RUN_TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
TIMING_FILE="$TIMING_DIR/${RUN_TIMESTAMP}-timing.json"
TIMING_LOG="$TIMING_DIR/${RUN_TIMESTAMP}-timing.log"

cd "$FRONTEND_DIR"

# Collect test files if sharding
if [[ "$SHARD_MODE" == true ]]; then
    # Get all test files using vitest --list
    TEST_FILES=$(npx vitest --list 2>/dev/null | grep "^src/" | sed 's/::.*//' | sort -u)
    
    # Convert to array
    TEST_FILE_ARRAY=()
    while IFS= read -r test_file; do
        [[ -n "$test_file" ]] && TEST_FILE_ARRAY+=("$test_file")
    done <<< "$TEST_FILES"
    
    TOTAL_FILES=${#TEST_FILE_ARRAY[@]}
    
    if (( TOTAL_FILES == 0 )); then
        echo "ERROR: No test files found" >&2
        exit 2
    fi
    
    # Calculate file ranges for this shard
    FILES_PER_SHARD=$(( (TOTAL_FILES + SHARD_TOTAL - 1) / SHARD_TOTAL ))
    START_IDX=$(( SHARD_N * FILES_PER_SHARD ))
    END_IDX=$(( START_IDX + FILES_PER_SHARD - 1 ))
    [[ $END_IDX -ge $TOTAL_FILES ]] && END_IDX=$(( TOTAL_FILES - 1 ))
    
    # Extract files for this shard
    SHARD_FILES_ARRAY=()
    for i in $(seq 0 $((TOTAL_FILES - 1))); do
        if [[ $i -ge $START_IDX && $i -le $END_IDX ]]; then
            SHARD_FILES_ARRAY+=("${TEST_FILE_ARRAY[$i]}")
        fi
    done
    
    echo "Running shard $SHARD_N of $SHARD_TOTAL ($(( END_IDX - START_IDX + 1 )) files of $TOTAL_FILES total)"
fi

# Build the vitest command
if [[ "$PROFILE_MODE" == true ]]; then
    # Profile mode: verbose output
    echo "=== Frontend UI Test Profile Mode ===" | tee "$TIMING_LOG"
    echo "Timestamp: $("$PYTHON" -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())')" | tee -a "$TIMING_LOG"
    echo "" | tee -a "$TIMING_LOG"
    
    START_MS=$("$PYTHON" -c 'import time; print(int(time.time() * 1000))')
    npm run test:ui -- --reporter=verbose 2>&1 | tee -a "$TIMING_LOG"
    TEST_EXIT=$?
    END_MS=$("$PYTHON" -c 'import time; print(int(time.time() * 1000))')
    
    # Calculate duration in milliseconds
    DURATION_MS=$((END_MS - START_MS))
    
    # Extract file-level timings from verbose output
    # Parse output to find per-file test counts and durations
    "$PYTHON" -c "
import json
import re
from datetime import datetime

timings = []

with open('$TIMING_LOG', 'r') as f:
    for line in f:
        # Match lines like: '✓ src/utils/__tests__/selectors.test.ts > ...'
        match = re.match(r'^\s*[✓✗]\s+(\S+)\s+>\s+.*\((\d+)\s+tests?\)\s+(\d+ms)', line)
        if match:
            file_path = match.group(1)
            test_info = match.group(2)
            duration = match.group(3)
            timings.append({
                'file': file_path,
                'test_count': int(re.search(r'(\d+)', test_info).group(1)),
                'duration_ms': int(re.search(r'(\d+)', duration).group(1))
            })

with open('$TIMING_FILE', 'w') as f:
    json.dump({
        'timestamp': datetime.now().isoformat(),
        'mode': 'profile',
        'duration_ms': $DURATION_MS,
        'exit_code': $TEST_EXIT,
        'file_timings': sorted(timings, key=lambda x: x['duration_ms'], reverse=True)
    }, f, indent=2)

print(f'Written timing data to $TIMING_FILE')
print(f'Total files: {len(timings)}')
"
    
    exit $TEST_EXIT
    
elif [[ "$SHARD_MODE" == true ]]; then
    # Shard mode: run specific test files
    echo "=== Frontend UI Test Shard Mode ===" | tee "$TIMING_LOG"
    echo "Shard: $SHARD_N / $SHARD_TOTAL" | tee -a "$TIMING_LOG"
    echo "Files: ${SHARD_FILES_ARRAY[*]}" | tee -a "$TIMING_LOG"
    echo "" | tee -a "$TIMING_LOG"
    
    START_MS=$("$PYTHON" -c 'import time; print(int(time.time() * 1000))')
    npx vitest run "${SHARD_FILES_ARRAY[@]}" --reporter=verbose 2>&1 | tee -a "$TIMING_LOG"
    TEST_EXIT=$?
    END_MS=$("$PYTHON" -c 'import time; print(int(time.time() * 1000))')
    
    DURATION_MS=$((END_MS - START_MS))
    
    echo "" | tee -a "$TIMING_LOG"
    echo "Shard completed in ${DURATION_MS}ms" | tee -a "$TIMING_LOG"
    
    exit $TEST_EXIT
    
else
    # Standard mode: just run tests
    echo "=== Running Frontend UI Tests ==="
    START_MS=$("$PYTHON" -c 'import time; print(int(time.time() * 1000))')
    npm run test:ui 2>&1
    TEST_EXIT=$?
    END_MS=$("$PYTHON" -c 'import time; print(int(time.time() * 1000))')
    
    DURATION_MS=$((END_MS - START_MS))
    echo ""
    echo "Duration: ${DURATION_MS}ms"
    
    exit $TEST_EXIT
fi
