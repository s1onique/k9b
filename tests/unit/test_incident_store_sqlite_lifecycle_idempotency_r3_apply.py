"""R3 regression tests for SQLite lifecycle idempotency (apply path).

Closes R3-2 from the
``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:

* **R3-2** — ``started`` / ``failed`` / ``completed`` must
  immediately update the canonical projection atomically, and
  the state must survive close + reopen.

Companion files:

* ``test_incident_store_sqlite_lifecycle_idempotency_r3.py`` — R3-1,
  R3-5, R3-6, multi-process.
* ``test_incident_store_sqlite_lifecycle_idempotency_r3_events.py``
  — R3-3 hash chain.
* ``test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py``
  — R3-4 capability seam.

The tests rely on the canonical
:meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`
path that the R2 module now delegates to.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R3)
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
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


def _payload_started() -> dict[str, Any]:
    return {}


def _payload_failed() -> dict[str, Any]:
    return {"unavailable_reason": "captures-unavailable"}


def _read_projection_state(
    store: SQLiteIncidentStore, incident_id: str
) -> dict[str, Any]:
    """Return the parsed ``current_state_json`` for an incident.

    Returns an empty dict if no projection row exists so callers
    can ``.get("diagnosis_loop")`` without a None check.
    """
    with store._connect() as conn:
        row = conn.execute(
            "SELECT current_state_json FROM incident_current "
            "WHERE incident_id = ?",
            (incident_id,),
        ).fetchone()
    if row is None or row[0] is None:
        return {}
    return cast(dict[str, Any], json.loads(row[0]))


def _require_diag_loop(
    store: SQLiteIncidentStore, incident_id: str
) -> dict[str, Any]:
    """Return the ``diagnosis_loop`` block from the projection row.

    The canonical lifecycle apply mutates ``incident_current`` in
    the same transaction as the event insert + idempotency record
    insert. The ``diagnosis_loop`` block lives in
    ``current_state_json`` because the in-memory ``Incident`` model
    does not (yet) carry it as a typed attribute. Reading the
    projection is the canonical way to verify the canonical path
    actually wrote the lifecycle state.
    """
    state = _read_projection_state(store, incident_id)
    diag_loop = state.get("diagnosis_loop")
    assert diag_loop is not None, (
        f"projection row for {incident_id!r} must include "
        f"diagnosis_loop block; got {state!r}"
    )
    return cast(dict[str, Any], diag_loop)


class TestR3LifecycleAppliesUpdateCacheAndProjection(TestCase):
    """R3-2: ``started`` / ``failed`` / ``completed`` must update
    the canonical projection atomically, and the state must
    survive close + reopen.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_started_immediately_updates_projection(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        apply_lifecycle_transition_atomic(
            store,
            transition="started",
            incident_id=incident_id,
            run_id="run-started",
            collector_run_id="collector-started",
            fingerprint="fp-started",
            occurred_at=_OCCURRED_AT,
            payload=_payload_started(),
        )

        diag_loop = _require_diag_loop(store, incident_id)
        self.assertEqual(diag_loop["status"], "running")
        self.assertEqual(diag_loop["run_id"], "run-started")
        self.assertEqual(diag_loop["collector_run_id"], "collector-started")

    def test_failed_immediately_updates_projection(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        apply_lifecycle_transition_atomic(
            store,
            transition="failed",
            incident_id=incident_id,
            run_id="run-failed",
            collector_run_id="collector-failed",
            fingerprint="fp-failed",
            occurred_at=_OCCURRED_AT,
            payload=_payload_failed(),
        )

        diag_loop = _require_diag_loop(store, incident_id)
        self.assertEqual(diag_loop["status"], "failed")
        self.assertEqual(diag_loop["run_id"], "run-failed")
        self.assertEqual(
            diag_loop["unavailable_reason"], "captures-unavailable"
        )

    def test_completed_immediately_updates_projection(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-completed",
            collector_run_id="collector-completed",
            fingerprint="fp-completed",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )

        diag_loop = _require_diag_loop(store, incident_id)
        self.assertEqual(diag_loop["status"], "completed")
        self.assertEqual(diag_loop["review_packet_name"], "review.json")
        self.assertEqual(diag_loop["checks_run"], 1)
        self.assertEqual(diag_loop["decision"], "stop_root_cause_found")

    def test_state_survives_close_and_reopen(self) -> None:
        first_store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(first_store)
        apply_lifecycle_transition_atomic(
            first_store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-persist",
            collector_run_id="collector-persist",
            fingerprint="fp-persist",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed("review-persist.json"),
        )
        del first_store

        second_store = SQLiteIncidentStore(self._db_path)
        diag_loop = _require_diag_loop(second_store, incident_id)
        self.assertEqual(diag_loop["status"], "completed")
        self.assertEqual(diag_loop["review_packet_name"], "review-persist.json")

    def test_incident_current_advances_atomically(self) -> None:
        """R3-2: ``current_state_json`` and ``last_event_seq`` both
        advance in the same transaction.
        """
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)

        with store._connect() as conn:
            row_before = conn.execute(
                "SELECT current_state_json, last_event_seq "
                "FROM incident_current WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
        last_event_seq_before = int(row_before[1])

        apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-adv",
            collector_run_id="collector-adv",
            fingerprint="fp-adv",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )

        with store._connect() as conn:
            row_after = conn.execute(
                "SELECT current_state_json, last_event_seq "
                "FROM incident_current WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            diag_event = conn.execute(
                "SELECT event_seq FROM incident_events "
                "WHERE incident_id = ? "
                "AND event_type = 'incident.diagnosis_loop_completed'",
                (incident_id,),
            ).fetchone()
        last_event_seq_after = int(row_after[1])
        current_state = cast(dict[str, Any], json.loads(row_after[0]))

        self.assertEqual(
            last_event_seq_after,
            int(diag_event[0]),
            "incident_current.last_event_seq must equal the new event's event_seq",
        )
        self.assertGreater(
            last_event_seq_after,
            last_event_seq_before,
            "last_event_seq must advance after a lifecycle apply",
        )
        self.assertIn("diagnosis_loop", current_state)
        self.assertEqual(current_state["diagnosis_loop"]["status"], "completed")


__all__ = [
    "TestR3LifecycleAppliesUpdateCacheAndProjection",
]