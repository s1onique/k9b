"""Core selection-algebra tests for the commit-unknown selection handoff.

ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01 +
ACT-K9B-HULK-PROMOTION-SUCCESSFUL-ZERO-ACCESS-MODE01.

This module covers the closed outcome-to-selection algebra. Production
witness tests live in
:mod:`tests.unit.test_act_k9b_hulk_commit_unknown_selection_handoff01_witness`.
Reusable builders live in
:mod:`tests.unit.act_k9b_hulk_commit_unknown_selection_handoff01_support`.

The matrix exhaustively pins the typed
``PromotionOutcome | None`` -> ``selection_mode`` /
``selection_source`` / ``incident_access_mode`` projection so:

* a recorded ``PromotionCommitUnknown`` ALWAYS maps to
  ``commit_unknown`` (NEVER to ``store_scan``);
* ``PromotionSucceeded(empty)`` preserves the dispatcher's actual
  transport authority (``backend`` or ``local``) instead of falling
  back to the no-attempt sentinel;
* ``store_scan`` requires ``promotion_outcome is None`` (the legacy
  fail-closed guard is preserved).
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelectionUnavailable,
    DiagnosisSelectionWithoutPromotion,
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
)

from .act_k9b_hulk_commit_unknown_selection_handoff01_support import (
    PRODUCTION_WITNESS_RUN_ID,
    StubAutomaticDiagnosisExecution,
    build_commit_unknown_ambiguous_response,
    build_promotion_rejected,
    build_promotion_succeeded_empty,
    build_promotion_succeeded_with_ids,
)

# ---------------------------------------------------------------------------
# Outcome-to-mode matrix (acceptance)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "outcome_factory",
        "expected_mode",
        "expected_source",
        "expected_access_mode",
        "expected_reconciliation",
        "dispatcher_access_mode",
    ),
    [
        # ACT-K9B-HULK-PROMOTION-SUCCESSFUL-ZERO-ACCESS-MODE01:
        # ``None`` + ``no_promotion_run`` dispatcher -> no-attempt sentinel.
        (
            lambda: None,
            INCIDENT_SELECTION_MODE_STORE_SCAN,
            DIAGNOSIS_SELECTION_SOURCE_EXPLICIT_NON_PROMOTION,
            INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
            False,
            INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
        ),
        # ``None`` + backend dispatcher -> backend transport preserved.
        (
            lambda: None,
            INCIDENT_SELECTION_MODE_STORE_SCAN,
            DIAGNOSIS_SELECTION_SOURCE_EXPLICIT_NON_PROMOTION,
            "backend",
            False,
            "backend",
        ),
        # ``PromotionSucceeded`` with non-empty IDs -> backend.
        (
            build_promotion_succeeded_with_ids,
            INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
            "backend",
            False,
            "backend",
        ),
        # ``PromotionSucceeded`` empty -> backend (zero IDs MUST NOT
        # collapse the transport authority).
        (
            build_promotion_succeeded_empty,
            INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
            "backend",
            False,
            "backend",
        ),
        # ``PromotionCommitUnknown`` -> ``reconciliation_required``.
        (
            build_commit_unknown_ambiguous_response,
            INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
            INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED,
            True,
            "backend",
        ),
        # ``PromotionRejected`` -> ``blocked``, preserves dispatcher mode.
        (
            build_promotion_rejected,
            INCIDENT_SELECTION_MODE_BLOCKED,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED,
            "backend",
            False,
            "backend",
        ),
        # ``PromotionSucceeded`` empty + local dispatcher -> local.
        (
            build_promotion_succeeded_empty,
            INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
            "local",
            False,
            "local",
        ),
    ],
)
def test_authority_outcome_to_mode_matrix(
    outcome_factory,
    expected_mode: str,
    expected_source: str,
    expected_access_mode: str,
    expected_reconciliation: bool,
    dispatcher_access_mode: str,
) -> None:
    """Every closed ``PromotionOutcome | None`` variant maps to a typed mode."""
    promotion_outcome = outcome_factory()
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode=dispatcher_access_mode,
    )
    assert authority.selection_mode == expected_mode
    assert authority.selection_source == expected_source
    assert authority.incident_access_mode == expected_access_mode
    assert authority.reconciliation_required is expected_reconciliation
    assert authority.promotion_outcome is promotion_outcome


# ---------------------------------------------------------------------------
# Fail-closed: every negative combination must raise BEFORE collector runs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("selection_mode", "promotion_outcome_factory", "expected_match"),
    [
        # commit_unknown + store_scan -- negative: modes inconsistent
        (
            INCIDENT_SELECTION_MODE_STORE_SCAN,
            build_commit_unknown_ambiguous_response,
            "does not accept a recorded promotion outcome",
        ),
        # success outcome + commit_unknown mode -- negative
        (
            INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
            build_promotion_succeeded_with_ids,
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
            build_promotion_rejected,
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
    from k8s_diag_agent.health.loop_runner_execute import (
        _build_diagnosis_selection_for_execution,
    )

    promotion_outcome = promotion_outcome_factory()
    execution = StubAutomaticDiagnosisExecution(
        should_run=True,
        selection_mode=selection_mode,
        incident_access_mode="backend",
    ).to_execution()
    with pytest.raises(Exception) as exc_info:
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=execution,
            promotion_outcome=promotion_outcome,
            canonical_incident_ids=[],
            scheduler_run_id=PRODUCTION_WITNESS_RUN_ID,
        )
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
            build_promotion_succeeded_with_ids,
        ),
        (
            INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
            build_promotion_succeeded_empty,
        ),
        (
            INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
            build_commit_unknown_ambiguous_response,
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
    from k8s_diag_agent.collect.diagnosis_selection import (
        DiagnosisSelectionFromPromotion,
        NoPromotionSelectionReason,
    )
    from k8s_diag_agent.health.loop_runner_execute import (
        _build_diagnosis_selection_for_execution,
    )

    promotion_outcome = promotion_outcome_factory()
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode="backend",
    )
    assert authority.selection_mode == selection_mode

    execution = StubAutomaticDiagnosisExecution(
        should_run=True,
        selection_mode=selection_mode,
        incident_access_mode="backend",
    ).to_execution()
    if selection_mode in (
        INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
        INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
    ):
        selection = _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=execution,
            promotion_outcome=promotion_outcome,
            canonical_incident_ids=list(
                promotion_outcome.diagnosis_incident_ids
            ),
            scheduler_run_id=PRODUCTION_WITNESS_RUN_ID,
        )
        assert isinstance(selection, DiagnosisSelectionFromPromotion)
    elif selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN:
        selection = _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=execution,
            promotion_outcome=promotion_outcome,
            canonical_incident_ids=[],
            scheduler_run_id=PRODUCTION_WITNESS_RUN_ID,
        )
        assert isinstance(selection, DiagnosisSelectionUnavailable)
    elif selection_mode == INCIDENT_SELECTION_MODE_STORE_SCAN:
        selection = _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=execution,
            promotion_outcome=promotion_outcome,
            canonical_incident_ids=[],
            scheduler_run_id=PRODUCTION_WITNESS_RUN_ID,
        )
        assert isinstance(selection, DiagnosisSelectionWithoutPromotion)
        assert (
            selection.reason is NoPromotionSelectionReason.SCHEDULED_SCAN_RUN
        )


# ---------------------------------------------------------------------------
# Authority object construction
# ---------------------------------------------------------------------------


def test_authority_is_frozen_and_carries_all_fields() -> None:
    """The authority is a frozen dataclass with all four selection fields."""
    promotion_outcome = build_commit_unknown_ambiguous_response()
    authority = DiagnosisExecutionAuthority(
        promotion_outcome=promotion_outcome,
        selection_mode=INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
        selection_source=DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
        incident_access_mode=INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED,
        reconciliation_required=True,
    )
    assert authority.promotion_outcome is promotion_outcome
    assert authority.selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN
    assert (
        authority.selection_source
        == DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN
    )
    assert (
        authority.incident_access_mode
        == INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED
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
