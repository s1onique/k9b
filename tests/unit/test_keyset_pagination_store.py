"""Unit tests for keyset pagination in incident store.

These tests verify:
1. Results are ordered by first_observed_at, then incident_id
2. Equal timestamps are deterministically ordered by incident ID
3. Page two starts strictly after the final key from page one
4. Keyset pagination works with status filtering
5. Empty page behavior

Uses SQLite in-memory database for testing.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC

from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
    list_incidents_for_diagnosis_page_impl,
)
from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    DiagnosisPageLimit,
    make_test_cursor,
)
from k8s_diag_agent.collect.incident_store_sqlite_schema import (
    get_schema_sql,
)


class TestKeysetPaginationOrdering:
    """Tests for ordering guarantees."""

    def test_results_ordered_by_first_observed_at_asc(self) -> None:
        """Results are ordered by first_observed_at ASC."""
        with _create_test_db() as conn:
            # Insert incidents with different timestamps
            _insert_incident(conn, "inc-003", "open", "2024-01-03T10:00:00+00:00")
            _insert_incident(conn, "inc-001", "open", "2024-01-01T10:00:00+00:00")
            _insert_incident(conn, "inc-002", "open", "2024-01-02T10:00:00+00:00")

            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(10), after=None
            )

            # Verify ordering: first_observed_at ASC
            assert len(page.incidents) == 3
            assert page.incidents[0].incident_id == "inc-001"  # Jan 1
            assert page.incidents[1].incident_id == "inc-002"  # Jan 2
            assert page.incidents[2].incident_id == "inc-003"  # Jan 3
            assert page.has_more is False

    def test_equal_timestamps_ordered_by_incident_id_asc(self) -> None:
        """Equal timestamps are deterministically ordered by incident_id ASC."""
        with _create_test_db() as conn:
            # Insert incidents with the SAME timestamp but different IDs
            ts = "2024-01-15T10:00:00+00:00"
            _insert_incident(conn, "inc-c", "open", ts)
            _insert_incident(conn, "inc-a", "open", ts)
            _insert_incident(conn, "inc-b", "open", ts)

            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(10), after=None
            )

            # Verify deterministic ordering when timestamps are equal
            assert len(page.incidents) == 3
            assert page.incidents[0].incident_id == "inc-a"  # Alphabetical
            assert page.incidents[1].incident_id == "inc-b"
            assert page.incidents[2].incident_id == "inc-c"

    def test_complex_mixed_ordering(self) -> None:
        """Mixed timestamps and IDs are ordered correctly."""
        with _create_test_db() as conn:
            # Insert in random order
            _insert_incident(conn, "inc-z", "open", "2024-01-02T10:00:00+00:00")
            _insert_incident(conn, "inc-a", "open", "2024-01-01T10:00:00+00:00")
            _insert_incident(conn, "inc-b", "open", "2024-01-01T12:00:00+00:00")
            _insert_incident(conn, "inc-y", "open", "2024-01-02T08:00:00+00:00")

            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(10), after=None
            )

            # Verify complete ordering
            assert len(page.incidents) == 4
            assert page.incidents[0].incident_id == "inc-a"   # Jan 1 10:00
            assert page.incidents[1].incident_id == "inc-b"    # Jan 1 12:00
            assert page.incidents[2].incident_id == "inc-y"   # Jan 2 08:00
            assert page.incidents[3].incident_id == "inc-z"    # Jan 2 10:00


class TestKeysetPaginationCursor:
    """Tests for cursor-based pagination."""

    def test_page_two_starts_after_page_one_final_key(self) -> None:
        """Page two starts strictly after the final key from page one."""
        with _create_test_db() as conn:
            # Insert 5 incidents
            for i in range(1, 6):
                _insert_incident(conn, f"inc-{i:02d}", "open", f"2024-01-{i:02d}T10:00:00+00:00")

            # Get first page of 2
            page1 = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(2), after=None
            )

            assert len(page1.incidents) == 2
            assert page1.incidents[0].incident_id == "inc-01"
            assert page1.incidents[1].incident_id == "inc-02"
            assert page1.has_more is True
            assert page1.next_cursor is not None

            # Get second page using cursor
            page2 = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(2), after=page1.next_cursor
            )

            assert len(page2.incidents) == 2
            assert page2.incidents[0].incident_id == "inc-03"  # Strictly after inc-02
            assert page2.incidents[1].incident_id == "inc-04"
            assert page2.has_more is True
            assert page2.next_cursor is not None

            # Get third page
            page3 = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(2), after=page2.next_cursor
            )

            assert len(page3.incidents) == 1  # Only one left
            assert page3.incidents[0].incident_id == "inc-05"
            assert page3.has_more is False
            assert page3.next_cursor is None

    def test_cursor_at_end_returns_empty_page(self) -> None:
        """Cursor at end of data returns empty page with has_more=False."""
        with _create_test_db() as conn:
            _insert_incident(conn, "inc-01", "open", "2024-01-01T10:00:00+00:00")

            # Create cursor pointing to the only incident
            cursor = make_test_cursor(
                first_observed_at_text="2024-01-01T10:00:00+00:00",
                incident_id="inc-01",
            )

            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(10), after=cursor
            )

            assert len(page.incidents) == 0
            assert page.has_more is False
            assert page.next_cursor is None

    def test_cursor_to_nonexistent_incident_returns_all(self) -> None:
        """Cursor to deleted/non-existent incident returns entries after cursor."""
        with _create_test_db() as conn:
            _insert_incident(conn, "inc-01", "open", "2024-01-01T10:00:00+00:00")
            _insert_incident(conn, "inc-02", "open", "2024-01-02T10:00:00+00:00")

            # Cursor to non-existent incident
            cursor = make_test_cursor(
                first_observed_at_text="2024-01-01T10:00:00+00:00",
                incident_id="inc-does-not-exist",
            )

            # "inc-does-not-exist" > "inc-01" alphabetically
            # So cursor (2024-01-01, "inc-does-not-exist") is AFTER inc-01
            # Query returns entries > cursor, which is inc-02 (next day)
            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(10), after=cursor
            )

            # Only inc-02 is returned (inc-01 is before cursor)
            assert len(page.incidents) == 1
            assert page.incidents[0].incident_id == "inc-02"

    def test_cursor_with_same_timestamp_different_id(self) -> None:
        """Cursor correctly handles same timestamp, different incident ID."""
        with _create_test_db() as conn:
            ts = "2024-01-15T10:00:00+00:00"
            _insert_incident(conn, "inc-aaa", "open", ts)
            _insert_incident(conn, "inc-bbb", "open", ts)
            _insert_incident(conn, "inc-ccc", "open", ts)

            # Cursor at (2024-01-15, "inc-aaa") - should return inc-bbb and inc-ccc
            cursor = make_test_cursor(
                first_observed_at_text=ts,
                incident_id="inc-aaa",
            )

            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(10), after=cursor
            )

            assert len(page.incidents) == 2
            assert page.incidents[0].incident_id == "inc-bbb"
            assert page.incidents[1].incident_id == "inc-ccc"


class TestKeysetPaginationStatus:
    """Tests for status filtering with pagination."""

    def test_active_only_filters_closed_incidents(self) -> None:
        """active_only=True filters out resolved/closed incidents."""
        with _create_test_db() as conn:
            _insert_incident(conn, "inc-01", "open", "2024-01-01T10:00:00+00:00")
            _insert_incident(conn, "inc-02", "resolved", "2024-01-02T10:00:00+00:00")
            _insert_incident(conn, "inc-03", "open", "2024-01-03T10:00:00+00:00")
            _insert_incident(conn, "inc-04", "collecting_evidence", "2024-01-04T10:00:00+00:00")

            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(10), after=None
            )

            # Only active statuses: open, collecting_evidence, investigating
            assert len(page.incidents) == 3
            assert page.incidents[0].incident_id == "inc-01"
            assert page.incidents[1].incident_id == "inc-03"
            assert page.incidents[2].incident_id == "inc-04"
            # inc-02 (resolved) should not appear

    def test_active_only_with_pagination(self) -> None:
        """Pagination works correctly with active_only filter."""
        with _create_test_db() as conn:
            _insert_incident(conn, "inc-01", "open", "2024-01-01T10:00:00+00:00")
            _insert_incident(conn, "inc-02", "resolved", "2024-01-02T10:00:00+00:00")
            _insert_incident(conn, "inc-03", "open", "2024-01-03T10:00:00+00:00")
            _insert_incident(conn, "inc-04", "investigating", "2024-01-04T10:00:00+00:00")

            # First page of 2 active incidents
            page1 = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(2), after=None
            )

            assert len(page1.incidents) == 2
            assert page1.incidents[0].incident_id == "inc-01"
            assert page1.incidents[1].incident_id == "inc-03"
            assert page1.has_more is True

            # Second page
            page2 = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(2), after=page1.next_cursor
            )

            assert len(page2.incidents) == 1
            assert page2.incidents[0].incident_id == "inc-04"
            assert page2.has_more is False


class TestKeysetPaginationEdge:
    """Edge case tests."""

    def test_empty_database_returns_empty_page(self) -> None:
        """Empty database returns empty page."""
        with _create_test_db() as conn:
            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(10), after=None
            )

            assert len(page.incidents) == 0
            assert page.has_more is False
            assert page.next_cursor is None

    def test_limit_one_returns_correctly(self) -> None:
        """Limit of 1 returns correct page info."""
        with _create_test_db() as conn:
            _insert_incident(conn, "inc-01", "open", "2024-01-01T10:00:00+00:00")
            _insert_incident(conn, "inc-02", "open", "2024-01-02T10:00:00+00:00")

            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(1), after=None
            )

            assert len(page.incidents) == 1
            assert page.incidents[0].incident_id == "inc-01"
            assert page.has_more is True  # More exists
            assert page.next_cursor is not None

    def test_limit_exceeds_total_returns_all(self) -> None:
        """Limit exceeding total returns all data with has_more=False."""
        with _create_test_db() as conn:
            _insert_incident(conn, "inc-01", "open", "2024-01-01T10:00:00+00:00")
            _insert_incident(conn, "inc-02", "open", "2024-01-02T10:00:00+00:00")
            _insert_incident(conn, "inc-03", "open", "2024-01-03T10:00:00+00:00")

            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(100), after=None
            )

            assert len(page.incidents) == 3
            assert page.has_more is False
            assert page.next_cursor is None

    def test_cursor_with_different_timestamps(self) -> None:
        """Cursor handles different timestamps correctly."""
        with _create_test_db() as conn:
            # Use timestamps without microseconds to ensure consistent comparison
            _insert_incident(conn, "inc-01", "open", "2024-01-01T10:00:00+00:00")
            _insert_incident(conn, "inc-02", "open", "2024-01-01T11:00:00+00:00")
            _insert_incident(conn, "inc-03", "open", "2024-01-01T12:00:00+00:00")

            # Cursor at (10:00:00, "inc-01")
            cursor = make_test_cursor(
                first_observed_at_text="2024-01-01T10:00:00+00:00",
                incident_id="inc-01",
            )

            page = list_incidents_for_diagnosis_page_impl(
                conn, active_only=True, limit=DiagnosisPageLimit(10), after=cursor
            )

            # inc-02 and inc-03 should be returned (strictly after cursor)
            assert len(page.incidents) == 2
            assert page.incidents[0].incident_id == "inc-02"
            assert page.incidents[1].incident_id == "inc-03"


# =============================================================================
# Test Helpers
# =============================================================================


def _create_test_db() -> sqlite3.Connection:
    """Create an in-memory SQLite database with the incident schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create schema
    for sql in get_schema_sql():
        conn.executescript(sql)

    conn.commit()
    return conn


def _insert_incident(
    conn: sqlite3.Connection,
    incident_id: str,
    status: str,
    first_observed_at: str,
    namespace: str = "default",
) -> None:
    """Insert an incident into the test database."""
    import hashlib
    import json
    from datetime import datetime

    # Create current state JSON
    state = {
        "incident_id": incident_id,
        "namespace": namespace,
        "object_kind": "Pod",
        "object_name": f"test-{incident_id}",
        "candidate_class": "CrashLoopBackOff",
        "severity": "error",
        "status": status,
        "first_observed_at": first_observed_at,
        "last_observed_at": first_observed_at,
        "aggregate_version": 1,
    }

    now = datetime.now(UTC).isoformat()

    conn.execute(
        """
        INSERT INTO incident_current (
            incident_id, aggregate_version, source_candidate_id,
            namespace, object_kind, object_name, raw_object_kind,
            candidate_class, severity, status,
            first_observed_at, last_observed_at,
            current_state_json, last_event_seq, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            incident_id,
            1,
            f"candidate-{incident_id}",
            namespace,
            "Pod",
            f"test-{incident_id}",
            None,
            "CrashLoopBackOff",
            "error",
            status,
            first_observed_at,
            first_observed_at,
            json.dumps(state),
            1,
            now,
        ),
    )

    # Also insert an event for completeness
    event_payload = json.dumps(state)
    event_sha256 = hashlib.sha256(event_payload.encode()).hexdigest()

    conn.execute(
        """
        INSERT INTO incident_events (
            event_id, incident_id, aggregate_version, event_type,
            occurred_at, actor, actor_id, payload_json, payload_sha256,
            event_sha256, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"evt-{incident_id}-1",
            incident_id,
            1,
            "INCIDENT_OPENED",
            first_observed_at,
            "system",
            None,
            event_payload,
            hashlib.sha256(event_payload.encode()).hexdigest(),
            event_sha256,
            now,
        ),
    )

    conn.commit()
