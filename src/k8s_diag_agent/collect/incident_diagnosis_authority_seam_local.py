"""Local-mode lifecycle writer for the automatic-diagnosis authority seam.

This module owns the ``local`` half of the lifecycle dispatch split: it
calls the in-process :class:`IncidentStore` directly when the scheduler
resolves ``LifecycleDispatchMode.LOCAL``. The backend-mode half lives in
:mod:`incident_diagnosis_authority_seam_backend` and is selected when
the dispatcher resolves ``LifecycleDispatchMode.BACKEND``.

The seam module (:mod:`incident_diagnosis_authority_seam`) is the only
public entry point; callers MUST NOT import from this file directly.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
"""

from __future__ import annotations

from typing import Any

from .incident_diagnosis_authority_seam_types import (
    LifecycleTransition,
    LifecycleWriteApplied,
    LifecycleWriteFailed,
    LifecycleWriteOutcome,
)
from .incident_store_provider import get_incident_store


def _record_lifecycle_local(
    *,
    transition: LifecycleTransition,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
    payload: dict[str, Any],
) -> LifecycleWriteOutcome:
    """Apply a lifecycle transition through the local incident store.

    The local store returns ``None`` when the incident is absent, which
    we surface as :class:`LifecycleWriteFailed` with the canonical
    ``incident_not_found`` reason so the scheduler can distinguish it
    from generic persistence failures.
    """
    store = get_incident_store()
    try:
        if transition == LifecycleTransition.STARTED:
            updated = store.mark_diagnosis_loop_started(
                incident_id=incident_id,
                run_id=run_id,
                collector_run_id=collector_run_id,
            )
        elif transition == LifecycleTransition.FAILED:
            updated = store.mark_diagnosis_loop_failed(
                incident_id=incident_id,
                run_id=run_id,
                collector_run_id=collector_run_id,
                unavailable_reason=str(payload.get("unavailable_reason", "")) or None,
            )
        elif transition == LifecycleTransition.COMPLETED:
            updated = store.mark_diagnosis_loop_completed(
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
        else:  # pragma: no cover - exhaustiveness guard
            return LifecycleWriteFailed(
                transition=transition,
                incident_id=incident_id,
                reason_code="unsupported_transition",
                detail=f"unsupported transition: {transition!r}",
            )
    except Exception as exc:  # noqa: BLE001 - boundary translation
        return LifecycleWriteFailed(
            transition=transition,
            incident_id=incident_id,
            reason_code="local_persistence_failed",
            detail=f"local store raised {type(exc).__name__}: {exc}",
            exception_type=type(exc).__name__,
        )

    if updated is None:
        return LifecycleWriteFailed(
            transition=transition,
            incident_id=incident_id,
            reason_code="incident_not_found",
            detail=(
                f"local store has no incident for {incident_id!r}"
            ),
        )
    return LifecycleWriteApplied(
        transition=transition,
        incident_id=incident_id,
        idempotent_replay=False,
        http_status=None,
        detail="applied via local store",
    )
