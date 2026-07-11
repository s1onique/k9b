"""Tests for scheduler path integration.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01
"""

from __future__ import annotations

import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop import run_automatic_diagnosis_loop_evidence_collection
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import AutoLoopIncidentResult
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store
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
                "eligibility_version": record_dict.get("eligibility_version"),
                "schema_version": record_dict.get("schema_version"),
                "incidents_processed": record_dict.get("incidents_processed"),
                "incidents_eligible": record_dict.get("incidents_eligible"),
                "incidents_skipped": record_dict.get("incidents_skipped"),
                "incidents_ineligible": record_dict.get("incidents_ineligible"),
                "incidents_with_errors": record_dict.get("incidents_with_errors"),
                "skip_reasons": record_dict.get("skip_reasons"),
                "ineligible_reasons": record_dict.get("ineligible_reasons"),
                "error_reasons": record_dict.get("error_reasons"),
            })

    handler = LogCapture()
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield captured
    logger.removeHandler(handler)


class TestSchedulerPathIntegration:
    """Tests proving the scheduler path emits eligibility summary."""

    def test_scheduler_auto_diagnosis_path_emits_eligibility_summary(
        self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch, enabled_auto_loop
    ):
        """Prove the scheduler-executed path emits eligibility summary."""
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

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=incident_ids,
            )

            summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
            assert len(summary_logs) == 1, f"Expected 1 summary event, got {len(summary_logs)}"

            summary = summary_logs[0]

            # Verify production contract
            assert summary["event"] == "automatic-diagnosis-eligibility-summary"
            assert summary["collector_run_id"] is not None
            # ACT-K9B-AUTO-DIAGNOSIS-DISPOSITION-ADT01: schema version bumped
            # to 2 because the disposition ADT now carries typed reason maps.
            assert summary["eligibility_version"] == 2
            assert summary["schema_version"] == 2
            assert summary["incidents_processed"] == 10
            assert summary["incidents_eligible"] == 0
            assert summary["incidents_skipped"] == 10
            assert summary["incidents_ineligible"] == 0
            assert summary["incidents_with_errors"] == 0
            # Closed vocabulary member ``review_packet_budget_exhausted``
            # replaces the legacy ``budget_exhausted`` string used by the
            # pre-ADT eligibility check.
            assert summary["skip_reasons"]["review_packet_budget_exhausted"] == 10

            # Verify result matches
            assert result.incidents_processed == 10
            assert result.incidents_eligible == 0
            assert result.incidents_skipped == 10

        finally:
            set_incident_store(None)
