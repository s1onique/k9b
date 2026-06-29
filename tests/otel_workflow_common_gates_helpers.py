# Copyright (c) 2025 Artem Chistyakov
# SPDX-License-Identifier: MIT

"""Shared helpers for OTel workflow common gates tests.

This module contains constants and utility functions used across the
test_otel_workflow_*_gate.py test files. It intentionally does NOT
have a test_ prefix so pytest does not collect it as a test file.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OTEL_WORKFLOW = REPO_ROOT / ".github/workflows/k9b-otel-demo-incident-lab.yml"
OTEL_ORCHESTRATOR = REPO_ROOT / "scripts/k9b_otel_demo_lab.py"
PROVIDER_HEALTH = REPO_ROOT / "scripts/k9b_otel_demo_lab_provider_health.py"
DEPLOYMENT_PHASES = REPO_ROOT / "scripts/k9b_otel_demo_lab_deployment.py"
FRONTEND_SMOKE = REPO_ROOT / "scripts/k9b_otel_frontend_smoke.py"
TRAFFIC_SCRIPT = REPO_ROOT / "scripts/k9b_otel_demo_lab_traffic.py"
PROVIDER_PREFLIGHT = REPO_ROOT / "scripts/k9b_provider_preflight.py"


def read_text(path: Path) -> str:
    """Read text content from a file."""
    return path.read_text(encoding="utf-8")


def index_of(haystack: str, needle: str) -> int:
    """Find index of needle in haystack, asserting it exists."""
    idx = haystack.find(needle)
    assert idx >= 0, f"Missing expected marker: {needle}"
    return idx
