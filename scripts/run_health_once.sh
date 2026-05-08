#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${HEALTH_PYTHON_BIN:-$ROOT/.venv/bin/python}"
SRC_PATH="$ROOT/src"
export PYTHONPATH="$SRC_PATH${PYTHONPATH:+:$PYTHONPATH}"

# Environment-resolved paths for Kubernetes scheduler runtime.
# Defaults mirror the values.yaml defaults for local dev when env vars are unset.
CONFIG_PATH="${HEALTH_CONFIG_PATH:-runs/health-config.local.json}"
RUNS_DIR="${HEALTH_RUNS_DIR:-}"

GENERATE_DIGEST=0
DIGEST_OUTPUT=""
DIGEST_TARGET="none"

echo "Operator quick-run steps: inspect config → run health loop → summarize artifacts → optional digest."

usage() {
  cat <<'EOF'
Usage: run_health_once.sh [options]

Options:
  --config PATH       Health config JSON (default: from HEALTH_CONFIG_PATH env or runs/health-config.local.json)
  --runs-dir PATH     Explicit run artifacts directory (defaults to <output_dir>/health from the config)
  --digest            Emit a markdown digest (stdout)
  --digest-output PATH
                      Emit a digest and write it to the provided file
  -h, --help          Show this help
EOF
}

resolve_runs_dir() {
  "$PYTHON" - "$1" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
output_dir = "runs"
try:
    raw = json.loads(path.read_text(encoding="utf-8"))
    output_dir = raw.get("output_dir") or output_dir
except (OSError, json.JSONDecodeError):
    pass
print(os.path.join(output_dir, "health"))
PY
}

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|y|Y)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

BUILD_DIAGNOSTIC_PACK="${HEALTH_BUILD_DIAGNOSTIC_PACK:-0}"
HEALTH_REQUIRE_SUMMARY="${HEALTH_REQUIRE_SUMMARY:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG_PATH="$2"
      shift 2
      ;;
    --runs-dir)
      RUNS_DIR="$2"
      shift 2
      ;;
    --digest)
      GENERATE_DIGEST=1
      shift
      ;;
    --digest-output)
      GENERATE_DIGEST=1
      DIGEST_OUTPUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

# Resolve RUNS_DIR: env override > explicit arg > config-derived default.
if [[ -z "$RUNS_DIR" ]]; then
  RUNS_DIR="$(resolve_runs_dir "$CONFIG_PATH")"
fi
RUNS_BASE_DIR="$(dirname "$RUNS_DIR")"

# Ensure the health runs directory exists before writing artifacts.
# This handles fresh PVC scenarios where the subdirectory may not exist yet.
echo "Ensuring runs directory exists: $RUNS_DIR"
if ! mkdir -p "$RUNS_DIR"; then
  echo "Failed to create runs directory: $RUNS_DIR" >&2
  exit 1
fi

echo "Inspecting health config: $CONFIG_PATH"
if ! "$PYTHON" "$ROOT/scripts/inspect_health_config.py" "$CONFIG_PATH"; then
  echo "Config inspection failed; aborting health run." >&2
  exit 1
fi
echo "Config inspection result: PASS"

# Execute the canonical health loop before summary.
# Uses --once so it runs a single iteration and exits (one-shot scheduler pattern).
echo "Running health loop with config: $CONFIG_PATH"
export HEALTH_RUNS_DIR="$RUNS_DIR"
if ! "$PYTHON" -m k8s_diag_agent.cli run-health-loop --config "$CONFIG_PATH" --once; then
  echo "Health loop failed; aborting." >&2
  exit 1
fi
echo "Health loop completed"

SUMMARY_OUTPUT="$RUNS_DIR/health-summary.txt"
echo "Summarizing artifacts to $SUMMARY_OUTPUT"

# Capture summary output and exit code.
_summary_exit=0
if ! "$PYTHON" -m k8s_diag_agent.cli health-summary --runs-dir "$RUNS_DIR" > "$SUMMARY_OUTPUT" 2>&1; then
  _summary_stdout=$(cat "$SUMMARY_OUTPUT" 2>/dev/null || echo "")
  if echo "$_summary_stdout" | grep -q "Unable to discover any health runs"; then
    echo "WARNING: Health summary found no runs (empty PVC or fresh start)." >&2
    echo "This is expected on first scheduler startup." >&2
    if is_truthy "$HEALTH_REQUIRE_SUMMARY"; then
      echo "HEALTH_REQUIRE_SUMMARY=true; exiting non-zero due to no-runs summary." >&2
      echo "Summary output:" >&2
      cat "$SUMMARY_OUTPUT" >&2
      exit 1
    fi
    echo "Continuing anyway (HEALTH_REQUIRE_SUMMARY=false)."
    # Write a minimal placeholder so downstream tooling sees a file.
    echo "# No health runs found at $(date -Iseconds)" > "$SUMMARY_OUTPUT"
    echo "# This is expected on fresh PVC / first scheduler startup." >> "$SUMMARY_OUTPUT"
  else
    echo "Health summary failed; inspect $RUNS_DIR for artifacts." >&2
    echo "Summary output:" >&2
    cat "$SUMMARY_OUTPUT" >&2
    exit 1
  fi
fi

cat "$SUMMARY_OUTPUT"
echo "Health summary written to $SUMMARY_OUTPUT"

if is_truthy "$BUILD_DIAGNOSTIC_PACK"; then
  echo "Building diagnostic pack for latest run"
  HEALTH_REQUIRE_DIAGNOSTIC_PACK="${HEALTH_REQUIRE_DIAGNOSTIC_PACK:-false}"
  UI_INDEX_PATH="${RUNS_DIR%/}/ui-index.json"
  export UI_INDEX_PATH
  RUN_ID=""
  if [[ -f "$UI_INDEX_PATH" ]]; then
    RUN_ID="$($PYTHON - <<'PY'
import json
import os
from pathlib import Path

ui_index_path = Path(os.environ["UI_INDEX_PATH"])
data = json.loads(ui_index_path.read_text(encoding="utf-8"))
run_entry = data.get("run", {})
run_id = run_entry.get("run_id")
print(run_id or "")
PY
    )"
  else
    echo "WARNING: UI index missing at $UI_INDEX_PATH; cannot determine run_id" >&2
  fi
  if [[ -n "$RUN_ID" ]]; then
    if "$PYTHON" "$ROOT/scripts/build_diagnostic_pack.py" --run-id "$RUN_ID" --runs-dir "$RUNS_BASE_DIR"; then
      if ! "$PYTHON" "$ROOT/scripts/update_ui_index.py" --runs-dir "$RUNS_BASE_DIR" --run-id "$RUN_ID"; then
        echo "Warning: unable to refresh UI index after pack creation" >&2
      fi
    else
      echo "ERROR: Diagnostic pack build failed for run_id=$RUN_ID" >&2
      if is_truthy "$HEALTH_REQUIRE_DIAGNOSTIC_PACK"; then
        echo "HEALTH_REQUIRE_DIAGNOSTIC_PACK=true; exiting non-zero due to pack build failure." >&2
        exit 1
      fi
      echo "Continuing anyway (HEALTH_REQUIRE_DIAGNOSTIC_PACK=false)."
    fi
  else
    echo "ERROR: Unable to read run_id from UI index" >&2
    if is_truthy "$HEALTH_REQUIRE_DIAGNOSTIC_PACK"; then
      echo "HEALTH_REQUIRE_DIAGNOSTIC_PACK=true; exiting non-zero due to missing run_id." >&2
      exit 1
    fi
    echo "Continuing anyway (HEALTH_REQUIRE_DIAGNOSTIC_PACK=false)."
  fi
fi

if [[ $GENERATE_DIGEST -eq 1 ]]; then
  DIGEST_TARGET="stdout"
  if [[ -n "$DIGEST_OUTPUT" ]]; then
    DIGEST_TARGET="$DIGEST_OUTPUT"
  fi
  echo "Generating health digest (${DIGEST_TARGET})"
  DIGEST_CMD=("$ROOT/scripts/make_health_digest.sh" --runs-dir "$RUNS_DIR" --config "$CONFIG_PATH")
  if [[ -n "$DIGEST_OUTPUT" ]]; then
    DIGEST_CMD+=(--output "$DIGEST_OUTPUT")
  fi
  "${DIGEST_CMD[@]}"
  if [[ -n "$DIGEST_OUTPUT" ]]; then
    echo "Digest written to $DIGEST_OUTPUT"
  else
    echo "Digest emitted to stdout"
  fi
fi

echo "Operator health snapshot complete (runs_dir=$RUNS_DIR, summary=$SUMMARY_OUTPUT, digest=$DIGEST_TARGET)"