"""Rollback-after-mutation tests for the scoped atomic recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.

These tests verify the rollback-transaction contract: every
exception raised AFTER the recorder has begun mutating fields must
restore the accumulator to its pre-call state. The probes
``_set_outcome_recording_probe`` and ``_set_apply_batch_probe`` let
each test inject a failure at a specific commit point without
monkey-patching the host class.

Every scenario:

1. Captures the accumulator's canonical ``_snapshot()`` BEFORE
   the call.
2. Installs a probe that raises a bounded failure.
3. Invokes :meth:`record_scoped_promotion_batch`.
4. Asserts the call raises the bounded failure.
5. Re-captures the canonical snapshot AFTER the call.
6. Asserts every recorded field is byte-for-byte identical to
   the pre-call state.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeRecording,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_projection import (
    build_compatibility_batch_from_handoff,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_recorder import (
    _clear_probes,
    _set_apply_batch_probe,
    _set_outcome_recording_probe,
)
from tests.unit.scoped_handoff_atomic_support import (
    completed_handoff,
)


def _snapshot(acc: RunPromotionAccumulator) -> dict[str, object]:
    """Return a JSON-serialisable snapshot of every accumulator field."""
    return {
        "promotion_records": list(acc.promotion_records),
        "_seen_canonical_ids": set(acc._seen_canonical_ids),
        "batches": list(acc.batches),
        "total_scanned": acc.total_scanned,
        "total_firing": acc.total_firing,
        "total_opened_incidents": acc.total_opened_incidents,
        "total_updated_incidents": acc.total_updated_incidents,
        "total_skipped_duplicates": acc.total_skipped_duplicates,
        "total_errors": acc.total_errors,
        "total_unique_candidate_count": acc.total_unique_candidate_count,
        "last_promotion_mode": acc.last_promotion_mode,
        "last_incident_access_mode": acc.last_incident_access_mode,
        "last_source_kind": acc.last_source_kind,
        "last_promotion_scan_scope": acc.last_promotion_scan_scope,
        "promotion_outcome": acc.promotion_outcome,
        "promotion_outcome_run_id": acc.promotion_outcome_run_id,
        "scoped_promotion_handoff": acc.scoped_promotion_handoff,
    }


@pytest.fixture(autouse=True)
def _reset_probes():
    """Ensure every test starts with the probe slots cleared."""
    _clear_probes()
    yield
    _clear_probes()


class TestRollbackAfterMutationBegins:
    """The rollback transaction survives any mid-mutation failure."""

    def test_failure_after_handoff_assignment_rolls_back_state(self) -> None:
        """An exception from ``record_promotion_outcome`` restores every field."""
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-rollback",),
        )
        acc = RunPromotionAccumulator()
        batch = build_compatibility_batch_from_handoff(handoff)
        before = _snapshot(acc)

        # Probe fires AFTER the handoff assignment, BEFORE
        # record_promotion_outcome is called. This is the
        # precise commit phase where mutation has already begun
        # (scoped_promotion_handoff has been set) but the outcome
        # has not been recorded.
        def _raise() -> None:
            raise RuntimeError("simulated outcome-recording failure")

        _set_outcome_recording_probe(_raise)

        with pytest.raises(RuntimeError, match="outcome-recording failure"):
            acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        after = _snapshot(acc)
        assert after == before
        # The pre-mutation handoff is exactly the one expected.
        assert acc.scoped_promotion_handoff is None

    def test_failure_after_outcome_recording_rolls_back_state(self) -> None:
        """An exception from ``_apply_batch`` restores every field."""
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-rollback-2",),
        )
        acc = RunPromotionAccumulator()
        batch = build_compatibility_batch_from_handoff(handoff)
        before = _snapshot(acc)

        # Probe fires AFTER record_promotion_outcome has returned
        # successfully. Both the handoff and the outcome are
        # already installed, so this is the strictest rollback
        # test: the snapshot must restore ALL atomic fields.
        def _raise() -> None:
            raise RuntimeError("simulated _apply_batch failure")

        _set_apply_batch_probe(_raise)

        with pytest.raises(RuntimeError, match="_apply_batch failure"):
            acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        after = _snapshot(acc)
        assert after == before
        assert acc.scoped_promotion_handoff is None
        assert acc.promotion_outcome is None
        assert acc.promotion_outcome_run_id == ""
        # The aggregate accounting batch is NOT installed.
        assert acc.batches == []

    def test_rollback_preserves_object_identity_for_typed_outcome(
        self,
    ) -> None:
        """Mutated identity fields are not part of the post-rollback state."""
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-rollback-id",),
        )
        acc = RunPromotionAccumulator()
        batch = build_compatibility_batch_from_handoff(handoff)

        def _raise() -> None:
            raise RuntimeError("id-rollback probe")

        _set_outcome_recording_probe(_raise)

        with pytest.raises(RuntimeError):
            acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        # Identity slots are exactly their pre-call identity: None
        # and "" -- the assignment + record cycle was rolled back.
        assert acc.scoped_promotion_handoff is None
        assert acc.promotion_outcome is None
        assert acc.promotion_outcome_run_id == ""
        assert acc.batches == []

    def test_no_probe_means_normal_recording_works(self) -> None:
        """Sanity: with no probe installed, recording commits normally."""
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-no-probe",),
        )
        acc = RunPromotionAccumulator()
        batch = build_compatibility_batch_from_handoff(handoff)

        recording = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording is PromotionOutcomeRecording.NEW
        assert acc.scoped_promotion_handoff is handoff
        assert acc.batches == [batch]
