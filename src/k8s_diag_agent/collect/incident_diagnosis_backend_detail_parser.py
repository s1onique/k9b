"""Canonical parser for the backend incident-detail payload.

The parser is the **single** total projection from the raw backend HTTP
response body to the typed envelope used by the automatic-diagnosis
backend lookup.

Design contract:

* Rejects non-object top-level JSON.
* Validates the API envelope (``schema_version`` + ``payload_type``).
* Validates ``payload_type == "incident-internal-detail"``.
* Validates the schema version is supported (currently ``"1"`` only).
* Requires the ``incident`` aggregate field to be present and an object.
* Returns typed parsed data (``ParsedInternalIncidentDetail``) carrying
  the envelope metadata alongside the aggregate.
* Never returns ``None`` to indicate malformed data; raises
  :class:`BackendIncidentDetailParseError` (or its subclasses) instead.
* Never treats an arbitrary dictionary as an incident merely because it
  has an ``incident_id`` field.

The legacy :func:`incident_diagnosis_dispatch_contracts.parse_backend_incident_detail_payload`
parser is preserved for the listing payload path and is kept as a
thin shim around the legacy bare-aggregate contract. The canonical
*incident-detail* parser is this one; the legacy parser is only invoked
from the listing path where bare aggregates historically appeared.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from k8s_diag_agent.domain.incident_lifecycle import IncidentId

__all__ = [
    "SUPPORTED_PAYLOAD_TYPE",
    "SUPPORTED_SCHEMA_VERSION",
    "ParsedInternalIncidentDetail",
    "BackendIncidentDetailParseError",
    "BackendIncidentInvalidJsonError",
    "BackendIncidentInvalidPayloadError",
    "BackendIncidentUnsupportedSchemaError",
    "BackendIncidentDeserializationError",
    "parse_internal_incident_detail_payload",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


SUPPORTED_PAYLOAD_TYPE: Final[str] = "incident-internal-detail"
"""The only ``payload_type`` value accepted by the canonical parser."""

SUPPORTED_SCHEMA_VERSION: Final[int] = 1
"""The only ``schema_version`` value accepted by the canonical parser."""


# ---------------------------------------------------------------------------
# Typed parsed result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParsedInternalIncidentDetail:
    """Typed projection of a backend incident-detail response envelope.

    The :attr:`incident` field carries the raw aggregate dictionary
    (still a dict; the canonical lookup function delegates its
    deserialization to :class:`k8s_diag_agent.collect.incident_lifecycle.Incident.from_dict`).
    """

    requested_incident_id: IncidentId
    payload_type: str
    schema_version: int
    incident: dict[str, Any]


# ---------------------------------------------------------------------------
# Parse error hierarchy
# ---------------------------------------------------------------------------


class BackendIncidentDetailParseError(ValueError):
    """Base class for canonical-parser errors.

    The lookup function translates each subclass into a precise
    :class:`BackendIncidentLookupFailureCode`; never collapse them
    into a generic ``ValueError``.
    """

    def __init__(self, message: str, *, missing_field: str | None = None) -> None:
        super().__init__(message)
        self.missing_field = missing_field


class BackendIncidentInvalidJsonError(BackendIncidentDetailParseError):
    """The response body could not be decoded as JSON."""


class BackendIncidentInvalidPayloadError(BackendIncidentDetailParseError):
    """The response body decoded to JSON but did not match the contract envelope."""


class BackendIncidentUnsupportedSchemaError(BackendIncidentDetailParseError):
    """The ``schema_version`` field is not in the supported set."""


class BackendIncidentDeserializationError(BackendIncidentDetailParseError):
    """The aggregate could not be deserialized into a domain ``Incident``."""


# ---------------------------------------------------------------------------
# Canonical parser
# ---------------------------------------------------------------------------


def _coerce_schema_version(value: object) -> int | None:
    """Coerce a schema-version value to ``int`` when possible.

    Accepts ``int`` directly, ``str`` representations like ``"1"``, and
    returns ``None`` for unsupported shapes so the caller can map the
    shape mismatch to ``BackendIncidentInvalidPayloadError``.
    """
    if isinstance(value, bool):
        # bool is a subclass of int but never a valid schema version.
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped, base=10)
        except ValueError:
            return None
    return None


def parse_internal_incident_detail_payload(
    payload: object,
    *,
    requested_incident_id: IncidentId,
) -> ParsedInternalIncidentDetail:
    """Parse a backend incident-detail response into typed envelope data.

    Args:
        payload: The raw decoded JSON payload (already deserialised by the
            caller from the HTTP response body).
        requested_incident_id: The branded ``IncidentId`` the caller asked
            for. The parser retains it on the parsed result so the lookup
            function can validate the returned incident identity.

    Returns:
        A :class:`ParsedInternalIncidentDetail` instance carrying the
        envelope metadata and the aggregate dict.

    Raises:
        BackendIncidentInvalidPayloadError: When ``payload`` is not a JSON
            object, is missing the required envelope fields, or has a
            non-object ``incident`` aggregate.
        BackendIncidentUnsupportedSchemaError: When ``schema_version`` is
            not in the supported set.
        BackendIncidentDeserializationError: When the aggregate fails
            canonical field validation. (The lookup function does NOT
            call ``Incident.from_dict`` from this parser; it only
            performs envelope validation. Deserialization itself is
            performed by the lookup function with the canonical
            ``Incident.from_dict`` call, so this error is reserved for
            the rare envelope-time aggregate-shape issue that prevents
            passing it to ``Incident.from_dict``.)
    """
    if not isinstance(payload, dict):
        raise BackendIncidentInvalidPayloadError(
            "backend incident response is not a JSON object",
            missing_field=None,
        )

    payload_type = payload.get("payload_type")
    if not isinstance(payload_type, str) or not payload_type:
        raise BackendIncidentInvalidPayloadError(
            "backend incident response missing string payload_type",
            missing_field="payload_type",
        )
    if payload_type != SUPPORTED_PAYLOAD_TYPE:
        raise BackendIncidentInvalidPayloadError(
            (
                f"backend incident response has unsupported payload_type "
                f"{payload_type!r}; expected {SUPPORTED_PAYLOAD_TYPE!r}"
            ),
            missing_field="payload_type",
        )

    if "schema_version" not in payload:
        raise BackendIncidentInvalidPayloadError(
            "backend incident response missing schema_version",
            missing_field="schema_version",
        )
    schema_version = _coerce_schema_version(payload["schema_version"])
    if schema_version is None:
        raise BackendIncidentInvalidPayloadError(
            (
                "backend incident response schema_version is not an integer: "
                f"{payload['schema_version']!r}"
            ),
            missing_field="schema_version",
        )
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise BackendIncidentUnsupportedSchemaError(
            (
                f"backend incident response schema_version {schema_version} "
                f"is not supported (expected {SUPPORTED_SCHEMA_VERSION})"
            ),
            missing_field=None,
        )

    aggregate = payload.get("incident")
    if not isinstance(aggregate, dict):
        raise BackendIncidentInvalidPayloadError(
            "backend incident response does not contain an incident object",
            missing_field="incident",
        )

    return ParsedInternalIncidentDetail(
        requested_incident_id=requested_incident_id,
        payload_type=payload_type,
        schema_version=schema_version,
        incident=aggregate,
    )
