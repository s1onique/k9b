"""Tests for per-incident skipped logs with collector_run_id.

Related to: ACT-K9B-AUTO-DIAGNOSIS-ELIGIBILITY-SUMMARY-PROD-PATH01
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
                "name": record.name,
                "levelname": record.levelname,
                "event": record_dict.get("event"),
                "collector_run_id": record_dict.get("collector_run_id"),
                "incident_id": record_dict.get("incident_id"),
                "eligible": record_dict.get("eligible"),
                "eligibility_reason": record_dict.get("eligibility_reason"),
                "skip_reason": record_dict.get("skip_reason"),
            })

    handler = LogCapture()
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield captured
    logger.removeHandler(handler)


class TestPerIncidentSkippedLogs:
    """Tests proving per-incident skipped logs include collector_run_id."""

    def test_skipped_incident_log_includes_collector_run_id(
        self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch, enabled_auto_loop
    ):
        """Prove per-incident skipped logs include collector_run_id for correlation."""
        store = IncidentStore()
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], datetime.now(UTC))
        incident_id = incidents[0].incident_id
        store.mark_collecting_evidence(incident_id, bundle_id="test-bundle-001")
        set_incident_store(store)

        try:
            mock_result = AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=False,
                eligibility_reason="budget_exhausted",
                skipped=True,
                skip_reason="Budget exhausted",
            )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._process_incident",
                lambda **kwargs: mock_result,
            )

            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[incident_id],
            )

            # Find the aggregate summary to get its collector_run_id
            summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
            assert len(summary_logs) == 1
            expected_collector_run_id = summary_logs[0]["collector_run_id"]

            # Find per-incident skipped log
            skipped_logs = [log for log in capture_logs if log["event"] == "incident-skipped"]
            assert len(skipped_logs) == 1

            skipped_log = skipped_logs[0]
            assert skipped_log["collector_run_id"] == expected_collector_run_id, (
                "Per-incident skip log must have same collector_run_id as aggregate summary"
            )
            assert skipped_log["incident_id"] == incident_id
            assert skipped_log["eligible"] is False
            assert skipped_log["eligibility_reason"] == "budget_exhausted"

        finally:
            set_incident_store(None)
