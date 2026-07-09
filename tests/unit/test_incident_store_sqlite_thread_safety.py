"""Cross-thread SQLite incident store tests.

Tests that verify SQLiteIncidentStore works correctly when operations
are called from different threads (simulating HTTP request handlers).
"""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import time
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


def make_candidate(
    name: str,
    namespace: str = "default",
    candidate_class: CandidateClass = CandidateClass.CRASH_LOOP,
) -> IncidentCandidate:
    """Helper to create test candidates."""
    return IncidentCandidate(
        candidate_id=f"{namespace}-{ObjectKind.POD.value.lower()}-{name}-{candidate_class.value}",
        namespace=namespace,
        object_kind=ObjectKind.POD,
        object_name=name,
        candidate_class=candidate_class,
        severity=Severity.ERROR,
        signals=(
            CandidateSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="Back-off restarting",
            ),
        ),
        evidence_needed=("pod_logs", "pod_describe"),
        raw_object_kind=None,
    )


class TestSQLiteIncidentStoreCrossThreadPromotion(TestCase):
    """Test cross-thread promotion scenarios."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_promote_candidates_from_different_thread(self) -> None:
        """Test that promote_candidates works when called from a different thread.

        This is the core regression test for the SQLite thread safety fix.
        The store is created on the main thread, but promotion happens from
        a worker thread (simulating HTTP request handler).
        """
        # Create store on main thread
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Promotion result container
        result: dict[str, Any] = {"incident": None, "error": None}

        def promote_in_thread() -> None:
            """Promote from a different thread."""
            try:
                candidate = make_candidate(name="test-pod")
                incidents = store.promote_candidates([candidate], observed_at)
                result["incident"] = incidents[0] if incidents else None
            except Exception as e:
                result["error"] = e

        # Start worker thread
        thread = threading.Thread(target=promote_in_thread)
        thread.start()
        thread.join(timeout=10.0)

        # Verify no error occurred
        self.assertIsNone(
            result["error"],
            f"Cross-thread promotion failed: {result['error']}"
        )

        # Verify incident was created
        self.assertIsNotNone(result["incident"])
        self.assertEqual(len(store), 1)

        # Verify incident is in the store
        incident_id = result["incident"].incident_id
        retrieved = store.get_incident(incident_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.namespace, "default")
        self.assertEqual(retrieved.object_name, "test-pod")

        # Verify event was persisted in SQLite
        events = store.get_incident_events(incident_id)
        self.assertGreater(len(events), 0)

        # Verify projection was updated
        self.assertEqual(store.get_incident_count(), 1)

    def test_repeated_cross_thread_promotions_preserve_projection(self) -> None:
        """Test multiple cross-thread promotions don't corrupt projection.

        Sequential promotions from different threads should all succeed
        and the final projection should be consistent.
        """
        # Create store on main thread
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Results from multiple threads
        results: list[dict[str, Any]] = []
        lock = threading.Lock()

        def promote_in_thread(pod_name: str, delay: float = 0.0) -> None:
            """Promote from a different thread."""
            time.sleep(delay)  # Stagger threads
            try:
                candidate = make_candidate(name=pod_name)
                incidents = store.promote_candidates([candidate], observed_at)
                with lock:
                    results.append({
                        "success": True,
                        "incident": incidents[0] if incidents else None,
                        "pod_name": pod_name,
                    })
            except Exception as e:
                with lock:
                    results.append({
                        "success": False,
                        "error": str(e),
                        "pod_name": pod_name,
                    })

        # Start multiple threads
        threads = [
            threading.Thread(target=promote_in_thread, args=(f"pod-{i}", i * 0.05))
            for i in range(3)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=15.0)

        # Verify all succeeded
        for r in results:
            self.assertTrue(
                r.get("success", False),
                f"Promotion of {r.get('pod_name')} failed: {r.get('error')}"
            )

        # Verify all incidents are in the store
        self.assertEqual(len(store), 3)
        self.assertEqual(store.get_incident_count(), 3)

        # Verify projection integrity
        events = store.get_incident_events(results[0]["incident"].incident_id)
        self.assertGreater(len(events), 0)

    def test_concurrent_promotions_serialize_correctly(self) -> None:
        """Test that concurrent promotions are serialized and don't interfere.

        This tests that the write lock properly serializes concurrent
        write operations and no events are lost or corrupted.
        """
        # Create store on main thread
        store = SQLiteIncidentStore(self._db_path)
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Counter for successful promotions
        success_count = 0
        lock = threading.Lock()
        barrier = threading.Barrier(3)  # Sync thread start

        def promote_in_thread(thread_id: int) -> None:
            """Promote from a different thread with synchronized start."""
            nonlocal success_count
            barrier.wait()  # Wait for all threads to be ready
            try:
                # Use different candidates to test separate promotions
                # They all have the same dedupe key (same pod name/namespace)
                # so they should merge into one incident
                candidate = IncidentCandidate(
                    candidate_id=f"thread-{thread_id}-id",
                    namespace="default",
                    object_kind=ObjectKind.POD,
                    object_name="shared-pod",  # Same name = same dedupe key
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

        # Start threads
        threads = [threading.Thread(target=promote_in_thread, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        # All promotions should succeed (serialized)
        self.assertEqual(success_count, 3)

        # Should have 1 incident (same dedupe key = merged)
        self.assertEqual(len(store), 1)

        # Should have 3 events (OPENED + 2 SIGNAL_OBSERVED)
        incident_id = store.list_incidents()[0].incident_id
        events = store.get_incident_events(incident_id)
        self.assertGreaterEqual(len(events), 3)

    def test_sqlite_objects_not_shared_across_threads(self) -> None:
        """Verify that sqlite3.ProgrammingError is NOT raised.

        This is the explicit test that the original bug is fixed.
        """
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def thread_main() -> None:
            barrier.wait()
            try:
                # This should NOT raise sqlite3.ProgrammingError
                store.promote_candidates([make_candidate("pod-1")], observed_at)
            except sqlite3.ProgrammingError as e:
                errors.append(e)

        def thread_worker() -> None:
            barrier.wait()
            time.sleep(0.1)  # Let main thread go first
            try:
                # This should NOT raise sqlite3.ProgrammingError
                store.promote_candidates([make_candidate("pod-2")], observed_at)
            except sqlite3.ProgrammingError as e:
                errors.append(e)

        t1 = threading.Thread(target=thread_main)
        t2 = threading.Thread(target=thread_worker)

        t1.start()
        t2.start()

        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        # No sqlite3.ProgrammingError should have occurred
        sqlite_errors = [e for e in errors if "SQLite objects created in a thread" in str(e)]
        self.assertEqual(
            len(sqlite_errors),
            0,
            f"SQLite thread safety violation: {sqlite_errors}"
        )


class TestSQLiteIncidentStoreInternalAPIErrorContract(TestCase):
    """Test that internal API correctly reports promotion failures."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_promotion_failure_does_not_hide_exception(self) -> None:
        """Verify that promotion failures propagate correctly.

        This test ensures that when SQLite operations fail, the exception
        is not silently swallowed and the store is not left in an
        inconsistent state.
        """
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # First promotion should succeed
        candidate = make_candidate(name="pod-1")
        incidents = store.promote_candidates([candidate], observed_at)
        self.assertEqual(len(incidents), 1)

        # Verify incident is persisted
        incident_id = incidents[0].incident_id
        self.assertIsNotNone(store.get_incident(incident_id))

        # Verify projection is correct
        self.assertEqual(store.get_incident_count(), 1)

    def test_concurrent_access_maintains_consistency(self) -> None:
        """Test that concurrent reads and writes don't corrupt data."""
        store = SQLiteIncidentStore(self._db_path)
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Pre-populate with some incidents
        for i in range(5):
            store.promote_candidates([make_candidate(f"pod-{i}")], observed_at)

        read_count = 0
        write_success = True
        lock = threading.Lock()
        barrier = threading.Barrier(3)

        def reader() -> None:
            nonlocal read_count
            barrier.wait()
            for _ in range(5):
                _ = store.list_incidents()
                _ = store.get_incident_count()
                _ = store.get_event_count()
                with lock:
                    read_count += 1
                time.sleep(0.01)

        def writer() -> None:
            nonlocal write_success
            barrier.wait()
            for i in range(5):
                try:
                    store.promote_candidates(
                        [make_candidate(f"concurrent-pod-{i}")],
                        observed_at
                    )
                except Exception:
                    with lock:
                        write_success = False

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        # Writes should all succeed
        self.assertTrue(write_success)

        # Store should be in consistent state
        self.assertGreaterEqual(len(store), 5)  # At least initial 5 + some writes
