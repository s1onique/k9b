"""Regression test for persisted diagnosis contract.

This test mirrors the CI Phase 4 contract check that verifies:
1. automatic_diagnosis_review.available is True
2. automatic_diagnosis_loop_summary.status is "completed"

This was added after fixing diagnosis_not_persisted failure where the
one-pass service was not emitting timeline events or writing review packets.

See: .github/workflows/k9b-cnpg-incident-lab-live.yml Phase 4
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_service import (
    IncidentOnePassServiceRequest,
    run_incident_one_pass_diagnosis,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.ui.api_incident_diagnosis_loop_summary import (
    build_automatic_diagnosis_loop_summary,
)
from k8s_diag_agent.ui.api_incident_reads import build_automatic_diagnosis_review_payload

from .test_incident_diagnosis_service_fixtures import (
    FakeArtifactWriter,
    FakeDiagnosisProvider,
    _create_test_incident,
    set_incident_store,
)


class TestPersistedDiagnosisContract:
    """Regression tests for persisted diagnosis contract.

    These tests verify that running one-pass diagnosis correctly persists
    state that satisfies the CI Phase 4 contract check:
    - automatic_diagnosis_review.available = True
    - automatic_diagnosis_loop_summary.status != "not_run"
    """

    def test_one_pass_diagnosis_persists_review_packet(self, tmp_path: Path) -> None:
        """One-pass diagnosis makes automatic_diagnosis_review.available=True."""
        # Setup: Create and populate store
        store = IncidentStore()
        incident = _create_test_incident("test-contract-incident-001")
        store._incidents["test-contract-incident-001"] = incident
        set_incident_store(store)

        external_analysis_dir = tmp_path

        request = IncidentOnePassServiceRequest(
            incident_id="test-contract-incident-001",
            external_analysis_dir=external_analysis_dir,
            diagnosis_provider=FakeDiagnosisProvider({
                "summary": "Test diagnosis for contract",
                "confidence": "high",
                "likely_causes": ["probe failure"],
                "recommended_investigations": [],
            }),
            artifact_writer=FakeArtifactWriter(),
        )

        # Execute: Run one-pass diagnosis
        result = run_incident_one_pass_diagnosis(request)

        # Verify: Service completed without error
        assert result.error is None, f"Service returned error: {result.error}"
        assert result.artifact_written is True

        # Verify: Review packet exists in external_analysis_dir
        auto_review = build_automatic_diagnosis_review_payload(
            external_analysis_dir, "test-contract-incident-001"
        )
        assert auto_review["available"] is True, (
            "automatic_diagnosis_review.available should be True after one-pass diagnosis"
        )
        assert auto_review.get("artifact_name") is not None, (
            "artifact_name should be present when available=True"
        )
        assert auto_review.get("decision") is not None, (
            "decision should be present when available=True"
        )

    def test_one_pass_diagnosis_emits_completed_event(self, tmp_path: Path) -> None:
        """One-pass diagnosis makes automatic_diagnosis_loop_summary.status=completed."""
        # Setup: Create and populate store
        store = IncidentStore()
        incident = _create_test_incident("test-contract-incident-002")
        store._incidents["test-contract-incident-002"] = incident
        set_incident_store(store)

        external_analysis_dir = tmp_path

        request = IncidentOnePassServiceRequest(
            incident_id="test-contract-incident-002",
            external_analysis_dir=external_analysis_dir,
            diagnosis_provider=FakeDiagnosisProvider({
                "summary": "Test diagnosis for loop status",
                "confidence": "medium",
                "likely_causes": ["resource pressure"],
                "recommended_investigations": [],
            }),
        )

        # Execute: Run one-pass diagnosis
        result = run_incident_one_pass_diagnosis(request)

        # Verify: Service completed without error
        assert result.error is None, f"Service returned error: {result.error}"

        # Verify: Timeline events are emitted
        # Re-fetch incident from store to get updated events
        updated_incident = store.get_incident("test-contract-incident-002")
        assert updated_incident is not None

        # Incident uses 'events' field for timeline
        events_data = []
        for event in updated_incident.events:
            events_data.append({
                "event_type": event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
                "occurred_at": event.occurred_at.isoformat() if hasattr(event, 'occurred_at') else None,
                "data": getattr(event, 'data', {}),
            })

        # Build loop summary from events
        loop_summary = build_automatic_diagnosis_loop_summary(
            events=events_data,
            review_packet_available=True,
        )

        # build_automatic_diagnosis_loop_summary returns a dict
        loop_status = loop_summary.get("status") if isinstance(loop_summary, dict) else getattr(loop_summary, 'status', 'not_run')

        assert loop_status != "not_run", (
            "automatic_diagnosis_loop_summary.status should not be 'not_run' after one-pass diagnosis"
        )
        assert loop_status == "completed", (
            f"automatic_diagnosis_loop_summary.status should be 'completed', got '{loop_status}'"
        )

    def test_incident_detail_includes_automatic_diagnosis_fields(self, tmp_path: Path) -> None:
        """Incident detail includes both automatic_diagnosis_review and loop_summary."""
        # Setup
        store = IncidentStore()
        incident = _create_test_incident("test-contract-incident-003")
        store._incidents["test-contract-incident-003"] = incident
        set_incident_store(store)

        external_analysis_dir = tmp_path

        request = IncidentOnePassServiceRequest(
            incident_id="test-contract-incident-003",
            external_analysis_dir=external_analysis_dir,
            diagnosis_provider=FakeDiagnosisProvider({
                "summary": "Full contract test",
                "confidence": "high",
                "likely_causes": ["probe failure"],
                "recommended_investigations": [],
            }),
        )

        # Execute
        result = run_incident_one_pass_diagnosis(request)
        assert result.error is None

        # Verify: Re-fetch incident and check both fields
        updated_incident = store.get_incident("test-contract-incident-003")
        assert updated_incident is not None

        auto_review = build_automatic_diagnosis_review_payload(
            external_analysis_dir, "test-contract-incident-003"
        )
        assert auto_review["available"] is True

        events_data = []
        for event in updated_incident.events:
            events_data.append({
                "event_type": event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
                "occurred_at": event.occurred_at.isoformat() if hasattr(event, 'occurred_at') else None,
                "data": getattr(event, 'data', {}),
            })

        loop_summary = build_automatic_diagnosis_loop_summary(
            events=events_data,
            review_packet_available=True,
        )

        # build_automatic_diagnosis_loop_summary returns a dict
        loop_status = loop_summary.get("status") if isinstance(loop_summary, dict) else getattr(loop_summary, 'status', 'not_run')

        assert loop_status == "completed"

        # Both fields satisfy the CI Phase 4 contract
        # This is what the contract check script verifies
        contract_satisfied = (
            auto_review["available"] is True
            and loop_status == "completed"
        )
        assert contract_satisfied, (
            "CI Phase 4 contract requires both "
            "automatic_diagnosis_review.available=True "
            "and automatic_diagnosis_loop_summary.status=completed"
        )

    def test_provider_status_persisted_in_review_packet(self, tmp_path: Path) -> None:
        """Provider status is persisted in review packet and visible in auto_review.

        This test verifies the Phase 4 provider_status_missing fix:
        - Provider metadata is now persisted when one-pass diagnosis completes
        - Provider status appears in automatic_diagnosis_review.provider_status
        - The contract checker can find provider fields at the canonical path
        """
        # Setup
        store = IncidentStore()
        incident = _create_test_incident("test-contract-incident-004")
        store._incidents["test-contract-incident-004"] = incident
        set_incident_store(store)

        external_analysis_dir = tmp_path

        # Use FakeDiagnosisProvider which reports as configured but not invoked
        request = IncidentOnePassServiceRequest(
            incident_id="test-contract-incident-004",
            external_analysis_dir=external_analysis_dir,
            diagnosis_provider=FakeDiagnosisProvider({
                "summary": "Provider status test",
                "confidence": "medium",
                "likely_causes": ["resource pressure"],
                "recommended_investigations": [],
            }),
        )

        # Execute
        result = run_incident_one_pass_diagnosis(request)
        assert result.error is None

        # Verify: Provider status fields are persisted
        auto_review = build_automatic_diagnosis_review_payload(
            external_analysis_dir, "test-contract-incident-004"
        )
        assert auto_review["available"] is True, (
            "automatic_diagnosis_review.available should be True after one-pass diagnosis"
        )

        # Provider status should be present in the canonical path
        provider_status = auto_review.get("provider_status")
        assert provider_status is not None, (
            "automatic_diagnosis_review.provider_status should be present "
            "to satisfy Phase 4 provider_status_missing contract"
        )

        # Verify provider status fields
        assert "provider_configured" in provider_status or "provider_enabled" in provider_status, (
            "provider_status should contain provider_configured or provider_enabled"
        )

        # Provider configured should match the FakeDiagnosisProvider behavior
        # (FakeDiagnosisProvider is a non-NoOp provider, so it should be configured=True)
        provider_configured = provider_status.get("provider_configured")
        assert provider_configured is not None, (
            "provider_status.provider_configured should be present"
        )

        # Verify the review packet JSON contains provider_status
        from k8s_diag_agent.collect.incident_diagnosis_review_packet import (
            load_review_packet_summary,
        )
        packet_summary = load_review_packet_summary(external_analysis_dir, "test-contract-incident-004")
        assert packet_summary is not None
        assert "provider_status" in packet_summary, (
            "Review packet summary should include provider_status"
        )

    def test_contract_checker_finds_provider_status_at_canonical_path(self, tmp_path: Path) -> None:
        """Contract checker uses canonical path automatic_diagnosis_review.provider_status."""
        # Setup
        store = IncidentStore()
        incident = _create_test_incident("test-contract-incident-005")
        store._incidents["test-contract-incident-005"] = incident
        set_incident_store(store)

        external_analysis_dir = tmp_path

        request = IncidentOnePassServiceRequest(
            incident_id="test-contract-incident-005",
            external_analysis_dir=external_analysis_dir,
            diagnosis_provider=FakeDiagnosisProvider({
                "summary": "Canonical path test",
                "confidence": "high",
                "likely_causes": ["probe failure"],
                "recommended_investigations": [],
            }),
        )

        # Execute
        result = run_incident_one_pass_diagnosis(request)
        assert result.error is None

        # Build incident detail payload (simulates GET /api/incidents/{id})
        auto_review = build_automatic_diagnosis_review_payload(
            external_analysis_dir, "test-contract-incident-005"
        )

        # Simulate the incident JSON that contract checker would see
        incident_json = {
            "incident_id": "test-contract-incident-005",
            "automatic_diagnosis_review": auto_review,
            "automatic_diagnosis_loop_summary": {
                "status": "completed",
            },
        }

        # Test the contract checker's canonical path logic
        from scripts.check_persisted_diagnosis_contract import check_provider_status

        provider_ok, failure_class, findings = check_provider_status(incident_json)

        # Provider should be found at canonical path
        assert provider_ok, (
            f"Contract checker should find provider status at canonical path. "
            f"Failure: {failure_class}, Findings: {findings}"
        )

        # Verify findings mention provider_configured
        assert any("provider_configured" in f for f in findings), (
            f"Findings should mention provider_configured. Got: {findings}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
