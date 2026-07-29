"""Scoped recording authority: first recording, equal replay, conflicting replay, interleaved unrelated batch.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01.

See :mod:`test_scoped_recording_authority_interleaved_corrupt` for the
corrupt-state, rollback, and global-scan siblings.
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
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_projection import (
    build_compatibility_batch_from_handoff,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_recording_authority import (
    ScopedPromotionRecordedAuthority,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorRejected,
    ScopedPromotionAccumulatorUncertain,
)
from tests.unit.scoped_handoff_atomic_support import (
    completed_handoff,
    make_completed_batch,
    rejected_handoff,
    uncertain_handoff,
)

# ---------------------------------------------------------------------------
# First-recording path: each variant commits the single authority.
# ---------------------------------------------------------------------------


class TestFirstRecordingAllVariants:
    """The first atomic recording commits a single authority for every variant."""

    def test_first_completed_recording_commits_authority(self) -> None:
        acc = RunPromotionAccumulator()
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-A",),
        )
        batch = make_completed_batch(handoff=handoff)
        recording = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording is PromotionOutcomeRecording.NEW
        # The single authority is stored.
        assert isinstance(
            acc.scoped_promotion_recording,
            ScopedPromotionRecordedAuthority,
        )
        assert acc.scoped_promotion_recording.handoff is handoff
        assert acc.scoped_promotion_recording.batch is batch
        # Derived projections come from the authority.
        assert acc.scoped_promotion_handoff is handoff
        assert acc.scoped_promotion_batch is batch
        assert acc.scoped_promotion_request_id == handoff.request_id
        assert (
            acc.scoped_promotion_request_fingerprint
            == handoff.request_fingerprint
        )

    def test_first_uncertain_recording_commits_authority(self) -> None:
        acc = RunPromotionAccumulator()
        handoff = uncertain_handoff()
        batch = build_compatibility_batch_from_handoff(handoff)
        recording = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording is PromotionOutcomeRecording.NEW
        assert isinstance(
            acc.scoped_promotion_recording,
            ScopedPromotionRecordedAuthority,
        )
        assert isinstance(
            acc.scoped_promotion_handoff,
            ScopedPromotionAccumulatorUncertain,
        )

    def test_first_rejected_recording_commits_authority(self) -> None:
        acc = RunPromotionAccumulator()
        handoff = rejected_handoff()
        batch = build_compatibility_batch_from_handoff(handoff)
        recording = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording is PromotionOutcomeRecording.NEW
        assert isinstance(
            acc.scoped_promotion_recording,
            ScopedPromotionRecordedAuthority,
        )
        assert isinstance(
            acc.scoped_promotion_handoff,
            ScopedPromotionAccumulatorRejected,
        )


# ---------------------------------------------------------------------------
# Identical-replay path: each variant returns IDEMPOTENT and preserves
# the stored authority by identity.
# ---------------------------------------------------------------------------


class TestEqualReplayAllVariants:
    """Equal replay of each variant returns IDEMPOTENT and preserves identity."""

    def test_equal_completed_replay_is_idempotent(self) -> None:
        acc = RunPromotionAccumulator()
        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-replay-c",),
        )
        batch = make_completed_batch(handoff=handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        stored_authority = acc.scoped_promotion_recording
        stored_outcome = acc.promotion_outcome

        replay = acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        assert replay is PromotionOutcomeRecording.IDEMPOTENT
        assert acc.scoped_promotion_recording is stored_authority
        assert acc.promotion_outcome is stored_outcome

    def test_equal_uncertain_replay_is_idempotent(self) -> None:
        acc = RunPromotionAccumulator()
        handoff = uncertain_handoff()
        batch = build_compatibility_batch_from_handoff(handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        stored_authority = acc.scoped_promotion_recording

        replay = acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        assert replay is PromotionOutcomeRecording.IDEMPOTENT
        assert acc.scoped_promotion_recording is stored_authority

    def test_equal_rejected_replay_is_idempotent(self) -> None:
        acc = RunPromotionAccumulator()
        handoff = rejected_handoff()
        batch = build_compatibility_batch_from_handoff(handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        stored_authority = acc.scoped_promotion_recording

        replay = acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        assert replay is PromotionOutcomeRecording.IDEMPOTENT
        assert acc.scoped_promotion_recording is stored_authority


# ---------------------------------------------------------------------------
# Conflicting replay: each variant raises bounded conflict.
# ---------------------------------------------------------------------------


class TestConflictingReplayAllVariants:
    """A conflicting replay for each variant raises a bounded conflict."""

    def test_completed_to_completed_conflict(self) -> None:
        acc = RunPromotionAccumulator()
        seed = completed_handoff(diagnosis_incident_ids=("canonical-c1",))
        acc.record_scoped_promotion_batch(
            handoff=seed,
            batch=make_completed_batch(handoff=seed),
        )

        different = completed_handoff(
            diagnosis_incident_ids=("canonical-c2",),
        )
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=different,
                batch=make_completed_batch(handoff=different),
            )

    def test_completed_to_uncertain_conflict(self) -> None:
        acc = RunPromotionAccumulator()
        seed = completed_handoff(diagnosis_incident_ids=("canonical-u1",))
        acc.record_scoped_promotion_batch(
            handoff=seed,
            batch=make_completed_batch(handoff=seed),
        )

        new_handoff = uncertain_handoff()
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff,
                batch=build_compatibility_batch_from_handoff(new_handoff),
            )

    def test_completed_to_rejected_conflict(self) -> None:
        acc = RunPromotionAccumulator()
        seed = completed_handoff(diagnosis_incident_ids=("canonical-r1",))
        acc.record_scoped_promotion_batch(
            handoff=seed,
            batch=make_completed_batch(handoff=seed),
        )

        new_handoff = rejected_handoff()
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff,
                batch=build_compatibility_batch_from_handoff(new_handoff),
            )


# ---------------------------------------------------------------------------
# Interleaved unrelated batch before replay.
# ---------------------------------------------------------------------------


class TestInterleavedUnrelatedBatch:
    """Unrelated batches added between recordings do NOT change the replay result."""

    def test_unrelated_batch_does_not_displace_replay_batch(self) -> None:
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

        acc = RunPromotionAccumulator()
        seed = completed_handoff(diagnosis_incident_ids=("canonical-i1",))
        batch_seed = make_completed_batch(handoff=seed)
        acc.record_scoped_promotion_batch(handoff=seed, batch=batch_seed)
        stored_authority = acc.scoped_promotion_recording

        # Append an unrelated aggregate batch via the legacy
        # ``add_batch`` path. The recorder's general ``batches``
        # list now contains two entries.
        unrelated_result = IncidentPromotionResult(
            ok=True,
            scanned=1,
            firing=1,
            opened_incidents=0,
            updated_incidents=0,
            promotion_mode=MODE_BACKEND_API,
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        unrelated_batch = PromotionBatch(
            promotion_result=unrelated_result,
            promotion_records=(),
            source_kind="alertmanager",
            cluster_context="unrelated-cluster",
            snapshot_bundle_id=None,
        )
        acc.add_batch(unrelated_batch)

        # Replay the same scoped handoff + batch and confirm
        # the scoped authority is preserved by identity.
        replay = acc.record_scoped_promotion_batch(
            handoff=seed, batch=batch_seed
        )
        assert replay is PromotionOutcomeRecording.IDEMPOTENT
        assert acc.scoped_promotion_recording is stored_authority
        # The general batches list still carries both the
        # scoped batch and the unrelated batch.
        assert batch_seed in acc.batches
        assert unrelated_batch in acc.batches

    def test_unrelated_batch_then_conflicting_replay_raises(self) -> None:
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

        acc = RunPromotionAccumulator()
        seed = completed_handoff(diagnosis_incident_ids=("canonical-i2",))
        batch_seed = make_completed_batch(handoff=seed)
        acc.record_scoped_promotion_batch(handoff=seed, batch=batch_seed)

        unrelated_result = IncidentPromotionResult(
            ok=True,
            scanned=1,
            firing=1,
            opened_incidents=0,
            updated_incidents=0,
            promotion_mode=MODE_BACKEND_API,
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        unrelated_batch = PromotionBatch(
            promotion_result=unrelated_result,
            promotion_records=(),
            source_kind="alertmanager",
        )
        acc.add_batch(unrelated_batch)

        conflicting = completed_handoff(
            diagnosis_incident_ids=("canonical-i3",),
        )
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=conflicting,
                batch=make_completed_batch(handoff=conflicting),
            )


# ---------------------------------------------------------------------------
# Corrupt-state tests.
# ---------------------------------------------------------------------------


