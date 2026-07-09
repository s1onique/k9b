"""Tests for build_incident_internal_detail_payload serializer."""

from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentSignal,
    IncidentStatus,
)
from k8s_diag_agent.ui.api_incident_internal_reads import (
    build_incident_internal_detail_payload,
)


class TestBuildIncidentInternalDetailPayload:
    """Tests for detail serializer."""

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

    def test_includes_all_base_fields(self) -> None:
        """Detail payload includes all fields from list item payload."""
        incident = self._make_incident()
        payload = build_incident_internal_detail_payload(incident)

        # All list item fields should be present
        assert payload["incident_id"] == "test-incident-123"
        assert payload["source_candidate_id"] == "test-candidate-456"
        assert payload["namespace"] == "default"
        assert payload["object_kind"] == "Pod"
        assert payload["raw_object_kind"] is None
        assert payload["object_name"] == "nginx-pod"
        assert payload["candidate_class"] == "PodCrashLoop"
        assert payload["severity"] == "high"
        assert payload["status"] == "open"

    def test_maps_first_observed_at_to_created_at(self) -> None:
        """first_observed_at should serialize as created_at."""
        incident = self._make_incident()
        payload = build_incident_internal_detail_payload(incident)

        assert payload["created_at"] == "2024-01-15T10:30:00+00:00"

    def test_maps_last_observed_at_to_updated_at(self) -> None:
        """last_observed_at should serialize as updated_at."""
        incident = self._make_incident()
        payload = build_incident_internal_detail_payload(incident)

        assert payload["updated_at"] == "2024-01-15T12:45:00+00:00"

    def test_created_at_is_none_when_first_observed_at_is_none(self) -> None:
        """created_at should be None when first_observed_at is None."""
        incident = Incident(
            incident_id="test-incident-123",
            source_candidate_id="test-candidate-456",
            namespace="default",
            object_kind="Pod",
            object_name="nginx-pod",
            raw_object_kind=None,
            candidate_class="PodCrashLoop",
            severity="high",
            status=IncidentStatus.OPEN,
            first_observed_at=None,
            last_observed_at=datetime(2024, 1, 15, 12, 45, 0, tzinfo=UTC),
            signals=[],
            signal_count=0,
        )
        payload = build_incident_internal_detail_payload(incident)

        assert payload["created_at"] is None

    def test_updated_at_is_none_when_last_observed_at_is_none(self) -> None:
        """updated_at should be None when last_observed_at is None."""
        incident = Incident(
            incident_id="test-incident-123",
            source_candidate_id="test-candidate-456",
            namespace="default",
            object_kind="Pod",
            object_name="nginx-pod",
            raw_object_kind=None,
            candidate_class="PodCrashLoop",
            severity="high",
            status=IncidentStatus.OPEN,
            first_observed_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            last_observed_at=None,
            signals=[],
            signal_count=0,
        )
        payload = build_incident_internal_detail_payload(incident)

        assert payload["updated_at"] is None

    def test_includes_signals_list(self) -> None:
        """Detail payload includes signals for diagnosis context."""
        signals = [
            IncidentSignal(
                source="detector-1",
                reason="CrashLoopBackOff detected",
                message="Container crashed 3 times in 5 minutes",
                captured_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                run_id="run-abc",
                detector_id="detector-crash",
                finding_id="finding-123",
                fingerprint="fp-xyz",
            ),
            IncidentSignal(
                source="detector-2",
                reason="High restart count",
                message="Container restart count exceeded threshold",
                captured_at=datetime(2024, 1, 15, 10, 35, 0, tzinfo=UTC),
                run_id=None,
                detector_id=None,
                finding_id=None,
                fingerprint=None,
            ),
        ]
        incident = self._make_incident(signals=signals)
        payload = build_incident_internal_detail_payload(incident)

        assert len(payload["signals"]) == 2
        assert payload["signals"][0]["source"] == "detector-1"
        assert payload["signals"][0]["reason"] == "CrashLoopBackOff detected"
        assert payload["signals"][0]["captured_at"] == "2024-01-15T10:30:00+00:00"
        assert payload["signals"][0]["run_id"] == "run-abc"
        assert payload["signals"][0]["detector_id"] == "detector-crash"
        assert payload["signals"][0]["finding_id"] == "finding-123"
        assert payload["signals"][0]["fingerprint"] == "fp-xyz"

        # Optional fields should be None when not set
        assert payload["signals"][1]["run_id"] is None
        assert payload["signals"][1]["detector_id"] is None
        assert payload["signals"][1]["finding_id"] is None
        assert payload["signals"][1]["fingerprint"] is None

    def test_empty_signals_list(self) -> None:
        """Detail payload handles empty signals list."""
        incident = self._make_incident(signals=[])
        payload = build_incident_internal_detail_payload(incident)

        assert payload["signals"] == []

    def test_signal_count_matches_actual_signals(self) -> None:
        """signal_count should reflect actual number of signals."""
        signals = [
            IncidentSignal(
                source="detector-1",
                reason="Test",
                message="Test message",
                captured_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            ),
            IncidentSignal(
                source="detector-2",
                reason="Test 2",
                message="Test message 2",
                captured_at=datetime(2024, 1, 15, 10, 35, 0, tzinfo=UTC),
            ),
            IncidentSignal(
                source="detector-3",
                reason="Test 3",
                message="Test message 3",
                captured_at=datetime(2024, 1, 15, 10, 40, 0, tzinfo=UTC),
            ),
        ]
        incident = self._make_incident(signals=signals)
        payload = build_incident_internal_detail_payload(incident)

        assert payload["signal_count"] == 3
        assert len(payload["signals"]) == 3

    def test_object_kind_is_plain_string(self) -> None:
        """object_kind should be a plain string, not enum value."""
        incident = self._make_incident()
        payload = build_incident_internal_detail_payload(incident)

        assert isinstance(payload["object_kind"], str)
        assert payload["object_kind"] == "Pod"

    def test_status_is_string_value(self) -> None:
        """status should be the string value of the enum."""
        incident = self._make_incident()
        payload = build_incident_internal_detail_payload(incident)

        assert isinstance(payload["status"], str)
        assert payload["status"] == "open"
