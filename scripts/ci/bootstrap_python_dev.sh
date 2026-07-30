#!/usr/bin/env bash
# Canonical Python development-environment bootstrap.
#
# ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION04
#
# Contract:
#   - create ./.venv when absent
#   - install the repository's canonical ``.[dev]`` dependency set
#   - print tool versions (python, pip, pytest, ruff, mypy)
#   - fail closed if any required tool is missing
#   - accept NO arbitrary package names
#   - handle NO secrets
#
# This script is the SINGLE authority for installing Python dev
# dependencies in this repository.  Any workflow that needs pytest,
# Ruff, or mypy MUST invoke this script rather than calling
# ``pip install`` directly.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "FATAL: ${PYTHON_BIN} is not on PATH" >&2
  exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "Creating virtual environment at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip >/dev/null
# Canonical: install the ``.[dev]`` extra; this is the SINGLE source of
# truth for pytest, Ruff and mypy.  No standalone ``pip install pytest``
# anywhere in this repository.
python -m pip install -e ".[dev]"

echo "=== Bootstrap versions ==="
python --version
python -m pip --version
python -m pytest --version
python -m ruff --version
python -m mypy --version

# Fail closed if any required tool is missing.  Tooling is otherwise
# declared via pyproject's [project.optional-dependencies].dev extra
# and the version line above would have crashed.
for tool in pytest ruff mypy; do
  if ! python -c "import ${tool}" >/dev/null 2>&1; then
    echo "FATAL: required tool '${tool}' is not importable after canonical install" >&2
    exit 1
  fi
done

echo "Bootstrap OK: .[dev] installed, all required tools importable."