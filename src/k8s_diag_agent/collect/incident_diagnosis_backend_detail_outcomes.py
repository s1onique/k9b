"""Typed outcome algebra for backend incident-detail lookup.

This module defines the canonical three-way lookup outcome used by the
automatic-diagnosis backend read path. The model is designed so that a
successful HTTP 200 response **cannot** be converted into ``BackendIncidentNotFound``
through any parser/schema/deserialization/identity failure: every non-404
anomaly is funnelled into ``BackendIncidentLookupFailed`` with a stable
``BackendIncidentLookupFailureCode``.

Design contract (ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01):

* Three disjoint outcome variants: ``BackendIncidentFound``,
  ``BackendIncidentNotFound``, and ``BackendIncidentLookupFailed``.
* No ``Incident | None``, no ``Optional[Incident]``, no boolean ``found``
  flag, no ``(incident, error)`` tuple.
* Failure reason is an enum (``BackendIncidentLookupFailureCode``);
  ``BackendIncidentLookupFailed`` is NOT a subclass of ``BackendIncidentNotFound``.
* Outcome dataclasses are frozen; ``requested_incident_id`` is retained on
  every variant as a branded ``IncidentId`` (not a bare ``str``).
* ``BackendIncidentFound.incident`` is statically typed as the canonical
  :class:`Incident` aggregate; the field cannot be widened to ``object``,
  ``Any``, ``dict``, or any union containing them.
* ``BackendIncidentNotFound`` carries an explicit ``source`` discriminator
  (``BackendIncidentLookupSource``) so the logs never claim an HTTP status
  that was not observed. Backend mode sets ``http_status=404``; local-store
  mode leaves ``http_status=None``.
* The ``BackendIncidentNotFound`` constructor MUST only be reachable from
  the HTTP 404 branch of the canonical lookup function. Static-verifier
  rules enforce this.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01
R1 follow-up: ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01-R1
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from k8s_diag_agent.collect.incident_lifecycle import Incident
from k8s_diag_agent.domain.incident_lifecycle import IncidentId

__all__ = [
    "BackendIncidentLookupFailureCode",
    "BackendIncidentLookupSource",
    "BackendIncidentFound",
    "BackendIncidentNotFound",
    "BackendIncidentLookupFailed",
    "BackendIncidentLookupOutcome",
    "BackendIncidentLookupDiagnostic",
    "make_lookup_diagnostic",
]


# ---------------------------------------------------------------------------
# Failure codes
# ---------------------------------------------------------------------------


class BackendIncidentLookupFailureCode(StrEnum):
    """Canonical closed vocabulary of backend incident-detail lookup failures.

    Stable, low-cardinality, machine-readable strings. Detail-level
    information belongs in bounded diagnostics, never in the code value.
    """

    INVALID_JSON = "invalid_json"
    INVALID_PAYLOAD = "invalid_payload"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    DESERIALIZATION_FAILED = "deserialization_failed"
    IDENTITY_MISMATCH = "identity_mismatch"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    HTTP_CLIENT_ERROR = "http_client_error"
    BACKEND_ERROR = "backend_error"
    TRANSPORT_ERROR = "transport_error"


# ---------------------------------------------------------------------------
# Lookup source discriminator
# ---------------------------------------------------------------------------


class BackendIncidentLookupSource(StrEnum):
    """Where the canonical lookup result was sourced from.

    ``BACKEND_API`` indicates a real HTTP read against the backend
    internal-detail API; ``http_status`` MUST be set to the observed value
    (typically ``404`` for the not-found variant).

    ``LOCAL_STORE`` indicates an in-process read against the local
    incident store (no HTTP transport); ``http_status`` MUST be ``None``
    because no HTTP status was observed. Logs MUST NOT claim an HTTP
    status that was not observed.
    """

    BACKEND_API = "backend_api"
    LOCAL_STORE = "local_store"


# ---------------------------------------------------------------------------
# Bounded diagnostic
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BackendIncidentLookupDiagnostic:
    """Bounded, redaction-safe metadata about a backend incident lookup.

    Only safe metadata is retained: never the raw response body, never the
    ``Authorization`` header, never internal API tokens. ``detail`` is
    pre-truncated using the canonical disposition-detail bound (see
    :mod:`k8s_diag_agent.collect.incident_diagnosis_disposition`).
    """

    requested_incident_id: IncidentId
    http_status: int | None
    failure_code: BackendIncidentLookupFailureCode | None
    payload_schema_version: int | None
    payload_type: str | None
    exception_type: str | None
    detail: str | None


def make_lookup_diagnostic(
    *,
    requested_incident_id: IncidentId,
    http_status: int | None = None,
    failure_code: BackendIncidentLookupFailureCode | None = None,
    payload_schema_version: int | None = None,
    payload_type: str | None = None,
    exception_type: str | None = None,
    detail: str | None = None,
    max_chars: int = 512,
) -> BackendIncidentLookupDiagnostic:
    """Construct a bounded diagnostic with the canonical detail-truncation bound.

    The default bound matches :data:`incident_diagnosis_disposition.DEFAULT_DETAIL_MAX_CHARS`.
    """

    from .incident_diagnosis_disposition import sanitize_disposition_detail

    sanitized_detail = sanitize_disposition_detail(detail, max_chars=max_chars)
    return BackendIncidentLookupDiagnostic(
        requested_incident_id=requested_incident_id,
        http_status=http_status,
        failure_code=failure_code,
        payload_schema_version=payload_schema_version,
        payload_type=payload_type,
        exception_type=exception_type,
        detail=sanitized_detail,
    )


# ---------------------------------------------------------------------------
# Outcome variants
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BackendIncidentFound:
    """The backend returned a valid canonical incident matching the request.

    The :attr:`incident` field is statically typed as the canonical
    :class:`Incident` aggregate. It cannot be widened to ``object``,
    ``Any``, ``dict``, or any union containing them; the negative
    mypy proof ``BackendIncidentFound(..., incident={"incident_id": "x"})``
    is therefore expected to fail type checking.

    The :attr:`source` discriminator is required for every construction
    site and indicates where the typed found outcome was produced from.
    For an HTTP-backed read the value is
    :attr:`BackendIncidentLookupSource.BACKEND_API` and ``http_status``
    must equal the observed value (typically ``200``). For a local-store
    read the value is
    :attr:`BackendIncidentLookupSource.LOCAL_STORE` and ``http_status``
    must be ``None`` because no HTTP exchange occurred.
    """

    requested_incident_id: IncidentId
    incident: Incident
    source: BackendIncidentLookupSource
    http_status: int | None
    payload_schema_version: int | None
    payload_type: str | None

    def __post_init__(self) -> None:
        if (
            self.source == BackendIncidentLookupSource.BACKEND_API
            and self.http_status != 200
        ):
            raise ValueError(
                "BackendIncidentFound with source=BACKEND_API must have "
                f"http_status == 200 (got {self.http_status!r})."
            )
        if (
            self.source == BackendIncidentLookupSource.LOCAL_STORE
            and self.http_status is not None
        ):
            raise ValueError(
                "BackendIncidentFound with source=LOCAL_STORE must have "
                "http_status=None; no HTTP status was observed."
            )


@dataclass(frozen=True, slots=True)
class BackendIncidentNotFound:
    """The requested incident was not found.

    This variant is constructed by the canonical lookup when the backend
    returns HTTP 404 (``source=BackendIncidentLookupSource.BACKEND_API``,
    ``http_status=404``) and by the dispatcher when the local store
    returns ``None`` (``source=BackendIncidentLookupSource.LOCAL_STORE``,
    ``http_status=None``). The source discriminator is the only truthful
    way to distinguish the two paths in the logs; ``http_status`` MUST
    be ``None`` whenever ``source == LOCAL_STORE``.
    """

    requested_incident_id: IncidentId
    source: BackendIncidentLookupSource
    http_status: int | None = None

    def __post_init__(self) -> None:
        if self.source == BackendIncidentLookupSource.LOCAL_STORE and self.http_status is not None:
            raise ValueError(
                "BackendIncidentNotFound with source=LOCAL_STORE must have http_status=None; "
                "no HTTP status was observed."
            )
        if self.source == BackendIncidentLookupSource.BACKEND_API and self.http_status != 404:
            raise ValueError(
                "BackendIncidentNotFound with source=BACKEND_API must have http_status=404; "
                f"got http_status={self.http_status!r}."
            )


@dataclass(frozen=True, slots=True)
class BackendIncidentLookupFailed:
    """The backend lookup did not produce a typed found/not-found outcome.

    Every failure mode of the canonical lookup is funnelled here:
    transport errors, malformed JSON, invalid payloads, unsupported schema
    versions, deserialization errors, identity mismatches, and HTTP 4xx
    (except 404) / 5xx responses.
    """

    requested_incident_id: IncidentId
    failure_code: BackendIncidentLookupFailureCode
    detail: str
    http_status: int | None = None
    payload_schema_version: int | None = None
    payload_type: str | None = None
    exception_type: str | None = None

    def to_diagnostic(self) -> BackendIncidentLookupDiagnostic:
        """Project this failure into a bounded diagnostic."""
        return make_lookup_diagnostic(
            requested_incident_id=self.requested_incident_id,
            http_status=self.http_status,
            failure_code=self.failure_code,
            payload_schema_version=self.payload_schema_version,
            payload_type=self.payload_type,
            exception_type=self.exception_type,
            detail=self.detail,
        )


# Canonical closed union of all lookup outcomes.
BackendIncidentLookupOutcome: TypeAlias = (
    "BackendIncidentFound | BackendIncidentNotFound | BackendIncidentLookupFailed"
)