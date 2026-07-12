"""SQLite-backed adapter for the diagnosis-loop lifecycle idempotency contract.

R3 ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01: this module is
now a thin adapter. The durable critical section lives on
:class:`k8s_diag_agent.collect.incident_store_sqlite_context.SQLiteWriteContext`
as :meth:`apply_diagnosis_lifecycle_idempotently`. That single canonical
method owns:

* ``BEGIN IMMEDIATE`` writer serialization,
* the idempotency lookup,
* the canonical hash-chained event append,
* the canonical ``incident_current`` projection update,
* the idempotency record insert,
* the commit,
* the in-memory cache refresh.

This module only:

1. Resolves ``diagnosis_run_id`` from the request payload,
2. Opens the store's write context (in-process lock + connection),
3. Delegates to the canonical context method,
4. Translates any raised exception into the bounded
   ``persistence_failed`` outcome that the upper layer (HTTP
   handler / dispatch) expects.

It MUST NOT reach into ``store._write_lock``, ``store._connect()``,
``store._incidents``, ``store._snapshot_incident()``, or
``store._state_to_incident()`` directly. All authority flows through
the canonical write context so the hash chain, projection, and cache
cannot drift.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .incident_store_sqlite import SQLiteIncidentStore

_logger = logging.getLogger(__name__)


def apply_lifecycle_transition_atomic(
    store: SQLiteIncidentStore,
    *,
    transition: str,
    incident_id: str,
    run_id: str | None,
    collector_run_id: str,
    fingerprint: str,
    occurred_at: datetime,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Apply a lifecycle transition atomically with the idempotency record.

    Returns one of:

    * ``{"outcome": "applied", "idempotent_replay": False,
        "incident": Incident | None}``
    * ``{"outcome": "applied", "idempotent_replay": True}``
    * ``{"outcome": "replay_mismatch"}``
    * ``{"outcome": "incident_not_found"}``
    * ``{"outcome": "persistence_failed",
        "exception_type": str, "detail": str}``

    Implementation note: the canonical path is owned by
    :meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`.
    This function is the SQLite entry point for the upper-layer
    ``apply_transition_idempotently`` dispatch in
    :mod:`k8s_diag_agent.ui.server_incident_diagnosis_lifecycle_idempotency`.
    """
    diagnosis_run_id_raw = payload.get("diagnosis_run_id")
    diagnosis_run_id: str | None = (
        diagnosis_run_id_raw if isinstance(diagnosis_run_id_raw, str) else None
    )
    if diagnosis_run_id is None:
        diagnosis_run_id = run_id

    try:
        with store._write_context() as ctx:
            return ctx.apply_diagnosis_lifecycle_idempotently(
                transition=transition,
                incident_id=incident_id,
                run_id=run_id,
                collector_run_id=collector_run_id,
                diagnosis_run_id=diagnosis_run_id,
                fingerprint=fingerprint,
                occurred_at=occurred_at,
                payload=dict(payload),
            )
    except Exception as exc:  # noqa: BLE001 - boundary translation
        return {
            "outcome": "persistence_failed",
            "exception_type": type(exc).__name__,
            "detail": f"sqlite store raised {type(exc).__name__}: {exc}",
        }


__all__ = [
    "apply_lifecycle_transition_atomic",
]