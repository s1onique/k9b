"""Tests for SQLite write context capability seam - diagnosis loop and projection.

These tests verify that:
1. Diagnosis loop events use write context capability
2. Evidence attachment uses write context capability
3. Projection rebuild preserves cache consistency
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest import TestCase

from k8s_diag_agent.collect.incident_evidence import EvidenceRole
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore

from .incident_store_sqlite_seam_helpers import make_candidate


class TestSQLiteWriteContextDiagnosisLoop(TestCase):
    """Test diagnosis loop events use write context capability."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_mark_diagnosis_loop_started_uses_context(self) -> None:
        """Test mark_diagnosis_loop_started works through context."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create incident
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], observed_at)
        incident_id = incidents[0].incident_id

        # Mark diagnosis loop started
        updated = store.mark_diagnosis_loop_started(incident_id, run_id="run-123", collector_run_id="collector-1")
        self.assertIsNotNone(updated)

        # Verify event
        events = store.get_incident_events(incident_id)
        event_types = [e.event_type for e in events]
        self.assertIn("incident.diagnosis_loop_started", event_types)

    def test_mark_diagnosis_loop_completed_uses_context(self) -> None:
        """Test mark_diagnosis_loop_completed works through context."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create incident
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], observed_at)
        incident_id = incidents[0].incident_id

        # Mark diagnosis loop completed
        updated = store.mark_diagnosis_loop_completed(
            incident_id,
            run_id="run-123",
            collector_run_id="collector-1",
            checks_requested=5,
            checks_run=3,
            decision="stop_no_checks_proposed",
        )
        self.assertIsNotNone(updated)

        # Verify event
        events = store.get_incident_events(incident_id)
        event_types = [e.event_type for e in events]
        self.assertIn("incident.diagnosis_loop_completed", event_types)

    def test_mark_diagnosis_loop_failed_uses_context(self) -> None:
        """Test mark_diagnosis_loop_failed works through context."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create incident
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], observed_at)
        incident_id = incidents[0].incident_id

        # Mark diagnosis loop failed
        updated = store.mark_diagnosis_loop_failed(
            incident_id,
            run_id="run-123",
            collector_run_id="collector-1",
            unavailable_reason="timeout",
        )
        self.assertIsNotNone(updated)

        # Verify event
        events = store.get_incident_events(incident_id)
        event_types = [e.event_type for e in events]
        self.assertIn("incident.diagnosis_loop_failed", event_types)


class TestSQLiteWriteContextEvidenceAttachment(TestCase):
    """Test evidence attachment uses write context capability."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_attach_evidence_uses_context(self) -> None:
        """Test attach_evidence works through context."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create incident
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], observed_at)
        incident_id = incidents[0].incident_id

        # Attach evidence
        updated = store.attach_evidence(incident_id, artifact_id="artifact-123", role=EvidenceRole.SNAPSHOT)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.evidence_count, 1)

        # Verify event
        events = store.get_incident_events(incident_id)
        event_types = [e.event_type for e in events]
        self.assertIn("incident.evidence_attached", event_types)


class TestSQLiteWriteContextRebuildProjection(TestCase):
    """Test projection rebuild preserves cache consistency."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_rebuild_projection_preserves_cache_consistency(self) -> None:
        """Test that rebuild_projection restores cache from events."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create some incidents
        store.promote_candidates([make_candidate("pod-1")], observed_at)
        store.promote_candidates([make_candidate("pod-2")], observed_at)

        initial_count = len(store)
        self.assertEqual(initial_count, 2)

        # Rebuild projection
        rebuilt_count = store.rebuild_projection()

        # Cache should match
        self.assertEqual(len(store), rebuilt_count)
        self.assertEqual(len(store), initial_count)

        # Verify incidents are accessible
        incidents = store.list_incidents()
        self.assertEqual(len(incidents), 2)
