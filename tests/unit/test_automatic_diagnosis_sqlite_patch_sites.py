"""SQLite starvation regression tests for keyset pagination - Patch sites tests.

These tests prove mocks patch at correct production use sites:
- batch _process_incident
- _write_loop_summary
- _emit_eligibility_summary
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
from unittest.mock import MagicMock, patch

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
    run_automatic_diagnosis_loop_evidence_collection,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
    AutoLoopIncidentResult,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)


class TestProductionMockPatchSites(TestCase):
    """Tests proving mocks patch at correct production use sites.

    These tests verify that mocks are patching the actual function names
    that production code uses, not alternative imports.
    """

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "patch_test.sqlite3"
        self._runs_dir = Path(self._temp_dir) / "runs"
        self._runs_dir.mkdir(parents=True, exist_ok=True)

        # Create incidents
        self._create_incidents(5)

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _create_incidents(self, num_incidents: int) -> None:
        """Create incidents via raw SQLite."""
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        from k8s_diag_agent.collect.incident_store_sqlite_migrations import (
            run_migrations,
        )

        run_migrations(conn)

        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        for i in range(num_incidents):
            incident_id = f"patch-test-{i:03d}"
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
                "signals": [{"source": "test"}],
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

    def test_write_loop_summary_mock_was_called(self) -> None:
        """Assert _write_loop_summary mock was called at its production use site."""
        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._runs_dir / "health" / "default" / "external-analysis"
        ext_analysis.mkdir(parents=True, exist_ok=True)

        mock_write_summary = MagicMock()

        env_patch = patch.dict("os.environ", {
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true",
            "K9B_INCIDENT_STORE_BACKEND": "sqlite",
            "K9B_INCIDENT_STORE_SQLITE_PATH": str(self._db_path),
            "K9B_INCIDENT_PROMOTION_MODE": "local",
        })

        with env_patch:
            with patch("k8s_diag_agent.collect.incident_store_provider.get_incident_store", return_value=store):
                with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_config.get_incident_store", return_value=store):
                    # Patch at the production use site
                    with patch(
                        "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary",
                        mock_write_summary,
                    ):
                        with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_eligibility.emit_eligibility_summary"):
                            with patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_started", return_value=None):
                                with patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_completed", return_value=None):
                                    with patch(
                                        "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor._process_incident",
                                        return_value=AutoLoopIncidentResult(
                                            incident_id="test",
                                            eligible=True,
                                            eligibility_reason="test",
                                            skipped=False,
                                        ),
                                    ):
                                        run_automatic_diagnosis_loop_evidence_collection(
                                            external_analysis_dir=ext_analysis,
                                        )

        # Assert mock was called (proves it patches the correct use site)
        mock_write_summary.assert_called()

    def test_emit_eligibility_summary_mock_was_called(self) -> None:
        """Assert _emit_eligibility_summary mock was called at its production use site."""
        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._runs_dir / "health" / "default" / "external-analysis"
        ext_analysis.mkdir(parents=True, exist_ok=True)

        mock_emit_eligibility = MagicMock()

        env_patch = patch.dict("os.environ", {
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true",
            "K9B_INCIDENT_STORE_BACKEND": "sqlite",
            "K9B_INCIDENT_STORE_SQLITE_PATH": str(self._db_path),
            "K9B_INCIDENT_PROMOTION_MODE": "local",
        })

        with env_patch:
            with patch("k8s_diag_agent.collect.incident_store_provider.get_incident_store", return_value=store):
                with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_config.get_incident_store", return_value=store):
                    with patch("k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor._write_loop_summary"):
                        # Patch at the production use site
                        with patch(
                            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._emit_eligibility_summary",
                            mock_emit_eligibility,
                        ):
                            with patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_started", return_value=None):
                                with patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_completed", return_value=None):
                                    with patch(
                                        "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor._process_incident",
                                        return_value=AutoLoopIncidentResult(
                                            incident_id="test",
                                            eligible=True,
                                            eligibility_reason="test",
                                            skipped=False,
                                        ),
                                    ):
                                        run_automatic_diagnosis_loop_evidence_collection(
                                            external_analysis_dir=ext_analysis,
                                        )

        # Assert mock was called (proves it patches the correct use site)
        mock_emit_eligibility.assert_called()

    def test_process_incident_mock_patches_batch_use_site(self) -> None:
        """Assert _process_incident mock patches batch module use-site, not defining module.

        The batch module imports _process_incident from evidence_processor and calls it.
        Patching at the batch module use-site is the correct approach per Python's
        mock documentation - patch where the object is looked up, not where it is defined.
        """
        store = SQLiteIncidentStore(self._db_path)
        ext_analysis = self._runs_dir / "health" / "default" / "external-analysis"
        ext_analysis.mkdir(parents=True, exist_ok=True)

        mock_batch_process = MagicMock(return_value=AutoLoopIncidentResult(
            incident_id="test",
            eligible=True,
            eligibility_reason="test",
            skipped=False,
        ))

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
                            with patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_started", return_value=None):
                                with patch.object(SQLiteIncidentStore, "mark_diagnosis_loop_completed", return_value=None):
                                    # Patch at the batch module use-site (correct approach)
                                    with patch(
                                        "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                                        mock_batch_process,
                                    ):
                                        run_automatic_diagnosis_loop_evidence_collection(
                                            external_analysis_dir=ext_analysis,
                                        )

        # Assert mock was called (proves it patches the correct use site)
        mock_batch_process.assert_called()


__all__ = [
    "TestProductionMockPatchSites",
]
