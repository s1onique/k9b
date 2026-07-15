"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 typed rejection tests.

Covers invariant O7 (typed pre-commit rejection through the production
path).

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.promotion_dispatch_outcome import (
    PromotionRequestValidationError,
    PromotionScopeError,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionRejectionCode,
    is_rejected,
)
from k8s_diag_agent.health.loop_alertmanager_snapshot_signals import (
    AlertSignalPromotionDispatchResult,
    _ingest_alert_signals,
)

from .incident_current_run_promotion_dispatch_outcome01_support import (
    RUN_ID,
    CapturingLog,
    build_alert,
    build_snapshot,
    build_source,
    persist_signals,
    stub_dispatch_raises,
)


class TestProductionPathTypedRejection:
    """``PromotionRequestValidationError`` / ``PromotionScopeError``
    raised by the real production dispatcher must classify into
    :class:`PromotionRejected` -- not :class:`PromotionCommitUnknown`.
    """

    def _run_with_dispatcher_exception(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
        exc: BaseException,
    ) -> tuple[RunPromotionAccumulator, CapturingLog, AlertSignalPromotionDispatchResult]:
        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 3)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        stub_dispatch_raises(monkeypatch, exc)

        snapshot = build_snapshot([build_alert(i) for i in range(3)])
        log = CapturingLog()
        result = _ingest_alert_signals(
            snapshot=snapshot,
            selected_source=build_source(),
            snapshot_path=None,
            directories={"root": runs_dir},
            incident_store=None,
            log_event=log,
            run_id=RUN_ID,
            run_label="run-2026-07-15T0340Z",
            effective_cluster_context=None,
            promotion_accumulator=accumulator,
        )
        return accumulator, log, result

    def test_promotion_request_validation_error_propagation(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from k8s_diag_agent.collect import (
            promotion_dispatch_outcome as cls_module,
        )

        spy_calls: list[dict] = []

        original_classifier = cls_module.classify_promotion_dispatch_result

        def classifier_spy(*, run_id: str, **kwargs: Any) -> Any:
            spy_calls.append(kwargs)
            return original_classifier(run_id=run_id, **kwargs)

        monkeypatch.setattr(
            cls_module,
            "classify_promotion_dispatch_result",
            classifier_spy,
        )

        accumulator, log, result = self._run_with_dispatcher_exception(
            tmp_path,
            monkeypatch,
            PromotionRequestValidationError("bad signal ids"),
        )

        assert len(spy_calls) == 1
        assert isinstance(
            spy_calls[0]["outcome"],
            PromotionRequestValidationError,
        )
        assert is_rejected(result.outcome)
        assert result.outcome.reason is (
            PromotionRejectionCode.MALFORMED_SIGNAL_IDS
        )
        assert is_rejected(accumulator.promotion_outcome)
        assert accumulator.canonical_incident_ids() == []
        projection = log.by_event(
            "promotion-dispatch-outcome-classified",
        )[0]
        assert projection["promotion_outcome"] == "rejected"
        assert projection["promotion_outcome_reason"] == (
            "malformed_signal_ids"
        )
        assert projection["reconciliation_required"] is False

    def test_promotion_scope_error_propagation(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        accumulator, _, result = self._run_with_dispatcher_exception(
            tmp_path,
            monkeypatch,
            PromotionScopeError("not in scope"),
        )
        assert is_rejected(result.outcome)
        assert result.outcome.reason is (
            PromotionRejectionCode.CURRENT_RUN_SCOPE_VIOLATION
        )
        assert is_rejected(accumulator.promotion_outcome)