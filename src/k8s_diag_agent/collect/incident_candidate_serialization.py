"""Canonical serialization for IncidentCandidate objects.

This module provides serialization/deserialization for IncidentCandidate objects
used in the scheduler-to-backend promotion API.

Usage:
    # Serialize candidates for API transmission
    candidate_dicts = [incident_candidate_to_dict(c) for c in candidates]

    # Deserialize candidates from API response
    candidates = [incident_candidate_from_dict(d) for d in candidate_dicts]
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from .incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)


def _wire_value(value: Any) -> str:
    """Convert a value to a wire-safe string.

    Handles both Enum members (which have .value) and raw strings.
    This ensures the serializer is tolerant of both enum instances
    and string literals when building candidate dicts.
    """
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _input_value(value: Any) -> str:
    """Convert an input value to a normalized string.

    Handles both Enum members and raw strings, converting to lowercase
    for case-insensitive matching before enum construction.
    """
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def incident_candidate_to_dict(candidate: IncidentCandidate) -> dict[str, Any]:
    """Convert an IncidentCandidate to a dict for API transmission.

    Args:
        candidate: The IncidentCandidate to serialize

    Returns:
        Dict representation suitable for JSON serialization and API transmission
    """
    # Use _wire_value for backward compatibility - the dataclass.to_dict()
    # already handles enum values correctly, but tests may pass raw strings
    signals = [
        {
            "source": signal.source,
            "reason": signal.reason,
            "message": signal.message,
        }
        for signal in candidate.signals
    ]

    result: dict[str, Any] = {
        "candidate_id": candidate.candidate_id,
        "namespace": candidate.namespace,
        "object_kind": _wire_value(candidate.object_kind),
        "object_name": candidate.object_name,
        "class": _wire_value(candidate.candidate_class),
        "candidate_class": _wire_value(candidate.candidate_class),
        "severity": _wire_value(candidate.severity),
        "signals": signals,
        "evidence_needed": list(candidate.evidence_needed),
    }

    if candidate.raw_object_kind:
        result["raw_object_kind"] = candidate.raw_object_kind

    return result


def incident_candidate_from_dict(data: dict[str, Any]) -> IncidentCandidate:
    """Parse an IncidentCandidate from a dict (e.g., from API request body).

    Args:
        data: Dict parsed from JSON request body

    Returns:
        IncidentCandidate instance

    Raises:
        ValueError: If required fields are missing or have invalid values
    """
    # Parse severity
    sev_str = data.get("severity", "warning")
    if sev_str.lower() == "error":
        severity = Severity.ERROR
    else:
        severity = Severity.WARNING

    # Parse object kind - handle both enum value and raw string
    kind_str = data.get("object_kind", "Unknown")
    try:
        object_kind = ObjectKind(kind_str)
    except ValueError:
        object_kind = ObjectKind.UNKNOWN

    # Parse candidate class - handle both enum value and raw string
    class_str = data.get("candidate_class", data.get("class", "unknown"))
    try:
        candidate_class = CandidateClass(class_str)
    except ValueError:
        candidate_class = CandidateClass.UNKNOWN

    # Build signals
    signals: list[CandidateSignal] = []
    for sig_data in data.get("signals", []):
        signals.append(
            CandidateSignal(
                source=sig_data.get("source", "detector"),
                reason=sig_data.get("reason", ""),
                message=sig_data.get("message", ""),
            )
        )

    # Build evidence needed as tuple
    evidence_needed = tuple(data.get("evidence_needed", []))

    # Validate required fields
    candidate_id = data.get("candidate_id", "")
    if not candidate_id:
        raise ValueError("candidate_id is required")

    namespace = data.get("namespace", "")
    if not namespace:
        raise ValueError("namespace is required")

    object_name = data.get("object_name", "")
    if not object_name:
        raise ValueError("object_name is required")

    return IncidentCandidate(
        candidate_id=candidate_id,
        namespace=namespace,
        object_kind=object_kind,
        object_name=object_name,
        candidate_class=candidate_class,
        severity=severity,
        signals=tuple(signals),
        evidence_needed=evidence_needed,
        raw_object_kind=data.get("raw_object_kind"),
    )


def incident_candidates_to_dict_list(
    candidates: list[IncidentCandidate],
) -> list[dict[str, Any]]:
    """Convert a list of IncidentCandidates to a list of dicts.

    Args:
        candidates: List of IncidentCandidates to serialize

    Returns:
        List of dict representations
    """
    return [incident_candidate_to_dict(c) for c in candidates]


def incident_candidates_from_dict_list(
    data: list[dict[str, Any]],
) -> list[IncidentCandidate]:
    """Parse a list of IncidentCandidates from a list of dicts.

    Args:
        data: List of dicts parsed from JSON request body

    Returns:
        List of IncidentCandidate instances

    Raises:
        ValueError: If any candidate fails to parse
    """
    return [incident_candidate_from_dict(c) for c in data]


__all__ = [
    "incident_candidate_to_dict",
    "incident_candidate_from_dict",
    "incident_candidates_to_dict_list",
    "incident_candidates_from_dict_list",
]
