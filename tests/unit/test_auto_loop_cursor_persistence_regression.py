"""Regression tests for cursor-based pagination in automatic diagnosis loop.

These tests prove that the cursor-based pagination works correctly:
1. Partial-page budget exhaustion: cursor is saved after last examined incident
2. Resume: cursor is loaded and passed to listing
3. End and wrap: cursor is cleared when suffix is empty
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

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
from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
    DiagnosisPageIncident,
)
from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
    IncidentDiagnosisPage,
)
from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    cursor_after_page_incident,
    decode_cursor,
    encode_cursor,
)
from k8s_diag_agent.collect.incident_diagnosis_pagination_results import (
    AutomaticPageListed,
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


def _make_page_incident(incident_id: str, timestamp: datetime) -> DiagnosisPageIncident:
    """Create a DiagnosisPageIncident with exact timestamp text."""
    ts_text = timestamp.isoformat()
    return DiagnosisPageIncident(
        incident_id=incident_id,
        status="open",
        first_observed_at=timestamp,
        first_observed_at_key=ts_text,
    )


def _make_page(
    incident_ids: list[str],
    *,
    has_more: bool,
    start_hour: int = 10,
) -> IncidentDiagnosisPage:
    """Create an IncidentDiagnosisPage for testing.

    Args:
        incident_ids: List of incident IDs for this page
        has_more: Whether there are more pages after this one
        start_hour: Starting hour for timestamps (default 10)
    """
    incidents = []
    for i, inc_id in enumerate(incident_ids):
        ts = datetime(2024, 6, 15, start_hour, i, 0, tzinfo=UTC)
        incidents.append(_make_page_incident(inc_id, ts))

    next_cursor = cursor_after_page_incident(incidents[-1]) if has_more else None

    return IncidentDiagnosisPage(
        incidents=tuple(incidents),
        next_cursor=next_cursor,
        has_more=has_more,
    )


def _make_empty_page() -> IncidentDiagnosisPage:
    """Create an empty IncidentDiagnosisPage for testing."""
    return IncidentDiagnosisPage(
        incidents=(),
        next_cursor=None,
        has_more=False,
    )


def _write_cursor_file(cursor_file: Path, incident_id: str, timestamp: datetime) -> None:
    """Write a valid cursor file using the new schema format."""
    incident = _make_page_incident(incident_id, timestamp)
    cursor = cursor_after_page_incident(incident)
    encoded_cursor = encode_cursor(cursor)

    cursor_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cursor_file, "w") as f:
        json.dump({
            "schemaVersion": 2,
            "cursor": encoded_cursor,
            "savedAt": "2026-01-01T00:00:00+00:00",
        }, f)


def _read_and_decode_cursor(cursor_file: Path) -> tuple[str, str]:
    """Read cursor file and decode it, returning (incident_id, first_observed_at_text).

    Raises AssertionError if the cursor cannot be decoded.
    """
    with open(cursor_file) as f:
        cursor_data = json.load(f)

    # Verify schema version
    assert cursor_data["schemaVersion"] == 2, \
        f"Expected schemaVersion 2, got {cursor_data['schemaVersion']}"

    # Verify savedAt is present
    assert "savedAt" in cursor_data, "Missing savedAt field"

    # Decode the opaque cursor token
    opaque_token = cursor_data["cursor"]
    cursor_obj, decode_error = decode_cursor(opaque_token)

    assert decode_error is None, \
        f"Failed to decode cursor: {decode_error}"

    assert cursor_obj is not None, \
        "decode_cursor returned None cursor without error"

    return cursor_obj.incident_id, cursor_obj.first_observed_at_text


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
        """Run 1: Budget exhausted after processing 3 of 9 incidents, cursor saved for last examined.

        Scenario:
        - 9 incidents fetched (01-09) from listing
        - Diagnosis budget = 3, processes incidents 01, 02, 03
        - Budget exhausted after processing incident-03
        - Cursor is saved for incident-03 (the last examined row)

        Expected: persisted cursor decodes to incident-03
        """
        # Create a page with 9 incidents, has_more=True to indicate more pages exist
        incident_ids = [f"incident-{i:02d}" for i in range(1, 10)]
        mock_page = _make_page(incident_ids, has_more=True)

        def mock_list_page(scan_cursor, scan_bound):
            return AutomaticPageListed(page=mock_page)

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_with_pagination",
            mock_list_page,
        )

        def mock_process_incident(
            incident_id: str,
            external_analysis_dir: Path,
            config: AutomaticDiagnosisLoopConfig,
            collector_run_id: str,
            now: datetime,
            review_packet_budget = None,
        ) -> AutoLoopIncidentResult:
            # All are eligible
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=True,
                eligibility_reason="active_incident",
                run_id=f"run-{incident_id}",
                skipped=False,
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            mock_process_incident,
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary",
            lambda **kwargs: {},
        )

        # Run 1: budget = 3, will exhaust after processing 3 incidents (01, 02, 03)
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=3),
        )

        # Verify budget was exhausted
        assert result.incidents_eligible == 3, \
            f"Expected 3 eligible incidents, got {result.incidents_eligible}"
        assert len(result.incident_results) == 3, \
            f"Expected 3 results, got {len(result.incident_results)}"

        # Verify processed incidents were 01, 02, 03
        processed_ids = [r["incident_id"] for r in result.incident_results]
        assert processed_ids == ["incident-01", "incident-02", "incident-03"], \
            f"Expected processed 01-03, got {processed_ids}"

        # Verify cursor was saved with incident-03 (last examined)
        runs_dir = temp_external_dir.parent.parent
        cursor_file = runs_dir / "state" / "automatic-diagnosis" / "auto-loop-scan-cursor.json"
        assert cursor_file.exists(), f"Cursor file should exist at {cursor_file}"

        # Decode and verify cursor contains incident-03
        cursor_incident_id, cursor_timestamp = _read_and_decode_cursor(cursor_file)
        assert cursor_incident_id == "incident-03", \
            f"Cursor should be incident-03 (last examined), got {cursor_incident_id}"

        # Verify timestamp matches incident-03's exact timestamp
        expected_ts = datetime(2024, 6, 15, 10, 2, 0, tzinfo=UTC).isoformat()
        assert cursor_timestamp == expected_ts, \
            f"Cursor timestamp should be {expected_ts}, got {cursor_timestamp}"

    def test_cursor_resume_on_second_run(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Run 2: Resume from cursor for incident-03, processing begins at incident-04.

        Scenario:
        - Run 1 saved cursor with incident-03
        - Run 2 receives cursor, listing validates compound cursor value
        - Processing begins at incident-04 (after cursor)
        - Incidents 04-09 are not skipped

        Expected: listing receives cursor, first processed is incident-04
        """
        # Pre-seed cursor file with incident-03 using new schema
        runs_dir = temp_external_dir.parent.parent
        cursor_dir = runs_dir / "state" / "automatic-diagnosis"
        cursor_file = cursor_dir / "auto-loop-scan-cursor.json"

        _write_cursor_file(
            cursor_file,
            "incident-03",
            datetime(2024, 6, 15, 10, 2, 0, tzinfo=UTC)
        )

        # Track cursor passed to listing
        cursor_received = [None]

        # Create remaining incidents for the resume page (04-09)
        remaining_incidents = [f"incident-{i:02d}" for i in range(4, 10)]
        mock_page = _make_page(remaining_incidents, has_more=False)

        def mock_list_page(scan_cursor, scan_bound):
            # Validate that the cursor is a non-null compound cursor
            assert scan_cursor is not None, \
                "Listing should receive cursor from previous run"
            # Decode cursor to validate compound cursor value
            cursor_obj, decode_error = decode_cursor(str(scan_cursor))
            assert decode_error is None, \
                f"Cursor should be valid compound cursor, got error: {decode_error}"
            assert cursor_obj is not None
            assert cursor_obj.incident_id == "incident-03", \
                f"Cursor should reference incident-03, got {cursor_obj.incident_id}"
            cursor_received[0] = scan_cursor
            return AutomaticPageListed(page=mock_page)

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_with_pagination",
            mock_list_page,
        )

        processed = []

        def mock_process_incident(
            incident_id: str,
            external_analysis_dir: Path,
            config: AutomaticDiagnosisLoopConfig,
            collector_run_id: str,
            now: datetime,
            review_packet_budget = None,
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
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            mock_process_incident,
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary",
            lambda **kwargs: {},
        )

        # Run 2 - should resume from cursor
        _result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=10),
        )

        # Verify listing was called with cursor
        assert cursor_received[0] is not None, \
            "Listing should receive cursor from previous run"

        # Verify first processed is incident-04 (after cursor for 03)
        assert len(processed) > 0, "Should have processed incidents"
        assert processed[0] == "incident-04", \
            f"First processed should be incident-04 (after cursor), got {processed[0]}"

        # Verify incidents 04-09 were processed (not skipped)
        assert len(processed) == 6, \
            f"Expected 6 incidents (04-09), got {len(processed)}"
        assert processed == remaining_incidents, \
            f"Expected {remaining_incidents}, got {processed}"

    def test_cursor_cleared_when_suffix_empty(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Empty suffix after cursor: cursor file is removed, next run starts fresh.

        Scenario:
        - Cursor saved with incident-09 (last incident)
        - Run 2 queries with cursor
        - Returns empty page (no incidents after cursor)
        - Cursor should be cleared

        Expected: cursor file is removed
        """
        # Simulate cursor at end of list
        runs_dir = temp_external_dir.parent.parent
        cursor_dir = runs_dir / "state" / "automatic-diagnosis"
        cursor_file = cursor_dir / "auto-loop-scan-cursor.json"

        _write_cursor_file(
            cursor_file,
            "incident-09",
            datetime(2024, 6, 15, 10, 8, 0, tzinfo=UTC)
        )

        # Track cursor received
        cursor_received = [None]

        def mock_list_page(scan_cursor, scan_bound):
            cursor_received[0] = scan_cursor
            # Return empty page - no more incidents after cursor
            return AutomaticPageListed(page=_make_empty_page())

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_with_pagination",
            mock_list_page,
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

        # Verify cursor was received
        assert cursor_received[0] is not None, \
            "Listing should receive cursor"

        # Verify cursor was cleared
        assert not cursor_file.exists(), \
            "Cursor file should be removed when suffix is empty"

    def test_terminal_page_consumed_clears_cursor(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Non-empty terminal page fully consumed: cursor is cleared.

        Scenario:
        - Cursor exists from previous run
        - Listing returns a terminal page (has_more=False) with incidents
        - All incidents are processed successfully
        - Cursor should be cleared

        Expected: cursor file is removed after full consumption
        """
        # Pre-seed cursor
        runs_dir = temp_external_dir.parent.parent
        cursor_dir = runs_dir / "state" / "automatic-diagnosis"
        cursor_file = cursor_dir / "auto-loop-scan-cursor.json"

        _write_cursor_file(
            cursor_file,
            "incident-05",
            datetime(2024, 6, 15, 10, 4, 0, tzinfo=UTC)
        )

        # Terminal page with incidents 06-08, has_more=False
        terminal_incidents = ["incident-06", "incident-07", "incident-08"]
        mock_page = _make_page(terminal_incidents, has_more=False)

        def mock_list_page(scan_cursor, scan_bound):
            return AutomaticPageListed(page=mock_page)

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_with_pagination",
            mock_list_page,
        )

        def mock_process_incident(
            incident_id: str,
            external_analysis_dir: Path,
            config: AutomaticDiagnosisLoopConfig,
            collector_run_id: str,
            now: datetime,
            review_packet_budget = None,
        ) -> AutoLoopIncidentResult:
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=True,
                eligibility_reason="active_incident",
                run_id=f"run-{incident_id}",
                skipped=False,
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            mock_process_incident,
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._write_loop_summary",
            lambda **kwargs: {},
        )

        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            config=AutomaticDiagnosisLoopConfig(max_incidents_per_run=10),
        )

        # All incidents processed
        assert result.incidents_eligible == 3, \
            f"Expected 3 eligible, got {result.incidents_eligible}"

        # Cursor should be cleared after fully consuming terminal page
        assert not cursor_file.exists(), \
            "Cursor file should be removed after fully consumed terminal page"
