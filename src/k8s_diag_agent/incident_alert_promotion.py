"""Alert signal to incident promotion service.

This module promotes persisted alert signals into K9B incidents.

Promotion rules:
- Firing alert signals open or update incidents
- Resolved alert signals attach to existing incidents without auto-resolving
- Classification is deterministic
- Correlation keys are deterministic
- No auto-resolution of incidents
- No new incidents from resolved alerts alone

Suggested by: ACT-K9B-ALERT-INCIDENT-PROMOTION01
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .collect.incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from .collect.incident_lifecycle import (
    Incident,
    IncidentEvent,
    IncidentEventActor,
    IncidentEventType,
    IncidentSignal,
    IncidentStatus,
    make_event_id,
)
from .collect.incident_store import IncidentStore
from .incident_alert_classifier import (
    AlertIncidentClass,
    EntityKind,
    classify_alert_signal,
)
from .incident_alert_correlation import build_alert_incident_correlation_key
from .incident_alert_signal import AlertSignal, AlertStatus
from .incident_alert_signal_reader import scan_alert_signal_artifacts

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Promotion Result Model
# =============================================================================


@dataclass(frozen=True)
class AlertIncidentPromotionResult:
    """Result of an alert-to-incident promotion scan.

    In addition to the aggregate counts, this result exposes per-candidate
    records (``opened_incident_ids`` / ``updated_incident_ids`` /
    ``promotion_records``) so that downstream callers (notably automatic
    diagnosis) can consume canonical ``incident_id`` values directly rather
    than synthesizing IDs from namespace, object kind, object name,
    candidate class, or alert labels.

    Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01
    """

    scanned_signal_count: int = 0
    firing_signal_count: int = 0
    resolved_signal_count: int = 0
    opened_incident_count: int = 0
    updated_incident_count: int = 0
    skipped_duplicate_count: int = 0
    skipped_resolved_without_open_incident_count: int = 0
    malformed_artifact_count: int = 0
    error_count: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)
    # Canonical identity propagation. ``opened_incident_ids`` and
    # ``updated_incident_ids`` are derived from ``promotion_records`` and
    # are kept as separate convenience lists for log/response consumers.
    opened_incident_ids: tuple[str, ...] = field(default_factory=tuple)
    updated_incident_ids: tuple[str, ...] = field(default_factory=tuple)
    promotion_records: tuple[dict[str, str | None], ...] = field(default_factory=tuple)
    unique_candidate_count: int = 0
    promotion_scan_scope: str = "alert_signals_run_dir"

    def to_dict(self) -> dict[str, object]:
        """Convert to dict for serialization."""
        return {
            "scanned_signal_count": self.scanned_signal_count,
            "firing_signal_count": self.firing_signal_count,
            "resolved_signal_count": self.resolved_signal_count,
            "opened_incident_count": self.opened_incident_count,
            "updated_incident_count": self.updated_incident_count,
            "skipped_duplicate_count": self.skipped_duplicate_count,
            "skipped_resolved_without_open_incident_count": (
                self.skipped_resolved_without_open_incident_count
            ),
            "malformed_artifact_count": self.malformed_artifact_count,
            "error_count": self.error_count,
            "errors": list(self.errors),
            "opened_incident_ids": list(self.opened_incident_ids),
            "updated_incident_ids": list(self.updated_incident_ids),
            "promotion_records": [dict(r) for r in self.promotion_records],
            "unique_candidate_count": self.unique_candidate_count,
            "promotion_scan_scope": self.promotion_scan_scope,
        }


# =============================================================================
# Alert Incident Candidate Projection
# =============================================================================


def alert_signal_to_incident_candidate(
    signal: AlertSignal,
    correlation_key: str,
    *,
    signal_fingerprint: str | None = None,
) -> IncidentCandidate:
    """Project an alert signal to an incident candidate.

    Args:
        signal: The alert signal
        correlation_key: The correlation key for this signal

    Returns:
        IncidentCandidate suitable for promotion
    """
    classification = classify_alert_signal(signal)

    # Map alert class to candidate class
    candidate_class = _map_alert_class_to_candidate_class(classification.class_)

    # Map alert severity to candidate severity
    severity = _map_severity(signal.severity)

    # Determine object kind
    object_kind = _map_entity_kind_to_object_kind(classification.entity_kind)

    # Build signals
    signals = [
        CandidateSignal(
            source="alert",
            reason=signal.alertname,
            message=_build_alert_message(signal),
            fingerprint=signal_fingerprint or signal.signal_id,
        )
    ]

    return IncidentCandidate(
        candidate_id=correlation_key,
        namespace=classification.namespace,
        object_kind=object_kind,
        object_name=classification.entity_name,
        candidate_class=candidate_class,
        severity=severity,
        signals=tuple(signals),
        evidence_needed=("alert_evidence",),
        raw_object_kind=None,
    )


def _map_alert_class_to_candidate_class(alert_class: AlertIncidentClass) -> CandidateClass:
    """Map alert incident class to candidate class."""
    mapping = {
        AlertIncidentClass.CRASH_LOOP: CandidateClass.CRASH_LOOP,
        AlertIncidentClass.IMAGE_PULL_ERROR: CandidateClass.IMAGE_PULL_ERROR,
        AlertIncidentClass.PENDING_POD: CandidateClass.PENDING_POD,
        AlertIncidentClass.DEPLOYMENT_UNAVAILABLE: CandidateClass.DEPLOYMENT_UNAVAILABLE,
        AlertIncidentClass.NODE_UNAVAILABLE: CandidateClass.UNKNOWN,
        AlertIncidentClass.TARGET_UNREACHABLE: CandidateClass.UNKNOWN,
        AlertIncidentClass.EXTERNAL_ALERT: CandidateClass.UNKNOWN,
    }
    return mapping.get(alert_class, CandidateClass.UNKNOWN)


def _map_severity(severity: str | None) -> Severity:
    """Map alert severity to candidate severity."""
    if severity is None:
        return Severity.WARNING

    sev = severity.lower()
    if sev in ("critical", "error", "err"):
        return Severity.ERROR
    return Severity.WARNING


def _map_entity_kind_to_object_kind(entity_kind: EntityKind) -> ObjectKind:
    """Map alert entity kind to candidate object kind."""
    mapping = {
        EntityKind.POD: ObjectKind.POD,
        EntityKind.DEPLOYMENT: ObjectKind.DEPLOYMENT,
        EntityKind.NODE: ObjectKind.NODE,
        EntityKind.JOB: ObjectKind.UNKNOWN,
        EntityKind.SERVICE: ObjectKind.UNKNOWN,
        EntityKind.CONTAINER: ObjectKind.POD,
        EntityKind.INSTANCE: ObjectKind.UNKNOWN,
        EntityKind.ALERT: ObjectKind.UNKNOWN,
    }
    return mapping.get(entity_kind, ObjectKind.UNKNOWN)


def _build_alert_message(signal: AlertSignal) -> str:
    """Build a message from alert signal."""
    parts = [f"Alert: {signal.alertname}"]
    if signal.severity:
        parts.append(f"Severity: {signal.severity}")
    if signal.status:
        parts.append(f"Status: {signal.status.value}")
    return " | ".join(parts)


# =============================================================================
# Incident Promotion Functions
# =============================================================================


def open_incident_from_alert_signal(
    signal: AlertSignal,
    candidate: IncidentCandidate,
    correlation_key: str,
    observed_at: datetime,
) -> Incident:
    """Open a new incident from an alert signal.

    Args:
        signal: The alert signal
        candidate: The incident candidate
        correlation_key: The correlation key
        observed_at: When the signal was observed

    Returns:
        New Incident in OPEN state
    """
    incident_id = correlation_key

    # Create incident signal
    incident_signals = [
        IncidentSignal(
            source="alert",
            reason=signal.alertname,
            message=_build_alert_message(signal),
            captured_at=observed_at,
            fingerprint=signal.signal_id,
        )
    ]

    # Create OPENED event
    opened_event = IncidentEvent(
        event_id=make_event_id(incident_id, "alert_opened", observed_at),
        incident_id=incident_id,
        event_type=IncidentEventType.OPENED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=observed_at,
        message=f"Incident opened from alert signal: {signal.alertname}",
        data={
            "alert_signal_id": signal.signal_id,
            "correlation_key": correlation_key,
            "severity": signal.severity or "unknown",
        },
    )

    return Incident(
        incident_id=incident_id,
        source_candidate_id=candidate.candidate_id,
        namespace=candidate.namespace,
        object_kind=candidate.object_kind.value,
        object_name=candidate.object_name,
        raw_object_kind=candidate.raw_object_kind,
        candidate_class=candidate.candidate_class.value,
        severity=candidate.severity.value,
        status=IncidentStatus.OPEN,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        signals=incident_signals,
        evidence_needed=list(candidate.evidence_needed),
        evidence_links=[],
        signal_count=len(incident_signals),
        events=[opened_event],
    )


def attach_alert_signal_to_incident(
    incident: Incident,
    signal: AlertSignal,
    correlation_key: str,
    observed_at: datetime,
) -> Incident:
    """Attach an alert signal to an existing incident.

    This function does NOT change incident status or resolve the incident.

    Args:
        incident: The existing incident
        signal: The alert signal to attach
        correlation_key: The correlation key
        observed_at: When the signal was observed

    Returns:
        Updated Incident with attached signal
    """
    # Check for duplicate attachment
    if any(s.fingerprint == signal.signal_id for s in incident.signals):
        return incident

    # Create new signal
    new_signal = IncidentSignal(
        source="alert",
        reason=signal.alertname,
        message=_build_alert_message(signal),
        captured_at=observed_at,
        fingerprint=signal.signal_id,
    )

    # Create timeline event
    event_data = {
        "alert_signal_id": signal.signal_id,
        "correlation_key": correlation_key,
        "status": signal.status.value,
    }
    signal_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "alert_signal_attached", observed_at, event_data),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.SIGNAL_MERGED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=observed_at,
        message=f"Alert signal attached: {signal.alertname} ({signal.status.value})",
        data=event_data,
    )

    return replace(
        incident,
        last_observed_at=observed_at,
        signals=incident.signals + [new_signal],
        signal_count=incident.signal_count + 1,
        events=incident.events + [signal_event],
    )


# =============================================================================
# Promotion Service
# =============================================================================


# Track per-incident promotion outcomes so callers (notably the auto-diagnosis
# loop) can consume canonical ``incident_id`` values directly. The tuples are
# populated alongside the aggregate counts in the helpers below.
_FIRING_OUTCOME_OPENED = "opened"
_FIRING_OUTCOME_UPDATED = "updated"
_FIRING_OUTCOME_DUPLICATE = "skipped_duplicate"
_FIRING_OUTCOME_ERROR = "error"


def promote_alert_signals_to_incidents(
    *,
    incident_store: IncidentStore,
    runs_dir: Path,
    now: datetime | None = None,
) -> AlertIncidentPromotionResult:
    """Promote alert signals to incidents.

    This service:
    - Scans persisted alert signal artifacts
    - Classifies each signal
    - Builds correlation keys
    - Firing alerts: open new incident or update existing
    - Resolved alerts: attach to existing incident (no auto-resolve)

    Args:
        incident_store: The incident store to write to
        runs_dir: The runs directory containing alert signal artifacts
        now: Current timestamp (defaults to now)

    Returns:
        AlertIncidentPromotionResult with promotion statistics. The result
        exposes per-candidate ``promotion_records`` and canonical
        ``opened_incident_ids`` / ``updated_incident_ids`` for callers to
        consume directly without re-deriving incident IDs.
    """
    if now is None:
        now = datetime.now(UTC)

    errors: list[str] = []
    scanned = 0
    firing_count = 0
    resolved_count = 0
    opened_count = 0
    updated_count = 0
    skipped_dup = 0
    skipped_resolved = 0
    malformed_count = 0
    unique_keys: set[str] = set()
    firing_outcomes: list[tuple[str, str | None, str]] = []

    # Scan alert signal artifacts
    artifacts = scan_alert_signal_artifacts(runs_dir)
    scan_scope = (
        f"alert_signal_artifacts:dir={runs_dir}"
        if runs_dir is not None
        else "alert_signal_artifacts:no_dir"
    )

    for artifact in artifacts:
        try:
            if artifact.signal is None:
                malformed_count += 1
                continue

            signal = artifact.signal
            scanned += 1

            # Classify the signal
            classification = classify_alert_signal(signal)

            # Build correlation key
            correlation_key = build_alert_incident_correlation_key(signal, classification)
            unique_keys.add(correlation_key)

            if signal.status == AlertStatus.FIRING:
                firing_count += 1
                outcome_record = _handle_firing_alert_with_outcome(
                    incident_store=incident_store,
                    signal=signal,
                    correlation_key=correlation_key,
                    observed_at=signal.received_at,
                    errors=errors,
                )
                if outcome_record is not None:
                    firing_outcomes.append(outcome_record)
                    outcome = outcome_record[2]
                    if outcome == _FIRING_OUTCOME_OPENED:
                        opened_count += 1
                    elif outcome == _FIRING_OUTCOME_UPDATED:
                        updated_count += 1
                    elif outcome == _FIRING_OUTCOME_DUPLICATE:
                        skipped_dup += 1
            elif signal.status == AlertStatus.RESOLVED:
                resolved_count += 1
                skipped_resolved = _handle_resolved_alert(
                    incident_store=incident_store,
                    signal=signal,
                    correlation_key=correlation_key,
                    observed_at=signal.received_at,
                    errors=errors,
                    skipped_resolved=skipped_resolved,
                )

        except Exception as e:
            error_msg = f"Error processing artifact {artifact.identity}: {e}"
            logger.exception(error_msg)
            errors.append(error_msg)
            firing_outcomes.append((
                getattr(artifact, "identity", "<unknown>"),
                None,
                _FIRING_OUTCOME_ERROR,
            ))

    opened_ids: list[str] = []
    updated_ids: list[str] = []
    promotion_records: list[dict[str, str | None]] = []
    for source_candidate_id, canonical_incident_id, outcome in firing_outcomes:
        promotion_records.append({
            "source_candidate_id": source_candidate_id,
            "canonical_incident_id": canonical_incident_id,
            "promotion_outcome": outcome,
        })
        if outcome == _FIRING_OUTCOME_OPENED and canonical_incident_id is not None:
            opened_ids.append(canonical_incident_id)
        elif outcome == _FIRING_OUTCOME_UPDATED and canonical_incident_id is not None:
            updated_ids.append(canonical_incident_id)

    # Log promotion scan scope and unique candidate count for observability.
    # This is observed by both webhook and scheduler health-loop emission paths.
    logger.info(
        "Alert signal promotion scan complete",
        extra={
            "event": "alert-signal-promotion-scan",
            "promotion_scan_scope": scan_scope,
            "unique_candidate_count": len(unique_keys),
            "scanned_signal_count": scanned,
            "opened_incident_count": opened_count,
            "updated_incident_count": updated_count,
            "skipped_duplicate_count": skipped_dup,
            "promoted_canonical_incident_count": len(opened_ids) + len(updated_ids),
        },
    )

    return AlertIncidentPromotionResult(
        scanned_signal_count=scanned,
        firing_signal_count=firing_count,
        resolved_signal_count=resolved_count,
        opened_incident_count=opened_count,
        updated_incident_count=updated_count,
        skipped_duplicate_count=skipped_dup,
        skipped_resolved_without_open_incident_count=skipped_resolved,
        malformed_artifact_count=malformed_count,
        error_count=len(errors),
        errors=tuple(errors),
        opened_incident_ids=tuple(opened_ids),
        updated_incident_ids=tuple(updated_ids),
        promotion_records=tuple(promotion_records),
        unique_candidate_count=len(unique_keys),
        promotion_scan_scope=scan_scope,
    )


def _handle_firing_alert_with_outcome(
    incident_store: IncidentStore,
    signal: AlertSignal,
    correlation_key: str,
    observed_at: datetime,
    errors: list[str],
) -> tuple[str, str | None, str] | None:
    """Open or update incident, returning the per-candidate promotion outcome."""
    # Check if incident already exists
    existing = incident_store.get_incident(correlation_key)

    if existing is None:
        # Open new incident
        candidate = alert_signal_to_incident_candidate(signal, correlation_key)
        new_incident = open_incident_from_alert_signal(
            signal=signal,
            candidate=candidate,
            correlation_key=correlation_key,
            observed_at=observed_at,
        )
        incident_store.add_incident(new_incident)
        return (correlation_key, new_incident.incident_id, _FIRING_OUTCOME_OPENED)

    if any(s.fingerprint == signal.signal_id for s in existing.signals):
        return (correlation_key, existing.incident_id, _FIRING_OUTCOME_DUPLICATE)

    updated = attach_alert_signal_to_incident(
        incident=existing,
        signal=signal,
        correlation_key=correlation_key,
        observed_at=observed_at,
    )
    incident_store.add_incident(updated)
    return (correlation_key, updated.incident_id, _FIRING_OUTCOME_UPDATED)


def _handle_firing_alert(
    incident_store: IncidentStore,
    signal: AlertSignal,
    correlation_key: str,
    observed_at: datetime,
    errors: list[str],
    opened_count: int,
    updated_count: int,
    skipped_dup: int,
) -> tuple[int, int, int]:
    """Handle a firing alert - open or update incident. Returns (opened, updated, skipped_dup)."""
    outcome = _handle_firing_alert_with_outcome(
        incident_store=incident_store,
        signal=signal,
        correlation_key=correlation_key,
        observed_at=observed_at,
        errors=errors,
    )
    if outcome is None:
        return opened_count, updated_count, skipped_dup
    if outcome[2] == _FIRING_OUTCOME_OPENED:
        opened_count += 1
    elif outcome[2] == _FIRING_OUTCOME_UPDATED:
        updated_count += 1
    elif outcome[2] == _FIRING_OUTCOME_DUPLICATE:
        skipped_dup += 1
    return opened_count, updated_count, skipped_dup


def _handle_resolved_alert(
    incident_store: IncidentStore,
    signal: AlertSignal,
    correlation_key: str,
    observed_at: datetime,
    errors: list[str],
    skipped_resolved: int,
) -> int:
    """Handle a resolved alert - attach to existing incident only. Returns updated skipped_resolved."""
    # Find existing incident by correlation key
    existing = incident_store.get_incident(correlation_key)

    if existing is None:
        # No matching incident - skip
        skipped_resolved += 1
        return skipped_resolved

    # Check if this is a duplicate signal
    if any(s.fingerprint == signal.signal_id for s in existing.signals):
        return skipped_resolved

    # Attach resolved alert to existing incident
    updated = attach_alert_signal_to_incident(
        incident=existing,
        signal=signal,
        correlation_key=correlation_key,
        observed_at=observed_at,
    )
    incident_store.add_incident(updated)
    return skipped_resolved
