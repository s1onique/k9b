"""SQLite starvation regression tests for keyset pagination - Cursor lifecycle tests.

These tests prove cursor lifecycle management:
- Partial-page save
- Continuing-page save
- Final-page clear
- Empty-suffix clear
- Explicit-ID cursor isolation
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_cursor_ops import (
    handle_cursor_disposition,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
    run_automatic_diagnosis_loop_evidence_collection,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
    AutoLoopIncidentResult,
)
from k8s_diag_agent.collect.incident_diagnosis_cursor_disposition import (
    ClearScanCursor,
    CursorClearReason,
    SaveScanCursor,
    decide_cursor_disposition,
)
from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    decode_cursor,
    make_test_cursor,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)


class TestSQLiteCursorLifecycle(TestCase):
    """Tests proving cursor lifecycle management."""

    def setUp(self) -> None:
        """Set up test fixtures with real SQLite database."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "cursor_lifecycle_test.sqlite3"
        self._runs_dir = Path(self._temp_dir) / "runs"
        self._runs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _create_incidents_via_store(
        self,
        num_incidents: int,
        start_offset: int = 0,
        statuses: list[str] | None = None,
    ) -> list[str]:
        """Create incidents directly via raw SQLite."""
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        from k8s_diag_agent.collect.incident_store_sqlite_migrations import (
            run_migrations,
        )

        run_migrations(conn)

        incident_ids = []
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        if statuses is None:
            statuses = [IncidentStatus.OPEN.value] * num_incidents

        for i in range(num_incidents):
            idx = start_offset + i
            incident_id = f"auto-loop-{idx:03d}"
            incident_ids.append(incident_id)
            ts = base_time + timedelta(seconds=idx)
            event_sha = f"sha256-evt-{uuid.uuid4().hex[:16]}"
            status = statuses[i] if i < len(statuses) else IncidentStatus.OPEN.value

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
                "object_name": f"pod-{idx}",
                "candidate_class": "crash_loop",
                "severity": "error",
                "source_candidate_id": f"candidate-{incident_id}",
                "first_observed_at": ts.isoformat(),
                "last_observed_at": ts.isoformat(),
                "signals": [{
                    "source": "test-detector",
                    "reason": "crash_loop_detected",
                    "message": "Pod crash loop detected",
                    "captured_at": ts.isoformat(),
                }],
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
                    status,
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

    def _mock_external_analysis_dir(self) -> Path:
        """Create a mock external analysis directory structure."""
        ext_analysis = self._runs_dir / "health" / "default" / "external-analysis"
        ext_analysis.mkdir(parents=True, exist_ok=True)
        return ext_analysis

    def _get_cursor_token(self) -> str | None:
        """Get current scan cursor token from runs directory."""
        cursor_file = self._runs_dir / "health" / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
        if cursor_file.exists():
            with open(cursor_file) as f:
                data: dict[str, object] = json.load(f)
                cursor = data.get("cursor")
                return cursor if isinstance(cursor, str) else None
        return None

    def _run_loop_and_get_listed_incidents(
        self,
        external_analysis_dir: Path,
        incident_ids: list[str] | None = None,
        store: SQLiteIncidentStore | None = None,
    ) -> list[str]:
        """Run the loop to get the list of incidents that would be processed."""
        def make_process_result(
            incident_id: str,
            external_analysis_dir: Path,
            config: object,
            collector_run_id: str,
            now: object,
        ) -> AutoLoopIncidentResult:
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=True,
                eligibility_reason="test",
                skipped=False,
            )

        env_patch = patch.dict("os.environ", {
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true",
            "K9B_INCIDENT_STORE_BACKEND": "sqlite",
            "K9B_INCIDENT_STORE_SQLITE_PATH": str(self._db_path),
            "K9B_INCIDENT_PROMOTION_MODE": "local",
        })

        result = None
        with ExitStack() as stack:
            stack.enter_context(env_patch)
            if store is not None:
                stack.enter_context(patch("k8s_diag_agent.collect.incident_store_provider.get_incident_store", return_value=store))
                stack.enter_context(patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_config.get_incident_store", return_value=store))

            stack.enter_context(patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary", return_value={}))
            stack.enter_context(patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._emit_eligibility_summary", return_value=None))
            stack.enter_context(patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_started", return_value=None))
            stack.enter_context(patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_completed", return_value=None))
            stack.enter_context(patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident", side_effect=make_process_result))

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=external_analysis_dir,
                incident_ids=incident_ids,
            )

        return [r.get("incident_id") for r in result.incident_results if r.get("incident_id")]

    def test_partial_page_saves_last_examined(self) -> None:
        """Prove partial page saves the last examined row."""
        # Create 12 incidents - page size is 30 (10 * 3), so partial page will save cursor
        self._create_incidents_via_store(12)

        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._mock_external_analysis_dir()
        processed = self._run_loop_and_get_listed_incidents(ext_analysis, store=store)

        # Cursor should be saved with last processed incident
        cursor = self._get_cursor_token()
        self.assertIsNotNone(cursor, "Partial page should save cursor")

        if cursor:
            decoded, err = decode_cursor(cursor)
            self.assertIsNone(err)

            # Last processed should match cursor
            self.assertEqual(
                decoded.incident_id,
                processed[-1],
                "Cursor should point to last processed incident",
            )

    def test_final_page_consumed_clears_cursor(self) -> None:
        """Prove final page consumption (empty final page) clears cursor with FINAL_PAGE_CONSUMED."""
        # Create 5 incidents - all fit in one page with no has_more
        self._create_incidents_via_store(5)

        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._mock_external_analysis_dir()

        mock_disposition_result = []

        def capture_disposition(disposition, runs_dir):
            mock_disposition_result.append(disposition)
            handle_cursor_disposition(disposition, runs_dir)

        # First invocation - processes all 5, has_more=False
        with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.handle_cursor_disposition", side_effect=capture_disposition):
            _ = self._run_loop_and_get_listed_incidents(ext_analysis, store=store)

        # Cursor should be cleared (final page consumed)
        cursor_after = self._get_cursor_token()
        self.assertIsNone(cursor_after, "Cursor should be cleared after final page consumed")

        # Verify the disposition was FINAL_PAGE_CONSUMED
        self.assertEqual(len(mock_disposition_result), 1, "Should have exactly one disposition")
        disposition = mock_disposition_result[0]
        self.assertIsInstance(disposition, ClearScanCursor)
        self.assertEqual(disposition.reason, CursorClearReason.FINAL_PAGE_CONSUMED)

    def test_explicit_ids_cause_zero_cursor_operations(self) -> None:
        """Prove explicit IDs cause zero cursor reads, saves, clears, or resets."""
        self._create_incidents_via_store(5)

        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._mock_external_analysis_dir()

        def make_process_result(
            incident_id: str,
            **_: object,
        ) -> AutoLoopIncidentResult:
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=True,
                eligibility_reason="test",
                skipped=False,
            )

        env_patch = patch.dict("os.environ", {
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true",
            "K9B_INCIDENT_STORE_BACKEND": "sqlite",
            "K9B_INCIDENT_STORE_SQLITE_PATH": str(self._db_path),
            "K9B_INCIDENT_PROMOTION_MODE": "local",
        })

        with env_patch:
            with patch("k8s_diag_agent.collect.incident_store_provider.get_incident_store", return_value=store):
                with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_config.get_incident_store", return_value=store):
                    with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary"):
                        with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._emit_eligibility_summary"):
                            with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_cursor_ops.save_scan_cursor") as mock_save:
                                with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_cursor_ops.clear_scan_cursor") as mock_clear:
                                    with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_listing.load_scan_cursor") as mock_load:
                                        with patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_started", return_value=None):
                                            with patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_completed", return_value=None):
                                                with patch(
                                                    "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                                                    side_effect=make_process_result,
                                                ):
                                                    run_automatic_diagnosis_loop_evidence_collection(
                                                        external_analysis_dir=ext_analysis,
                                                        incident_ids=["auto-loop-000", "auto-loop-001"],
                                                    )

        # Verify no cursor operations occurred
        mock_load.assert_not_called()
        mock_save.assert_not_called()
        mock_clear.assert_not_called()


class TestCursorDispositionStateMachine(TestCase):
    """Tests for cursor disposition state machine decisions."""

    def test_cursor_disposition_state_machine_empty_suffix(self) -> None:
        """Prove cursor disposition state machine for empty suffix scenario."""
        # Empty suffix after cursor was present
        disposition = decide_cursor_disposition(
            automatic_selection=True,
            examined_rows=0,
            page_rows=0,
            has_more=False,
            last_examined_cursor=None,
            listing_failed=False,
            cursor_was_present=True,
        )

        self.assertIsInstance(disposition, ClearScanCursor)
        self.assertEqual(disposition.reason, CursorClearReason.EMPTY_SUFFIX_REACHED)

    def test_cursor_disposition_state_machine_final_page(self) -> None:
        """Prove cursor disposition state machine for final page consumed scenario."""
        last_cursor = make_test_cursor(
            first_observed_at_text="2024-01-01T12:00:00+00:00",
            incident_id="test-incident",
        )

        # Final page consumed (all rows examined, no more pages)
        disposition = decide_cursor_disposition(
            automatic_selection=True,
            examined_rows=10,
            page_rows=10,
            has_more=False,
            last_examined_cursor=last_cursor,
            listing_failed=False,
            cursor_was_present=True,
        )

        self.assertIsInstance(disposition, ClearScanCursor)
        self.assertEqual(disposition.reason, CursorClearReason.FINAL_PAGE_CONSUMED)

    def test_cursor_disposition_state_machine_more_pages(self) -> None:
        """Prove cursor disposition state machine for more pages scenario."""
        last_cursor = make_test_cursor(
            first_observed_at_text="2024-01-01T12:00:00+00:00",
            incident_id="test-incident",
        )

        # All rows examined, more pages exist
        disposition = decide_cursor_disposition(
            automatic_selection=True,
            examined_rows=10,
            page_rows=10,
            has_more=True,
            last_examined_cursor=last_cursor,
            listing_failed=False,
            cursor_was_present=True,
        )

        self.assertIsInstance(disposition, SaveScanCursor)
        self.assertEqual(disposition.cursor, last_cursor)


__all__ = [
    "TestSQLiteCursorLifecycle",
    "TestCursorDispositionStateMachine",
]
