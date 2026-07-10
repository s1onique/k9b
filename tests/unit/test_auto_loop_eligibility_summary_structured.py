"""Tests for structured event field with hyphens.

Related to: ACT-K9B-AUTO-DIAGNOSIS-ELIGIBILITY-SUMMARY-PROD-PATH01
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop import run_automatic_diagnosis_loop_evidence_collection


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
            })

    handler = LogCapture()
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield captured
    logger.removeHandler(handler)


class TestStructuredEventField:
    """Tests proving the structured event field uses hyphens and is grep-friendly."""

    def test_eligibility_summary_event_field_is_hyphenated(self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch):
        """Prove eligibility summary uses event field with hyphens, not underscores."""
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.is_automatic_diagnosis_loop_enabled",
            lambda: False,
        )

        run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )

        summary_logs = [log for log in capture_logs if log["event"] == "automatic-diagnosis-eligibility-summary"]
        assert len(summary_logs) == 1

        # Critical: must be hyphenated for grep
        assert summary_logs[0]["event"] == "automatic-diagnosis-eligibility-summary"

    def test_production_grep_would_find_event(self, temp_external_dir, capture_logs, monkeypatch: pytest.MonkeyPatch):
        """Regression: prove production grep command would find the event."""
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.is_automatic_diagnosis_loop_enabled",
            lambda: False,
        )

        run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )

        # Simulate production grep behavior
        events_found = [
            log["event"] for log in capture_logs
            if "automatic-diagnosis-eligibility-summary" in (log.get("event") or "")
        ]

        assert len(events_found) == 1, (
            f"Production grep would find {len(events_found)} matches, expected 1"
        )
