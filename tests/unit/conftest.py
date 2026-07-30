"""Pytest configuration for tests/unit.

Adds tests/unit to sys.path so that fixture modules (like incident_store_fixtures)
can be imported by sibling test modules.
"""

from __future__ import annotations

import subprocess as subprocess_module
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_review_packet import (
    write_diagnosis_review_packet,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import reset_incident_store, set_incident_store

# Import kubectl guard to enforce unit test boundaries
from tests.conftest_kubectl_guard import forbid_real_kubectl  # noqa: F401

# Add this directory to sys.path so fixtures can be imported
_tests_unit = Path(__file__).parent
if str(_tests_unit) not in sys.path:
    sys.path.insert(0, str(_tests_unit))

# Add scripts/ci to sys.path so the runtime-gate scripts (which are not
# packages) can be imported directly.  This is required for the promotion
# runtime gate unit tests which import modules like
# run_promotion_runtime_gate, promotion_runtime_static_scope, and
# promotion_runtime_static_gate_runner from scripts/ci.
_scripts_ci = _tests_unit.parent.parent / "scripts" / "ci"
if str(_scripts_ci) not in sys.path:
    sys.path.insert(0, str(_scripts_ci))


# =============================================================================
# Fixtures for automatic_diagnosis_review tests
# =============================================================================


@pytest.fixture
def temp_external_dir():
    """Provide a temporary directory for artifact writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_case_file():
    """Provide a sample case file with suggested checks."""
    return {
        "schema_version": "1.0",
        "generated_at": "2026-06-19T08:00:00+00:00",
        "incident": {
            "incident_id": "test-incident-123",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
        },
        "suggested_checks": [
            {"check_id": "pod_logs", "title": "Check pod logs", "read_only": True},
        ],
    }


@pytest.fixture
def sample_orchestrator_result():
    """Provide a sample orchestrator result with paths."""
    return {
        "decision": "run_allowed_read_only_checks",
        "runner_result": {
            "checks_requested": 3,
            "checks_run": 3,
            "checks_skipped": 0,
            "checks_rejected": 0,
        },
        "artifact": {
            "artifact_path": "/some/path/run123-read-only-check-results.json",
            "written": True
        },
        "loop_pass_artifact": {
            "artifact_path": "/some/path/run123-diagnosis-loop-pass.json",
            "written": True
        },
    }


@pytest.fixture
def incident_store():
    """Provide a clean incident store for tests."""
    store = IncidentStore()
    set_incident_store(store)
    yield store
    set_incident_store(None)
    reset_incident_store()


def write_review_packet(
    temp_external_dir: Path,
    incident_id: str = "test-incident",
    run_id: str = "auto-test-incident-20260619-080000-abc123",
    decision: str = "run_allowed_read_only_checks",
    checks_requested: int = 3,
    checks_run: int = 2,
    checks_skipped: int = 0,
    checks_rejected: int = 1,
    eligible: bool = True,
    eligibility_reason: str = "active_incident",
    sample_case_file: dict | None = None,
    sample_orchestrator_result: dict | None = None,
    now: datetime | None = None,
) -> None:
    """Helper to write a diagnosis review packet."""
    if now is None:
        now = datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC)

    write_diagnosis_review_packet(
        external_analysis_dir=temp_external_dir,
        incident_id=incident_id,
        collector_run_id="collector-1",
        run_id=run_id,
        decision=decision,
        checks_requested=checks_requested,
        checks_run=checks_run,
        checks_skipped=checks_skipped,
        checks_rejected=checks_rejected,
        eligible=eligible,
        eligibility_reason=eligibility_reason,
        case_file=sample_case_file or {
            "schema_version": "1.0",
            "generated_at": "2026-06-19T08:00:00+00:00",
            "incident": {
                "incident_id": incident_id,
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
            },
            "suggested_checks": [
                {"check_id": "pod_logs", "title": "Check pod logs", "read_only": True},
            ],
        },
        orchestrator_result=sample_orchestrator_result or {
            "decision": decision,
            "runner_result": {
                "checks_requested": checks_requested,
                "checks_run": checks_run,
                "checks_skipped": checks_skipped,
                "checks_rejected": checks_rejected,
            },
        },
        now=now,
    )


# =============================================================================
# External-analysis subprocess compatibility (kubectl-boundary hardening)
# =============================================================================

# External analysis modules that need subprocess attribute for patch() to work
_EXTERNAL_ANALYSIS_MODULES = [
    "k8s_diag_agent.external_analysis.alertmanager_discovery",
    "k8s_diag_agent.external_analysis.alertmanager_discovery_crd_strategy",
    "k8s_diag_agent.external_analysis.alertmanager_discovery_service_strategy",
    "k8s_diag_agent.external_analysis.alertmanager_discovery_backing_identity",
    "k8s_diag_agent.external_analysis.vmalert_discovery_crd_strategy",
    "k8s_diag_agent.external_analysis.vmalert_discovery_service_strategy",
]


def pytest_configure(config) -> None:
    """Pre-import external_analysis modules and add subprocess attribute.
    
    Some modules import subprocess locally inside functions, which means they don't
    have a module-level subprocess attribute. This breaks tests that use
    patch("module.subprocess.run", ...). We fix this by:
    1. Force-importing these modules
    2. Adding subprocess to their namespace
    """
    import importlib
    
    for _module_path in _EXTERNAL_ANALYSIS_MODULES:
        try:
            # Force import the module
            _mod = importlib.import_module(_module_path)
            # Add subprocess attribute if not present
            if not hasattr(_mod, "subprocess"):
                _mod.subprocess = subprocess_module
        except ImportError:
            pass


# NOTE: The autouse kubectl mock was removed.
# 
# The kubectl-boundary guard in conftest_kubectl_guard.py blocks real kubectl
# in unit tests. Tests must patch at the correct call-site seam:
#
#   monkeypatch.setattr("k8s_diag_agent.collect.incident_collectors.kubectl", fake_kubectl)
#
# NOT at subprocess.run or other internal paths.
#
# For tests that truly need kubectl, use @pytest.mark.live_kubernetes.
