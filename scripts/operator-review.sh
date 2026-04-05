#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
REVIEW_SCRIPT="$ROOT/scripts/review_latest_health.py"

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

echo "Running operator review workflow"
"$PYTHON" "$REVIEW_SCRIPT" --run-health "$@"
