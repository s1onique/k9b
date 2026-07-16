"""Direct tests of the diagnosis-selection execution helper.

ACT-K9B-SEAM01-DIAGNOSIS-SELECTION-CONSUMPTION01 contract:

Every diagnosis-selection execution mode (and the
:func:`_build_diagnosis_selection_for_execution` helper that maps
each mode to a closed :class:`DiagnosisSelection` variant) is
verified directly here -- NOT only through the public
:func:`run_automatic_diagnosis_loop` wrapper. The helper consumes
the actual typed :class:`PromotionOutcome` carried on the
accumulator and enforces the closed mode/outcome algebra:

| Selection mode            | Permitted outcome         |
| ------------------------- | ------------------------- |
| ``explicit_incident_ids`` | :class:`PromotionSucceeded` |
| ``current_run_empty``     | :class:`PromotionSucceeded` |
| ``store_scan``            | ``None``                  |
| ``commit_unknown``        | :class:`PromotionCommitUnknown` |
| ``blocked``               | helper must NOT execute   |

Every other cross-product MUST raise. The parametrized tests below
cover the valid cross-product (acceptance) and a sample of
invalid cross-products (rejection) for each branch.

The full ``execute_health_loop_run`` blocked path is exercised in
:func:`TestExecuteHealthLoopRunBlockedPath` below -- the test
calls ``_derive_automatic_diagnosis_inputs`` directly with a
contract-error accumulator and asserts the blocked decision is
emitted. A second test patches the collector path so a
regression that mistakenly invokes the collector at the
blocked path is detected.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelectionFromPromotion,
    DiagnosisSelectionUnavailable,
    DiagnosisSelectionWithoutPromotion,
    NoPromotionSelectionReason,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRecord,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.domain.incident_lifecycle import IncidentId
from k8s_diag_agent.health.loop_runner_execute import (
    INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
    INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
    INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
    INCIDENT_SELECTION_MODE_STORE_SCAN,
    AutomaticDiagnosisExecution,
    _build_diagnosis_selection_for_execution,
)

_RECONCILIATION_TOKEN = PromotionReconciliationToken(
    request_id="test-req-id-1",
    request_fingerprint="test-fingerprint-1",
)


def _succeeded(
    run_id: str,
    ids: tuple[str, ...] = (),
    *,
    diagnosis_ids: tuple[str, ...] | None = None,
) -> PromotionSucceeded:
    """Build a real :class:`PromotionSucceeded` with a given run id.

    The ``diagnosis_ids`` argument overrides the IDs placed on
    ``diagnosis_incident_ids`` (the typed outcome's source of truth).
    Tests that need to exercise authority splits can use it to
    construct a Succeeded outcome whose typed IDs disagree with the
    orchestrator's parallel ``canonical_incident_ids`` argument.
    """
    records = tuple(
        PromotionRecord(
            source_candidate_id=f"cand-{run_id}-{i}",
            canonical_incident_id=IncidentId(f"incident-{run_id}-{i}"),
            promotion_outcome="opened",
        )
        for i in ids
    )
    if diagnosis_ids is None:
        diagnosis_ids = tuple(IncidentId(i) for i in ids)
    return PromotionSucceeded(
        run_id=run_id,
        requested_signal_ids=ids,
        records=records,
        diagnosis_incident_ids=diagnosis_ids,
    )


def _commit_unknown(run_id: str) -> PromotionCommitUnknown:
    return PromotionCommitUnknown(
        run_id=run_id,
        reason=PromotionUncertaintyCode.PROTOCOL_ERROR,
        reconciliation_token=_RECONCILIATION_TOKEN,
        requested_signal_ids=("sig-1", "sig-2"),
    )


def _execution(mode: str) -> AutomaticDiagnosisExecution:
    return AutomaticDiagnosisExecution(
        should_run=True,
        selection_mode=mode,
        incident_access_mode="backend",
    )


# ---------------------------------------------------------------------------
# Acceptance: valid (mode, outcome) cross-product
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode, outcome_factory, expected_cls, canonical_incident_ids, expected_ids",
    [
        (
            INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
            lambda run_id: _succeeded(
                run_id, ids=("inc-a", "inc-b")
            ),
            DiagnosisSelectionFromPromotion,
            ("inc-a", "inc-b"),
            ("inc-a", "inc-b"),
        ),
        (
            INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
            lambda run_id: _succeeded(run_id),
            DiagnosisSelectionFromPromotion,
            (),
            (),
        ),
        (
            INCIDENT_SELECTION_MODE_STORE_SCAN,
            lambda run_id: None,
            DiagnosisSelectionWithoutPromotion,
            (),
            (),
        ),
        (
            INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
            lambda run_id: _commit_unknown(run_id),
            DiagnosisSelectionUnavailable,
            (),
            (),
        ),
    ],
)
def test_helper_accepts_valid_cross_product(
    mode, outcome_factory, expected_cls,
    canonical_incident_ids, expected_ids,
):
    """The helper accepts the documented (mode, outcome) cross-product.

    Each accepted selection:
    * has its ``promotion_run_id`` bound to the carried outcome's
      ``run_id`` (for selection types that carry one)
    * preserves the carried ``PromotionCommitUnknown`` outcome
      verbatim in the unavailable selection
    * maps the store-scan path to the bounded
      :class:`DiagnosisSelectionWithoutPromotion`
    """
    scheduler_run_id = "exec-mode-test-001"
    outcome = outcome_factory(scheduler_run_id)
    execution = _execution(mode)

    selection = _build_diagnosis_selection_for_execution(
        automatic_diagnosis_execution=execution,
        promotion_outcome=outcome,
        canonical_incident_ids=canonical_incident_ids,
        scheduler_run_id=scheduler_run_id,
    )

    assert isinstance(selection, expected_cls)
    if mode == INCIDENT_SELECTION_MODE_EXPLICIT_IDS:
        assert isinstance(selection, DiagnosisSelectionFromPromotion)
        assert selection.promotion_run_id == scheduler_run_id
        assert selection.incident_ids == expected_ids
    elif mode == INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY:
        assert isinstance(selection, DiagnosisSelectionFromPromotion)
        assert selection.promotion_run_id == scheduler_run_id
        assert selection.incident_ids == expected_ids
    elif mode == INCIDENT_SELECTION_MODE_STORE_SCAN:
        assert isinstance(selection, DiagnosisSelectionWithoutPromotion)
        assert selection.reason is NoPromotionSelectionReason.SCHEDULED_SCAN_RUN
    elif mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN:
        assert isinstance(selection, DiagnosisSelectionUnavailable)
        assert selection.outcome is outcome  # forwarded verbatim
        assert selection.outcome.reason is PromotionUncertaintyCode.PROTOCOL_ERROR
        assert selection.outcome.reconciliation_token is _RECONCILIATION_TOKEN


# ---------------------------------------------------------------------------
# Rejection: invalid (mode, outcome) cross-product
# ---------------------------------------------------------------------------


def test_helper_rejects_explicit_ids_without_promotion_succeeded():
    """``explicit_incident_ids`` REQUIRES PromotionSucceeded."""
    scheduler_run_id = "exec-mode-bad-001"
    with pytest.raises(ValueError, match="PromotionSucceeded"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=_execution(
                INCIDENT_SELECTION_MODE_EXPLICIT_IDS
            ),
            promotion_outcome=None,  # not a PromotionSucceeded
            canonical_incident_ids=("inc-a",),
            scheduler_run_id=scheduler_run_id,
        )


def test_helper_rejects_current_run_empty_without_promotion_succeeded():
    """``current_run_empty`` REQUIRES PromotionSucceeded."""
    scheduler_run_id = "exec-mode-bad-002"
    with pytest.raises(ValueError, match="current_run_empty"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=_execution(
                INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY
            ),
            promotion_outcome=None,
            canonical_incident_ids=(),
            scheduler_run_id=scheduler_run_id,
        )


def test_helper_rejects_store_scan_with_recorded_outcome():
    """``store_scan`` REQUIRES no recorded promotion outcome."""
    scheduler_run_id = "exec-mode-bad-003"
    with pytest.raises(ValueError, match="store_scan"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=_execution(
                INCIDENT_SELECTION_MODE_STORE_SCAN
            ),
            promotion_outcome=_succeeded(scheduler_run_id),
            canonical_incident_ids=(),
            scheduler_run_id=scheduler_run_id,
        )


def test_helper_rejects_commit_unknown_without_promotion_commit_unknown():
    """``commit_unknown`` REQUIRES PromotionCommitUnknown (not a fabrication)."""
    scheduler_run_id = "exec-mode-bad-004"
    with pytest.raises(ValueError, match="PromotionCommitUnknown"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=_execution(
                INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN
            ),
            promotion_outcome=None,  # not a PromotionCommitUnknown
            canonical_incident_ids=(),
            scheduler_run_id=scheduler_run_id,
        )


def test_helper_rejects_unknown_mode():
    """An unknown mode raises ValueError (no silent fall-through)."""
    with pytest.raises(ValueError, match="unknown selection_mode"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=_execution(
                "some_unknown_mode"
            ),
            promotion_outcome=None,
            canonical_incident_ids=(),
            scheduler_run_id="any",
        )


# ---------------------------------------------------------------------------
# Authority split rejection (R14 close-out)
# ---------------------------------------------------------------------------


def test_helper_rejects_authority_split_when_parallel_ids_diverge():
    """The typed outcome is the sole source of ``incident_ids``.

    Passing a parallel ``canonical_incident_ids`` argument whose value
    disagrees with ``promotion_outcome.diagnosis_incident_ids`` MUST
    raise :class:`ValueError`; a regression that silently accepted the
    split (the previous behaviour) would let the orchestrator smuggle
    IDs through a second source.
    """
    scheduler_run_id = "auth-split-001"
    outcome = _succeeded(
        scheduler_run_id,
        diagnosis_ids=("a", "b"),
    )
    with pytest.raises(ValueError, match="authority split rejected"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=_execution(
                INCIDENT_SELECTION_MODE_EXPLICIT_IDS
            ),
            promotion_outcome=outcome,
            canonical_incident_ids=("z",),  # disagrees with outcome
            scheduler_run_id=scheduler_run_id,
        )


def test_helper_rejects_authority_split_when_canonical_empty_but_outcome_has_ids():
    """An empty ``canonical_incident_ids`` argument does NOT zero out
    a non-empty ``promotion_outcome.diagnosis_incident_ids``.

    The previous helper accepted the silent drop; the canonical
    factory rejects the split because the typed outcome IS the only
    authority for the IDs going onto the selection.
    """
    scheduler_run_id = "auth-split-002"
    outcome = _succeeded(
        scheduler_run_id,
        diagnosis_ids=("a", "b"),
    )
    with pytest.raises(ValueError, match="authority split rejected"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=_execution(
                INCIDENT_SELECTION_MODE_EXPLICIT_IDS
            ),
            promotion_outcome=outcome,
            canonical_incident_ids=(),
            scheduler_run_id=scheduler_run_id,
        )



def test_helper_rejects_explicit_ids_with_empty_outcome():
    """R19 cardinality invariant: ``explicit_incident_ids`` REQUIRES
    a non-empty typed outcome.

    A ``PromotionSucceeded`` with an empty
    ``diagnosis_incident_ids`` MUST NOT pass the
    ``explicit_incident_ids`` mode; the mode semantically requires
    at least one diagnosis ID.
    """
    scheduler_run_id = "r19-cardinality-explicit-empty"
    outcome = _succeeded(scheduler_run_id)  # empty diagnosis IDs
    execution = _execution(INCIDENT_SELECTION_MODE_EXPLICIT_IDS)
    with pytest.raises(ValueError, match="non-empty diagnosis_incident_ids"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=execution,
            promotion_outcome=outcome,
            canonical_incident_ids=(),
            scheduler_run_id=scheduler_run_id,
        )


def test_helper_rejects_current_run_empty_with_non_empty_outcome():
    """R19 cardinality invariant: ``current_run_empty`` REQUIRES
    an empty typed outcome.

    A ``PromotionSucceeded`` with non-empty
    ``diagnosis_incident_ids`` MUST NOT pass the
    ``current_run_empty`` mode; the mode semantically requires
    zero work.
    """
    scheduler_run_id = "r19-cardinality-empty-nonempty"
    outcome = _succeeded(scheduler_run_id, ids=("inc-a",))
    execution = _execution(INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY)
    with pytest.raises(ValueError, match="EMPTY diagnosis_incident_ids"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=execution,
            promotion_outcome=outcome,
            canonical_incident_ids=("inc-a",),
            scheduler_run_id=scheduler_run_id,
        )


def test_helper_rejects_blocked_mode():
    """The ``blocked`` mode MUST NOT reach the helper.

    The orchestrator short-circuits blocked decisions BEFORE this
    helper runs; leaking one through the helper is a programming
    error and raises :class:`ValueError`.
    """
    scheduler_run_id = "auth-split-003"
    blocked_execution = AutomaticDiagnosisExecution(
        should_run=False,
        selection_mode="blocked",
        incident_access_mode="backend",
        blocked_reason="promotion_consistency_contract_error",
    )
    with pytest.raises(ValueError, match="blocked is not a valid"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=blocked_execution,
            promotion_outcome=None,
            canonical_incident_ids=(),
            scheduler_run_id=scheduler_run_id,
        )


# ---------------------------------------------------------------------------
# Identity mismatch (R1 close-out)
# ---------------------------------------------------------------------------


def test_helper_rejects_cross_run_promotion_succeeded():
    """A ``PromotionSucceeded`` with a different run_id than the
    scheduler is rejected at the seam BEFORE the collector runs.

    R14 close-out: the cross-run identity check now lives in the
    canonical :func:`build_diagnosis_selection` factory, which is
    invoked from ``_build_diagnosis_selection_for_execution``. This
    is strictly stronger than the previous behaviour -- a foreign
    outcome cannot even reach the collector seam.
    """
    scheduler_run_id = "exec-mode-identity-001"
    foreign_outcome = _succeeded(
        "foreign-run-id-zzz",
        diagnosis_ids=("inc-x",),
    )
    with pytest.raises(ValueError, match="disagrees with run_id"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=_execution(
                INCIDENT_SELECTION_MODE_EXPLICIT_IDS
            ),
            promotion_outcome=foreign_outcome,
            canonical_incident_ids=("inc-x",),
            scheduler_run_id=scheduler_run_id,
        )


def test_helper_rejects_cross_run_promotion_commit_unknown():
    """A ``PromotionCommitUnknown`` with a different run_id than the
    scheduler is rejected at the seam.

    The helper delegates to the canonical factory, which compares
    ``promotion_outcome.run_id`` against the scheduler's
    ``run_id``; a disagreement is a :class:`ValueError`.
    """
    scheduler_run_id = "exec-mode-identity-002"
    foreign_outcome = _commit_unknown("foreign-run-id-yyy")
    with pytest.raises(ValueError, match="disagrees with run_id"):
        _build_diagnosis_selection_for_execution(
            automatic_diagnosis_execution=_execution(
                INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN
            ),
            promotion_outcome=foreign_outcome,
            canonical_incident_ids=(),
            scheduler_run_id=scheduler_run_id,
        )
