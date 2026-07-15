"""Public wrapper return boundary regression for Item-3 closure.

Proves that run_alertmanager_snapshot_collection() returns the typed
AlertSignalPromotionDispatchResult envelope through the public API.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01-CLOSURE.

Reviewer blocking item: the code returns through the correct boundary
(loop_runner_monitoring), but no test asserts that the public
run_alertmanager_snapshot_collection() returns the typed envelope.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.health import loop_runner_monitoring as monitoring
from k8s_diag_agent.health.loop_alertmanager_snapshot_signals import (
    AlertSignalPromotionDispatchResult,
)


class TestPublicWrapperReturn:
    """Public API boundary: run_alertmanager_snapshot_collection() returns typed envelope."""

    def test_run_alertmanager_snapshot_collection_returns_typed_envelope(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The public run_alertmanager_snapshot_collection() returns AlertSignalPromotionDispatchResult.

        This pins the R3-1 fix: the typed outcome is no longer discarded
        when flowing through the public monitoring wrapper.
        """
        # Build a sentinel result that we can verify is returned
        sentinel = AlertSignalPromotionDispatchResult(
            workset=None,
            outcome=None,
        )

        def stubbed_impl(**_kwargs: Any) -> AlertSignalPromotionDispatchResult:
            return sentinel

        monkeypatch.setattr(
            monitoring,
            "_run_alertmanager_snapshot_collection_impl",
            stubbed_impl,
        )

        # Call the public API with correct signature
        result = monitoring.run_alertmanager_snapshot_collection(
            inventory=None,
            run_id="test-run-123",
            run_label="test-label",
            log_event=lambda *args, **kwargs: None,
            directories={"root": "/tmp"},
            start_port_forward=lambda: (None, 0),
            stop_port_forward=lambda *args, **kwargs: None,
            incident_store=None,
        )

        # The public wrapper MUST return the typed envelope, not discard it
        assert result is sentinel, (
            "run_alertmanager_snapshot_collection() must return "
            "AlertSignalPromotionDispatchResult, not discard it"
        )
        assert isinstance(result, AlertSignalPromotionDispatchResult)

    def test_wrapper_return_preserves_outcome_when_accumulator_is_none(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The typed outcome is preserved even when no accumulator is passed.

        This is the R3-1 regression: before the fix, the typed outcome
        was discarded when the caller did not supply an accumulator.
        """
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionCommitUnknown,
            PromotionReconciliationToken,
            PromotionUncertaintyCode,
        )

        token = PromotionReconciliationToken(
            request_id="req-abc123",
            request_fingerprint="fp-xyz789",
        )
        commit_unknown_outcome = PromotionCommitUnknown(
            run_id="test-run-456",
            reason=PromotionUncertaintyCode.TRANSPORT_TIMEOUT,
            reconciliation_token=token,
            requested_signal_ids=("sig-1", "sig-2"),
        )
        sentinel = AlertSignalPromotionDispatchResult(
            workset=None,
            outcome=commit_unknown_outcome,
        )

        def stubbed_impl(**_kwargs: Any) -> AlertSignalPromotionDispatchResult:
            return sentinel

        monkeypatch.setattr(
            monitoring,
            "_run_alertmanager_snapshot_collection_impl",
            stubbed_impl,
        )

        result = monitoring.run_alertmanager_snapshot_collection(
            inventory=None,
            run_id="test-run-456",
            run_label="test-label",
            log_event=lambda *args, **kwargs: None,
            directories={"root": "/tmp"},
            start_port_forward=lambda: (None, 0),
            stop_port_forward=lambda *args, **kwargs: None,
            incident_store=None,
        )

        assert result is sentinel
        assert result.outcome is commit_unknown_outcome
        assert result.outcome is not None
