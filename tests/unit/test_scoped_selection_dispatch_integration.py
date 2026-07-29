"""Scoped selection dispatcher integration.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01.

These tests drive the active atomic accumulator path through
``promote_alert_signals_scoped_for_accumulator`` with a typed
backend spy that records the exact request arguments and
returns the supplied typed dispatch result.

The active atomic accumulator path is the canonical recording
route. The lower-level compatibility paths are exercised in
their own accumulator compatibility suite; this module asserts
the production-shaped atomic recording only.
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


class _TypedBackendSpy:
    """Typed spy that captures the canonical backend call shape.

    Implements the exact ``promote_alert_signals_via_scoped_backend_api``
    signature with named-only arguments and returns the supplied
    typed dispatch result. The captured call arguments are
    asserted against the dispatcher expectations.
    """

    def __init__(
        self,
        typed_result: Any,
    ) -> None:
        self._typed_result = typed_result
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        *,
        run_id: str,
        source_identity: str,
        signal_ids: list[str],
    ) -> Any:
        self.calls.append(
            {
                "run_id": run_id,
                "source_identity": source_identity,
                "signal_ids": list(signal_ids),
            }
        )
        return self._typed_result


def _drive_active_dispatch(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    typed_result: Any,
    health_run_id: str = "health-run-typed-handoff-001",
    source_identity: str = "source-test",
    cluster_context: str = "ctx-test",
) -> tuple[RunPromotionAccumulator, Any, _TypedBackendSpy]:
    """Drive the active atomic recorder path with a typed
    backend spy and return ``(accumulator, batch, spy)``.
    """
    spy = _TypedBackendSpy(typed_result)
    monkeypatch.setattr(
        incident_promotion_backend,
        "promote_alert_signals_via_scoped_backend_api",
        spy,
    )
    accumulator = RunPromotionAccumulator()
    expected_signal_ids = list(default_requested_signal_ids())
    batch = promote_alert_signals_scoped_for_accumulator(
        runs_dir=tmp_path,
        health_run_id=health_run_id,
        source_identity=source_identity,
        signal_ids=expected_signal_ids,
        accumulator=accumulator,
        cluster_context=cluster_context,
    )
    # The typed backend spy recorded exactly one call with the
    # canonical request arguments.
    assert len(spy.calls) == 1
    return accumulator, batch, spy


class TestScopedAccumulatorDispatchResultFingerprint:
    """Active dispatcher path is invoked with the typed dispatch result."""

    def test_promote_alert_signals_scoped_consumes_typed_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """The dispatcher must call the typed backend exactly
        once with the canonical request arguments and record
        the typed handoff verbatim."""
        projection = build_completed_projection()
        accumulator, batch, spy = _drive_active_dispatch(
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            typed_result=ScopedPromotionDispatchCompleted(
                projection=projection
            ),
        )
        # The typed backend spy recorded exactly one call with
        # the canonical request arguments.
        call = spy.calls[0]
        assert call["run_id"] == "health-run-typed-handoff-001"
        assert call["source_identity"] == "source-test"
        assert call["signal_ids"] == list(default_requested_signal_ids())
        assert len(call["signal_ids"]) == 34

        # The accumulator recorded the typed handoff verbatim.
        assert isinstance(
            accumulator.scoped_promotion_handoff,
            ScopedPromotionAccumulatorHandoff,
        )
        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert (
            accumulator.scoped_promotion_handoff.outcome
            is projection.promotion_outcome
        )
        assert (
            accumulator.scoped_promotion_handoff.receipt
            is projection.aggregate_receipt
        )
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
        """Commit-unknown carries the typed outcome by identity
        and the bounded ``reconciliation_required`` access mode.
        """
        projection = build_uncertain_projection()
        accumulator, batch, spy = _drive_active_dispatch(
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            typed_result=ScopedPromotionDispatchUncertain(
                projection=projection
            ),
        )
        # Typed backend spy recorded exactly one call.
        call = spy.calls[0]
        assert call["run_id"] == "health-run-typed-handoff-001"
        assert call["source_identity"] == "source-test"
        assert call["signal_ids"] == list(default_requested_signal_ids())

        # Identity preserved through the dispatcher.
        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert (
            accumulator.promotion_outcome.reconciliation_token
            is projection.promotion_outcome.reconciliation_token
        )
        assert (
            accumulator.promotion_outcome.reconciliation_token.request_id
            == DEFAULT_REQUEST_ID_UNCERTAIN
        )
        assert (
            accumulator.scoped_promotion_request_id
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
        """Rejected carries the typed outcome by identity and the
        bounded ``backend`` access mode with the atomic error
        counter populated.
        """
        projection = build_rejected_projection()
        accumulator, batch, spy = _drive_active_dispatch(
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            typed_result=ScopedPromotionDispatchRejected(
                projection=projection
            ),
        )
        # Typed backend spy recorded exactly one call.
        call = spy.calls[0]
        assert call["run_id"] == "health-run-typed-handoff-001"
        assert call["source_identity"] == "source-test"
        assert call["signal_ids"] == list(default_requested_signal_ids())

        assert accumulator.promotion_outcome is projection.promotion_outcome
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
