"""Regression tests for existing packet and alert refresh bugs.

Tests prove that:
1. Existing review packets don't prevent diagnosis loop from running
2. Alert refresh doesn't starve unprocessed pending work
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
    run_automatic_diagnosis_loop_evidence_collection,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
    AutoLoopIncidentResult,
)


@pytest.fixture
def temp_external_dir(tmp_path: Path) -> Path:
    """Create a temporary external analysis directory.

    Mirrors production path structure: runs/{run_id}/external-analysis
    This ensures runs_dir derivation (parent.parent) works correctly.
    """
    runs_dir = tmp_path / "runs"
    health_dir = runs_dir / "health"
    return health_dir / "external-analysis"


@pytest.fixture
def enabled_auto_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable automatic diagnosis loop."""
    monkeypatch.setattr(
        "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.is_automatic_diagnosis_loop_enabled",
        lambda: True,
    )


class TestExistingPacketContinuesIntoLoop:
    """Test that existing review packets don't prevent diagnosis loop from running."""

    def test_existing_review_packet_runs_diagnosis_loop(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Bug fix regression: Existing review packet should not skip diagnosis loop."""
        mock_incidents = []
        mock_incident = MagicMock()
        mock_incident.incident_id = "incident-01"
        mock_incident.status.value = "open"
        mock_incidents.append(mock_incident)

        review_packet_dir = temp_external_dir / "review-packets"
        review_packet_dir.mkdir(parents=True, exist_ok=True)
        (review_packet_dir / "auto-incident-01-20240101-test-diagnosis-review-packet.json").touch()

        def mock_list_incidents(
            active_only: bool = True,
            limit: int | None = None,
            after_incident_id: str | None = None,
        ):
            return mock_incidents, True, None

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_for_diagnosis",
            mock_list_incidents,
        )

        diagnosis_loop_run = []

        def mock_process_incident(
            incident_id: str,
            external_analysis_dir: Path,
            config: AutomaticDiagnosisLoopConfig,
            collector_run_id: str,
            now: datetime,
        ) -> AutoLoopIncidentResult:
            diagnosis_loop_run.append(incident_id)
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=True,
                eligibility_reason="active_incident",
                run_id=f"run-{incident_id}",
                skipped=False,
                loop_pass_artifact_written=True,
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._process_incident",
            mock_process_incident,
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary",
            lambda **kwargs: {},
        )

        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=1, max_passes_per_incident=1),
        )

        assert len(diagnosis_loop_run) == 1, f"Expected diagnosis loop to run, got {diagnosis_loop_run}"
        assert result.incidents_eligible == 1


class TestAlertRefreshDoesNotStarvePendingWork:
    """Test that alert refresh (updated timestamps) doesn't starve pending work."""

    def test_older_unprocessed_incident_still_selected(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Bug fix regression: Alert refresh should not starve unprocessed incidents."""
        mock_incidents = []
        for i, name in enumerate(["incident-old", "incident-new"], 1):
            mock_incident = MagicMock()
            mock_incident.incident_id = name
            mock_incident.status.value = "open"
            mock_incidents.append(mock_incident)

        def mock_list_incidents(
            active_only: bool = True,
            limit: int | None = None,
            after_incident_id: str | None = None,
        ):
            return mock_incidents, True, None

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_for_diagnosis",
            mock_list_incidents,
        )

        processed = []

        def mock_process_incident(
            incident_id: str,
            external_analysis_dir: Path,
            config: AutomaticDiagnosisLoopConfig,
            collector_run_id: str,
            now: datetime,
        ) -> AutoLoopIncidentResult:
            processed.append(incident_id)
            if incident_id == "incident-old":
                return AutoLoopIncidentResult(
                    incident_id=incident_id,
                    eligible=False,
                    eligibility_reason="budget_exhausted",
                    skipped=True,
                    skip_reason="budget_exhausted",
                )
            else:
                return AutoLoopIncidentResult(
                    incident_id=incident_id,
                    eligible=True,
                    eligibility_reason="active_incident",
                    run_id=f"run-{incident_id}",
                    skipped=False,
                )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._process_incident",
            mock_process_incident,
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary",
            lambda **kwargs: {},
        )

        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=1),
        )

        assert "incident-old" in processed, "Old incident should have been checked"
        assert "incident-new" in processed, "New incident should have been checked"
        assert result.incidents_eligible == 1
        assert result.incident_results[1]["incident_id"] == "incident-new"
