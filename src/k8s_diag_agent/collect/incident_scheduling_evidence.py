"""Scheduling evidence extraction for P4c diagnosis.

This module provides deterministic extraction of scheduling-related events
from Kubernetes event lists for use in LLM diagnosis prompts.

Scheduling failure evidence includes:
- FailedScheduling events
- Unschedulable conditions
- nodeSelector mismatch messages
- Pod affinity/anti-affinity conflicts

This extraction ensures the LLM sees the root-cause evidence directly
without relying on implicit correlation.
"""

from __future__ import annotations

from typing import Any

# Scheduling failure markers for P4c diagnosis
_SCHEDULING_FAILURE_MARKERS = (
    "FailedScheduling",
    "Unschedulable",
    "no matching node",
    "cannot schedule",
    "unschedulable",
    "nodeSelector",
    "node affinity/selector",
    "didn't match",
)


def extract_scheduling_evidence(
    events: Any,
) -> list[dict[str, str]] | None:
    """Extract scheduling failure evidence from events.

    For P4c scheduling diagnosis, this explicitly extracts scheduling-related
    events to ensure the LLM sees the root-cause evidence directly.

    Args:
        events: List of event payloads from the case file

    Returns:
        List of scheduling evidence dicts with type, reason, message, and involved_object,
        or None if no scheduling events found.
    """
    if not events:
        return None

    scheduling_evidence: list[dict[str, str]] = []

    for event in events:
        if not isinstance(event, dict):
            continue

        # Check if this is a scheduling-related event
        reason = str(event.get("reason", "")).lower()
        message = str(event.get("message", "")).lower()

        # Check for scheduling failure markers
        is_scheduling = any(
            marker.lower() in reason or marker.lower() in message
            for marker in _SCHEDULING_FAILURE_MARKERS
        )

        if is_scheduling:
            # Extract key scheduling details
            evidence_entry: dict[str, str] = {
                "type": str(event.get("type", "")),
                "reason": str(event.get("reason", "")),
                "message": str(event.get("message", "")),
            }

            # Include involved object if available
            involved_object_kind = event.get("involved_object_kind")
            involved_object_name = event.get("involved_object_name")
            if involved_object_kind:
                evidence_entry["involved_object_kind"] = str(involved_object_kind)
            if involved_object_name:
                evidence_entry["involved_object_name"] = str(involved_object_name)

            scheduling_evidence.append(evidence_entry)

        # Stop after collecting enough evidence
        if len(scheduling_evidence) >= 10:
            break

    return scheduling_evidence if scheduling_evidence else None


__all__ = [
    "extract_scheduling_evidence",
]
