"""Exhaustive handoff/batch consistency validators for the scoped atomic recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
CORRECTION04-REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.
ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
CORRECTION05-STRICT-TYPING-AND-ROLLBACK-CLOSURE01.

The validators enforce, for every dispatch variant, that the
accompanying :class:`PromotionBatch` is a faithful accounting
projection of the closed handoff variant. Each validator
MUST cover:

* the bounded access mode (``backend`` /
  ``reconciliation_required``);
* the exact count of scanned and firing events;
* the authoritative opened and updated aggregate IDs (and
  counts);
* the bounded ``errors`` / ``error_messages`` projection;
* the canonical ``promotion_mode``, ``promotion_scan_scope``,
  and ``unique_candidate_count`` invariants;
* the bounded ``source_kind`` / ``cluster_context`` /
  ``snapshot_bundle_id`` provenance envelope;
* the empty-``promotion_records`` aggregate invariant.

The shape of each validator mirrors the
:class:`ScopedPromotionAccumulatorCompleted` /
:class:`ScopedPromotionAccumulatorUncertain` /
:class:`ScopedPromotionAccumulatorRejected` construction
invariant documented in :mod:`promotion_scoped_accumulator_handoff`
so a future variant addition fails the static check rather
than silently bypassing validation. The dispatcher
:func:`validate_scoped_handoff_batch_consistency` ends with
:func:`typing.assert_never` so a new variant addition MUST
satisfy the static check.
"""

from __future__ import annotations

from typing import assert_never

from .incident_promotion_batch import PromotionBatch
from .incident_promotion_dispatch_constants import (
    INCIDENT_ACCESS_MODE_BACKEND,
    MODE_BACKEND_API,
)
from .promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
    ScopedPromotionAccumulatorHandoff,
    ScopedPromotionAccumulatorRejected,
    ScopedPromotionAccumulatorUncertain,
)
from .promotion_scoped_http_seam import ScopedPromotionReceipt

# Strings that participate in compatibility/accounting checks
# only and MUST agree with :mod:`incident_promotion_dispatch`.
_RECONCILIATION_REQUIRED_ACCESS_MODE = "reconciliation_required"
_EXPECTED_SOURCE_KIND = "alertmanager"
_EXPECTED_SCAN_SCOPE = "internal_api_alert_signals:scoped"
_EMPTY_RECORDS: tuple[object, ...] = ()


def _require_common_batch_frame(
    *,
    handoff: ScopedPromotionAccumulatorHandoff,
    batch: PromotionBatch,
    signal_count: int,
) -> tuple[
    object,  # promotion_result
    str,  # backend access-mode
    int,  # expected_scanned
    int,  # expected_unique_candidate_count
]:
    """Enforce the bounded cross-variant batch envelope.

    Called by every variant validator. The check returns the bounded
    fields the variant tests consult in the next step. The
    ``batch`` parameter is typed as the canonical
    :class:`PromotionBatch` so the static checker can verify the
    full surface of the batch envelope is consulted; no
    ``object``-typed dynamic dispatch remains inside the
    validator.
    """
    pr = batch.promotion_result
    if batch.promotion_records != _EMPTY_RECORDS:
        raise ValueError(
            "record_scoped_promotion_batch forbids per-signal "
            "promotion_records on the scoped aggregate batch "
            f"(got {len(batch.promotion_records)} records)"
        )
    if batch.source_kind != _EXPECTED_SOURCE_KIND:
        raise ValueError(
            "Scoped aggregate batch MUST carry source_kind="
            f"{_EXPECTED_SOURCE_KIND!r}; got {batch.source_kind!r}"
        )
    if batch.promotion_scan_scope != _EXPECTED_SCAN_SCOPE:
        raise ValueError(
            "Scoped aggregate batch MUST carry promotion_scan_scope="
            f"{_EXPECTED_SCAN_SCOPE!r}; got {batch.promotion_scan_scope!r}"
        )
    if batch.promotion_mode != MODE_BACKEND_API:
        raise ValueError(
            "Scoped aggregate batch MUST carry promotion_mode="
            f"{MODE_BACKEND_API!r}; got {batch.promotion_mode!r}"
        )
    return pr, INCIDENT_ACCESS_MODE_BACKEND, signal_count, signal_count


def _validate_completed(
    *,
    handoff: ScopedPromotionAccumulatorCompleted,
    batch: PromotionBatch,
    receipt: ScopedPromotionReceipt,
    requested_signal_count: int,
) -> None:
    """Validate a completed-handoff / batch pair exhaustively."""
    pr, expected_access_mode, expected_scanned, expected_unique = (
        _require_common_batch_frame(
            handoff=handoff,
            batch=batch,
            signal_count=requested_signal_count,
        )
    )
    if not pr.ok:
        raise ValueError(
            "Completed handoff rejected: batch.promotion_result.ok "
            "MUST be True for completed scoped promotions"
        )
    if pr.incident_access_mode != expected_access_mode:
        raise ValueError(
            "Completed handoff rejected: incident_access_mode MUST be "
            f"{expected_access_mode!r}"
        )
    if pr.scanned != expected_scanned:
        raise ValueError(
            "Completed handoff rejected: batch.scanned disagrees with "
            f"len(outcome.requested_signal_ids) ({pr.scanned} vs "
            f"{expected_scanned})"
        )
    if pr.firing != expected_scanned:
        raise ValueError(
            "Completed handoff rejected: batch.firing disagrees with "
            f"len(outcome.requested_signal_ids) ({pr.firing} vs "
            f"{expected_scanned})"
        )
    if pr.unique_candidate_count != expected_unique:
        raise ValueError(
            "Completed handoff rejected: batch.unique_candidate_count "
            f"disagrees ({pr.unique_candidate_count} vs {expected_unique})"
        )
    if pr.errors != 0:
        raise ValueError(
            "Completed handoff rejected: batch.errors MUST be 0; "
            f"got {pr.errors}"
        )
    if pr.error_messages:
        raise ValueError(
            "Completed handoff rejected: batch.error_messages MUST be "
            f"empty; got {pr.error_messages!r}"
        )
    receipt_opened = receipt.opened_incident_ids
    receipt_updated = receipt.materially_changed_incident_ids
    receipt_refreshed = receipt.observation_refreshed_incident_ids
    receipt_unchanged = receipt.unchanged_incident_ids
    if tuple(pr.opened_incident_ids) != receipt_opened:
        raise ValueError(
            "Completed handoff rejected: batch.opened_incident_ids "
            "disagrees with receipt.opened_incident_ids"
        )
    if tuple(pr.updated_incident_ids) != receipt_updated:
        raise ValueError(
            "Completed handoff rejected: batch.updated_incident_ids "
            "disagrees with receipt.materially_changed_incident_ids"
        )
    if tuple(pr.observation_refreshed_incident_ids) != receipt_refreshed:
        raise ValueError(
            "Completed handoff rejected: batch.observation_refreshed_incident_ids "
            "disagrees with receipt.observation_refreshed_incident_ids"
        )
    if tuple(pr.unchanged_incident_ids) != receipt_unchanged:
        raise ValueError(
            "Completed handoff rejected: batch.unchanged_incident_ids "
            "disagrees with receipt.unchanged_incident_ids"
        )
    if pr.opened_incidents != len(receipt_opened):
        raise ValueError(
            "Completed handoff rejected: batch.opened_incidents disagrees "
            "with len(receipt.opened_incident_ids)"
        )
    if pr.updated_incidents != len(receipt_updated):
        raise ValueError(
            "Completed handoff rejected: batch.updated_incidents disagrees "
            "with len(receipt.materially_changed_incident_ids)"
        )


def _validate_uncertain(
    *,
    handoff: ScopedPromotionAccumulatorUncertain,
    batch: PromotionBatch,
    requested_signal_count: int,
) -> None:
    """Validate an uncertain-handoff / batch pair exhaustively."""
    pr, expected_access_mode_unused, expected_scanned, expected_unique = (
        _require_common_batch_frame(
            handoff=handoff,
            batch=batch,
            signal_count=requested_signal_count,
        )
    )
    if pr.ok:
        raise ValueError(
            "Uncertain handoff rejected: batch.promotion_result.ok "
            "MUST be False for uncertain scoped promotions"
        )
    if pr.incident_access_mode != _RECONCILIATION_REQUIRED_ACCESS_MODE:
        raise ValueError(
            "Uncertain handoff rejected: incident_access_mode MUST be "
            f"{_RECONCILIATION_REQUIRED_ACCESS_MODE!r}"
        )
    if pr.scanned != expected_scanned:
        raise ValueError(
            "Uncertain handoff rejected: batch.scanned disagrees with "
            f"len(outcome.requested_signal_ids) ({pr.scanned} vs "
            f"{expected_scanned})"
        )
    if pr.firing != expected_scanned:
        raise ValueError(
            "Uncertain handoff rejected: batch.firing disagrees with "
            f"len(outcome.requested_signal_ids) ({pr.firing} vs "
            f"{expected_scanned})"
        )
    if pr.unique_candidate_count != expected_unique:
        raise ValueError(
            "Uncertain handoff rejected: batch.unique_candidate_count "
            f"disagrees ({pr.unique_candidate_count} vs {expected_unique})"
        )
    if pr.opened_incidents != 0 or pr.updated_incidents != 0:
        raise ValueError(
            "Uncertain handoff rejected: opened/updated counts MUST be 0"
        )
    if pr.opened_incident_ids or pr.updated_incident_ids:
        raise ValueError(
            "Uncertain handoff rejected: opened/updated incident IDs "
            "MUST be empty"
        )
    if pr.observation_refreshed_incident_ids or pr.unchanged_incident_ids:
        raise ValueError(
            "Uncertain handoff rejected: observation/unchanged "
            "incident IDs MUST be empty for the uncertain variant"
        )
    if pr.errors != 0:
        raise ValueError(
            "Uncertain handoff rejected: batch.errors MUST be 0; "
            f"got {pr.errors}"
        )
    if pr.error_messages:
        raise ValueError(
            "Uncertain handoff rejected: batch.error_messages MUST be empty"
        )
    if pr.skipped_duplicates != 0:
        raise ValueError(
            "Uncertain handoff rejected: batch.skipped_duplicates "
            f"MUST be 0; got {pr.skipped_duplicates}"
        )


def _validate_rejected(
    *,
    handoff: ScopedPromotionAccumulatorRejected,
    batch: PromotionBatch,
    rejected_signal_count: int,
) -> None:
    """Validate a rejected-handoff / batch pair exhaustively."""
    pr, expected_access_mode, expected_scanned, expected_unique = (
        _require_common_batch_frame(
            handoff=handoff,
            batch=batch,
            signal_count=rejected_signal_count,
        )
    )
    if pr.ok:
        raise ValueError(
            "Rejected handoff rejected: batch.promotion_result.ok "
            "MUST be False for rejected scoped promotions"
        )
    if pr.incident_access_mode != expected_access_mode:
        raise ValueError(
            "Rejected handoff rejected: incident_access_mode MUST be "
            f"{expected_access_mode!r}"
        )
    if pr.scanned != expected_scanned:
        raise ValueError(
            "Rejected handoff rejected: batch.scanned disagrees with "
            f"len(outcome.rejected_signal_ids) ({pr.scanned} vs "
            f"{expected_scanned})"
        )
    if pr.firing != expected_scanned:
        raise ValueError(
            "Rejected handoff rejected: batch.firing disagrees with "
            f"len(outcome.rejected_signal_ids) ({pr.firing} vs "
            f"{expected_scanned})"
        )
    if pr.unique_candidate_count != expected_unique:
        raise ValueError(
            "Rejected handoff rejected: batch.unique_candidate_count "
            f"disagrees ({pr.unique_candidate_count} vs {expected_unique})"
        )
    if pr.opened_incidents != 0 or pr.updated_incidents != 0:
        raise ValueError(
            "Rejected handoff rejected: opened/updated counts MUST be 0"
        )
    if pr.opened_incident_ids or pr.updated_incident_ids:
        raise ValueError(
            "Rejected handoff rejected: opened/updated incident IDs "
            "MUST be empty"
        )
    if pr.observation_refreshed_incident_ids or pr.unchanged_incident_ids:
        raise ValueError(
            "Rejected handoff rejected: observation/unchanged "
            "incident IDs MUST be empty for the rejected variant"
        )
    if pr.errors != 1:
        raise ValueError(
            "Rejected handoff rejected: batch.errors MUST be 1 for the "
            f"bounded rejection projection; got {pr.errors}"
        )
    expected_messages = (handoff.outcome.reason.value,)
    if pr.error_messages != expected_messages:
        raise ValueError(
            "Rejected handoff rejected: batch.error_messages MUST equal "
            f"the typed rejection reason {expected_messages!r}; "
            f"got {pr.error_messages!r}"
        )
    if pr.skipped_duplicates != 0:
        raise ValueError(
            "Rejected handoff rejected: batch.skipped_duplicates "
            f"MUST be 0; got {pr.skipped_duplicates}"
        )


def validate_scoped_handoff_batch_consistency(
    handoff: ScopedPromotionAccumulatorHandoff,
    batch: object,
) -> None:
    """Validate that the handoff and batch agree on the dispatch variant.

    Dispatches to the per-variant validator. Each variant enforces
    every bounded cross-variant invariant first, then its
    variant-specific aggregate deltas. A new handoff variant added
    without updating this dispatcher fails the static check via
    :func:`typing.assert_never` so an unhandled variant cannot
    silently bypass validation.

    The ``batch`` parameter is typed as ``object`` because the
    validator is the single canonical boundary that converts the
    untyped caller payload into a typed :class:`PromotionBatch`;
    once narrowed, the per-variant validators operate strictly
    on ``PromotionBatch`` instances.
    """
    if not isinstance(handoff, ScopedPromotionAccumulatorHandoff):
        raise TypeError(
            "record_scoped_promotion_batch requires a "
            f"ScopedPromotionAccumulatorHandoff; got {type(handoff).__name__}"
        )
    if not isinstance(batch, PromotionBatch):
        raise TypeError(
            "record_scoped_promotion_batch requires a PromotionBatch; "
            f"got {type(batch).__name__}"
        )
    if isinstance(handoff, ScopedPromotionAccumulatorCompleted):
        _validate_completed(
            handoff=handoff,
            batch=batch,
            receipt=handoff.receipt,
            requested_signal_count=len(
                handoff.outcome.requested_signal_ids
            ),
        )
        return
    if isinstance(handoff, ScopedPromotionAccumulatorUncertain):
        _validate_uncertain(
            handoff=handoff,
            batch=batch,
            requested_signal_count=len(
                handoff.outcome.requested_signal_ids
            ),
        )
        return
    if isinstance(handoff, ScopedPromotionAccumulatorRejected):
        _validate_rejected(
            handoff=handoff,
            batch=batch,
            rejected_signal_count=len(
                handoff.outcome.rejected_signal_ids
            ),
        )
        return
    # Exhaustiveness: a new handoff variant MUST fail typing.
    assert_never(handoff)


__all__ = [
    "validate_scoped_handoff_batch_consistency",
]