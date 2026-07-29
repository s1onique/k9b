"""Replay-conflict field tests for the scoped atomic recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.

The exhaustive equivalence predicates
(:func:`_receipt_equivalent`, :func:`_batch_accounting_equivalent`)
are built on dataclass equality. Each test in this matrix mutates
ONE authoritative field on either the handoff or the candidate
batch and confirms the atomic recorder raises the bounded
exception.

The matrix separates two failure shapes:

* **Replay conflict** -- a replay that changes a field the
  validator does NOT check directly (request identity fields,
  receipt-level aggregates, etc.). The equivalence check
  raises :class:`PromotionOutcomeConflictError`.
* **Validation rejection** -- a replay that breaks a field the
  validator DOES check exhaustively (source_kind, scan_scope,
  promotion_mode, opened/updated counts, etc.). The validator
  raises :class:`ValueError` BEFORE the equivalence check.

Both shapes are documented here so the focused matrix stays
complete even though the test assertions differ.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
    PromotionOutcomeRecording,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_projection import (
    build_compatibility_batch_from_handoff,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
)
from tests.unit.scoped_handoff_atomic_support import (
    completed_handoff,
    make_completed_batch,
    make_completed_projection,
    rejected_handoff,
    uncertain_handoff,
)


def _seed_completed(acc: RunPromotionAccumulator) -> None:
    """Seed the accumulator with a completed handoff/batch."""
    handoff = completed_handoff(
        diagnosis_incident_ids=("canonical-conflict",),
    )
    batch = make_completed_batch(handoff=handoff)
    recording = acc.record_scoped_promotion_batch(
        handoff=handoff, batch=batch
    )
    assert recording is PromotionOutcomeRecording.NEW


# ---------------------------------------------------------------------------
# Replay conflict (equivalence catches it)
# ---------------------------------------------------------------------------


class TestHandoffRequestIdentityReplayConflict:
    """Request id / fingerprint mismatches on the candidate handoff."""

    def test_conflicting_request_id_raises_conflict(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = ScopedPromotionAccumulatorCompleted(
            outcome=make_completed_projection(
                diagnosis_incident_ids=("canonical-conflict",)
            ).promotion_outcome,
            receipt=make_completed_projection(
                diagnosis_incident_ids=("canonical-conflict",)
            ).aggregate_receipt,
            request_id="different-request-id-still-canonical",
            request_fingerprint="a" * 64,
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_conflicting_request_fingerprint_raises_conflict(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        base = make_completed_projection(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        different_fp_handoff = ScopedPromotionAccumulatorCompleted(
            outcome=base.promotion_outcome,
            receipt=base.aggregate_receipt,
            request_id=base.request_id,
            request_fingerprint="e" * 64,
        )
        different_fp_batch = make_completed_batch(
            handoff=different_fp_handoff
        )
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=different_fp_handoff, batch=different_fp_batch
            )


class TestReceiptReplayConflict:
    """Receipt-level conflicts must be caught by ``_receipt_equivalent``.

    The closed-union ``__post_init__`` validator rejects mismatched
    receipt/outcome contracts at construction time (with
    :class:`ValueError`). The recorder is therefore protected
    against receipt conflicts before the equivalence check ever
    runs. The test pins the upstream rejection.
    """

    def test_receipt_opened_ids_mismatch_rejected_at_construction(
        self,
    ) -> None:
        outcome = make_completed_projection(
            diagnosis_incident_ids=("canonical-receipt-x",)
        ).promotion_outcome
        from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
            ScopedPromotionReceipt,
        )
        from tests.unit.scoped_handoff_atomic_support import _make_bound

        wrong_bound = _make_bound(
            run_id=outcome.run_id,
            requested_signal_ids=outcome.requested_signal_ids,
            diagnosis_incident_ids=("canonical-receipt-y",),
        )
        wrong_receipt = ScopedPromotionReceipt(bound=wrong_bound)
        with pytest.raises(ValueError, match="diagnosis_incident_ids"):
            ScopedPromotionAccumulatorCompleted(
                outcome=outcome,
                receipt=wrong_receipt,
                request_id=outcome.run_id,
                request_fingerprint="a" * 64,
            )


# ---------------------------------------------------------------------------
# Validation rejection (validator catches it before conflict check)
# ---------------------------------------------------------------------------


class TestBatchValidationRejection:
    """Fields the validator checks exhaustively are rejected with
    :class:`ValueError` BEFORE the equivalence check runs.
    """

    def test_invalid_source_kind_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_batch = replace(new_batch, source_kind="not_alertmanager")
        with pytest.raises(ValueError, match="source_kind"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_cluster_context_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_batch = replace(
            new_batch, cluster_context="ctx-mutated-replay"
        )
        # Cluster context is not in the validator's check list, so
        # this fires the conflict path.
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_snapshot_bundle_id_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_batch = replace(
            new_batch, snapshot_bundle_id="bundle-mutated-replay"
        )
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_promotion_scan_scope_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            promotion_scan_scope="mutated_scan_scope",
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="promotion_scan_scope"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_promotion_mode_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            promotion_mode="local",  # was "backend-api"
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="promotion_mode"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_incident_access_mode_rejected_by_validator(
        self,
    ) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            incident_access_mode="local",  # was "backend"
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="incident_access_mode"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_opened_incident_ids_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            opened_incident_ids=("canonical-replay-mutated",),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="opened_incident_ids"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_updated_incident_ids_rejected_by_validator(
        self,
    ) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            updated_incident_ids=("canonical-replay-mutated",),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="updated_incident_ids"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_observation_refreshed_rejected_by_validator(
        self,
    ) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            observation_refreshed_incident_ids=(
                "canonical-replay-mutated",
            ),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="observation_refreshed_incident_ids"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_unchanged_incident_ids_rejected_by_validator(
        self,
    ) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            unchanged_incident_ids=("canonical-replay-mutated",),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="unchanged_incident_ids"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_error_messages_rejected_by_validator(self) -> None:
        """Completed batches MUST carry empty error_messages."""
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            error_messages=("replay-mutated-error",),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="error_messages"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_unique_candidate_count_rejected_by_validator(
        self,
    ) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            unique_candidate_count=(
                new_batch.promotion_result.unique_candidate_count + 1
            ),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="unique_candidate_count"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_skipped_duplicates_raises_conflict(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            skipped_duplicates=(
                new_batch.promotion_result.skipped_duplicates + 1
            ),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_scanned_count_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            scanned=new_batch.promotion_result.scanned + 1,
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="scanned"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_firing_count_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            firing=new_batch.promotion_result.firing + 1,
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="firing"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )


# ---------------------------------------------------------------------------
# Handoff variant change (closed-union conflict)
# ---------------------------------------------------------------------------


class TestVariantChangeConflict:
    """A replay that switches the closed-union variant is a conflict."""

    def test_completed_to_uncertain_raises(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = uncertain_handoff(
            requested_signal_ids=(
                "sig-a", "sig-b", "sig-c", "sig-d", "sig-e",
            ),
        )
        new_batch = build_compatibility_batch_from_handoff(new_handoff)
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_completed_to_rejected_raises(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = rejected_handoff(
            requested_signal_ids=(
                "sig-a", "sig-b", "sig-c", "sig-d", "sig-e",
            ),
        )
        new_batch = build_compatibility_batch_from_handoff(new_handoff)
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_uncertain_to_rejected_raises(self) -> None:
        acc = RunPromotionAccumulator()
        uncertain = uncertain_handoff()
        acc.record_scoped_promotion_batch(
            handoff=uncertain,
            batch=build_compatibility_batch_from_handoff(uncertain),
        )
        new_handoff = rejected_handoff(
            requested_signal_ids=tuple(f"sig-{i:02d}" for i in range(5))
        )
        new_batch = build_compatibility_batch_from_handoff(new_handoff)
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )
