"""Incident lifecycle transition functions.

This module provides pure functions for incident state transitions.
All functions are pure with no side effects.

Lifecycle invariant for ready_for_review:
    open -> collecting_evidence -> ready_for_review

Terminal states that cannot transition to ready_for_review:
    - SUPPRESSED
    - DUPLICATE
    - RESOLVED

Also rejects direct transition from OPEN (must go through COLLECTING_EVIDENCE first).

NOTE: Status-transitioning functions (mark_collecting_evidence, mark_ready_for_review,
suppress_incident, mark_duplicate) have been migrated to the typed path via
incident_lifecycle_transitions.py. This module retains non-status-transitioning
functions for bundle promotion and diagnosis loop support.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .incident_events import IncidentEvent, IncidentEventActor, IncidentEventType, make_event_id
from .incident_evidence import (
    ArtifactId,
    EvidenceLink,
    EvidenceRole,
)

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate
    from .incident_lifecycle import Incident  # noqa: F401


def merge_candidate_into_incident(
    incident: Incident,
    candidate: IncidentCandidate,
    observed_at: datetime,
) -> Incident:
    """Merge a new candidate observation into an existing incident."""
    from .incident_lifecycle import IncidentSignal

    new_signals = [
        IncidentSignal(
            source=sig.source,
            reason=sig.reason,
            message=sig.message,
            captured_at=observed_at,
            fingerprint=sig.fingerprint,
        )
        for sig in candidate.signals
    ]

    # Create SIGNAL_MERGED event
    merge_data = {"signal_count": len(new_signals), "candidate_id": candidate.candidate_id}
    merge_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "signal_merged", observed_at, merge_data),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.SIGNAL_MERGED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=observed_at,
        message=f"Merged {len(new_signals)} signal(s) from candidate",
        data=merge_data,
    )

    return replace(
        incident,
        last_observed_at=observed_at,
        signals=incident.signals + new_signals,
        signal_count=incident.signal_count + len(new_signals),
        events=incident.events + [merge_event],
    )


def attach_evidence_artifact(
    incident: Incident,
    artifact_id: ArtifactId,
    role: EvidenceRole,
    occurred_at: datetime | None = None,
) -> Incident:
    """Attach an evidence artifact to the incident (idempotent).

    Args:
        incident: The incident to attach evidence to
        artifact_id: Branded artifact ID
        role: Role of the evidence
        occurred_at: Optional timestamp (defaults to now)

    Returns:
        Updated incident with evidence link and event
    """
    now = occurred_at or datetime.now(UTC)
    artifact_id_str = str(artifact_id)

    # Check idempotency
    if any(link.artifact_id == artifact_id_str and link.role == role for link in incident.evidence_links):
        return incident

    new_link = EvidenceLink(
        incident_id=incident.incident_id,
        artifact_id=artifact_id,
        role=role,
        attached_at=now,
    )

    new_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "evidence_artifact_attached", now),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.EVIDENCE_ARTIFACT_ATTACHED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=now,
        message=f"Evidence artifact attached: {artifact_id_str}",
        data={"artifact_id": artifact_id_str, "role": role.value},
    )

    return replace(
        incident,
        evidence_links=incident.evidence_links + [new_link],
        evidence_count=incident.evidence_count + 1,
        events=incident.events + [new_event],
    )


def mark_diagnosis_loop_started(
    incident: Incident,
    run_id: str,
    collector_run_id: str,
    occurred_at: datetime | None = None,
) -> Incident:
    """Mark that automatic diagnosis loop started for an incident.

    Safe metadata only - no raw packet contents, logs, or stack traces.

    Args:
        incident: The incident to update
        run_id: The run_id for this diagnosis loop pass
        collector_run_id: The batch collector run ID
        occurred_at: Optional timestamp (defaults to now)

    Returns:
        Updated incident with diagnosis_loop_started event appended
    """
    now = occurred_at or datetime.now(UTC)

    event_data = {
        "run_id": run_id,
        "collector_run_id": collector_run_id,
        "read_only": True,
        "review_required_before_any_action": True,
        "no_remediation_attempted": True,
    }

    new_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "diagnosis_loop_started", now, event_data),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.DIAGNOSIS_LOOP_STARTED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=now,
        message="Automatic diagnosis loop started",
        data=event_data,
    )

    return replace(incident, events=incident.events + [new_event])


def mark_diagnosis_loop_completed(
    incident: Incident,
    run_id: str,
    collector_run_id: str,
    review_packet_name: str | None = None,
    checks_requested: int = 0,
    checks_run: int = 0,
    checks_rejected: int = 0,
    decision: str | None = None,
    occurred_at: datetime | None = None,
) -> Incident:
    """Mark that automatic diagnosis loop completed successfully.

    Safe metadata only - no raw packet contents, logs, or stack traces.

    The decision field is captured and stored in the event data to enable
    pass accumulation tracking in the automatic diagnosis loop summary.

    Args:
        incident: The incident to update
        run_id: The run_id for this diagnosis loop pass
        collector_run_id: The batch collector run ID
        review_packet_name: Optional review packet filename
        checks_requested: Number of checks requested
        checks_run: Number of checks actually run
        checks_rejected: Number of checks rejected
        decision: The terminal decision from the policy-enforced loop pass
            (e.g., "stop_no_checks_proposed", "stop_root_cause_found")
        occurred_at: Optional timestamp (defaults to now)

    Returns:
        Updated incident with diagnosis_loop_completed event appended
    """
    now = occurred_at or datetime.now(UTC)

    event_data: dict[str, object] = {
        "run_id": run_id,
        "collector_run_id": collector_run_id,
        "checks_requested": checks_requested,
        "checks_run": checks_run,
        "checks_rejected": checks_rejected,
        "read_only": True,
        "review_required_before_any_action": True,
        "no_remediation_attempted": True,
    }

    if review_packet_name:
        event_data["review_packet_id"] = review_packet_name

    # Store the terminal decision for pass accumulation tracking.
    if decision:
        event_data["decision"] = decision

    new_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "diagnosis_loop_completed", now, event_data),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.DIAGNOSIS_LOOP_COMPLETED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=now,
        message="Automatic diagnosis loop completed",
        data=event_data,
    )

    return replace(incident, events=incident.events + [new_event])


def mark_diagnosis_loop_failed(
    incident: Incident,
    run_id: str | None = None,
    collector_run_id: str | None = None,
    unavailable_reason: str | None = None,
    occurred_at: datetime | None = None,
) -> Incident:
    """Mark that automatic diagnosis loop failed or produced unavailable state.

    Safe metadata only - no raw packet contents, logs, stack traces, or prompts.
    Uses bounded reason codes only for failure information.

    Safe reason codes:
        - unsafe_run_id: Generated run_id failed safety validation
        - case_file_error: Failed to build case file
        - case_file_none: Case file returned None
        - orchestrator_error: Orchestrator raised an exception
        - not_eligible: Incident not eligible for diagnosis loop

    Args:
        incident: The incident to update
        run_id: Optional run_id for the failed pass
        collector_run_id: Optional batch collector run ID
        unavailable_reason: Safe bounded reason code
        occurred_at: Optional timestamp (defaults to now)

    Returns:
        Updated incident with diagnosis_loop_failed event appended
    """
    now = occurred_at or datetime.now(UTC)

    event_data: dict[str, object] = {
        "read_only": True,
        "review_required_before_any_action": True,
        "no_remediation_attempted": True,
    }

    if run_id:
        event_data["run_id"] = run_id
    if collector_run_id:
        event_data["collector_run_id"] = collector_run_id
    if unavailable_reason:
        event_data["unavailable_reason"] = unavailable_reason

    new_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "diagnosis_loop_failed", now, event_data),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.DIAGNOSIS_LOOP_FAILED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=now,
        message="Automatic diagnosis loop failed or unavailable",
        data=event_data,
    )

    return replace(incident, events=incident.events + [new_event])


def can_transition_to_ready_for_review(incident: Incident) -> bool:
    """Check if incident can transition to READY_FOR_REVIEW.

    Lifecycle invariant: open -> collecting_evidence -> ready_for_review

    Terminal states that cannot transition to ready_for_review:
    - SUPPRESSED
    - DUPLICATE
    - RESOLVED

    Also rejects direct transition from OPEN (must go through COLLECTING_EVIDENCE first).

    Args:
        incident: The incident to check

    Returns:
        True if transition is allowed, False otherwise
    """
    from .incident_lifecycle import IncidentStatus

    # Terminal states cannot transition
    if incident.status in (
        IncidentStatus.SUPPRESSED,
        IncidentStatus.DUPLICATE,
        IncidentStatus.RESOLVED,
    ):
        return False

    # OPEN status cannot skip COLLECTING_EVIDENCE
    if incident.status == IncidentStatus.OPEN:
        return False

    # Only COLLECTING_EVIDENCE or INVESTIGATING can transition to READY_FOR_REVIEW
    return incident.status in (
        IncidentStatus.COLLECTING_EVIDENCE,
        IncidentStatus.INVESTIGATING,
    )


__all__ = [
    "merge_candidate_into_incident",
    "attach_evidence_artifact",
    "mark_diagnosis_loop_started",
    "mark_diagnosis_loop_completed",
    "mark_diagnosis_loop_failed",
    "can_transition_to_ready_for_review",
]
