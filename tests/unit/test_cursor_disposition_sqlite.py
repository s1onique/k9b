"""Tests for cursor disposition logic with real SQLite pagination."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import TestCase

from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    DiagnosisPageLimit,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)


class TestCursorDispositionWithSQLite(TestCase):
    """Test cursor disposition logic with real SQLite pagination."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "cursor_test.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _create_incidents(self, num_incidents: int) -> None:
        """Create incidents directly in SQLite."""
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        from k8s_diag_agent.collect.incident_store_sqlite_migrations import (
            run_migrations,
        )

        run_migrations(conn)

        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        for i in range(num_incidents):
            incident_id = f"cursor-test-{i:03d}"
            ts = base_time + timedelta(seconds=i)
            event_sha = f"sha256-evt-{uuid.uuid4().hex[:16]}"

            conn.execute(
                """
                INSERT INTO incident_events
                (event_id, incident_id, aggregate_version, event_type, occurred_at,
                 actor, actor_id, payload_json, payload_sha256,
                 previous_event_sha256, event_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt-{incident_id}-001",
                    incident_id,
                    1,
                    IncidentEventType.OPENED.value,
                    ts.isoformat(),
                    IncidentEventActor.SYSTEM.value,
                    None,
                    '{"namespace": "default"}',
                    event_sha,
                    event_sha,
                    event_sha,
                    datetime.now(UTC).isoformat(),
                ),
            )

            state = {
                "incident_id": incident_id,
                "status": IncidentStatus.OPEN.value,
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": f"pod-{i}",
                "first_observed_at": ts.isoformat(),
                "last_observed_at": ts.isoformat(),
            }

            conn.execute(
                """
                INSERT INTO incident_current
                (incident_id, aggregate_version, source_candidate_id, namespace,
                 object_kind, object_name, candidate_class, severity, status,
                 first_observed_at, last_observed_at, current_state_json,
                 last_event_seq, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    1,
                    f"candidate-{incident_id}",
                    "default",
                    "Pod",
                    f"pod-{i}",
                    "crash_loop",
                    "error",
                    IncidentStatus.OPEN.value,
                    ts.isoformat(),
                    ts.isoformat(),
                    json.dumps(state),
                    1,
                    datetime.now(UTC).isoformat(),
                ),
            )

        conn.commit()
        conn.close()

    def test_final_page_cursor_disposition(self) -> None:
        """Verify cursor disposition on final page (has_more=False)."""
        self._create_incidents(5)
        store = SQLiteIncidentStore(self._db_path)

        page = store.list_incidents_for_diagnosis_page(
            active_only=True,
            limit=DiagnosisPageLimit(10),
            after_cursor=None,
        )

        self.assertEqual(len(page.incidents), 5)
        self.assertFalse(page.has_more)
        self.assertIsNone(page.next_cursor)

    def test_has_more_triggers_save(self) -> None:
        """Verify has_more=True requires next_cursor for save."""
        self._create_incidents(10)
        store = SQLiteIncidentStore(self._db_path)

        page = store.list_incidents_for_diagnosis_page(
            active_only=True,
            limit=DiagnosisPageLimit(5),
            after_cursor=None,
        )

        self.assertEqual(len(page.incidents), 5)
        self.assertTrue(page.has_more)
        self.assertIsNotNone(page.next_cursor)
        self.assertEqual(
            page.next_cursor.incident_id,
            page.incidents[-1].incident_id,
        )


__all__ = ["TestCursorDispositionWithSQLite"]
