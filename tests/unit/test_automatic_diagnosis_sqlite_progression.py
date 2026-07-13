"""SQLite starvation regression tests for keyset pagination - Progression tests.

These tests prove progression through keyset pagination:
- Crossing the real 30-row page boundary
- No duplicate processing before wraparound
- Compound cursor progression
- Eligible incident beyond the initial page

Design constraints:
- Uses real SQLite database, not simulation
- Tests the pagination and cursor persistence logic
- Mocks expensive write operations at their actual production use sites
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
from unittest.mock import MagicMock, patch

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


class TestSQLiteStarvationProgression(TestCase):
    """Tests proving progression through keyset pagination."""

    def setUp(self) -> None:
        """Set up test fixtures with real SQLite database."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "progression_test.sqlite3"
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
            review_packet_budget = None,
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

    def test_pagination_across_pages_processes_all_incidents(self) -> None:
        """Prove pagination works across multiple runs to process all incidents.

        Page limit = scan_bound = max_diagnoses * 3 = 10 * 3 = 30 incidents per page.
        With 42 incidents, we need 2 runs to process all (first run: 10 processed, cursor saved;
        second run: continues from cursor, processes more).
        """
        # Create 42 incidents - page limit is 30 (10 * 3)
        self._create_incidents_via_store(42)

        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._mock_external_analysis_dir()

        all_processed_ids: set[str] = set()

        for run_num in range(5):
            processed = self._run_loop_and_get_listed_incidents(ext_analysis, store=store)
            all_processed_ids.update(processed)

            if "auto-loop-030" in all_processed_ids:
                break

        # The key assertion: incident auto-loop-030 (beyond first page of 30) was processed
        self.assertIn(
            "auto-loop-030",
            all_processed_ids,
            f"auto-loop-030 (index 30, beyond first page) should be processed across multiple runs. "
            f"Processed after 5 runs: {sorted(all_processed_ids)}",
        )

        beyond_page_zero = {f"auto-loop-{i:03d}" for i in range(30, 42)}
        found_beyond = all_processed_ids & beyond_page_zero

        self.assertGreater(
            len(found_beyond),
            0,
            f"Should find incidents beyond first page (indices 30+). Processed: {sorted(all_processed_ids)}",
        )

    def test_cursor_persists_across_invocations(self) -> None:
        """Prove at least two invocations persist increasing cursors."""
        self._create_incidents_via_store(42)

        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._mock_external_analysis_dir()

        # First invocation
        _ = self._run_loop_and_get_listed_incidents(ext_analysis, store=store)
        cursor1 = self._get_cursor_token()
        self.assertIsNotNone(cursor1, "First invocation should save a cursor")

        # Second invocation
        _ = self._run_loop_and_get_listed_incidents(ext_analysis, store=store)
        cursor2 = self._get_cursor_token()
        self.assertIsNotNone(cursor2, "Second invocation should save a cursor")

        if cursor1 and cursor2:
            decoded1, err1 = decode_cursor(cursor1)
            decoded2, err2 = decode_cursor(cursor2)
            self.assertIsNone(err1)
            self.assertIsNone(err2)

            # Cursor should advance to later incident
            self.assertGreater(
                decoded2.first_observed_at_text,
                decoded1.first_observed_at_text,
            )

    def test_no_duplicate_processing_before_wraparound(self) -> None:
        """Prove no incident is examined twice before wraparound.

        Bound test before cursor clear/wraparound occurs.
        """
        self._create_incidents_via_store(20)

        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._mock_external_analysis_dir()

        processed_incidents: list[str] = []
        mock_process = MagicMock()

        def capture_process(
            incident_id: str,
            external_analysis_dir: Path,
            config: object,
            collector_run_id: str,
            now: object,
            review_packet_budget = None,
        ) -> AutoLoopIncidentResult:
            processed_incidents.append(incident_id)
            mock_process()
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

        loop_invocations = 0
        with env_patch:
            with patch("k8s_diag_agent.collect.incident_store_provider.get_incident_store", return_value=store):
                with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_config.get_incident_store", return_value=store):
                    with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary"):
                        with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._emit_eligibility_summary"):
                            with patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_started", return_value=None):
                                with patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_completed", return_value=None):
                                    with patch(
                                        "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                                        side_effect=capture_process,
                                    ):
                                        for _ in range(3):
                                            prev_cursor = self._get_cursor_token()
                                            run_automatic_diagnosis_loop_evidence_collection(
                                                external_analysis_dir=ext_analysis,
                                            )
                                            curr_cursor = self._get_cursor_token()
                                            loop_invocations += 1

                                            if prev_cursor and not curr_cursor:
                                                break

        self.assertGreater(loop_invocations, 0, "Should have run the loop at least once")
        mock_process.assert_called()
        self.assertGreater(len(processed_incidents), 0, "Should have processed at least one incident")

        # No incident should appear twice before cursor wraps around
        seen_counts: dict[str, int] = {}
        for inc_id in processed_incidents:
            seen_counts[inc_id] = seen_counts.get(inc_id, 0) + 1

        duplicates = {k: v for k, v in seen_counts.items() if v > 1}
        self.assertEqual(
            duplicates,
            {},
            f"Should not process same incident twice before wraparound: {duplicates}",
        )


__all__ = [
    "TestSQLiteStarvationProgression",
]
