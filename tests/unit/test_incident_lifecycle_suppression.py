"""Tests for incident suppression and duplicate handling.

Covers:
- suppressed state
- duplicate state
- suppression reason recording
- duplicate target recording
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentStatus,
    mark_duplicate,
    suppress_incident,
)


def make_suppression_incident(
    status: IncidentStatus = IncidentStatus.OPEN,
    incident_id: str = "test",
) -> Incident:
    """Create an incident ready for suppression testing."""
    now = datetime.now(UTC)
    return Incident(
        incident_id=incident_id,
        source_candidate_id="test",
        namespace="default",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind=None,
        candidate_class="crash_loop",
        severity="error",
        status=status,
        first_observed_at=now,
        last_observed_at=now,
    )


class TestSuppressionTransition(unittest.TestCase):
    """Test suppress_incident state transition."""

    def test_suppress_incident_records_reason(self) -> None:
        """suppress_incident must record suppression reason."""
        incident = make_suppression_incident()

        updated = suppress_incident(incident, "known issue in maintenance window")

        self.assertEqual(updated.status, IncidentStatus.SUPPRESSED)
        self.assertEqual(updated.suppressed_reason, "known issue in maintenance window")


class TestDuplicateTransition(unittest.TestCase):
    """Test mark_duplicate state transition."""

    def test_mark_duplicate_records_duplicate_target(self) -> None:
        """mark_duplicate must record the duplicate target."""
        incident = make_suppression_incident(incident_id="duplicate-incident")

        updated = mark_duplicate(incident, "primary-incident-123")

        self.assertEqual(updated.status, IncidentStatus.DUPLICATE)
        self.assertEqual(updated.duplicate_of, "primary-incident-123")


if __name__ == "__main__":
    unittest.main()
