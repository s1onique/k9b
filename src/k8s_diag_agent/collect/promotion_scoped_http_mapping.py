"""Exhaustive scoped HTTP transport to ``PromotionOutcome`` mapping.

ACT-K9B-HULK-PROMOTION-SCOPED-MAPPING-PROJECTION-AND-REACHABILITY-CLOSURE01.

Exhaustively maps every variant of
:class:`ScopedPromotionHttpTransportOutcome` to the closed
:class:`PromotionOutcome` union with the bounded commit
disposition.

The projection algebra is closed: every variant carries a
distinct combination of outcome / receipt presence / disposition
that is unrepresentable in the other variants. Only the
completed projection carries an aggregate receipt. Uncertain and
rejected projections carry no receipt; the receipt cannot be
falsified for a failed attempt.

The mapping preserves the exact bounded reason codes established
in ``PromotionUncertaintyCode`` and ``PromotionRejectionCode``. Each
known HTTP shape maps to one specific reason so the operator can
correlate the selection handoff with the actual transport
observation. There is no ``AMBIGUOUS_RESPONSE`` catch-all bucket
for known shapes.

The deterministic SHA-256 request fingerprint is the stable
half of ``PromotionReconciliationToken``; the request id is the
transport half. ``request_id`` is NEVER used as the fingerprint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpAccepted,
    PromotionHttpInvalidJson,
    PromotionHttpInvalidSchema,
    PromotionHttpNoContent,
    PromotionHttpRejected,
    PromotionHttpResponseTruncated,
    PromotionHttpTransportFailureAfterSend,
    PromotionHttpTransportFailureBeforeSend,
    PromotionHttpTransportReasonCode,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpAuthenticationRejected,
    ScopedPromotionHttpBodyLimitExceeded,
    ScopedPromotionHttpReadFailed,
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpShortRead,
    ScopedPromotionHttpSucceeded,
    ScopedPromotionHttpTransportOutcome,
    ScopedPromotionReceipt,
    ScopedReadFailureReason,
    scoped_promotion_request_fingerprint,
)

# ---------------------------------------------------------------------------
# Closed projection algebra
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScopedPromotionCompletedProjection:
    """A completed promotion carries the aggregate receipt.

    ``DEFINITELY_COMMITTED`` is the only disposition for this
    projection variant; a receipt cannot be constructed without
    a valid bound.
    """

    promotion_outcome: PromotionSucceeded
    aggregate_receipt: ScopedPromotionReceipt
    request_id: str
    request_fingerprint: str

    @property
    def commit_disposition(self) -> PromotionCommitDisposition:
        return PromotionCommitDisposition.DEFINITELY_COMMITTED

    @property
    def requires_reconciliation(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ScopedPromotionUncertainProjection:
    """An uncertain projection carries NO receipt.

    ``MAY_HAVE_COMMITTED`` is the only disposition for this
    projection variant; reconciliation is required.
    """

    promotion_outcome: PromotionCommitUnknown
    request_id: str
    request_fingerprint: str

    @property
    def commit_disposition(self) -> PromotionCommitDisposition:
        return PromotionCommitDisposition.MAY_HAVE_COMMITTED

    @property
    def requires_reconciliation(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class ScopedPromotionRejectedProjection:
    """A rejected projection carries NO receipt.

    ``DEFINITELY_NOT_COMMITTED`` is the only disposition for this
    projection variant; the bound failed before any mutation could
    occur.
    """

    promotion_outcome: PromotionRejected
    request_id: str
    request_fingerprint: str

    @property
    def commit_disposition(self) -> PromotionCommitDisposition:
        return PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED

    @property
    def requires_reconciliation(self) -> bool:
        return False


# Closed union -- each variant is unrepresentable in the others.
ScopedTransportPromotionProjection = (
    ScopedPromotionCompletedProjection
    | ScopedPromotionUncertainProjection
    | ScopedPromotionRejectedProjection
)


# ---------------------------------------------------------------------------
# Compatibility helpers
# ---------------------------------------------------------------------------


def projection_commit_disposition(
    projection: ScopedTransportPromotionProjection,
) -> PromotionCommitDisposition:
    """Return the typed commit disposition for any projection variant."""
    return projection.commit_disposition


def projection_requires_reconciliation(
    projection: ScopedTransportPromotionProjection,
) -> bool:
    """Return whether the projection requires reconciliation."""
    return projection.requires_reconciliation


def projection_request_id(
    projection: ScopedTransportPromotionProjection,
) -> str:
    """Return the transport correlation identity."""
    return projection.request_id


def projection_request_fingerprint(
    projection: ScopedTransportPromotionProjection,
) -> str:
    """Return the deterministic request fingerprint."""
    return projection.request_fingerprint


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------


def _reconciliation_token(
    context: ScopedPromotionHttpRequestContext,
) -> PromotionReconciliationToken:
    """Build the bounded reconciliation token."""
    return PromotionReconciliationToken(
        request_id=context.request_id,
        request_fingerprint=scoped_promotion_request_fingerprint(
            context.request
        ),
    )


def _commit_unknown(
    context: ScopedPromotionHttpRequestContext,
    *,
    code: PromotionUncertaintyCode,
) -> PromotionCommitUnknown:
    return PromotionCommitUnknown(
        run_id=str(context.request.run_id),
        reason=code,
        reconciliation_token=_reconciliation_token(context),
        requested_signal_ids=tuple(
            str(signal_id) for signal_id in context.request.signal_ids
        ),
    )


def _rejected(
    context: ScopedPromotionHttpRequestContext,
    *,
    code: PromotionRejectionCode,
) -> PromotionRejected:
    return PromotionRejected(
        run_id=str(context.request.run_id),
        reason=code,
        rejected_signal_ids=tuple(
            str(signal_id) for signal_id in context.request.signal_ids
        ),
    )


def _fingerprint(
    context: ScopedPromotionHttpRequestContext,
) -> str:
    fp: str = scoped_promotion_request_fingerprint(context.request)
    return fp


def map_scoped_http_transport_to_promotion_outcome(
    transport: ScopedPromotionHttpTransportOutcome,
    *,
    context: ScopedPromotionHttpRequestContext,
) -> ScopedTransportPromotionProjection:
    """Exhaustively map the scoped transport union to a typed projection.

    Returns a closed :class:`ScopedTransportPromotionProjection`
    variant. Only the completed projection carries an aggregate
    receipt. The closed union is narrowed with ``assert_never`` so a
    new variant cannot silently disappear from the dispatch.
    """
    fingerprint = _fingerprint(context)

    if isinstance(transport, ScopedPromotionHttpSucceeded):
        return ScopedPromotionCompletedProjection(
            promotion_outcome=PromotionSucceeded(
                run_id=str(context.request.run_id),
                requested_signal_ids=tuple(
                    str(signal_id)
                    for signal_id in context.request.signal_ids
                ),
                records=(),
                diagnosis_incident_ids=tuple(
                    str(i)
                    for i in transport.bound.actionable_incident_ids
                ),
            ),
            aggregate_receipt=ScopedPromotionReceipt(
                bound=transport.bound
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )

    if isinstance(transport, ScopedPromotionHttpBodyLimitExceeded):
        return ScopedPromotionUncertainProjection(
            promotion_outcome=_commit_unknown(
                context,
                code=(
                    PromotionUncertaintyCode
                    .HTTP_RESPONSE_BODY_LIMIT_EXCEEDED
                ),
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )
    if isinstance(transport, ScopedPromotionHttpShortRead):
        return ScopedPromotionUncertainProjection(
            promotion_outcome=_commit_unknown(
                context,
                code=PromotionUncertaintyCode.HTTP_RESPONSE_SHORT_READ,
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )
    if isinstance(transport, ScopedPromotionHttpReadFailed):
        # Exhaustive matching over the closed read-failure reason
        # vocabulary. No silent timeout fallback.
        if transport.reason_code == ScopedReadFailureReason.TIMEOUT:
            code = PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND
        elif (
            transport.reason_code == ScopedReadFailureReason.CONNECTION_LOST
        ):
            code = (
                PromotionUncertaintyCode
                .HTTP_CONNECTION_LOST_AFTER_SEND
            )
        else:
            assert_never(transport.reason_code)
            code = PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND
        return ScopedPromotionUncertainProjection(
            promotion_outcome=_commit_unknown(context, code=code),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )

    if isinstance(transport, ScopedPromotionHttpAuthenticationRejected):
        # 401 / 403 prove no promotion execution could begin.
        # ``DEFINITELY_NOT_COMMITTED`` is the only valid disposition.
        return ScopedPromotionRejectedProjection(
            promotion_outcome=_rejected(
                context,
                code=PromotionRejectionCode.AUTHENTICATION_REJECTED,
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )

    if isinstance(transport, PromotionHttpAccepted):
        return ScopedPromotionUncertainProjection(
            promotion_outcome=_commit_unknown(
                context,
                code=PromotionUncertaintyCode.HTTP_ACCEPTED_WITHOUT_RESULT,
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )
    if isinstance(transport, PromotionHttpNoContent):
        return ScopedPromotionUncertainProjection(
            promotion_outcome=_commit_unknown(
                context,
                code=PromotionUncertaintyCode.HTTP_NO_CONTENT_AFTER_SEND,
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )
    if isinstance(transport, PromotionHttpInvalidJson):
        return ScopedPromotionUncertainProjection(
            promotion_outcome=_commit_unknown(
                context,
                code=PromotionUncertaintyCode.HTTP_INVALID_JSON,
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )
    if isinstance(transport, PromotionHttpInvalidSchema):
        return ScopedPromotionUncertainProjection(
            promotion_outcome=_commit_unknown(
                context,
                code=PromotionUncertaintyCode.HTTP_INVALID_SCHEMA,
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )
    if isinstance(transport, PromotionHttpResponseTruncated):
        return ScopedPromotionUncertainProjection(
            promotion_outcome=_commit_unknown(
                context,
                code=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )
    if isinstance(transport, PromotionHttpTransportFailureAfterSend):
        # Exhaustive matching over the closed transport reason
        # vocabulary. No silent timeout fallback.
        if transport.reason_code == (
            PromotionHttpTransportReasonCode.HTTP_READ_TIMEOUT_AFTER_SEND
        ):
            code = PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND
        elif transport.reason_code == (
            PromotionHttpTransportReasonCode
            .HTTP_CONNECTION_LOST_AFTER_SEND
        ):
            code = (
                PromotionUncertaintyCode
                .HTTP_CONNECTION_LOST_AFTER_SEND
            )
        else:
            assert_never(transport.reason_code)
            code = PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND
        return ScopedPromotionUncertainProjection(
            promotion_outcome=_commit_unknown(context, code=code),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )
    if isinstance(transport, PromotionHttpTransportFailureBeforeSend):
        # Before-send failure preserves its typed reason:
        # configuration vs unreachable. The client attaches the
        # typed reason code so the mapper branches rather than
        # collapsing both into a single bucket.
        reason_code = transport.reason_code
        if reason_code == (
            PromotionHttpTransportReasonCode.HTTP_FAILURE_BEFORE_SEND
        ):
            code = PromotionRejectionCode.CONFIGURATION_BLOCKED
        else:
            code = PromotionRejectionCode.BACKEND_UNREACHABLE
        return ScopedPromotionRejectedProjection(
            promotion_outcome=_rejected(context, code=code),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )
    if isinstance(transport, PromotionHttpRejected):
        # Untyped HTTP error (400 / 409 / 429 / 5xx without validated
        # backend disposition): commit-unknown. A malformed 500 MUST
        # NOT produce the authentication variant.
        return ScopedPromotionUncertainProjection(
            promotion_outcome=_commit_unknown(
                context,
                code=(
                    PromotionUncertaintyCode
                    .PROMOTION_HTTP_ERROR_UNCERTAIN
                ),
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
        )

    # Closed union: any unhandled variant is a bug, not a
    # fallback. ``assert_never`` raises at runtime and the
    # static type checker rejects a reachable argument.
    assert_never(transport)
