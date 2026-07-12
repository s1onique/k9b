"""R3 regression tests for SQLite lifecycle idempotency (events).

Closes R3-3 from the
``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:

* **R3-3** — the canonical event append must use the hash chain.
  The full event chain must pass ``verify_hash_chain`` and a
  subsequent canonical event must still link correctly.

Companion files:

* ``test_incident_store_sqlite_lifecycle_idempotency_r3.py`` — R3-1,
  R3-2, R3-5, R3-6.
* ``test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py`` —
  R3-4 capability seam.

The tests rely on the canonical
:meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`
path that the R2 module now delegates to.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R3)
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest import TestCase

from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
    verify_hash_chain,
)
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


def _payload_completed() -> dict[str, object]:
    return {
        "review_packet_name": "review.json",
        "checks_requested": 1,
        "checks_run": 1,
        "checks_rejected": 0,
        "decision": "stop_root_cause_found",
    }


class TestR3HashChain(TestCase):
    """R3-3: The canonical event writer must produce valid hash
    chains. A subsequent canonical event must still link correctly.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_full_chain_passes_verify_hash_chain(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-hash",
            collector_run_id="collector-hash",
            fingerprint="fp-hash",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )

        events = store.get_incident_events(incident_id, limit=1000)
        events_sorted = sorted(events, key=lambda e: e.aggregate_version)
        self.assertTrue(
            verify_hash_chain(events_sorted),
            "complete incident event chain must pass verify_hash_chain",
        )

    def test_lifecycle_event_has_real_sha256(self) -> None:
        """R3-3: ``payload_sha256``, ``previous_event_sha256``, and
        ``event_sha256`` are real hashes, NOT the empty placeholders
        the R2 patch emitted.
        """
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-sha",
            collector_run_id="collector-sha",
            fingerprint="fp-sha",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        with store._connect() as conn:
            row = conn.execute(
                "SELECT event_id, payload_sha256, previous_event_sha256, "
                "event_sha256 FROM incident_events "
                "WHERE incident_id = ? "
                "AND event_type = 'incident.diagnosis_loop_completed'",
                (incident_id,),
            ).fetchone()
        self.assertNotEqual(row[1], "")
        self.assertNotEqual(row[2], "")
        self.assertNotEqual(row[3], "")

    def test_normal_canonical_event_after_lifecycle_links_correctly(self) -> None:
        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)
        apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-link",
            collector_run_id="collector-link",
            fingerprint="fp-link",
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )

        follow_up_at = datetime(2026, 7, 12, 11, 0, 0, tzinfo=UTC)
        with store._write_context() as ctx:
            stored = ctx.append_event(
                incident_id=incident_id,
                event_type=IncidentEventType.SIGNAL_OBSERVED,
                actor=IncidentEventActor.SYSTEM,
                payload={
                    "last_observed_at": follow_up_at.isoformat(),
                    "signal_count": 2,
                    "signals": [],
                },
                occurred_at=follow_up_at,
            )
        self.assertIsNotNone(stored.event_sha256)
        self.assertNotEqual(stored.event_sha256, "")
        self.assertNotEqual(stored.payload_sha256, "")

        events = store.get_incident_events(incident_id, limit=1000)
        sorted_events = sorted(events, key=lambda e: e.aggregate_version)
        self.assertTrue(verify_hash_chain(sorted_events))


__all__ = [
    "TestR3HashChain",
]