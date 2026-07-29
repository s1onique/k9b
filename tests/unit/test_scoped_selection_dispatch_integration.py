"""Scoped selection dispatcher integration tests.

ACT-K9B-HULK-PROMOTION-SELECTION-SUITE-RESPONSIBILITY-SPLIT01.

These tests exercise the active dispatcher path
(``promote_alert_signals_scoped_for_accumulator``) end-to-end
with the canonical closed-union projections for the
completed, uncertain and rejected outcomes. The
``ScopedPromotionAccumulator`` MUST receive the typed authority
untouched by identity and the resulting batch MUST carry the
bounded access mode.
"""

from __future__ import annotations

from typing import Any

import pytest
from scoped_selection_typed_support import (
    DEFAULT_REQUEST_ID_COMPLETED,
    DEFAULT_REQUEST_ID_REJECTED,
    DEFAULT_REQUEST_ID_UNCERTAIN,
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
    MODE_BACKEND_API,
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


def _stub_promote_factory(projection: Any):
    """Return a stub for ``promote_alert_signals_via_scoped_backend_api``
    that emits the supplied projection as a typed dispatch result.
    """

    def _stub(*, run_id: str, source_identity: str, signal_ids: list[str]) -> Any:
        # The dispatcher variation is encoded on the projection
        # itself; the stub returns the dispatch variant the
        # production-shaped integration case requires.
        return projection

    return _stub


class TestScopedAccumulatorDispatchResultFingerprint:
    """Active dispatcher path is invoked with the typed dispatch result."""

    def test_promote_alert_signals_scoped_consumes_typed_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """The dispatcher must call the typed accumulator handoff path."""
        projection = build_completed_projection()

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

        # The accumulator recorded the typed handoff verbatim.
        assert isinstance(
            accumulator.scoped_promotion_handoff,
            ScopedPromotionAccumulatorHandoff,
        )
        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert (
            accumulator.scoped_promotion_request_id
            == DEFAULT_REQUEST_ID_COMPLETED
        )

        # The batch carries the bounded access mode.
        assert batch.promotion_result.incident_access_mode == (
            INCIDENT_ACCESS_MODE_BACKEND
        )
        assert batch.promotion_result.promotion_mode == MODE_BACKEND_API

    def test_uncertain_batch_carries_reconciliation_required_access_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
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
            accumulator.scoped_promotion_request_id
            == DEFAULT_REQUEST_ID_UNCERTAIN
        )
        assert (
            accumulator.promotion_outcome.reconciliation_token.request_id
            == DEFAULT_REQUEST_ID_UNCERTAIN
        )
        assert batch.promotion_result.incident_access_mode == (
            "reconciliation_required"
        )

    def test_rejected_batch_carries_backend_access_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
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

        assert (
            accumulator.scoped_promotion_request_id
            == DEFAULT_REQUEST_ID_REJECTED
        )
        assert accumulator.promotion_outcome.reason is (
            PromotionRejectionCode.BACKEND_UNREACHABLE
        )
        assert batch.promotion_result.incident_access_mode == (
            INCIDENT_ACCESS_MODE_BACKEND
        )
        assert batch.promotion_result.errors == 1
