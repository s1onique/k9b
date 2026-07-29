"""Atomicity and idempotence tests for the scoped accumulator recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION03-
ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01.

These tests pin the validate-before-mutate contract. Each
conflict scenario is followed by a complete pre/post snapshot
diff: after a rejected mutation the accumulator MUST be
byte-for-byte identical to its pre-call state.

Two positive classes are pinned:

* New handoff -> ``PromotionOutcomeRecording.NEW``.
* Identical replay -> ``PromotionOutcomeRecording.IDEMPOTENT``,
  no field mutated, original objects retained by identity.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
    PromotionOutcomeRecording,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_recorder import (
    _build_compatibility_batch_from_handoff,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
)
from tests.unit.scoped_handoff_atomic_support import (
    accumulator_snapshot,
    completed_handoff,
    make_completed_batch,
    rejected_handoff,
    uncertain_handoff,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _commit_completed(acc: RunPromotionAccumulator) -> None:
    """Seed an accumulator with a single completed handoff/batch."""
    handoff = completed_handoff()
    batch = make_completed_batch(handoff=handoff)
    acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)


def _build_completed_handoff_with_request_id(
    *, request_id: str
) -> ScopedPromotionAccumulatorCompleted:
    """Construct a handoff identical to the seed except for ``request_id``."""
    base = completed_handoff()
    # All other fields stay identical so the only delta is the
    # request id (which still passes the SHA-256 + bounded
    # length validations in __post_init__).
    return ScopedPromotionAccumulatorCompleted(
        outcome=base.outcome,
        receipt=base.receipt,
        request_id=request_id,
        request_fingerprint=base.request_fingerprint,
    )


def _build_completed_handoff_with_fingerprint(
    *, fingerprint: str
) -> ScopedPromotionAccumulatorCompleted:
    base = completed_handoff()
    return ScopedPromotionAccumulatorCompleted(
        outcome=base.outcome,
        receipt=base.receipt,
        request_id=base.request_id,
        request_fingerprint=fingerprint,
    )


# ---------------------------------------------------------------------------
# First-recording path: NEW is returned.
# ---------------------------------------------------------------------------


class TestFirstRecordingReturnsNew:
    """The first atomic recording returns ``NEW`` and commits state."""

    def test_first_recording_returns_new_and_commits_outcome(self) -> None:
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-corr03",)
        )
        acc = RunPromotionAccumulator()
        batch = make_completed_batch(handoff=handoff)
        pre = accumulator_snapshot(acc)
        recording = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording is PromotionOutcomeRecording.NEW
        assert acc.scoped_promotion_handoff is handoff
        assert acc.promotion_outcome is handoff.outcome
        # Spot-check the aggregate delta vs. the pre snapshot.
        assert pre["promotion_records"] == []
        assert acc.batches == [batch]
        assert acc.last_promotion_mode == batch.promotion_mode
        assert acc.last_incident_access_mode == (
            batch.incident_access_mode
        )


# ---------------------------------------------------------------------------
# Atomicity: every conflict leaves the accumulator unchanged.
# ---------------------------------------------------------------------------


class TestConflictLeavesAccumulatorIntact:
    """Pre-call snapshot MUST equal the post-call snapshot for any conflict."""

    def test_conflicting_outcome_leaves_accumulator_intact(self) -> None:
        acc = RunPromotionAccumulator()
        _commit_completed(acc)
        before = accumulator_snapshot(acc)

        # Construct a materially different Completed outcome with a
        # different set of canonical IDs.
        different = completed_handoff(
            diagnosis_incident_ids=("canonical-X", "canonical-Y")
        )
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=different,
                batch=make_completed_batch(handoff=different),
            )

        assert accumulator_snapshot(acc) == before

    def test_same_outcome_different_request_id_leaves_intact(self) -> None:
        acc = RunPromotionAccumulator()
        _commit_completed(acc)
        before = accumulator_snapshot(acc)

        different_id = _build_completed_handoff_with_request_id(
            request_id="different-request-id-still-canonical",
        )
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=different_id,
                batch=make_completed_batch(handoff=different_id),
            )
        assert accumulator_snapshot(acc) == before

    def test_same_outcome_different_fingerprint_leaves_intact(self) -> None:
        acc = RunPromotionAccumulator()
        _commit_completed(acc)
        before = accumulator_snapshot(acc)

        different_fp = _build_completed_handoff_with_fingerprint(
            fingerprint="e" * 64,
        )
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=different_fp,
                batch=make_completed_batch(handoff=different_fp),
            )
        assert accumulator_snapshot(acc) == before

    def test_different_completed_receipt_leaves_intact(self) -> None:
        acc = RunPromotionAccumulator()
        _commit_completed(acc)
        before = accumulator_snapshot(acc)

        # Build a handoff that uses a syntactically valid but
        # materially different receipt (different opened IDs).
        different_receipt_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-other",),
        )
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=different_receipt_handoff,
                batch=make_completed_batch(
                    handoff=different_receipt_handoff
                ),
            )
        assert accumulator_snapshot(acc) == before

    def test_completed_to_uncertain_conflict_leaves_intact(self) -> None:
        acc = RunPromotionAccumulator()
        _commit_completed(acc)
        before = accumulator_snapshot(acc)

        uncertain = uncertain_handoff()
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=uncertain,
                batch=_build_compatibility_batch_from_handoff(uncertain),
            )
        assert accumulator_snapshot(acc) == before

    def test_uncertain_to_rejected_conflict_leaves_intact(self) -> None:
        acc = RunPromotionAccumulator()
        # Seed the accumulator with an uncertain handoff.
        uncertain = uncertain_handoff()
        acc.record_scoped_promotion_batch(
            handoff=uncertain,
            batch=_build_compatibility_batch_from_handoff(uncertain),
        )
        before = accumulator_snapshot(acc)

        rejected = rejected_handoff()
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=rejected,
                batch=_build_compatibility_batch_from_handoff(rejected),
            )
        assert accumulator_snapshot(acc) == before

    def test_invalid_handoff_construction_rejected_at_post_init(
        self,
    ) -> None:
        """A malformed handoff cannot be constructed at all.

        This protects the atomic recorder from a class of inputs
        where the caller smuggles in a handoff that violates
        __post_init__ invariants before the recorder sees it.
        """
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            ScopedPromotionAccumulatorCompleted,
        )

        base = completed_handoff()
        with pytest.raises(ValueError):
            # Empty request_id violates __post_init__.
            ScopedPromotionAccumulatorCompleted(
                outcome=base.outcome,
                receipt=base.receipt,
                request_id="",
                request_fingerprint=base.request_fingerprint,
            )


# ---------------------------------------------------------------------------
# Idempotence: equal replay retains installed identity.
# ---------------------------------------------------------------------------


class TestIdempotentReplayPreservesIdentity:
    """A semantically equal replay MUST NOT replace stored identity."""

    def test_same_handoff_object_same_batch_returns_idempotent(self) -> None:
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-corr03",)
        )
        acc = RunPromotionAccumulator()
        batch = make_completed_batch(handoff=handoff)

        recording_first = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording_first is PromotionOutcomeRecording.NEW
        stored_outcome = acc.promotion_outcome
        stored_handoff = acc.scoped_promotion_handoff

        # Replay with the EXACT same objects.
        recording_second = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording_second is PromotionOutcomeRecording.IDEMPOTENT
        # Identity preserved.
        assert acc.promotion_outcome is stored_outcome
        assert acc.scoped_promotion_handoff is stored_handoff

    def test_equal_newly_constructed_handoff_same_batch_returns_idempotent(
        self,
    ) -> None:
        original = completed_handoff(
            diagnosis_incident_ids=("canonical-corr03",),
        )
        acc = RunPromotionAccumulator()
        original_batch = make_completed_batch(handoff=original)
        recording_first = acc.record_scoped_promotion_batch(
            handoff=original, batch=original_batch
        )
        assert recording_first is PromotionOutcomeRecording.NEW
        stored_outcome = acc.promotion_outcome
        stored_handoff = acc.scoped_promotion_handoff

        # Build a NEW handoff that is semantically equal: same
        # outcome, same request_id, same request_fingerprint.
        # Reception is
        # ``__post_init__``-enforced identical, so the construction
        # is accepted and the equivalent replay triggers the
        # idempotent path.
        replayed = ScopedPromotionAccumulatorCompleted(
            outcome=original.outcome,
            receipt=original.receipt,
            request_id=original.request_id,
            request_fingerprint=original.request_fingerprint,
        )
        replayed_batch = make_completed_batch(handoff=replayed)
        recording_replay = acc.record_scoped_promotion_batch(
            handoff=replayed, batch=replayed_batch
        )
        assert recording_replay is PromotionOutcomeRecording.IDEMPOTENT
        assert acc.promotion_outcome is stored_outcome
        assert acc.scoped_promotion_handoff is stored_handoff


# ---------------------------------------------------------------------------
# Boundary cases on type-narrowing.
# ---------------------------------------------------------------------------


class TestAtomicRecorderBoundaries:
    """Strict input gates around the atomic recorder."""

    def test_non_handoff_payload_rejected(self) -> None:
        acc = RunPromotionAccumulator()
        batch = make_completed_batch(handoff=completed_handoff())
        with pytest.raises(TypeError):
            acc.record_scoped_promotion_batch(
                handoff="not-a-handoff",  # type: ignore[arg-type]
                batch=batch,
            )

    def test_non_batch_payload_rejected(self) -> None:
        acc = RunPromotionAccumulator()
        handoff = completed_handoff()
        with pytest.raises(TypeError):
            acc.record_scoped_promotion_batch(
                handoff=handoff,
                batch="not-a-batch",  # type: ignore[arg-type]
            )

    def test_batch_with_non_empty_records_rejected(self) -> None:
        """Scoped aggregate batches MUST NOT carry per-signal records."""
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )
        from k8s_diag_agent.collect.incident_promotion_batch import (
            PromotionBatch,
        )
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            INCIDENT_ACCESS_MODE_BACKEND,
            MODE_BACKEND_API,
            IncidentPromotionResult,
        )
        handoff = completed_handoff()
        bad_result = IncidentPromotionResult(
            ok=True,
            scanned=0,
            firing=0,
            opened_incidents=0,
            updated_incidents=0,
            promotion_mode=MODE_BACKEND_API,
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        bad_batch = PromotionBatch(
            promotion_result=bad_result,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="<smuggled>",
                    canonical_incident_id="c-smuggled",
                    promotion_outcome="opened",
                ),
            ),
            source_kind="alertmanager",
        )
        acc = RunPromotionAccumulator()
        with pytest.raises(ValueError, match="promotion_records"):
            acc.record_scoped_promotion_batch(
                handoff=handoff, batch=bad_batch
            )
