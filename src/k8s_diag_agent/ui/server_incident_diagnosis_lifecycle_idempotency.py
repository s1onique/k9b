"""Atomic, idempotent application of diagnosis-loop lifecycle transitions.

This module owns the authoritative critical section for the internal
diagnosis-loop lifecycle endpoint. It is deliberately separated from the
HTTP request/response handler so the idempotency + concurrency contract
lives in one focused place:

    begin authoritative critical section (per-store lock)
        ↓
    look up idempotency key
        ├─ same key + same fingerprint → return stored result (replay)
        ├─ same key + different fingerprint → conflict
        └─ absent → apply transition
                     persist idempotency record (atomic, non-swallowed)
        ↓
    commit / release lock

The idempotency lookup happens **before** the transition is applied,
the whole operation runs under a lock so two concurrent deliveries
cannot both apply, a canonical payload fingerprint is stored and
compared so a same-key/different-payload request is rejected, and the
idempotency record is written as part of the same critical section as
the mutation (it is never swallowed as best-effort).

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R1)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from weakref import WeakKeyDictionary

if TYPE_CHECKING:
    from ..collect.incident_store_sqlite import SQLiteIncidentStore

_logger = logging.getLogger(__name__)


# Same-process lock for the in-memory fallback path. The
# SQLite-backed critical section lives in
# :mod:`incident_store_sqlite_lifecycle_idempotency` and serializes
# across processes via ``BEGIN IMMEDIATE`` instead of this lock;
# this lock only guards the in-process ``IncidentStore`` path used
# in tests.
_IDEMPOTENCY_LOCK = threading.RLock()

# In-memory idempotency registry, keyed to the store instance so
# each store gets its own clean slate. SQLite-backed stores do NOT
# use this registry; they delegate to
# :func:`apply_lifecycle_transition_atomic` which persists the
# record inside the same transaction as the mutation.
_STORE_REGISTRIES: WeakKeyDictionary[Any, dict[tuple[Any, ...], dict[str, Any]]] = (
    WeakKeyDictionary()
)


def _registry_for(store: Any) -> dict[tuple[Any, ...], dict[str, Any]]:
    """Return the in-memory idempotency registry bound to ``store``.

    Used only for non-SQLite stores (tests). The registry lives and
    dies with the store instance. Stores that cannot be weakly
    referenced fall back to an instance attribute so the record
    still shares the store's lifetime.
    """
    try:
        reg = _STORE_REGISTRIES.get(store)
        if reg is None:
            reg = {}
            _STORE_REGISTRIES[store] = reg
        return reg
    except TypeError:
        reg = getattr(store, "_diag_lifecycle_idempotency", None)
        if reg is None:
            reg = {}
            store._diag_lifecycle_idempotency = reg
        return reg


def _idempotency_key(
    *,
    incident_id: str,
    transition: str,
    collector_run_id: str,
    diagnosis_run_id: str | None,
) -> tuple[Any, ...]:
    return (incident_id, transition, collector_run_id, diagnosis_run_id)


def _payload_fingerprint(payload: dict[str, Any]) -> str:
    """Compute a canonical fingerprint over the request payload.

    The fingerprint intentionally excludes the delivery timestamp
    (``occurredAt``) and the identity fields already captured by the
    idempotency key. It captures the semantic payload (review packet
    name, check counts, decision, unavailable reason, ...) so a repeat
    delivery that reuses the identity but changes the payload is
    detected as a conflict rather than collapsed as a replay.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sqlite_store(store: Any) -> bool:
    """Return True when ``store`` is a SQLite-backed incident store.

    Detection is by class identity (not duck typing) so a misnamed
    subclass does not accidentally pick up the SQLite critical
    section.
    """
    from ..collect.incident_store_sqlite import SQLiteIncidentStore

    return isinstance(store, SQLiteIncidentStore)


def _apply_transition_to_store(
    *,
    store: Any,
    transition: str,
    incident_id: str,
    collector_run_id: str,
    diagnosis_run_id: str | None,
    payload: dict[str, Any],
) -> Any:
    """Apply the bounded transition to the backend-owned store.

    Returns the updated incident (or ``None`` when the incident is
    absent). Raises on persistence failure; the caller translates the
    exception into a ``persistence_failed`` outcome.
    """
    run_id = diagnosis_run_id or ""
    if transition == "started":
        return store.mark_diagnosis_loop_started(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
        )
    if transition == "failed":
        return store.mark_diagnosis_loop_failed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            unavailable_reason=str(payload.get("unavailable_reason", "")) or None,
        )
    if transition == "completed":
        return store.mark_diagnosis_loop_completed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            review_packet_name=(
                str(payload["review_packet_name"])
                if payload.get("review_packet_name") is not None
                else None
            ),
            checks_requested=int(payload.get("checks_requested", 0) or 0),
            checks_run=int(payload.get("checks_run", 0) or 0),
            checks_rejected=int(payload.get("checks_rejected", 0) or 0),
            decision=(
                str(payload["decision"])
                if payload.get("decision") is not None
                else None
            ),
        )
    raise ValueError(f"unsupported transition: {transition!r}")


def apply_transition_idempotently(
    *,
    transition: str,
    incident_id: str,
    collector_run_id: str,
    diagnosis_run_id: str | None,
    occurred_at: datetime,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Apply the transition idempotently to the canonical backend store.

    The complete lookup → apply → record sequence runs under
    ``_IDEMPOTENCY_LOCK`` so concurrent duplicate deliveries cannot
    both apply the transition. Returns a ``result`` dict with one of:

    * ``{"outcome": "applied", "idempotent_replay": bool}``
    * ``{"outcome": "replay_mismatch"}``          (same key, different payload)
    * ``{"outcome": "incident_not_found"}``
    * ``{"outcome": "persistence_failed", "exception_type": str, "detail": str}``
    """
    from ..collect.incident_store_provider import get_incident_store

    store = get_incident_store()
    fingerprint = _payload_fingerprint(payload)

    # SQLite-backed stores get the durable critical section: the
    # mutation AND the idempotency record are written inside the same
    # ``BEGIN IMMEDIATE`` transaction, so two concurrent backend
    # processes serialize on the database and the result survives a
    # crash-restart. This is what makes restart-durable and
    # multi-process idempotency hold.
    if _is_sqlite_store(store):
        from ..collect.incident_store_sqlite_lifecycle_idempotency import (
            apply_lifecycle_transition_atomic,
        )

        return apply_lifecycle_transition_atomic(
            store=cast("SQLiteIncidentStore", store),
            transition=transition,
            incident_id=incident_id,
            run_id=diagnosis_run_id,
            collector_run_id=collector_run_id,
            fingerprint=fingerprint,
            occurred_at=occurred_at,
            payload=dict(payload),
        )

    # In-memory / test-only path: same-process lock + per-store
    # registry. This path is intentionally process-local because the
    # in-memory store has no shared durable state.
    key = _idempotency_key(
        incident_id=incident_id,
        transition=transition,
        collector_run_id=collector_run_id,
        diagnosis_run_id=diagnosis_run_id,
    )
    with _IDEMPOTENCY_LOCK:
        registry = _registry_for(store)

        # 1. Idempotency lookup BEFORE applying the transition.
        existing = registry.get(key)
        if existing is not None:
            if existing.get("fingerprint") != fingerprint:
                # Same idempotency key, different payload → conflict.
                return {"outcome": "replay_mismatch"}
            # Same key + same fingerprint → return the prior outcome
            # without reapplying the transition.
            return {"outcome": "applied", "idempotent_replay": True}

        # 2. Absent key → apply the transition.
        try:
            updated = _apply_transition_to_store(
                store=store,
                transition=transition,
                incident_id=incident_id,
                collector_run_id=collector_run_id,
                diagnosis_run_id=diagnosis_run_id,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001 - boundary translation
            return {
                "outcome": "persistence_failed",
                "exception_type": type(exc).__name__,
                "detail": f"store raised {type(exc).__name__}: {exc}",
            }

        if updated is None:
            # Incident absent: do NOT record an idempotency marker so a
            # later delivery (after the incident exists) can apply.
            return {"outcome": "incident_not_found"}

        # 3. Persist the idempotency record as part of the same critical
        #    section as the mutation. This assignment is in-memory and
        #    cannot silently fail; the record is therefore durable for
        #    the lifetime of the backend-owned store and atomic with the
        #    applied transition. It is NOT best-effort.
        registry[key] = {
            "fingerprint": fingerprint,
            "occurred_at": occurred_at.isoformat(),
            "applied": True,
        }

        return {"outcome": "applied", "idempotent_replay": False}


def _project_lifecycle_event(
    *,
    store: Any,
    incident_id: str,
    transition: str,
    collector_run_id: str,
    diagnosis_run_id: str | None,
    occurred_at: datetime,
    payload: dict[str, Any],
) -> None:
    """Project an observability-only lifecycle event onto the incident.

    Unlike the idempotency record (which is authoritative and never
    swallowed), this projection is best-effort and only runs on stores
    that support ``append_event``.
    """
    append_event = getattr(store, "append_event", None)
    if append_event is None:
        return
    try:
        from ..collect.incident_events import (
            IncidentEvent,
            IncidentEventActor,
            IncidentEventType,
            make_event_id,
        )

        incident = store.get_incident(incident_id)
        if incident is None:
            return
        if transition == "completed":
            event_type = IncidentEventType.REVIEW_PACKET_GENERATED
        else:
            event_type = IncidentEventType.STATUS_CHANGED
        event = IncidentEvent(
            event_id=make_event_id(incident_id, transition, occurred_at),
            incident_id=incident_id,
            event_type=event_type,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=occurred_at,
            message=f"diagnosis-loop {transition}",
            data={
                "transition": transition,
                "collector_run_id": collector_run_id,
                "diagnosis_run_id": diagnosis_run_id,
                "payload": dict(payload),
            },
        )
        append_event(incident_id, event)
    except Exception:  # noqa: BLE001 - projection is observability-only
        _logger.debug(
            "lifecycle event projection failed",
            exc_info=True,
            extra={"incident_id": incident_id, "transition": transition},
        )


__all__ = [
    "apply_transition_idempotently",
]
