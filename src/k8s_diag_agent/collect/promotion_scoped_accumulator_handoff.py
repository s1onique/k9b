"""Typed accumulator handoff for the scoped promotion path.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION01-FINALIZATION01.

This module is the single seam between the active scoped dispatcher
(:class:`ScopedPromotionDispatchResult`) and the run-scoped
:class:`RunPromotionAccumulator`. Every active scoped promotion
outcome MUST reach the accumulator through one of the closed
variants defined here. Legacy dictionaries and legacy
``promotion_records`` arrays MUST NOT cross this boundary.

The handoff is closed and exhaustive:

* :class:`ScopedPromotionAccumulatorCompleted` -- the dispatch
  produced a completed projection. The original
  :class:`PromotionSucceeded` outcome and the aggregate receipt
  are forwarded unchanged. The commit disposition is
  :attr:`PromotionCommitDisposition.DEFINITELY_COMMITTED`.

* :class:`ScopedPromotionAccumulatorUncertain` -- the dispatch
  produced an uncertain projection. The original
  :class:`PromotionCommitUnknown` outcome (with its reconciliation
  token) is forwarded unchanged. Receipt is structurally
  impossible: ``MAY_HAVE_COMMITTED``.

* :class:`ScopedPromotionAccumulatorRejected` -- the dispatch
  produced a rejected projection. The original
  :class:`PromotionRejected` outcome is forwarded unchanged.
  Receipt is structurally impossible:
  ``DEFINITELY_NOT_COMMITTED``.

The adapter :func:`scoped_dispatch_result_to_accumulator_handoff`
reuses every existing projection field by identity (``is``). No
field is reconstructed and no second ``PromotionOutcome`` is
synthesized.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from .promotion_outcomes import (
    PromotionCommitDisposition,
    PromotionCommitUnknown,
    PromotionRejected,
    PromotionSucceeded,
)
from .promotion_scoped_http_mapping import (
    ScopedPromotionCompletedProjection,
    ScopedPromotionRejectedProjection,
    ScopedPromotionUncertainProjection,
)
from .promotion_scoped_http_seam import (
    ScopedPromotionDispatchCompleted,
    ScopedPromotionDispatchRejected,
    ScopedPromotionDispatchResult,
    ScopedPromotionDispatchUncertain,
    ScopedPromotionReceipt,
)


@dataclass(frozen=True, slots=True)
class ScopedPromotionAccumulatorCompleted:
    """Completed scoped promotion reaches the accumulator.

    The original :class:`PromotionSucceeded` outcome and the
    aggregate :class:`ScopedPromotionReceipt` are reused by
    identity. The receipt is required and the commit disposition
    is :attr:`PromotionCommitDisposition.DEFINITELY_COMMITTED`.
    """

    outcome: PromotionSucceeded
    receipt: ScopedPromotionReceipt
    request_id: str
    request_fingerprint: str

    @property
    def commit_disposition(self) -> PromotionCommitDisposition:
        return PromotionCommitDisposition.DEFINITELY_COMMITTED


@dataclass(frozen=True, slots=True)
class ScopedPromotionAccumulatorUncertain:
    """Uncertain scoped promotion reaches the accumulator.

    The original :class:`PromotionCommitUnknown` outcome is
    reused by identity; the reconciliation token travels with it.
    A receipt is structurally impossible for this variant; the
    commit disposition is :attr:`PromotionCommitDisposition.MAY_HAVE_COMMITTED`.
    """

    outcome: PromotionCommitUnknown
    request_id: str
    request_fingerprint: str

    @property
    def commit_disposition(self) -> PromotionCommitDisposition:
        return PromotionCommitDisposition.MAY_HAVE_COMMITTED


@dataclass(frozen=True, slots=True)
class ScopedPromotionAccumulatorRejected:
    """Rejected scoped promotion reaches the accumulator.

    The original :class:`PromotionRejected` outcome is reused by
    identity. A receipt is structurally impossible for this
    variant; the commit disposition is
    :attr:`PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED`.
    """

    outcome: PromotionRejected
    request_id: str
    request_fingerprint: str

    @property
    def commit_disposition(self) -> PromotionCommitDisposition:
        return PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED


# Closed union -- each variant is unrepresentable in the others.
# The accumulator narrows on the concrete variant; the closed
# union prevents any silent loss of authority.
ScopedPromotionAccumulatorHandoff = (
    ScopedPromotionAccumulatorCompleted
    | ScopedPromotionAccumulatorUncertain
    | ScopedPromotionAccumulatorRejected
)


def scoped_dispatch_result_to_accumulator_handoff(
    result: ScopedPromotionDispatchResult,
) -> ScopedPromotionAccumulatorHandoff:
    """Convert the typed dispatch result into the closed accumulator handoff.

    The conversion preserves every original projection field by
    identity. The mapping is exhaustive; a new dispatch-result
    variant MUST fail typing through :func:`typing.assert_never`.

    Required mapping:

    * ``ScopedPromotionDispatchCompleted``
      -> ``ScopedPromotionAccumulatorCompleted`` reusing
      ``projection.promotion_outcome`` and
      ``projection.aggregate_receipt`` unchanged. ``request_id``
      and ``request_fingerprint`` are preserved.

    * ``ScopedPromotionDispatchUncertain``
      -> ``ScopedPromotionAccumulatorUncertain`` reusing
      ``projection.promotion_outcome`` unchanged (carrying the
      reconciliation token). ``request_id`` and
      ``request_fingerprint`` are preserved.

    * ``ScopedPromotionDispatchRejected``
      -> ``ScopedPromotionAccumulatorRejected`` reusing
      ``projection.promotion_outcome`` unchanged. ``request_id``
      and ``request_fingerprint`` are preserved.

    The function MUST NOT reconstruct a second
    :class:`PromotionOutcome` and MUST NOT derive commit
    authority from ``promotion_records``,
    ``promotion_record_count``, canonical incident counts,
    diagnosis incident counts, or ``ok``/``errors`` fields.
    """
    if isinstance(result, ScopedPromotionDispatchCompleted):
        projection: ScopedPromotionCompletedProjection = result.projection
        return ScopedPromotionAccumulatorCompleted(
            outcome=projection.promotion_outcome,
            receipt=projection.aggregate_receipt,
            request_id=projection.request_id,
            request_fingerprint=projection.request_fingerprint,
        )
    if isinstance(result, ScopedPromotionDispatchRejected):
        rejected_projection: ScopedPromotionRejectedProjection = result.projection
        return ScopedPromotionAccumulatorRejected(
            outcome=rejected_projection.promotion_outcome,
            request_id=rejected_projection.request_id,
            request_fingerprint=rejected_projection.request_fingerprint,
        )
    if isinstance(result, ScopedPromotionDispatchUncertain):
        uncertain_projection: ScopedPromotionUncertainProjection = result.projection
        return ScopedPromotionAccumulatorUncertain(
            outcome=uncertain_projection.promotion_outcome,
            request_id=uncertain_projection.request_id,
            request_fingerprint=uncertain_projection.request_fingerprint,
        )
    # Exhaustiveness: a new dispatch-result variant MUST fail typing.
    assert_never(result)


__all__ = [
    "ScopedPromotionAccumulatorCompleted",
    "ScopedPromotionAccumulatorHandoff",
    "ScopedPromotionAccumulatorRejected",
    "ScopedPromotionAccumulatorUncertain",
    "scoped_dispatch_result_to_accumulator_handoff",
]