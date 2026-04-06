#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
SRC_PATH="$ROOT/src"
export PYTHONPATH="$SRC_PATH:$PYTHONPATH"

CONFIG_PATH="runs/health-config.local.json"
RUNS_DIR_OVERRIDE=""
GENERATE_DIGEST=0
DIGEST_OUTPUT=""

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
"$PYTHON" "$ROOT/scripts/inspect_health_config.py" "$CONFIG_PATH"

echo "Running one-shot health loop"
"$PYTHON" -m k8s_diag_agent.cli run-health-loop --config "$CONFIG_PATH" --once

echo "Summarizing artifacts in $RUNS_DIR"
"$PYTHON" -m k8s_diag_agent.cli health-summary --runs-dir "$RUNS_DIR"

if [[ $GENERATE_DIGEST -eq 1 ]]; then
  echo "Generating health digest"
  DIGEST_CMD=("$ROOT/scripts/make_health_digest.sh" --runs-dir "$RUNS_DIR" --config "$CONFIG_PATH")
  if [[ -n "$DIGEST_OUTPUT" ]]; then
    DIGEST_CMD+=(--output "$DIGEST_OUTPUT")
  fi
  "${DIGEST_CMD[@]}"
fi

echo "Operator health snapshot complete"
