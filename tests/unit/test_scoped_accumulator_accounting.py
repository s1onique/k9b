"""Aggregate accounting truth for the scoped accumulator recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION03-
ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01.

The atomic recorder preserves the same aggregate state as the
legacy ``add_batch`` path, with one exception: scoped aggregate
batches MUST NOT fabricate ``PromotionRecord`` entries. The
``promotion_records`` list therefore stays ``[]`` even when
non-zero opened / updated aggregates are carried by the
accompanying batch.

Each test pins one aggregate field and the empty-records invariant
together, so the focused matrix reads top-down as a complete
description of the scoped accounting truth.
"""

from __future__ import annotations

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_recorder import (
    _build_compatibility_batch_from_handoff,
)
from tests.unit.scoped_handoff_atomic_support import (
    completed_handoff,
    make_completed_batch,
    rejected_handoff,
    uncertain_handoff,
)

# ---------------------------------------------------------------------------
# Completed: aggregate fields are populated, records stay empty.
# ---------------------------------------------------------------------------


class TestCompletedAggregateAccounting:
    """Completed scoped aggregate accounting carries receipts/IDs, no records."""

    def test_completed_zero_ids_populates_scanned_firing_not_records(
        self,
    ) -> None:
        handoff = completed_handoff(
            requested_signal_ids=tuple(f"sig-{i:02d}" for i in range(34)),
            diagnosis_incident_ids=(),
        )
        acc = RunPromotionAccumulator()
        batch = make_completed_batch(handoff=handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        # Aggregate totals follow the batch.
        assert acc.total_scanned == 34
        assert acc.total_firing == 34
        assert acc.total_opened_incidents == 0
        assert acc.total_updated_incidents == 0
        assert acc.total_errors == 0
        # Source kind + scope + mode.
        assert acc.last_source_kind == "alertmanager"
        assert acc.last_incident_access_mode == "backend"
        assert acc.last_promotion_mode == "backend-api"
        # No per-signal record fabrication.
        assert acc.promotion_records == []
        assert acc._seen_canonical_ids == set()
        # Batch inventory carries exactly the one scoped batch.
        assert acc.batches == [batch]

    def test_completed_actionable_ids_populate_opened_aggregate(self) -> None:
        canonical_ids = ("canonical-corr03-a", "canonical-corr03-b")
        handoff = completed_handoff(
            requested_signal_ids=("sig-a", "sig-b"),
            diagnosis_incident_ids=canonical_ids,
        )
        acc = RunPromotionAccumulator()
        batch = make_completed_batch(handoff=handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        assert acc.total_scanned == 2
        assert acc.total_firing == 2
        assert acc.total_opened_incidents == len(canonical_ids)
        # Raw records MUST stay empty even when canonical IDs are present.
        assert acc.promotion_records == []

    def test_completed_records_carry_receipt_observation_unaffected(self) -> None:
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-keep",),
        )
        acc = RunPromotionAccumulator()
        batch = make_completed_batch(handoff=handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        # Bundled receipt aggregates propagate verbatim from the receipt.
        assert batch.promotion_result.observation_refreshed_incident_ids == tuple(
            handoff.receipt.observation_refreshed_incident_ids
        )
        assert batch.promotion_result.unchanged_incident_ids == tuple(
            handoff.receipt.unchanged_incident_ids
        )


# ---------------------------------------------------------------------------
# Uncertain: zero aggregate, access mode forced to "reconciliation_required".
# ---------------------------------------------------------------------------


class TestUncertainAggregateAccounting:
    """Uncertain accounting never fabricates records."""

    def test_uncertain_records_zero_aggregate(self) -> None:
        handoff = uncertain_handoff(
            requested_signal_ids=tuple(f"sig-{i:02d}" for i in range(7))
        )
        acc = RunPromotionAccumulator()
        batch = _build_compatibility_batch_from_handoff(handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        assert acc.total_scanned == 7
        assert acc.total_firing == 7
        assert acc.total_opened_incidents == 0
        assert acc.total_updated_incidents == 0
        assert acc.total_errors == 0
        assert acc.last_incident_access_mode == "reconciliation_required"
        assert acc.last_promotion_mode == "backend-api"
        assert acc.promotion_records == []


# ---------------------------------------------------------------------------
# Rejected: bounded error, access mode "backend", no records fabricated.
# ---------------------------------------------------------------------------


class TestRejectedAggregateAccounting:
    """Rejected accounting carries the bounded rejection projection."""

    def test_rejected_records_one_error_and_zero_records(self) -> None:
        handoff = rejected_handoff(
            requested_signal_ids=tuple(f"sig-{i:02d}" for i in range(4))
        )
        acc = RunPromotionAccumulator()
        batch = _build_compatibility_batch_from_handoff(handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        assert acc.total_scanned == 4
        assert acc.total_firing == 4
        assert acc.total_errors == 1
        assert acc.total_opened_incidents == 0
        assert acc.total_updated_incidents == 0
        assert acc.last_incident_access_mode == "backend"
        assert acc.last_promotion_mode == "backend-api"
        assert acc.promotion_records == []


# ---------------------------------------------------------------------------
# Source / cluster metadata
# ---------------------------------------------------------------------------


class TestSourceClusterMetadata:
    """The dispatcher supplies source kind and cluster metadata verbatim."""

    def test_source_kind_is_alertmanager_and_carries_cluster_context(
        self,
    ) -> None:
        handoff = completed_handoff()
        acc = RunPromotionAccumulator()
        batch = make_completed_batch(handoff=handoff)
        # Inject cluster context through the dispatcher projection so
        # the accounting batch is recognisable as cluster-tagged.
        from dataclasses import replace

        cluster_batch = replace(batch, cluster_context="ctx-corr03-atomic")
        acc.record_scoped_promotion_batch(
            handoff=handoff, batch=cluster_batch
        )
        # Source kind is preserved through the dispatcher projection.
        assert acc.batches[0].source_kind == "alertmanager"
        assert acc.batches[0].cluster_context == "ctx-corr03-atomic"
        assert acc.last_source_kind == "alertmanager"
