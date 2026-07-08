"""Tests for rebuild_projection functions.

Tests the rebuild_projection and rebuild_projection_for_incident functions.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
    StoredEvent,
    compute_event_sha256,
    compute_payload_sha256,
)
from k8s_diag_agent.collect.incident_store_sqlite_projection import (
    rebuild_projection,
    rebuild_projection_for_incident,
)


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Provide a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_incidents.sqlite3"


@pytest.fixture
def temp_db_conn(temp_db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Provide a configured SQLite connection with schema."""
    from k8s_diag_agent.collect.incident_store_sqlite_migrations import run_migrations

    conn = sqlite3.connect(str(temp_db_path))
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    yield conn
    conn.close()


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


def insert_event(conn: sqlite3.Connection, event: StoredEvent) -> None:
    """Insert a test event into the database."""
    conn.execute(
        """
        INSERT INTO incident_events (
            event_seq, event_id, incident_id, aggregate_version, event_type,
            occurred_at, actor, actor_id, payload_json, payload_sha256,
            previous_event_sha256, event_sha256, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            None,  # event_seq is autoincrement
            event.event_id,
            event.incident_id,
            event.aggregate_version,
            event.event_type,
            event.occurred_at.isoformat(),
            event.actor,
            event.actor_id,
            event.payload_json,
            event.payload_sha256,
            event.previous_event_sha256,
            event.event_sha256,
            event.created_at.isoformat(),
        ),
    )
    conn.commit()


class TestRebuildProjectionForIncident:
    """Tests for rebuild_projection_for_incident function."""

    def test_rebuild_returns_none_for_nonexistent_incident(
        self, temp_db_conn: sqlite3.Connection
    ) -> None:
        """Returns None when incident has no events."""
        result = rebuild_projection_for_incident(temp_db_conn, "nonexistent-incident")
        assert result is None

    def test_rebuild_single_event(self, temp_db_conn: sqlite3.Connection) -> None:
        """Rebuilds state from a single OPENED event."""
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "cand-1",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "candidate_class": "crash_loop",
                "severity": "error",
            },
        )
        insert_event(temp_db_conn, event)

        result = rebuild_projection_for_incident(temp_db_conn, "test-inc-1")

        assert result is not None
        assert result["incident_id"] == "test-inc-1"
        assert result["status"] == "open"
        assert result["namespace"] == "default"
        assert result["current_state_json"] != ""

    def test_rebuild_multiple_events(self, temp_db_conn: sqlite3.Connection) -> None:
        """Rebuilds correct state from multiple events in order."""
        # Event 1: OPENED
        event1 = create_test_event(
            incident_id="test-inc-2",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "cand-1",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "candidate_class": "crash_loop",
                "severity": "error",
                "signal_count": 1,
            },
        )
        insert_event(temp_db_conn, event1)

        # Event 2: SIGNAL_OBSERVED
        event2 = create_test_event(
            incident_id="test-inc-2",
            event_type=IncidentEventType.SIGNAL_OBSERVED,
            aggregate_version=2,
            payload={
                "signal_count": 2,
                "last_observed_at": "2024-01-01T13:00:00+00:00",
            },
            previous_event_sha256=event1.event_sha256,
        )
        insert_event(temp_db_conn, event2)

        # Event 3: RESOLVED
        event3 = create_test_event(
            incident_id="test-inc-2",
            event_type=IncidentEventType.RESOLVED,
            aggregate_version=3,
            payload={"notes": "Fixed"},
            previous_event_sha256=event2.event_sha256,
        )
        insert_event(temp_db_conn, event3)

        result = rebuild_projection_for_incident(temp_db_conn, "test-inc-2")

        assert result is not None
        assert result["status"] == "resolved"
        assert result["signal_count"] == 2
        assert result["resolved_at"] is not None
        assert result["resolution_notes"] == "Fixed"
        assert result["aggregate_version"] == 3

    def test_rebuild_does_not_include_other_incident_events(
        self, temp_db_conn: sqlite3.Connection
    ) -> None:
        """Rebuild filters to only the specified incident."""
        # Event for incident 1
        event1 = create_test_event(
            incident_id="other-inc",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "cand-other",
                "namespace": "kube-system",
                "object_kind": "Node",
                "object_name": "other-node",
                "candidate_class": "unreachable",
                "severity": "critical",
            },
        )
        insert_event(temp_db_conn, event1)

        # Event for incident 2
        event2 = create_test_event(
            incident_id="test-inc-3",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "cand-3",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "my-pod",
                "candidate_class": "crash_loop",
                "severity": "warning",
            },
        )
        insert_event(temp_db_conn, event2)

        result = rebuild_projection_for_incident(temp_db_conn, "test-inc-3")

        assert result is not None
        assert result["incident_id"] == "test-inc-3"
        assert result["namespace"] == "default"
        assert result["object_name"] == "my-pod"


class TestRebuildProjection:
    """Tests for rebuild_projection function."""

    def test_rebuild_empty_db(self, temp_db_conn: sqlite3.Connection) -> None:
        """Rebuilding empty DB returns 0."""
        count = rebuild_projection(temp_db_conn)
        assert count == 0

    def test_rebuild_single_incident(self, temp_db_conn: sqlite3.Connection) -> None:
        """Rebuilds projection for a single incident."""
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "cand-1",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "candidate_class": "crash_loop",
                "severity": "error",
            },
        )
        insert_event(temp_db_conn, event)

        count = rebuild_projection(temp_db_conn)

        assert count == 1

        # Verify incident_current table
        cursor = temp_db_conn.execute(
            "SELECT incident_id, status, namespace FROM incident_current"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["incident_id"] == "test-inc-1"
        assert row["status"] == "open"
        assert row["namespace"] == "default"

    def test_rebuild_multiple_incidents(self, temp_db_conn: sqlite3.Connection) -> None:
        """Rebuilds projection for multiple incidents."""
        # Incident 1
        event1 = create_test_event(
            incident_id="inc-1",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "cand-1",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "pod-1",
                "candidate_class": "crash_loop",
                "severity": "error",
            },
        )
        insert_event(temp_db_conn, event1)

        # Incident 2
        event2 = create_test_event(
            incident_id="inc-2",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "cand-2",
                "namespace": "kube-system",
                "object_kind": "Node",
                "object_name": "node-1",
                "candidate_class": "unreachable",
                "severity": "critical",
            },
        )
        insert_event(temp_db_conn, event2)

        count = rebuild_projection(temp_db_conn)

        assert count == 2

        # Verify both incidents in projection
        cursor = temp_db_conn.execute(
            "SELECT incident_id FROM incident_current ORDER BY incident_id"
        )
        rows = cursor.fetchall()
        assert len(rows) == 2
        assert rows[0]["incident_id"] == "inc-1"
        assert rows[1]["incident_id"] == "inc-2"

    def test_rebuild_clears_existing_projection(
        self, temp_db_conn: sqlite3.Connection
    ) -> None:
        """Rebuild clears existing projection before rebuilding."""
        # First build
        event1 = create_test_event(
            incident_id="test-inc",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "cand-1",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "pod-1",
                "candidate_class": "crash_loop",
                "severity": "error",
            },
        )
        insert_event(temp_db_conn, event1)

        rebuild_projection(temp_db_conn)

        # Manually add a stale entry
        temp_db_conn.execute(
            """
            INSERT OR IGNORE INTO incident_current (
                incident_id, aggregate_version, source_candidate_id,
                namespace, object_kind, object_name, raw_object_kind,
                candidate_class, severity, status, first_observed_at,
                last_observed_at, current_state_json, last_event_seq, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "stale-incident",
                1,
                "stale-candidate",
                "stale-ns",
                "Pod",
                "stale-pod",
                None,
                "crash_loop",
                "warning",
                "open",
                "2024-01-01T10:00:00+00:00",
                "2024-01-01T10:00:00+00:00",
                "{}",
                1,
                "2024-01-01T10:00:00+00:00",
            ),
        )
        temp_db_conn.commit()

        # Rebuild should only have the incident from events
        count = rebuild_projection(temp_db_conn)

        assert count == 1

        cursor = temp_db_conn.execute(
            "SELECT incident_id FROM incident_current"
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["incident_id"] == "test-inc"
