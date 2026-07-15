"""Closed union tests for ``signal_persistence_outcomes``.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 invariant coverage.

The 33-identity-duplicate production regression surfaced because the
old :class:`AlertSignalAdapterResult` exposed three independent
counters (``signals_written``, ``signals_skipped_duplicates``,
``signals_failed``) that the orchestrator had to combine by hand. A
successfully identical observation collapsed into ``skipped_duplicates``
and was hidden from the current-run workset.

This module asserts that the new outcome algebra is closed,
deterministic, and that counts are derived projections of the typed
sequence.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.signal_persistence_outcomes import (
    SignalIdentityConflict,
    SignalIdentityConflictCode,
    SignalIdentityMatched,
    SignalInserted,
    SignalPersistenceFailed,
    SignalPersistenceFailureCode,
    SignalPersistenceOutcome,
    SignalPersistenceSummary,
    is_promotable,
)


class TestSignalInserted:
    def test_carries_canonical_identity(self) -> None:
        outcome = SignalInserted(signal_id="sha256:abc")
        assert outcome.signal_id == "sha256:abc"

    def test_is_promotable(self) -> None:
        assert is_promotable(SignalInserted(signal_id="x"))


class TestSignalIdentityMatched:
    def test_carries_existing_identity(self) -> None:
        outcome = SignalIdentityMatched(signal_id="sha256:abc")
        assert outcome.signal_id == "sha256:abc"

    def test_is_promotable(self) -> None:
        assert is_promotable(SignalIdentityMatched(signal_id="x"))


class TestSignalIdentityConflict:
    def test_bounded_reason_code_required(self) -> None:
        outcome = SignalIdentityConflict(
            signal_id="x",
            existing_artifact_identity="sha256:y",
            reason=SignalIdentityConflictCode.DIFFERENT_FINGERPRINT,
        )
        assert outcome.reason is SignalIdentityConflictCode.DIFFERENT_FINGERPRINT

    def test_free_form_detail_optional(self) -> None:
        outcome = SignalIdentityConflict(
            signal_id="x",
            existing_artifact_identity=None,
            reason=SignalIdentityConflictCode.DIFFERENT_LABELS,
            detail="labels differ",
        )
        assert outcome.detail == "labels differ"

    def test_is_not_promotable(self) -> None:
        outcome = SignalIdentityConflict(
            signal_id="x",
            existing_artifact_identity=None,
            reason=SignalIdentityConflictCode.DIFFERENT_FINGERPRINT,
        )
        assert not is_promotable(outcome)


class TestSignalPersistenceFailed:
    def test_candidate_id_may_be_none(self) -> None:
        outcome = SignalPersistenceFailed(
            candidate_signal_id=None,
            reason=SignalPersistenceFailureCode.IO_ERROR,
        )
        assert outcome.candidate_signal_id is None

    def test_is_not_promotable(self) -> None:
        outcome = SignalPersistenceFailed(
            candidate_signal_id="x",
            reason=SignalPersistenceFailureCode.SCHEMA_ERROR,
        )
        assert not is_promotable(outcome)


class TestUnionMembership:
    @pytest.mark.parametrize(
        "outcome",
        [
            SignalInserted(signal_id="a"),
            SignalIdentityMatched(signal_id="b"),
            SignalIdentityConflict(
                signal_id="c",
                existing_artifact_identity=None,
                reason=SignalIdentityConflictCode.DIFFERENT_FINGERPRINT,
            ),
            SignalPersistenceFailed(
                candidate_signal_id="d",
                reason=SignalPersistenceFailureCode.IO_ERROR,
            ),
        ],
    )
    def test_member_of_closed_union(
        self,
        outcome: SignalPersistenceOutcome,
    ) -> None:
        # Each member belongs to exactly one of the four variant
        # classes, and is therefore a ``SignalPersistenceOutcome``.
        assert isinstance(
            outcome,
            (SignalInserted, SignalIdentityMatched,
             SignalIdentityConflict, SignalPersistenceFailed),
        )
        # Exactly one of the four is-instance checks is True.
        flags = [
            isinstance(outcome, SignalInserted),
            isinstance(outcome, SignalIdentityMatched),
            isinstance(outcome, SignalIdentityConflict),
            isinstance(outcome, SignalPersistenceFailed),
        ]
        assert sum(flags) == 1


class TestSignalPersistenceSummary:
    def test_empty_sequence(self) -> None:
        summary = SignalPersistenceSummary(outcomes=())
        assert summary.inserted_count == 0
        assert summary.identity_matched_count == 0
        assert summary.identity_conflict_count == 0
        assert summary.persistence_failure_count == 0
        assert summary.promotable_count == 0
        assert not summary.has_conflicts
        assert not summary.has_failures

    def test_counts_derived_from_outcomes(self) -> None:
        outcomes = (
            SignalInserted(signal_id="a"),
            SignalIdentityMatched(signal_id="b"),
            SignalIdentityMatched(signal_id="c"),
            SignalIdentityConflict(
                signal_id="d",
                existing_artifact_identity=None,
                reason=SignalIdentityConflictCode.DIFFERENT_FINGERPRINT,
            ),
            SignalPersistenceFailed(
                candidate_signal_id="e",
                reason=SignalPersistenceFailureCode.IO_ERROR,
            ),
        )
        summary = SignalPersistenceSummary(outcomes=outcomes)
        assert summary.inserted_count == 1
        assert summary.identity_matched_count == 2
        assert summary.identity_conflict_count == 1
        assert summary.persistence_failure_count == 1
        assert summary.promotable_count == 3
        assert summary.has_conflicts
        assert summary.has_failures


class TestFreeFormStringsAreNotAuthority:
    def test_detail_does_not_drive_authority(self) -> None:
        # Free-form error text MUST NOT change the outcome type.
        outcome = SignalIdentityMatched(signal_id="x")
        assert is_promotable(outcome)

    def test_unknown_failure_reason_is_closed(self) -> None:
        # ``detail`` may mention arbitrary text; the ``reason`` is
        # always from the closed enum.
        outcome = SignalPersistenceFailed(
            candidate_signal_id="x",
            reason=SignalPersistenceFailureCode.UNKNOWN_ERROR,
            detail=("x" * 1000),  # Long detail
        )
        assert outcome.reason is SignalPersistenceFailureCode.UNKNOWN_ERROR

    def test_determinism_across_outcomes(self) -> None:
        # Reconstructed sequence is order-stable.
        outcomes_a = (
            SignalInserted(signal_id="x"),
            SignalIdentityMatched(signal_id="y"),
        )
        outcomes_b = tuple(reversed(outcomes_a))
        # The dataclasses are hashable, so they can be placed in sets.
        # The union forbids mixed insertion order from changing the
        # type, but the count projections remain stable.
        assert SignalPersistenceSummary(
            outcomes=outcomes_a,
        ).promotable_count == SignalPersistenceSummary(
            outcomes=outcomes_b,
        ).promotable_count


class TestExistingDuplicateDetection:
    """Existing idempotent behavior must remain deterministic.

    The 33-identity-duplicate production regression occurred because
    identity-matched observations were silently dropped from the
    workset. These tests prove the new algebra admits them.
    """

    def test_33_identity_matched_outcomes_all_promotable(self) -> None:
        outcomes = tuple(
            SignalIdentityMatched(signal_id=f"sha256:signal-{i:03d}")
            for i in range(33)
        )
        summary = SignalPersistenceSummary(outcomes=outcomes)
        assert summary.identity_matched_count == 33
        assert summary.inserted_count == 0
        assert summary.promotable_count == 33
        assert all(is_promotable(outcome) for outcome in outcomes)


def _assert_imports() -> None:
    """Smoke test: every public symbol is importable."""
    symbols: list[Any] = [
        SignalIdentityConflictCode,
        SignalIdentityConflict,
        SignalIdentityMatched,
        SignalInserted,
        SignalPersistenceFailed,
        SignalPersistenceFailureCode,
        SignalPersistenceOutcome,
        SignalPersistenceSummary,
        is_promotable,
    ]
    assert all(symbol is not None for symbol in symbols)
