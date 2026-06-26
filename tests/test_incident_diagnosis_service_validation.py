"""Tests for incident diagnosis service request validation.

These tests verify that the service properly validates incoming requests
and handles edge cases like missing incidents or misconfigured providers.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_service import (
    IncidentOnePassServiceRequest,
    run_incident_one_pass_diagnosis,
)

from .test_incident_diagnosis_service_fixtures import (
    FakeDiagnosisProvider,
    _create_test_incident,
    set_incident_store,
)


def test_service_rejects_missing_incident() -> None:
    """Service returns error for missing incident."""
    request = IncidentOnePassServiceRequest(
        incident_id="nonexistent-incident",
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=FakeDiagnosisProvider({
            "summary": "test",
            "confidence": "high",
            "likely_causes": [],
            "recommended_investigations": [],
        }),
    )

    result = run_incident_one_pass_diagnosis(request)

    assert result.incident_id == "nonexistent-incident"
    assert result.error == "Incident not found"
    assert result.run_id == ""


def test_service_rejects_missing_diagnosis_provider() -> None:
    """Service fails closed when no diagnosis provider is configured."""
    from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create and populate store with a real incident
    store = IncidentStore()
    now = datetime.now(UTC)
    incident = Incident(
        incident_id="test-incident-001",
        source_candidate_id="test-candidate-001",
        namespace="test-namespace",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind=None,
        candidate_class="PodFailure",
        severity="medium",
        status=IncidentStatus.OPEN,
        first_observed_at=now,
        last_observed_at=now,
    )
    store._incidents["test-incident-001"] = incident
    set_incident_store(store)

    # Request without provider - should fail
    request = IncidentOnePassServiceRequest(
        incident_id="test-incident-001",
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=None,  # NoOpDiagnosisProvider is default
    )

    result = run_incident_one_pass_diagnosis(request)

    assert result.incident_id == "test-incident-001"
    assert result.error is not None
    assert "Diagnosis provider error" in result.error or "NoOpDiagnosisProvider" in result.error


def test_service_rejects_mutation_proposals() -> None:
    """Service fails closed when provider returns mutation proposals."""
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create and populate store with a real incident
    store = IncidentStore()
    incident = _create_test_incident("test-incident-002")
    store._incidents["test-incident-002"] = incident
    set_incident_store(store)

    # Provider that returns mutation proposal
    request = IncidentOnePassServiceRequest(
        incident_id="test-incident-002",
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=FakeDiagnosisProvider({
            "summary": "Try kubectl apply to fix this",
            "confidence": "high",
            "likely_causes": ["configuration issue"],
            "recommended_investigations": [],
        }),
    )

    result = run_incident_one_pass_diagnosis(request)

    assert result.incident_id == "test-incident-002"
    assert result.error is not None
    assert "Safety enforcement failed" in result.error
    assert "Mutation proposal" in result.error
