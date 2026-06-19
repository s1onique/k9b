"""Shared fixtures and helpers for automatic_diagnosis_review tests.

This module contains shared test fixtures and helper functions used by
multiple test files for the automatic_diagnosis_review feature.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_review_packet import (
    write_diagnosis_review_packet,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import reset_incident_store, set_incident_store


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
