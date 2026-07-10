"""Regression tests for skipped-head starvation bug in automatic diagnosis loop.

BUG: Previously, max_incidents_per_run was applied BEFORE eligibility filtering,
causing incidents at position 11+ to be permanently starved when the first 10
were already processed (had review packets). The scheduler would select the first
10 incidents, which were all skipped because they already had review packets, and
the loop would exit without processing any incidents.

FIX: The loop now uses a larger scan window (3x budget) and continues scanning
past skipped incidents until the diagnosis budget is exhausted or scan bound is reached.

These tests prove the fix:
1. Skipped-head starvation: First N incidents are skipped, but the loop finds eligible ones beyond
2. Diagnosis budget exhaustion: Loop stops after starting max_diagnoses incidents
3. Scan bound: Loop stops after scanning max_incidents without finding eligible ones
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


class TestSkippedHeadStarvationRegression:
    """Regression tests for skipped-head starvation bug.

    These tests prove that the fix correctly handles the case where:
    - First N incidents are skipped (e.g., budget_exhausted because they already have review packets)
    - The loop continues scanning to find eligible incidents beyond the initial batch
    """

    def test_skipped_head_starvation_finds_eligible_incident_beyond_prefix(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Bug fix regression: Loop should skip past exhausted incidents to find eligible ones.

        Scenario:
        - 15 incidents total
        - First 10 have budget_exhausted (already have review packets)
        - 11th is eligible
        - max_incidents_per_run = 5 (scan_bound = 15)

        Expected: incident 11 starts diagnosis (not starved by the first 10)
        """
        # Mock incident listing to return 15 incidents
        mock_incidents = []
        for i in range(1, 16):
            mock_incident = MagicMock()
            mock_incident.incident_id = f"incident-{i:02d}"
            mock_incident.status.value = "open"
            mock_incidents.append(mock_incident)

        def mock_list_incidents(
            active_only: bool = True,
            limit: int | None = None,
            after_incident_id: str | None = None,
        ):
            # Return all 15 with limit 30 (scan_bound = 5 * 3 = 15)
            return mock_incidents[: min(len(mock_incidents), limit or 30)], True, None

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_for_diagnosis",
            mock_list_incidents,
        )

        # Track processed incidents
        processed = []

        def mock_process_incident(
            incident_id: str,
            external_analysis_dir: Path,
            config: AutomaticDiagnosisLoopConfig,
            collector_run_id: str,
            now: datetime,
        ) -> AutoLoopIncidentResult:
            processed.append(incident_id)
            idx = int(incident_id.split("-")[1])

            if idx <= 10:
                # First 10 are exhausted (already have review packets)
                return AutoLoopIncidentResult(
                    incident_id=incident_id,
                    eligible=False,
                    eligibility_reason="budget_exhausted",
                    skipped=True,
                    skip_reason="budget_exhausted",
                )
            else:
                # 11th and beyond are eligible
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

        # Patch _write_loop_summary to avoid writing artifacts
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary",
            lambda **kwargs: {},
        )

        # Use max_incidents_per_run=5 so scan_bound=15 (5*3) - enough to scan past the first 10
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=5),
        )

        # Verify: incident 11 should have been processed (not starved)
        assert result.incidents_eligible == 5, f"Expected 5 eligible (11-15), got {result.incidents_eligible}"
        assert "incident-11" in processed, f"Expected incident-11 to be processed, got {processed}"
        assert "incident-10" in processed, f"Expected incident-10 to be processed (skipped), got {processed}"

        # Verify: incident 11-15 are the ones that became eligible
        assert len(result.incident_results) > 0
        eligible_results = [r for r in result.incident_results if r.get("eligible")]
        assert len(eligible_results) == 5
        eligible_ids = [r["incident_id"] for r in eligible_results]
        assert eligible_ids == ["incident-11", "incident-12", "incident-13", "incident-14", "incident-15"]

    def test_skipped_head_starvation_continues_past_multiple_skipped(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Bug fix regression: Loop should skip multiple exhausted incidents.

        Scenario:
        - 20 incidents total
        - First 15 have budget_exhausted
        - 16th-20th are eligible
        - max_incidents_per_run = 7 (scan_bound = 21)

        Expected: incidents 16-20 start diagnosis (not starved by the first 15)
        """
        # Mock incident listing
        mock_incidents = []
        for i in range(1, 21):
            mock_incident = MagicMock()
            mock_incident.incident_id = f"incident-{i:02d}"
            mock_incident.status.value = "open"
            mock_incidents.append(mock_incident)

        def mock_list_incidents(
            active_only: bool = True,
            limit: int | None = None,
            after_incident_id: str | None = None,
        ):
            # Return all 20 incidents, limited by scan_bound (7*3=21)
            return mock_incidents[: min(len(mock_incidents), limit or 30)], True, None

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
            idx = int(incident_id.split("-")[1])

            if idx <= 15:
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

        # Use max_incidents_per_run=7 so scan_bound=21 (7*3) - enough to scan all 20 incidents
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=7),
        )

        # Verify: incidents 16-20 should have been processed (5 eligible)
        assert result.incidents_eligible == 5, f"Expected 5 eligible (16-20), got {result.incidents_eligible}"
        assert "incident-16" in processed, "incident-16 should be processed"
        assert "incident-15" in processed, "incident-15 should be checked (skipped)"

    def test_diagnosis_budget_exhausted_stops_loop(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Bug fix regression: Loop should stop after diagnosis budget is exhausted.

        Scenario:
        - 10 eligible incidents
        - max_incidents_per_run = 3

        Expected: exactly 3 diagnoses started, loop stops
        """
        mock_incidents = []
        for i in range(1, 11):
            mock_incident = MagicMock()
            mock_incident.incident_id = f"incident-{i:02d}"
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
        call_count = 0

        def mock_process_incident(
            incident_id: str,
            external_analysis_dir: Path,
            config: AutomaticDiagnosisLoopConfig,
            collector_run_id: str,
            now: datetime,
        ) -> AutoLoopIncidentResult:
            nonlocal call_count
            call_count += 1
            processed.append(incident_id)
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
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=3),
        )

        # Verify: exactly 3 diagnoses started
        assert result.incidents_eligible == 3, f"Expected 3 eligible, got {result.incidents_eligible}"
        assert len(processed) == 3, f"Expected 3 processed, got {len(processed)}"
        assert processed == ["incident-01", "incident-02", "incident-03"]

    def test_scan_bound_stops_loop_when_no_eligible_found(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Bug fix regression: Loop should stop when scan bound is reached.

        Scenario:
        - 30 incidents all with budget_exhausted
        - max_incidents_per_run = 1
        - scan_bound = 3 (10 * 3 = 30, but we limit to ensure test runs fast)

        Expected: loop processes up to scan_bound and stops with 0 eligible
        """
        # Create 30 exhausted incidents
        mock_incidents = []
        for i in range(1, 31):
            mock_incident = MagicMock()
            mock_incident.incident_id = f"incident-{i:02d}"
            mock_incident.status.value = "open"
            mock_incidents.append(mock_incident)

        # Use smaller scan_bound for test (scan_bound = max_incidents_per_run * 3)
        # With max=1, scan_bound=3

        def mock_list_incidents(
            active_only: bool = True,
            limit: int | None = None,
            after_incident_id: str | None = None,
        ):
            # Limit is scan_bound = 3
            return mock_incidents[:limit], True, None

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
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=False,
                eligibility_reason="budget_exhausted",
                skipped=True,
                skip_reason="budget_exhausted",
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

        # Verify: all 3 scanned incidents were skipped, scan_bound was reached
        assert result.incidents_skipped == 3, f"Expected 3 skipped, got {result.incidents_skipped}"
        assert result.incidents_eligible == 0
        assert len(processed) == 3, f"Expected 3 processed, got {len(processed)}"
