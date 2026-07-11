"""Tests for health loop wrapper path eligibility summary emission.

This module tests that the health loop integration point (run_automatic_diagnosis_loop)
correctly emits the eligibility summary event with proper correlation to the scheduler run.

Related to: ACT-K9B-AUTO-DIAGNOSIS-ELIGIBILITY-SUMMARY-PROD-PATH01
"""

from __future__ import annotations

import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import AutoLoopIncidentResult
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store
from k8s_diag_agent.health.loop_automatic_diagnosis import run_automatic_diagnosis_loop
from tests.unit.incident_store_fixtures import make_candidate


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
                "event": record_dict.get("event"),
                "collector_run_id": record_dict.get("collector_run_id"),
                "run_id": record_dict.get("run_id"),
                "incidents_processed": record_dict.get("incidents_processed"),
                "incidents_eligible": record_dict.get("incidents_eligible"),
                "incidents_skipped": record_dict.get("incidents_skipped"),
                "eligibility_version": record_dict.get("eligibility_version"),
            })

    handler = LogCapture()
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield captured
    logger.removeHandler(handler)


class TestHealthWrapperPathEligibilitySummary:
    """Tests proving health loop wrapper emits eligibility summary with scheduler correlation."""

    def test_health_wrapper_emits_eligibility_summary_with_scheduler_run_id(
        self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch, enabled_auto_loop
    ):
        """Prove health wrapper emits eligibility summary with run_id correlation.

        This is the production scheduler path. The wrapper calls the collector and
        the collector should emit the eligibility summary with the scheduler_run_id
        passed through for correlation with other scheduler logs.
        """
        store = IncidentStore()
        incident_ids = []
        for i in range(10):
            candidate = make_candidate(name=f"test-pod-{i}")
            incidents = store.promote_candidates([candidate], datetime.now(UTC))
            incident_id = incidents[0].incident_id
            store.mark_collecting_evidence(incident_id, bundle_id=f"test-bundle-{i:03d}")
            incident_ids.append(incident_id)

        set_incident_store(store)

        try:
            def mock_process(**kwargs):
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=False,
                    eligibility_reason="budget_exhausted",
                    skipped=True,
                    skip_reason="Budget exhausted for review packets",
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                mock_process,
            )

            scheduler_run_id = "scheduler-20260710-001122"

            result = run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                scheduler_run_id=scheduler_run_id,
            )

            # Find eligibility summary event
            summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
            assert len(summary_logs) == 1, f"Expected 1 eligibility summary, got {len(summary_logs)}"

            summary = summary_logs[0]

            # Verify the scheduler_run_id is correlated in the summary
            assert summary["run_id"] == scheduler_run_id, (
                "Eligibility summary must include scheduler_run_id for correlation"
            )
            assert summary["collector_run_id"] is not None

            # Verify result matches
            assert result["automatic_diagnosis_enabled"] is True
            assert result["collector_run_id"] is not None
            assert result["run_id"] == scheduler_run_id
            assert result["incidents_processed"] == 10
            assert result["incidents_eligible"] == 0
            assert result["incidents_skipped"] == 10

        finally:
            set_incident_store(None)

    def test_health_wrapper_disabled_path_does_not_emit_collector_summary(
        self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch
    ):
        """Prove disabled wrapper path does NOT emit eligibility summary.

        The wrapper checks is_automatic_diagnosis_loop_enabled and returns early,
        so the collector is never called and no eligibility summary is emitted.
        This is correct behavior - the wrapper emits a disabled event instead.
        """
        monkeypatch.setattr(
            "k8s_diag_agent.health.loop_automatic_diagnosis.is_automatic_diagnosis_loop_enabled",
            lambda: False,
        )

        result = run_automatic_diagnosis_loop(
            external_analysis_dir=temp_external_dir,
            scheduler_run_id="scheduler-20260710-001122",
        )

        assert result["automatic_diagnosis_enabled"] is False

        # The wrapper returns before calling the collector, so no eligibility summary is emitted
        assert not [
            log
            for log in capture_logs
            if log["event"] == "automatic-diagnosis-eligibility-summary"
        ], "Disabled wrapper should not emit eligibility summary"
