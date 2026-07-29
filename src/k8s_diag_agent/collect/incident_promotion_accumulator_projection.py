"""Derived scoped-recording projections and aggregate read helpers.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION01-ACCUMULATOR-SPLIT-AND-RANGE-GATE-TRUTH01.

The :class:`RunPromotionAccumulator` exposes a small set of
read-only projections that downstream code (orchestrator,
verifier, structured log) consumes:

* :attr:`scoped_promotion_handoff` /
  :attr:`scoped_promotion_batch` -- derived projections of the
  single :attr:`scoped_promotion_recording` authority.
* :attr:`scoped_promotion_request_id` /
  :attr:`scoped_promotion_request_fingerprint` -- derived
  projections of the recorded handoff.
* :meth:`__setattr__` -- rejects writes to the derived
  projections.
* :meth:`scoped_promotion_handoff_value` -- legacy typed-handoff
  accessor.
* :meth:`as_dict` -- JSON-friendly summary projection.
* :meth:`has_promotion_activity` /
  :meth:`aggregated_error_messages` -- aggregate read
  projections.

This module owns the single canonical implementation of every
projection. The :class:`RunPromotionAccumulator` dataclass
delegates to the helpers below so the dataclass state remains
declared in one canonical place while the projection logic
lives in a focused module under the hard 500-line size cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_promotion_accumulator import RunPromotionAccumulator
    from .incident_promotion_batch import PromotionBatch
    from .promotion_scoped_accumulator_handoff import (
        ScopedPromotionAccumulatorHandoff,
    )


_FORBIDDEN_DERIVED_NAMES: frozenset[str] = frozenset(
    {
        "scoped_promotion_request_id",
        "scoped_promotion_request_fingerprint",
        "scoped_promotion_handoff",
        "scoped_promotion_batch",
    }
)


def scoped_promotion_handoff_value(
    acc: RunPromotionAccumulator,
) -> ScopedPromotionAccumulatorHandoff | None:
    """Return the recorded scoped promotion handoff, if any.

    ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
    derived projection of the scoped recording authority. The
    accessor MUST NOT be reconstructed from legacy counters or
    aggregate incident IDs.
    """
    authority = acc.scoped_promotion_recording
    if authority is None:
        return None
    return authority.handoff


def scoped_promotion_batch_projection(
    acc: RunPromotionAccumulator,
) -> PromotionBatch | None:
    """Return the recorded batch from the scoped authority.

    ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
    derived projection of :attr:`scoped_promotion_recording`.
    External callers MUST NOT assign to it; the recorder is the
    authoritative write path.
    """
    authority = acc.scoped_promotion_recording
    if authority is None:
        return None
    return authority.batch


def scoped_promotion_request_id_projection(
    acc: RunPromotionAccumulator,
) -> str:
    """Return the recorded handoff's request id, or ``""`` when absent.

    Derived projection of the scoped recording authority's
    handoff. The accumulator does NOT store a mutable copy of
    this value; callers MUST NOT assign to the property.
    """
    authority = acc.scoped_promotion_recording
    if authority is None:
        return ""
    return authority.handoff.request_id


def scoped_promotion_request_fingerprint_projection(
    acc: RunPromotionAccumulator,
) -> str:
    """Return the recorded handoff's fingerprint, or ``""`` when absent.

    Derived projection of the scoped recording authority's
    handoff. The accumulator does NOT store a mutable copy of
    this value; callers MUST NOT assign to the property.
    """
    authority = acc.scoped_promotion_recording
    if authority is None:
        return ""
    return authority.handoff.request_fingerprint


def has_promotion_activity(acc: RunPromotionAccumulator) -> bool:
    """Return True if at least one batch has been accepted.

    The orchestrator uses this to distinguish a deliberate
    empty promotion run from one that never reached promotion.
    """
    return bool(acc.batches)


def aggregated_error_messages(acc: RunPromotionAccumulator) -> tuple[str, ...]:
    """Return bounded error messages from every accepted batch."""
    messages: list[str] = []
    for batch in acc.batches:
        messages.extend(batch.error_messages)
    return tuple(messages)


def as_dict(acc: RunPromotionAccumulator) -> dict[str, object]:
    """Return a JSON-friendly snapshot of the accumulator.

    The shape mirrors the existing ``promotion_summary_propagated``
    dict consumed by
    :func:`loop_automatic_diagnosis.run_automatic_diagnosis_loop` so
    the existing structured-log paths stay intact.
    """
    return {
        "promotion_records": [
            record.to_dict() for record in acc.promotion_records
        ],
        "opened_incident_ids": acc.canonical_incident_ids(),
        "promotion_outcomes": list(acc.promotion_outcomes()),
        "unique_candidate_count": len(
            {
                record.source_candidate_id
                for record in acc.promotion_records
            }
        ),
    }


def reject_derived_assignment(name: str, value: object) -> None:
    """Reject writes to derived scoped-recording projections.

    Called by :meth:`RunPromotionAccumulator.__setattr__`. The
    canonical list of forbidden derived names is owned by this
    module so a future derived projection is added in exactly
    one place.
    """
    if name in _FORBIDDEN_DERIVED_NAMES:
        raise AttributeError(
            f"{name} is a derived projection of "
            "scoped_promotion_recording; assignment is forbidden."
        )


__all__ = [
    "_FORBIDDEN_DERIVED_NAMES",
    "aggregated_error_messages",
    "as_dict",
    "has_promotion_activity",
    "reject_derived_assignment",
    "scoped_promotion_batch_projection",
    "scoped_promotion_handoff_value",
    "scoped_promotion_request_fingerprint_projection",
    "scoped_promotion_request_id_projection",
]