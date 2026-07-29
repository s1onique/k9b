"""Scoped selection unavailable final-summary integration.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01.

This integration test exercises the canonical unavailable paths
(commit-unknown and rejected) through the active
``run_automatic_diagnosis_loop`` final-summary construction and
asserts the bounded canonical fields.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from scoped_selection_typed_support import (
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
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionDispatchRejected,
    ScopedPromotionDispatchUncertain,
)
from k8s_diag_agent.health.loop_automatic_diagnosis import (
    build_diagnosis_selection,
    run_automatic_diagnosis_loop,
)


def _stub_collector() -> Any:
    """Return a stub object that mimics the
    ``AutomaticDiagnosisLoopResult`` shape returned by the
    canonical collector.
    """
    return type(
        "_Stub",
        (),
        {
            "incidents_processed": 0,
            "incidents_eligible": 0,
            "incidents_skipped": 0,
            "incidents_ineligible": 0,
            "incidents_with_errors": 0,
            "total_review_packets_written": 0,
            "disposition_summary": type(
                "_StubSummary",
                (),
                {
                    "skip_reasons": {},
                    "ineligible_reasons": {},
                    "error_reasons": {},
                },
            )(),
            "run_id": "test-run",
        },
    )()


class TestScopedSelectionUnavailableFinalSummary:
    """Production-shaped final-summary through the unavailable paths."""

    def test_commit_unknown_emits_canonical_final_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """Commit-unknown drives the active atomic recorder and
        the actual final-summary construction with the
        ``commit_unknown`` selection mode and the reconciliation
        token identity.
        """
        projection = build_uncertain_projection()
        monkeypatch.setattr(
            incident_promotion_backend,
            "promote_alert_signals_via_scoped_backend_api",
            lambda **_: ScopedPromotionDispatchUncertain(
                projection=projection
            ),
        )
        accumulator = RunPromotionAccumulator()
        promote_alert_signals_scoped_for_accumulator(
            runs_dir=tmp_path,
            health_run_id="health-run-typed-handoff-001",
            source_identity="source-test",
            signal_ids=list(default_requested_signal_ids()),
            accumulator=accumulator,
            cluster_context="ctx-test",
        )
        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert (
            accumulator.promotion_outcome.reconciliation_token
            is projection.promotion_outcome.reconciliation_token
        )

        with patch(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop."
            "run_automatic_diagnosis_loop_evidence_collection",
            return_value=_stub_collector(),
        ), patch(
            "k8s_diag_agent.health.loop_automatic_diagnosis."
            "is_automatic_diagnosis_loop_enabled",
            return_value=True,
        ):
            selection = build_diagnosis_selection(
                promotion_outcome=projection.promotion_outcome,
                run_id="health-run-typed-handoff-001",
                non_promotion_policy_enabled=False,
            )
            summary = run_automatic_diagnosis_loop(
                external_analysis_dir=tmp_path,
                log_event_fn=lambda *a, **kw: None,
                diagnosis_selection=selection,
                scheduler_run_id="health-run-typed-handoff-001",
                backend_endpoint_identity={
                    "incident_access_mode": "reconciliation_required",
                },
            )

        assert (
            summary["selection_source"]
            == "unavailable_due_to_commit_unknown"
        )
        assert summary["selection_mode"] == "commit_unknown"
        assert summary["store_scan_performed"] is False
        assert summary["incident_access_mode"] == "reconciliation_required"
        assert summary["reconciliation_required"] is True
        assert summary["selected_incident_count"] == 0
        assert summary["promotion_propagated_to_diagnosis"] is False
        assert summary["blocked_reason"] == "promotion_commit_unknown"

    def test_rejected_emits_canonical_final_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """Rejected drives the active atomic recorder and the
        actual final-summary construction with the bounded
        ``unavailable_due_to_rejected_promotion`` selection source
        and the ``promotion_consistency_error_recorded`` flag.
        """
        projection = build_rejected_projection()
        monkeypatch.setattr(
            incident_promotion_backend,
            "promote_alert_signals_via_scoped_backend_api",
            lambda **_: ScopedPromotionDispatchRejected(
                projection=projection
            ),
        )
        accumulator = RunPromotionAccumulator()
        promote_alert_signals_scoped_for_accumulator(
            runs_dir=tmp_path,
            health_run_id="health-run-typed-handoff-001",
            source_identity="source-test",
            signal_ids=list(default_requested_signal_ids()),
            accumulator=accumulator,
            cluster_context="ctx-test",
        )
        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert accumulator.promotion_outcome.reason is (
            PromotionRejectionCode.BACKEND_UNREACHABLE
        )

        with patch(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop."
            "run_automatic_diagnosis_loop_evidence_collection",
            return_value=_stub_collector(),
        ), patch(
            "k8s_diag_agent.health.loop_automatic_diagnosis."
            "is_automatic_diagnosis_loop_enabled",
            return_value=True,
        ):
            selection = build_diagnosis_selection(
                promotion_outcome=projection.promotion_outcome,
                run_id="health-run-typed-handoff-001",
                non_promotion_policy_enabled=False,
            )
            summary = run_automatic_diagnosis_loop(
                external_analysis_dir=tmp_path,
                log_event_fn=lambda *a, **kw: None,
                diagnosis_selection=selection,
                scheduler_run_id="health-run-typed-handoff-001",
                backend_endpoint_identity={
                    "incident_access_mode": INCIDENT_ACCESS_MODE_BACKEND,
                },
            )

        assert (
            summary["selection_source"]
            == "unavailable_due_to_rejected_promotion"
        )
        assert summary["selection_mode"] == "blocked"
        assert summary["store_scan_performed"] is False
        assert summary["incident_access_mode"] == INCIDENT_ACCESS_MODE_BACKEND
        assert summary["promotion_consistency_error_recorded"] is True
        assert summary["selected_incident_count"] == 0
        assert summary["reconciliation_required"] is False
        assert summary["blocked_reason"] == "promotion_rejected"
        assert summary["promotion_propagated_to_diagnosis"] is False
