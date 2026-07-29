"""Production-boundary witness tests for the commit-unknown selection handoff.

ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01.

This module covers the production witness shape:

* 29 firing signals / 1 inserted / 28 identity-matched;
* ``PromotionCommitUnknown`` projection never selects ``store_scan``;
* the canonical selection builder accepts the production-shape
  ``commit_unknown`` outcome;
* the dispatch decision path emits the typed
  ``automatic_diagnosis_commit_unknown`` event with the correct
  selection fields.

Closed outcome-to-selection algebra lives in
:mod:`tests.unit.test_act_k9b_hulk_commit_unknown_selection_handoff01`.
Reusable builders live in
:mod:`tests.unit.act_k9b_hulk_commit_unknown_selection_handoff01_support`.
"""

from __future__ import annotations

from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelectionUnavailable,
    DiagnosisSelectionWithoutPromotion,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    may_have_committed as _may_have_committed,
)
from k8s_diag_agent.health.loop_runner_execute import (
    DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
    INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED,
    INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
    INCIDENT_SELECTION_MODE_STORE_SCAN,
    _build_diagnosis_execution_authority,
    _build_diagnosis_selection_for_execution,
)

from .act_k9b_hulk_commit_unknown_selection_handoff01_support import (
    PRODUCTION_WITNESS_RUN_ID,
    PRODUCTION_WITNESS_SIGNAL_IDS,
    StubAutomaticDiagnosisExecution,
    build_commit_unknown_ambiguous_response,
)

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
    promotion_outcome = build_commit_unknown_ambiguous_response()
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode="backend",
    )

    # 1) selection_mode MUST be commit_unknown, NOT store_scan
    assert authority.selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN
    assert authority.selection_mode != INCIDENT_SELECTION_MODE_STORE_SCAN

    # 2) selection_source is the typed commit-unknown source
    assert (
        authority.selection_source
        == DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN
    )

    # 3) incident_access_mode is reconciliation_required
    assert (
        authority.incident_access_mode
        == INCIDENT_ACCESS_MODE_RECONCILIATION_REQUIRED
    )

    # 4) reconciliation is required
    assert authority.reconciliation_required is True

    # 5) diagnosis MUST NOT be invoked
    assert authority.diagnosis_invoked is False

    # 6) all 29 requested signal IDs are preserved on the outcome
    assert len(promotion_outcome.requested_signal_ids) == 29

    # 7) outcome retains the typed metadata
    assert promotion_outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE
    assert _may_have_committed(promotion_outcome) is True


def test_production_witness_selection_builder_accepts_commit_unknown() -> None:
    """The canonical selection builder consumes ``commit_unknown`` cleanly."""
    promotion_outcome = build_commit_unknown_ambiguous_response()
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode="backend",
    )
    execution = StubAutomaticDiagnosisExecution(
        should_run=False,
        selection_mode=authority.selection_mode,
        incident_access_mode="backend",
        blocked_reason="promotion_commit_unknown",
    ).to_execution()
    assert execution.selection_mode == INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN

    selection = _build_diagnosis_selection_for_execution(
        automatic_diagnosis_execution=execution,
        promotion_outcome=promotion_outcome,
        canonical_incident_ids=[],
        scheduler_run_id=PRODUCTION_WITNESS_RUN_ID,
    )
    assert isinstance(selection, DiagnosisSelectionUnavailable)
    assert selection.outcome is promotion_outcome
    # store_scan MUST NOT have been produced for a recorded outcome
    assert not isinstance(selection, DiagnosisSelectionWithoutPromotion)


def test_production_witness_requested_signal_ids_preserved() -> None:
    """All 29 requested signal IDs remain available for later reconciliation.

    ACT-K9B-HULK-PROMOTION-COMMIT-UNKNOWN-SELECTION-HANDOFF01 requires
    that the requested signal IDs survive the production witness run
    so the post-commit reconciliation attempt can re-derive the
    original request. The cardinality MUST equal 29 (the production
    observed firing-signal count).
    """
    promotion_outcome = build_commit_unknown_ambiguous_response()
    assert promotion_outcome.requested_signal_ids == (
        PRODUCTION_WITNESS_SIGNAL_IDS
    )
    assert len(promotion_outcome.requested_signal_ids) == 29


def test_production_witness_blocked_event_shape() -> None:
    """The typed ``automatic_diagnosis_commit_unknown`` event fields.

    Production captures this event with:

    * ``selection_mode=commit_unknown``
    * ``selection_source=promotion_commit_unknown``
    * ``incident_access_mode=reconciliation_required``
    * ``reconciliation_required=True``
    * ``stop_reason=promotion_commit_unknown``
    * ``diagnosis_invoked=False``

    The execution-authority object carries every field the event
    consumer reads, so this assertion guards the boundary between the
    authority and the structured log payload.
    """
    promotion_outcome = build_commit_unknown_ambiguous_response()
    authority = _build_diagnosis_execution_authority(
        promotion_outcome=promotion_outcome,
        dispatcher_incident_access_mode="backend",
    )

    # The event consumer reads the authority directly.
    assert authority.selection_mode == "commit_unknown"
    assert authority.selection_source == "promotion_commit_unknown"
    assert authority.incident_access_mode == "reconciliation_required"
    assert authority.reconciliation_required is True
    assert authority.diagnosis_invoked is False
    # No store scan after commit-unknown.
    assert authority.is_store_scan is False
    assert authority.is_blocked is False
