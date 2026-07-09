"""Read-only serializers for the internal scheduler-to-backend API.

This module provides serialization functions for the internal incident
read API used by the automatic diagnosis loop.

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO persistence (in-memory only for this module)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, TypedDict

# =============================================================================
# TypedDict Payloads (moved from api_payloads_incident_reads.py for LLM-friendliness)
# =============================================================================


class IncidentSignalPayload(TypedDict, total=False):
    """Signal that contributed to an incident.

    Provenance fields (run_id, detector_id, finding_id, fingerprint) are optional.
    """

    source: str
    reason: str
    message: str
    captured_at: str
    run_id: str | None
    detector_id: str | None
    finding_id: str | None
    fingerprint: str | None


class IncidentInternalListItemPayload(TypedDict):
    """Internal scheduler-to-backend incident list item projection.

    This payload is used by the internal API (GET /api/internal/incidents)
    for scheduler/backend communication. It provides a lightweight summary
    for the automatic diagnosis loop.

    Design constraints:
    - Serializes first_observed_at as created_at (API compatibility)
    - Serializes last_observed_at as updated_at (API compatibility)
    - object_kind is a plain string (not enum.value)

    Haskellized: one total projection function from Incident -> dict,
    with no ad-hoc field access scattered in handlers.

    Note: All fields are required (total=True) for maximum static enforcement.
    """

    incident_id: str
    source_candidate_id: str
    namespace: str
    object_kind: str
    raw_object_kind: str | None
    object_name: str
    candidate_class: str
    severity: str
    status: str
    created_at: str | None  # Mapped from first_observed_at
    updated_at: str | None  # Mapped from last_observed_at
    signal_count: int
    evidence_count: int


class IncidentInternalDetailPayload(TypedDict):
    """Internal scheduler-to-backend incident detail projection.

    This payload is used by the internal API (GET /api/internal/incidents/{id})
    for scheduler/backend communication. It provides full incident detail
    for the automatic diagnosis loop.

    Design constraints:
    - Serializes first_observed_at as created_at (API compatibility)
    - Serializes last_observed_at as updated_at (API compatibility)
    - Includes signals for diagnosis context
    - object_kind is a plain string (not enum.value)

    Haskellized: one total projection function from Incident -> dict,
    with no ad-hoc field access scattered in handlers.

    Note: All fields are required (total=True) for maximum static enforcement.
    """

    incident_id: str
    source_candidate_id: str
    namespace: str
    object_kind: str
    raw_object_kind: str | None
    object_name: str
    candidate_class: str
    severity: str
    status: str
    created_at: str | None  # Mapped from first_observed_at
    updated_at: str | None  # Mapped from last_observed_at
    signal_count: int
    evidence_count: int
    signals: list[IncidentSignalPayload]


# =============================================================================
# Small structural protocols for fanatical typing
# =============================================================================


class StatusValueReadable(Protocol):
    """Protocol for status values that have a string .value property."""

    @property
    def value(self) -> str: ...


class IsoDatetimeReadable(Protocol):
    """Protocol for datetime-like objects with isoformat()."""

    def isoformat(self) -> str: ...


class IncidentSignalReadable(Protocol):
    """Protocol for signal-like objects in incident payloads.

    Matches the dataclass structure of IncidentSignal for structural subtyping.
    Plain attributes (no @property) to match dataclass field semantics.
    """

    # Required fields
    source: str
    reason: str
    message: str
    captured_at: datetime  # datetime has isoformat() method

    # Optional fields
    run_id: str | None
    detector_id: str | None
    finding_id: str | None
    fingerprint: str | None


# Protocol for structural subtyping - static analysis only, not runtime-checked.
# Using Protocol enables duck-typing: any object with the required properties
# can be serialized, regardless of concrete type.
class IncidentReadable(Protocol):
    """Structural protocol for incident-like read inputs.

    This protocol defines the minimum interface required for serializing
    incidents to internal API payloads. Any object with these properties
    can be serialized, regardless of concrete type.

    This enables duck-typing: test mocks and adapters can satisfy this
    protocol without inheriting from Incident, promoting looser coupling
    between the serialization layer and the domain model.

    Note: status.value is called at serialization time to ensure the
    enum value (not the enum object) is returned.
    """

    @property
    def incident_id(self) -> str: ...

    @property
    def source_candidate_id(self) -> str: ...

    @property
    def namespace(self) -> str: ...

    @property
    def object_kind(self) -> str: ...

    @property
    def raw_object_kind(self) -> str | None: ...

    @property
    def object_name(self) -> str: ...

    @property
    def candidate_class(self) -> str: ...

    @property
    def severity(self) -> str: ...

    @property
    def status(self) -> StatusValueReadable: ...  # Has .value property (StrEnum)

    @property
    def first_observed_at(self) -> IsoDatetimeReadable | None: ...

    @property
    def last_observed_at(self) -> IsoDatetimeReadable | None: ...

    @property
    def signal_count(self) -> int: ...

    @property
    def evidence_count(self) -> int: ...

    @property
    def signals(self) -> Any: ...  # Iterable[IncidentSignalReadable] - variance issues, handled in impl


# =============================================================================
# Serialization Functions
# =============================================================================


__all__ = [
    "build_incident_internal_list_item_payload",
    "build_incident_internal_detail_payload",
]


def _signal_to_payload(signal: Any) -> IncidentSignalPayload:
    """Convert IncidentSignal to IncidentSignalPayload.

    Helper for building signal lists in detail payloads.
    IncidentSignal.captured_at is always a datetime (required field).
    """
    return {
        "source": signal.source,
        "reason": signal.reason,
        "message": signal.message,
        "captured_at": signal.captured_at.isoformat(),
        "run_id": signal.run_id,
        "detector_id": signal.detector_id,
        "finding_id": signal.finding_id,
        "fingerprint": signal.fingerprint,
    }


def build_incident_internal_detail_payload(
    incident: IncidentReadable,
) -> IncidentInternalDetailPayload:
    """Build IncidentInternalDetailPayload from Incident model.

    Internal scheduler-to-backend incident detail projection.
    Used by GET /api/internal/incidents/{id} for the automatic diagnosis loop.

    Haskellized: one total projection function from Incident -> dict,
    with no ad-hoc field access scattered in handlers.

    Design constraints:
    - Serializes first_observed_at as created_at (API compatibility)
    - Serializes last_observed_at as updated_at (API compatibility)
    - Includes signals for diagnosis context
    - object_kind is a plain string (Incident.object_kind is already str)
    """
    return {
        "incident_id": incident.incident_id,
        "source_candidate_id": incident.source_candidate_id,
        "namespace": incident.namespace,
        "object_kind": incident.object_kind,
        "raw_object_kind": incident.raw_object_kind,
        "object_name": incident.object_name,
        "candidate_class": incident.candidate_class,
        "severity": incident.severity,
        "status": incident.status.value,
        "created_at": (
            incident.first_observed_at.isoformat()
            if incident.first_observed_at
            else None
        ),
        "updated_at": (
            incident.last_observed_at.isoformat()
            if incident.last_observed_at
            else None
        ),
        "signal_count": incident.signal_count,
        "evidence_count": incident.evidence_count,
        "signals": [_signal_to_payload(s) for s in incident.signals],
    }


def build_incident_internal_list_item_payload(
    incident: IncidentReadable,
) -> IncidentInternalListItemPayload:
    """Build IncidentInternalListItemPayload from Incident model.

    Internal scheduler-to-backend incident list item projection.
    Used by GET /api/internal/incidents for the automatic diagnosis loop.

    Haskellized: one total projection function from Incident -> dict,
    with no ad-hoc field access scattered in handlers.

    Design constraints:
    - Serializes first_observed_at as created_at (API compatibility)
    - Serializes last_observed_at as updated_at (API compatibility)
    - object_kind is a plain string (Incident.object_kind is already str)
    """
    return {
        "incident_id": incident.incident_id,
        "source_candidate_id": incident.source_candidate_id,
        "namespace": incident.namespace,
        "object_kind": incident.object_kind,
        "raw_object_kind": incident.raw_object_kind,
        "object_name": incident.object_name,
        "candidate_class": incident.candidate_class,
        "severity": incident.severity,
        "status": incident.status.value,
        "created_at": (
            incident.first_observed_at.isoformat()
            if incident.first_observed_at
            else None
        ),
        "updated_at": (
            incident.last_observed_at.isoformat()
            if incident.last_observed_at
            else None
        ),
        "signal_count": incident.signal_count,
        "evidence_count": incident.evidence_count,
    }
