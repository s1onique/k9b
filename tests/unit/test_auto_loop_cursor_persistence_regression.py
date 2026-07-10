"""Regression tests for cursor-based pagination in automatic diagnosis loop.

These tests prove that the cursor-based pagination works correctly:
1. Partial-page budget exhaustion: cursor is saved after last examined incident
2. Resume: cursor is loaded and passed to listing
3. End and wrap: cursor is cleared when suffix is empty
"""

from __future__ import annotations

import json
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


class TestCursorPersistenceMultiRun:
    """Multi-run cursor persistence regression tests.

    These tests prove that the cursor-based pagination works correctly:
    1. Partial-page budget exhaustion: cursor is saved after last examined incident
    2. Resume: cursor is loaded and passed to listing
    3. End and wrap: cursor is cleared when suffix is empty
    """

    def test_cursor_saved_after_budget_exhaustion(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Run 1: Budget exhausted halfway through fetched page, cursor saved with last examined ID.

        Scenario:
        - 9 incidents fetched (01-09)
        - Budget = 3, first 3 eligible, budget exhausted after incident-03
        - Cursor should be saved as incident-03 (last examined)

        Expected: cursor file contains incident-03
        """
        mock_incidents = []
        for i in range(1, 10):
            mock_incident = MagicMock()
            mock_incident.incident_id = f"incident-{i:02d}"
            mock_incident.status.value = "open"
            mock_incidents.append(mock_incident)

        def mock_list_incidents(
            active_only: bool = True,
            limit: int | None = None,
            after_incident_id: str | None = None,
        ):
            # First run: no cursor, return all 9
            assert after_incident_id is None, "First run should have no cursor"
            return mock_incidents, True, None

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_for_diagnosis",
            mock_list_incidents,
        )

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
            # All are eligible
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

        # Run 1: budget = 3, will exhaust after processing 3 incidents
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=3),
        )

        # Verify budget was exhausted
        assert result.incidents_eligible == 3
        assert len(result.incident_results) == 3

        # Verify cursor was saved with incident-03 (last examined)
        runs_dir = temp_external_dir.parent.parent
        cursor_file = runs_dir / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
        assert cursor_file.exists(), f"Cursor file should exist at {cursor_file}"

        with open(cursor_file) as f:
            cursor_data = json.load(f)
        assert cursor_data["last_incident_id"] == "incident-03", \
            f"Cursor should be incident-03, got {cursor_data['last_incident_id']}"

    def test_cursor_resume_on_second_run(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Run 2: Existing cursor is loaded and passed to listing, processing begins at cursor+1.

        Scenario:
        - Run 1 saved cursor with incident-03
        - Run 2 should receive after_incident_id="03" and start at incident-04

        Expected: listing is called with after_incident_id="03", first processed is incident-04
        """
        mock_incidents = []
        for i in range(1, 10):
            mock_incident = MagicMock()
            mock_incident.incident_id = f"incident-{i:02d}"
            mock_incident.status.value = "open"
            mock_incidents.append(mock_incident)

        # Track cursor passed to listing
        cursor_passed = []

        def mock_list_incidents(
            active_only: bool = True,
            limit: int | None = None,
            after_incident_id: str | None = None,
        ):
            cursor_passed.append(after_incident_id)
            # Simulate cursor-based pagination: slice after cursor position
            if after_incident_id is not None:
                # Find cursor position and slice after it
                for idx, inc in enumerate(mock_incidents):
                    if inc.incident_id == after_incident_id:
                        return mock_incidents[idx + 1:], True, None
                # Cursor not found, return all (restart)
                return mock_incidents, True, None
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

        # First, simulate Run 1 completing and saving cursor
        runs_dir = temp_external_dir.parent.parent
        runs_dir.mkdir(parents=True, exist_ok=True)
        cursor_dir = runs_dir / "state" / "automatic-diagnosis"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        cursor_file = cursor_dir / "auto-loop-scan-cursor.json"
        with open(cursor_file, "w") as f:
            json.dump({
                "last_incident_id": "incident-03",
                "saved_at": "2026-01-01T00:00:00+00:00",
            }, f)

        # Run 2
        _result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=3),
        )

        # Verify listing was called with cursor
        assert cursor_passed[0] == "incident-03", \
            f"Listing should receive cursor incident-03, got {cursor_passed[0]}"

        # Verify incident-04 was first processed (after cursor)
        assert processed[0] == "incident-04", \
            f"First processed should be incident-04, got {processed[0]}"

    def test_cursor_cleared_when_suffix_empty(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Empty suffix after cursor: cursor file is removed, next run starts fresh.

        Scenario:
        - Cursor saved with incident-09 (last incident)
        - Run 2 queries with after_incident_id="09"
        - Returns empty list (no incidents after cursor)
        - Cursor should be cleared

        Expected: cursor file is removed
        """
        # Simulate cursor at end of list
        runs_dir = temp_external_dir.parent.parent
        runs_dir.mkdir(parents=True, exist_ok=True)
        cursor_dir = runs_dir / "state" / "automatic-diagnosis"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        cursor_file = cursor_dir / "auto-loop-scan-cursor.json"
        with open(cursor_file, "w") as f:
            json.dump({
                "last_incident_id": "incident-09",
                "saved_at": "2026-01-01T00:00:00+00:00",
            }, f)

        def mock_list_incidents(
            active_only: bool = True,
            limit: int | None = None,
            after_incident_id: str | None = None,
        ):
            # Cursor was at end, so return empty list
            assert after_incident_id == "incident-09", \
                f"Should receive cursor incident-09, got {after_incident_id}"
            return [], True, None

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_for_diagnosis",
            mock_list_incidents,
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary",
            lambda **kwargs: {},
        )

        # Patch log_zero_incidents_diagnostic to avoid side effects
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.log_zero_incidents_diagnostic",
            lambda config: None,
        )

        # Run 2
        _result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=3),
        )

        # Verify cursor was cleared
        assert not cursor_file.exists(), \
            "Cursor file should be removed when suffix is empty"

        # Verify next run will start fresh (no cursor)
        # (This would require a third run, but the fact that cursor_file
        #  doesn't exist proves it was cleared)
