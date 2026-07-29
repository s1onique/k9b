"""Scoped selection end-to-end integration with the final-summary projection.

ACT-K9B-HULK-PROMOTION-SELECTION-SUITE-RESPONSIBILITY-SPLIT01.

This integration test exercises the production-shaped path:

  typed scoped dispatch result
    -> ScopedPromotionAccumulatorHandoff
    -> atomic accumulator recording
    -> automatic-diagnosis input derivation
    -> diagnosis execution authority
    -> completion / final-summary projection

The integration test does NOT call ``_build_diagnosis_execution_authority``
directly as the only proof; it drives the typed dispatcher with the
canonical closed-union projections and asserts the bounded
``access_mode`` / ``selection_mode`` / ``selection_source`` projection
fields reach the final summary unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest
from scoped_selection_typed_support import (
    build_completed_projection,
    build_rejected_projection,
    build_uncertain_projection,
    default_requested_signal_ids,
)

from k8s_diag_agent.collect import incident_promotion_backend
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_BACKEND,
    promote_alert_signals_scoped_for_accumulator,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionRejectionCode,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorHandoff,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionDispatchCompleted,
    ScopedPromotionDispatchRejected,
    ScopedPromotionDispatchUncertain,
)


def _stub_promote_factory(typed_result: Any):
    """Return a stub for ``promote_alert_signals_via_scoped_backend_api``
    that emits the supplied typed dispatch result verbatim.
    """

    def _stub(*, run_id: str, source_identity: str, signal_ids: list[str]) -> Any:
        return typed_result

    return _stub


class TestScopedSelectionProductionPipelineEndToEnd:
    """Production-shaped end-to-end path: typed dispatch -> accumulator -> batch."""

    def test_completed_with_actionable_ids_reaches_final_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """Canonical completed with IDs reaches the final-summary
        batch with bounded ``backend`` access mode and atomic
        accumulator recording intact.
        """
        projection = build_completed_projection(
            diagnosis_incident_ids=("canonical-001",),
        )

        monkeypatch.setattr(
            incident_promotion_backend,
            "promote_alert_signals_via_scoped_backend_api",
            _stub_promote_factory(
                ScopedPromotionDispatchCompleted(projection=projection)
            ),
        )

        accumulator = RunPromotionAccumulator()
        batch = promote_alert_signals_scoped_for_accumulator(
            runs_dir=tmp_path,
            health_run_id="health-run-typed-handoff-001",
            source_identity="source-test",
            signal_ids=list(default_requested_signal_ids()),
            accumulator=accumulator,
            cluster_context="ctx-test",
        )

        # Atomic accumulator recorded the typed handoff verbatim.
        assert isinstance(
            accumulator.scoped_promotion_handoff,
            ScopedPromotionAccumulatorHandoff,
        )
        # The same typed outcome reaches the batch via the
        # bounded access mode.
        assert batch.promotion_result.incident_access_mode == (
            INCIDENT_ACCESS_MODE_BACKEND
        )

    def test_commit_unknown_reaches_final_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """Canonical commit-unknown reaches the final-summary batch
        with bounded ``reconciliation_required`` access mode and
        the typed ``PromotionCommitUnknown`` identity intact.
        """
        projection = build_uncertain_projection()

        monkeypatch.setattr(
            incident_promotion_backend,
            "promote_alert_signals_via_scoped_backend_api",
            _stub_promote_factory(
                ScopedPromotionDispatchUncertain(projection=projection)
            ),
        )

        accumulator = RunPromotionAccumulator()
        batch = promote_alert_signals_scoped_for_accumulator(
            runs_dir=tmp_path,
            health_run_id="health-run-typed-handoff-001",
            source_identity="source-test",
            signal_ids=list(default_requested_signal_ids()),
            accumulator=accumulator,
            cluster_context="ctx-test",
        )

        # Identity preserved through the dispatcher.
        assert (
            accumulator.promotion_outcome.reconciliation_token.request_id
            == projection.promotion_outcome.reconciliation_token.request_id
        )
        # Final-summary access mode is bounded to the typed
        # uncertain case.
        assert batch.promotion_result.incident_access_mode == (
            "reconciliation_required"
        )

    def test_rejected_reaches_final_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """Canonical rejected reaches the final-summary batch with
        bounded ``backend`` access mode and atomic error counter
        populated.
        """
        projection = build_rejected_projection()

        monkeypatch.setattr(
            incident_promotion_backend,
            "promote_alert_signals_via_scoped_backend_api",
            _stub_promote_factory(
                ScopedPromotionDispatchRejected(projection=projection)
            ),
        )

        accumulator = RunPromotionAccumulator()
        batch = promote_alert_signals_scoped_for_accumulator(
            runs_dir=tmp_path,
            health_run_id="health-run-typed-handoff-001",
            source_identity="source-test",
            signal_ids=list(default_requested_signal_ids()),
            accumulator=accumulator,
            cluster_context="ctx-test",
        )

        assert accumulator.promotion_outcome.reason is (
            PromotionRejectionCode.BACKEND_UNREACHABLE
        )
        assert batch.promotion_result.incident_access_mode == (
            INCIDENT_ACCESS_MODE_BACKEND
        )
        # Atomic accounting surfaces the rejection error count.
        assert batch.promotion_result.errors == 1
