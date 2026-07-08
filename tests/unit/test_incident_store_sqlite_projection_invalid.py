"""Tests for invalid event type handling.

Tests the apply_event_to_state function with unknown/invalid event types.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
    StoredEvent,
    compute_event_sha256,
    compute_payload_sha256,
)
from k8s_diag_agent.collect.incident_store_sqlite_projection import apply_event_to_state


def create_test_event(
    incident_id: str,
    event_type: str,
    aggregate_version: int,
    payload: dict[str, Any],
    occurred_at: datetime | None = None,
    event_id: str | None = None,
    previous_event_sha256: str | None = None,
) -> StoredEvent:
    """Helper to create a test StoredEvent."""
    if occurred_at is None:
        occurred_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    if event_id is None:
        event_id = f"{incident_id}-{event_type}-{aggregate_version}"

    payload_sha256 = compute_payload_sha256(payload)

    event_sha256 = compute_event_sha256(
        event_id=event_id,
        incident_id=incident_id,
        aggregate_version=aggregate_version,
        event_type=event_type,
        occurred_at=occurred_at,
        actor=IncidentEventActor.SYSTEM.value,
        actor_id=None,
        payload_sha256=payload_sha256,
        previous_event_sha256=previous_event_sha256,
    )

    return StoredEvent(
        event_seq=aggregate_version,
        event_id=event_id,
        incident_id=incident_id,
        aggregate_version=aggregate_version,
        event_type=event_type,
        occurred_at=occurred_at,
        actor=IncidentEventActor.SYSTEM.value,
        actor_id=None,
        payload_json=json.dumps(payload),
        payload_sha256=payload_sha256,
        previous_event_sha256=previous_event_sha256,
        event_sha256=event_sha256,
        created_at=datetime.now(UTC),
    )


class TestInvalidEventType:
    """Tests for handling of invalid/unknown event types."""

    def test_unknown_event_type_does_not_crash(self) -> None:
        """Unknown event type is silently ignored (no-op)."""
        state: dict[str, Any] = {"status": "open"}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type="incident.unknown_type",
            aggregate_version=2,
            payload={"some_field": "some_value"},
        )

        # Should not raise
        apply_event_to_state(state, event)

        # State should be unchanged except for metadata
        assert state["status"] == "open"
        assert state["aggregate_version"] == 2
        assert state["last_event_seq"] == 2

    def test_empty_payload_handled(self) -> None:
        """Empty payload is handled gracefully."""
        state: dict[str, Any] = {}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.SUPPRESSED,
            aggregate_version=1,
            payload={},  # Empty payload
        )

        # Should not raise
        apply_event_to_state(state, event)

        assert state["status"] == "suppressed"
        assert state["suppressed_reason"] is None  # None from empty payload

    def test_missing_optional_fields_handled(self) -> None:
        """Missing optional payload fields are handled gracefully."""
        state: dict[str, Any] = {}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "namespace": "default",
                # Missing many optional fields
            },
        )

        # Should not raise
        apply_event_to_state(state, event)

        assert state["incident_id"] == "test-inc-1"
        assert state["namespace"] == "default"
        assert state["signal_count"] == 1  # Default value
        assert state["evidence_count"] == 0  # Default value
