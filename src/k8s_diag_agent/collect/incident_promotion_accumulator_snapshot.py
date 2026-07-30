"""Typed snapshot / restore helpers for the run promotion accumulator.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION01-ACCUMULATOR-SPLIT-AND-RANGE-GATE-TRUTH01.

The :class:`RunPromotionAccumulator` exposes two private methods
:meth:`_snapshot` and :meth:`_restore` that capture and restore
every mutable field of the accumulator. This module owns the
single canonical implementation of those methods. The
:class:`RunPromotionAccumulator` dataclass delegates to the
``snapshot_state`` / ``restore_state`` helpers below so the
dataclass state remains declared in one canonical place while
the snapshot logic lives in a focused module under the hard
500-line size cap.

The snapshot value object itself is declared in
:mod:`incident_promotion_scoped_atomic_host_protocol` so the
split recorder modules can import it without depending on the
dataclass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_promotion_accumulator import RunPromotionAccumulator
    from .incident_promotion_scoped_atomic_host_protocol import (
        AccumulatorSnapshot,
    )


def snapshot_state(
    acc: RunPromotionAccumulator,
) -> AccumulatorSnapshot:
    """Return a typed snapshot of every mutable accumulator field.

    Captures every mutable field the atomic recorder can touch so a
    partial-batch rollback leaves no observable drift. The mutable
    containers are stored as their frozen copies (immutable tuples
    / frozensets) so the restore path can detect drift via tuple
    equality.

    ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
    the snapshot also captures the single
    :class:`ScopedPromotionRecordedAuthority` so the recording
    authority is part of the atomic transaction.
    """
    from .incident_promotion_scoped_atomic_host_protocol import (
        AccumulatorSnapshot,
    )

    return AccumulatorSnapshot(
        promotion_records=tuple(acc.promotion_records),
        seen_canonical_ids=frozenset(acc._seen_canonical_ids),
        batches=tuple(acc.batches),
        total_scanned=acc.total_scanned,
        total_firing=acc.total_firing,
        total_opened_incidents=acc.total_opened_incidents,
        total_updated_incidents=acc.total_updated_incidents,
        total_skipped_duplicates=acc.total_skipped_duplicates,
        total_errors=acc.total_errors,
        total_unique_candidate_count=acc.total_unique_candidate_count,
        last_promotion_mode=acc.last_promotion_mode,
        last_incident_access_mode=acc.last_incident_access_mode,
        last_source_kind=acc.last_source_kind,
        last_promotion_scan_scope=acc.last_promotion_scan_scope,
        promotion_outcome=acc.promotion_outcome,
        promotion_outcome_run_id=acc.promotion_outcome_run_id,
        scoped_promotion_handoff=(
            acc.scoped_promotion_recording.handoff
            if acc.scoped_promotion_recording is not None
            else None
        ),
        scoped_promotion_recording=acc.scoped_promotion_recording,
    )


def restore_state(
    acc: RunPromotionAccumulator,
    snap: AccumulatorSnapshot,
) -> None:
    """Restore every mutable field from a typed snapshot, in place.

    The mutable containers are rewritten IN PLACE (``clear()`` /
    ``extend()`` / ``update()``) so any external observer holding a
    reference to the original list/set sees the same Python
    object after the rollback. Replacing the field with a new
    container would silently orphan externally retained
    references.

    ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
    the restore path also resets
    :attr:`scoped_promotion_recording` (and the derived
    :attr:`scoped_promotion_handoff`) so the rollback transaction
    leaves the scoped authority in its pre-call state.
    """
    acc.promotion_records.clear()
    acc.promotion_records.extend(snap.promotion_records)
    acc._seen_canonical_ids.clear()
    acc._seen_canonical_ids.update(snap.seen_canonical_ids)
    acc.batches.clear()
    acc.batches.extend(snap.batches)
    acc.total_scanned = snap.total_scanned
    acc.total_firing = snap.total_firing
    acc.total_opened_incidents = snap.total_opened_incidents
    acc.total_updated_incidents = snap.total_updated_incidents
    acc.total_skipped_duplicates = snap.total_skipped_duplicates
    acc.total_errors = snap.total_errors
    acc.total_unique_candidate_count = snap.total_unique_candidate_count
    acc.last_promotion_mode = snap.last_promotion_mode
    acc.last_incident_access_mode = snap.last_incident_access_mode
    acc.last_source_kind = snap.last_source_kind
    acc.last_promotion_scan_scope = snap.last_promotion_scan_scope
    acc.promotion_outcome = snap.promotion_outcome
    acc.promotion_outcome_run_id = snap.promotion_outcome_run_id
    acc.scoped_promotion_recording = snap.scoped_promotion_recording
    # ``scoped_promotion_handoff`` and ``scoped_promotion_batch``
    # are derived properties of the authority; nothing to restore.


__all__ = [
    "snapshot_state",
    "restore_state",
]