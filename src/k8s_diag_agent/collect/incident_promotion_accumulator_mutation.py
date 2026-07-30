"""Legacy batch and record mutators for the run promotion accumulator.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION01-ACCUMULATOR-SPLIT-AND-RANGE-GATE-TRUTH01.

The :class:`RunPromotionAccumulator` exposes a small set of
mutator methods that drive the legacy ``promotion_records`` /
``_seen_canonical_ids`` / aggregate counters:

* :meth:`add_record` / :meth:`add_records` /
  :meth:`record_promotion_result` -- append a single
  ``PromotionRecord`` to the legacy dedup state.
* :meth:`add_batch` -- validate-before-mutate atomic batch
  aggregation.
* :meth:`_apply_batch` -- internal non-rolled-back batch
  application.
* :meth:`_local_skipped_duplicate_count` -- derived counter
  for the ``local`` promotion path.

This module owns the single canonical implementation of every
mutator. The :class:`RunPromotionAccumulator` dataclass
delegates to the helpers below so the dataclass state remains
declared in one canonical place while the mutation logic
lives in a focused module under the hard 500-line size cap.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from .incident_identity_hardening import (
    INCIDENT_ACCESS_MODE_BACKEND,
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_SKIPPED_DUPLICATE,
    PromotionConsistencyContractError,
    PromotionRecord,
    _validate_response_contracts,
)
from .incident_promotion_batch import PromotionBatch

if TYPE_CHECKING:
    from .incident_promotion_accumulator import (
        RunPromotionAccumulator,
    )


def _local_skipped_duplicate_count_mutation(
    acc: RunPromotionAccumulator,
) -> int:
    """Count ``skipped_duplicate`` outcomes from local records.

    R5 (item 5): the batch-level ``skipped_duplicates`` aggregate
    is sourced from the dispatcher's authoritative count, but
    ``local`` promotion only knows about :class:`PromotionRecord`
    values. Counting the local records directly means the
    accumulator surfaces the same number whichever path
    produced the batch.
    """
    return sum(
        1
        for record in acc.promotion_records
        if record.promotion_outcome
        == PROMOTION_OUTCOME_SKIPPED_DUPLICATE
    )


def add_record_mutation(
    acc: RunPromotionAccumulator,
    record: PromotionRecord,
) -> None:
    """Append a single ``PromotionRecord`` to the accumulator.

    Records with a ``None`` canonical incident ID do NOT populate
    the dedup set so they can never mask a later authoritative
    ``canonical_incident_id`` with the same value.

    Note: this method only mutates the legacy accumulator state.
    The typed outcome (when recorded) is the single source of
    truth for downstream projections; legacy state is the
    fallback only when no typed outcome is recorded.
    """
    acc.promotion_records.append(record)
    if record.canonical_incident_id:
        acc._seen_canonical_ids.add(record.canonical_incident_id)


def add_records_mutation(
    acc: RunPromotionAccumulator,
    records: Iterable[PromotionRecord],
) -> None:
    """Iterate and call :func:`add_record` for each entry."""
    for record in records:
        add_record_mutation(acc, record)


def record_promotion_result_mutation(
    acc: RunPromotionAccumulator,
    *,
    source: str,
    incident_ids: tuple[str, ...],
) -> None:
    """Record canonical incident IDs from a promotion result atomically.

    Each ID is recorded with a synthetic ``PromotionRecord`` using
    the "opened" outcome (since we only record actionable IDs
    from promotion). If any ID is already in the accumulator, it
    is not duplicated.
    """
    for incident_id in incident_ids:
        if incident_id not in acc._seen_canonical_ids:
            acc._seen_canonical_ids.add(incident_id)
            acc.promotion_records.append(
                PromotionRecord(
                    source_candidate_id=f"<{source}>",
                    canonical_incident_id=incident_id,
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                )
            )


def add_batch_mutation(
    acc: RunPromotionAccumulator,
    batch: PromotionBatch,
) -> None:
    """Consume a typed ``PromotionBatch`` and aggregate it atomically.

    R4 contract: ``add_batch`` is validate-before-mutate. The
    batch's ``incident_access_mode`` MUST agree with the running
    value (or with the empty accumulator's absent value). If the
    running accumulator has been seeded with one mode and a
    subsequent batch disagrees, the call raises
    :class:`AccumulatorAccessModeError` and restores the
    accumulator to the exact state it had before the call.
    ``promotion_records``, ``_seen_canonical_ids``,
    ``batches``, ``total_*``, and ``last_*`` are all preserved.

    R3 contract: batch records are added via :func:`add_record` so
    canonical-ID dedup stays consistent. The aggregate metrics
    are added to the running totals and the latest batch's
    ``promotion_mode`` / ``incident_access_mode`` /
    ``source_kind`` / ``promotion_scan_scope`` are stored
    verbatim for downstream structured logging.

    R7 contract (item 3): every backend-authoritative batch is
    validated against the ordered-sequence-with-multiplicity
    contract BEFORE any field on the accumulator is mutated. The
    authoritative ``opened_incident_ids`` /
    ``updated_incident_ids`` arrays carried by the dispatcher's
    ``IncidentPromotionResult`` MUST match the ordered sequence
    of ``canonical_incident_id`` values on the
    ``promotion_records`` list (with multiplicity).
    """
    from .incident_promotion_accumulator import AccumulatorAccessModeError
    from .incident_promotion_accumulator_snapshot import (
        restore_state,
        snapshot_state,
    )

    snap = snapshot_state(acc)
    try:
        if batch.incident_access_mode == INCIDENT_ACCESS_MODE_BACKEND:
            _validate_response_contracts(
                promotion_records=list(batch.promotion_records),
                opened_incidents=batch.opened_incidents,
                updated_incidents=batch.updated_incidents,
                opened_incident_ids=batch.opened_incident_ids,
                updated_incident_ids=batch.updated_incident_ids,
            )
        _apply_batch_mutation(acc, batch)
    except AccumulatorAccessModeError:
        restore_state(acc, snap)
        raise
    except PromotionConsistencyContractError:
        restore_state(acc, snap)
        raise


def _apply_batch_mutation(
    acc: RunPromotionAccumulator,
    batch: PromotionBatch,
) -> None:
    """Internal: actually merge a batch (no rollback handling)."""
    if (
        acc.last_incident_access_mode
        and acc.last_incident_access_mode != batch.incident_access_mode
    ):
        from .incident_promotion_accumulator import (
            AccumulatorAccessModeError,
        )

        raise AccumulatorAccessModeError(
            f"Conflicting access modes within one run: "
            f"{acc.last_incident_access_mode!r} vs "
            f"{batch.incident_access_mode!r}",
            running_mode=acc.last_incident_access_mode,
            rejected_mode=batch.incident_access_mode,
        )
    acc.batches.append(batch)
    for record in batch.promotion_records:
        add_record_mutation(acc, record)
    acc.total_scanned += batch.scanned
    acc.total_firing += batch.firing
    acc.total_opened_incidents += batch.opened_incidents
    acc.total_updated_incidents += batch.updated_incidents
    record_skipped = _local_skipped_duplicate_count_mutation(acc)
    acc.total_skipped_duplicates = max(
        acc.total_skipped_duplicates + batch.skipped_duplicates,
        record_skipped,
    )
    acc.total_unique_candidate_count += batch.unique_candidate_count
    acc.total_errors += batch.errors
    acc.last_promotion_mode = batch.promotion_mode
    acc.last_incident_access_mode = batch.incident_access_mode
    acc.last_source_kind = batch.source_kind
    acc.last_promotion_scan_scope = batch.promotion_scan_scope


__all__ = [
    "_apply_batch_mutation",
    "_local_skipped_duplicate_count_mutation",
    "add_batch_mutation",
    "add_record_mutation",
    "add_records_mutation",
    "record_promotion_result_mutation",
]