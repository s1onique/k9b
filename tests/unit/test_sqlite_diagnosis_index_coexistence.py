"""Production-schema coexistence planner tests for SQLite diagnosis pagination.

These tests prove the production schema (with all three indexes) uses an
order-preserving query plan for active-only pagination. Unlike isolation tests
that drop competing indexes, these tests verify the planner's behavior with
the complete production schema intact.

Required indexes in production schema:
- idx_incident_current_active_diagnosis_scan (partial index for active queries)
- idx_incident_current_diagnosis_scan (general scan index)
- idx_incident_current_status_seen (status+time index)
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import TestCase

from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
    _build_diagnosis_page_query,
)
from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    DiagnosisPageLimit,
)
from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)
from k8s_diag_agent.collect.incident_store_sqlite_migrations import (
    run_migrations,
)


class TestSQLiteDiagnosisIndexPlannerCoexistence(TestCase):
    """Production-schema coexistence planner tests.

    These tests prove the production schema (with all three indexes) uses an
    order-preserving query plan for active-only pagination. Unlike isolation tests
    that drop competing indexes, these tests verify the planner's behavior with
    the complete production schema intact.

    Required indexes in production schema:
    - idx_incident_current_active_diagnosis_scan (partial index for active queries)
    - idx_incident_current_diagnosis_scan (general scan index)
    - idx_incident_current_status_seen (status+time index)
    """

    def setUp(self) -> None:
        """Set up test fixtures with real SQLite database."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "coexistence_test.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _create_incidents_via_sqlite(
        self,
        num_incidents: int,
        statuses: list[str] | None = None,
    ) -> list[str]:
        """Create incidents directly via raw SQLite with production schema."""
        if statuses is None:
            statuses = ["open"]

        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        # Use production schema path
        run_migrations(conn)

        incident_ids = []
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        for i in range(num_incidents):
            incident_id = f"coexistence-{i:03d}"
            incident_ids.append(incident_id)
            ts = base_time + timedelta(seconds=i)
            event_sha = f"sha256-evt-{uuid.uuid4().hex[:16]}"
            status = statuses[i % len(statuses)]

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
                    json.dumps({
                        "namespace": "default",
                        "object_kind": "Pod",
                        "source_candidate_id": f"candidate-{incident_id}",
                    }),
                    event_sha,
                    event_sha,
                    event_sha,
                    datetime.now(UTC).isoformat(),
                ),
            )

            state = {
                "incident_id": incident_id,
                "status": status,
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": f"pod-{i}",
                "source_candidate_id": f"candidate-{incident_id}",
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
                    status,
                    ts.isoformat(),
                    ts.isoformat(),
                    json.dumps(state),
                    1,
                    datetime.now(UTC).isoformat(),
                ),
            )

        conn.commit()
        # Run ANALYZE to update SQLite statistics
        conn.execute("ANALYZE incident_current")
        conn.close()

        return incident_ids

    def _get_explain_plan(self, conn: sqlite3.Connection, sql: str, params: list[str | int]) -> str:
        """Get EXPLAIN QUERY PLAN output as string."""
        explain_sql = f"EXPLAIN QUERY PLAN {sql}"
        cursor = conn.execute(explain_sql, params)
        plan_lines = list(cursor.fetchall())
        return "\n".join(str(row) for row in plan_lines)

    def test_coexistence_active_only_no_table_scan(self) -> None:
        """Prove active-only query uses an index, not table scan, with full production schema.

        This test verifies that with the complete production schema intact
        (all three indexes present), the active-only query uses an appropriate
        index and does not perform an unrestricted table scan.
        """
        # Create mixed active/resolved distribution
        statuses = []
        for i in range(40):
            if i % 3 == 0:
                statuses.append("resolved")
            else:
                statuses.append("open")
        self._create_incidents_via_sqlite(40, statuses=statuses)

        conn = sqlite3.connect(self._db_path)
        try:
            # Build active-only query
            sql, params = _build_diagnosis_page_query(
                active_only=True,
                limit=DiagnosisPageLimit(5),
                after=None,
            )

            plan_text = self._get_explain_plan(conn, sql, params)

            # Require: uses an index (not full table scan)
            self.assertIn(
                "USING INDEX",
                plan_text,
                f"Active-only query should use an index, not full table scan. Plan:\n{plan_text}",
            )

            # Require: no USE TEMP B-TREE FOR ORDER BY
            self.assertNotIn(
                "USE TEMP B-TREE FOR ORDER BY",
                plan_text,
                f"Query should not build temp B-tree for ordering. Plan:\n{plan_text}",
            )

        finally:
            conn.close()

    def test_coexistence_active_only_with_cursor_no_table_scan(self) -> None:
        """Prove continuation query uses an index with full production schema."""
        # Create highly selective active rows
        statuses = ["open", "open", "open", "resolved", "resolved"]
        self._create_incidents_via_sqlite(40, statuses=statuses * 8)

        conn = sqlite3.connect(self._db_path)
        try:
            # Get first page to establish cursor
            sql1, params1 = _build_diagnosis_page_query(
                active_only=True,
                limit=DiagnosisPageLimit(5),
                after=None,
            )
            cursor1 = conn.execute(sql1, params1)
            page1_rows = list(cursor1.fetchall())
            self.assertEqual(len(page1_rows), 6)

            # Build cursor from last row of first page
            last_row = page1_rows[4]
            ts_text = last_row[2]
            inc_id = last_row[0]

            from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import make_test_cursor

            cursor_key = make_test_cursor(
                first_observed_at_text=ts_text,
                incident_id=inc_id,
            )

            # Build continuation query
            sql2, params2 = _build_diagnosis_page_query(
                active_only=True,
                limit=DiagnosisPageLimit(5),
                after=cursor_key,
            )

            plan_text = self._get_explain_plan(conn, sql2, params2)

            # Require: uses an index (not full table scan)
            self.assertIn(
                "USING INDEX",
                plan_text,
                f"Continuation query should use an index, not full table scan. Plan:\n{plan_text}",
            )

            # Require: no USE TEMP B-TREE FOR ORDER BY
            self.assertNotIn(
                "USE TEMP B-TREE FOR ORDER BY",
                plan_text,
                f"Query should not build temp B-tree for ordering. Plan:\n{plan_text}",
            )

        finally:
            conn.close()

    def test_coexistence_all_indexes_present(self) -> None:
        """Prove all three production indexes exist."""
        self._create_incidents_via_sqlite(5)

        conn = sqlite3.connect(self._db_path)
        try:
            # Verify all three indexes exist
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
            )
            index_names = [row[0] for row in cursor.fetchall()]

            self.assertIn("idx_incident_current_active_diagnosis_scan", index_names)
            self.assertIn("idx_incident_current_diagnosis_scan", index_names)
            self.assertIn("idx_incident_current_status_seen", index_names)

        finally:
            conn.close()

    def test_coexistence_partial_index_predicate_verified(self) -> None:
        """Prove partial index WHERE clause matches canonical predicate."""
        self._create_incidents_via_sqlite(5)

        conn = sqlite3.connect(self._db_path)
        try:
            # Get partial index definition
            cursor = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_incident_current_active_diagnosis_scan'"
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            index_sql = row[0]

            # Verify predicate matches canonical
            from k8s_diag_agent.collect.incident_diagnosis_active_status import (
                verify_status_values_match_index,
            )

            is_valid, message = verify_status_values_match_index(index_sql)
            self.assertTrue(
                is_valid,
                f"Partial index predicate mismatch: {message}",
            )

        finally:
            conn.close()


__all__ = ["TestSQLiteDiagnosisIndexPlannerCoexistence"]
