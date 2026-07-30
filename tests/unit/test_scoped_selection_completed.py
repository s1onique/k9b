"""Scoped completed selection semantics.

ACT-K9B-HULK-PROMOTION-SELECTION-SUITE-RESPONSIBILITY-SPLIT01.

These tests pin the completed-selection authority flowing out
of the typed accumulator handoff. The canonical aggregate
proof shape is ``records=()`` with the receipt as the only
authority: zero diagnosis IDs (aggregate successful zero) and
non-zero diagnosis IDs (actionable completed) MUST both
resolve to ``promotion_outcome_kind=succeeded`` with
``selection_mode`` ``current_run_empty`` or ``explicit_incident_ids``
respectively. A zero diagnosis-ID count MUST NOT collapse into
``no_promotion_run`` or ``store_scan``.
"""

from __future__ import annotations

from scoped_selection_typed_support import (
    build_completed_projection,
)

from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_BACKEND,
)
from k8s_diag_agent.health.loop_runner_execute import (
    DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
    INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
    INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
    _build_diagnosis_execution_authority,
)


class TestAggregateSuccessfulZeroThroughSelection:
    """Aggregate scoped success with zero diagnosis IDs stays a completed promotion."""

    def test_zero_diagnosis_ids_do_not_collapse_to_no_promotion_run(self) -> None:
        projection = build_completed_projection(
            diagnosis_incident_ids=()
        )
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        assert (
            authority.selection_mode
            is INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY
        )
        assert (
            authority.selection_source is DIAGNOSIS_SELECTION_SOURCE_PROMOTION
        )
        assert authority.incident_access_mode == INCIDENT_ACCESS_MODE_BACKEND
        assert authority.reconciliation_required is False

    def test_zero_diagnosis_ids_with_ids_do_not_collapse_to_no_promotion_run(
        self,
    ) -> None:
        projection = build_completed_projection(
            diagnosis_incident_ids=("canonical-001", "canonical-002"),
        )
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        assert (
            authority.selection_mode
            is INCIDENT_SELECTION_MODE_EXPLICIT_IDS
        )
        assert (
            authority.selection_source is DIAGNOSIS_SELECTION_SOURCE_PROMOTION
        )
        assert authority.incident_access_mode == INCIDENT_ACCESS_MODE_BACKEND
