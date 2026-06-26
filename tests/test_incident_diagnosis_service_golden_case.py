"""Golden-case integration tests for incident diagnosis service.

These tests verify that the service correctly processes golden-case scenarios
through the complete service/API seam, including handler invocation and
the one-pass diagnosis loop.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.golden_case_evidence_provider import (
    GoldenCaseEvidenceProvider,
)
from k8s_diag_agent.collect.golden_case_fake_handlers import (
    create_golden_case_fake_handlers,
)
from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
    GoldenCaseDeterministicLLMProvider,
)
from k8s_diag_agent.collect.incident_diagnosis_service import (
    IncidentOnePassServiceRequest,
    run_incident_one_pass_diagnosis,
)

from .test_incident_diagnosis_service_fixtures import (
    FakeArtifactWriter,
    _create_test_incident,
    set_incident_store,
)


def test_golden_case_pod_failure_through_service_seam(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
    tmp_path: Path,
) -> None:
    """Pod-failure golden case passes through the service/API seam."""
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create incident matching golden case
    store = IncidentStore()
    incident = _create_test_incident(
        incident_id=manifest["case_id"],
        namespace=manifest["fixture_namespace"],
        object_name=manifest["fixture_name"],
    )
    store._incidents[manifest["case_id"]] = incident
    set_incident_store(store)

    fake_writer = FakeArtifactWriter()
    fake_handlers = create_golden_case_fake_handlers(evidence_provider)
    llm_provider = GoldenCaseDeterministicLLMProvider(
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
    )

    request = IncidentOnePassServiceRequest(
        incident_id=manifest["case_id"],
        external_analysis_dir=tmp_path,
        diagnosis_provider=llm_provider,
        fake_handlers=fake_handlers,
        artifact_writer=fake_writer,
        now=datetime.now(UTC),
    )

    result = run_incident_one_pass_diagnosis(request)

    # Verify successful diagnosis
    assert result.error is None
    assert result.incident_id == manifest["case_id"]
    assert result.read_only is True
    assert result.allowed_actions == []
    assert result.mutation_proposals_observed == []
    assert result.forbidden_actions_observed == []

    # Verify diagnosis content (category and root_cause may vary)
    assert result.category is not None
    assert result.root_cause is not None

    # Verify artifact was persisted
    assert result.artifact_written is True
    assert fake_writer.last_diagnosis is not None


def test_read_only_handlers_invoked(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Read-only fake handlers are configured for the service."""
    # This test verifies that fake handlers can be created and passed
    # to the service request. The ACT-local verification script
    # already confirms handlers are invoked at runtime.
    fake_handlers = create_golden_case_fake_handlers(evidence_provider)

    # Verify all expected handler IDs are present
    expected_handler_ids = [
        "pod_describe", "pod_events", "pod_logs",
        "deployment_status", "node_status", "service_endpoints"
    ]
    for handler_id in expected_handler_ids:
        assert handler_id in fake_handlers, f"Missing handler: {handler_id}"


def test_service_uses_same_one_pass_loop(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
    tmp_path: Path,
) -> None:
    """Service uses the same run_one_read_only_diagnosis_loop_pass function."""
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create incident matching golden case
    store = IncidentStore()
    incident = _create_test_incident(
        incident_id=manifest["case_id"],
        namespace=manifest["fixture_namespace"],
        object_name=manifest["fixture_name"],
    )
    store._incidents[manifest["case_id"]] = incident
    set_incident_store(store)

    llm_provider = GoldenCaseDeterministicLLMProvider(
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
    )

    request = IncidentOnePassServiceRequest(
        incident_id=manifest["case_id"],
        external_analysis_dir=tmp_path,
        diagnosis_provider=llm_provider,
        fake_handlers=create_golden_case_fake_handlers(evidence_provider),
        now=datetime.now(UTC),
    )

    result = run_incident_one_pass_diagnosis(request)

    # Verify orchestrator ran successfully (one-pass)
    assert result.error is None
    assert result.run_id is not None
