"""Closed union of promotion outcomes.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 domain model.

Promotion is a single authoritative decision with three mutually
exclusive variants:

* :class:`PromotionSucceeded` -- the request was accepted; the
  returned diagnosis IDs are safe to dispatch. Empty IDs are
  a valid authoritative zero-work result.
* :class:`PromotionRejected` -- the request is known not to have
  committed; diagnosis MUST NOT consume IDs from this outcome.
* :class:`PromotionCommitUnknown` -- the caller cannot prove whether
  the request committed; reconciliation is mandatory before
  diagnosis may proceed.

Counts that previously accompanied promotion booleans
(``promotion_may_have_committed``,
``promotion_propagated_to_diagnosis``,
``promotion_consistency_error_recorded``) are now projections of the
outcome variant. They are not separately maintained authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .incident_identity_hardening import PromotionRecord


class PromotionRejectionCode(StrEnum):
    """Bounded reason codes for :class:`PromotionRejected`.

    Free-form detail may be attached, but authority decisions MUST
    only branch on this enum.
    """

    CURRENT_RUN_SCOPE_VIOLATION = "current_run_scope_violation"
    """A signal id was not present in the current-run scope."""

    SOURCE_IDENTITY_MISMATCH = "source_identity_mismatch"
    """A signal belongs to a different source instance."""

    CONTRACT_VIOLATION = "contract_violation"
    """The wire request was malformed."""

    MALFORMED_SIGNAL_IDS = "malformed_signal_ids"
    """Signal ids violated the safe-id contract."""

    DUPLICATE_SIGNAL_IDS = "duplicate_signal_ids"
    """The workset contained duplicate signal ids."""

    UNSUPPORTED_FIELDS = "unsupported_fields"
    """Wire request contained unknown fields where strict parsing forbids them."""

    WORKLIST_INCONSISTENT = "worklist_inconsistent"
    """The backend's authoritative lookup contradicted the dispatcher."""

    EXTERNAL_RULE_FAILURE = "external_rule_failure"
    """Backend rule engine refused the promotion explicitly."""

    CONFIGURATION_BLOCKED = "configuration_blocked"
    """Missing or invalid scheduler / backend configuration."""

    BACKEND_UNREACHABLE = "backend_unreachable"
    """DNS failure, connection refused, or pre-connect TLS error."""

    AUTHENTICATION_REJECTED = "authentication_rejected"
    """The backend returned ``401`` or ``403`` before promotion
    execution could begin."""

    PROMOTION_HTTP_ERROR_UNCERTAIN = "promotion_http_error_uncertain"
    """Generic untyped HTTP error (4xx / 5xx) whose commit status
    cannot be inferred from the status code alone; reconciliation
    is required before commit certainty is established."""

    UNKNOWN = "unknown"
    """Catch-all bucket. Use sparingly; prefer a specific code."""


class PromotionCommitDisposition(StrEnum):
    """Closed commit-certainty disposition for any promotion outcome.

    Three values exhaust the possible states:
    ``DEFINITELY_COMMITTED``, ``DEFINITELY_NOT_COMMITTED``, and
    ``MAY_HAVE_COMMITTED``. A compatibility property exposes the
    legacy ``may_have_committed`` boolean where required.
    """

    DEFINITELY_COMMITTED = "definitely_committed"
    """The backend acknowledged a completed commit."""

    DEFINITELY_NOT_COMMITTED = "definitely_not_committed"
    """The backend rejected before promotion execution could begin,
    OR no request body was transmitted."""

    MAY_HAVE_COMMITTED = "may_have_committed"
    """Transport returned without proving whether the request body
    was processed; reconciliation is required before commit
    certainty is established."""


class PromotionUncertaintyCode(StrEnum):
    """Bounded reason codes for :class:`PromotionCommitUnknown`.

    Reconciliation is mandatory regardless of which code is recorded.
    """

    TRANSPORT_TIMEOUT = "transport_timeout"
    """Request reached the wire but no response was received in time."""

    TRANSPORT_REFUSED = "transport_refused"
    """Connection refused at the backend boundary."""

    PROTOCOL_ERROR = "protocol_error"
    """The response was unparseable or violated the wire contract."""

    BACKEND_INTERNAL_ERROR = "backend_internal_error"
    """The backend returned 5xx but did not acknowledge the request."""

    AMBIGUOUS_RESPONSE = "ambiguous_response"
    """Invariant-violation fallback. NOT used for any known transport shape."""

    # ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION11:
    # Bounded codes replacing AMBIGUOUS_RESPONSE for known classifier inputs.
    # Each known shape maps to a specific code so the operator can correlate
    # the selection handoff with the actual transport observation.
    DISPATCH_RETURNED_NONE = "dispatch_returned_none"
    """Dispatcher returned None without a transport observation."""

    DISPATCH_INTERNAL_ERROR = "dispatch_internal_error"
    """Dispatcher raised PromotionDispatchError (internal dispatch failure)."""

    DISPATCH_UNTYPED_EXCEPTION = "dispatch_untyped_exception"
    """Dispatcher raised an unexpected exception type."""

    # ACT-K9B-HULK-PROMOTION-AMBIGUOUS-RESPONSE-TRANSPORT-TRUTH01:
    # bounded codes replacing the catch-all bucket. Each known HTTP
    # shape maps to a specific code so the operator can correlate the
    # selection handoff with the actual transport observation.
    HTTP_ACCEPTED_WITHOUT_RESULT = "http_accepted_without_result"
    """``202 Accepted`` without an authoritative completion result."""

    HTTP_NO_CONTENT_AFTER_SEND = "http_no_content_after_send"
    """``204 No Content`` after a mutating request."""

    HTTP_EMPTY_SUCCESS_BODY = "http_empty_success_body"
    """``2xx`` with an empty body (cannot be reinterpreted as successful zero)."""

    HTTP_INVALID_JSON = "http_invalid_json"
    """Response completed but the body failed to decode as JSON."""

    HTTP_INVALID_SCHEMA = "http_invalid_schema"
    """Response decoded as JSON but failed wire-schema validation."""

    HTTP_RESPONSE_TRUNCATED = "http_response_truncated"
    """The response body exceeded the bounded reader limit."""

    HTTP_RESPONSE_BODY_LIMIT_EXCEEDED = "http_response_body_limit_exceeded"
    """The response body exceeded the bounded reader cap; the body
    is dropped to prevent silent truncation masquerading as
    complete input."""

    HTTP_RESPONSE_SHORT_READ = "http_response_short_read"
    """The declared Content-Length exceeds the bytes actually
    received from the response stream."""

    HTTP_READ_TIMEOUT_AFTER_SEND = "http_read_timeout_after_send"
    """Read timeout after the request body was transmitted."""

    HTTP_CONNECTION_LOST_AFTER_SEND = "http_connection_lost_after_send"
    """Connection lost after the request body was transmitted."""

    HTTP_TRANSMISSION_UNKNOWN = "http_transmission_unknown"
    """Transport failure after dispatch where the boundary cannot
    prove whether the request bytes reached the wire. The active
    scoped path emits this only after the dispatcher exhausts the
    closed :class:`ScopedDispatchUncertaintyReason` vocabulary."""

    PROMOTION_HTTP_ERROR_UNCERTAIN = "promotion_http_error_uncertain"
    """Generic untyped HTTP error (4xx / 5xx) whose commit status
    cannot be inferred from the status code alone; reconciliation
    is required before commit certainty is established."""

    HTTP_FAILURE_BEFORE_SEND = "http_failure_before_send"
    """Transport failure before the request was transmitted."""

    UNEXPECTED_CLIENT_RESULT = "unexpected_client_result"
    """Final invariant-violation fallback. Production code MUST NOT raise this."""


@dataclass(frozen=True, slots=True)
class PromotionReconciliationToken:
    """Stable reconciliation identifier carried on commit-unknown outcomes.

    The token is the only authoritative bridge between the original
    request and a later reconciliation attempt. Backend APIs that
    surface a read-after-write reconcile operation can reuse the
    ``request_id`` value; transport-only uncertainty uses the
    generated ``request_fingerprint``.

    Two tokens are equal iff **both** ``request_id`` and
    ``request_fingerprint`` match. ``request_id`` carries the
    backend-side identity; ``request_fingerprint`` is the local
    deterministic digest of the request. A backend may issue a
    different ``request_id`` for the same logical request
    (e.g. after a retry), so the dataclass contract uses field-by-
    field comparison rather than fingerprint-only.
    """

    request_id: str
    """Stable backend-side identity for the original request."""

    request_fingerprint: str
    """Deterministic fingerprint of the original request payload."""


@dataclass(frozen=True, slots=True)
class PromotionSucceeded:
    """Promotion was accepted; diagnosis may consume the IDs.

    ``diagnosis_incident_ids=()`` is a valid authoritative zero-work
    result and MUST NOT trigger any kind of fallback.
    """

    run_id: str
    requested_signal_ids: tuple[str, ...]
    records: tuple[PromotionRecord, ...]
    diagnosis_incident_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("PromotionSucceeded requires a run_id")
        # Runtime validation: every record MUST be a PromotionRecord.
        # Using typing.cast() in the classifier is a no-op at runtime;
        # this __post_init__ enforces the contract so invalid states
        # (e.g. strings or tuples from test stubs) are rejected at
        # construction time rather than failing only when projected.
        for i, record in enumerate(self.records):
            if not isinstance(record, PromotionRecord):
                raise TypeError(
                    f"PromotionSucceeded.records[{i}] is {type(record).__name__!r}, "
                    f"expected PromotionRecord instance"
                )
        # Deterministic, deduplicated ordering on diagnosis_incident_ids
        # is enforced at construction time so projection telemetry
        # never has to re-sort.
        object.__setattr__(
            self,
            "diagnosis_incident_ids",
            _stable_unique(self.diagnosis_incident_ids),
        )

    @property
    def canonical_incident_count(self) -> int:
        """Number of canonical diagnosis IDs that survive dedupe."""
        return len(self.diagnosis_incident_ids)


@dataclass(frozen=True, slots=True)
class PromotionRejected:
    """Promotion is known not to have committed.

    Diagnosis MUST NOT consume IDs from this outcome. Reconciliation
    is not required because nothing was committed.
    """

    run_id: str
    reason: PromotionRejectionCode
    rejected_signal_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("PromotionRejected requires a run_id")


@dataclass(frozen=True, slots=True)
class PromotionCommitUnknown:
    """Promotion commit status could not be determined.

    The caller MUST reconcile before a later diagnosis handoff may
    proceed. Diagnosis MUST NOT dispatch from this outcome variant.

    The :class:`PromotionReconciliationToken` is the only
    authoritative bridge to a reconciliation attempt.

    ``requested_signal_ids`` is carried on every commit-unknown
    outcome so the request-fidelity telemetry
    (``requested_signal_count``) is non-zero for any real attempt.
    """

    run_id: str
    reason: PromotionUncertaintyCode
    reconciliation_token: PromotionReconciliationToken
    requested_signal_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("PromotionCommitUnknown requires a run_id")
        if self.reconciliation_token is None:
            raise ValueError(
                "PromotionCommitUnknown requires a non-None reconciliation_token"
            )


# Closed union -- exhaustively matched where used.
PromotionOutcome = PromotionSucceeded | PromotionRejected | PromotionCommitUnknown


def is_succeeded(outcome: PromotionOutcome) -> bool:
    """Return True iff the outcome is :class:`PromotionSucceeded`."""
    return isinstance(outcome, PromotionSucceeded)


def is_rejected(outcome: PromotionOutcome) -> bool:
    """Return True iff the outcome is :class:`PromotionRejected`."""
    return isinstance(outcome, PromotionRejected)


def is_commit_unknown(outcome: PromotionOutcome) -> bool:
    """Return True iff the outcome is :class:`PromotionCommitUnknown`."""
    return isinstance(outcome, PromotionCommitUnknown)


def may_have_committed(outcome: PromotionOutcome) -> bool:
    """Project ``promotion_may_have_committed`` from the outcome variant.

    * Success -> true (authoritatively known to have committed).
    * Rejection -> false (authoritatively known not to have committed).
    * Commit unknown -> true (caller cannot prove either direction).

    The earlier definition returned ``is_commit_unknown(outcome)`` which
    incorrectly reported ``False`` for :class:`PromotionSucceeded`.
    The name says "may have committed" -- a confirmed success either
    committed or completed authoritatively and the boolean is
    truthfully ``True``. A confirmed rejection truthfully reports
    ``False`` because no commit happened. A commit-unknown result
    cannot prove either direction, so it is ``True``.

    These three projections are consistent across the seam and are the
    ONLY allowed way to set ``promotion_may_have_committed``.
    """
    return is_succeeded(outcome) or is_commit_unknown(outcome)


def propagation_available(outcome: PromotionOutcome) -> bool:
    """Project ``promotion_propagated_to_diagnosis`` from the outcome.

    This projection means "the typed outcome permits propagation to
    diagnosis", NOT "diagnosis has actually consumed the IDs". A
    later audit must distinguish the two with a separate field.

    Only :class:`PromotionSucceeded` permits downstream diagnosis
    propagation. Rejection and commit-unknown both fail closed.
    """
    return is_succeeded(outcome)


def consistency_error_recorded(outcome: PromotionOutcome) -> bool:
    """Project ``promotion_consistency_error_recorded`` from the outcome.

    This is true only for outcomes whose consistency status warrants
    explicit operator reporting (rejection and commit unknown).
    Successful promotion reports ``False`` here.
    """
    return isinstance(outcome, (PromotionRejected, PromotionCommitUnknown))


def _stable_unique(
    values: tuple[str, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


__all__ = [
    "PromotionCommitUnknown",
    "PromotionOutcome",
    "PromotionReconciliationToken",
    "PromotionRejected",
    "PromotionRejectionCode",
    "PromotionSucceeded",
    "PromotionUncertaintyCode",
    "consistency_error_recorded",
    "is_commit_unknown",
    "is_rejected",
    "is_succeeded",
    "may_have_committed",
    "propagation_available",
]