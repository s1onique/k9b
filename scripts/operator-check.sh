#!/usr/bin/env bash
set -euo pipefail

echo "Running unit tests"
.venv/bin/python -m unittest discover tests

echo "Running mypy"
.venv/bin/python -m mypy src tests

echo "Running health loop"
.venv/bin/python -m k8s_diag_agent.cli run-health-loop --config runs/health-config.local.json

echo "Health artifacts available under runs/health"
