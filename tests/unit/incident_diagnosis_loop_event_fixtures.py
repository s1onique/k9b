"""Fixtures for diagnosis loop event tests.

This module provides shared test helpers for diagnosis loop event transition tests.
Kept minimal and explicit - no clever factories that obscure payload shapes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_lifecycle import Incident

# Test timestamps - shared across all event tests
TEST_TIME_1 = datetime(2026, 6, 21, 0, 0, 0, tzinfo=UTC)
TEST_TIME_2 = datetime(2026, 6, 21, 0, 1, 0, tzinfo=UTC)
TEST_TIME_3 = datetime(2026, 6, 21, 0, 2, 0, tzinfo=UTC)


def make_test_incident(
    incident_id: str = "test-incident",
    events: list | None = None,
) -> Incident:
    """Create a minimal test incident.

    Args:
        incident_id: Unique identifier for the incident
        events: Optional list of incident events

    Returns:
        Incident instance suitable for testing
    """
    return Incident(
        incident_id=incident_id,
        source_candidate_id="candidate-123",
        namespace="default",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind=None,
        candidate_class="crash_loop",
        severity="error",
        status="open",
        first_observed_at=TEST_TIME_1,
        last_observed_at=TEST_TIME_1,
        events=events or [],
    )
