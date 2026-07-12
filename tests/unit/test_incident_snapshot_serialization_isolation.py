"""R5 regression tests: snapshot and serialization isolation for ``diagnosis_loop``.

Closes R5-1 from the
``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:

* ``snapshot_incident`` must deep-copy the ``diagnosis_loop`` projection
  field so mutations on the returned snapshot cannot reach back into
  the cached aggregate and bypass the canonical event writer.
* ``incident_to_dict`` (and therefore ``Incident.to_dict()``) must
  deep-copy the ``diagnosis_loop`` projection field for the same
  reason.
* The deep copy must also break aliasing on nested mutable structures,
  not just the top-level dict (the field is declared ``dict[str, Any]``
  and may legally contain nested dicts/lists).

The pre-R5 code passed the same dictionary reference through both
boundaries, which allowed the following event-store authority bypass:

    read snapshot
        ↓
    mutate returned diagnosis_loop dictionary
        ↓
    cached aggregate changes
        ↓
    no canonical event
    no projection update
    no hash-chain entry

These tests prove that mutations on the returned snapshot/payload are
isolated from the source aggregate and from any nested mutable state.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R5)
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentStatus,
)
from k8s_diag_agent.collect.incident_lifecycle_serialization import (
    incident_to_dict,
)
from k8s_diag_agent.collect.incident_snapshot_helpers import snapshot_incident
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
    apply_lifecycle_transition_atomic,
)


def _make_incident_with_diagnosis_loop(
    incident_id: str = "default-pod-isolation-pod-crash_loop",
    *,
    diagnosis_loop: dict | None = None,
) -> Incident:
    """Build an Incident with a populated ``diagnosis_loop`` projection."""
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    return Incident(
        incident_id=incident_id,
        source_candidate_id="test-candidate",
        namespace="default",
        object_kind="Pod",
        object_name="isolation-pod",
        raw_object_kind=None,
        candidate_class="crash_loop",
        severity="error",
        status=IncidentStatus.OPEN,
        first_observed_at=now,
        last_observed_at=now,
        diagnosis_loop=diagnosis_loop,
    )


# =============================================================================
# R5-1: snapshot_incident must deep-copy diagnosis_loop
# =============================================================================


class TestR5SnapshotIsolation(unittest.TestCase):
    """R5-1: ``snapshot_incident`` must isolate the cached aggregate."""

    def test_snapshot_diagnosis_loop_does_not_alias_cache(self) -> None:
        """Mutating the snapshot's diagnosis_loop must NOT mutate the cache."""
        cached = _make_incident_with_diagnosis_loop(
            diagnosis_loop={"status": "completed"},
        )

        snapshot = snapshot_incident(cached)

        # Mutate the returned snapshot.
        self.assertIsNotNone(snapshot.diagnosis_loop)
        snapshot.diagnosis_loop["status"] = "tampered"

        # The cached aggregate must remain unchanged.
        self.assertIsNotNone(cached.diagnosis_loop)
        self.assertEqual(
            cached.diagnosis_loop["status"],
            "completed",
            "snapshot must not alias the cached aggregate's diagnosis_loop",
        )

    def test_snapshot_diagnosis_loop_nested_mutation_is_isolated(self) -> None:
        """The deep copy must also break aliasing on nested mutable state.

        A shallow ``dict(...)`` would NOT be sufficient: the field is
        declared ``dict[str, Any]`` and may legitimately contain nested
        dicts and lists. This test proves we use ``deepcopy``, not just
        a shallow copy.
        """
        nested = {"checks": [{"name": "check-a"}, {"name": "check-b"}]}
        cached = _make_incident_with_diagnosis_loop(
            diagnosis_loop={
                "status": "running",
                "run_state": nested,
            },
        )

        snapshot = snapshot_incident(cached)

        # Mutate the nested structure on the snapshot.
        self.assertIsNotNone(snapshot.diagnosis_loop)
        snapshot.diagnosis_loop["run_state"]["checks"][0]["name"] = "tampered"

        # The nested state on the cached aggregate must be unchanged.
        self.assertIsNotNone(cached.diagnosis_loop)
        self.assertEqual(
            cached.diagnosis_loop["run_state"]["checks"][0]["name"],
            "check-a",
            "snapshot must deep-copy nested mutable state, not just the top-level dict",
        )

    def test_snapshot_diagnosis_loop_none_passes_through(self) -> None:
        """A None diagnosis_loop must remain None (no spurious empty dict)."""
        cached = _make_incident_with_diagnosis_loop(diagnosis_loop=None)
        snapshot = snapshot_incident(cached)
        self.assertIsNone(snapshot.diagnosis_loop)


# =============================================================================
# R5-1: incident_to_dict must deep-copy diagnosis_loop
# =============================================================================


class TestR5SerializationIsolation(unittest.TestCase):
    """R5-1: ``incident_to_dict`` must isolate the source aggregate."""

    def test_to_dict_diagnosis_loop_does_not_alias_incident(self) -> None:
        """Mutating the payload's diagnosis_loop must NOT mutate the incident."""
        incident = _make_incident_with_diagnosis_loop(
            diagnosis_loop={"status": "completed"},
        )

        payload = incident_to_dict(incident)

        # Mutate the serialized payload.
        self.assertIsNotNone(payload["diagnosis_loop"])
        payload["diagnosis_loop"]["status"] = "tampered"

        # The source aggregate must remain unchanged.
        self.assertIsNotNone(incident.diagnosis_loop)
        self.assertEqual(
            incident.diagnosis_loop["status"],
            "completed",
            "to_dict payload must not alias the incident's diagnosis_loop",
        )

    def test_to_dict_diagnosis_loop_nested_mutation_is_isolated(self) -> None:
        """The deep copy must also break aliasing on nested mutable state."""
        incident = _make_incident_with_diagnosis_loop(
            diagnosis_loop={
                "status": "running",
                "run_state": {"checks": [{"name": "check-a"}]},
            },
        )

        payload = incident_to_dict(incident)

        # Mutate the nested structure on the payload.
        self.assertIsNotNone(payload["diagnosis_loop"])
        payload["diagnosis_loop"]["run_state"]["checks"][0]["name"] = "tampered"

        # The nested state on the source aggregate must be unchanged.
        self.assertIsNotNone(incident.diagnosis_loop)
        self.assertEqual(
            incident.diagnosis_loop["run_state"]["checks"][0]["name"],
            "check-a",
            "to_dict must deep-copy nested mutable state, not just the top-level dict",
        )

    def test_to_dict_diagnosis_loop_none_passes_through(self) -> None:
        """A None diagnosis_loop must serialize as None."""
        incident = _make_incident_with_diagnosis_loop(diagnosis_loop=None)
        payload = incident_to_dict(incident)
        self.assertIsNone(payload["diagnosis_loop"])

    def test_incident_to_dict_dataclass_aliases_helper(self) -> None:
        """``Incident.to_dict`` routes through ``incident_to_dict`` and inherits isolation."""
        incident = _make_incident_with_diagnosis_loop(
            diagnosis_loop={"status": "completed"},
        )
        payload = incident.to_dict()
        payload["diagnosis_loop"]["status"] = "tampered"
        self.assertEqual(
            incident.diagnosis_loop["status"],
            "completed",
            "Incident.to_dict must inherit isolation from incident_to_dict",
        )


# =============================================================================
# R5-1: integration with the canonical SQLite lifecycle apply path
# =============================================================================


class TestR5StoreAndSnapshotIsolation(unittest.TestCase):
    """R5-1: the cached store aggregate is the canonical authority.

    These tests combine the snapshot helper with the canonical SQLite
    lifecycle-apply path so we prove the end-to-end invariant:
    mutating the snapshot returned by ``store.get_incident`` cannot
    mutate the cache that backs the canonical event writer.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _populate(self, store: SQLiteIncidentStore) -> str:
        from tests.unit.incident_store_sqlite_seam_helpers import make_candidate

        candidate = make_candidate(name="r5-isolation-pod")
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        incidents = store.promote_candidates([candidate], observed_at)
        return str(incidents[0].incident_id)

    def test_store_get_incident_diagnosis_loop_is_isolated_from_cache(self) -> None:
        """``store.get_incident`` returns a snapshot; mutating it must not
        mutate ``store._incidents``.
        """
        store = SQLiteIncidentStore(self._db_path)
        incident_id = self._populate(store)

        result = apply_lifecycle_transition_atomic(
            store,
            transition="completed",
            incident_id=incident_id,
            run_id="run-r5-isolation",
            collector_run_id="collector-r5-isolation",
            fingerprint="fp-r5-isolation",
            occurred_at=datetime(2026, 7, 12, 11, 0, 0, tzinfo=UTC),
            payload={
                "review_packet_name": "r5-review.json",
                "checks_requested": 1,
                "checks_run": 1,
                "checks_rejected": 0,
                "decision": "stop_root_cause_found",
            },
        )
        self.assertEqual(result["outcome"], "applied")

        # 1. The cached aggregate carries the typed field.
        cached = store._incidents[incident_id]
        self.assertIsNotNone(cached.diagnosis_loop)
        self.assertEqual(cached.diagnosis_loop.get("status"), "completed")

        # 2. ``store.get_incident`` returns a snapshot copy.
        detail = store.get_incident(incident_id)
        self.assertIsNotNone(detail)
        self.assertIsNotNone(detail.diagnosis_loop)
        detail.diagnosis_loop["status"] = "tampered"

        # 3. The cached aggregate must NOT have been mutated.
        cached_after = store._incidents[incident_id]
        self.assertIsNotNone(cached_after.diagnosis_loop)
        self.assertEqual(
            cached_after.diagnosis_loop["status"],
            "completed",
            "store.get_incident must return an isolated snapshot, not a reference",
        )

        # 4. The durable projection must NOT have been mutated.
        with sqlite3.connect(str(self._db_path)) as conn:
            (projection_json,) = conn.execute(
                "SELECT current_state_json FROM incident_current "
                "WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
        import json as _json

        projection = _json.loads(projection_json)
        self.assertEqual(
            projection["diagnosis_loop"]["status"],
            "completed",
            "durable projection must not be mutated by snapshot consumer",
        )


__all__ = [
    "TestR5SnapshotIsolation",
    "TestR5SerializationIsolation",
    "TestR5StoreAndSnapshotIsolation",
]


if __name__ == "__main__":
    unittest.main()