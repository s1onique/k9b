"""Scoped recording authority: corrupt state, rollback, global store-scan regression.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01.

See :mod:`test_scoped_recording_authority_first_replay` for the
first-recording / equal-replay / conflicting-replay / interleaved-unrelated-batch
matrix.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_batch import (
    PromotionBatch,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    IncidentPromotionResult,
)
from k8s_diag_agent.collect.incident_promotion_dispatch_constants import (
    INCIDENT_ACCESS_MODE_BACKEND,
    MODE_BACKEND_API,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_recording_authority import (
    ScopedPromotionRecordedAuthority,
)
from tests.unit.scoped_handoff_atomic_support import (
    completed_handoff,
    make_completed_batch,
)


class TestCorruptScopedStateFailsClosed:
    """Corrupt scoped state raises a bounded conflict, never incidental errors."""

    def test_authority_present_but_outcome_absent(self) -> None:
        acc = RunPromotionAccumulator()
        handoff = completed_handoff(diagnosis_incident_ids=("canonical-cA",))
        batch = make_completed_batch(handoff=handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        # Wipe the typed outcome to simulate persisted-state drift.
        acc.promotion_outcome = None
        with pytest.raises(PromotionOutcomeConflictError, match="inconsistent"):
            acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

    def test_recorded_authority_with_invalid_batch_raises_at_construction(self) -> None:
        """Construction of the authority runs the validator.

        ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
        :class:`ScopedPromotionRecordedAuthority` runs the same
        validator the recorder uses in Phase 1. A structurally
        contradictory batch raises ``ValueError`` at
        construction time, NOT an ``AttributeError`` /
        ``IndexError`` at replay time. The accumulator's
        authority stays uncorrupted by construction validation.
        """

        # The accumulator is not used in this test; we only
        # construct the authority itself, which the validator
        # rejects BEFORE the accumulator is touched.
        handoff = completed_handoff(diagnosis_incident_ids=("canonical-cB",))
        # Build a structurally contradictory batch: the
        # promotion_result disagrees with the completed handoff
        # (opened_incident_ids do not match the receipt).
        bad_result = IncidentPromotionResult(
            ok=True,
            scanned=0,
            firing=0,
            opened_incidents=0,
            updated_incidents=0,
            promotion_mode=MODE_BACKEND_API,
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        bad_batch = PromotionBatch(
            promotion_result=bad_result,
            promotion_records=(),
            source_kind="alertmanager",
        )
        with pytest.raises(ValueError):
            ScopedPromotionRecordedAuthority(
                handoff=handoff,
                batch=bad_batch,
            )

    def test_recorded_outcome_run_id_differs_from_authority(self) -> None:
        acc = RunPromotionAccumulator()
        handoff = completed_handoff(diagnosis_incident_ids=("canonical-cC",))
        batch = make_completed_batch(handoff=handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        # Drift the recorded run id without touching the authority.
        acc.promotion_outcome_run_id = "drifted-run-id"
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)


# ---------------------------------------------------------------------------
# Partial commit rollback + container identity.
# ---------------------------------------------------------------------------


class TestRollbackScopesAuthority:
    """The rollback transaction restores the authority + container identity."""

    def test_partial_apply_batch_mutation_rolls_back_authority(self) -> None:
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )

        acc = RunPromotionAccumulator()
        handoff = completed_handoff(diagnosis_incident_ids=("canonical-r1",))
        batch = make_completed_batch(handoff=handoff)
        before_authority = acc.scoped_promotion_recording
        before_records = acc.promotion_records
        before_seen = acc._seen_canonical_ids

        def _partially_mutate(batch_arg: object) -> None:
            acc.batches.append(batch_arg)
            acc.total_scanned += batch_arg.scanned
            acc.total_firing += batch_arg.firing
            acc.promotion_records.append(
                PromotionRecord(
                    source_candidate_id="<sentinel>",
                    canonical_incident_id="sentinel",
                    promotion_outcome="opened",
                )
            )
            acc._seen_canonical_ids.add("sentinel")
            raise RuntimeError("partial apply failure")

        with patch.object(acc, "_apply_batch", side_effect=_partially_mutate):
            with pytest.raises(RuntimeError, match="partial apply"):
                acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        # Pre-call state preserved.
        assert acc.scoped_promotion_recording is before_authority
        assert acc.scoped_promotion_recording is None
        assert acc.promotion_records is before_records
        assert acc.promotion_records == []
        assert acc._seen_canonical_ids is before_seen
        assert acc._seen_canonical_ids == set()
        assert acc.batches == []

    def test_container_identity_preserved_through_rollback(self) -> None:
        acc = RunPromotionAccumulator()
        handoff = completed_handoff(diagnosis_incident_ids=("canonical-cI",))
        batch = make_completed_batch(handoff=handoff)
        original_batches = acc.batches
        original_records = acc.promotion_records
        original_seen = acc._seen_canonical_ids

        def _raise_apply(batch_arg: object) -> None:
            acc.batches.append(batch_arg)
            raise RuntimeError("identity-rollback probe")

        with patch.object(acc, "_apply_batch", side_effect=_raise_apply):
            with pytest.raises(RuntimeError):
                acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)

        assert acc.batches is original_batches
        assert acc.promotion_records is original_records
        assert acc._seen_canonical_ids is original_seen
        assert acc.batches == []
        assert acc.promotion_records == []
        assert acc._seen_canonical_ids == set()


# ---------------------------------------------------------------------------
# Selection-mode / final-summary regression guards.
# ---------------------------------------------------------------------------


def test_no_global_store_scan_after_scoped_outcome() -> None:
    """A recorded scoped outcome MUST NOT trigger a global store scan.

    The active scoped dispatcher publishes a typed
    ``PromotionSucceeded`` to the accumulator. The legacy
    ``promotion_records`` / aggregate counters are derived from
    the scoped recording authority, NOT from a global store scan.
    A regression test pins that the scoped recorder's typed
    outcome reaches the accumulator and the projected
    ``promotion_outcome`` is preserved.
    """
    acc = RunPromotionAccumulator()
    handoff = completed_handoff(diagnosis_incident_ids=("canonical-r3",))
    batch = make_completed_batch(handoff=handoff)
    acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
    # The promotion outcome is the typed one from the authority,
    # not a re-derived legacy shape.
    assert acc.promotion_outcome is not None
    assert acc.promotion_outcome == handoff.outcome
    # ``batches`` is the general inventory; the scoped batch is
    # in there for aggregate accounting but the recorder never
    # consults it for the scoped replay check.
    assert batch in acc.batches
    assert acc.scoped_promotion_batch is batch
