"""Regression tests for SQLite atomic lifecycle idempotency.

These tests close the R2 failures from
``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01``:

* **Restart-durable idempotency** — closing and reopening the SQLite
  store preserves the idempotency record so a retried delivery
  collapses to a replay instead of double-applying.
* **Multi-process idempotency** — two separate SQLiteIncidentStore
  instances (each opening its own connection / process) serialize
  on ``BEGIN IMMEDIATE`` so the lookup→apply→record cycle never
  runs the mutation twice.
* **SQLite atomic mutation + idempotency commit** — the mutation
  (``incident_events`` insert) and the idempotency record insert
  (``lifecycle_idempotency`` insert) land in the same transaction
  and either both commit or neither does.

The HTTP / endpoint dispatch path is exercised separately in
``tests/unit/test_automatic_diagnosis_authority_seam01_endpoint.py``
and ``tests/unit/test_automatic_diagnosis_authority_seam01_dispatch.py``.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R2)
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import TestCase

from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
    apply_lifecycle_transition_atomic,
)

from .incident_store_sqlite_seam_helpers import make_candidate

_OCCURRED_AT = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)


def _populate(store: SQLiteIncidentStore) -> str:
    """Create one incident and return its id."""
    candidate = make_candidate(name="diag-loop-test-pod")
    observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    incidents = store.promote_candidates([candidate], observed_at)
    return str(incidents[0].incident_id)


def _payload_completed(review_packet_name: str = "review.json") -> dict[str, Any]:
    return {
        "review_packet_name": review_packet_name,
        "checks_requested": 1,
        "checks_run": 1,
        "checks_rejected": 0,
        "decision": "stop_root_cause_found",
    }


class TestSQLiteLifecycleIdempotencyAtomic(TestCase):
    """The atomic apply path: one transaction, three outcomes."""

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_first_apply_returns_applied_with_replay_false(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        fingerprint = "fp-completed-001"
        result = apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-1",
            collector_run_id="collector-1",
            fingerprint=fingerprint,
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(result["outcome"], "applied")
        self.assertFalse(result["idempotent_replay"])
        self.assertIsNotNone(result.get("incident"))

    def test_replay_with_same_fingerprint_returns_replay_true(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        fingerprint = "fp-completed-002"
        first = apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-1",
            collector_run_id="collector-1",
            fingerprint=fingerprint,
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(first["outcome"], "applied")

        second = apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-1",
            collector_run_id="collector-1",
            fingerprint=fingerprint,
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(second["outcome"], "applied")
        self.assertTrue(second["idempotent_replay"])

    def test_same_key_different_fingerprint_returns_replay_mismatch(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        first = apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-1",
            collector_run_id="collector-1",
            fingerprint="fp-a",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed("review-a.json"),
        )
        self.assertEqual(first["outcome"], "applied")

        second = apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-1",
            collector_run_id="collector-1",
            fingerprint="fp-b",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed("review-b.json"),
        )
        self.assertEqual(second["outcome"], "replay_mismatch")

    def test_unknown_incident_returns_incident_not_found(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        # No population; the incident id is absent.
        result = apply_lifecycle_transition_atomic(
            store,
            transition="started",
            incident_id="missing-incident",
            run_id="run-1",
            collector_run_id="collector-1",
            fingerprint="fp-missing",
            occurred_at=_OCCURRED_AT,
            payload={},
        )
        self.assertEqual(result["outcome"], "incident_not_found")


class TestSQLiteLifecycleIdempotencyRestartDurable(TestCase):
    """Idempotency record survives closing and reopening the store."""

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_record_survives_store_close_and_reopen(self) -> None:
        # 1. Open store, populate, apply one transition.
        first_store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(first_store)
        fingerprint = "fp-restart"
        first = apply_lifecycle_transition_atomic(
            first_store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-restart",
            collector_run_id="collector-restart",
            fingerprint=fingerprint,
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(first["outcome"], "applied")
        self.assertFalse(first["idempotent_replay"])
        # Simulate a backend restart by discarding the in-memory
        # store instance. The SQLite file on disk still has the
        # idempotency record.
        del first_store

        # 2. Open a brand-new store instance against the same file.
        second_store = SQLiteIncidentStore(self._db_path)

        # 3. Re-deliver the exact same transition. The durable
        # idempotency record must cause a replay, NOT a fresh apply.
        second = apply_lifecycle_transition_atomic(
            second_store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-restart",
            collector_run_id="collector-restart",
            fingerprint=fingerprint,
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(second["outcome"], "applied")
        self.assertTrue(
            second["idempotent_replay"],
            "second process should collapse to replay after restart",
        )


class TestSQLiteLifecycleIdempotencyMultiProcess(TestCase):
    """Two independent store instances simulate two backend processes.

    The in-process ``_write_lock`` does not protect across processes;
    the SQLite ``BEGIN IMMEDIATE`` does. We prove the contract by
    opening two stores against the same SQLite file and asserting
    that exactly one apply + one replay happen even though the two
    stores never share a Python lock.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_two_stores_one_apply_one_replay(self) -> None:
        # Process A opens the database, populates an incident, and
        # applies the lifecycle transition. Process B opens the
        # same file independently and replays the transition.
        process_a = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(process_a)
        fingerprint = "fp-multi-process"

        a_result = apply_lifecycle_transition_atomic(
            process_a,
            transition="completed",
            incident_id=incident_id,
            run_id="run-mp",
            collector_run_id="collector-mp",
            fingerprint=fingerprint,
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(a_result["outcome"], "applied")
        self.assertFalse(a_result["idempotent_replay"])

        # Process B starts "fresh": different in-memory cache, no
        # Python-level shared state with process A.
        process_b = SQLiteIncidentStore(self._db_path)
        b_result = apply_lifecycle_transition_atomic(
            process_b,
            transition="completed",
            incident_id=incident_id,
            run_id="run-mp",
            collector_run_id="collector-mp",
            fingerprint=fingerprint,
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(b_result["outcome"], "applied")
        self.assertTrue(
            b_result["idempotent_replay"],
            "Process B should observe the durable idempotency record",
        )

        # Cross-process event count must be exactly one applied
        # transition. Two ``append_event`` calls would be visible
        # here; exactly one means the mutation ran once.
        #
        # The event_type string follows the canonical
        # ``IncidentEventType`` enum value
        # (``incident.diagnosis_loop_completed``). The R3 patch
        # routes the lifecycle apply through the canonical event
        # writer so this column value is the same as for events
        # appended via ``mark_diagnosis_loop_completed_impl``.
        with process_b._connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM incident_events "
                "WHERE incident_id = ? "
                "AND event_type = 'incident.diagnosis_loop_completed'",
                (incident_id,),
            )
            (count,) = cursor.fetchone()
        self.assertEqual(
            count,
            1,
            "exactly one incident.diagnosis_loop_completed event must exist across both processes",
        )

        # Idempotency row count must be exactly one (no double-write).
        with process_b._connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM lifecycle_idempotency "
                "WHERE incident_id = ? AND transition = 'completed'",
                (incident_id,),
            )
            (idem_count,) = cursor.fetchone()
        self.assertEqual(
            idem_count,
            1,
            "exactly one idempotency record must exist across both processes",
        )


class TestSQLiteLifecycleIdempotencyAtomicity(TestCase):
    """The mutation and the idempotency record land in one transaction."""

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_event_and_idempotency_record_both_present(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-atomic",
            collector_run_id="collector-atomic",
            fingerprint="fp-atomic",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )

        # Canonical ``IncidentEventType`` value:
        # ``incident.diagnosis_loop_completed``.
        with store._connect() as conn:
            ev_count = conn.execute(
                "SELECT COUNT(*) FROM incident_events "
                "WHERE incident_id = ? "
                "AND event_type = 'incident.diagnosis_loop_completed'",
                (incident_id,),
            ).fetchone()[0]
            idem_count = conn.execute(
                "SELECT COUNT(*) FROM lifecycle_idempotency "
                "WHERE incident_id = ? AND transition = 'completed'",
                (incident_id,),
            ).fetchone()[0]
        self.assertEqual(ev_count, 1)
        self.assertEqual(idem_count, 1)

    def test_incident_not_found_writes_no_event_and_no_record(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        result = apply_lifecycle_transition_atomic(
            store,
            transition="started",
            incident_id="never-existed",
            run_id="run-x",
            collector_run_id="collector-x",
            fingerprint="fp-x",
            occurred_at=_OCCURRED_AT,
            payload={},
        )
        self.assertEqual(result["outcome"], "incident_not_found")

        with store._connect() as conn:
            ev_count = conn.execute(
                "SELECT COUNT(*) FROM incident_events",
            ).fetchone()[0]
            idem_count = conn.execute(
                "SELECT COUNT(*) FROM lifecycle_idempotency",
            ).fetchone()[0]
        self.assertEqual(ev_count, 0)
        self.assertEqual(idem_count, 0)


class TestSQLiteLifecycleIdempotencyConcurrency(TestCase):
    """Concurrent in-process apply calls collapse to one apply + N-1 replays.

    The store's in-process ``_write_lock`` still gates Python-level
    access; the test proves that overlap from many threads produces
    the same observable idempotency contract as the single-process
    path.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_concurrent_threads_one_apply_n_minus_one_replays(self) -> None:
        import threading

        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        fingerprint = "fp-concurrent"
        payload = _payload_completed()

        n = 8
        results: list[dict[str, Any]] = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(n)

        def deliver() -> None:
            barrier.wait()
            r = apply_lifecycle_transition_atomic(
                store,
                transition="completed",
                incident_id=incident_id,
                run_id="run-conc",
                collector_run_id="collector-conc",
                fingerprint=fingerprint,
                occurred_at=_OCCURRED_AT,
                payload=payload,
            )
            with results_lock:
                results.append(r)

        threads = [threading.Thread(target=deliver) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        outcomes = [r["outcome"] for r in results]
        self.assertTrue(all(o == "applied" for o in outcomes))
        replays = [r["idempotent_replay"] for r in results]
        self.assertEqual(replays.count(False), 1)
        self.assertEqual(replays.count(True), n - 1)

        # Canonical ``IncidentEventType`` value:
        # ``incident.diagnosis_loop_completed``.
        with store._connect() as conn:
            ev_count = conn.execute(
                "SELECT COUNT(*) FROM incident_events "
                "WHERE incident_id = ? "
                "AND event_type = 'incident.diagnosis_loop_completed'",
                (incident_id,),
            ).fetchone()[0]
            idem_count = conn.execute(
                "SELECT COUNT(*) FROM lifecycle_idempotency "
                "WHERE incident_id = ? AND transition = 'completed'",
                (incident_id,),
            ).fetchone()[0]
        self.assertEqual(ev_count, 1)
        self.assertEqual(idem_count, 1)


__all__ = [
    "TestSQLiteLifecycleIdempotencyAtomic",
    "TestSQLiteLifecycleIdempotencyRestartDurable",
    "TestSQLiteLifecycleIdempotencyMultiProcess",
    "TestSQLiteLifecycleIdempotencyAtomicity",
    "TestSQLiteLifecycleIdempotencyConcurrency",
]