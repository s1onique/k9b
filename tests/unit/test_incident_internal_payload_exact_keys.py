"""Exact-key tests for internal incident API payloads.

These tests verify that payloads contain exactly the expected keys
and no extra keys, ensuring the TypedDict contract is enforced.
"""

from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentSignal,
    IncidentStatus,
)
from k8s_diag_agent.ui.api_incident_internal_reads import (
    build_incident_internal_detail_payload,
    build_incident_internal_list_item_payload,
)


class TestIncidentInternalListItemPayloadExactKeys:
    """Verify list item payload has exactly the expected keys."""

    def _make_incident(
        self,
        first_observed: datetime | None = None,
        last_observed: datetime | None = None,
    ) -> Incident:
        """Helper to create test incidents."""
        return Incident(
            incident_id="test-incident-123",
            source_candidate_id="test-candidate-456",
            namespace="default",
            object_kind="Pod",
            object_name="nginx-pod",
            raw_object_kind=None,
            candidate_class="PodCrashLoop",
            severity="high",
            status=IncidentStatus.OPEN,
            first_observed_at=first_observed or datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            last_observed_at=last_observed or datetime(2024, 1, 15, 12, 45, 0, tzinfo=UTC),
            signals=[],
            signal_count=0,
        )

    def test_list_item_payload_has_exactly_required_keys(self) -> None:
        """List item payload should have exactly the defined keys, no extras."""
        incident = self._make_incident()
        payload = build_incident_internal_list_item_payload(incident)

        # Expected keys based on IncidentInternalListItemPayload TypedDict
        expected_keys = {
            "incident_id",
            "source_candidate_id",
            "namespace",
            "object_kind",
            "raw_object_kind",
            "object_name",
            "candidate_class",
            "severity",
            "status",
            "created_at",
            "updated_at",
            "signal_count",
            "evidence_count",
        }

        actual_keys = set(payload.keys())
        extra_keys = actual_keys - expected_keys
        missing_keys = expected_keys - actual_keys

        assert not extra_keys, f"Payload has unexpected keys: {extra_keys}"
        assert not missing_keys, f"Payload is missing keys: {missing_keys}"
        assert actual_keys == expected_keys, f"Key mismatch: expected={expected_keys}, actual={actual_keys}"

    def test_list_item_payload_has_no_extra_keys(self) -> None:
        """List item payload should not have keys from detail payload."""
        incident = self._make_incident()
        payload = build_incident_internal_list_item_payload(incident)

        # These are detail-only keys that should NOT appear in list item
        detail_only_keys = {"signals", "evidence_needed", "evidence_links", "events"}

        for key in detail_only_keys:
            assert key not in payload, f"List item payload should not have '{key}' (detail-only key)"


class TestIncidentInternalDetailPayloadExactKeys:
    """Verify detail payload has exactly the expected keys."""

    def _make_incident(
        self,
        signals: list[IncidentSignal] | None = None,
        first_observed: datetime | None = None,
        last_observed: datetime | None = None,
    ) -> Incident:
        """Helper to create test incidents."""
        return Incident(
            incident_id="test-incident-123",
            source_candidate_id="test-candidate-456",
            namespace="default",
            object_kind="Pod",
            object_name="nginx-pod",
            raw_object_kind=None,
            candidate_class="PodCrashLoop",
            severity="high",
            status=IncidentStatus.OPEN,
            first_observed_at=first_observed or datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            last_observed_at=last_observed or datetime(2024, 1, 15, 12, 45, 0, tzinfo=UTC),
            signals=signals or [],
            signal_count=len(signals) if signals else 0,
        )

    def test_detail_payload_has_exactly_required_keys(self) -> None:
        """Detail payload should have exactly the defined keys, no extras."""
        incident = self._make_incident()
        payload = build_incident_internal_detail_payload(incident)

        # Expected keys based on IncidentInternalDetailPayload TypedDict
        expected_keys = {
            "incident_id",
            "source_candidate_id",
            "namespace",
            "object_kind",
            "raw_object_kind",
            "object_name",
            "candidate_class",
            "severity",
            "status",
            "created_at",
            "updated_at",
            "signal_count",
            "evidence_count",
            "signals",
        }

        actual_keys = set(payload.keys())
        extra_keys = actual_keys - expected_keys
        missing_keys = expected_keys - actual_keys

        assert not extra_keys, f"Payload has unexpected keys: {extra_keys}"
        assert not missing_keys, f"Payload is missing keys: {missing_keys}"
        assert actual_keys == expected_keys, f"Key mismatch: expected={expected_keys}, actual={actual_keys}"

    def test_detail_payload_includes_signals_key(self) -> None:
        """Detail payload must include signals key (list item does not)."""
        incident = self._make_incident(signals=[
            IncidentSignal(
                source="detector-1",
                reason="Test",
                message="Test message",
                captured_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            ),
        ])
        payload = build_incident_internal_detail_payload(incident)

        assert "signals" in payload
        assert isinstance(payload["signals"], list)
        assert len(payload["signals"]) == 1

    def test_detail_payload_does_not_have_evidence_fields(self) -> None:
        """Detail payload should not have evidence-related keys from external API."""
        incident = self._make_incident()
        payload = build_incident_internal_detail_payload(incident)

        # These are from IncidentDetailPayload (external API), not IncidentInternalDetailPayload
        external_only_keys = {
            "evidence_needed",
            "evidence_links",
            "events",
            "evidence_artifacts",
            "suggested_checks",
            "automatic_diagnosis_review",
            "automatic_diagnosis_loop_summary",
        }

        for key in external_only_keys:
            assert key not in payload, f"Detail payload should not have '{key}' (external API key)"

    def test_list_item_vs_detail_payload_differ(self) -> None:
        """List item and detail payloads should have different key sets."""
        incident_list = self._make_incident()
        incident_detail = self._make_incident()

        list_payload = build_incident_internal_list_item_payload(incident_list)
        detail_payload = build_incident_internal_detail_payload(incident_detail)

        list_keys = set(list_payload.keys())
        detail_keys = set(detail_payload.keys())

        # Detail should have all list keys PLUS signals
        assert list_keys < detail_keys, "Detail payload should be a superset of list payload"
        assert "signals" in detail_keys, "Detail payload must include 'signals'"
        assert "signals" not in list_keys, "List item payload must NOT include 'signals'"
