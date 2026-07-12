"""Authority seam for automatic-diagnosis incident reads and lifecycle writes.

This module owns the **single** typed boundary that the automatic-diagnosis
processor crosses when it needs to record diagnosis-loop lifecycle
transitions (``started`` / ``failed`` / ``completed``) through the
configured incident authority (local in-memory store, or backend
internal API).

The aggregate eligibility evaluator (:func:`evaluate_incident_eligibility`)
and the local-store compatibility wrapper (:func:`check_incident_eligibility`)
are defined in :mod:`incident_diagnosis_auto_loop_config` and re-exported
here for callers that want the canonical API through this seam.

The split-authority defect closed by
``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` is anchored in this
seam:

* The previous code re-resolved the backend-fetched incident through
  the **local** ``get_incident_store()`` for eligibility evaluation,
  producing ``not_eligible: incident_not_found`` on the scheduler even
  though the backend had returned HTTP 200 with a valid canonical
  incident. The aggregate evaluator accepts a typed
  :class:`Incident` and does not call any incident resolver.
* The previous code also routed diagnosis-lifecycle writes through the
  local store even in backend mode. The lifecycle seam below resolves
  the same dispatch configuration the incident-detail lookup uses, and
  routes writes accordingly.

To keep this module at a maintainable size, the implementation is
split across four sibling modules:

* :mod:`incident_diagnosis_authority_seam_types` — closed vocabulary,
  bounded typed outcomes, schema-version constant.
* :mod:`incident_diagnosis_authority_seam_local` — local-mode writer.
* :mod:`incident_diagnosis_authority_seam_backend` — backend-mode HTTP
  transport + response translator.

This seam module is the only public entry point; callers MUST NOT
import from the sibling modules directly.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .incident_diagnosis_authority_seam_types import (
    LIFECYCLE_SCHEMA_VERSION,
    LifecycleDispatchMode,
    LifecycleTransition,
    LifecycleWriteApplied,
    LifecycleWriteFailed,
    LifecycleWriteOutcome,
    LifecycleWriteRejected,
    LifecycleWriteSkipped,
)
from .incident_diagnosis_auto_loop_config import (
    check_incident_eligibility,
    evaluate_incident_eligibility,
)
from .incident_diagnosis_dispatch_contracts import (
    ENV_BACKEND_URL,
    ENV_INTERNAL_API_TOKEN,
    ENV_PROCESS_ROLE,
    ENV_PROMOTION_MODE,
    ENV_STORE_BACKEND,
    MODE_BACKEND_API,
    IncidentDiagnosisDispatchConfig,
)

_logger = logging.getLogger(__name__)


__all__ = [
    "LifecycleTransition",
    "LifecycleDispatchMode",
    "LifecycleWriteOutcome",
    "LifecycleWriteApplied",
    "LifecycleWriteRejected",
    "LifecycleWriteFailed",
    "LifecycleWriteSkipped",
    "evaluate_incident_eligibility",
    "check_incident_eligibility",
    "record_diagnosis_loop_started",
    "record_diagnosis_loop_failed",
    "record_diagnosis_loop_completed",
    "build_lifecycle_request",
]


# ---------------------------------------------------------------------------
# Lifecycle authority seam
# ---------------------------------------------------------------------------


def _resolve_lifecycle_dispatch_mode() -> LifecycleDispatchMode:
    """Resolve the lifecycle dispatch mode from the same env config the
    incident-detail dispatcher uses.

    Keeping the resolution in lock-step with
    :mod:`incident_diagnosis_dispatch_contracts` is critical: a
    scheduler that performs backend-mode incident reads MUST also
    perform backend-mode lifecycle writes, otherwise it silently
    diverges from the configured authority and writes to a
    non-authoritative store.
    """
    config = IncidentDiagnosisDispatchConfig(
        mode=os.environ.get(ENV_PROMOTION_MODE, "auto").lower(),  # type: ignore[arg-type]
        backend_url=os.environ.get(ENV_BACKEND_URL),
        internal_api_token=os.environ.get(ENV_INTERNAL_API_TOKEN),
        store_backend=os.environ.get(ENV_STORE_BACKEND, "memory").lower(),
        process_role=os.environ.get(ENV_PROCESS_ROLE, "").lower(),
    )
    resolved = config.resolved_mode()
    if resolved == MODE_BACKEND_API:
        return LifecycleDispatchMode.BACKEND
    return LifecycleDispatchMode.LOCAL


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class _LifecycleRequest:
    """Internal wire-shape for the backend lifecycle endpoint."""

    schema_version: int
    incident_id: str
    transition: LifecycleTransition
    collector_run_id: str
    diagnosis_run_id: str | None
    occurred_at: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "incidentId": self.incident_id,
            "transition": self.transition.value,
            "collectorRunId": self.collector_run_id,
            "occurredAt": self.occurred_at,
            "payload": dict(self.payload),
        }
        if self.diagnosis_run_id is not None:
            body["diagnosisRunId"] = self.diagnosis_run_id
        return body


def build_lifecycle_request(
    *,
    incident_id: str,
    transition: LifecycleTransition,
    collector_run_id: str,
    diagnosis_run_id: str | None,
    payload: dict[str, Any] | None = None,
) -> _LifecycleRequest:
    """Construct the canonical lifecycle wire-payload.

    Centralises the schema-version and field-naming contract so the
    scheduler client and the backend handler cannot drift.
    """
    return _LifecycleRequest(
        schema_version=LIFECYCLE_SCHEMA_VERSION,
        incident_id=str(incident_id),
        transition=transition,
        collector_run_id=str(collector_run_id),
        diagnosis_run_id=(
            str(diagnosis_run_id) if diagnosis_run_id is not None else None
        ),
        occurred_at=_now_iso(),
        payload=dict(payload or {}),
    )


# ---------------------------------------------------------------------------
# Public lifecycle authority API
# ---------------------------------------------------------------------------


def _dispatch_lifecycle(
    *,
    transition: LifecycleTransition,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
    payload: dict[str, Any],
) -> LifecycleWriteOutcome:
    """Resolve the dispatch mode and apply the transition.

    The local- and backend-mode writers are imported lazily to avoid a
    circular import: each writer imports :func:`build_lifecycle_request`
    from this seam module, so this module cannot import them at
    top-level. The dispatch call only happens at runtime, by which time
    the seam module is fully initialised.
    """
    # Lazy imports to break the circular cycle between this seam module
    # and its sibling writers.
    from .incident_diagnosis_authority_seam_backend import (
        _record_lifecycle_backend,
    )
    from .incident_diagnosis_authority_seam_local import (
        _record_lifecycle_local,
    )

    mode = _resolve_lifecycle_dispatch_mode()
    if mode == LifecycleDispatchMode.LOCAL:
        return _record_lifecycle_local(
            transition=transition,
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            payload=payload,
        )
    return _record_lifecycle_backend(
        transition=transition,
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
        payload=payload,
    )


def _emit_lifecycle_event(
    *,
    outcome: LifecycleWriteOutcome,
    collector_run_id: str,
    diagnosis_run_id: str,
    incident_access_mode: str,
) -> None:
    """Emit a structured INFO-level event for the lifecycle write.

    Events:
        automatic-diagnosis-lifecycle-transition-applied
        automatic-diagnosis-lifecycle-transition-rejected
        automatic-diagnosis-lifecycle-transition-failed
        automatic-diagnosis-lifecycle-transition-skipped
    """
    if isinstance(outcome, LifecycleWriteApplied):
        event = "automatic-diagnosis-lifecycle-transition-applied"
        extra: dict[str, Any] = {
            "event": event,
            "incident_id": outcome.incident_id,
            "collector_run_id": collector_run_id,
            "diagnosis_run_id": diagnosis_run_id,
            "transition": outcome.transition.value,
            "incident_access_mode": incident_access_mode,
            "http_status": outcome.http_status,
            "idempotent_replay": outcome.idempotent_replay,
            "applied": True,
        }
        if outcome.detail is not None:
            extra["detail"] = outcome.detail
        _logger.info("lifecycle transition applied", extra=extra)
        return

    if isinstance(outcome, LifecycleWriteRejected):
        event = "automatic-diagnosis-lifecycle-transition-rejected"
        extra = {
            "event": event,
            "incident_id": outcome.incident_id,
            "collector_run_id": collector_run_id,
            "diagnosis_run_id": diagnosis_run_id,
            "transition": outcome.transition.value,
            "incident_access_mode": incident_access_mode,
            "http_status": outcome.http_status,
            "failure_code": outcome.reason_code,
            "applied": False,
        }
        if outcome.detail is not None:
            extra["detail"] = outcome.detail
        _logger.info("lifecycle transition rejected", extra=extra)
        return

    if isinstance(outcome, LifecycleWriteFailed):
        event = "automatic-diagnosis-lifecycle-transition-failed"
        extra = {
            "event": event,
            "incident_id": outcome.incident_id,
            "collector_run_id": collector_run_id,
            "diagnosis_run_id": diagnosis_run_id,
            "transition": outcome.transition.value,
            "incident_access_mode": incident_access_mode,
            "http_status": outcome.http_status,
            "failure_code": outcome.reason_code,
            "applied": False,
        }
        if outcome.exception_type is not None:
            extra["exception_type"] = outcome.exception_type
        if outcome.detail is not None:
            extra["detail"] = outcome.detail
        _logger.warning("lifecycle transition failed", extra=extra)
        return

    if isinstance(outcome, LifecycleWriteSkipped):
        event = "automatic-diagnosis-lifecycle-transition-skipped"
        extra = {
            "event": event,
            "incident_id": outcome.incident_id,
            "collector_run_id": collector_run_id,
            "diagnosis_run_id": diagnosis_run_id,
            "transition": outcome.transition.value,
            "incident_access_mode": incident_access_mode,
            "applied": False,
            "reason": outcome.reason,
        }
        _logger.info("lifecycle transition skipped", extra=extra)
        return


def record_diagnosis_loop_started(
    *,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
) -> LifecycleWriteOutcome:
    """Record that the automatic-diagnosis loop started for an incident."""
    outcome = _dispatch_lifecycle(
        transition=LifecycleTransition.STARTED,
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
        payload={},
    )
    _emit_lifecycle_event(
        outcome=outcome,
        collector_run_id=collector_run_id,
        diagnosis_run_id=run_id,
        incident_access_mode=_resolve_lifecycle_dispatch_mode().value,
    )
    return outcome


def record_diagnosis_loop_failed(
    *,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
    unavailable_reason: str,
) -> LifecycleWriteOutcome:
    """Record that the automatic-diagnosis loop failed for an incident."""
    outcome = _dispatch_lifecycle(
        transition=LifecycleTransition.FAILED,
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
        payload={"unavailable_reason": str(unavailable_reason)},
    )
    _emit_lifecycle_event(
        outcome=outcome,
        collector_run_id=collector_run_id,
        diagnosis_run_id=run_id,
        incident_access_mode=_resolve_lifecycle_dispatch_mode().value,
    )
    return outcome


def record_diagnosis_loop_completed(
    *,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
    review_packet_name: str | None = None,
    checks_requested: int = 0,
    checks_run: int = 0,
    checks_rejected: int = 0,
    decision: str | None = None,
) -> LifecycleWriteOutcome:
    """Record that the automatic-diagnosis loop completed for an incident."""
    payload: dict[str, Any] = {
        "checks_requested": int(checks_requested),
        "checks_run": int(checks_run),
        "checks_rejected": int(checks_rejected),
    }
    if review_packet_name is not None:
        payload["review_packet_name"] = str(review_packet_name)
    if decision is not None:
        payload["decision"] = str(decision)
    outcome = _dispatch_lifecycle(
        transition=LifecycleTransition.COMPLETED,
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
        payload=payload,
    )
    _emit_lifecycle_event(
        outcome=outcome,
        collector_run_id=collector_run_id,
        diagnosis_run_id=run_id,
        incident_access_mode=_resolve_lifecycle_dispatch_mode().value,
    )
    return outcome
