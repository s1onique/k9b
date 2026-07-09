"""SQLite lifecycle methods for incident store.

This module provides the lifecycle transition methods for SQLite-backed incidents:
- Promotion and addition methods
- Evidence attachment
- Diagnosis loop tracking

These methods use SQLiteWriteContext to encapsulate write authority:
- Event append goes through ctx.append_event()
- Cache access goes through ctx.get_cached_incident() and ctx.put_cached_incident()

The store provides _write_context() context manager for thread-safe writes.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .incident_bundle_promotion import (
    merge_candidate_into_incident_with_bundle,
    open_incident_from_candidate_with_bundle,
)
from .incident_candidates import IncidentCandidate
from .incident_evidence import EvidenceLink, EvidenceRole
from .incident_lifecycle import (
    Incident,
    incident_id_from_candidate,
    merge_candidate_into_incident,
    open_incident_from_candidate,
)
from .incident_store_sqlite_context import SQLiteWriteContext
from .incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)

if TYPE_CHECKING:

    from .incident_store_sqlite import SQLiteIncidentStore

_logger = logging.getLogger(__name__)


def promote_candidates_impl(
    store: SQLiteIncidentStore,
    candidates: list[IncidentCandidate] | tuple[IncidentCandidate, ...],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> tuple[Incident, ...]:
    """Promote candidates to incidents with event sourcing.

    This implementation uses the store's _write_context() to ensure
    thread-safe writes. The write context owns:
    - Event append authority
    - Cache read/write authority
    - Snapshot helper access
    """
    with store._write_context() as ctx:
        updated_incidents: dict[str, Incident] = {}

        for candidate in candidates:
            incident_id = incident_id_from_candidate(candidate)

            if ctx.has_incident(incident_id):
                # Merge into existing
                existing = ctx.get_cached_incident(incident_id)
                if existing is None:
                    # Should not happen if has_incident is True, but be safe
                    continue

                if snapshot_bundle_id is not None:
                    updated = merge_candidate_into_incident_with_bundle(
                        existing, candidate, observed_at, snapshot_bundle_id
                    )
                else:
                    updated = merge_candidate_into_incident(existing, candidate, observed_at)

                # Create event for signal merge
                payload = {
                    "signal_count": len(candidate.signals),
                    "candidate_id": candidate.candidate_id,
                    "last_observed_at": observed_at.isoformat(),
                    "signals": [s.to_dict() for s in updated.signals],
                }

                if snapshot_bundle_id is not None:
                    payload["bundle_id"] = snapshot_bundle_id
                    payload["status"] = updated.status.value
                    payload["evidence_links"] = [e.to_dict() for e in updated.evidence_links]
                    ctx.append_event(
                        incident_id=incident_id,
                        event_type=IncidentEventType.COLLECTING_EVIDENCE_STARTED,
                        actor=IncidentEventActor.SYSTEM,
                        payload=payload,
                        occurred_at=observed_at,
                    )
                else:
                    ctx.append_event(
                        incident_id=incident_id,
                        event_type=IncidentEventType.SIGNAL_OBSERVED,
                        actor=IncidentEventActor.SYSTEM,
                        payload=payload,
                        occurred_at=observed_at,
                    )

                ctx.put_cached_incident(updated)
                updated_incidents[incident_id] = updated
            else:
                # Open new incident
                if snapshot_bundle_id is not None:
                    new_incident = open_incident_from_candidate_with_bundle(
                        candidate, observed_at, snapshot_bundle_id
                    )
                else:
                    new_incident = open_incident_from_candidate(candidate, observed_at)

                # Create OPENED event (ALWAYS first event for correct projection)
                opened_payload = {
                    "source_candidate_id": candidate.candidate_id,
                    "namespace": candidate.namespace,
                    "object_kind": candidate.object_kind.value,
                    "object_name": candidate.object_name,
                    "raw_object_kind": candidate.raw_object_kind,
                    "candidate_class": candidate.candidate_class.value,
                    "severity": candidate.severity.value,
                    "first_observed_at": observed_at.isoformat(),
                    "last_observed_at": observed_at.isoformat(),
                    "signals": [s.to_dict() for s in new_incident.signals],
                    "evidence_needed": list(new_incident.evidence_needed),
                    "signal_count": new_incident.signal_count,
                    "evidence_count": new_incident.evidence_count,
                    "status": "open",  # Start with OPEN status
                }

                ctx.append_event(
                    incident_id=incident_id,
                    event_type=IncidentEventType.OPENED,
                    actor=IncidentEventActor.SYSTEM,
                    payload=opened_payload,
                    occurred_at=observed_at,
                )

                # If snapshot bundle provided, also emit COLLECTING_EVIDENCE_STARTED
                # NOTE: Each ctx.append_event() call starts its own BEGIN IMMEDIATE transaction
                # and commits independently. These are two durable events, not one atomic op.
                if snapshot_bundle_id is not None:
                    collecting_payload = {
                        "bundle_id": snapshot_bundle_id,
                        "status": "collecting_evidence",
                        "last_observed_at": observed_at.isoformat(),
                        "evidence_links": [e.to_dict() for e in new_incident.evidence_links],
                        "evidence_count": new_incident.evidence_count,
                        "latest_snapshot_bundle_id": snapshot_bundle_id,
                    }

                    ctx.append_event(
                        incident_id=incident_id,
                        event_type=IncidentEventType.COLLECTING_EVIDENCE_STARTED,
                        actor=IncidentEventActor.SYSTEM,
                        payload=collecting_payload,
                        occurred_at=observed_at,
                    )

                ctx.put_cached_incident(new_incident)
                updated_incidents[incident_id] = new_incident

        all_updated = [ctx.snapshot_incident(i) for i in updated_incidents.values()]
        return tuple(sorted(all_updated, key=lambda i: i.incident_id))


def add_incident_impl(
    store: SQLiteIncidentStore,
    incident: Incident,
) -> None:
    """Add an incident by appending an OPENED event.

    Thread safety: Uses store._write_context() for thread-safe writes.
    """
    with store._write_context() as ctx:
        if ctx.has_incident(incident.incident_id):
            _logger.warning(
                "Incident %s already exists, skipping add",
                incident.incident_id,
            )
            return

        payload = {
            "source_candidate_id": incident.source_candidate_id,
            "namespace": incident.namespace,
            "object_kind": incident.object_kind,
            "object_name": incident.object_name,
            "raw_object_kind": incident.raw_object_kind,
            "candidate_class": incident.candidate_class,
            "severity": incident.severity,
            "first_observed_at": incident.first_observed_at.isoformat(),
            "last_observed_at": incident.last_observed_at.isoformat(),
            "signals": [s.to_dict() for s in incident.signals],
            "evidence_needed": list(incident.evidence_needed),
            "signal_count": incident.signal_count,
            "evidence_count": incident.evidence_count,
        }

        ctx.append_event(
            incident_id=incident.incident_id,
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            payload=payload,
            occurred_at=incident.first_observed_at,
        )

        ctx.put_cached_incident(incident)


# =============================================================================
# Evidence Methods
# =============================================================================


def attach_evidence_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    artifact_id: str,
    role: EvidenceRole,
) -> Incident | None:
    """Attach evidence to incident.

    Thread safety: Uses store._write_context() for thread-safe writes.
    """
    with store._write_context() as ctx:
        incident = ctx.get_cached_incident(incident_id)
        if incident is None:
            return None

        new_link = EvidenceLink(
            incident_id=incident_id,
            artifact_id=artifact_id,
            role=role,
            attached_at=datetime.now(UTC),
        )
        evidence_links = list(incident.evidence_links) + [new_link]

        payload = {
            "artifact_id": artifact_id,
            "role": role.value,
            "evidence_links": [e.to_dict() for e in evidence_links],
            "evidence_count": len(evidence_links),
        }

        ctx.append_event(
            incident_id=incident_id,
            event_type=IncidentEventType.EVIDENCE_ATTACHED,
            actor=IncidentEventActor.SYSTEM,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )

        updated = incident.__class__(
            **{
                **incident.__dict__,
                "evidence_links": evidence_links,
                "evidence_count": len(evidence_links),
            }
        )
        ctx.put_cached_incident(updated)
        return ctx.snapshot_incident(updated)


# =============================================================================
# Diagnosis Loop Methods
# =============================================================================


def mark_diagnosis_loop_started_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
) -> Incident | None:
    """Mark diagnosis loop started.

    Thread safety: Uses store._write_context() for thread-safe writes.
    """
    with store._write_context() as ctx:
        incident = ctx.get_cached_incident(incident_id)
        if incident is None:
            return None

        payload = {
            "run_id": run_id,
            "collector_run_id": collector_run_id,
        }

        ctx.append_event(
            incident_id=incident_id,
            event_type=IncidentEventType.DIAGNOSIS_LOOP_STARTED,
            actor=IncidentEventActor.SYSTEM,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )

        return ctx.snapshot_incident(incident)


def mark_diagnosis_loop_completed_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
    review_packet_name: str | None = None,
    checks_requested: int = 0,
    checks_run: int = 0,
    checks_rejected: int = 0,
    decision: str | None = None,
) -> Incident | None:
    """Mark diagnosis loop completed.

    Thread safety: Uses store._write_context() for thread-safe writes.
    """
    with store._write_context() as ctx:
        incident = ctx.get_cached_incident(incident_id)
        if incident is None:
            return None

        payload = {
            "run_id": run_id,
            "collector_run_id": collector_run_id,
            "review_packet_name": review_packet_name,
            "checks_requested": checks_requested,
            "checks_run": checks_run,
            "checks_rejected": checks_rejected,
            "decision": decision,
        }

        ctx.append_event(
            incident_id=incident_id,
            event_type=IncidentEventType.DIAGNOSIS_LOOP_COMPLETED,
            actor=IncidentEventActor.SYSTEM,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )

        return ctx.snapshot_incident(incident)


def mark_diagnosis_loop_failed_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    run_id: str | None = None,
    collector_run_id: str | None = None,
    unavailable_reason: str | None = None,
) -> Incident | None:
    """Mark diagnosis loop failed.

    Thread safety: Uses store._write_context() for thread-safe writes.
    """
    with store._write_context() as ctx:
        incident = ctx.get_cached_incident(incident_id)
        if incident is None:
            return None

        payload = {
            "run_id": run_id,
            "collector_run_id": collector_run_id,
            "unavailable_reason": unavailable_reason,
        }

        ctx.append_event(
            incident_id=incident_id,
            event_type=IncidentEventType.DIAGNOSIS_LOOP_FAILED,
            actor=IncidentEventActor.SYSTEM,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )

        return ctx.snapshot_incident(incident)


__all__ = [
    "promote_candidates_impl",
    "add_incident_impl",
    "attach_evidence_impl",
    "mark_diagnosis_loop_started_impl",
    "mark_diagnosis_loop_completed_impl",
    "mark_diagnosis_loop_failed_impl",
]
