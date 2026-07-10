"""Tests for automatic diagnosis loop eligibility summary emission on all exit paths.

Related to: ACT-K9B-AUTO-DIAGNOSIS-ELIGIBILITY-SUMMARY-PROD-PATH01
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def temp_external_dir():
    """Provide a temporary directory for artifact writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def enabled_auto_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the enabled production path without consulting cluster configuration."""
    monkeypatch.setattr(
        "k8s_diag_agent.collect."
        "incident_diagnosis_auto_loop_evidence_collection."
        "is_automatic_diagnosis_loop_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "k8s_diag_agent.health.loop_automatic_diagnosis."
        "is_automatic_diagnosis_loop_enabled",
        lambda: True,
    )


@pytest.fixture
def capture_logs():
    """Capture structured logs emitted by the collector."""
    captured: list[dict[str, Any]] = []

    class LogCapture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            record_dict = record.__dict__
            captured.append({
                "message": record.getMessage(),
                "name": record.name,
                "levelname": record.levelname,
                "event": record_dict.get("event"),
                "collector_run_id": record_dict.get("collector_run_id"),
                "eligibility_version": record_dict.get("eligibility_version"),
                "incidents_processed": record_dict.get("incidents_processed"),
                "incidents_eligible": record_dict.get("incidents_eligible"),
                "incidents_skipped": record_dict.get("incidents_skipped"),
                "incidents_ineligible": record_dict.get("incidents_ineligible"),
                "incidents_with_errors": record_dict.get("incidents_with_errors"),
                "skip_reasons": record_dict.get("skip_reasons"),
                "error_reasons": record_dict.get("error_reasons"),
                "incident_id": record_dict.get("incident_id"),
                "run_id": record_dict.get("run_id"),
                "eligible": record_dict.get("eligible"),
                "eligibility_reason": record_dict.get("eligibility_reason"),
                "skip_reason": record_dict.get("skip_reason"),
                "budget_diagnostics": record_dict.get("budget_diagnostics"),
            })

    handler = LogCapture()
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield captured
    logger.removeHandler(handler)


class TestEligibilitySummaryEmissionOnAllPaths:
    """Tests proving eligibility summary is emitted on ALL collector exit paths."""

    def test_disabled_path_emits_summary(self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch):
        """Prove disabled path emits eligibility summary."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
            run_automatic_diagnosis_loop_evidence_collection,
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.is_automatic_diagnosis_loop_enabled",
            lambda: False,
        )

        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )

        assert result.enabled is False

        summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
        assert len(summary_logs) == 1, f"Expected 1 summary event, got {len(summary_logs)}"

        summary = summary_logs[0]
        assert summary["collector_run_id"] is not None
        assert summary["eligibility_version"] == 1
        assert summary["incidents_processed"] == 0
        assert summary["incidents_eligible"] == 0

    def test_listing_failure_path_emits_summary(self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch):
        """Prove incident listing failure path emits eligibility summary."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
            run_automatic_diagnosis_loop_evidence_collection,
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.is_automatic_diagnosis_loop_enabled",
            lambda: True,
        )
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_for_diagnosis",
            lambda **kwargs: (None, False, "Connection refused"),
        )

        run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )

        summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
        assert len(summary_logs) == 1, f"Expected 1 summary event, got {len(summary_logs)}"

        summary = summary_logs[0]
        assert summary["collector_run_id"] is not None
        assert summary["incidents_processed"] == 0

    def test_zero_candidates_path_emits_summary(self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch):
        """Prove zero candidates path emits eligibility summary."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
            run_automatic_diagnosis_loop_evidence_collection,
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.is_automatic_diagnosis_loop_enabled",
            lambda: True,
        )
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_for_diagnosis",
            lambda **kwargs: ([], True, None),
        )
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.log_zero_incidents_diagnostic",
            lambda config: None,
        )

        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )

        assert result.incidents_processed == 0

        summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
        assert len(summary_logs) == 1, f"Expected 1 summary event, got {len(summary_logs)}"

        summary = summary_logs[0]
        assert summary["incidents_processed"] == 0
        assert summary["incidents_eligible"] == 0

    def test_normal_loop_with_skipped_incidents_emits_summary(
        self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch, enabled_auto_loop
    ):
        """Prove normal loop with skipped incidents emits eligibility summary."""
        from datetime import UTC, datetime

        from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
            run_automatic_diagnosis_loop_evidence_collection,
        )
        from k8s_diag_agent.collect.incident_store import IncidentStore
        from k8s_diag_agent.collect.incident_store_provider import set_incident_store
        from tests.unit.incident_store_fixtures import make_candidate

        store = IncidentStore()
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], datetime.now(UTC))
        incident_id = incidents[0].incident_id
        store.mark_collecting_evidence(incident_id, bundle_id="test-bundle-001")
        set_incident_store(store)

        try:
            from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
                DiagnosisBudgetDiagnostic,
            )
            from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
                AutoLoopIncidentResult,
            )

            mock_result = AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=False,
                eligibility_reason="budget_exhausted",
                skipped=True,
                skip_reason="Budget exhausted for review packets",
                budget_diagnostics=(
                    DiagnosisBudgetDiagnostic(
                        name="review_packet_budget",
                        used=10,
                        limit=10,
                        remaining=0,
                        exhausted=True,
                        source="test",
                        resettable=True,
                    ),
                ),
            )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._process_incident",
                lambda **kwargs: mock_result,
            )

            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[incident_id],
            )

            summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
            assert len(summary_logs) == 1, f"Expected 1 summary event, got {len(summary_logs)}"

            summary = summary_logs[0]
            assert summary["collector_run_id"] is not None
            assert summary["incidents_processed"] == 1
            assert summary["incidents_eligible"] == 0
            assert summary["incidents_skipped"] == 1
            assert "budget_exhausted" in summary["skip_reasons"]

        finally:
            set_incident_store(None)
