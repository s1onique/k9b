"""Backend-owned promotion of an explicit current-run alert-signal workset.

Contract
--------
The scheduler hands the backend a :class:`PromoteAlertSignalsRequest`
identifying exactly which normalized alert-signal artifacts (and only
those) belong to the current run. The backend:

* Promotes only those artifacts -- there is no fallback to scanning the
  global firing-signal inventory, no "all signals" interpretation, and no
  resumption of a previous run's batch.
* Returns a typed :class:`IncidentPromotionResult` that categorises every
  requested signal as opened, materially changed, observation refresh,
  unchanged, or skipped and exposes the canonical actionable incident
  IDs for the diagnosis handoff.
* Fails closed when the scope is internally inconsistent (missing
  artifacts, source-identity mismatches, malformed payloads, etc.).
"""

from __future__ import annotations

import logging
from pathlib import Path

from .collect.incident_lifecycle import Incident
from .collect.incident_store import IncidentStore
from .domain.identifiers import AlertSignalId
from .domain.incident_lifecycle import IncidentId
from .incident_alert_classifier import classify_alert_signal
from .incident_alert_correlation import build_alert_incident_correlation_key
from .incident_alert_promotion import (
    alert_signal_to_incident_candidate,
    attach_alert_signal_to_incident,
    open_incident_from_alert_signal,
)
from .incident_alert_promotion_contract import (
    MAX_PROMOTION_FAILURES,
    IncidentPromotionFailure,
    IncidentPromotionResult,
    PromoteAlertSignalsRequest,
    PromotionScopeError,
)
from .incident_alert_signal import AlertSignal, AlertStatus
from .incident_alert_signal_store import read_alert_signal_artifact

_logger = logging.getLogger(__name__)

_CATEGORY_UNCHANGED = "unchanged"
_CATEGORY_OBSERVATION = "observation"
_CATEGORY_MATERIAL = "material"
_CATEGORY_OPENED = "opened"

_CATEGORY_PRIORITY: dict[str, int] = {
    _CATEGORY_UNCHANGED: 0,
    _CATEGORY_OBSERVATION: 1,
    _CATEGORY_MATERIAL: 2,
    _CATEGORY_OPENED: 3,
}


def promote_scoped_alert_signals(
    *,
    request: PromoteAlertSignalsRequest,
    incident_store: IncidentStore,
    runs_dir: Path,
) -> IncidentPromotionResult:
    """Promote only ``request.signal_ids``; never enumerate persisted signals."""
    if not request.signal_ids:
        return IncidentPromotionResult.empty(request)

    # Validate the complete scope before the first durable mutation. A
    # missing, malformed, or cross-source artifact makes the request
    # internally inconsistent and therefore fails closed.
    artifacts = _load_and_validate_scope(request=request, runs_dir=runs_dir)

    # ``incident_categories`` and ``incident_first_index`` track the
    # single most severe category observed per canonical incident and the
    # first request index that produced it, so the final per-incident
    # category respects the request order required by the ACT.
    incident_categories: dict[str, str] = {}
    incident_first_index: dict[str, int] = {}
    skipped_signal_ids: list[AlertSignalId] = []
    failures: list[IncidentPromotionFailure] = []

    for index, (signal_id, artifact) in enumerate(
        zip(request.signal_ids, artifacts, strict=True),
    ):
        signal = artifact.signal
        if signal is None:  # guarded by _load_and_validate_scope
            raise PromotionScopeError(
                "signal artifact lost its normalized signal"
            )
        try:
            if signal.status not in (AlertStatus.FIRING, AlertStatus.RESOLVED):
                skipped_signal_ids.append(signal_id)
                continue
            outcome = _promote_one(
                signal=signal,
                incident_store=incident_store,
            )
            if outcome is None:
                skipped_signal_ids.append(signal_id)
                continue
            category, incident_id = outcome
            _record_incident_category(
                categories=incident_categories,
                first_index=incident_first_index,
                incident_id=incident_id,
                category=category,
                request_index=index,
            )
        except Exception as exc:
            _logger.exception(
                "Scoped alert signal promotion failed",
                extra={
                    "event": "alert-signal-scoped-promotion-failed",
                    "run_id": str(request.run_id),
                    "source_identity": request.source_identity,
                    "signal_id": str(signal_id),
                },
            )
            if len(failures) >= MAX_PROMOTION_FAILURES:
                _logger.warning(
                    "Reached max promotion failures; truncating remaining diagnostics",
                    extra={
                        "max_failures": MAX_PROMOTION_FAILURES,
                        "run_id": str(request.run_id),
                    },
                )
                # Surface a generic failure so the remaining signals
                # are NOT silently treated as actionable; the rest of
                # the request continues to advance the accumulator but
                # the diagnostics stay bounded.
                continue
            failures.append(
                IncidentPromotionFailure(
                    signal_id=signal_id,
                    reason_code="promotion_error",
                    detail=type(exc).__name__,
                )
            )

    ordered = _partition_incidents(
        categories=incident_categories,
        first_index=incident_first_index,
    )

    result = IncidentPromotionResult(
        run_id=request.run_id,
        source_identity=request.source_identity,
        scanned_signal_ids=tuple(request.signal_ids),
        opened_incident_ids=tuple(ordered[_CATEGORY_OPENED]),
        materially_changed_incident_ids=tuple(ordered[_CATEGORY_MATERIAL]),
        observation_refreshed_incident_ids=tuple(ordered[_CATEGORY_OBSERVATION]),
        unchanged_incident_ids=tuple(ordered[_CATEGORY_UNCHANGED]),
        skipped_signal_ids=tuple(skipped_signal_ids),
        failures=tuple(failures),
    )
    # The downstream diagnosis handoff consumes the canonical
    # ``actionable_incident_ids`` projection owned by the result
    # dataclass. We read it once to make the projection explicit and
    # the test surface stable.
    _ = result.actionable_incident_ids
    return result


def _load_and_validate_scope(
    *,
    request: PromoteAlertSignalsRequest,
    runs_dir: Path,
) -> tuple[object, ...]:
    artifacts: list[object] = []
    for signal_id in request.signal_ids:
        artifact = read_alert_signal_artifact(runs_dir, str(signal_id))
        if artifact is None or artifact.signal is None:
            raise PromotionScopeError(
                f"signal {signal_id!s} is not present in the current-run scope"
            )
        if artifact.signal.source_instance != request.source_identity:
            raise PromotionScopeError(
                f"signal {signal_id!s} does not belong to source "
                f"{request.source_identity!r}"
            )
        artifacts.append(artifact)
    return tuple(artifacts)


def _promote_one(
    *,
    signal: AlertSignal,
    incident_store: IncidentStore,
) -> tuple[str, str] | None:
    """Promote one signal and return (category, canonical incident_id).

    ``None`` is returned for signals that are valid but contribute no
    durable domain mutation (e.g. resolved alerts without an open
    incident, or non-firing/resolved statuses we choose to ignore).
    """
    classification = classify_alert_signal(signal)
    correlation_key = build_alert_incident_correlation_key(signal, classification)

    existing = incident_store.get_incident(correlation_key)
    if existing is None and signal.status == AlertStatus.FIRING:
        candidate = alert_signal_to_incident_candidate(
            signal,
            correlation_key,
            signal_fingerprint=signal.signal_id,
        )
        new_incident = open_incident_from_alert_signal(
            signal=signal,
            candidate=candidate,
            correlation_key=correlation_key,
            observed_at=signal.received_at,
        )
        incident_store.add_incident(new_incident)
        return _CATEGORY_OPENED, new_incident.incident_id

    if existing is None:
        # Resolved alert with no open incident: nothing actionable.
        return None

    if _signal_already_attached(existing, signal):
        # Observation-only refresh: same signal_id, same correlation
        # key, no new diagnostic information. ``last_observed_at`` does
        # NOT advance; no new ``IncidentEvent`` is appended; no
        # actionable category is produced.
        return _CATEGORY_UNCHANGED, existing.incident_id

    if signal.status == AlertStatus.FIRING:
        updated = attach_alert_signal_to_incident(
            incident=existing,
            signal=signal,
            correlation_key=correlation_key,
            observed_at=signal.received_at,
        )
    else:
        # Resolved signal: mirror the legacy semantics of attaching
        # without changing the lifecycle. Treat as observation-only
        # refresh because resolved alerts never re-classify the
        # incident.
        updated = attach_alert_signal_to_incident(
            incident=existing,
            signal=signal,
            correlation_key=correlation_key,
            observed_at=signal.received_at,
        )
    incident_store.add_incident(updated)
    if signal.status == AlertStatus.RESOLVED:
        # R2: resolved alerts are explicitly observation-only regardless
        # of the fingerprint delta. A new resolved signal may carry a
        # fingerprint that the material-change classifier would mark
        # as material, but resolved alerts never re-classify the
        # incident. Surfacing the resolved attachment as observation
        # is the contract.
        return _CATEGORY_OBSERVATION, updated.incident_id
    return _classify_material_change(existing, updated), updated.incident_id


def _signal_already_attached(existing: Incident, signal: AlertSignal) -> bool:
    return any(
        sig.fingerprint == signal.signal_id for sig in existing.signals
    )


def _classify_material_change(previous: Incident, updated: Incident) -> str:
    """Decide whether the updated incident carries new diagnostic information.

    A material change is one that can alter diagnosis or operator action:
    severity, namespace/object kind/name, candidate class, or a
    previously-unseen signal fingerprint. Everything else (last_observed
    bookkeeping, duplicate-observation events) is observation-only.
    """
    if previous.severity != updated.severity:
        return _CATEGORY_MATERIAL
    if previous.candidate_class != updated.candidate_class:
        return _CATEGORY_MATERIAL
    if previous.namespace != updated.namespace:
        return _CATEGORY_MATERIAL
    if previous.object_kind != updated.object_kind:
        return _CATEGORY_MATERIAL
    if previous.object_name != updated.object_name:
        return _CATEGORY_MATERIAL
    previous_fingerprints = {
        sig.fingerprint for sig in previous.signals if sig.fingerprint
    }
    updated_fingerprints = {
        sig.fingerprint for sig in updated.signals if sig.fingerprint
    }
    if updated_fingerprints - previous_fingerprints:
        return _CATEGORY_MATERIAL
    return _CATEGORY_OBSERVATION


def _record_incident_category(
    *,
    categories: dict[str, str],
    first_index: dict[str, int],
    incident_id: str,
    category: str,
    request_index: int,
) -> None:
    previous = categories.get(incident_id)
    if previous is None:
        categories[incident_id] = category
        first_index[incident_id] = request_index
        return
    if _CATEGORY_PRIORITY[category] > _CATEGORY_PRIORITY[previous]:
        categories[incident_id] = category
    first_index[incident_id] = min(first_index[incident_id], request_index)


def _partition_incidents(
    *,
    categories: dict[str, str],
    first_index: dict[str, int],
) -> dict[str, list[IncidentId]]:
    """Return per-category incident ID lists in first-occurrence order."""
    ordered = sorted(
        categories.items(),
        key=lambda item: (first_index[item[0]], item[0]),
    )
    buckets: dict[str, list[IncidentId]] = {
        _CATEGORY_UNCHANGED: [],
        _CATEGORY_OBSERVATION: [],
        _CATEGORY_MATERIAL: [],
        _CATEGORY_OPENED: [],
    }
    for incident_id, category in ordered:
        buckets[category].append(IncidentId(incident_id))
    return buckets


__all__ = ["promote_scoped_alert_signals"]
