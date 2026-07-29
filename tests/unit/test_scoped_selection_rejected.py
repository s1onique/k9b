"""Scoped rejected selection semantics.

ACT-K9B-HULK-PROMOTION-SELECTION-SUITE-RESPONSIBILITY-SPLIT01.

These tests pin the rejection-authority routing flowing out of
the typed accumulator handoff. The same ``PromotionRejected``
object MUST reach the selection handoff unchanged by identity
and MUST resolve to ``selection_mode=blocked`` with
``selection_source=promotion_blocked`` and
``reconciliation_required=False``.
"""

from __future__ import annotations

from scoped_selection_typed_support import build_rejected_projection

from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_BACKEND,
)
from k8s_diag_agent.health.loop_runner_execute import (
    DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED,
    INCIDENT_SELECTION_MODE_BLOCKED,
    _build_diagnosis_execution_authority,
)


class TestRejectionAuthorityThroughSelection:
    """Rejection authority flows into the selection handoff as blocked."""

    def test_rejected_routes_to_blocked_selection(self) -> None:
        projection = build_rejected_projection()
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        assert authority.selection_mode is INCIDENT_SELECTION_MODE_BLOCKED
        assert (
            authority.selection_source
            is DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED
        )
        assert authority.reconciliation_required is False
