#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
SRC_PATH="$ROOT/src"
export PYTHONPATH="$SRC_PATH${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Error: .venv python interpreter not found at $PYTHON" >&2
  exit 1
fi

# Returns the parent runs directory (canonical contract).
# The health loop internally uses runs/health/ subdirectory.
resolve_runs_dir() {
  "$PYTHON" - "$1" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
output_dir = "runs"  # Canonical: parent runs directory
try:
    raw = json.loads(path.read_text(encoding="utf-8"))
    configured = raw.get("output_dir")
    if configured:
        # If user configured output_dir as runs/health, normalize to parent runs
        configured_path = Path(configured)
        if configured_path.name == "health":
            output_dir = str(configured_path.parent)
        else:
            output_dir = configured
except (OSError, json.JSONDecodeError):
    pass
print(output_dir)
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

CONFIG_PATH="${HEALTH_CONFIG_PATH:-runs/health-config.local.json}"
RUNS_DIR="${HEALTH_RUNS_DIR:-}"
if [[ -z "$RUNS_DIR" ]]; then
  RUNS_DIR="$(resolve_runs_dir "$CONFIG_PATH")"
fi

UI_RUNS_DIR="${HEALTH_UI_RUNS_DIR:-$RUNS_DIR}"
UI_HOST="${HEALTH_UI_HOST:-127.0.0.1}"
UI_PORT="${HEALTH_UI_PORT:-8080}"

SKIP_REFRESH="${HEALTH_SKIP_REFRESH:-0}"
RUN_DIGEST="${HEALTH_RUN_DIGEST:-0}"
DIGEST_OUTPUT="${HEALTH_DIGEST_OUTPUT:-}"
BUILD_DIAGNOSTIC_PACK="${HEALTH_BUILD_DIAGNOSTIC_PACK:-0}"

export HEALTH_BUILD_DIAGNOSTIC_PACK="$BUILD_DIAGNOSTIC_PACK"
if ! is_truthy "$SKIP_REFRESH"; then
  run_cmd=("$ROOT/scripts/run_health_once.sh" --config "$CONFIG_PATH" --runs-dir "$RUNS_DIR")
  if is_truthy "$RUN_DIGEST"; then
    run_cmd+=(--digest)
  fi
  if [[ -n "$DIGEST_OUTPUT" ]]; then
    run_cmd+=(--digest-output "$DIGEST_OUTPUT")
  fi
  echo "Running health snapshot before launching UI (config=$CONFIG_PATH, runs_dir=$RUNS_DIR)"
  "${run_cmd[@]}"
  echo "Health snapshot complete"
else
  echo "Skipping health refresh (refresh-less backend mode; using artifacts in $RUNS_DIR)"
fi

echo "Starting health UI on $UI_HOST:$UI_PORT watching $UI_RUNS_DIR"
exec "$PYTHON" -m k8s_diag_agent.cli health-ui --runs-dir "$UI_RUNS_DIR" --host "$UI_HOST" --port "$UI_PORT"
