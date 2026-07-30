#!/usr/bin/env bash
# Canonical Python development-environment bootstrap.
#
# ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION04/05
#
# Contract:
#   - create ./.venv when absent
#   - install the repository's canonical ``.[dev]`` dependency set
#   - print tool versions (python, pip, pytest, ruff, mypy)
#   - prove every tool resolves under ``${VENV_DIR}/bin/``
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

# Explicit PATH authority (P0-6): the runner must see the venv bin
# directory BEFORE any proof command, before the source-activate that
# only affects shell-local aliases.
export PATH="${VENV_DIR}/bin:${PATH}"

# When running under GitHub Actions, also append the venv directory to
# $GITHUB_PATH so subsequent steps inherit it.  $GITHUB_PATH does not
# affect the currently-executing step, so the explicit PATH export above
# is still required.
if [ -n "${GITHUB_PATH:-}" ]; then
  printf '%s\n' "${VENV_DIR}/bin" >> "${GITHUB_PATH}"
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

# PATH proof (P0-6): each tool MUST resolve to the venv bin directory.
for tool in python pytest ruff mypy; do
  resolved="$(command -v "${tool}" || true)"
  if [ -z "${resolved}" ]; then
    echo "FATAL: ${tool} not on PATH after canonical bootstrap" >&2
    exit 1
  fi
  case "${resolved}" in
    "${VENV_DIR}/bin/${tool}") ;;
    *)
      echo "FATAL: ${tool} resolves to ${resolved}, expected ${VENV_DIR}/bin/${tool}" >&2
      exit 1
      ;;
  esac
done
echo "PATH proof OK: all tools resolve to ${VENV_DIR}/bin/."

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