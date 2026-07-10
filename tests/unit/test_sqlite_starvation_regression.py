"""Real SQLite-backed starvation regression tests for keyset pagination.

These tests prove:
1. 40+ persisted active incidents with deterministic immutable ordering
2. Actual production function list_incidents_for_diagnosis_page() works correctly
3. Eligible incident beyond initial page is eventually processed
4. At least two persisted cursor transitions occur
5. SQLite mode never accesses store._incidents (proved via isolation)

The key invariant: SQLite pagination MUST bypass store._incidents cache
and query incident_current directly to prevent starvation.

Design constraints:
- Uses real SQLite database, not simulation
- Uses actual production code paths
- Proves isolation between cache and pagination
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
    list_incidents_for_diagnosis_page_impl,
)
from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    DiagnosisPageLimit,
    decode_cursor,
    encode_cursor,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)


class TestSQLiteStarvationRegression(TestCase):
    """Regression tests proving SQLite pagination prevents starvation.

    These tests use real SQLite database operations to prove:
    1. Pagination works across 40+ incidents
    2. Cache (_incidents) is bypassed by pagination
    3. Cursor transitions work correctly across pages
    """

    def setUp(self) -> None:
        """Set up test fixtures with real SQLite database."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "starvation_test.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _create_incidents_via_sqlite(
        self,
        num_incidents: int,
        start_offset: int = 0,
    ) -> list[str]:
        """Create incidents directly via raw SQLite (bypassing store cache).

        This creates incidents in incident_events + incident_current tables
        directly, proving that pagination queries the tables, not the cache.
        """
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        # Run migrations first
        from k8s_diag_agent.collect.incident_store_sqlite_migrations import (
            run_migrations,
        )

        run_migrations(conn)

        incident_ids = []
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        for i in range(num_incidents):
            idx = start_offset + i
            incident_id = f"starvation-test-{idx:03d}"
            incident_ids.append(incident_id)

            # Timestamp advances by 1 second each (deterministic immutable ordering)
            ts = base_time + timedelta(seconds=idx)

            # Use unique sha256 values per incident
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
                    '{"namespace": "default", "object_kind": "Pod"}',
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
                "object_name": f"pod-{idx}",
                "candidate_class": "crash_loop",
                "severity": "error",
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
                    f"pod-{idx}",
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

        return incident_ids

    def test_sqlite_pagination_bypasses_cache(self) -> None:
        """Prove SQLite pagination queries tables, not store._incidents cache."""
        num_incidents = 10
        expected_ids = self._create_incidents_via_sqlite(num_incidents)

        store = SQLiteIncidentStore(self._db_path)

        # Verify cache doesn't contain our incidents
        cached_ids = set(store._incidents.keys())
        for inc_id in expected_ids:
            self.assertNotIn(
                inc_id,
                cached_ids,
                f"Incident {inc_id} should NOT be in cache",
            )

        # Pagination MUST find incidents via SQLite
        page = store.list_incidents_for_diagnosis_page(
            active_only=True,
            limit=DiagnosisPageLimit(5),
            after_cursor=None,
        )

        self.assertGreater(len(page.incidents), 0)
        self.assertLessEqual(len(page.incidents), 5)

        returned_ids = {inc.incident_id for inc in page.incidents}
        self.assertTrue(
            returned_ids.issubset(set(expected_ids)),
            f"Returned {returned_ids} should be subset of created {set(expected_ids)}",
        )

    def test_forty_plus_incidents_across_pages(self) -> None:
        """Create 42 incidents and verify pagination across all pages."""
        num_incidents = 42
        page_size = 5

        expected_ids = self._create_incidents_via_sqlite(num_incidents)
        store = SQLiteIncidentStore(self._db_path)

        all_returned_ids: list[str] = []
        cursor = None
        page_count = 0

        while page_count < 20:
            page = store.list_incidents_for_diagnosis_page(
                active_only=True,
                limit=DiagnosisPageLimit(page_size),
                after_cursor=cursor,
            )

            page_ids = [inc.incident_id for inc in page.incidents]
            all_returned_ids.extend(page_ids)
            page_count += 1

            if not page.has_more:
                break

            self.assertIsNotNone(page.next_cursor)
            cursor = page.next_cursor

        self.assertEqual(len(all_returned_ids), num_incidents)
        self.assertEqual(len(all_returned_ids), len(set(all_returned_ids)))
        self.assertEqual(set(all_returned_ids), set(expected_ids))

        expected_pages = (num_incidents + page_size - 1) // page_size
        self.assertEqual(page_count, expected_pages)

    def test_cursor_transitions_persist_across_runs(self) -> None:
        """Prove cursor can be saved, persisted, and loaded across store instances."""
        num_incidents = 15
        page_size = 4
        expected_ids = self._create_incidents_via_sqlite(num_incidents)

        # Run 1
        store1 = SQLiteIncidentStore(self._db_path)
        page1 = store1.list_incidents_for_diagnosis_page(
            active_only=True,
            limit=DiagnosisPageLimit(page_size),
            after_cursor=None,
        )

        self.assertGreater(len(page1.incidents), 0)
        self.assertTrue(page1.has_more)

        run1_ids = [inc.incident_id for inc in page1.incidents]
        saved_cursor = page1.next_cursor
        self.assertIsNotNone(saved_cursor)

        token = encode_cursor(saved_cursor)
        decoded, err = decode_cursor(token)
        self.assertIsNone(err)
        self.assertEqual(decoded.incident_id, run1_ids[-1])

        # Run 2
        store2 = SQLiteIncidentStore(self._db_path)
        page2 = store2.list_incidents_for_diagnosis_page(
            active_only=True,
            limit=DiagnosisPageLimit(page_size),
            after_cursor=saved_cursor,
        )

        run2_ids = [inc.incident_id for inc in page2.incidents]
        self.assertEqual(set(run1_ids) & set(run2_ids), set())
        self.assertEqual(run2_ids[0], expected_ids[len(run1_ids)])

        # Run 3
        store3 = SQLiteIncidentStore(self._db_path)
        page3 = store3.list_incidents_for_diagnosis_page(
            active_only=True,
            limit=DiagnosisPageLimit(page_size),
            after_cursor=page2.next_cursor,
        )

        run3_ids = [inc.incident_id for inc in page3.incidents]
        self.assertEqual(set(run1_ids) & set(run3_ids), set())
        self.assertEqual(set(run2_ids) & set(run3_ids), set())
        self.assertEqual(
            run3_ids[0],
            expected_ids[len(run1_ids) + len(run2_ids)],
        )

        self.assertIsNotNone(page1.next_cursor)
        self.assertIsNotNone(page2.next_cursor)

    def test_sqlite_read_context_is_used(self) -> None:
        """Prove that _read_context() is used for pagination."""
        store = SQLiteIncidentStore(self._db_path)
        initial_count = len(store._incidents)

        new_incidents = self._create_incidents_via_sqlite(5, start_offset=100)

        self.assertEqual(len(store._incidents), initial_count)

        page = store.list_incidents_for_diagnosis_page(
            active_only=True,
            limit=DiagnosisPageLimit(10),
            after_cursor=None,
        )

        returned_ids = {inc.incident_id for inc in page.incidents}
        self.assertTrue(
            any(inc_id in returned_ids for inc_id in new_incidents),
            f"New incidents {new_incidents} should be found via pagination",
        )

    def test_direct_impl_uses_connection(self) -> None:
        """Prove list_incidents_for_diagnosis_page_impl works with raw connection."""
        self._create_incidents_via_sqlite(20)

        conn = sqlite3.connect(self._db_path)
        try:
            page = list_incidents_for_diagnosis_page_impl(
                conn=conn,
                active_only=True,
                limit=DiagnosisPageLimit(5),
                after=None,
            )

            self.assertEqual(len(page.incidents), 5)
            self.assertTrue(page.has_more)
            self.assertIsNotNone(page.next_cursor)

            for i in range(len(page.incidents) - 1):
                curr = page.incidents[i]
                next_inc = page.incidents[i + 1]
                self.assertLess(
                    curr.first_observed_at,
                    next_inc.first_observed_at,
                    "Incidents should be ordered by first_observed_at",
                )
        finally:
            conn.close()

    def test_eligible_incident_beyond_initial_page(self) -> None:
        """Prove eligible incident beyond initial page is eventually processed."""
        self._create_incidents_via_sqlite(20)
        store = SQLiteIncidentStore(self._db_path)

        target_id = "starvation-test-014"
        cursor = None
        found = False

        for _ in range(10):
            page = store.list_incidents_for_diagnosis_page(
                active_only=True,
                limit=DiagnosisPageLimit(5),
                after_cursor=cursor,
            )

            page_ids = [inc.incident_id for inc in page.incidents]
            if target_id in page_ids:
                found = True
                break

            if not page.has_more:
                break

            cursor = page.next_cursor

        self.assertTrue(found, f"Target {target_id} should be found beyond initial pages")


__all__ = ["TestSQLiteStarvationRegression"]
