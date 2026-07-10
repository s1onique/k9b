"""SQLite compound key progression tests for keyset pagination.

These tests prove:
1. Compound cursor (first_observed_at, incident_id) progression works correctly
2. Strict monotonic increase with equal timestamps
3. incident_id tie-breaker works when timestamps are equal

Design constraints:
- Uses real SQLite database, not simulation
- Tests the pagination and cursor persistence logic
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

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
    run_automatic_diagnosis_loop_evidence_collection,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
    AutoLoopIncidentResult,
)
from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    decode_cursor,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)


class TestSQLiteCompoundKeyProgression(TestCase):
    """Tests proving compound key progression through keyset pagination."""

    def setUp(self) -> None:
        """Set up test fixtures with real SQLite database."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "compound_key_test.sqlite3"
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
        """Create incidents directly via raw SQLite (cache populated by store)."""
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
        """Create a mock external analysis directory structure.

        The loop derives runs_dir from external_analysis_dir.parent.parent.
        For this to work, we need: {runs}/X/Y/external-analysis
        Then parent.parent = {runs}/X, and cursor saves to {runs}/X/state/automatic-diagnosis/

        To get cursor at {runs}/state/automatic-diagnosis/, we need:
        {runs}/external-analysis/X/Y which has parent.parent = {runs}
        """
        ext_analysis = self._runs_dir / "external-analysis" / "auto-loop" / "default"
        ext_analysis.mkdir(parents=True, exist_ok=True)
        return ext_analysis

    def _get_cursor_token(self) -> str | None:
        """Get current scan cursor token from runs directory.

        The cursor is stored under runs/external-analysis/state/automatic-diagnosis/auto-loop-scan-cursor.json
        """
        cursor_file = self._runs_dir / "external-analysis" / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
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
        config: AutomaticDiagnosisLoopConfig | None = None,
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
                config=config,
            )

        return [r.get("incident_id") for r in result.incident_results if r.get("incident_id")]

    def test_compound_key_strict_monotonic_progression_equal_timestamps(self) -> None:
        """Prove strict compound-key progression with equal timestamps crosses cursor boundary.

        This test creates ONLY incidents with the EXACT same stored timestamp and verifies
        that the automatic-loop progresses through them using incident_id as tie-breaker.

        Key assertions:
        - first.first_observed_at_text == second.first_observed_at_text
        - first.incident_id < second.incident_id
        - (first.first_observed_at_text, first.incident_id) < (second.first_observed_at_text, second.incident_id)

        The test must fail if pagination compares timestamps alone.
        """
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        from k8s_diag_agent.collect.incident_store_sqlite_migrations import (
            run_migrations,
        )

        run_migrations(conn)

        # Create ONLY incidents with same timestamp (all in same group)
        # Use IDs that sort correctly for tie-breaking
        shared_ts = datetime(2024, 1, 1, 15, 0, 0, tzinfo=UTC).isoformat()
        for i in range(10):
            incident_id = f"tie-{i:03d}"
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
                    shared_ts,
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
                "object_name": f"pod-tie-{i}",
                "candidate_class": "crash_loop",
                "severity": "error",
                "source_candidate_id": f"candidate-{incident_id}",
                "first_observed_at": shared_ts,
                "last_observed_at": shared_ts,
                "signals": [{
                    "source": "test-detector",
                    "reason": "crash_loop_detected",
                    "message": "Pod crash loop detected",
                    "captured_at": shared_ts,
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
                    f"pod-tie-{i}",
                    "crash_loop",
                    "error",
                    IncidentStatus.OPEN.value,
                    shared_ts,
                    shared_ts,
                    json.dumps(state),
                    1,
                    datetime.now(UTC).isoformat(),
                ),
            )

        conn.commit()
        conn.close()

        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._mock_external_analysis_dir()

        # Use config with small batch size to force multiple pages
        config = AutomaticDiagnosisLoopConfig(max_incidents_per_run=2)

        # Run the loop multiple times and collect cursor snapshots
        cursors: list[tuple[str, str]] = []

        for i in range(5):
            result = self._run_loop_and_get_listed_incidents(ext_analysis, store=store, config=config)
            cursor = self._get_cursor_token()
            if cursor:
                decoded, err = decode_cursor(cursor)
                self.assertIsNone(err)
                if decoded:
                    cursors.append((decoded.first_observed_at_text, decoded.incident_id))
            else:
                # Debug: check if cursor file exists
                cursor_file = self._runs_dir / "state" / "automatic-diagnosis"
                print(f"Run {i}: No cursor saved. Directory exists: {cursor_file.exists()}, files: {list(cursor_file.glob('*')) if cursor_file.exists() else 'N/A'}")
                print(f"Run {i}: Listed incidents: {result}")
                # Also check other possible locations
                for pattern in [
                    self._runs_dir / "state" / "automatic-diagnosis" / "*.json",
                    self._runs_dir / "external-analysis" / "state" / "automatic-diagnosis" / "*.json",
                    self._runs_dir / "external-analysis" / "auto-loop" / "state" / "automatic-diagnosis" / "*.json",
                ]:
                    print(f"  Checking: {pattern} - exists: {pattern.parent.exists()}, files: {list(pattern.parent.glob('*')) if pattern.parent.exists() else 'N/A'}")

        self.assertGreaterEqual(
            len(cursors),
            2,
            f"Should have at least 2 cursor snapshots to verify progression. Got {len(cursors)} cursors.",
        )

        # Verify strict monotonic increase with equal timestamps
        for i in range(len(cursors) - 1):
            ts1, id1 = cursors[i]
            ts2, id2 = cursors[i + 1]

            # Assert: timestamps are equal (all in same timestamp group)
            self.assertEqual(
                ts1,
                ts2,
                f"Cursors {i} and {i+1} should have equal timestamps (same group). "
                f"Got ts1={ts1}, ts2={ts2}",
            )

            # Assert: incident IDs increase (tie-breaker works)
            self.assertLess(
                id1,
                id2,
                f"Cursor {i} incident_id ({id1}) should be < cursor {i+1} ({id2}). "
                f"If this fails, pagination is comparing timestamps alone without incident_id tie-breaker.",
            )

            # Assert: compound key is strictly increasing
            self.assertTrue(
                (ts2 > ts1) or (ts2 == ts1 and id2 > id1),
                f"Compound key ({ts1}, {id1}) should be < ({ts2}, {id2})",
            )


__all__ = ["TestSQLiteCompoundKeyProgression"]
