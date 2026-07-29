"""Exhaustive scoped HTTP transport to ``PromotionOutcome`` mapping.

ACT-K9B-HULK-PROMOTION-SCOPED-DISPATCH-ACTIVATION-AND-CERTAINTY01-CORRECTION01.

Exhaustively maps every variant of
:class:`ScopedPromotionHttpTransportOutcome` to the closed
:class:`PromotionOutcome` union (defined in
:mod:`k8s_diag_agent.collect.promotion_outcomes`).

The mapping is closed and uses ``typing.assert_never`` so a newly
added variant cannot silently disappear from the dispatch. There
is no ``AMBIGUOUS_RESPONSE`` catch-all bucket for known shapes.

Mapping rules:

* ``ScopedPromotionHttpSucceeded`` (200 valid canonical body) ->
  ``PromotionSucceeded`` with the bound ``actionable_incident_ids``
  projected into ``diagnosis_incident_ids``.
  ``diagnosis_incident_ids=()`` (aggregate successful zero) is
  preserved as ``PromotionSucceeded`` -- NEVER collapsed into
  ``no_promotion_run``.
* ``accepted``, ``no content``, ``invalid JSON``,
  ``invalid schema``, body limit, short read, read failure,
  unknown transmission uncertainty ->
  ``PromotionCommitUnknown`` with the request id as the
  reconciliation token.
* Missing configuration, proven pre-send failure ->
  ``PromotionRejected``. Other HTTP errors are
  ``PromotionCommitUnknown`` until a validated backend disposition
  proves execution did not start.

The run id is taken from ``context.request.run_id`` and is the
domain identity used by the downstream selection / diagnosis.
"""

from __future__ import annotations

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
)


def _reconciliation_token(
    context: ScopedPromotionHttpRequestContext,
) -> PromotionReconciliationToken:
    """Build the bounded reconciliation token from the request id.

    The request id is the transport correlation identity; it is
    NOT a domain identity (never promoted to ``run_id``).
    """
    return PromotionReconciliationToken(
        request_id=context.request_id,
        request_fingerprint=context.request_id,
    )


def _uncertain(
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


def map_scoped_http_transport_to_promotion_outcome(
    transport: ScopedPromotionHttpTransportOutcome,
    *,
    context: ScopedPromotionHttpRequestContext,
) -> PromotionOutcome:
    """Exhaustively map the scoped transport union to PromotionOutcome."""
    if isinstance(transport, ScopedPromotionHttpSucceeded):
        bound = transport.bound
        actionable = tuple(
            str(i) for i in bound.actionable_incident_ids
        )
        return PromotionSucceeded(
            run_id=str(context.request.run_id),
            requested_signal_ids=tuple(
                str(signal_id) for signal_id in context.request.signal_ids
            ),
            records=(),
            diagnosis_incident_ids=actionable,
        )

    if isinstance(transport, PromotionHttpAccepted):
        return _uncertain(
            context,
            code=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
        )
    if isinstance(transport, PromotionHttpNoContent):
        return _uncertain(
            context,
            code=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
        )
    if isinstance(transport, PromotionHttpInvalidJson):
        return _uncertain(
            context,
            code=PromotionUncertaintyCode.WIRE_SCHEMA_MISMATCH,
        )
    if isinstance(transport, PromotionHttpInvalidSchema):
        return _uncertain(
            context,
            code=PromotionUncertaintyCode.WIRE_SCHEMA_MISMATCH,
        )
    if isinstance(transport, PromotionHttpResponseTruncated):
        return _uncertain(
            context,
            code=PromotionUncertaintyCode.WIRE_SCHEMA_MISMATCH,
        )
    if isinstance(transport, PromotionHttpTransportFailureBeforeSend):
        return _rejected(
            context,
            code=PromotionRejectionCode.BLOCKED,
        )
    if isinstance(transport, PromotionHttpTransportFailureAfterSend):
        return _uncertain(
            context,
            code=PromotionUncertaintyCode.WIRE_SCHEMA_MISMATCH,
        )
    if isinstance(transport, PromotionHttpRejected):
        return _uncertain(
            context,
            code=PromotionUncertaintyCode.WIRE_SCHEMA_MISMATCH,
        )

    # Closed union: any unhandled variant is a bug, not a fallback.
    assert_never(transport)
