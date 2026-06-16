#!/usr/bin/env bash
# Run unit tests with timing instrumentation.
# Outputs per-file timing to support profiling and sharding decisions.
#
# Usage:
#   scripts/run_unit_tests.sh              # standard run (pytest tests/)
#   scripts/run_unit_tests.sh --profile    # with per-test timing
#   scripts/run_unit_tests.sh --shard N K  # run shard N of K (0-indexed)
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

# Parse arguments
PROFILE_MODE=false
SHARD_MODE=false
VERIFY_MODE=false
LIST_FILES_MODE=false
SHARD_N=0
SHARD_TOTAL=1
VERIFY_TOTAL=0

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
        -h|--help)
            echo "Usage: $0 [--profile] [--shard N K] [--verify-shards K] [--list-files]"
            echo "  --profile           Enable pytest --durations profiling"
            echo "  --shard N K         Run shard N of K parallel shards (0-indexed)"
            echo "  --verify-shards K   Verify K-way shard partition correctness"
            echo "  --list-files        List all test files (or shard files if combined with --shard)"
            echo ""
            echo "Examples:"
            echo "  $0                          # Run all tests"
            echo "  $0 --profile                # Run with profiling"
            echo "  $0 --shard 0 2              # Run first half of files"
            echo "  $0 --shard 1 2              # Run second half of files"
            echo "  $0 --verify-shards 2        # Verify 2-way sharding is correct"
            echo "  $0 --shard 0 2 --list-files # List files in shard 0 of 2"
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

# Function to get all test files (deterministic order)
_get_all_test_files() {
    # Use pytest collection for accurate test file discovery
    # This captures all test files under tests/ including unittest-style files
    "$PYTHON" -m pytest --collect-only -q tests/ 2>/dev/null | \
        grep "^tests/" | \
        sed 's/::.*//' | \
        sort -u
}

# Function to get files for a specific shard using deterministic contiguous chunks
_get_shard_files() {
    local shard_index=$1
    local shard_count=$2
    
    local all_files=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && all_files+=("$line")
    done < <(_get_all_test_files)
    
    local total_files=${#all_files[@]}
    local files_per_shard=$(( (total_files + shard_count - 1) / shard_count ))
    local start_idx=$(( shard_index * files_per_shard ))
    local end_idx=$(( start_idx + files_per_shard - 1 ))
    [[ $end_idx -ge $total_files ]] && end_idx=$(( total_files - 1 ))
    
    # Output files for this shard in original order
    for i in $(seq 0 $((total_files - 1))); do
        if [[ $i -ge $start_idx && $i -le $end_idx ]]; then
            echo "${all_files[$i]}"
        fi
    done
}

# Function to list all files or shard files
_list_files() {
    if [[ "$SHARD_MODE" == true ]]; then
        _get_shard_files "$SHARD_N" "$SHARD_TOTAL"
    else
        _get_all_test_files
    fi
}

# Handle list-files mode
if [[ "$LIST_FILES_MODE" == true ]]; then
    _list_files
    exit 0
fi

# Handle verify-shards mode
if [[ "$VERIFY_MODE" == true ]]; then
    echo "=== Verifying ${VERIFY_TOTAL}-way shard partition ==="
    
    # Collect all files using Python for reliable array handling
    "$PYTHON" -c "
import subprocess
import sys

# Get all test files
result = subprocess.run(
    ['$PYTHON', '-m', 'pytest', '--collect-only', '-q', 'tests/'],
    capture_output=True, text=True
)

all_files = set()
for line in result.stdout.splitlines():
    if line.startswith('tests/'):
        # Extract file path (before ::)
        file_path = line.split('::')[0]
        all_files.add(file_path)

all_files = sorted(all_files)
total_files = len(all_files)
print(f'Total test files: {total_files}', file=sys.stderr)

# Verify each shard
all_shard_files = []
for shard_idx in range($VERIFY_TOTAL):
    files_per_shard = (total_files + $VERIFY_TOTAL - 1) // $VERIFY_TOTAL
    start_idx = shard_idx * files_per_shard
    end_idx = min(start_idx + files_per_shard - 1, total_files - 1)
    
    shard_files = all_files[start_idx:end_idx+1] if start_idx < total_files else []
    count = len(shard_files)
    print(f'Shard {shard_idx}/{$VERIFY_TOTAL}: {count} files', file=sys.stderr)
    
    # Check for empty shard
    if count == 0 and total_files >= $VERIFY_TOTAL:
        print('  WARNING: Empty shard (may indicate uneven distribution)', file=sys.stderr)
    
    all_shard_files.extend(shard_files)

print('', file=sys.stderr)

# Check for missing files
missing = 0
for f in all_files:
    if f not in all_shard_files:
        print(f'ERROR: File missing from all shards: {f}', file=sys.stderr)
        missing += 1

# Check for duplicates
seen = set()
duplicates = 0
for f in sorted(all_shard_files):
    if f in seen:
        print(f'ERROR: Duplicate file across shards: {f}', file=sys.stderr)
        duplicates += 1
    else:
        seen.add(f)

print('', file=sys.stderr)
print('=== Verification Results ===', file=sys.stderr)
print(f'Total files: {total_files}', file=sys.stderr)
print(f'Files in shards: {len(all_shard_files)}', file=sys.stderr)
print(f'Missing files: {missing}', file=sys.stderr)
print(f'Duplicate files: {duplicates}', file=sys.stderr)

errors = missing + duplicates
if errors == 0:
    print('', file=sys.stderr)
    print('VERIFICATION PASSED: All files appear in exactly one shard.', file=sys.stderr)
    sys.exit(0)
else:
    print('', file=sys.stderr)
    print(f'VERIFICATION FAILED: {errors} error(s) found.', file=sys.stderr)
    sys.exit(1)
"
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

# Collect test files if sharding
SHARD_FILES=""
if [[ "$SHARD_MODE" == true ]]; then
    # Get files for this shard using Python for reliable array handling
    SHARD_FILES=$("$PYTHON" -c "
import subprocess
import sys

# Get all test files
result = subprocess.run(
    ['$PYTHON', '-m', 'pytest', '--collect-only', '-q', 'tests/'],
    capture_output=True, text=True
)

all_files = set()
for line in result.stdout.splitlines():
    if line.startswith('tests/'):
        file_path = line.split('::')[0]
        all_files.add(file_path)

all_files = sorted(all_files)
total_files = len(all_files)

# Calculate shard range
files_per_shard = (total_files + $SHARD_TOTAL - 1) // $SHARD_TOTAL
start_idx = $SHARD_N * files_per_shard
end_idx = min(start_idx + files_per_shard - 1, total_files - 1)

# Output files for this shard
if start_idx < total_files:
    for f in all_files[start_idx:end_idx+1]:
        print(f, end=' ')
" 2>/dev/null)
    
    echo "[unit-tests] mode=pytest"
    echo "[unit-tests] suite=tests/"
    echo "[unit-tests] shard_index=$SHARD_N"
    echo "[unit-tests] shard_count=$SHARD_TOTAL"
    echo "[unit-tests] files=$("$PYTHON" -c "
files = '$SHARD_FILES'.split()
print(len([f for f in files if f]))
" 2>/dev/null)"
    echo "[unit-tests] command=\"python -m pytest $SHARD_FILES\""
fi

# Build pytest command
if [[ "$PROFILE_MODE" == true ]]; then
    # Profile mode: use pytest with durations
    if [[ "$SHARD_MODE" == true ]]; then
        "$PYTHON" -m pytest $SHARD_FILES --durations=100 -v --tb=short 2>&1 | tee "$TIMING_LOG"
    else
        echo "[unit-tests] mode=pytest"
        echo "[unit-tests] suite=tests/"
        "$PYTHON" -m pytest tests/ --durations=100 -v --tb=short 2>&1 | tee "$TIMING_LOG"
    fi
    PYTEST_EXIT=$?
    
    # Extract timing data from pytest output
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
    # Standard mode: use pytest tests/ for complete coverage
    if [[ "$SHARD_MODE" == true && -n "$SHARD_FILES" ]]; then
        "$PYTHON" -m pytest $SHARD_FILES --tb=short 2>&1 | tee "$TIMING_LOG"
    else
        echo "[unit-tests] mode=pytest"
        echo "[unit-tests] suite=tests/"
        "$PYTHON" -m pytest tests/ --tb=short 2>&1 | tee "$TIMING_LOG"
    fi
    exit $?
fi
