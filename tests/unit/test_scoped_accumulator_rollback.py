"""Rollback-after-mutation tests for the scoped atomic recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.
ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION05-
STRICT-TYPING-AND-ROLLBACK-CLOSURE01.

These tests verify the rollback-transaction contract: every
exception raised AFTER the recorder has begun mutating fields must
restore the accumulator to its pre-call state.

The previous design used module-level mutable probe slots so tests
could inject a failure at a specific commit point without
monkey-patching the host class. CORRECTION05 removed those probes
because global mutable production state is unsafe under parallel
tests or concurrent recorder calls. The current tests instead
monkey-patch the instance method via :func:`unittest.mock.patch.object`
to raise a bounded failure at a defined point, then assert the
canonical pre/post snapshot diff.

Every scenario:

1. Captures the accumulator's canonical ``_snapshot()`` BEFORE
   the call.
2. Monkey-patches one of the commit methods to raise a bounded
   failure at a defined point.
3. Invokes :meth:`record_scoped_promotion_batch`.
4. Asserts the call raises the bounded failure.
5. Re-captures the canonical snapshot AFTER the call.
6. Asserts every recorded field is byte-for-byte identical to
   the pre-call state.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

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
from tests.unit.scoped_handoff_atomic_support import (
    completed_handoff,
)


def _snapshot(acc: RunPromotionAccumulator) -> dict[str, Any]:
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

        def _raise_outcome(
            outcome: Any,
        ) -> PromotionOutcomeRecording:
            raise RuntimeError("simulated outcome-recording failure")

        with patch.object(
            acc, "record_promotion_outcome", side_effect=_raise_outcome
        ):
            with pytest.raises(RuntimeError, match="outcome-recording failure"):
                acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        after = _snapshot(acc)
        assert after == before
        assert acc.scoped_promotion_handoff is None

    def test_failure_after_outcome_recording_rolls_back_state(self) -> None:
        """An exception from ``_apply_batch`` restores every field."""
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-rollback-2",),
        )
        acc = RunPromotionAccumulator()
        batch = build_compatibility_batch_from_handoff(handoff)
        before = _snapshot(acc)

        def _raise_apply(batch_arg: Any) -> None:
            raise RuntimeError("simulated _apply_batch failure")

        with patch.object(acc, "_apply_batch", side_effect=_raise_apply):
            with pytest.raises(RuntimeError, match="_apply_batch failure"):
                acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        after = _snapshot(acc)
        assert after == before
        assert acc.scoped_promotion_handoff is None
        assert acc.promotion_outcome is None
        assert acc.promotion_outcome_run_id == ""
        assert acc.batches == []

    def test_partial_apply_batch_mutation_rolls_back_everything(self) -> None:
        """An exception AFTER several mutations in ``_apply_batch`` rolls back.

        This test simulates the most important rollback scenario for
        aggregate-accounting atomicity: ``_apply_batch`` mutates
        several totals/collections and then raises midway. The
        rollback transaction MUST restore every field, including
        the partially-mutated totals and the partially-appended
        batches list.
        """
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )

        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-partial-rollback",),
        )
        acc = RunPromotionAccumulator()
        batch = build_compatibility_batch_from_handoff(handoff)
        before = _snapshot(acc)

        def _partially_mutate_then_raise(batch_arg: Any) -> None:
            # Mutate batches list, several totals, and a ``last_*``
            # field -- the recorder should snapshot the pre-call
            # state and restore it.
            acc.batches.append(batch_arg)
            acc.total_scanned += batch_arg.scanned
            acc.total_firing += batch_arg.firing
            acc.total_opened_incidents += batch_arg.opened_incidents
            acc.last_source_kind = batch_arg.source_kind
            acc.last_promotion_mode = batch_arg.promotion_mode
            acc.last_incident_access_mode = batch_arg.incident_access_mode
            acc.promotion_records.append(
                PromotionRecord(
                    source_candidate_id="<sentinel>",
                    canonical_incident_id="sentinel",
                    promotion_outcome="opened",
                )
            )
            acc._seen_canonical_ids.add("sentinel")
            raise RuntimeError("simulated partial apply failure")

        with patch.object(
            acc, "_apply_batch", side_effect=_partially_mutate_then_raise
        ):
            with pytest.raises(RuntimeError, match="partial apply failure"):
                acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        after = _snapshot(acc)
        assert after == before
        # The pre-mutation state is exactly the one expected.
        assert acc.scoped_promotion_handoff is None
        assert acc.promotion_outcome is None
        assert acc.batches == []

    def test_container_identity_preserved_after_rollback(self) -> None:
        """The mutable containers keep their original identity post-rollback.

        External observers holding a reference to ``batches`` /
        ``promotion_records`` / ``_seen_canonical_ids`` MUST see
        the same Python object after a partial-batch rollback. The
        ``_restore`` path uses ``clear()``/``extend()`` /
        ``update()`` instead of replacing the field with a new
        container.
        """
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-identity-rollback",),
        )
        acc = RunPromotionAccumulator()
        batch = build_compatibility_batch_from_handoff(handoff)

        original_batches = acc.batches
        original_records = acc.promotion_records
        original_seen_ids = acc._seen_canonical_ids

        def _raise_apply(batch_arg: Any) -> None:
            acc.batches.append(batch_arg)
            acc.total_scanned += batch_arg.scanned
            raise RuntimeError("simulated identity-rollback failure")

        with patch.object(acc, "_apply_batch", side_effect=_raise_apply):
            with pytest.raises(RuntimeError, match="identity-rollback failure"):
                acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        assert acc.batches is original_batches
        assert acc.promotion_records is original_records
        assert acc._seen_canonical_ids is original_seen_ids
        # And the contents are pre-call (empty in this scenario).
        assert acc.batches == []
        assert acc.promotion_records == []
        assert acc._seen_canonical_ids == set()

    def test_no_failure_means_normal_recording_works(self) -> None:
        """Sanity: with no failure injected, recording commits normally."""
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

    def test_promotion_outcome_conflict_rolls_back_atomically(self) -> None:
        """A second recording for a different run raises conflict and rolls back.

        When ``record_promotion_outcome`` raises
        :class:`PromotionOutcomeConflictError`, the recorder MUST
        restore the snapshot before propagating the conflict.
        """
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict-rollback",),
        )
        acc = RunPromotionAccumulator()
        batch = build_compatibility_batch_from_handoff(handoff)

        def _raise_conflict(outcome: Any) -> PromotionOutcomeRecording:
            raise PromotionOutcomeConflictError(
                "Simulated outcome conflict",
                running_run_id=outcome.run_id,
                rejected_run_id=outcome.run_id,
                running_variant=type(outcome).__name__,
                rejected_variant=type(outcome).__name__,
            )

        with patch.object(
            acc, "record_promotion_outcome", side_effect=_raise_conflict
        ):
            with pytest.raises(PromotionOutcomeConflictError):
                acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        assert acc.scoped_promotion_handoff is None
        assert acc.promotion_outcome is None
        assert acc.batches == []
        assert acc.total_scanned == 0