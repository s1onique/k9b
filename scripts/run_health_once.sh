#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
SRC_PATH="$ROOT/src"
export PYTHONPATH="$SRC_PATH${PYTHONPATH:+:$PYTHONPATH}"

CONFIG_PATH="runs/health-config.local.json"
RUNS_DIR_OVERRIDE=""
GENERATE_DIGEST=0
DIGEST_OUTPUT=""
DIGEST_TARGET="none"

echo "Operator quick-run steps: inspect config → run health loop → summarize artifacts → optional digest."

usage() {
  cat <<'EOF'
Usage: run_health_once.sh [options]

Options:
  --config PATH       Health config JSON (default: runs/health-config.local.json)
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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG_PATH="$2"
      shift 2
      ;;
    --runs-dir)
      RUNS_DIR_OVERRIDE="$2"
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

if [[ -n "$RUNS_DIR_OVERRIDE" ]]; then
  RUNS_DIR="$RUNS_DIR_OVERRIDE"
else
  RUNS_DIR="$(resolve_runs_dir "$CONFIG_PATH")"
fi

echo "Inspecting health config: $CONFIG_PATH"
if "$PYTHON" "$ROOT/scripts/inspect_health_config.py" "$CONFIG_PATH"; then
  echo "Config inspection result: PASS"
else
  echo "Config inspection failed; aborting health run." >&2
  exit 1
fi

echo "Running one-shot health loop"
if "$PYTHON" -m k8s_diag_agent.cli run-health-loop --config "$CONFIG_PATH" --once; then
  echo "Health run result: PASS (exit 0)"
else
  exit_code=$?
  echo "Health run result: FAIL (exit $exit_code)" >&2
  echo "Skipping summary because the health run failed." >&2
  exit "$exit_code"
fi

SUMMARY_OUTPUT="$RUNS_DIR/health-summary.txt"
echo "Summarizing artifacts to $SUMMARY_OUTPUT"
if "$PYTHON" -m k8s_diag_agent.cli health-summary --runs-dir "$RUNS_DIR" > "$SUMMARY_OUTPUT"; then
  cat "$SUMMARY_OUTPUT"
  echo "Health summary written to $SUMMARY_OUTPUT"
else
  echo "Health summary failed; inspect $RUNS_DIR for artifacts." >&2
  exit 1
fi

if is_truthy "$BUILD_DIAGNOSTIC_PACK"; then
  echo "Building diagnostic pack for latest run"
  UI_INDEX_PATH="$RUNS_DIR/ui-index.json"
  if [[ ! -f "$UI_INDEX_PATH" ]]; then
    echo "UI index missing; cannot determine run_id" >&2
  else
    RUN_ID="$($PYTHON - <<'PY'
import json
from pathlib import Path

path = Path("$UI_INDEX_PATH")
data = json.loads(path.read_text(encoding="utf-8"))
run_entry = data.get("run", {})
run_id = run_entry.get("run_id")
print(run_id or "")
PY
)"
    if [[ -n "$RUN_ID" ]]; then
      "$PYTHON" "$ROOT/scripts/build_diagnostic_pack.py" --run-id "$RUN_ID" --runs-dir "$RUNS_DIR"
      if ! "$PYTHON" "$ROOT/scripts/update_ui_index.py" --runs-dir "$RUNS_DIR" --run-id "$RUN_ID"; then
        echo "Warning: unable to refresh UI index after pack creation" >&2
      fi
    else
      echo "Unable to read run_id from UI index" >&2
    fi
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
