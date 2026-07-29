"""Exhaustive scoped HTTP transport to ``PromotionOutcome`` mapping.

ACT-K9B-HULK-PROMOTION-SCOPED-TRANSPORT-MAPPING-TRUTH01-CORRECTION01.

Exhaustively maps every variant of
:class:`ScopedPromotionHttpTransportOutcome` to the closed
:class:`PromotionOutcome` union with the bounded commit
disposition.

The mapping preserves the exact bounded reason codes established
in ``PromotionUncertaintyCode`` and ``PromotionRejectionCode``. Each
known HTTP shape maps to one specific reason so the operator can
correlate the selection handoff with the actual transport
observation. There is no ``AMBIGUOUS_RESPONSE`` catch-all bucket
for known shapes.

The mapping also carries an aggregate
:class:`ScopedPromotionReceipt` (constructed via
:meth:`ScopedPromotionReceipt.from_bound_result`) when the
transport succeeds, so downstream consumers have proof that a
promotion was attempted and completed even when every category
list is empty (aggregate successful zero).

The ``commit_disposition`` field on the projection is a closed
:class:`PromotionCommitDisposition` value, NOT an ambiguous
boolean. A compatibility property exposes the legacy
``may_have_committed`` boolean where required.
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
    PromotionOutcome,
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
    scoped_promotion_request_fingerprint,
)


@dataclass(frozen=True, slots=True)
class ScopedTransportPromotionProjection:
    """Typed projection returned by the bounded mapper.

    The aggregate receipt is the single authority for the
    derived fields; consumers MUST branch on the typed fields
    and MUST NOT reconstruct copy-state by hand.
    """

    promotion_outcome: PromotionOutcome
    aggregate_receipt: ScopedPromotionReceipt
    request_id: str
    request_fingerprint: str
    commit_disposition: PromotionCommitDisposition

    @property
    def may_have_committed(self) -> bool:
        """Legacy compatibility property. New decision logic MUST
        branch on :attr:`commit_disposition` instead.
        """
        return self.commit_disposition is not (
            PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
        )

    @property
    def requires_reconciliation(self) -> bool:
        """``True`` only when commit status is MAY_HAVE_COMMITTED.

        Both ``DEFINITELY_COMMITTED`` (success) and
        ``DEFINITELY_NOT_COMMITTED`` (pre-send failure / auth
        rejection) return ``False`` -- only the uncertain path
        requires reconciliation.
        """
        return self.commit_disposition is (
            PromotionCommitDisposition.MAY_HAVE_COMMITTED
        )


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
) -> PromotionOutcome:
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
) -> PromotionOutcome:
    return PromotionRejected(
        run_id=str(context.request.run_id),
        reason=code,
        rejected_signal_ids=tuple(
            str(signal_id) for signal_id in context.request.signal_ids
        ),
    )


def _commit_disposition(
    transport: ScopedPromotionHttpTransportOutcome,
) -> PromotionCommitDisposition:
    """Project the typed commit disposition from the transport union."""
    if isinstance(transport, ScopedPromotionHttpSucceeded):
        return PromotionCommitDisposition.DEFINITELY_COMMITTED
    if isinstance(transport, PromotionHttpTransportFailureBeforeSend):
        return PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
    if isinstance(transport, ScopedPromotionHttpAuthenticationRejected):
        return PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
    return PromotionCommitDisposition.MAY_HAVE_COMMITTED


def map_scoped_http_transport_to_promotion_outcome(
    transport: ScopedPromotionHttpTransportOutcome,
    *,
    context: ScopedPromotionHttpRequestContext,
) -> ScopedTransportPromotionProjection:
    """Exhaustively map the scoped transport union to a typed projection.

    Every variant maps to an exact bounded reason; the closed
    union is narrowed with ``assert_never`` so a new variant
    cannot silently disappear from the dispatch.
    """
    fingerprint = scoped_promotion_request_fingerprint(context.request)
    disposition = _commit_disposition(transport)

    if isinstance(transport, ScopedPromotionHttpSucceeded):
        bound = transport.bound
        actionable = tuple(
            str(i) for i in bound.actionable_incident_ids
        )
        outcome = PromotionSucceeded(
            run_id=str(context.request.run_id),
            requested_signal_ids=tuple(
                str(signal_id) for signal_id in context.request.signal_ids
            ),
            records=(),
            diagnosis_incident_ids=actionable,
        )
        return ScopedTransportPromotionProjection(
            promotion_outcome=outcome,
            aggregate_receipt=ScopedPromotionReceipt.from_bound_result(
                bound
            ),
            request_id=context.request_id,
            request_fingerprint=fingerprint,
            commit_disposition=disposition,
        )

    # Distinct body-read reasons preserved at the domain layer.
    if isinstance(transport, ScopedPromotionHttpBodyLimitExceeded):
        outcome = _commit_unknown(
            context,
            code=PromotionUncertaintyCode.HTTP_RESPONSE_BODY_LIMIT_EXCEEDED,
        )
    elif isinstance(transport, ScopedPromotionHttpShortRead):
        outcome = _commit_unknown(
            context,
            code=PromotionUncertaintyCode.HTTP_RESPONSE_SHORT_READ,
        )
    elif isinstance(transport, ScopedPromotionHttpReadFailed):
        # Read failure AFTER response headers were received.
        # The body MAY have been acknowledged by the backend.
        outcome = _commit_unknown(
            context,
            code=PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND,
        )
    # Authentication rejection is distinct from generic HTTP
    # error: 401 / 403 prove no execution could begin.
    elif isinstance(transport, ScopedPromotionHttpAuthenticationRejected):
        outcome = _rejected(
            context,
            code=PromotionRejectionCode.AUTHENTICATION_REJECTED,
        )
    elif isinstance(transport, PromotionHttpAccepted):
        outcome = _commit_unknown(
            context,
            code=PromotionUncertaintyCode.HTTP_ACCEPTED_WITHOUT_RESULT,
        )
    elif isinstance(transport, PromotionHttpNoContent):
        outcome = _commit_unknown(
            context,
            code=PromotionUncertaintyCode.HTTP_NO_CONTENT_AFTER_SEND,
        )
    elif isinstance(transport, PromotionHttpInvalidJson):
        outcome = _commit_unknown(
            context,
            code=PromotionUncertaintyCode.HTTP_INVALID_JSON,
        )
    elif isinstance(transport, PromotionHttpInvalidSchema):
        outcome = _commit_unknown(
            context,
            code=PromotionUncertaintyCode.HTTP_INVALID_SCHEMA,
        )
    elif isinstance(transport, PromotionHttpResponseTruncated):
        outcome = _commit_unknown(
            context,
            code=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
        )
    elif isinstance(transport, PromotionHttpTransportFailureAfterSend):
        outcome = _commit_unknown(
            context,
            code=PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND,
        )
    elif isinstance(transport, PromotionHttpTransportFailureBeforeSend):
        # Before-send failure preserves its typed reason. The client
        # attaches ``PromotionHttpTransportReasonCode`` so we branch
        # on that reason to distinguish configuration from
        # unreachable.
        reason_code = transport.reason_code
        if reason_code in {
            PromotionHttpTransportReasonCode.HTTP_FAILURE_BEFORE_SEND,
        }:
            outcome = _rejected(
                context,
                code=PromotionRejectionCode.CONFIGURATION_BLOCKED,
            )
        else:
            outcome = _rejected(
                context,
                code=PromotionRejectionCode.BACKEND_UNREACHABLE,
            )
    elif isinstance(transport, PromotionHttpRejected):
        outcome = _commit_unknown(
            context,
            code=PromotionUncertaintyCode.PROMOTION_HTTP_ERROR_UNCERTAIN,
        )
    else:
        # Closed union: any unhandled variant is a bug, not a
        # fallback. ``assert_never`` raises at runtime and the
        # static type checker rejects a reachable argument.
        assert_never(transport)

    return ScopedTransportPromotionProjection(
        promotion_outcome=outcome,
        aggregate_receipt=None,
        request_id=context.request_id,
        request_fingerprint=fingerprint,
        commit_disposition=disposition,
    )
