"""Tests for SQLite write context capability seam - lifecycle transitions.

These tests verify that:
1. State transitions use write context capability correctly
2. Investigation started uses canonical INVESTIGATION_STARTED enum
3. Cross-thread safety with context capability
"""

from __future__ import annotations

import shutil
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import TestCase

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore

from .incident_store_sqlite_seam_helpers import make_candidate


class TestSQLiteWriteContextInvestigationStarted(TestCase):
    """Test that mark_investigating uses canonical INVESTIGATION_STARTED enum."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_mark_investigating_uses_canonical_event_type(self) -> None:
        """Verify mark_investigating emits INVESTIGATION_STARTED event."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Promote to create incident
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], observed_at)
        incident_id = incidents[0].incident_id

        # Full lifecycle: OPEN -> COLLECTING_EVIDENCE -> READY_FOR_REVIEW -> INVESTIGATING
        store.mark_collecting_evidence(incident_id, "bundle-123")
        store.mark_ready_for_review(incident_id, "reviewer-1")

        # Mark as investigating
        updated = store.mark_investigating(incident_id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status.value, "investigating")

        # Verify the event type in database
        events = store.get_incident_events(incident_id)
        event_types = [e.event_type for e in events]

        # Should have INVESTIGATION_STARTED, not INVESTIGATING_STARTED
        self.assertIn("incident.investigation_started", event_types, "Expected INVESTIGATION_STARTED event, not INVESTIGATING_STARTED")
        self.assertNotIn("incident.investigating_started", event_types, "Found stale INVESTIGATING_STARTED event type")


class TestSQLiteWriteContextStateTransitions(TestCase):
    """Test state transitions use write context capability."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_mark_collecting_evidence_uses_context(self) -> None:
        """Test mark_collecting_evidence works through context."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create incident
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], observed_at)
        incident_id = incidents[0].incident_id

        # Transition
        updated = store.mark_collecting_evidence(incident_id, "bundle-123")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status.value, "collecting_evidence")

        # Verify event persisted
        events = store.get_incident_events(incident_id)
        self.assertGreaterEqual(len(events), 2)

    def test_suppress_uses_context(self) -> None:
        """Test suppress works through context."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create incident
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], observed_at)
        incident_id = incidents[0].incident_id

        # Suppress
        updated = store.suppress(incident_id, "test reason")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status.value, "suppressed")

    def test_resolve_uses_context(self) -> None:
        """Test resolve works through context."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create incident
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], observed_at)
        incident_id = incidents[0].incident_id

        # Full lifecycle: OPEN -> COLLECTING_EVIDENCE -> READY_FOR_REVIEW -> INVESTIGATING -> RESOLVED
        store.mark_collecting_evidence(incident_id, "bundle-123")
        store.mark_ready_for_review(incident_id, "reviewer-1")
        store.mark_investigating(incident_id)

        # Resolve
        updated = store.resolve(incident_id, "fixed")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status.value, "resolved")

    def test_mark_duplicate_uses_context(self) -> None:
        """Test mark_duplicate works through context."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create two incidents
        candidate1 = make_candidate(name="pod-1")
        candidate2 = make_candidate(name="pod-2")
        store.promote_candidates([candidate1], observed_at)
        incidents2 = store.promote_candidates([candidate2], observed_at)

        # Mark pod-2 as duplicate of pod-1
        incident1_id = store.list_incidents()[0].incident_id
        incident2_id = incidents2[0].incident_id

        updated = store.mark_duplicate(incident2_id, incident1_id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status.value, "duplicate")


class TestSQLiteWriteContextCrossThreadSafety(TestCase):
    """Test cross-thread safety with context capability."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_cross_thread_promotion_still_works(self) -> None:
        """Verify cross-thread promotion works with context capability."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        result: dict[str, Any] = {"incident": None, "error": None}

        def promote_in_thread() -> None:
            try:
                candidate = make_candidate(name="test-pod")
                incidents = store.promote_candidates([candidate], observed_at)
                result["incident"] = incidents[0] if incidents else None
            except Exception as e:
                result["error"] = e

        thread = threading.Thread(target=promote_in_thread)
        thread.start()
        thread.join(timeout=10.0)

        self.assertIsNone(result["error"], f"Cross-thread promotion failed: {result['error']}")
        self.assertIsNotNone(result["incident"])
        self.assertEqual(len(store), 1)

    def test_concurrent_promotions_serialize_correctly(self) -> None:
        """Test that concurrent promotions serialize correctly."""
        store = SQLiteIncidentStore(self._db_path)
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        success_count = 0
        lock = threading.Lock()
        barrier = threading.Barrier(3)

        def promote_in_thread(thread_id: int) -> None:
            nonlocal success_count
            barrier.wait()
            try:
                candidate = IncidentCandidate(
                    candidate_id=f"thread-{thread_id}-id",
                    namespace="default",
                    object_kind=ObjectKind.POD,
                    object_name="shared-pod",
                    candidate_class=CandidateClass.CRASH_LOOP,
                    severity=Severity.ERROR,
                    signals=(
                        CandidateSignal(
                            source=f"thread-{thread_id}",
                            reason="CrashLoopBackOff",
                            message=f"Signal from thread {thread_id}",
                        ),
                    ),
                    evidence_needed=("pod_logs",),
                    raw_object_kind=None,
                )
                observed = base_time.replace(second=thread_id)
                store.promote_candidates([candidate], observed)
                with lock:
                    success_count += 1
            except Exception as e:
                print(f"Thread {thread_id} failed: {e}")

        threads = [threading.Thread(target=promote_in_thread, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        self.assertEqual(success_count, 3)
        self.assertEqual(len(store), 1)

        # Should have events (OPENED + 2 SIGNAL_OBSERVED)
        incident_id = store.list_incidents()[0].incident_id
        events = store.get_incident_events(incident_id)
        self.assertGreaterEqual(len(events), 3)
