"""Scoped selection no-promotion final-summary integration.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01.

This integration test exercises the explicit no-promotion path
through the active ``run_automatic_diagnosis_loop`` final-summary
construction and asserts the canonical bounded fields.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelectionSource,
    DiagnosisSelectionWithoutPromotion,
    NoPromotionSelectionReason,
    selection_source,
)
from k8s_diag_agent.collect.store_scan_policy import StoreScanPolicy
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


class TestScopedSelectionFinalSummaryNoPromotion:
    """Production-shaped final-summary through the explicit no-promotion path."""

    def test_no_promotion_path_emits_canonical_final_summary(
        self,
        tmp_path: Any,
    ) -> None:
        """The explicit no-promotion path drives the actual
        final-summary construction with the bounded
        ``explicit_nonpromotion`` selection source and the
        ``store_scan_performed`` flag.
        """
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
                promotion_outcome=None,
                run_id="health-run-typed-handoff-001",
                non_promotion_policy_enabled=False,
                store_scan_policy=StoreScanPolicy.EXPLICIT_NON_PROMOTION,
                non_promotion_reason=(
                    NoPromotionSelectionReason.EXPLICIT_NON_PROMOTION_MODE
                ),
            )
            summary = run_automatic_diagnosis_loop(
                external_analysis_dir=tmp_path,
                log_event_fn=lambda *a, **kw: None,
                diagnosis_selection=selection,
                scheduler_run_id="health-run-typed-handoff-001",
            )

        assert isinstance(selection, DiagnosisSelectionWithoutPromotion)
        assert selection.source is (
            DiagnosisSelectionSource.EXPLICIT_NON_PROMOTION
        )
        # The explicit no-promotion branch is the only path that
        # may permit store scan.
        assert summary["store_scan_performed"] is True
        assert summary["selection_source"] == "explicit_nonpromotion"
        assert selection_source(selection) == "explicit_nonpromotion"
