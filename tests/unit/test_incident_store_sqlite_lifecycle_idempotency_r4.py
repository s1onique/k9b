"""R4 regression tests for SQLite lifecycle idempotency (cache authority).

Companion to ``test_incident_store_sqlite_lifecycle_idempotency_r4_concurrency``.
Split to keep both files under the LLM-friendly 500-line limit.

Closes R4-1, R4-2a, R4-4 blockers from the
``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:

* **R4-1** — the canonical ``apply_diagnosis_lifecycle_idempotently``
  path must prove incident existence against the durable
  ``incident_current`` projection inside the ``BEGIN IMMEDIATE``
  transaction. The process-local cache is a per-process Python dict
  and cannot prove absence across processes.

* **R4-2a** — pre-opened store regression. Process B's cache is
  loaded before process A promotes the incident. The lifecycle
  request landing on B must still apply (not be classified
  ``incident_not_found``) because the projection row exists.

* **R4-4** — the typed ``Incident.diagnosis_loop`` field carries the
  projection's lifecycle state through
  :meth:`SQLiteIncidentStore.get_incident` after a successful apply,
  so cache/detail reads expose the lifecycle state rather than
  dropping it.

The canonical path under test is
:meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently` /
:func:`k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency.apply_lifecycle_transition_atomic`.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R4)
"""

from __future__ import annotations

import shutil
import sqlite3
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
# R4-1 + R4-2a: Pre-opened store cache defect
# =============================================================================


class TestR4CacheAuthorityIsProjectionNotCache(TestCase):
    """R4-1 / R4-2a: process B's cache must not be authoritative.

    The previous canonical path used ``self._cache.get(incident_id)``
    as the existence check. In a multi-process deployment, B's cache
    is loaded at process start from the projection; if A promotes an
    incident after B opens, B's cache does not contain it. The old
    code short-circuited to ``incident_not_found`` and dropped the
    lifecycle request silently.

    This test opens B BEFORE A promotes, runs the lifecycle request
    through B, and asserts the durable state was written.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_lifecycle_apply_on_pre_opened_store_with_empty_cache(self) -> None:
        # 1. Process B opens the store before the incident exists
        #    on disk. Its cache is empty.
        process_b = SQLiteIncidentStore(self._db_path)
        self.assertEqual(
            len(process_b._incidents),
            0,
            "precondition: B's cache must be empty",
        )

        # 2. Process A promotes the incident. A's cache is updated;
        #    B's cache is NOT (separate process-local dict).
        process_a = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(process_a)
        self.assertIn(incident_id, process_a._incidents)
        self.assertNotIn(
            incident_id,
            process_b._incidents,
            "precondition: B's cache must still be empty after A promotes",
        )

        # 3. The lifecycle request lands on process B. Under the old
        #    code, B's ``self._cache.get(incident_id)`` returned None
        #    and the apply short-circuited to ``incident_not_found``.
        #    Under the R4 fix, B queries ``incident_current`` inside
        #    the transaction and finds the row.
        result = apply_lifecycle_transition_atomic(
            process_b,
            transition="completed",
            incident_id=incident_id,
            run_id="run-r4-pre-open",
            collector_run_id="collector-r4-pre-open",
            fingerprint="fp-r4-pre-open",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )

        self.assertEqual(
            result["outcome"],
            "applied",
            "pre-opened store must apply the lifecycle transition by querying "
            "incident_current, not its stale cache",
        )
        self.assertFalse(result["idempotent_replay"])

        # 4. Durable state was written.
        with process_b._connect() as conn:
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
            projection = conn.execute(
                "SELECT current_state_json FROM incident_current "
                "WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
        self.assertEqual(event_count, 1)
        self.assertEqual(idem_count, 1)
        self.assertIsNotNone(projection)
        self.assertIn(
            "diagnosis_loop",
            projection[0],
            "incident_current must carry the diagnosis_loop projection",
        )

    def test_lifecycle_apply_on_unknown_incident_returns_not_found(self) -> None:
        """The SQL existence check must still reject truly absent incidents.

        If the projection row is absent, the canonical path MUST roll
        back and return ``incident_not_found``. This guards against
        accidentally accepting any incident_id by relying on the
        database query instead of the cache.
        """
        store = SQLiteIncidentStore(self._db_path)
        result = apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id="default-pod-does-not-exist-crash_loop",
            run_id="run-r4-missing",
            collector_run_id="collector-r4-missing",
            fingerprint="fp-r4-missing",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(result["outcome"], "incident_not_found")

        # No durable rows were written.
        with sqlite3.connect(str(self._db_path)) as conn:
            (ev,) = conn.execute(
                "SELECT COUNT(*) FROM incident_events"
            ).fetchone()
            (idem,) = conn.execute(
                "SELECT COUNT(*) FROM lifecycle_idempotency"
            ).fetchone()
        self.assertEqual(ev, 0)
        self.assertEqual(idem, 0)


# =============================================================================
# R4-4: Typed diagnosis_loop field is exposed on the cache
# =============================================================================


class TestR4TypedDiagnosisLoopField(TestCase):
    """R4-4: ``Incident.diagnosis_loop`` carries the lifecycle state.

    The R3 close report claimed "the cache is refreshed from the
    projector". The dataclass did NOT have a typed ``diagnosis_loop``
    field, so the cache reconstructed through ``_state_to_incident``
    dropped the projection's lifecycle state. This test asserts that
    the typed field IS populated on the cached Incident AND on the
    detail-endpoint read after a canonical apply.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_apply_hydrates_typed_diagnosis_loop_on_cached_incident(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)

        # Pre-apply: typed field is None.
        self.assertIsNone(store._incidents[incident_id].diagnosis_loop)

        result = apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-r4-typed",
            collector_run_id="collector-r4-typed",
            fingerprint="fp-r4-typed",
            occurred_at=_OCCURRED_AT,
            payload={
                "review_packet_name": "r4-review.json",
                "checks_requested": 3,
                "checks_run": 3,
                "checks_rejected": 0,
                "decision": "stop_root_cause_found",
            },
        )
        self.assertEqual(result["outcome"], "applied")

        # 1. The returned Incident carries the typed field.
        returned = result["incident"]
        self.assertIsNotNone(returned)
        self.assertIsNotNone(returned.diagnosis_loop)
        self.assertEqual(returned.diagnosis_loop.get("status"), "completed")
        self.assertEqual(
            returned.diagnosis_loop.get("review_packet_name"),
            "r4-review.json",
        )

        # 2. The cached Incident (read via the public API) carries it.
        cached = store._incidents[incident_id]
        self.assertIsNotNone(cached.diagnosis_loop)
        self.assertEqual(cached.diagnosis_loop.get("status"), "completed")

        # 3. The detail-endpoint read (``store.get_incident``) carries it.
        detail = store.get_incident(incident_id)
        self.assertIsNotNone(detail)
        self.assertIsNotNone(detail.diagnosis_loop)
        self.assertEqual(detail.diagnosis_loop.get("status"), "completed")

        # 4. Round-trip: ``to_dict`` -> ``from_dict`` preserves it.
        rebuilt = store._state_to_incident(cached.to_dict())
        self.assertIsNotNone(rebuilt.diagnosis_loop)
        self.assertEqual(rebuilt.diagnosis_loop.get("status"), "completed")


__all__ = [
    "TestR4CacheAuthorityIsProjectionNotCache",
    "TestR4TypedDiagnosisLoopField",
]