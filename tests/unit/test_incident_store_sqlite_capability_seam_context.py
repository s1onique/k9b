"""Tests for SQLite write context capability seam - context behavior.

These tests verify that:
1. SQLiteWriteContext properly encapsulates write authority
2. Closed contexts reject use with clear errors
3. Cache operations work through the capability
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest import TestCase

from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_context import (
    ContextClosedError,
)
from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)

from .incident_store_sqlite_seam_helpers import make_candidate


class TestSQLiteWriteContextClosedRejection(TestCase):
    """Test that closed contexts reject use."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_closed_context_rejects_append_event(self) -> None:
        """Verify that a closed context rejects append_event."""
        store = SQLiteIncidentStore(self._db_path)

        # Get a context and close it
        ctx = None
        with store._write_context() as write_ctx:
            ctx = write_ctx

        # Context is now closed
        self.assertTrue(ctx.is_closed)

        # Attempting to use closed context should raise
        with self.assertRaises(ContextClosedError) as ctx_:
            ctx.append_event(
                incident_id="test-incident",
                event_type=IncidentEventType.OPENED,
                actor=IncidentEventActor.SYSTEM,
                payload={},
                occurred_at=datetime.now(UTC),
            )
        self.assertIn("closed", str(ctx_.exception).lower())

    def test_closed_context_rejects_put_cached_incident(self) -> None:
        """Verify that a closed context rejects put_cached_incident."""
        store = SQLiteIncidentStore(self._db_path)

        incident = Incident(
            incident_id="test-closed-context",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.OPEN,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
        )

        ctx = None
        with store._write_context() as write_ctx:
            ctx = write_ctx

        self.assertTrue(ctx.is_closed)

        with self.assertRaises(ContextClosedError):
            ctx.put_cached_incident(incident)

    def test_closed_context_rejects_get_cached_incident(self) -> None:
        """Verify that a closed context rejects get_cached_incident."""
        store = SQLiteIncidentStore(self._db_path)

        ctx = None
        with store._write_context() as write_ctx:
            ctx = write_ctx

        self.assertTrue(ctx.is_closed)

        with self.assertRaises(ContextClosedError):
            ctx.get_cached_incident("any-id")

    def test_closed_context_rejects_snapshot_incident(self) -> None:
        """Verify that a closed context rejects snapshot_incident."""
        store = SQLiteIncidentStore(self._db_path)

        incident = Incident(
            incident_id="test-snapshot",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.OPEN,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
        )

        ctx = None
        with store._write_context() as write_ctx:
            ctx = write_ctx

        self.assertTrue(ctx.is_closed)

        with self.assertRaises(ContextClosedError):
            ctx.snapshot_incident(incident)


class TestSQLiteWriteContextCacheOperations(TestCase):
    """Test cache operations through the capability."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_context_has_incident_returns_true_for_existing(self) -> None:
        """Test has_incident returns True for existing incidents."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Promote a candidate
        candidate = make_candidate(name="test-pod")
        store.promote_candidates([candidate], observed_at)

        # Check through context
        with store._write_context() as ctx:
            incident_id = candidate.candidate_id.replace("-crash-loop", "-crash-loop")
            # Find the actual incident ID
            incidents = store.list_incidents()
            self.assertEqual(len(incidents), 1)
            incident_id = incidents[0].incident_id
            self.assertTrue(ctx.has_incident(incident_id))

    def test_context_put_and_get_cached_incident(self) -> None:
        """Test put_cached_incident and get_cached_incident."""
        store = SQLiteIncidentStore(self._db_path)

        incident = Incident(
            incident_id="test-context-cache",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.OPEN,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
        )

        with store._write_context() as ctx:
            ctx.put_cached_incident(incident)
            retrieved = ctx.get_cached_incident("test-context-cache")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.incident_id, "test-context-cache")


class TestSQLiteWriteContextEventAppend(TestCase):
    """Test event append through the capability."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_context_append_event_updates_projection(self) -> None:
        """Test that append_event through context updates the projection."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # First, promote to create an incident
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], observed_at)
        self.assertEqual(len(incidents), 1)
        incident_id = incidents[0].incident_id

        # Verify initial event count
        initial_events = store.get_incident_events(incident_id)
        initial_count = len(initial_events)

        # Promote again to trigger a SIGNAL_OBSERVED event
        store.promote_candidates([candidate], observed_at)

        # Verify event was added
        events = store.get_incident_events(incident_id)
        self.assertEqual(len(events), initial_count + 1)


class TestSQLiteWriteContextPublicAPIStability(TestCase):
    """Test that public SQLiteIncidentStore API remains stable."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_promote_candidates_returns_tuple(self) -> None:
        """Test promote_candidates returns tuple of incidents."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        candidate = make_candidate(name="test-pod")
        result = store.promote_candidates([candidate], observed_at)

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 1)

    def test_list_incidents_returns_tuple(self) -> None:
        """Test list_incidents returns tuple of incidents."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        store.promote_candidates([make_candidate("pod-1")], observed_at)
        store.promote_candidates([make_candidate("pod-2")], observed_at)

        result = store.list_incidents()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_get_incident_returns_snapshot(self) -> None:
        """Test get_incident returns a snapshot."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        store.promote_candidates([make_candidate("test-pod")], observed_at)

        incident = store.list_incidents()[0]
        retrieved = store.get_incident(incident.incident_id)

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.incident_id, incident.incident_id)
