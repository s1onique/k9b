"""Tests for incident diagnosis service artifact persistence and response DTO.

These tests verify that the service properly persists diagnosis artifacts
and returns well-structured response DTOs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from k8s_diag_agent.collect.incident_diagnosis_service import (
    IncidentOnePassServiceRequest,
    run_incident_one_pass_diagnosis,
)

from .test_incident_diagnosis_service_fixtures import (
    FakeArtifactWriter,
    FakeDiagnosisProvider,
    _create_test_incident,
    set_incident_store,
)


def test_service_persists_diagnosis_artifacts() -> None:
    """Service persists diagnosis output to artifact writer."""
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create and populate store
    store = IncidentStore()
    incident = _create_test_incident("test-incident-003")
    store._incidents["test-incident-003"] = incident
    set_incident_store(store)

    fake_writer = FakeArtifactWriter()

    request = IncidentOnePassServiceRequest(
        incident_id="test-incident-003",
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=FakeDiagnosisProvider({
            "summary": "Diagnosis complete",
            "confidence": "high",
            "likely_causes": ["probe failure"],
            "recommended_investigations": [
                {"check_id": "pod_describe", "title": "Describe pod"}
            ],
        }),
        artifact_writer=fake_writer,
    )

    result = run_incident_one_pass_diagnosis(request)

    assert result.error is None
    assert result.artifact_written is True
    assert result.artifact_name is not None
    assert len(fake_writer.calls) == 1
    assert fake_writer.last_diagnosis is not None
    assert fake_writer.last_diagnosis["read_only"] is True
    assert fake_writer.last_diagnosis["allowed_actions"] == []


def test_service_returns_stable_dto() -> None:
    """Service returns properly structured response DTO."""
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create and populate store
    store = IncidentStore()
    incident = _create_test_incident("test-incident-004")
    store._incidents["test-incident-004"] = incident
    set_incident_store(store)

    request = IncidentOnePassServiceRequest(
        incident_id="test-incident-004",
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=FakeDiagnosisProvider({
            "summary": "Diagnosis complete",
            "confidence": "high",
            "likely_causes": ["probe failure"],
            "recommended_investigations": [],
        }),
    )

    result = run_incident_one_pass_diagnosis(request)

    # Verify DTO structure
    dto = result.to_dict()
    required_fields = [
        "schema_version", "incident_id", "run_id", "category", "root_cause",
        "confidence", "description", "evidence_refs", "read_only",
        "allowed_actions", "forbidden_actions_observed", "mutation_proposals_observed",
        "decision", "checks_run", "next_checks", "artifact_written",
    ]
    for field in required_fields:
        assert field in dto, f"Missing required field: {field}"

    # Verify types
    assert isinstance(dto["read_only"], bool)
    assert isinstance(dto["allowed_actions"], list)
    assert isinstance(dto["next_checks"], list)
    assert dto["read_only"] is True
    assert dto["allowed_actions"] == []
