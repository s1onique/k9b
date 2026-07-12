"""Regression tests for existing packet and alert refresh bugs.

Tests prove that:
1. Existing review packets don't prevent diagnosis loop from running
2. Alert refresh doesn't starve unprocessed pending work
"""

from __future__ import annotations

from datetime import UTC, datetime
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
from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
    DiagnosisPageIncident,
)
from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
    IncidentDiagnosisPage,
)
from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    cursor_after_page_incident,
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


def _make_page_incident(incident_id: str, hour: int, minute: int = 0) -> DiagnosisPageIncident:
    """Create a DiagnosisPageIncident with exact timestamp text."""
    timestamp = datetime(2024, 6, 15, hour, minute, 0, tzinfo=UTC)
    ts_text = timestamp.isoformat()
    return DiagnosisPageIncident(
        incident_id=incident_id,
        status="open",
        first_observed_at=timestamp,
        first_observed_at_key=ts_text,
    )


def _make_page(incident_ids: list[str], start_hour: int = 10) -> IncidentDiagnosisPage:
    """Create an IncidentDiagnosisPage for testing."""
    incidents = []
    for i, inc_id in enumerate(incident_ids):
        ts = datetime(2024, 6, 15, start_hour, i, 0, tzinfo=UTC)
        ts_text = ts.isoformat()
        incidents.append(DiagnosisPageIncident(
            incident_id=inc_id,
            status="open",
            first_observed_at=ts,
            first_observed_at_key=ts_text,
        ))

    has_more = len(incidents) > 0
    next_cursor = cursor_after_page_incident(incidents[-1]) if has_more else None

    return IncidentDiagnosisPage(
        incidents=tuple(incidents),
        next_cursor=next_cursor,
        has_more=has_more,
    )


def _mock_incident(incident_id: str) -> MagicMock:
    """Create a mock incident object for fetch_incident_for_diagnosis."""
    mock = MagicMock()
    mock.incident_id = incident_id
    mock.signals = []
    mock.to_dict.return_value = {
        "incident_id": incident_id,
        "status": "open",
        "title": f"Test incident {incident_id}",
        "first_observed_at": "2024-06-15T10:00:00+00:00",
    }
    return mock


class TestExistingPacketContinuesIntoLoop:
    """Test that existing review packets don't prevent diagnosis loop from running."""

    def test_existing_review_packet_runs_diagnosis_loop(
        self,
        temp_external_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        enabled_auto_loop,
    ) -> None:
        """Bug fix regression: Existing review packet should not skip diagnosis loop."""
        # Create page with one incident
        mock_page = _make_page(["incident-01"])

        def mock_list_page(scan_cursor, scan_bound):
            return AutomaticPageListed(page=mock_page)

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_with_pagination",
            mock_list_page,
        )

        # Mock the typed backend lookup to avoid needing a real
        # incident store. The new typed helper returns
        # ``BackendIncidentFound`` directly, so we wrap the legacy
        # mock incident in the canonical found outcome.
        from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
            BackendIncidentFound,
            BackendIncidentLookupSource,
        )
        from k8s_diag_agent.domain.incident_lifecycle import IncidentId

        def mock_fetch_typed(incident_id: IncidentId):
            return BackendIncidentFound(
                requested_incident_id=incident_id,
                incident=_mock_incident(str(incident_id)),
                source=BackendIncidentLookupSource.BACKEND_API,
                http_status=200,
                payload_schema_version=1,
                payload_type="incident-internal-detail",
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor.fetch_backend_incident_for_diagnosis_typed",
            mock_fetch_typed,
        )

        # Mock evaluate_incident_eligibility to return eligible (aggregate path used by the processor)
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor.evaluate_incident_eligibility",
            lambda *args, **kwargs: MagicMock(eligible=True, reason="active_incident"),
        )

        # Create review packet directory with existing packet
        review_packet_dir = temp_external_dir / "review-packets"
        review_packet_dir.mkdir(parents=True, exist_ok=True)
        (review_packet_dir / "auto-incident-01-20240101-test-diagnosis-review-packet.json").touch()

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
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
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
        # Create page with two incidents
        mock_page = _make_page(["incident-old", "incident-new"])

        def mock_list_page(scan_cursor, scan_bound):
            return AutomaticPageListed(page=mock_page)

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_with_pagination",
            mock_list_page,
        )

        # Mock the typed backend lookup to avoid needing a real
        # incident store.
        from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
            BackendIncidentFound,
            BackendIncidentLookupSource,
        )
        from k8s_diag_agent.domain.incident_lifecycle import IncidentId

        def mock_fetch_typed(incident_id: IncidentId):
            return BackendIncidentFound(
                requested_incident_id=incident_id,
                incident=_mock_incident(str(incident_id)),
                source=BackendIncidentLookupSource.BACKEND_API,
                http_status=200,
                payload_schema_version=1,
                payload_type="incident-internal-detail",
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor.fetch_backend_incident_for_diagnosis_typed",
            mock_fetch_typed,
        )

        # Mock evaluate_incident_eligibility to return eligible (aggregate path used by the processor)
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor.evaluate_incident_eligibility",
            lambda *args, **kwargs: MagicMock(eligible=True, reason="active_incident"),
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
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
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
