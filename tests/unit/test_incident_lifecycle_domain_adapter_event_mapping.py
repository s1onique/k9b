"""Tests for incident lifecycle domain adapter event mapping.

Required tests per ACT-K9B-HULK-DOMAIN-EVENT-TYPES01:
- each domain event type maps to expected IncidentEventType
- each domain actor maps to expected IncidentEventActor
- unknown event type raises ValueError
- unknown actor raises ValueError
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from k8s_diag_agent.collect.incident_events import IncidentEventActor, IncidentEventType

# Import the adapter function and mapping tables
from k8s_diag_agent.collect.incident_lifecycle_domain_adapter import (
    _DOMAIN_ACTOR_TO_STORE_ACTOR,
    _DOMAIN_EVENT_TO_STORE_EVENT,
    _map_lifecycle_event_to_incident_event,
)

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def base_time() -> datetime:
    """Standard test timestamp."""
    return datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)


# -----------------------------------------------------------------------------
# Test: Event type mapping
# -----------------------------------------------------------------------------

class TestEventTypeMapping:
    """Tests for domain event type to store event type mapping."""

    def test_incident_promoted_maps_to_opened(self, base_time: datetime) -> None:
        """incident_promoted maps to IncidentEventType.OPENED."""
        event = _create_mock_event(
            event_type="incident_promoted",
            actor="system",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.event_type == IncidentEventType.OPENED

    def test_incident_marked_collecting_evidence_maps_to_evidence_collection_started(
        self, base_time: datetime
    ) -> None:
        """incident_marked_collecting_evidence maps to EVIDENCE_COLLECTION_STARTED."""
        event = _create_mock_event(
            event_type="incident_marked_collecting_evidence",
            actor="system",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.event_type == IncidentEventType.EVIDENCE_COLLECTION_STARTED

    def test_incident_marked_ready_for_review_maps_to_review_packet_generated(
        self, base_time: datetime
    ) -> None:
        """incident_marked_ready_for_review maps to REVIEW_PACKET_GENERATED."""
        event = _create_mock_event(
            event_type="incident_marked_ready_for_review",
            actor="diagnosis_loop",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.event_type == IncidentEventType.REVIEW_PACKET_GENERATED

    def test_incident_marked_investigating_maps_to_status_changed(
        self, base_time: datetime
    ) -> None:
        """incident_marked_investigating maps to STATUS_CHANGED."""
        event = _create_mock_event(
            event_type="incident_marked_investigating",
            actor="user",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.event_type == IncidentEventType.STATUS_CHANGED

    def test_incident_suppressed_maps_to_suppressed(self, base_time: datetime) -> None:
        """incident_suppressed maps to IncidentEventType.SUPPRESSED."""
        event = _create_mock_event(
            event_type="incident_suppressed",
            actor="user",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.event_type == IncidentEventType.SUPPRESSED

    def test_incident_marked_duplicate_maps_to_marked_duplicate(
        self, base_time: datetime
    ) -> None:
        """incident_marked_duplicate maps to MARKED_DUPLICATE."""
        event = _create_mock_event(
            event_type="incident_marked_duplicate",
            actor="user",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.event_type == IncidentEventType.MARKED_DUPLICATE

    def test_incident_resolved_maps_to_closed(self, base_time: datetime) -> None:
        """incident_resolved maps to IncidentEventType.CLOSED."""
        event = _create_mock_event(
            event_type="incident_resolved",
            actor="user",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.event_type == IncidentEventType.CLOSED


# -----------------------------------------------------------------------------
# Test: Actor mapping
# -----------------------------------------------------------------------------

class TestActorMapping:
    """Tests for domain actor to store actor mapping."""

    def test_system_maps_to_system(self, base_time: datetime) -> None:
        """system maps to IncidentEventActor.SYSTEM."""
        event = _create_mock_event(
            event_type="incident_resolved",
            actor="system",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.actor == IncidentEventActor.SYSTEM

    def test_user_maps_to_user(self, base_time: datetime) -> None:
        """user maps to IncidentEventActor.USER."""
        event = _create_mock_event(
            event_type="incident_resolved",
            actor="user",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.actor == IncidentEventActor.USER

    def test_diagnosis_loop_maps_to_system(self, base_time: datetime) -> None:
        """diagnosis_loop maps to IncidentEventActor.SYSTEM (explicit mapping)."""
        event = _create_mock_event(
            event_type="incident_resolved",
            actor="diagnosis_loop",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.actor == IncidentEventActor.SYSTEM

    def test_test_maps_to_system(self, base_time: datetime) -> None:
        """test maps to IncidentEventActor.SYSTEM (explicit mapping)."""
        event = _create_mock_event(
            event_type="incident_resolved",
            actor="test",
            incident_id="test-1",
            created_at=base_time,
        )
        result = _map_lifecycle_event_to_incident_event(event, base_time)
        assert result.actor == IncidentEventActor.SYSTEM


# -----------------------------------------------------------------------------
# Test: Unknown event type raises ValueError
# -----------------------------------------------------------------------------

class TestUnknownEventType:
    """Tests for unknown event type handling."""

    def test_unknown_event_type_raises_value_error(self, base_time: datetime) -> None:
        """Unknown event type raises ValueError."""
        event = _create_mock_event(
            event_type="unknown_event_type",
            actor="system",
            incident_id="test-1",
            created_at=base_time,
        )
        with pytest.raises(ValueError) as exc_info:
            _map_lifecycle_event_to_incident_event(event, base_time)
        assert "unmapped lifecycle event type" in str(exc_info.value)
        assert "unknown_event_type" in str(exc_info.value)


# -----------------------------------------------------------------------------
# Test: Unknown actor raises ValueError
# -----------------------------------------------------------------------------

class TestUnknownActor:
    """Tests for unknown actor handling."""

    def test_unknown_actor_raises_value_error(self, base_time: datetime) -> None:
        """Unknown actor raises ValueError."""
        event = _create_mock_event(
            event_type="incident_resolved",
            actor="unknown_actor",
            incident_id="test-1",
            created_at=base_time,
        )
        with pytest.raises(ValueError) as exc_info:
            _map_lifecycle_event_to_incident_event(event, base_time)
        assert "unmapped lifecycle actor" in str(exc_info.value)
        assert "unknown_actor" in str(exc_info.value)


# -----------------------------------------------------------------------------
# Test: Mapping table completeness
# -----------------------------------------------------------------------------

class TestMappingTableCompleteness:
    """Tests for mapping table completeness."""

    def test_event_mapping_has_all_domain_events(self) -> None:
        """_DOMAIN_EVENT_TO_STORE_EVENT has all expected keys."""
        expected_keys = {
            "incident_promoted",
            "incident_marked_collecting_evidence",
            "incident_marked_ready_for_review",
            "incident_marked_investigating",
            "incident_suppressed",
            "incident_marked_duplicate",
            "incident_resolved",
        }
        assert set(_DOMAIN_EVENT_TO_STORE_EVENT.keys()) == expected_keys

    def test_actor_mapping_has_all_domain_actors(self) -> None:
        """_DOMAIN_ACTOR_TO_STORE_ACTOR has all expected keys."""
        expected_keys = {
            "system",
            "user",
            "diagnosis_loop",
            "test",
        }
        assert set(_DOMAIN_ACTOR_TO_STORE_ACTOR.keys()) == expected_keys


# -----------------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------------

def _create_mock_event(
    event_type: str,
    actor: str,
    incident_id: str,
    created_at: datetime,
    detail: str | None = None,
) -> object:
    """Create a mock domain event object for testing."""
    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True, kw_only=True)
    class MockDomainEvent:
        event_type: str
        actor: str
        incident_id: str
        created_at: datetime
        detail: str | None = None

    return MockDomainEvent(
        event_type=event_type,
        actor=actor,
        incident_id=incident_id,
        created_at=created_at,
        detail=detail,
    )
