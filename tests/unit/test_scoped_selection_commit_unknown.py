"""Scoped commit-unknown selection semantics.

ACT-K9B-HULK-PROMOTION-SELECTION-SUITE-RESPONSIBILITY-SPLIT01.

These tests pin the commit-unknown selection authority reaching
the diagnosis execution authority. The same ``PromotionCommitUnknown``
object MUST flow through the selection boundary with its
reconciliation identity preserved.
"""

from __future__ import annotations

from scoped_selection_typed_support import (
    build_uncertain_projection,
    default_requested_signal_ids,
)

from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_BACKEND,
)
from k8s_diag_agent.health.loop_runner_execute import (
    DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
    INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
    _build_diagnosis_execution_authority,
)


class TestCommitUnknownIdentityThroughSelection:
    """Commit-unknown identity flows into the selection handoff."""

    def test_commit_unknown_routes_to_commit_unknown_selection(self) -> None:
        projection = build_uncertain_projection()
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        assert (
            authority.selection_mode is INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN
        )
        assert (
            authority.selection_source
            is DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN
        )
        assert authority.reconciliation_required is True

    def test_commit_unknown_requested_signal_ids_preserved(self) -> None:
        projection = build_uncertain_projection()
        outcome = projection.promotion_outcome
        assert outcome.requested_signal_ids == default_requested_signal_ids()
