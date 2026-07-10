"""Tests for backend incident fetch contract parser.

This module tests the parse_backend_incident_detail_payload() function that
validates and parses backend API responses for the scheduler's automatic diagnosis loop.

The parser ensures that:
1. Wrapped canonical incidents are accepted
2. List item summaries are rejected (missing first_observed_at)
3. UI projections missing canonical fields are rejected
4. No KeyError can escape to the caller
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
    BackendIncidentShapeError,
    parse_backend_incident_detail_payload,
)
from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentSignal,
    IncidentStatus,
)
from k8s_diag_agent.ui.api_incident_internal_reads import (
    build_incident_internal_detail_response_payload,
    build_incident_internal_list_item_payload,
)


class TestParseBackendIncidentDetailPayload:
    """Tests for parse_backend_incident_detail_payload."""

    def _make_incident(
        self,
        incident_id: str = "test-incident-123",
        first_observed: datetime | None = None,
        last_observed: datetime | None = None,
    ) -> Incident:
        """Helper to create test incidents."""
        return Incident(
            incident_id=incident_id,
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
            signals=[
                IncidentSignal(
                    source="detector-1",
                    reason="CrashLoopBackOff",
                    message="Container crashed",
                    captured_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                ),
            ],
            signal_count=1,
            evidence_count=0,
        )

    def test_parse_backend_incident_detail_payload_accepts_wrapped_canonical_incident(
        self,
    ) -> None:
        """Parser accepts wrapped canonical incident with first_observed_at."""
        incident = self._make_incident()

        # Build wrapper payload using the serializer
        payload = build_incident_internal_detail_response_payload(incident)

        # Parser should accept and return valid Incident
        restored = parse_backend_incident_detail_payload(payload)

        assert restored.incident_id == incident.incident_id
        assert restored.source_candidate_id == incident.source_candidate_id
        assert restored.first_observed_at == incident.first_observed_at
        assert restored.last_observed_at == incident.last_observed_at

    def test_parse_backend_incident_detail_payload_rejects_list_item_shape(
        self,
    ) -> None:
        """Parser rejects list item summaries missing canonical fields."""
        incident = self._make_incident()

        # Build list item payload (summary shape, NOT canonical)
        list_item = build_incident_internal_list_item_payload(incident)

        # Parser must reject list item - it's missing first_observed_at/last_observed_at
        # Note: list item uses candidate_class which is now accepted as alias,
        # so the first missing field alphabetically is first_observed_at
        with pytest.raises(BackendIncidentShapeError) as exc:
            parse_backend_incident_detail_payload(list_item)

        assert exc.value.missing_field == "first_observed_at"

    def test_parse_backend_incident_detail_payload_rejects_ui_projection_missing_first_observed_at(
        self,
    ) -> None:
        """Parser rejects UI projections missing canonical fields."""
        incident = self._make_incident()

        # Build UI-style projection with created_at/updated_at (not canonical)
        ui_projection = {
            "incident_id": incident.incident_id,
            "status": "open",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }

        # Parser must reject - missing canonical fields (class/candidate_class)
        with pytest.raises(BackendIncidentShapeError) as exc:
            parse_backend_incident_detail_payload(ui_projection)

        assert exc.value.missing_field == "class"

    def test_parse_backend_incident_detail_payload_rejects_partial_projection(
        self,
    ) -> None:
        """Parser rejects partial projections missing required fields."""
        incident = self._make_incident()

        # Partial projection with only some fields (using canonical "class" key)
        partial = {
            "incident_id": incident.incident_id,
            "source_candidate_id": incident.source_candidate_id,
            "namespace": incident.namespace,
            "object_kind": incident.object_kind,
            "object_name": incident.object_name,
            "class": incident.candidate_class,  # Canonical key
            "severity": incident.severity,
            "status": incident.status.value,
            "first_observed_at": incident.first_observed_at.isoformat(),
            # Missing last_observed_at
        }

        # Parser must reject - missing last_observed_at
        with pytest.raises(BackendIncidentShapeError) as exc:
            parse_backend_incident_detail_payload(partial)

        assert exc.value.missing_field == "last_observed_at"

    def test_parse_backend_incident_detail_payload_rejects_non_dict(self) -> None:
        """Parser rejects non-dict inputs."""
        with pytest.raises(BackendIncidentShapeError) as exc:
            parse_backend_incident_detail_payload("not a dict")

        assert exc.value.missing_field is None

    def test_parse_backend_incident_detail_payload_rejects_list(self) -> None:
        """Parser rejects list inputs."""
        with pytest.raises(BackendIncidentShapeError) as exc:
            parse_backend_incident_detail_payload(["item1", "item2"])

        assert exc.value.missing_field is None

    def test_parse_backend_incident_detail_payload_rejects_wrapper_without_incident_key(
        self,
    ) -> None:
        """Parser rejects wrapper without incident key."""
        wrapper = {
            "schema_version": "1",
            "payload_type": "incident-internal-detail",
            # Missing "incident" key
        }

        with pytest.raises(BackendIncidentShapeError) as exc:
            parse_backend_incident_detail_payload(wrapper)

        # Should fail because incident is not a dict (it's None)
        assert "incident object" in str(exc.value).lower() or exc.value.missing_field is None

    def test_parse_backend_incident_detail_payload_round_trips_through_incident_from_dict(
        self,
    ) -> None:
        """Parser result can round-trip through Incident.from_dict/to_dict."""
        incident = self._make_incident()

        # Build wrapper payload
        payload = build_incident_internal_detail_response_payload(incident)

        # Parse it
        restored = parse_backend_incident_detail_payload(payload)

        # Serialize again
        reserialized = restored.to_dict()

        # Re-parse
        re_restored = Incident.from_dict(reserialized)

        assert re_restored.incident_id == incident.incident_id
        assert re_restored.status == incident.status

    def test_parse_backend_incident_detail_payload_rejects_missing_first_observed_at(
        self,
    ) -> None:
        """Regression test: parser must reject payload missing first_observed_at.

        This test specifically validates the original bug: when the backend
        returned a projection payload with created_at/updated_at instead of
        first_observed_at/last_observed_at, Incident.from_dict() would raise
        KeyError: 'first_observed_at'.

        The fix ensures the parser validates first_observed_at is present.
        """
        incident = self._make_incident()

        # Payload with all required fields but missing first_observed_at
        # Uses created_at/updated_at like the old buggy projection
        payload = {
            "incident_id": incident.incident_id,
            "source_candidate_id": incident.source_candidate_id,
            "namespace": incident.namespace,
            "object_kind": incident.object_kind,
            "object_name": incident.object_name,
            "class": incident.candidate_class,
            "severity": incident.severity,
            "status": incident.status.value,
            "last_observed_at": incident.last_observed_at.isoformat(),
            # Missing first_observed_at (using created_at instead would still fail)
            "created_at": "2024-01-15T10:30:00+00:00",
        }

        with pytest.raises(BackendIncidentShapeError) as exc:
            parse_backend_incident_detail_payload(payload)

        assert exc.value.missing_field == "first_observed_at"

    def test_parse_backend_incident_detail_payload_accepts_candidate_class_alias(
        self,
    ) -> None:
        """Parser accepts 'candidate_class' alias for backwards compatibility."""
        # Payload using candidate_class instead of class (like projection format)
        payload = {
            "incident_id": "test-incident-789",
            "source_candidate_id": "test-candidate-abc",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "candidate_class": "PodCrashLoop",  # Using alias
            "severity": "high",
            "status": "open",
            "first_observed_at": "2024-01-15T10:30:00+00:00",
            "last_observed_at": "2024-01-15T12:45:00+00:00",
        }

        # Parser should accept candidate_class alias
        restored = parse_backend_incident_detail_payload(payload)

        assert restored.incident_id == "test-incident-789"
        assert restored.source_candidate_id == "test-candidate-abc"


class TestBackendIncidentShapeError:
    """Tests for BackendIncidentShapeError attributes."""

    def test_error_has_missing_field_attribute(self) -> None:
        """Error exposes missing_field attribute."""
        error = BackendIncidentShapeError(
            "missing required field: first_observed_at",
            missing_field="first_observed_at",
        )

        assert error.missing_field == "first_observed_at"
        assert "first_observed_at" in str(error)

    def test_error_without_missing_field(self) -> None:
        """Error can be created without missing_field."""
        error = BackendIncidentShapeError("not a dict")

        assert error.missing_field is None
