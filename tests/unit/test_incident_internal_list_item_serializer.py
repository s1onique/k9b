"""Tests for incident internal list item serializer.

These tests verify that the internal list item serializer correctly maps
from the Incident domain model to the internal API payload.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentStatus,
)
from k8s_diag_agent.ui.api_incident_internal_reads import (
    build_incident_internal_list_item_payload,
)


def make_test_incident(
    incident_id: str = "test-incident",
    first_observed_at: datetime | None = None,
    last_observed_at: datetime | None = None,
) -> Incident:
    """Create an incident for testing with specified timestamps."""
    if first_observed_at is None:
        first_observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    if last_observed_at is None:
        last_observed_at = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

    return Incident(
        incident_id=incident_id,
        source_candidate_id="test-candidate",
        namespace="default",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind=None,
        candidate_class="crash_loop",
        severity="error",
        status=IncidentStatus.OPEN,
        first_observed_at=first_observed_at,
        last_observed_at=last_observed_at,
        signal_count=3,
        evidence_count=2,
    )


class TestBuildIncidentInternalListItemPayload(unittest.TestCase):
    """Test build_incident_internal_list_item_payload."""

    def test_maps_first_observed_at_to_created_at(self) -> None:
        """created_at must be serialized from first_observed_at."""
        first_observed = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        incident = make_test_incident(first_observed_at=first_observed)

        result = build_incident_internal_list_item_payload(incident)

        self.assertEqual(result["created_at"], first_observed.isoformat())

    def test_maps_last_observed_at_to_updated_at(self) -> None:
        """updated_at must be serialized from last_observed_at."""
        last_observed = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)
        incident = make_test_incident(last_observed_at=last_observed)

        result = build_incident_internal_list_item_payload(incident)

        self.assertEqual(result["updated_at"], last_observed.isoformat())

    def test_created_at_is_none_when_first_observed_at_is_none(self) -> None:
        """created_at must be None when first_observed_at is None."""
        # Create incident with None timestamps by using a mutable approach
        incident = make_test_incident()
        # Replace with None timestamps to test null handling
        incident.first_observed_at = None
        incident.last_observed_at = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        result = build_incident_internal_list_item_payload(incident)

        self.assertIsNone(result["created_at"])

    def test_updated_at_is_none_when_last_observed_at_is_none(self) -> None:
        """updated_at must be None when last_observed_at is None."""
        incident = make_test_incident()
        # Replace with None timestamps to test null handling
        incident.first_observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        incident.last_observed_at = None

        result = build_incident_internal_list_item_payload(incident)

        self.assertIsNone(result["updated_at"])

    def test_includes_all_required_fields(self) -> None:
        """All required fields must be present in output."""
        incident = make_test_incident()

        result = build_incident_internal_list_item_payload(incident)

        required_fields = [
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
        ]
        for field in required_fields:
            self.assertIn(field, result, f"Missing required field: {field}")

    def test_object_kind_is_plain_string(self) -> None:
        """object_kind must be a plain string, not enum.value."""
        incident = make_test_incident()

        result = build_incident_internal_list_item_payload(incident)

        # Incident.object_kind is already a str, not an enum
        self.assertIsInstance(result["object_kind"], str)
        self.assertEqual(result["object_kind"], "Pod")

    def test_status_is_string_value(self) -> None:
        """status must be the string value of the enum."""
        incident = make_test_incident()
        incident.status = IncidentStatus.OPEN

        result = build_incident_internal_list_item_payload(incident)

        self.assertIsInstance(result["status"], str)
        self.assertEqual(result["status"], "open")


class TestIncidentInternalListItemTimestampsAfterPromotion(unittest.TestCase):
    """Regression test: timestamps must be correct after incident promotion."""

    def test_timestamps_preserved_after_promotion(self) -> None:
        """Timestamps must be correctly serialized after candidate promotion.

        This is the regression test for the bug where handle_list_incidents
        failed with AttributeError because it referenced non-existent
        Incident.created_at instead of Incident.first_observed_at.
        """
        # Simulate promotion: first and last observed at same time initially
        promotion_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        incident = make_test_incident(
            first_observed_at=promotion_time,
            last_observed_at=promotion_time,
        )

        # Serialize
        result = build_incident_internal_list_item_payload(incident)

        # Both timestamps should be the promotion time
        expected = promotion_time.isoformat()
        self.assertEqual(result["created_at"], expected)
        self.assertEqual(result["updated_at"], expected)

    def test_different_first_and_last_observed(self) -> None:
        """When first_observed != last_observed, both must be serialized correctly."""
        first_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        last_time = datetime(2024, 1, 1, 14, 0, 0, tzinfo=UTC)

        incident = make_test_incident(
            first_observed_at=first_time,
            last_observed_at=last_time,
        )

        result = build_incident_internal_list_item_payload(incident)

        self.assertEqual(result["created_at"], first_time.isoformat())
        self.assertEqual(result["updated_at"], last_time.isoformat())


if __name__ == "__main__":
    unittest.main()
