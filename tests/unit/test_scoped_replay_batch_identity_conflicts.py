"""Replay-conflict field tests -- batch identity mismatches.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.
ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION05-
STRICT-TYPING-AND-ROLLBACK-CLOSURE01.

Split out of the original
:mod:`test_scoped_accumulator_replay_conflicts` matrix (CORRECTION05
file-size guard). Cluster context, snapshot bundle ID, and the
``skipped_duplicates`` counter are NOT in the validator's bounded
cross-variant check list, so they fall through to the dataclass
equality check in :func:`_batch_accounting_equivalent`. A
mismatch there raises :class:`PromotionOutcomeConflictError`
with a bounded identity-diff.
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
from tests.unit.scoped_handoff_atomic_support import (
    completed_handoff,
    make_completed_batch,
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


class TestBatchIdentityConflict:
    """Replay mutations the validator allows but the equivalence check rejects.

    Cluster context, snapshot bundle ID, and the skipped-duplicates
    counter are NOT in the validator's bounded cross-variant check
    list, so they fall through to the dataclass equality check in
    :func:`_batch_accounting_equivalent`. A mismatch there raises
    :class:`PromotionOutcomeConflictError` with a bounded
    identity-diff.
    """

    def test_invalid_cluster_context_raises_conflict(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_batch = replace(
            new_batch, cluster_context="ctx-mutated-replay"
        )
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_snapshot_bundle_id_raises_conflict(self) -> None:
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