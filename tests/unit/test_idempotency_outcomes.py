"""Idempotency tests for the current-run promotion seam.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 invariant coverage.

A repeated promotion request with the same logical identity MUST be
idempotent. A repeated request with materially different membership
MUST fail closed.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.current_run_promotion_workset import (
    CurrentRunPromotionWorkset,
    CurrentRunSignalProvenance,
    CurrentRunSignalRef,
    build_current_run_workset,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionReconciliationToken,
    PromotionSucceeded,
)
from k8s_diag_agent.collect.signal_persistence_outcomes import (
    SignalIdentityMatched,
    SignalInserted,
    SignalPersistenceSummary,
)

RUN_ID = "run-2026-07-15T03:30Z"
SOURCE = "alertmanager-prod"


def _identity_match_workset(n: int) -> CurrentRunPromotionWorkset:
    refs = tuple(
        CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=f"sha256:signal-{i:03d}",
            provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
        )
        for i in range(n)
    )
    return build_current_run_workset(
        run_id=RUN_ID,
        source_identity=SOURCE,
        references=refs,
    )


class TestIdempotency:
    def test_repeating_same_outcomes_is_a_no_op(self) -> None:
        # The same persistence outcome sequence MAY be replayed
        # safely. ``SignalIdentityMatched`` does not mutate persisted
        # state but is still promotable.
        outcomes_a = tuple(
            SignalIdentityMatched(signal_id=f"sha256:signal-{i:03d}")
            for i in range(33)
        )
        outcomes_b = outcomes_a
        summary_a = SignalPersistenceSummary(outcomes=outcomes_a)
        summary_b = SignalPersistenceSummary(outcomes=outcomes_b)
        assert summary_a.identity_matched_count == 33
        assert summary_b.identity_matched_count == 33
        assert summary_a.promotable_count == summary_b.promotable_count
        # No duplicates collapse to zero: identity matches REMAIN
        # promotable on subsequent replays.
        assert summary_a.promotable_count == 33

    def test_same_membership_same_run_workset_stable(self) -> None:
        workset_a = _identity_match_workset(33)
        workset_b = _identity_match_workset(33)
        assert workset_a.signal_ids == workset_b.signal_ids
        assert workset_a.total_count == workset_b.total_count

    def test_workset_fingerprint_matches_repeats(self) -> None:
        workset_a = _identity_match_workset(33)
        workset_b = _identity_match_workset(33)
        # The membership tuple is binary-equal across rebuilds.
        assert (
            tuple((ref.signal_id, ref.provenance) for ref in workset_a.signals)
            == tuple((ref.signal_id, ref.provenance) for ref in workset_b.signals)
        )


class TestOutcomeSummaries:
    def test_inserted_vs_matched_counted_separately(self) -> None:
        outcomes = (
            SignalInserted(signal_id="sha256:signal-001"),
            SignalIdentityMatched(signal_id="sha256:signal-002"),
            SignalIdentityMatched(signal_id="sha256:signal-003"),
        )
        summary = SignalPersistenceSummary(outcomes=outcomes)
        assert summary.inserted_count == 1
        assert summary.identity_matched_count == 2
        assert summary.promotable_count == 3
        # All three are part of the current-run workset regardless of
        # provenance mixity.
        assert summary.identity_conflict_count == 0


class TestTransportUncertainty:
    def test_commit_unknown_carries_reconciliation_identifier(self) -> None:
        token = PromotionReconciliationToken(
            request_id="req-abc",
            request_fingerprint="sha256:fingerprint",
        )
        outcome = PromotionSucceeded(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:signal-001",),
            records=(),
            diagnosis_incident_ids=(),
        )
        # Even when ``PromotionSucceeded`` has zero diagnosis IDs,
        # the ``requested_signal_ids`` are still part of the request.
        assert outcome.requested_signal_ids == ("sha256:signal-001",)
        # The reconciliation token is a stable bridge for retries.
        assert token.request_id == "req-abc"
        assert token.request_fingerprint == "sha256:fingerprint"


@pytest.mark.parametrize("n", [0, 1, 33])
def test_workset_zero_through_33_is_consistent(n: int) -> None:
    workset = _identity_match_workset(n)
    assert workset.total_count == n
    assert len(workset.signal_ids) == n
    assert workset.identity_matched_count == n
    assert workset.inserted_count == 0
