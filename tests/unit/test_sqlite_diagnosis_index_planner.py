"""SQLite planner tests for production pagination queries.

These tests prove that:
1. Partial index idx_incident_current_active_diagnosis_scan is used for active queries
2. General index idx_incident_current_diagnosis_scan is used for unfiltered queries
3. SQLite does not build temporary B-trees for ordering

The active query uses literal status predicates to match the partial index WHERE clause.
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


class TestSQLiteDiagnosisIndexPlanner(TestCase):
    """Tests proving pagination queries use correct indexes."""

    def setUp(self) -> None:
        """Set up test fixtures with real SQLite database."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "index_test.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _create_incidents_via_sqlite(
        self,
        num_incidents: int,
        statuses: list[str] | None = None,
    ) -> list[str]:
        """Create incidents directly via raw SQLite.

        Args:
            num_incidents: Number of incidents to create
            statuses: List of statuses to use (cycle through). Defaults to ['open'].
        """
        if statuses is None:
            statuses = ["open"]

        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        # Use production schema path
        run_migrations(conn)

        incident_ids = []
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        for i in range(num_incidents):
            incident_id = f"index-test-{i:03d}"
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

    def test_index_exists_with_correct_columns(self) -> None:
        """Prove idx_incident_current_diagnosis_scan exists with correct column ordering."""
        self._create_incidents_via_sqlite(5)

        conn = sqlite3.connect(self._db_path)
        try:
            # Verify the index exists
            cursor = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_incident_current_diagnosis_scan'"
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row, "Index idx_incident_current_diagnosis_scan should exist")

            index_sql = row[0] if row else ""
            # Index should be on (first_observed_at, incident_id) for ORDER BY coverage
            self.assertIn(
                "first_observed_at",
                index_sql,
                f"Index should include first_observed_at: {index_sql}",
            )
            self.assertIn(
                "incident_id",
                index_sql,
                f"Index should include incident_id: {index_sql}",
            )
        finally:
            conn.close()

    def test_partial_index_exists_for_active_queries(self) -> None:
        """Prove idx_incident_current_active_diagnosis_scan partial index exists.

        The partial index is designed to cover both the status filter and ORDER BY columns
        for active-only queries, avoiding TEMP B-TREE for sorting in production.
        """
        self._create_incidents_via_sqlite(5)

        conn = sqlite3.connect(self._db_path)
        try:
            # Verify the partial index exists
            cursor = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_incident_current_active_diagnosis_scan'"
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row, "Partial index idx_incident_current_active_diagnosis_scan should exist")

            index_sql = row[0] if row else ""
            # Partial index should include the ORDER BY columns
            self.assertIn(
                "first_observed_at",
                index_sql,
                f"Partial index should include first_observed_at: {index_sql}",
            )
            self.assertIn(
                "incident_id",
                index_sql,
                f"Partial index should include incident_id: {index_sql}",
            )
            # Partial index should have WHERE clause for active statuses
            self.assertIn(
                "WHERE",
                index_sql,
                f"Partial index should have WHERE clause: {index_sql}",
            )
            self.assertIn(
                "status",
                index_sql,
                f"Partial index WHERE clause should reference status: {index_sql}",
            )
        finally:
            conn.close()

    def test_explain_query_plan_uses_partial_index_for_active_query(self) -> None:
        """Prove EXPLAIN QUERY PLAN uses partial index for active_only=True.

        Isolates partial index by dropping competing status index to prove
        the partial index works correctly when it's the only status index available.
        This follows the user's R2J R5 guidance for isolation tests.
        """
        # Create incidents with mixed statuses to show partial-index selectivity
        self._create_incidents_via_sqlite(
            40,
            statuses=["open", "resolved"],  # 50% active, 50% inactive
        )

        conn = sqlite3.connect(self._db_path)
        try:
            # Drop the competing status index to prove partial index works in isolation
            conn.execute("DROP INDEX IF EXISTS idx_incident_current_status_seen")
            conn.commit()

            # Build the initial page query with active_only=True
            sql, params = _build_diagnosis_page_query(
                active_only=True,
                limit=DiagnosisPageLimit(5),
                after=None,
            )

            # Get EXPLAIN QUERY PLAN output
            explain_sql = f"EXPLAIN QUERY PLAN {sql}"
            cursor = conn.execute(explain_sql, params)
            plan_lines = list(cursor.fetchall())

            # Convert plan to readable format
            plan_text = "\n".join(str(row) for row in plan_lines)

            # Assert that the partial index is used
            self.assertIn(
                "idx_incident_current_active_diagnosis_scan",
                plan_text,
                f"Active-only query should use partial index. Plan:\n{plan_text}",
            )

            # Verify no temporary B-tree for ORDER BY
            self.assertNotIn(
                "USE TEMP B-TREE FOR ORDER BY",
                plan_text,
                f"Query should not build temp B-tree for ordering. Plan:\n{plan_text}",
            )
        finally:
            conn.close()

    def test_explain_query_plan_uses_partial_index_for_continuation(self) -> None:
        """Prove continuation query uses partial index.

        Isolates partial index by dropping competing status index to prove
        the partial index works correctly when it's the only status index available.
        The cursor's > operator should enable efficient index range scan.
        """
        self._create_incidents_via_sqlite(
            40,
            statuses=["open", "resolved"],
        )

        conn = sqlite3.connect(self._db_path)
        try:
            # Drop the competing status index to prove partial index works in isolation
            conn.execute("DROP INDEX IF EXISTS idx_incident_current_status_seen")
            conn.commit()

            # Get first page to establish cursor
            sql1, params1 = _build_diagnosis_page_query(
                active_only=True,
                limit=DiagnosisPageLimit(5),
                after=None,
            )
            cursor1 = conn.execute(sql1, params1)
            page1_rows = list(cursor1.fetchall())

            # Get cursor key from last row of first page
            last_row = page1_rows[4]
            ts_text = last_row[2]
            inc_id = last_row[0]

            # Build continuation query with cursor
            from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
                make_test_cursor,
            )

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

            # Get EXPLAIN QUERY PLAN for continuation
            explain_sql = f"EXPLAIN QUERY PLAN {sql2}"
            cursor = conn.execute(explain_sql, params2)
            plan_lines = list(cursor.fetchall())

            # Convert plan to readable format
            plan_text = "\n".join(str(row) for row in plan_lines)

            # Assert that the partial index is used
            self.assertIn(
                "idx_incident_current_active_diagnosis_scan",
                plan_text,
                f"Continuation query should use partial index. Plan:\n{plan_text}",
            )

            # Verify no temporary B-tree for ORDER BY
            self.assertNotIn(
                "USE TEMP B-TREE FOR ORDER BY",
                plan_text,
                f"Continuation query should not build temp B-tree for ordering. Plan:\n{plan_text}",
            )
        finally:
            conn.close()

    def test_explain_query_plan_uses_general_index_without_filter(self) -> None:
        """Prove idx_incident_current_diagnosis_scan is used when active_only=False.

        Without status filtering, the general diagnosis scan index is used.
        """
        self._create_incidents_via_sqlite(20)

        conn = sqlite3.connect(self._db_path)
        try:
            # Build query without active_only filter (no status filtering)
            sql, params = _build_diagnosis_page_query(
                active_only=False,  # No status filter
                limit=DiagnosisPageLimit(5),
                after=None,
            )

            # Get EXPLAIN QUERY PLAN output
            explain_sql = f"EXPLAIN QUERY PLAN {sql}"
            cursor = conn.execute(explain_sql, params)
            plan_lines = list(cursor.fetchall())

            # Convert plan to readable format
            plan_text = "\n".join(str(row) for row in plan_lines)

            # Assert that an index is used
            self.assertTrue(
                "USING INDEX" in plan_text or "USING COVERING INDEX" in plan_text,
                f"Unfiltered query should use an index. Plan:\n{plan_text}",
            )

            # When no status filter, should use general diagnosis_scan index
            self.assertIn(
                "idx_incident_current_diagnosis_scan",
                plan_text,
                f"Unfiltered query should use idx_incident_current_diagnosis_scan. Plan:\n{plan_text}",
            )

            # Verify no temporary B-tree for ORDER BY
            self.assertNotIn(
                "USE TEMP B-TREE FOR ORDER BY",
                plan_text,
                f"Query should not build temp B-tree for ordering. Plan:\n{plan_text}",
            )
        finally:
            conn.close()

    def test_query_execution_uses_ordering(self) -> None:
        """Prove pagination query returns results in correct order."""
        self._create_incidents_via_sqlite(10)

        conn = sqlite3.connect(self._db_path)
        try:
            sql, params = _build_diagnosis_page_query(
                active_only=True,
                limit=DiagnosisPageLimit(5),
                after=None,
            )

            cursor = conn.execute(sql, params)
            rows = list(cursor.fetchall())

            # Verify results are in correct order
            self.assertGreater(len(rows), 0, "Should return at least one row")
            timestamps = [row[2] for row in rows]
            self.assertEqual(
                timestamps,
                sorted(timestamps),
                "Results should be ordered by first_observed_at ASC",
            )

        finally:
            conn.close()

    def test_keyset_pagination_resumes_correctly(self) -> None:
        """Prove keyset pagination resumes at the correct position."""
        self._create_incidents_via_sqlite(20)

        conn = sqlite3.connect(self._db_path)
        try:
            # Get first page (query returns limit+1 to detect has_more)
            sql1, params1 = _build_diagnosis_page_query(
                active_only=True,
                limit=DiagnosisPageLimit(5),
                after=None,
            )
            cursor1 = conn.execute(sql1, params1)
            page1_rows = list(cursor1.fetchall())

            # Query returns limit+1 rows to detect has_more
            self.assertEqual(len(page1_rows), 6, "First page should have 6 rows (limit+1 for has_more)")

            # Get cursor key from last row of first page (row 5, index 4)
            last_row = page1_rows[4]  # Last row of the actual page (not the has_more indicator)
            ts_text = last_row[2]
            inc_id = last_row[0]

            # Build continuation query
            from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
                make_test_cursor,
            )

            cursor_key = make_test_cursor(
                first_observed_at_text=ts_text,
                incident_id=inc_id,
            )

            sql2, params2 = _build_diagnosis_page_query(
                active_only=True,
                limit=DiagnosisPageLimit(5),
                after=cursor_key,
            )
            cursor2 = conn.execute(sql2, params2)
            page2_rows = list(cursor2.fetchall())

            # Page 2 should have 6 rows (limit+1 for has_more detection)
            self.assertEqual(len(page2_rows), 6, "Second page should have 6 rows (limit+1)")

            # Verify no overlap - page 2's first row should be after page 1's last row
            page2_first_ts = page2_rows[0][2]
            self.assertGreater(
                page2_first_ts,
                ts_text,
                "Second page should start after first page's last row",
            )

        finally:
            conn.close()

__all__ = ["TestSQLiteDiagnosisIndexPlanner"]
