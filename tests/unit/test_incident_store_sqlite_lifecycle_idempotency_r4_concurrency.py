"""R4 regression tests for SQLite lifecycle idempotency (concurrency).

Companion to ``test_incident_store_sqlite_lifecycle_idempotency_r4``.
Split out to keep both files under the LLM-friendly 500-line limit.

Covers:

* **R4-2b** — overlapping concurrent stores. Two independent stores
  held open by two threads must serialize through ``BEGIN IMMEDIATE``
  so the canonical ``one apply + one replay`` contract holds even
  when both writers reach the canonical method simultaneously.

* **R4-3** — idempotent replay on a process with a stale cache must
  heal that cache so the next read of the cached ``Incident``
  reflects the durable lifecycle state, not the stale pre-apply
  view.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R4)
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import TestCase

from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
    apply_lifecycle_transition_atomic,
)

from .incident_store_sqlite_seam_helpers import make_candidate

# Local copies of the small test fixtures used by the core R4 file.
# We duplicate them here to avoid importing underscore-prefixed
# helpers across files (and to keep the concurrency file
# self-contained for tooling that introspects it).
_OCCURRED_AT = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)


def _populate(store: SQLiteIncidentStore) -> str:
    """Create one incident and return its id."""
    candidate = make_candidate(name="r4-diag-loop-test-pod")
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

# =============================================================================
# R4-3: Replay refreshes the stale cache
# =============================================================================


class TestR4ReplayRefreshesStaleCache(TestCase):
    """R4-3: idempotent replay must heal the local cache.

    When process A applies the original lifecycle and process B
    (whose cache is empty or stale) handles the retry, B's
    ``self._cache`` must reflect the durable projection row after
    the replay returns. The previous code committed the empty write
    transaction and returned ``{"outcome": "applied",
    "idempotent_replay": True}`` without refreshing the cache, so B
    could read a stale view of the incident for the rest of its
    lifetime.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_replay_on_pre_opened_store_heals_cache(self) -> None:
        # 1. B opens before the incident exists.
        process_b = SQLiteIncidentStore(self._db_path)

        # 2. A promotes the incident and applies the lifecycle.
        process_a = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(process_a)

        a_result = apply_lifecycle_transition_atomic(
            process_a,
            transition="completed",
            incident_id=incident_id,
            run_id="run-r4-replay",
            collector_run_id="collector-r4-replay",
            fingerprint="fp-r4-replay",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(a_result["outcome"], "applied")
        self.assertFalse(a_result["idempotent_replay"])

        # 3. B is still empty. The replay lands on B.
        self.assertNotIn(incident_id, process_b._incidents)

        b_result = apply_lifecycle_transition_atomic(
            process_b,
            transition="completed",
            incident_id=incident_id,
            run_id="run-r4-replay",
            collector_run_id="collector-r4-replay",
            fingerprint="fp-r4-replay",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(b_result["outcome"], "applied")
        self.assertTrue(b_result["idempotent_replay"])

        # 4. R4-3: B's cache MUST now contain the incident with the
        #    typed ``diagnosis_loop`` state hydrated from the
        #    projection.
        self.assertIn(
            incident_id,
            process_b._incidents,
            "replay must heal B's cache by refreshing from the projection",
        )
        b_cached = process_b._incidents[incident_id]
        self.assertIsNotNone(
            b_cached.diagnosis_loop,
            "replay must hydrate the typed diagnosis_loop field on B's cache",
        )
        self.assertEqual(
            b_cached.diagnosis_loop.get("status"),
            "completed",
        )

        # 5. Detail endpoint must also expose the same state.
        b_get = process_b.get_incident(incident_id)
        self.assertIsNotNone(b_get)
        self.assertIsNotNone(b_get.diagnosis_loop)
        self.assertEqual(b_get.diagnosis_loop.get("status"), "completed")


# =============================================================================
# R4-2b: Overlapping concurrent stores (barrier-based contention)
# =============================================================================


class TestR4OverlappingConcurrentStores(TestCase):
    """R4-2b: two stores held open by two threads contend concurrently.

    The existing R3 multi-process test opens the second store AFTER
    the first one writes, so it cannot expose ordering problems. This
    test holds BOTH stores open simultaneously, points both at the
    same database, has both threads enter the canonical write context,
    and verifies that exactly one applies while the other replays.

    The 3-party barrier ensures both writers AND the main thread
    release together, so both workers reach the critical section
    simultaneously and ``BEGIN IMMEDIATE`` serialization is exercised
    rather than coincidental sequential writes.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_two_stores_contend_concurrently_for_lifecycle_apply(self) -> None:
        # Single incident populated before the contended apply.
        primer = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(primer)

        # Two stores opened in parallel, both pointing at the same DB.
        store_a = SQLiteIncidentStore(self._db_path)
        store_b = SQLiteIncidentStore(self._db_path)

        # Same fingerprint on both threads so the second one to commit
        # MUST classify as ``idempotent_replay``. A mismatch would
        # yield ``replay_mismatch``.
        fingerprint = "fp-r4-concurrent"

        # 3-party barrier so the main thread also waits alongside the
        # workers; otherwise the barrier would break because only 2
        # worker parties are required.
        barrier = threading.Barrier(3)
        go = threading.Event()

        results: dict[str, dict[str, Any]] = {}
        errors: dict[str, BaseException] = {}

        def _worker(name: str, store: SQLiteIncidentStore) -> None:
            try:
                # Both threads pause here until the main thread
                # joins the barrier, ensuring they reach the
                # canonical write context within microseconds of
                # each other.
                barrier.wait(timeout=10.0)
                go.wait(timeout=10.0)
                results[name] = apply_lifecycle_transition_atomic(
                    store,
                    transition="completed",
                    incident_id=incident_id,
                    run_id="run-r4-concurrent",
                    collector_run_id="collector-r4-concurrent",
                    fingerprint=fingerprint,
                    occurred_at=_OCCURRED_AT,
                    payload=_payload_completed(),
                )
            except BaseException as exc:  # noqa: BLE001
                errors[name] = exc

        thread_a = threading.Thread(
            target=_worker, args=("a", store_a), name="r4-store-a"
        )
        thread_b = threading.Thread(
            target=_worker, args=("b", store_b), name="r4-store-b"
        )
        thread_a.start()
        thread_b.start()
        # Main thread participates in the barrier so all three
        # parties release together; this guarantees both workers
        # are inside the critical section before we set ``go``.
        barrier.wait(timeout=10.0)
        go.set()
        thread_a.join(timeout=15.0)
        thread_b.join(timeout=15.0)

        self.assertFalse(errors, f"workers raised: {errors}")
        self.assertEqual(set(results), {"a", "b"})

        outcomes = sorted(
            (r["outcome"], r.get("idempotent_replay", False))
            for r in results.values()
        )
        self.assertEqual(
            outcomes,
            [("applied", False), ("applied", True)],
            "exactly one thread must apply and exactly one must replay",
        )

        # Durable state: one event row, one idempotency row.
        with sqlite3.connect(str(self._db_path)) as conn:
            (event_count,) = conn.execute(
                "SELECT COUNT(*) FROM incident_events "
                "WHERE incident_id = ? "
                "AND event_type = 'incident.diagnosis_loop_completed'",
                (incident_id,),
            ).fetchone()
            (idem_count,) = conn.execute(
                "SELECT COUNT(*) FROM lifecycle_idempotency "
                "WHERE incident_id = ? AND transition = 'completed'",
                (incident_id,),
            ).fetchone()
        self.assertEqual(event_count, 1)
        self.assertEqual(idem_count, 1)


__all__ = [
    "TestR4ReplayRefreshesStaleCache",
    "TestR4OverlappingConcurrentStores",
]
