#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
SRC_PATH="$ROOT/src"
REVIEW_SCRIPT="$ROOT/scripts/review_latest_health.py"
export PYTHONPATH="$SRC_PATH:$PYTHONPATH"

log_operator_event() {
  local severity="$1"
  local message="$2"
  local run_label="${3:-operator-review}"
  PYTHONPATH="$SRC_PATH:$PYTHONPATH" "$PYTHON" - "$severity" "$message" "$run_label" <<'PY'
import sys
from k8s_diag_agent.structured_logging import emit_structured_log
emit_structured_log(
    component="operator-review-script",
    message=sys.argv[2],
    severity=sys.argv[1],
    run_label=sys.argv[3],
    metadata={"script": "operator-review"},
)
PY
}

RUN_TESTS=false
RUN_MYPY=false
POSITIONAL=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tests)
      RUN_TESTS=true
      shift
      ;;
    --mypy)
      RUN_MYPY=true
      shift
      ;;
    --)
      shift
      POSITIONAL+=("$@")
      break
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done

set -- "${POSITIONAL[@]}"

if [[ ! -x "$PYTHON" ]]; then
  log_operator_event "ERROR" "Interpreter $PYTHON not found"
  echo "Interpreter $PYTHON not found; run \"python -m venv .venv\" and install deps before using this script." >&2
  exit 1
fi

if $RUN_TESTS; then
  echo "Running unit tests"
  "$PYTHON" -m unittest discover tests
fi

if $RUN_MYPY; then
  echo "Running mypy"
  "$PYTHON" -m mypy src tests
fi

log_operator_event "INFO" "Operator review workflow invoked" "operator-review"

echo "Running operator review workflow"
"$PYTHON" "$REVIEW_SCRIPT" --run-health "$@"

log_operator_event "INFO" "Operator review workflow completed" "operator-review"
