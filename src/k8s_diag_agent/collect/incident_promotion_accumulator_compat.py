"""Compatibility wrapper for ``record_scoped_promotion``.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION01-ACCUMULATOR-SPLIT-AND-RANGE-GATE-TRUTH01.

The :class:`RunPromotionAccumulator` historically exposed
:meth:`record_scoped_promotion` (single-argument) for unit tests
that exercise the accumulator's handoff store. Active scoped
dispatchers use the typed two-argument
:meth:`record_scoped_promotion_batch` API. This module owns the
single canonical implementation of the legacy compatibility
wrapper so the active recorder API stays under the hard 500-line
size cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_promotion_accumulator import RunPromotionAccumulator
    from .promotion_scoped_accumulator_handoff import (
        ScopedPromotionAccumulatorHandoff,
    )


def record_scoped_promotion_compat(
    self: RunPromotionAccumulator,
    handoff: ScopedPromotionAccumulatorHandoff,
) -> None:
    """Compatibility wrapper around ``record_scoped_promotion_batch``.

    ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
    CORRECTION03-ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01.

    The active scoped dispatcher MUST call
    :meth:`record_scoped_promotion_batch` with both the typed
    handoff and the dispatcher's accounting batch. This wrapper
    exists only so existing unit tests that exercise
    ``record_scoped_promotion(handoff)`` still record the typed
    handoff and outcome; it routes through the new atomic
    operation so the single-request-identity-authority invariant
    is preserved.

    The wrapper builds the bounded accounting batch from the
    handoff itself (the dispatcher's projection has already
    produced the canonical ``IncidentPromotionResult``); it then
    forwards everything through the atomic recorder. When the
    caller has its own batch (the production dispatcher path) it
    MUST bypass this wrapper and call the atomic method directly.

    The handoff is the only authority for the active scoped
    path. The original :class:`PromotionOutcome` reaches the
    accumulator unchanged by identity. Receipt presence is
    governed by the handoff variant: only the completed variant
    carries a receipt; uncertain and rejected variants are
    structurally incapable of carrying one. Commit authority is
    derived from :attr:`commit_disposition`; the function MUST
    NOT infer whether promotion ran from ``promotion_records``,
    ``promotion_record_count``, canonical incident counts,
    diagnosis incident counts, or ``ok`` / ``errors`` fields.
    """
    from .incident_promotion_scoped_atomic_projection import (
        build_compatibility_batch_from_handoff,
    )

    accounting_batch = build_compatibility_batch_from_handoff(handoff)
    # Forward through the atomic path. The return value is
    # discarded for backward compatibility with the prior
    # signature, which returned ``None``.
    self.record_scoped_promotion_batch(
        handoff=handoff,
        batch=accounting_batch,
    )


__all__ = [
    "record_scoped_promotion_compat",
]