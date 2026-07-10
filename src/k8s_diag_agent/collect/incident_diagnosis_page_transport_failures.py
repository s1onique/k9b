"""Backend protocol failure types for page transport parsing.

Extracted from incident_diagnosis_page_transport.py to keep file sizes below
LLM-friendly thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BackendProtocolFailureKind(StrEnum):
    """Kinds of backend protocol violations."""

    NON_OBJECT_PAYLOAD = "non_object_payload"
    """Top-level payload is not an object."""

    MISSING_INCIDENTS = "missing_incidents"
    """Missing 'incidents' field."""

    INCIDENTS_NOT_LIST = "incidents_not_list"
    """'incidents' field is not a list."""

    INCIDENT_NOT_OBJECT = "incident_not_object"
    """An incident entry is not an object."""

    MISSING_INCIDENT_ID = "missing_incident_id"
    """Incident missing 'incident_id' field."""

    INCIDENT_ID_NOT_STRING = "incident_id_not_string"
    """'incident_id' field is not a string."""

    INCIDENT_ID_EMPTY = "incident_id_empty"
    """'incident_id' field is empty."""

    INCIDENT_ID_TOO_LONG = "incident_id_too_long"
    """'incident_id' exceeds maximum length."""

    INCIDENT_ID_DUPLICATE = "incident_id_duplicate"
    """Duplicate 'incident_id' found within the same page."""

    MISSING_STATUS = "missing_status"
    """Incident missing 'status' field."""

    INVALID_STATUS = "invalid_status"
    """'status' is not a valid domain status."""

    MISSING_TIMESTAMP = "missing_timestamp"
    """Incident missing 'first_observed_at' field."""

    TIMESTAMP_NOT_STRING = "timestamp_not_string"
    """'first_observed_at' is not a string."""

    TIMESTAMP_EMPTY = "timestamp_empty"
    """'first_observed_at' is empty."""

    TIMESTAMP_INVALID = "timestamp_invalid"
    """'first_observed_at' is not a valid ISO timestamp."""

    TIMESTAMP_NAIVE = "timestamp_naive"
    """'first_observed_at' is timezone-naive."""

    NEXTCURSOR_WRONG_TYPE = "nextcursor_wrong_type"
    """'nextCursor' is not null or string."""

    HASMORE_WRONG_TYPE = "hasmore_wrong_type"
    """'hasMore' is not a boolean."""

    TOTAL_WRONG_TYPE = "total_wrong_type"
    """'total' is not an integer."""

    HASMORE_TRUE_NO_NEXTCURSOR = "hasmore_true_no_nextcursor"
    """'hasMore=true' requires 'nextCursor' to be present."""

    HASMORE_FALSE_WITH_NEXTCURSOR = "hasmore_false_with_nextcursor"
    """'hasMore=false' requires 'nextCursor' to be null."""

    PROTOCOL_VIOLATION = "protocol_violation"
    """General protocol violation."""


# Maximum lengths
MAX_INCIDENT_ID_LENGTH = 256
MAX_NEXTCURSOR_LENGTH = 2048


@dataclass(frozen=True, slots=True)
class BackendProtocolFailure:
    """Structured failure from backend protocol violation.

    Attributes:
        kind: Error kind from BackendProtocolFailureKind
        message: Human-readable error message
        incident_index: Index of incident with error, if applicable
    """

    kind: BackendProtocolFailureKind
    message: str
    incident_index: int | None = None


__all__ = [
    "BackendProtocolFailureKind",
    "BackendProtocolFailure",
    "MAX_INCIDENT_ID_LENGTH",
    "MAX_NEXTCURSOR_LENGTH",
]
