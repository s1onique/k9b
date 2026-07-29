"""ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01 regression.

Live scheduler crash regression:

    outcome=commit_unknown (PromotionCommitUnknown)
    selection_mode=store_scan     # INCORRECT
    ValueError: store_scan mode does not accept a recorded promotion outcome

This test pins the closed outcome-to-selection algebra so a recorded
``PromotionCommitUnknown`` is ALWAYS projected to ``commit_unknown``,
NEVER to ``store_scan``, and the scheduler exits cleanly.

Production witness (29 firing signals / 1 inserted / 28 matched):
* 29 signals observed
* 1 SignalInserted, 28 SignalIdentityMatched
* 0 conflicts, 0 failures
* Dispatcher returns ``PromotionCommitUnknown(reason=ambiguous_response)``
* Reconciliation is required
* ``store_scan`` MUST NOT be selected
* Diagnosis MUST NOT be invoked
* Scheduler run completes without exception
* All 29 requested IDs remain available for later reconciliation
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelectionUnavailable,
    DiagnosisSelectionWithoutPromotion,
    NoPromotionSelectionReason,
)
from k8s_diag_agent.collect.incident_identity_hardening import PromotionRecord
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    may_have_committed as _may_have_committed,
)
from k8s_diag_agent.health.loop_runner_execute import (
    DIAGNOSIS_SELECTION_SOURCE_EXPLICIT_NON_PROMOTION,
    DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
    DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED,
    DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
    INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
    INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED,
    INCIDENT_SELECTION_MODE_BLOCKED,
    INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
    INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
    INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
    INCIDENT_SELECTION_MODE_STORE_SCAN,
    DiagnosisExecutionAuthority,
    _build_diagnosis_execution_authority,
    _build_diagnosis_selection_for_execution,
)

# ---------------------------------------------------------------------------
# Production witness fixtures
# ---------------------------------------------------------------------------


_RUN_ID = "health-run-20260729T050628Z"
_REQUESTED_SIGNAL_IDS: tuple[str, ...] = tuple(f"sig-{i:03d}" for i in range(29))


@dataclass(frozen=True)
class _StubAutomaticDiagnosisExecution:
    """Minimal stand-in for ``AutomaticDiagnosisExecution``."""

    should_run: bool
    selection_mode: str
    incident_access_mode: str
    blocked_reason: str | None = None


def _commit_unknown_ambiguous_response() -> PromotionCommitUnknown:
    """Return the production witness ``PromotionCommitUnknown``."""
    return PromotionCommitUnknown(
        run_id=_RUN_ID,
        reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
        reconciliation_token=PromotionReconciliationToken(
            request_id="req-29-ambiguous",
            request_fingerprint="sha256:production-witness",
        ),
        requested_signal_ids=_REQUESTED_SIGNAL_IDS,
    )


def _promotion_succeeded_with_ids() -> PromotionSucceeded:
    """Return a ``PromotionSucceeded`` carrying all 29 canonical IDs."""
    records = tuple(
        PromotionRecord(
            source_candidate_id=f"cand-{i}",
            canonical_incident_id=f"canonical-{i:03d}",
            promotion_outcome="opened",
        )
        for i in range(29)
    )
    return PromotionSucceeded(
        run_id=_RUN_ID,
        requested_signal_ids=_REQUESTED_SIGNAL_IDS,
        records=records,
        diagnosis_incident_ids=tuple(
            record.canonical_incident_id for record in records
        ),
    )


def _promotion_succeeded_empty() -> PromotionSucceeded:
    """Return a ``PromotionSucceeded`` with zero diagnosis IDs."""
    return PromotionSucceeded(
        run_id=_RUN_ID,
        requested_signal_ids=_REQUESTED_SIGNAL_IDS,
        records=(),
        diagnosis_incident_ids=(),
    )


def _promotion_rejected() -> PromotionRejected:
    """Return a ``PromotionRejected`` for the matrix test."""
    return PromotionRejected(
        run_id=_RUN_ID,
        reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
        rejected_signal_ids=_REQUESTED_SIGNAL_IDS,
    )


# ---------------------------------------------------------------------------
# Outcome-to-mode matrix (acceptance)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome_factory", "expected_mode", "expected_source", "expected_access_mode",
     "expected_reconciliation"),
    [
        (
            lambda: None,
            INCIDENT_SELECTION_MODE_STORE_SCAN,
            DIAGNOSIS_SELECTION_SOURCE_EXPLICIT_NON_PROMOTION,
            INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
            False,
        ),
        (
            _promotion_succeeded_with_ids,
            INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
            "backend",
            False,
        ),
        (
            _promotion_succeeded_empty,
            INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
            "backend",
            False,
        ),
        (
            _commit_unknown_ambiguous_response,
            INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
            INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED,
            True,
        ),
        (
            _promotion_rejected,
            INCIDENT_SELECTION_MODE_BLOCKED,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED,
            "backend",
            False,
        ),
    ],
)
def test_authority_outcome_to_mode_matrix(
    outcome_factory,
    expected_mode: str,
    expected_source: str,
    expected_access_mode: str,
    expected_reconciliation: bool,
) -> None:
    """Every closed ``PromotionOutcome | None`` variant maps to a typed mode."""
    promotion_outcome = outcome_factory()
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode="backend",
    )
    assert authority.selection_mode == expected_mode
    assert authority.selection_source == expected_source
    assert authority.incident_access_mode == expected_access_mode
    assert authority.reconciliation_required is expected_reconciliation
    assert authority.promotion_outcome is promotion_outcome


# ---------------------------------------------------------------------------
# Production-witness: 29 signals / 1 inserted / 28 matched / commit_unknown
# ---------------------------------------------------------------------------


def test_production_witness_commit_unknown_never_selects_store_scan() -> None:
    """Production witness: 29 signals, 1 inserted, 28 matched, commit_unknown.

    The live scheduler crash observed on
    ``run_id=health-run-20260729T050628Z`` was caused by an
    attempted promotion classified as ``commit_unknown`` being
    projected to ``selection_mode=store_scan``, which then tripped the
    typed guard. This test pins the corrected projection so the bug
    cannot regress.
    """
    promotion_outcome = _commit_unknown_ambiguous_response()
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode="backend",
    )

    # 1) selection_mode MUST be commit_unknown, NOT store_scan
    assert authority.selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN
    assert authority.selection_mode != INCIDENT_SELECTION_MODE_STORE_SCAN

    # 2) selection_source is the typed commit-unknown source
    assert authority.selection_source == (
        DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN
    )

    # 3) incident_access_mode is reconciliation_required
    assert authority.incident_access_mode == (
        INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED
    )

    # 4) reconciliation is required
    assert authority.reconciliation_required is True

    # 5) diagnosis MUST NOT be invoked
    assert authority.diagnosis_invoked is False

    # 6) all 29 requested signal IDs are preserved on the outcome
    assert len(promotion_outcome.requested_signal_ids) == 29

    # 7) outcome retains the typed metadata
    assert promotion_outcome.reason is (
        PromotionUncertaintyCode.AMBIGUOUS_RESPONSE
    )
    assert _may_have_committed(promotion_outcome) is True


def test_production_witness_selection_builder_accepts_commit_unknown() -> None:
    """The canonical selection builder consumes ``commit_unknown`` cleanly."""
    promotion_outcome = _commit_unknown_ambiguous_response()
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode="backend",
    )
    execution = _StubAutomaticDiagnosisExecution(
        should_run=False,
        selection_mode=authority.selection_mode,
        incident_access_mode="backend",
        blocked_reason="promotion_commit_unknown",
    )
    assert execution.selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN

    selection = _build_diagnosis_selection_for_execution(
        automatic_diagnosis_execution=execution,
        promotion_outcome=promotion_outcome,
        canonical_incident_ids=[],
        scheduler_run_id=_RUN_ID,
    )
    assert isinstance(selection, DiagnosisSelectionUnavailable)
    assert selection.outcome is promotion_outcome
    # store_scan MUST NOT have been produced for a recorded outcome
    assert not isinstance(selection, DiagnosisSelectionWithoutPromotion)


# ---------------------------------------------------------------------------
# Fail-closed: every negative combination must raise BEFORE collector runs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("selection_mode", "promotion_outcome_factory", "expected_match"),
    [
        # commit_unknown + store_scan -- negative: modes inconsistent
        (
            INCIDENT_SELECTION_MODE_STORE_SCAN,
            _commit_unknown_ambiguous_response,
            "does not accept a recorded promotion outcome",
        ),
        # success outcome + commit_unknown mode -- negative
        (
            INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
            _promotion_succeeded_with_ids,
            "requires PromotionCommitUnknown",
        ),
        # no outcome + explicit IDs -- negative
        (
            INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
            lambda: None,
            "requires PromotionSucceeded",
        ),
        # no outcome + current-run-empty -- negative
        (
            INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
            lambda: None,
            "requires PromotionSucceeded",
        ),
        # rejected outcome + store_scan -- negative
        (
            INCIDENT_SELECTION_MODE_STORE_SCAN,
            _promotion_rejected,
            "does not accept a recorded promotion outcome",
        ),
        # commit_unknown mode + None -- negative
        (
            INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
            lambda: None,
            "requires a PromotionCommitUnknown",
        ),
    ],
)
def test_negative_combinations_fail_closed(
    selection_mode: str,
    promotion_outcome_factory,
    expected_match: str,
) -> None:
    """Every negative (mode, outcome) combination MUST raise before
    the collector can execute. The fail-closed guard is preserved.
    """
    promotion_outcome = promotion_outcome_factory()
    execution = _StubAutomaticDiagnosisExecution(
        should_run=True,
        selection_mode=selection_mode,
        incident_access_mode="backend",
    )
    with pytest.raises(Exception) as exc_info:
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=execution,
            promotion_outcome=promotion_outcome,
            canonical_incident_ids=[],
            scheduler_run_id=_RUN_ID,
        )
    # Either a ValueError or a typed PromotionConsistencyContractError;
    # both carry the expected fragment.
    assert expected_match in str(exc_info.value), (
        f"expected {expected_match!r} in {exc_info.value!r}"
    )


# ---------------------------------------------------------------------------
# Invariants: every mode requires its typed outcome
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("selection_mode", "promotion_outcome_factory"),
    [
        (
            INCIDENT_SELECTION_MODE_STORE_SCAN,
            lambda: None,
        ),
        (
            INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
            _promotion_succeeded_with_ids,
        ),
        (
            INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
            _promotion_succeeded_empty,
        ),
        (
            INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
            _commit_unknown_ambiguous_response,
        ),
    ],
)
def test_authority_mode_invariants_hold(
    selection_mode: str,
    promotion_outcome_factory,
) -> None:
    """Every positive combination round-trips through the authority
    AND through the canonical selection builder.
    """
    promotion_outcome = promotion_outcome_factory()
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode="backend",
    )
    assert authority.selection_mode == selection_mode

    execution = _StubAutomaticDiagnosisExecution(
        should_run=True,
        selection_mode=selection_mode,
        incident_access_mode="backend",
    )
    if selection_mode in (
        INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
        INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
    ):
        selection = _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=execution,
            promotion_outcome=promotion_outcome,
            canonical_incident_ids=(
                list(promotion_outcome.diagnosis_incident_ids)
            ),
            scheduler_run_id=_RUN_ID,
        )
        # The closed typed selection must come out.
        from k8s_diag_agent.collect.diagnosis_selection import (
            DiagnosisSelectionFromPromotion,
        )
        assert isinstance(selection, DiagnosisSelectionFromPromotion)
    elif selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN:
        selection = _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=execution,
            promotion_outcome=promotion_outcome,
            canonical_incident_ids=[],
            scheduler_run_id=_RUN_ID,
        )
        assert isinstance(selection, DiagnosisSelectionUnavailable)
    elif selection_mode == INCIDENT_SELECTION_MODE_STORE_SCAN:
        selection = _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=execution,
            promotion_outcome=promotion_outcome,
            canonical_incident_ids=[],
            scheduler_run_id=_RUN_ID,
        )
        assert isinstance(selection, DiagnosisSelectionWithoutPromotion)
        assert selection.reason is NoPromotionSelectionReason.SCHEDULED_SCAN_RUN


# ---------------------------------------------------------------------------
# Authority object construction
# ---------------------------------------------------------------------------


def test_authority_is_frozen_and_carries_all_fields() -> None:
    """The authority is a frozen dataclass with all four selection fields."""
    promotion_outcome = _commit_unknown_ambiguous_response()
    authority = DiagnosisExecutionAuthority(
        promotion_outcome=promotion_outcome,
        selection_mode=INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
        selection_source=DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
        incident_access_mode=INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED,
        reconciliation_required=True,
    )
    assert authority.promotion_outcome is promotion_outcome
    assert authority.selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN
    assert authority.selection_source == (
        DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN
    )
    assert authority.incident_access_mode == (
        INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED
    )
    assert authority.reconciliation_required is True
    assert authority.is_commit_unknown is True
    assert authority.is_blocked is False
    assert authority.is_store_scan is False
    assert authority.is_current_run_empty is False
    assert authority.diagnosis_invoked is False
    with pytest.raises(Exception):
        # frozen dataclass: assignment must fail
        authority.selection_mode = INCIDENT_SELECTION_MODE_STORE_SCAN


def test_authority_assert_never_on_unknown_variant() -> None:
    """Future closed-union expansion that drops a variant must raise
    rather than silently fall through to ``store_scan``.
    """
    # Use a stub class that mimics a future closed-union variant
    # outside the current ``PromotionOutcome`` union. The
    # ``_build_diagnosis_execution_authority`` helper MUST NOT match
    # it (it's not a PromotionSucceeded / PromotionRejected /
    # PromotionCommitUnknown).
    class _FutureVariant:
        pass

    future = _FutureVariant()
    with pytest.raises((AssertionError, TypeError)):
        _build_diagnosis_execution_authority(
            promotion_outcome=future,
            dispatcher_incident_access_mode="backend",
        )
