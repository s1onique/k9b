"""R3 regression tests for SQLite lifecycle idempotency (core).

Closes R3-1, R3-5, R3-6 blockers from the
``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:

* **R3-1** — existing v1 production databases must upgrade in
  place so the lifecycle endpoint does not crash with
  ``no such table: lifecycle_idempotency``.
* **R3-5** — the UNIQUE index must still enforce uniqueness when
  ``diagnosis_run_id`` is ``NULL``.
* **R3-6** — a fault injected between event append and idempotency
  insert must roll back the event, projection, and cache.

Companion files split for LLM-friendly size limits:

* ``test_incident_store_sqlite_lifecycle_idempotency_r3_apply.py``
  — R3-2 lifecycle-applies projection/cache updates.
* ``test_incident_store_sqlite_lifecycle_idempotency_r3_events.py``
  — R3-3 hash-chain tests.
* ``test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py``
  — R3-4 capability-seam tests.

The tests rely on the canonical
:meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`
path that the R2 module now delegates to.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R3)
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


class TestR3SchemaUpgrade(TestCase):
    """R3-1: Existing v1 databases upgrade in place to v2.

    Builds a genuine v1 schema (no ``lifecycle_idempotency`` table),
    records ``SCHEMA_VERSION = 1`` in ``schema_migrations``, then
    reopens the file with the new code and asserts that the table
    + index are installed and that ``schema_migrations`` is bumped
    to ``2``.
    """

    def test_v1_database_upgrades_to_v2_with_table_and_index(self) -> None:
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "v1_production.sqlite3"
        try:
            from k8s_diag_agent.collect import (
                incident_store_sqlite_schema as schema_module,
            )

            v1_init_statements = [
                schema_module.CREATE_SCHEMA_MIGRATIONS,
                schema_module.CREATE_INCIDENT_EVENTS,
                schema_module.CREATE_EVENTS_INDICES,
                schema_module.CREATE_INCIDENT_CURRENT,
                schema_module.CREATE_CURRENT_INDICES,
                schema_module.CREATE_TRIGGERS,
            ]
            with sqlite3.connect(str(db_path)) as conn:
                for stmt in v1_init_statements:
                    conn.executescript(stmt)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (1, "2025-01-01T00:00:00+00:00"),
                )
                conn.commit()
                tables = {
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            self.assertNotIn(
                "lifecycle_idempotency",
                tables,
                "v1-shaped database must not have lifecycle_idempotency yet",
            )

            # Reopen the database with the new code. ``run_migrations``
            # sees ``current_version = 1 < SCHEMA_VERSION = 2`` and
            # applies the v2 upgrade (CREATE TABLE IF NOT EXISTS
            # lifecycle_idempotency + the COALESCE-based UNIQUE
            # index).
            SQLiteIncidentStore(db_path)

            with sqlite3.connect(str(db_path)) as conn:
                tables_after = {
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                indexes_after = {
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    ).fetchall()
                }
                recorded_version = conn.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0]

            self.assertIn(
                "lifecycle_idempotency",
                tables_after,
                "lifecycle_idempotency table must be added by the v2 upgrade",
            )
            self.assertIn(
                "idx_lifecycle_idempotency_key",
                indexes_after,
                "lifecycle_idempotency unique index must be added by the v2 upgrade",
            )
            self.assertGreaterEqual(int(recorded_version), 2)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestR3Rollback(TestCase):
    """R3-6: Fault between event append and idempotency insert must
    roll back the event, projection, and cache.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_idempotency_insert_failure_rolls_back_everything(self) -> None:
        from unittest import mock

        from k8s_diag_agent.collect import (
            incident_store_sqlite_context as context_module,
        )

        store = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(store)

        with store._connect() as conn:
            ev_count_before = conn.execute(
                "SELECT COUNT(*) FROM incident_events"
            ).fetchone()[0]
            idem_count_before = conn.execute(
                "SELECT COUNT(*) FROM lifecycle_idempotency"
            ).fetchone()[0]
            projection_before = conn.execute(
                "SELECT current_state_json FROM incident_current "
                "WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()[0]
        cache_before = (
            store._incidents[incident_id].to_dict()
            if incident_id in store._incidents
            else None
        )

        def _failing_insert(*args: Any, **kwargs: Any) -> None:
            raise sqlite3.OperationalError(
                "injected fault: idempotency insert"
            )

        with mock.patch.object(
            context_module,
            "_insert_lifecycle_idempotency_row",
            side_effect=_failing_insert,
        ):
            result = apply_lifecycle_transition_atomic(
                store,
                transition="completed",
                incident_id=incident_id,
                run_id="run-rb",
                collector_run_id="collector-rb",
                fingerprint="fp-rb",
                occurred_at=_OCCURRED_AT,
                payload=_payload_completed(),
            )

        self.assertEqual(result["outcome"], "persistence_failed")
        self.assertIn("idempotency", result.get("detail", ""))

        with store._connect() as conn:
            ev_count_after = conn.execute(
                "SELECT COUNT(*) FROM incident_events"
            ).fetchone()[0]
            idem_count_after = conn.execute(
                "SELECT COUNT(*) FROM lifecycle_idempotency"
            ).fetchone()[0]
            projection_after = conn.execute(
                "SELECT current_state_json FROM incident_current "
                "WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()[0]
        self.assertEqual(
            ev_count_after,
            ev_count_before,
            "event row must be rolled back when idempotency insert fails",
        )
        self.assertEqual(
            idem_count_after,
            idem_count_before,
            "idempotency row must not be present",
        )
        self.assertEqual(
            projection_after,
            projection_before,
            "incident_current projection must be unchanged",
        )

        cache_after = (
            store._incidents[incident_id].to_dict()
            if incident_id in store._incidents
            else None
        )
        self.assertEqual(cache_after, cache_before)


class TestR3MultiProcessRegression(TestCase):
    """R3 cross-check: the canonical path preserves the multi-process
    one-apply-one-replay contract.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_two_stores_one_apply_one_replay_through_canonical_path(self) -> None:
        process_a = SQLiteIncidentStore(self._db_path)
        incident_id = _populate(process_a)
        fingerprint = "fp-mp-r3"

        a_result = apply_lifecycle_transition_atomic(
            process_a,
            transition="completed",
            incident_id=incident_id,
            run_id="run-mp-r3",
            collector_run_id="collector-mp-r3",
            fingerprint=fingerprint,
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(a_result["outcome"], "applied")
        self.assertFalse(a_result["idempotent_replay"])

        process_b = SQLiteIncidentStore(self._db_path)
        b_result = apply_lifecycle_transition_atomic(
            process_b,
            transition="completed",
            incident_id=incident_id,
            run_id="run-mp-r3",
            collector_run_id="collector-mp-r3",
            fingerprint=fingerprint,
            occurred_at=_OCCURRED_AT,
            payload=_payload_completed(),
        )
        self.assertEqual(b_result["outcome"], "applied")
        self.assertTrue(b_result["idempotent_replay"])

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
        self.assertEqual(event_count, 1)
        self.assertEqual(idem_count, 1)


class TestR3SchemaUniqueness(TestCase):
    """R3-5: NULL ``diagnosis_run_id`` must still participate in the
    UNIQUE constraint. The COALESCE expression in the index makes
    NULL compare equal to ``''``.
    """

    def setUp(self) -> None:
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_duplicate_null_diagnosis_run_id_is_rejected(self) -> None:
        SQLiteIncidentStore(self._db_path)
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """
                INSERT INTO lifecycle_idempotency (
                    incident_id, transition, collector_run_id,
                    diagnosis_run_id, fingerprint, occurred_at, applied_at
                ) VALUES (?, ?, ?, NULL, 'fp-1',
                          '2026-01-01T00:00:00+00:00',
                          '2026-01-01T00:00:00+00:00')
                """,
                ("inc-1", "started", "collector-1"),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO lifecycle_idempotency (
                        incident_id, transition, collector_run_id,
                        diagnosis_run_id, fingerprint, occurred_at, applied_at
                    ) VALUES (?, ?, ?, NULL, 'fp-2',
                              '2026-01-01T00:00:00+00:00',
                              '2026-01-01T00:00:00+00:00')
                    """,
                    ("inc-1", "started", "collector-1"),
                )


__all__ = [
    "TestR3SchemaUpgrade",
    "TestR3Rollback",
    "TestR3MultiProcessRegression",
    "TestR3SchemaUniqueness",
]
