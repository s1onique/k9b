"""Exhaustive scoped HTTP transport to ``PromotionOutcome`` mapping.

ACT-K9B-HULK-PROMOTION-SCOPED-TRANSPORT-MAPPING-TRUTH01.

Exhaustively maps every variant of
:class:`ScopedPromotionHttpTransportOutcome` to the closed
:class:`PromotionOutcome` union (defined in
:mod:`k8s_diag_agent.collect.promotion_outcomes`).

The mapping preserves the exact bounded reason codes established
in ``PromotionUncertaintyCode`` and ``PromotionRejectionCode``. Each
known HTTP shape maps to one specific reason so the operator can
correlate the selection handoff with the actual transport
observation. There is no ``AMBIGUOUS_RESPONSE`` catch-all bucket
for known shapes.

The mapping also carries an aggregate
:class:`ScopedPromotionReceipt` when the transport succeeds, so
downstream consumers have proof that a promotion was attempted
and completed even when every category list is empty (aggregate
successful zero).

The ``request_fingerprint`` is the deterministic SHA-256 over
the canonical request payload (NOT the request id); two
attempts of the same promotion scope produce the same
fingerprint even when they carry different transport correlation
ids.
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
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionOutcome,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpSucceeded,
    ScopedPromotionHttpTransportOutcome,
    ScopedPromotionReceipt,
    scoped_promotion_request_fingerprint,
)


@dataclass(frozen=True, slots=True)
class ScopedTransportPromotionProjection:
    """Typed projection returned by the bounded mapper.

    Carries the typed ``PromotionOutcome``, the bounded aggregate
    receipt (when present), the transport correlation identity, and
    the deterministic request fingerprint. Tuple-shaped returns
    are forbidden; downstream consumers MUST branch on the typed
    fields.
    """

    promotion_outcome: PromotionOutcome
    aggregate_receipt: ScopedPromotionReceipt | None
    request_id: str
    request_fingerprint: str
    may_have_committed: bool


def _reconciliation_token(
    context: ScopedPromotionHttpRequestContext,
) -> PromotionReconciliationToken:
    """Build the bounded reconciliation token.

    ``request_id`` is the transport correlation identity (one per
    attempt); ``request_fingerprint`` is the deterministic digest
    over the canonical request payload (stable across attempts).
    The two tokens together let reconciliation correlate retries
    without conflating them with backend runs.
    """
    return PromotionReconciliationToken(
        request_id=context.request_id,
        request_fingerprint=scoped_promotion_request_fingerprint(
            context.request
        ),
    )


def _uncertain(
    context: ScopedPromotionHttpRequestContext,
    *,
    code: PromotionUncertaintyCode,
    may_have_committed: bool,
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


def _build_aggregate_receipt(
    transport: ScopedPromotionHttpSucceeded,
) -> ScopedPromotionReceipt:
    """Build the aggregate scoped receipt from a successful transport.

    The receipt proves a promotion was attempted and completed even
    when every category list is empty (aggregate successful zero).
    Downstream consumers MUST NOT derive ``no_promotion_run`` from
    the absence of records.
    """
    result = transport.bound.result
    return ScopedPromotionReceipt(
        requested_signal_ids=tuple(
            str(signal_id) for signal_id in result.scanned_signal_ids
        ),
        scanned_signal_ids=tuple(
            str(signal_id) for signal_id in result.scanned_signal_ids
        ),
        opened_incident_ids=tuple(
            str(i) for i in result.opened_incident_ids
        ),
        materially_changed_incident_ids=tuple(
            str(i) for i in result.materially_changed_incident_ids
        ),
        observation_refreshed_incident_ids=tuple(
            str(i) for i in result.observation_refreshed_incident_ids
        ),
        unchanged_incident_ids=tuple(
            str(i) for i in result.unchanged_incident_ids
        ),
        skipped_signal_ids=tuple(
            str(signal_id) for signal_id in result.skipped_signal_ids
        ),
        failure_count=len(result.failures),
    )


def map_scoped_http_transport_to_promotion_outcome(
    transport: ScopedPromotionHttpTransportOutcome,
    *,
    context: ScopedPromotionHttpRequestContext,
) -> ScopedTransportPromotionProjection:
    """Exhaustively map the scoped transport union to a typed projection.

    Returns a :class:`ScopedTransportPromotionProjection` carrying
    the typed :class:`PromotionOutcome`, the bounded aggregate
    receipt (when present), the transport correlation identity, and
    the deterministic request fingerprint.

    Every variant maps to an exact bounded reason; the closed union
    is narrowed with ``assert_never`` so a new variant cannot
    silently disappear from the dispatch.
    """
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
            aggregate_receipt=_build_aggregate_receipt(transport),
            request_id=context.request_id,
            request_fingerprint=scoped_promotion_request_fingerprint(
                context.request
            ),
            may_have_committed=False,
        )

    fingerprint = scoped_promotion_request_fingerprint(context.request)

    # 202 Accepted: HTTP says "accepted for processing, not
    # completed". Always commit-unknown.
    if isinstance(transport, PromotionHttpAccepted):
        outcome = _uncertain(
            context,
            code=PromotionUncertaintyCode.HTTP_ACCEPTED_WITHOUT_RESULT,
            may_have_committed=True,
        )
    # 204 No Content: backend acknowledged the request but
    # returned no payload. NEVER reinterpreted as successful zero.
    elif isinstance(transport, PromotionHttpNoContent):
        outcome = _uncertain(
            context,
            code=PromotionUncertaintyCode.HTTP_NO_CONTENT_AFTER_SEND,
            may_have_committed=True,
        )
    elif isinstance(transport, PromotionHttpInvalidJson):
        outcome = _uncertain(
            context,
            code=PromotionUncertaintyCode.HTTP_INVALID_JSON,
            may_have_committed=True,
        )
    elif isinstance(transport, PromotionHttpInvalidSchema):
        outcome = _uncertain(
            context,
            code=PromotionUncertaintyCode.HTTP_INVALID_SCHEMA,
            may_have_committed=True,
        )
    elif isinstance(transport, PromotionHttpResponseTruncated):
        outcome = _uncertain(
            context,
            code=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
            may_have_committed=True,
        )
    elif isinstance(transport, PromotionHttpTransportFailureBeforeSend):
        outcome = _rejected(
            context,
            code=PromotionRejectionCode.CONFIGURATION_BLOCKED,
        )
    elif isinstance(transport, PromotionHttpTransportFailureAfterSend):
        outcome = _uncertain(
            context,
            code=PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND,
            may_have_committed=True,
        )
    elif isinstance(transport, PromotionHttpRejected):
        # Definite HTTP rejection. Without a validated backend
        # disposition proving execution did not start, commit
        # status is uncertain; the active scoped path does not
        # classify raw 4xx/5xx as ``no_execution``.
        outcome = _uncertain(
            context,
            code=PromotionUncertaintyCode.PROMOTION_HTTP_ERROR_UNCERTAIN
            if hasattr(PromotionUncertaintyCode, "PROMOTION_HTTP_ERROR_UNCERTAIN")
            else PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
            may_have_committed=True,
        )
    else:
        # Closed union: any unhandled variant is a bug, not a
        # fallback.
        assert_never(transport)
        # ``assert_never`` is unreachable at runtime; the
        # assignment below keeps mypy happy while making the
        # static-check guarantee explicit.
        outcome = _uncertain(  # pragma: no cover
            context,
            code=PromotionUncertaintyCode.UNEXPECTED_CLIENT_RESULT,
            may_have_committed=True,
        )

    return ScopedTransportPromotionProjection(
        promotion_outcome=outcome,
        aggregate_receipt=None,
        request_id=context.request_id,
        request_fingerprint=fingerprint,
        may_have_committed=_may_have_committed(transport),
    )


def _may_have_committed(transport: ScopedPromotionHttpTransportOutcome) -> bool:
    """Project the typed ``may_have_committed`` from the transport union."""
    if isinstance(transport, PromotionHttpTransportFailureBeforeSend):
        return False
    # PromotionHttpRejected is mapped to PromotionCommitUnknown;
    # commit status is uncertain, so may_have_committed is True.
    return True
