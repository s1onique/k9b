"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 production wiring tests.

Covers invariants O1, O2, O3, O4, O5, O10, O15, O16.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    MODE_BACKEND_API,
    IncidentPromotionResult,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    is_succeeded,
)
from k8s_diag_agent.health.loop_alertmanager_snapshot_signals import (
    AlertSignalPromotionDispatchResult,
    _ingest_alert_signals,
)

from .incident_current_run_promotion_dispatch_outcome01_support import (
    RUN_ID,
    SOURCE_IDENTITY,
    CapturingLog,
    build_alert,
    build_snapshot,
    build_source,
    persist_signals,
    stub_dispatch_with_batch,
    successful_result_template,
)


class TestProductionWiring:
    """The real ``_ingest_alert_signals`` path wires the classifier."""

    def test_classifier_invoked_once_with_real_dispatcher_return(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 5)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        from k8s_diag_agent.collect import (
            promotion_dispatch_outcome as cls_module,
        )

        original_classifier = cls_module.classify_promotion_dispatch_result
        spy_calls: list[dict] = []

        def classifier_spy(
            *,
            run_id: str,
            requested_signal_ids: tuple[str, ...],
            requested_signal_payload: dict,
            outcome: Any,
            authoritative_records: tuple = (),
        ) -> Any:
            spy_calls.append(
                {
                    "run_id": run_id,
                    "requested_signal_ids": tuple(requested_signal_ids),
                    "requested_signal_payload": dict(requested_signal_payload),
                    "outcome": outcome,
                    "authoritative_records": tuple(authoritative_records),
                }
            )
            return original_classifier(
                run_id=run_id,
                requested_signal_ids=requested_signal_ids,
                requested_signal_payload=requested_signal_payload,
                outcome=outcome,
                authoritative_records=authoritative_records,
            )

        monkeypatch.setattr(
            cls_module,
            "classify_promotion_dispatch_result",
            classifier_spy,
        )

        successful_result = successful_result_template()
        captured = stub_dispatch_with_batch(monkeypatch, successful_result)

        snapshot = build_snapshot([build_alert(i) for i in range(5)])
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

        assert isinstance(result, AlertSignalPromotionDispatchResult)
        assert result.outcome is not None
        assert is_succeeded(result.outcome)
        assert result.workset is not None
        assert sorted(result.workset.signal_ids) == sorted(
            captured["signal_ids"]
        )

        assert len(spy_calls) == 1
        call = spy_calls[0]
        assert call["outcome"] is successful_result

        payload = call["requested_signal_payload"]
        assert payload["runId"] == RUN_ID
        assert payload["sourceIdentity"] == SOURCE_IDENTITY
        assert sorted(payload["signalIds"]) == sorted(captured["signal_ids"])

        assert accumulator.promotion_outcome is result.outcome
        assert accumulator.promotion_outcome_run_id == RUN_ID

        projection_events = log.by_event(
            "promotion-dispatch-outcome-classified",
        )
        assert len(projection_events) == 1
        projection = projection_events[0]
        assert projection["promotion_outcome"] == "succeeded"
        assert projection["promotion_outcome_available"] is True
        assert projection["reconciliation_required"] is False
        assert projection["diagnosis_invoked"] is False

    def test_outcome_returned_when_accumulator_is_none(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 3)
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        successful_result = successful_result_template(
            opened_incidents=1,
            updated_incidents=0,
            opened_incident_ids=("inc-1",),
            updated_incident_ids=(),
        )
        stub_dispatch_with_batch(monkeypatch, successful_result)

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
            promotion_accumulator=None,
        )

        assert isinstance(result, AlertSignalPromotionDispatchResult)
        assert result.outcome is not None
        assert is_succeeded(result.outcome)
        projection_events = log.by_event(
            "promotion-dispatch-outcome-classified",
        )
        assert projection_events[0]["promotion_outcome_variant"] == (
            "synthesised"
        )

    def test_non_empty_success_retains_ids(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 3)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        successful_result = successful_result_template(
            opened_incidents=1,
            updated_incidents=0,
            opened_incident_ids=("inc-1",),
            updated_incident_ids=(),
        )
        stub_dispatch_with_batch(monkeypatch, successful_result)

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

        assert is_succeeded(result.outcome)
        assert accumulator.canonical_incident_ids() == ["inc-1"]
        projection = log.by_event(
            "promotion-dispatch-outcome-classified",
        )[0]
        assert projection["promotion_outcome"] == "succeeded"
        assert projection["canonical_incident_id_count"] == 1

    def test_authoritative_batch_records_reach_typed_outcome(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 3)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        result_obj = IncidentPromotionResult(
            ok=True,
            opened_incident_ids=("inc-1",),
            promotion_mode=MODE_BACKEND_API,
            promotion_records=(),
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode="backend",
        )
        authoritative = (
            PromotionRecord(
                source_candidate_id="cand-1",
                canonical_incident_id="inc-1",
                promotion_outcome="opened",
            ),
            PromotionRecord(
                source_candidate_id="cand-2",
                canonical_incident_id="inc-2",
                promotion_outcome="updated",
            ),
        )
        stub_dispatch_with_batch(monkeypatch, result_obj, authoritative)

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

        outcome = accumulator.promotion_outcome
        assert outcome is not None
        assert outcome.records == authoritative
        assert accumulator.recorded_records() == authoritative