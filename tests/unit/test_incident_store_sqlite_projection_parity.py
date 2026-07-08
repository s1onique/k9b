"""Tests for projection parity between live updates and full rebuilds.

This is the key correctness invariant for event sourcing: events are the source
of truth, and both live updates (via update_projection_for_event) and full rebuilds
(via rebuild_projection_for_incident) must produce identical state.
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
    rebuild_projection_for_incident,
)
from k8s_diag_agent.collect.incident_store_sqlite_queries import (
    update_projection_for_event,
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


class TestProjectionParity:
    """Tests that live projection matches rebuilt projection.

    This is the key correctness invariant: events are the source of truth,
    and both live updates and full rebuilds must produce identical state.
    """

    def test_live_and_rebuilt_projection_match(
        self, temp_db_conn: sqlite3.Connection
    ) -> None:
        """Live incident_current equals rebuilt incident_current after same events.

        This proves the projection unification is deterministic:
        - update_projection_for_event() uses canonical apply_event_to_state()
        - rebuild_projection() uses same canonical apply_event_to_state()
        Both paths must produce identical current_state_json.
        """
        # Create a sequence of events for an incident
        event1 = create_test_event(
            incident_id="parity-test-inc",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "cand-parity",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "parity-pod",
                "candidate_class": "crash_loop",
                "severity": "error",
                "signal_count": 1,
            },
        )
        insert_event(temp_db_conn, event1)
        update_projection_for_event(temp_db_conn, event1)

        event2 = create_test_event(
            incident_id="parity-test-inc",
            event_type=IncidentEventType.COLLECTING_EVIDENCE_STARTED,
            aggregate_version=2,
            payload={
                "bundle_id": "bundle-123",
                "status": "collecting_evidence",
                "evidence_links": [{"artifact_id": "art-1", "role": "snapshot"}],
                "evidence_count": 1,
            },
            previous_event_sha256=event1.event_sha256,
        )
        insert_event(temp_db_conn, event2)
        update_projection_for_event(temp_db_conn, event2)

        event3 = create_test_event(
            incident_id="parity-test-inc",
            event_type=IncidentEventType.MARKED_DUPLICATE,
            aggregate_version=3,
            payload={
                "duplicate_of": "other-incident-456",
                "previous_status": "collecting_evidence",
                "status": "duplicate",
            },
            previous_event_sha256=event2.event_sha256,
        )
        insert_event(temp_db_conn, event3)
        update_projection_for_event(temp_db_conn, event3)

        # Get live projection state
        cursor = temp_db_conn.execute(
            "SELECT current_state_json FROM incident_current WHERE incident_id = ?",
            ("parity-test-inc",),
        )
        live_row = cursor.fetchone()
        assert live_row is not None
        live_state = json.loads(live_row[0])

        # Delete projection and rebuild
        temp_db_conn.execute(
            "DELETE FROM incident_current WHERE incident_id = ?", ("parity-test-inc",)
        )
        temp_db_conn.commit()

        rebuilt_state = rebuild_projection_for_incident(temp_db_conn, "parity-test-inc")
        assert rebuilt_state is not None
        rebuilt_json = json.loads(rebuilt_state["current_state_json"])

        # Parity check: live and rebuilt must match
        # Compare key fields that should be identical
        assert live_state["incident_id"] == rebuilt_json["incident_id"]
        assert live_state["status"] == rebuilt_json["status"]  # "duplicate"
        assert (
            live_state["duplicate_of"] == rebuilt_json["duplicate_of"]
        )  # "other-incident-456"
        assert live_state["namespace"] == rebuilt_json["namespace"]  # "default"
        assert live_state["object_name"] == rebuilt_json["object_name"]  # "parity-pod"
        assert live_state["severity"] == rebuilt_json["severity"]  # "error"
        assert (
            live_state["aggregate_version"] == rebuilt_json["aggregate_version"]
        )  # 3
        assert live_state["signal_count"] == rebuilt_json["signal_count"]  # 1

        # Full JSON equality for complete proof
        assert live_state == rebuilt_json, (
            f"Live and rebuilt projections differ!\n"
            f"Live: {live_state}\n"
            f"Rebuilt: {rebuilt_json}"
        )

    def test_mark_duplicate_projection_parity(
        self, temp_db_conn: sqlite3.Connection
    ) -> None:
        """Live and rebuilt projections match for MARKED_DUPLICATE event.

        This was a runtime bug where MARKED_DUPLICATE was incorrectly used
        instead of the proper enum, causing crashes. This test verifies the
        fix works correctly in the projection path.
        """
        # OPENED event
        event1 = create_test_event(
            incident_id="duplicate-parity",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "cand-dup",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "dup-pod",
                "candidate_class": "crash_loop",
                "severity": "warning",
            },
        )
        insert_event(temp_db_conn, event1)
        update_projection_for_event(temp_db_conn, event1)

        # MARKED_DUPLICATE event (the bug was here)
        event2 = create_test_event(
            incident_id="duplicate-parity",
            event_type=IncidentEventType.MARKED_DUPLICATE,
            aggregate_version=2,
            payload={
                "duplicate_of": "original-incident-123",
                "previous_status": "open",
                "status": "duplicate",
            },
            previous_event_sha256=event1.event_sha256,
        )
        insert_event(temp_db_conn, event2)
        update_projection_for_event(temp_db_conn, event2)

        # Get live projection
        cursor = temp_db_conn.execute(
            "SELECT current_state_json FROM incident_current WHERE incident_id = ?",
            ("duplicate-parity",),
        )
        live_row = cursor.fetchone()
        assert live_row is not None
        live_state = json.loads(live_row[0])

        # Rebuild
        temp_db_conn.execute(
            "DELETE FROM incident_current WHERE incident_id = ?", ("duplicate-parity",)
        )
        temp_db_conn.commit()
        rebuilt_state = rebuild_projection_for_incident(temp_db_conn, "duplicate-parity")
        assert rebuilt_state is not None
        rebuilt_json = json.loads(rebuilt_state["current_state_json"])

        # Verify both have correct duplicate status
        assert live_state["status"] == "duplicate"
        assert rebuilt_json["status"] == "duplicate"
        assert live_state["duplicate_of"] == "original-incident-123"
        assert rebuilt_json["duplicate_of"] == "original-incident-123"
        assert live_state == rebuilt_json

    def test_imported_event_first_projection_parity(
        self, temp_db_conn: sqlite3.Connection
    ) -> None:
        """Live and rebuilt projections match when IMPORTED is the first event.

        This tests the edge case where an incident is imported as the first event,
        proving that update_projection_for_event() uses the canonical projector
        for new incidents (not create_initial_state).
        """
        # IMPORTED event as first event
        event1 = create_test_event(
            incident_id="imported-incident",
            event_type=IncidentEventType.IMPORTED,
            aggregate_version=1,
            payload={
                "incident_id": "imported-incident",
                "source_candidate_id": "imported-candidate",
                "namespace": "default",
                "object_kind": "Deployment",
                "object_name": "imported-deployment",
                "candidate_class": "crash_loop",
                "severity": "warning",
                "status": "open",
                "first_observed_at": "2024-01-01T10:00:00+00:00",
                "last_observed_at": "2024-01-01T12:00:00+00:00",
                "signal_count": 5,
                "evidence_count": 2,
            },
        )
        insert_event(temp_db_conn, event1)
        update_projection_for_event(temp_db_conn, event1)

        # Get live projection
        cursor = temp_db_conn.execute(
            "SELECT current_state_json FROM incident_current WHERE incident_id = ?",
            ("imported-incident",),
        )
        live_row = cursor.fetchone()
        assert live_row is not None
        live_state = json.loads(live_row[0])

        # Rebuild
        temp_db_conn.execute(
            "DELETE FROM incident_current WHERE incident_id = ?", ("imported-incident",)
        )
        temp_db_conn.commit()
        rebuilt_state = rebuild_projection_for_incident(temp_db_conn, "imported-incident")
        assert rebuilt_state is not None
        rebuilt_json = json.loads(rebuilt_state["current_state_json"])

        # Verify both have correct imported state
        assert live_state["incident_id"] == "imported-incident"
        assert rebuilt_json["incident_id"] == "imported-incident"
        assert live_state["namespace"] == "default"
        assert rebuilt_json["namespace"] == "default"
        assert live_state["object_name"] == "imported-deployment"
        assert rebuilt_json["object_name"] == "imported-deployment"
        assert live_state["signal_count"] == 5
        assert rebuilt_json["signal_count"] == 5
        assert live_state == rebuilt_json
