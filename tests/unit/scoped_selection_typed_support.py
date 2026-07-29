"""Shared typed-fixture construction for the scoped selection suite.

ACT-K9B-HULK-PROMOTION-SELECTION-SUITE-RESPONSIBILITY-SPLIT01.

This module is the single owner of the canonical closed-union
builders that every focused scoped-selection test file uses.
The builders emit the production-shaped ``records=()`` complete
aggregate result -- the receipt is the only authority for the
aggregate zero / actionable IDs / commit-unknown / rejected
selection paths. No fixture in this suite fabricates
``PromotionRecord`` instances, ``<scoped:...>`` synthetic source
candidate identifiers, or per-signal outcome evidence; the
canonical aggregate-proof shape carries an empty
``records`` tuple.

The module is intentionally limited to builders and helpers -- NO
test functions live here. The split layout prevents the support
module from drifting into the test-class boundary.
"""

from __future__ import annotations

from typing import Any

from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionCompletedProjection,
    ScopedPromotionReceipt,
    ScopedPromotionRejectedProjection,
    ScopedPromotionUncertainProjection,
)

DEFAULT_RUN_ID = "health-run-typed-handoff-001"
DEFAULT_REQUEST_ID_COMPLETED = "promotion-request-completed-001"
DEFAULT_REQUEST_ID_UNCERTAIN = "promotion-request-uncertain-001"
DEFAULT_REQUEST_ID_REJECTED = "promotion-request-rejected-001"
DEFAULT_REQUEST_FINGERPRINT_COMPLETED = "a" * 64
DEFAULT_REQUEST_FINGERPRINT_UNCERTAIN = "b" * 64
DEFAULT_REQUEST_FINGERPRINT_REJECTED = "c" * 64


def _build_bound(
    *,
    run_id: str,
    requested_signal_ids: tuple[str, ...],
    diagnosis_incident_ids: tuple[str, ...],
) -> Any:
    """Build a :class:`BoundScopedPromotionResult` for the receipt.

    The receipt is the only authority for the canonical aggregate
    scoped result; the builder keeps the construction in one
    place so the focused test files can compose the closed union
    without duplicating the binding logic.
    """
    from k8s_diag_agent.domain.identifiers import AlertSignalId
    from k8s_diag_agent.domain.incident_lifecycle import IncidentId
    from k8s_diag_agent.incident_alert_promotion_binding import (
        BoundScopedPromotionResult,
    )
    from k8s_diag_agent.incident_alert_promotion_contract import (
        IncidentPromotionResult,
        PromoteAlertSignalsRequest,
    )

    typed_signal_ids = tuple(
        AlertSignalId(value) for value in requested_signal_ids
    )
    opened_incident_ids = tuple(
        IncidentId(value) for value in diagnosis_incident_ids
    )
    success = IncidentPromotionResult(
        run_id=run_id,
        source_identity="source-test",
        scanned_signal_ids=typed_signal_ids,
        opened_incident_ids=opened_incident_ids,
    )
    return BoundScopedPromotionResult(
        request=PromoteAlertSignalsRequest(
            run_id=run_id,
            source_identity="source-test",
            signal_ids=typed_signal_ids,
        ),
        result=success,
    )


def default_requested_signal_ids(
    count: int = 34,
) -> tuple[str, ...]:
    """Return the canonical 34-signal fixture used by every
    scoped selection test.

    The number is the production-shaped requested-signal count
    the active dispatcher derives from the canonical
    ``PromoteAlertSignalsRequest`` workset.
    """
    return tuple(f"sig-{i:02d}" for i in range(count))


def build_completed_projection(
    *,
    run_id: str = DEFAULT_RUN_ID,
    requested_signal_ids: tuple[str, ...] = default_requested_signal_ids(),
    diagnosis_incident_ids: tuple[str, ...] = (),
) -> ScopedPromotionCompletedProjection:
    """Build a typed completed projection.

    The canonical aggregate ``records`` tuple is ALWAYS empty --
    the receipt is the only authority. ``diagnosis_incident_ids``
    may be empty (the aggregate-successful-zero case) or non-empty
    (the aggregate-with-actionable-IDs case). The defaults mirror
    the production-shaped requested-signal count.
    """
    bound_obj = _build_bound(
        run_id=run_id,
        requested_signal_ids=requested_signal_ids,
        diagnosis_incident_ids=diagnosis_incident_ids,
    )
    return ScopedPromotionCompletedProjection(
        promotion_outcome=PromotionSucceeded(
            run_id=run_id,
            requested_signal_ids=requested_signal_ids,
            records=(),
            diagnosis_incident_ids=diagnosis_incident_ids,
        ),
        aggregate_receipt=ScopedPromotionReceipt(bound=bound_obj),
        request_id=DEFAULT_REQUEST_ID_COMPLETED,
        request_fingerprint=DEFAULT_REQUEST_FINGERPRINT_COMPLETED,
    )


def build_uncertain_projection(
    *,
    run_id: str = DEFAULT_RUN_ID,
    requested_signal_ids: tuple[str, ...] = default_requested_signal_ids(),
) -> ScopedPromotionUncertainProjection:
    """Build a typed uncertain projection.

    The ``reconciliation_token`` carries the canonical
    request id and request fingerprint for the uncertain
    outcome; the projection re-asserts the same pair at
    the projection level so the accumulator receives
    identity-preserved values.
    """
    return ScopedPromotionUncertainProjection(
        promotion_outcome=PromotionCommitUnknown(
            run_id=run_id,
            reason=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
            reconciliation_token=PromotionReconciliationToken(
                request_id=DEFAULT_REQUEST_ID_UNCERTAIN,
                request_fingerprint=DEFAULT_REQUEST_FINGERPRINT_UNCERTAIN,
            ),
            requested_signal_ids=requested_signal_ids,
        ),
        request_id=DEFAULT_REQUEST_ID_UNCERTAIN,
        request_fingerprint=DEFAULT_REQUEST_FINGERPRINT_UNCERTAIN,
    )


def build_rejected_projection(
    *,
    run_id: str = DEFAULT_RUN_ID,
    requested_signal_ids: tuple[str, ...] = default_requested_signal_ids(),
) -> ScopedPromotionRejectedProjection:
    """Build a typed rejected projection."""
    return ScopedPromotionRejectedProjection(
        promotion_outcome=PromotionRejected(
            run_id=run_id,
            reason=PromotionRejectionCode.BACKEND_UNREACHABLE,
            rejected_signal_ids=requested_signal_ids,
        ),
        request_id=DEFAULT_REQUEST_ID_REJECTED,
        request_fingerprint=DEFAULT_REQUEST_FINGERPRINT_REJECTED,
    )


__all__ = [
    "DEFAULT_REQUEST_FINGERPRINT_COMPLETED",
    "DEFAULT_REQUEST_FINGERPRINT_REJECTED",
    "DEFAULT_REQUEST_FINGERPRINT_UNCERTAIN",
    "DEFAULT_REQUEST_ID_COMPLETED",
    "DEFAULT_REQUEST_ID_REJECTED",
    "DEFAULT_REQUEST_ID_UNCERTAIN",
    "DEFAULT_RUN_ID",
    "build_completed_projection",
    "build_rejected_projection",
    "build_uncertain_projection",
    "default_requested_signal_ids",
]


# ``PromotionCommitDisposition`` re-exported so focused test
# files can assert identity without reaching into the
# ``promotion_outcomes`` module directly.
_ = PromotionCommitDisposition
