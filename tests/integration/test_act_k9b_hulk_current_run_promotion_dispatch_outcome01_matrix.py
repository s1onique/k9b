"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 classification matrix tests.

Covers invariants O6, O8, O12, O17.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    MODE_BACKEND_API,
    IncidentPromotionResult,
)
from k8s_diag_agent.collect.promotion_dispatch_outcome import (
    PromotionDispatchError,
    PromotionProtocolError,
    PromotionTransportRefused,
    PromotionTransportTimeout,
    PromotionTransportUncertain,
    classify_promotion_dispatch_result,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionUncertaintyCode,
    is_commit_unknown,
    is_succeeded,
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
    stub_dispatch_with_batch,
)


class TestClassificationMatrixThroughProduction:
    """Each dispatcher result class flows through the production wiring."""

    def _run_with_dispatcher_result(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
        promotion_result: IncidentPromotionResult,
    ) -> tuple[RunPromotionAccumulator, CapturingLog, AlertSignalPromotionDispatchResult]:
        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 4)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        stub_dispatch_with_batch(monkeypatch, promotion_result)

        snapshot = build_snapshot([build_alert(i) for i in range(4)])
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

    def _run_with_dispatcher_exception(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
        exc: BaseException,
    ) -> RunPromotionAccumulator:
        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 3)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        stub_dispatch_raises(monkeypatch, exc)

        snapshot = build_snapshot([build_alert(i) for i in range(3)])
        _ingest_alert_signals(
            snapshot=snapshot,
            selected_source=build_source(),
            snapshot_path=None,
            directories={"root": runs_dir},
            incident_store=None,
            log_event=CapturingLog(),
            run_id=RUN_ID,
            run_label="run-2026-07-15T0340Z",
            effective_cluster_context=None,
            promotion_accumulator=accumulator,
        )
        return accumulator

    def test_generic_failed_result_is_commit_unknown(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        failed_result = IncidentPromotionResult(
            ok=False,
            scanned=4,
            firing=4,
            opened_incidents=0,
            updated_incidents=0,
            skipped_duplicates=0,
            errors=1,
            error_messages=("generic backend error",),
            promotion_mode=MODE_BACKEND_API,
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode="backend",
        )
        accumulator, log, result = self._run_with_dispatcher_result(
            tmp_path, monkeypatch, failed_result,
        )
        assert is_commit_unknown(result.outcome)
        assert accumulator.canonical_incident_ids() == []
        projection = log.by_event(
            "promotion-dispatch-outcome-classified",
        )[0]
        assert projection["promotion_outcome"] == "commit_unknown"
        assert projection["reconciliation_required"] is True
        assert projection["promotion_may_have_committed"] is True
        assert projection["diagnosis_handoff_available"] is False

    def test_transport_timeout_preserves_request_count(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 33)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        stub_dispatch_raises(
            monkeypatch, PromotionTransportTimeout("dispatch timed out"),
        )

        snapshot = build_snapshot([build_alert(i) for i in range(33)])
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

        assert is_commit_unknown(result.outcome)
        assert isinstance(result.outcome, PromotionCommitUnknown)
        assert len(result.outcome.requested_signal_ids) == 33
        projection = log.by_event(
            "promotion-dispatch-outcome-classified",
        )[0]
        assert projection["requested_signal_count"] == 33
        assert projection["promotion_outcome_reason"] == "transport_timeout"
        assert accumulator.canonical_incident_ids() == []

    def test_unexpected_exception_is_ambiguous_response(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class WeirdInternalError(RuntimeError):
            pass

        accumulator = self._run_with_dispatcher_exception(
            tmp_path, monkeypatch,
            WeirdInternalError("internal dispatcher blew up"),
        )
        outcome = accumulator.promotion_outcome
        assert outcome is not None
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE

    def test_promotion_dispatch_error_maps_to_commit_unknown(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        accumulator = self._run_with_dispatcher_exception(
            tmp_path, monkeypatch,
            PromotionDispatchError("internal dispatcher failure"),
        )
        outcome = accumulator.promotion_outcome
        assert outcome is not None
        assert is_commit_unknown(outcome)
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE

    def test_transport_refused_routes_through_uncertainty(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        accumulator = self._run_with_dispatcher_exception(
            tmp_path, monkeypatch,
            PromotionTransportRefused("connection refused"),
        )
        outcome = accumulator.promotion_outcome
        assert outcome is not None
        assert outcome.reason is PromotionUncertaintyCode.TRANSPORT_REFUSED

    def test_protocol_error_routes_through_uncertainty(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        accumulator = self._run_with_dispatcher_exception(
            tmp_path, monkeypatch,
            PromotionProtocolError("malformed response"),
        )
        outcome = accumulator.promotion_outcome
        assert outcome is not None
        assert outcome.reason is PromotionUncertaintyCode.PROTOCOL_ERROR

    def test_transport_uncertain_default(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        accumulator = self._run_with_dispatcher_exception(
            tmp_path, monkeypatch,
            PromotionTransportUncertain("uncategorised"),
        )
        outcome = accumulator.promotion_outcome
        assert outcome is not None
        assert outcome.reason is PromotionUncertaintyCode.AMBIGUOUS_RESPONSE
    def test_empty_batch_records_win_over_stale_result_records(self) -> None:
        """R3-empty: an explicitly empty batch record tuple is authoritative.

        An empty batch envelope (empty ``promotion_records``) is
        still authoritative -- it must NOT lose to potentially
        stale records carried by the bare
        ``IncidentPromotionResult.promotion_records``. The classifier's
        sentinel-style check (``authoritative_records is not None``)
        ensures the empty tuple wins.
        """
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            MODE_BACKEND_API,
            IncidentPromotionResult,
        )

        result = IncidentPromotionResult(
            ok=True,
            opened_incident_ids=(),
            promotion_mode=MODE_BACKEND_API,
            promotion_records=(
                # Stale record -- should NOT appear in the outcome.
                ("stale_source", "stale_incident", "opened"),
            ),
        )
        outcome = classify_promotion_dispatch_result(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": "run"},
            outcome=result,
            authoritative_records=(),  # empty but present
        )
        assert is_succeeded(outcome)
        # Authoritative empty batch record tuple wins over stale
        # result-side records.
        assert outcome.records == ()
