"""Exhaustive replay-equivalence checks for the scoped atomic recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.

This module owns the two replay-equivalence predicates used by
:meth:`ScopedPromotionAtomicRecorderMixin.record_scoped_promotion_batch`
when the dispatcher presents a semantically equal replay:

* :func:`_receipt_equivalent` -- the completed-handoff receipt
  comparison. Built on the canonical :class:`BoundScopedPromotionResult`
  equality so EVERY authoritative field is part of the check,
  including:

  * ``bound.request.{run_id, source_identity, ordered signal_ids}``
  * ``bound.result.{run_id, source_identity, ordered scanned-signal ids}``
  * ``bound.result.opened_incident_ids``
  * ``bound.result.materially_changed_incident_ids``
  * ``bound.result.observation_refreshed_incident_ids``
  * ``bound.result.unchanged_incident_ids``
  * ``bound.result.skipped_signal_ids``
  * ``bound.result.failures`` (including each failure's
    ``reason_code`` and bounded ``detail`` string)

* :func:`_batch_accounting_equivalent` -- the accounting-batch
  comparison across every field that
  :meth:`RunPromotionAccumulator._apply_batch` mutates, plus every
  bounded provenance field on the batch envelope:

  * ``batch.promotion_result.ok``
  * ``batch.promotion_result.scanned, firing``
  * ``batch.promotion_result.opened_incidents, updated_incidents``
  * ``batch.promotion_result.skipped_duplicates, errors``
  * ``batch.promotion_result.error_messages``
  * ``batch.promotion_result.unique_candidate_count``
  * ``batch.promotion_result.opened_incident_ids, updated_incident_ids``
  * ``batch.promotion_result.observation_refreshed_incident_ids,
    unchanged_incident_ids``
  * ``batch.promotion_result.promotion_mode, promotion_scan_scope,
    incident_access_mode``
  * ``batch.promotion_records == ()``
  * ``batch.source_kind, cluster_context, snapshot_bundle_id``

Both predicates compare immutable dataclass instances; equality
on ``frozen=True, slots=True`` dataclasses is exhaustive over the
declared fields. This module therefore stays small -- any new
canonical field automatically becomes part of the equivalence.
"""

from __future__ import annotations

from ..incident_alert_promotion_binding import BoundScopedPromotionResult
from .incident_promotion_batch import PromotionBatch


def _receipt_equivalent(
    running: BoundScopedPromotionResult,
    candidate: BoundScopedPromotionResult,
) -> bool:
    """Return True iff two receipts are equivalent for replay.

    Built on :class:`BoundScopedPromotionResult` equality so EVERY
    canonical field on the bound participates in the comparison --
    not just the partial handful of fields the previous revision
    inspected (request identity, opened IDs, materially-changed
    IDs).

    Equality here covers, in addition to the previously-listed
    fields, observation-refreshed IDs, unchanged IDs, the ordered
    skipped-signal list, and the bounded per-signal ``failures``
    tuple (each :class:`IncidentPromotionFailure` has its own
    ``reason_code`` and ``detail`` string). A replay that mutates
    any of these raises a conflict instead of silently surviving
    as ``IDEMPOTENT``.
    """
    return running == candidate


def _batch_accounting_equivalent(
    running: PromotionBatch,
    candidate: PromotionBatch,
) -> bool:
    """Return True iff two batches publish equivalent aggregate state.

    Built on :class:`PromotionBatch` equality so EVERY canonical
    accounting aggregate and bounded provenance field on the
    batch envelope participates in the comparison:

    * ``promotion_result`` -- the bounded
      :class:`IncidentPromotionResult` roll-up of scanned/firing/
      opened/updated/skipped_duplicates/errors plus the four
      incident-ID tuples (opened, updated, observation-refreshed,
      unchanged), the bounded ``error_messages``, the
      ``unique_candidate_count``, and the canonical
      ``promotion_mode``/``promotion_scan_scope``/
      ``incident_access_mode`` triples.
    * ``promotion_records`` -- the scoped aggregate contract
      forbids per-signal entries, so this MUST stay ``()``. The
      frozen-tuple equality propagates this constraint.
    * ``source_kind, cluster_context, snapshot_bundle_id`` --
      the bounded provenance envelope.

    The previous manual Boolean chain missed several of these
    fields; full dataclass equality closes every gap and keeps the
    module under the hard-size limit.
    """
    return running == candidate


__all__ = [
    "_batch_accounting_equivalent",
    "_receipt_equivalent",
]
