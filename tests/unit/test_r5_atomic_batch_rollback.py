"""R5 atomic-batch rollback proof for ``append_events_atomic``.

This test injects a failure during projection update of the second
``EventAppendSpec`` and proves the entire batch is rolled back:

* No event from the failed batch persists in ``incident_events``.
* No partial ``incident_current`` projection row persists.
* Aggregate ``incident_current.aggregate_version`` and event-chain
  ``previous_event_sha256`` are unchanged.
* The post-rollback assertions are read through a SEPARATE SQLite
  connection (not the same connection that issued ``BEGIN IMMEDIATE``)
  so the verifier observes the durable post-rollback state.

R4 contract (task 7) keeps the helper's signature; R5 (item 4) adds the
"failure during projection update of the second spec" injection and the
separate-connection assertion. The test uses an in-memory
``tempfile.TemporaryDirectory`` store so the SQLite WAL is fully
sealed between reads and writes.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R5
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_store_sqlite_events_writer import (
    EventAppendSpec,
    append_events_atomic,
)


class _ProjectionFailure(RuntimeError):
    """Marker failure for ``update_projection_for_event`` during rollback tests."""


class _StubStore:
    """Minimal ``SQLiteIncidentStore`` shim for the rollback injection.

    ``append_events_atomic`` only consumes ``cursor.connection``; we do
    NOT need a full store instance. The shim records the connection
    so the rollback test can verify state on a fresh handle after the
    failure.
    """


def _open_fresh_connection(path: Path) -> sqlite3.Connection:
    """Open a brand-new SQLite connection to the same file.

    Used after ``append_events_atomic`` returns or raises so the
    durability of the rollback is observable across connections,
    not just via the connection that ran the failed transaction.
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


class AtomicBatchRollbackTests(unittest.TestCase):
    """Verify the failure-injected batch rolls back atomically."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)
        self.db_path = self.tmp_path / "r5_rollback.sqlite"
        self.store_path = self.tmp_path / "store"
        self.store_path.mkdir()
        # Build the SQLite DB via the production store so the schema
        # matches the one exercised by ``append_events_atomic``.
        from k8s_diag_agent.collect.incident_store_sqlite import (
            SQLiteIncidentStore,
        )

        self._store = SQLiteIncidentStore(path=self.db_path)
        # Seed an incident + OPENED event so the second spec's
        # ``previous_event_sha256`` link has a real predecessor.
        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )

        candidate = IncidentCandidate(
            candidate_id="r5-rollback/seed",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="r5-rollback",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(
                CandidateSignal(
                    source="pod",
                    reason="CrashLoopBackOff",
                    message="Back-off restarting",
                ),
            ),
            evidence_needed=("pod_logs",),
        )
        self.observed_at = datetime.now(UTC)
        self._seeded = self._store.promote_candidates(
            candidates=[candidate],
            observed_at=self.observed_at,
            snapshot_bundle_id="r5-bundle",
        )
        self.incident_id = self._seeded[0].incident_id

    def tearDown(self) -> None:
        try:
            self._store.close()
        finally:
            self._tmpdir.cleanup()

    def test_second_spec_failure_rolls_back_entire_batch(self) -> None:
        """Projection-update failure on the second spec MUST roll everything back."""
        from k8s_diag_agent.collect import (
            incident_store_sqlite_queries as queries_module,
        )

        baseline_aggregate_version = self._projection_aggregate_version()
        baseline_last_event_seq = self._projection_last_event_seq()
        baseline_latest_event_sha = self._baseline_event_sha()

        # Patch ``update_projection_for_event`` (imported lazily from
        # ``incident_store_sqlite_queries`` by the writer) to fail on
        # the second call. The first event is inserted into
        # ``incident_events`` BEFORE the projection update runs, so a
        # partial state of "first event present, no projection
        # update, second event never inserted" is the failure shape
        # the R5 contract must guard against.
        original_update = queries_module.update_projection_for_event
        call_state = {"calls": 0}

        def _flaky_update_projection(
            conn: sqlite3.Connection,
            event: object,
        ) -> None:
            call_state["calls"] += 1
            if call_state["calls"] >= 2:
                raise _ProjectionFailure(
                    "simulated projection failure on second spec"
                )
            original_update(conn, event)
            return None

        # Build the EventAppendSpec with proper enum values; the writer
        # expects ``IncidentEventType`` (StrEnum) and the actor must be
        # the matching ``IncidentEventActor`` enum value.
        from k8s_diag_agent.collect.incident_store_sqlite_events import (
            IncidentEventActor,
            IncidentEventType,
        )

        queries_module.update_projection_for_event = _flaky_update_projection
        try:
            specs = (
                EventAppendSpec(
                    incident_id=self.incident_id,
                    event_type=IncidentEventType.COLLECTING_EVIDENCE_STARTED,
                    actor=IncidentEventActor.SCHEDULER,
                    payload={"r5_marker": "second_failure_point_a"},
                    occurred_at=self.observed_at,
                ),
                EventAppendSpec(
                    incident_id=self.incident_id,
                    event_type=IncidentEventType.READY_FOR_REVIEW,
                    actor=IncidentEventActor.SCHEDULER,
                    payload={"r5_marker": "second_failure_point_b"},
                    occurred_at=self.observed_at,
                ),
            )
            with self.assertRaises(_ProjectionFailure):
                with self._store._connect() as conn:
                    append_events_atomic(conn, specs)
            # The flaky projection ran exactly once (for the first
            # spec) and threw on the second call -- the partial state
            # to be rolled back.
            self.assertEqual(call_state["calls"], 2)
        finally:
            queries_module.update_projection_for_event = original_update

        # Read through a SEPARATE SQLite connection to prove the
        # rollback was durable, not just an in-memory undo.
        fresh = _open_fresh_connection(self.db_path)
        try:
            event_rows = fresh.execute(
                "SELECT event_id, payload_json FROM incident_events "
                "WHERE incident_id = ?",
                (self.incident_id,),
            ).fetchall()
        finally:
            fresh.close()

        roll_back_markers = [
            row
            for row in event_rows
            if "second_failure_point" in (row["payload_json"] or "")
        ]
        self.assertEqual(
            roll_back_markers,
            [],
            msg=(
                "Failure during projection update of the second "
                "EventAppendSpec MUST roll the entire "
                "append_events_atomic batch back; observed "
                f"{len(roll_back_markers)} partial events."
            ),
        )

        # The aggregate_version and last_event_seq on incident_current
        # must NOT have moved.
        fresh = _open_fresh_connection(self.db_path)
        try:
            row = fresh.execute(
                "SELECT aggregate_version, last_event_seq "
                "FROM incident_current WHERE incident_id = ?",
                (self.incident_id,),
            ).fetchone()
        finally:
            fresh.close()
        self.assertIsNotNone(
            row,
            msg="incident_current must persist the seeded row",
        )
        self.assertEqual(
            row["aggregate_version"],
            baseline_aggregate_version,
            msg=(
                "The projection ``aggregate_version`` MUST be "
                "unchanged after the rolled-back batch."
            ),
        )
        self.assertEqual(
            row["last_event_seq"],
            baseline_last_event_seq,
            msg=(
                "The projection ``last_event_seq`` MUST be unchanged "
                "after the rolled-back batch so downstream consumers "
                "see the same event position."
            ),
        )

        # The newest event-sha on the failure path is still the OPENED
        # seed; nothing from the failed batch advanced the chain.
        self.assertEqual(
            self._baseline_event_sha(),
            baseline_latest_event_sha,
            msg="aggregate event-sha must not advance for a failed batch",
        )

    def _baseline_event_sha(self) -> str | None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT event_sha256 FROM incident_events "
                "WHERE incident_id = ? ORDER BY aggregate_version DESC LIMIT 1",
                (self.incident_id,),
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def _projection_aggregate_version(self) -> int | None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT aggregate_version FROM incident_current "
                "WHERE incident_id = ?",
                (self.incident_id,),
            ).fetchone()
            return int(row[0]) if row else None
        finally:
            conn.close()

    def _projection_last_event_seq(self) -> int | None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT last_event_seq FROM incident_current "
                "WHERE incident_id = ?",
                (self.incident_id,),
            ).fetchone()
            return int(row[0]) if row else None
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
