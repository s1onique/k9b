"""Real automatic-loop empty-suffix coverage tests.

These tests verify production empty-suffix handling through the full orchestration path:
- Load cursor → production dispatch → SQLiteReadContext → empty terminal page
- decide_cursor_disposition → handle_cursor_disposition → clear cursor file

Asserts:
- isinstance(disposition, ClearScanCursor)
- disposition.reason is CursorClearReason.EMPTY_SUFFIX_REACHED
- cursor_file.exists() is False
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

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_cursor import (
    save_scan_cursor,
)
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
)
from k8s_diag_agent.collect.incident_diagnosis_cursor_persistence import (
    CursorPersistenceSucceeded,
    ScanCursorReset,
)
from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    encode_cursor,
    make_test_cursor,
)
from k8s_diag_agent.collect.incident_diagnosis_pagination_types import (
    OpaqueCursorToken,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)


class TestProductionEmptySuffixCoverage(TestCase):
    """Production empty-suffix coverage tests.

    These tests invoke the real automatic loop through:
    - load cursor
    - production dispatch
    - SQLiteReadContext
    - empty terminal page
    - decide_cursor_disposition
    - handle_cursor_disposition
    - clear cursor file
    """

    def setUp(self) -> None:
        """Set up test fixtures with real SQLite database."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "empty_suffix_test.sqlite3"
        self._runs_dir = Path(self._temp_dir) / "runs"
        self._runs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _create_incidents_via_sqlite(
        self,
        num_incidents: int,
        start_offset: int = 0,
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

        for i in range(num_incidents):
            idx = start_offset + i
            incident_id = f"auto-loop-{idx:03d}"
            incident_ids.append(incident_id)
            ts = base_time + timedelta(seconds=idx)
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
                "status": IncidentStatus.OPEN.value,
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

    def _mock_external_analysis_dir(self) -> Path:
        """Create a mock external analysis directory structure."""
        ext_analysis = self._runs_dir / "health" / "default" / "external-analysis"
        ext_analysis.mkdir(parents=True, exist_ok=True)
        return ext_analysis

    def _get_cursor_file(self) -> Path:
        """Get the cursor file path."""
        return self._runs_dir / "health" / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"

    def test_empty_suffix_reached_clears_cursor_file(self) -> None:
        """Prove EMPTY_SUFFIX_REACHED clears cursor file through real orchestration.

        This test:
        1. Creates a valid cursor positioned at the final SQLite incident
        2. Saves it using save_scan_cursor with OpaqueCursorToken
        3. Asserts save result is CursorPersistenceSucceeded
        4. Invokes the real automatic loop
        5. Verifies EMPTY_SUFFIX_REACHED clears the cursor file
        """
        # Create 3 incidents
        self._create_incidents_via_sqlite(3)

        # Create a cursor pointing to the LAST incident (so next page is empty)
        last_ts = datetime(2024, 1, 1, 12, 0, 2, tzinfo=UTC).isoformat()
        last_cursor = make_test_cursor(
            first_observed_at_text=last_ts,
            incident_id="auto-loop-002",
        )
        cursor_token = encode_cursor(last_cursor)

        # Save cursor using production save_scan_cursor with OpaqueCursorToken
        runs_dir = self._runs_dir / "health"
        save_result = save_scan_cursor(runs_dir, OpaqueCursorToken(cursor_token))

        # Assert save result is CursorPersistenceSucceeded
        self.assertIsInstance(
            save_result,
            CursorPersistenceSucceeded,
            f"Expected CursorPersistenceSucceeded, got {save_result}",
        )

        # Verify cursor file exists before
        cursor_file = self._get_cursor_file()
        self.assertTrue(cursor_file.exists(), "Cursor file should exist before loop")

        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._mock_external_analysis_dir()

        # Capture the disposition
        captured_disposition = []

        def capture_disposition(disposition, runs_dir):
            captured_disposition.append(disposition)
            handle_cursor_disposition(disposition, runs_dir)

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

        with ExitStack() as stack:
            stack.enter_context(env_patch)
            stack.enter_context(patch("k8s_diag_agent.collect.incident_store_provider.get_incident_store", return_value=store))
            stack.enter_context(patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_config.get_incident_store", return_value=store))
            stack.enter_context(patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary", return_value={}))
            stack.enter_context(patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._emit_eligibility_summary", return_value=None))
            stack.enter_context(patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_started", return_value=None))
            stack.enter_context(patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_completed", return_value=None))
            stack.enter_context(patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident", side_effect=make_process_result))
            stack.enter_context(patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.handle_cursor_disposition", side_effect=capture_disposition))

            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=ext_analysis,
            )

        # Verify disposition
        self.assertEqual(len(captured_disposition), 1, "Should have exactly one disposition")
        disposition = captured_disposition[0]

        # Assert: disposition is ClearScanCursor
        self.assertIsInstance(disposition, ClearScanCursor)

        # Assert: reason is EMPTY_SUFFIX_REACHED
        self.assertEqual(disposition.reason, CursorClearReason.EMPTY_SUFFIX_REACHED)

        # Assert: cursor file does not exist after
        self.assertFalse(
            cursor_file.exists(),
            f"Cursor file should be cleared after EMPTY_SUFFIX_REACHED. File: {cursor_file}",
        )

    def test_malformed_legacy_state_is_reset(self) -> None:
        """Regression: legacy cursor state (schemaVersion=1, last_incident_id) triggers reset."""
        # Arrange: create cursor file with legacy schema version
        # load_scan_cursor expects runs_dir, and constructs:
        #   {runs_dir}/state/automatic-diagnosis/auto-loop-scan-cursor.json
        cursor_file = self._runs_dir / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
        cursor_file.parent.mkdir(parents=True, exist_ok=True)
        # Legacy format: schemaVersion=1 with last_incident_id
        cursor_file.write_text(json.dumps({
            "schemaVersion": 1,
            "last_incident_id": "legacy-incident-001",
        }))
        assert cursor_file.exists()

        # Act: load_scan_cursor should detect legacy schema and reset
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_cursor import (
            load_scan_cursor,
        )
        result = load_scan_cursor(self._runs_dir)

        # Assert: result indicates reset
        self.assertIsInstance(result, ScanCursorReset)
        self.assertEqual(result.reason, "legacy_state_schema")

        # Assert: cursor file was cleared
        self.assertFalse(
            cursor_file.exists(),
            "Legacy cursor file should be cleared after reset",
        )


__all__ = [
    "TestProductionEmptySuffixCoverage",
]
