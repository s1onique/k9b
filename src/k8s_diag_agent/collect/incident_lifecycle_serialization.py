"""Serialization helpers for incident lifecycle models.

This module contains pure serialization/deserialization functions:
- to_dict methods for Incident dataclass
- from_dict classmethod for Incident reconstruction

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO autonomous root-cause claims
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse a datetime string to datetime object."""
    if value is None:
        return None
    return datetime.fromisoformat(value)


def incident_signal_to_dict(signal: Any) -> dict[str, Any]:
    """Serialize an IncidentSignal to dict."""
    result: dict[str, Any] = signal.to_dict()
    return result


def incident_event_to_dict(event: Any) -> dict[str, Any]:
    """Serialize an IncidentEvent to dict."""
    result: dict[str, Any] = event.to_dict()
    return result


def evidence_link_to_dict(link: Any) -> dict[str, Any]:
    """Serialize an EvidenceLink to dict."""
    result: dict[str, Any] = link.to_dict()
    return result


def review_packet_state_to_dict(review_packet: Any) -> dict[str, Any]:
    """Serialize a ReviewPacketState to dict."""
    result: dict[str, Any] = review_packet.to_dict()
    return result


def incident_to_dict(incident: Any) -> dict[str, Any]:
    """Serialize an Incident to dict for JSON storage."""

    return {
        "incident_id": incident.incident_id,
        "source_candidate_id": incident.source_candidate_id,
        "namespace": incident.namespace,
        "object_kind": incident.object_kind,
        "object_name": incident.object_name,
        "raw_object_kind": incident.raw_object_kind,
        "class": incident.candidate_class,
        "severity": incident.severity,
        "status": incident.status.value if hasattr(incident.status, 'value') else incident.status,
        "first_observed_at": incident.first_observed_at.isoformat(),
        "last_observed_at": incident.last_observed_at.isoformat(),
        "signals": [incident_signal_to_dict(s) for s in incident.signals],
        "evidence_needed": list(incident.evidence_needed),
        "evidence_links": [evidence_link_to_dict(e) for e in incident.evidence_links],
        "latest_snapshot_bundle_id": incident.latest_snapshot_bundle_id,
        "review_packet": review_packet_state_to_dict(incident.review_packet),
        "signal_count": incident.signal_count,
        "evidence_count": incident.evidence_count,
        "events": [incident_event_to_dict(e) for e in incident.events],
        "suppressed_reason": incident.suppressed_reason,
        "duplicate_of": incident.duplicate_of,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "resolution_notes": incident.resolution_notes,
    }


def incident_from_dict(data: dict[str, Any]) -> Any:
    """Reconstruct an Incident from a dict (e.g., loaded from JSON).

    Args:
        data: Dict representation of an incident.

    Returns:
        Reconstructed Incident instance.

    Raises:
        KeyError: If required fields are missing.
        ValueError: If field values are invalid.
    """
    # Import here to avoid circular imports
    from .incident_events import IncidentEvent, IncidentEventActor, IncidentEventType
    from .incident_evidence import EvidenceLink, EvidenceRole
    from .incident_lifecycle_types import IncidentStatus
    from .incident_review_packet_state import ReviewPacketState, ReviewPacketStatus

    # Parse datetime fields
    def _parse_dt(value: str | None) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value)

    # Reconstruct signals
    signals = []
    for s in data.get("signals", []):
        captured_at = _parse_dt(s.get("captured_at"))
        if captured_at is None:
            captured_at = datetime.now(UTC)
        signals.append(
            _make_incident_signal(
                source=s["source"],
                reason=s["reason"],
                message=s["message"],
                captured_at=captured_at,
                run_id=s.get("run_id"),
                detector_id=s.get("detector_id"),
                finding_id=s.get("finding_id"),
                fingerprint=s.get("fingerprint"),
            )
        )

    # Reconstruct evidence links
    evidence_links = []
    for e in data.get("evidence_links", []):
        # Convert role string to EvidenceRole enum
        role_value = e["role"]
        if isinstance(role_value, str):
            role = EvidenceRole(role_value)
        else:
            role = role_value
        # attached_at is optional, use current time if missing
        attached_at = _parse_dt(e.get("attached_at"))
        if attached_at is None:
            attached_at = datetime.now(UTC)
        evidence_links.append(EvidenceLink(
            incident_id=e["incident_id"],
            artifact_id=e["artifact_id"],
            role=role,
            attached_at=attached_at,
        ))

    # Reconstruct events
    events = []
    for e in data.get("events", []):
        occurred_at = _parse_dt(e["occurred_at"])
        if occurred_at is None:
            raise ValueError(f"Event {e.get('event_id', 'unknown')} missing required occurred_at")

        # Handle event_type - may be string or enum
        event_type = e["event_type"]
        if isinstance(event_type, str):
            event_type = IncidentEventType(event_type)

        # Handle actor - may be string or enum
        actor = e["actor"]
        if isinstance(actor, str):
            actor = IncidentEventActor(actor)

        events.append(IncidentEvent(
            event_id=e["event_id"],
            incident_id=e["incident_id"],
            event_type=event_type,
            actor=actor,
            occurred_at=occurred_at,
            message=e["message"],
            actor_id=e.get("actor_id"),
            data=e.get("data"),
        ))

    # Reconstruct review packet state
    review_packet_data = data.get("review_packet", {})
    # Convert status string to ReviewPacketStatus enum
    rp_status_value = review_packet_data.get("status", "not_generated")
    if isinstance(rp_status_value, str):
        rp_status = ReviewPacketStatus(rp_status_value)
    else:
        rp_status = rp_status_value
    review_packet = ReviewPacketState(
        status=rp_status,
        id=review_packet_data.get("id"),
        generated_at=_parse_dt(review_packet_data.get("generated_at")),
        error_message=review_packet_data.get("error_message"),
    )

    # Convert status string to IncidentStatus enum
    status_value = data["status"]
    if isinstance(status_value, str):
        status = IncidentStatus(status_value)
    else:
        status = status_value

    # Parse required datetime fields - fail if missing
    first_observed_at = _parse_dt(data["first_observed_at"])
    if first_observed_at is None:
        raise ValueError("Incident missing required first_observed_at field")

    last_observed_at = _parse_dt(data["last_observed_at"])
    if last_observed_at is None:
        raise ValueError("Incident missing required last_observed_at field")

    # Import Incident here to construct the instance
    from .incident_lifecycle import Incident

    return Incident(
        incident_id=data["incident_id"],
        source_candidate_id=data["source_candidate_id"],
        namespace=data["namespace"],
        object_kind=data["object_kind"],
        object_name=data["object_name"],
        raw_object_kind=data.get("raw_object_kind"),
        candidate_class=data["class"],
        severity=data["severity"],
        status=status,
        first_observed_at=first_observed_at,
        last_observed_at=last_observed_at,
        signals=signals,
        evidence_needed=list(data.get("evidence_needed", [])),
        evidence_links=evidence_links,
        latest_snapshot_bundle_id=data.get("latest_snapshot_bundle_id"),
        review_packet=review_packet,
        signal_count=data.get("signal_count", len(signals)),
        evidence_count=data.get("evidence_count", len(evidence_links)),
        events=events,
        suppressed_reason=data.get("suppressed_reason"),
        duplicate_of=data.get("duplicate_of"),
        resolved_at=_parse_dt(data.get("resolved_at")),
        resolution_notes=data.get("resolution_notes"),
    )


def _make_incident_signal(
    source: str,
    reason: str,
    message: str,
    captured_at: datetime,
    run_id: str | None = None,
    detector_id: str | None = None,
    finding_id: str | None = None,
    fingerprint: str | None = None,
) -> Any:
    """Create an IncidentSignal instance (imported lazily to avoid circular deps)."""
    from .incident_lifecycle_types import IncidentSignal
    return IncidentSignal(
        source=source,
        reason=reason,
        message=message,
        captured_at=captured_at,
        run_id=run_id,
        detector_id=detector_id,
        finding_id=finding_id,
        fingerprint=fingerprint,
    )


__all__ = [
    "incident_from_dict",
    "incident_to_dict",
    "incident_signal_to_dict",
    "incident_event_to_dict",
    "evidence_link_to_dict",
    "review_packet_state_to_dict",
]
