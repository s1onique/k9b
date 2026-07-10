"""Tests for exactly-one eligibility summary emission per collector run.

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
def capture_logs():
    """Capture structured logs emitted by the collector."""
    captured: list[dict[str, Any]] = []

    class LogCapture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            record_dict = record.__dict__
            captured.append({
                "message": record.getMessage(),
                "event": record_dict.get("event"),
                "incidents_processed": record_dict.get("incidents_processed"),
                "incidents_eligible": record_dict.get("incidents_eligible"),
                "incidents_skipped": record_dict.get("incidents_skipped"),
                "incidents_with_errors": record_dict.get("incidents_with_errors"),
            })

    handler = LogCapture()
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield captured
    logger.removeHandler(handler)


class TestExactlyOneSummaryEmission:
    """Tests proving exactly one eligibility summary is emitted per collector run."""

    def test_disabled_emits_exactly_one(self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch):
        """Prove disabled path emits exactly one eligibility summary."""
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.is_automatic_diagnosis_loop_enabled",
            lambda: False,
        )

        run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )

        summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
        assert len(summary_logs) == 1, f"Expected exactly 1 summary, got {len(summary_logs)}"

    def test_zero_candidates_emits_exactly_one(self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch):
        """Prove zero candidates path emits exactly one eligibility summary."""
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

        run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )

        summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
        assert len(summary_logs) == 1, f"Expected exactly 1 summary, got {len(summary_logs)}"

    def test_mixed_results_emits_exactly_one(
        self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch
    ):
        """Prove mixed eligible/skipped/error results emit exactly one eligibility summary."""
        store = IncidentStore()
        incident_ids = []
        for i in range(5):
            candidate = make_candidate(name=f"test-pod-{i}")
            incidents = store.promote_candidates([candidate], datetime.now(UTC))
            incident_id = incidents[0].incident_id
            store.mark_collecting_evidence(incident_id, bundle_id=f"test-bundle-{i:03d}")
            incident_ids.append(incident_id)

        set_incident_store(store)

        try:
            results = [
                AutoLoopIncidentResult(incident_id=incident_ids[0], eligible=False, eligibility_reason="budget_exhausted", skipped=True),
                AutoLoopIncidentResult(incident_id=incident_ids[1], eligible=True, eligibility_reason="eligible"),
                AutoLoopIncidentResult(incident_id=incident_ids[2], eligible=False, eligibility_reason="terminal_status_resolved", skipped=True),
                AutoLoopIncidentResult(incident_id=incident_ids[3], eligible=False, eligibility_reason="processing_error", error="KeyError: missing"),
                AutoLoopIncidentResult(incident_id=incident_ids[4], eligible=False, eligibility_reason="inactive_status_open", skipped=True),
            ]
            result_index = [0]

            def mock_process(**kwargs):
                result = results[result_index[0]]
                result_index[0] += 1
                return result

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._process_incident",
                mock_process,
            )

            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=incident_ids,
            )

            summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
            assert len(summary_logs) == 1, f"Expected exactly 1 summary, got {len(summary_logs)}"

            summary = summary_logs[0]
            assert summary["incidents_processed"] == 5
            assert summary["incidents_eligible"] == 1
            assert summary["incidents_skipped"] == 3
            assert summary["incidents_with_errors"] == 1

        finally:
            set_incident_store(None)
