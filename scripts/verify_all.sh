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
# Usage:
#   ./scripts/verify_all.sh                    # fast profile (local default)
#   ./scripts/verify_all.sh --fast             # explicit fast profile
#   ./scripts/verify_all.sh --full             # exhaustive merge-grade gate
#   ./scripts/verify_all.sh --json             # fast profile, JSON output
#   ./scripts/verify_all.sh --full --json      # full gate, JSON output
#
# Policy: Only --full may be called "full gate green".

set -uo pipefail

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

STEP_JSON_MODE=""
STEP_SCOPE="all"
STEP_PROFILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fast) STEP_PROFILE="fast"; shift ;;
        --full) STEP_PROFILE="full"; shift ;;
        --json)
            STEP_JSON_MODE=1
            export STEP_JSON_MODE
            shift
            ;;
        --python-only) STEP_SCOPE="python"; shift ;;
        --frontend-only) STEP_SCOPE="frontend"; shift ;;
        --helm-only) STEP_SCOPE="helm"; shift ;;
        -h|--help)
            cat <<'EOF'
Usage: ./scripts/verify_all.sh [--fast|--full] [--json] [--python-only|--frontend-only|--helm-only]

Profiles:
  --fast       Fast local profile (≤60s, policy + smoke checks) [DEFAULT]
  --full       Exhaustive merge-grade verification

Without --fast or --full, defaults to --fast for local development.

Output modes:
  --json       Emit only JSON summary to stdout
EOF
            exit 0
            ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# Default profile behavior
if [[ "$STEP_SCOPE" != "all" ]]; then
    STEP_PROFILE="full"  # Lane scope = full (legacy)
elif [[ -z "$STEP_PROFILE" ]]; then
    STEP_PROFILE="fast"  # Local default
fi

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Source step runner for state management
source "$SCRIPT_DIR/step_runner.sh"

# ---------------------------------------------------------------------------
# Recursion protection and locking
# ---------------------------------------------------------------------------

if [[ -n "${VERIFY_ALL_ACTIVE:-}" ]]; then
    echo "ERROR: verify_all.sh recursion detected." >&2
    exit 2
fi
export VERIFY_ALL_ACTIVE=1

_LOCK_DIR="$REPO_ROOT/.verify_lock"
mkdir -p "$_LOCK_DIR" 2>/dev/null || { echo "ERROR: Cannot create lock dir." >&2; exit 3; }
if ! mkdir "$_LOCK_DIR/lock" 2>/dev/null; then
    echo "ERROR: Another verification run is active." >&2
    exit 4
fi
trap 'rm -rf "$_LOCK_DIR" 2>/dev/null' EXIT

mkdir -p "$REPO_ROOT/runs/verification"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: Python not available at $PYTHON" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Load execution plan from Python
# ---------------------------------------------------------------------------

PLAN_FILE=$(mktemp "${REPO_ROOT}/.verify_plan_XXXXXX.json")

"$PYTHON" -c "
import sys
import json
sys.path.insert(0, '$SCRIPT_DIR')
from verify_profile_plan import emit_full_plan

plan = emit_full_plan('$STEP_PROFILE', '$STEP_SCOPE')
print(json.dumps(plan))
" > "$PLAN_FILE" 2>&1

if [[ $? -ne 0 ]]; then
    echo "ERROR: Failed to load profile plan" >&2
    cat "$PLAN_FILE" 2>/dev/null
    rm -f "$PLAN_FILE"
    exit 1
fi

# Parse plan metadata
VERIFY_PROFILE=$("$PYTHON" -c "
import json
with open('$PLAN_FILE') as f:
    print(json.load(f)['profile'])
")

IS_FULL_GATE=$("$PYTHON" -c "
import json
with open('$PLAN_FILE') as f:
    print('true' if json.load(f)['is_full_gate'] else 'false')
")

STEP_COUNT=$("$PYTHON" -c "
import json
with open('$PLAN_FILE') as f:
    print(json.load(f)['step_count'])
")

SKIPPED_JSON=$("$PYTHON" -c "
import json
with open('$PLAN_FILE') as f:
    print(json.dumps(json.load(f)['skipped']))
")

# Initialize lane state with valid JSON
"$PYTHON" -c "print('{\"python\": [], \"frontend\": [], \"helm\": []}')" > "$REPO_ROOT/runs/verification/${_RUN_TIMESTAMP}-lane-state.json"

# ---------------------------------------------------------------------------
# Run lanes via Python runner
# ---------------------------------------------------------------------------

case "$STEP_SCOPE" in
    all)
        "$PYTHON" "$SCRIPT_DIR/verify_profile_runner.py" "python" "$PLAN_FILE" &
        "$PYTHON" "$SCRIPT_DIR/verify_profile_runner.py" "frontend" "$PLAN_FILE" &
        "$PYTHON" "$SCRIPT_DIR/verify_profile_runner.py" "helm" "$PLAN_FILE" &
        wait
        ;;
    python)
        "$PYTHON" "$SCRIPT_DIR/verify_profile_runner.py" "python" "$PLAN_FILE"
        ;;
    frontend)
        "$PYTHON" "$SCRIPT_DIR/verify_profile_runner.py" "frontend" "$PLAN_FILE"
        ;;
    helm)
        "$PYTHON" "$SCRIPT_DIR/verify_profile_runner.py" "helm" "$PLAN_FILE"
        ;;
esac

# ---------------------------------------------------------------------------
# Emit timings
# ---------------------------------------------------------------------------

if [[ -z "${STEP_JSON_MODE:-}" ]]; then
    "$PYTHON" -c "
import json

state_file = '$REPO_ROOT/runs/verification/${_RUN_TIMESTAMP}-lane-state.json'
timings_file = '$REPO_ROOT/.gate-timings.json'

try:
    with open(state_file) as f:
        state = json.load(f)
except:
    state = {'python': [], 'frontend': [], 'helm': []}

timings = []
for lane in ['python', 'frontend', 'helm']:
    for step in state.get(lane, []):
        timings.append({
            'id': step['id'],
            'lane': lane,
            'exit_code': step['exit_code'],
            'duration_ms': step['duration_ms'],
        })

timings.sort(key=lambda x: x['duration_ms'], reverse=True)
total = sum(t['duration_ms'] for t in timings)

print()
print('=== Gate Timing Summary ===')
print(f'Total steps: {len(timings)}')
print(f'Total time: {total}ms ({total/1000:.1f}s)')
print()
print(f\"{'Step':<35} {'Duration':>10} {'Lane':<10} {'Exit':>5}\")
print('-' * 65)
for step in timings[:10]:
    dur = f\"{step['duration_ms']}ms\"
    if step['duration_ms'] >= 1000:
        dur = f\"{step['duration_ms']/1000:.1f}s\"
    print(f\"{step['id']:<35} {dur:>10} {step['lane']:<10} {step['exit_code']:>5}\")

with open(timings_file, 'w') as f:
    json.dump({'steps': timings, 'total_ms': total}, f)
" 2>/dev/null
fi

# ---------------------------------------------------------------------------
# Finalize
# ---------------------------------------------------------------------------

final_exit=0
failed_count=0

if [[ -f "$REPO_ROOT/runs/verification/${_RUN_TIMESTAMP}-lane-state.json" ]]; then
    failed_count=$("$PYTHON" -c "
import json
try:
    with open('$REPO_ROOT/runs/verification/${_RUN_TIMESTAMP}-lane-state.json') as f:
        state = json.load(f)
    print(sum(1 for s in state['python'] + state['frontend'] + state.get('helm', []) if s['status'] == 'FAIL'))
except:
    print(0)
" 2>/dev/null)
    if [[ "$failed_count" -gt 0 ]]; then
        final_exit=1
    fi
fi

# Print profile footer
if [[ -z "${STEP_JSON_MODE:-}" ]]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "VERIFICATION PROFILE: ${VERIFY_PROFILE}"
    echo "═══════════════════════════════════════════════════════════"
    echo "Profile: ${VERIFY_PROFILE}"
    echo "Steps: ${STEP_COUNT}"
    
    if [[ "$IS_FULL_GATE" != "true" ]]; then
        echo ""
        echo "Skipped (${VERIFY_PROFILE} profile excludes expensive suites):"
        "$PYTHON" -c "
import json
skipped = json.loads('$SKIPPED_JSON')
for s in skipped:
    print(f\"  - {s['id']} ({s['reason']})\")
" 2>/dev/null
        echo ""
        echo "For merge-grade verification:"
        echo "  ./scripts/verify_all.sh --full"
    fi
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    if [[ "$final_exit" == "0" ]]; then
        echo "VERIFICATION GATE [${VERIFY_PROFILE}]: PASSED"
    else
        echo "VERIFICATION GATE [${VERIFY_PROFILE}]: FAILED" >&2
    fi
fi

# Cleanup
rm -f "$PLAN_FILE"

step_finalize $final_exit
