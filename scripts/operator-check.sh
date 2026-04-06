#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
SRC_PATH="$ROOT/src"
export PYTHONPATH="$SRC_PATH:$PYTHONPATH"

log_operator_event() {
  local severity="$1"
  local message="$2"
  local run_label="${3:-operator-check}"
  PYTHONPATH="$SRC_PATH:$PYTHONPATH" "$PYTHON" - "$severity" "$message" "$run_label" <<'PY'
import sys
from k8s_diag_agent.structured_logging import emit_structured_log
emit_structured_log(
    component="operator-check-script",
    message=sys.argv[2],
    severity=sys.argv[1],
    run_label=sys.argv[3],
    metadata={"script": "operator-check"},
)
PY
}

log_operator_event "INFO" "Operator check workflow started" "operator-check"

echo "Running unit tests"
"$PYTHON" -m unittest discover tests
log_operator_event "INFO" "Unit tests completed" "operator-check"

echo "Running mypy"
"$PYTHON" -m mypy src tests
log_operator_event "INFO" "Mypy completed" "operator-check"

echo "Running health loop"
"$PYTHON" -m k8s_diag_agent.cli run-health-loop --config runs/health-config.local.json
log_operator_event "INFO" "Health loop invoked" "operator-check"

echo "Health artifacts available under runs/health"
log_operator_event "INFO" "Operator check workflow completed" "operator-check"
