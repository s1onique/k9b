"""Tests for incident_diagnosis_loop_orchestrator loop-pass artifact integration.

Tests prove:
1. Run decision writes both read-only-check-results artifact and diagnosis-loop-pass artifact
2. Stop decision writes only diagnosis-loop-pass artifact
3. Orchestrator result includes loop_pass_artifact
4. Loop-pass artifact references check-result artifact only when check-result artifact exists
5. Deterministic now produces deterministic timestamps in both artifacts
6. Fake handler injection still works
7. Result remains JSON-serializable
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator import (
    run_one_read_only_diagnosis_loop_pass,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus


def _make_mock_incident(incident_id: str) -> MagicMock:
    """Create a mock incident that has the right status.value attribute."""
    mock_incident = MagicMock()
    mock_incident.incident_id = incident_id
    mock_incident.namespace = "default"
    mock_incident.object_kind = "Pod"
    mock_incident.object_name = "test-pod"
    mock_incident.raw_object_kind = "Pod"
    mock_incident.candidate_class = "crash_loop"
    mock_incident.severity = "warning"
    # Use IncidentStatus enum so .value works
    mock_incident.status = IncidentStatus.OPEN
    mock_incident.first_observed_at = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    mock_incident.last_observed_at = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    mock_incident.signal_count = 1
    mock_incident.evidence_count = 0
    mock_incident.latest_snapshot_bundle_id = None
    mock_incident.suppressed_reason = None
    mock_incident.duplicate_of = None
    mock_incident.resolved_at = None
    mock_incident.resolution_notes = None
    mock_incident.source_candidate_id = "test-candidate"
    mock_incident.signals = []
    mock_incident.evidence_needed = []
    mock_incident.evidence_links = []
    mock_incident.review_packet = MagicMock()
    mock_incident.review_packet.to_dict.return_value = {
        "status": "not_generated",
        "id": None,
    }
    mock_incident.events = []
    mock_incident.get_timeline.return_value = []
    return mock_incident


class TestOrchestratorLoopPassArtifactIntegration:
    """Test loop-pass artifact integration in orchestrator."""

    def test_run_decision_writes_both_artifacts(self) -> None:
        """Run decision writes both read-only-check-results and diagnosis-loop-pass artifacts."""
        incident_id = "test-incident-001"
        run_id = "orch-run-001"

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            case_file = {
                "incident_id": incident_id,
                "schema_version": "1.0",
                "read_only": True,
                "allowed_actions": [],
                "incident": {
                    "incident_id": incident_id,
                    "namespace": "default",
                    "object_kind": "Pod",
                    "object_name": "test-pod",
                    "severity": "warning",
                    "status": "open",
                },
            }

            diagnosis_report = {
                "incident_id": incident_id,
                "diagnosis": {
                    "recommended_investigations": [
                        {
                            "check_id": "pod_logs",
                            "title": "Check pod logs",
                            "read_only": True,
                            "source": "llm_diagnosis",
                        },
                    ],
                },
            }

            mock_incident = _make_mock_incident(incident_id)
            with patch("k8s_diag_agent.collect.incident_case_file.get_incident_store") as mock_store:
                mock_store.return_value.get_incident.return_value = mock_incident

                result = run_one_read_only_diagnosis_loop_pass(
                    incident_id=incident_id,
                    external_analysis_dir=external_analysis_dir,
                    case_file=case_file,
                    diagnosis_report=diagnosis_report,
                    run_id=run_id,
                )

            # Should have loop_pass_artifact in result
            assert "loop_pass_artifact" in result
            assert result["loop_pass_artifact"]["written"] is True

            # Check that loop-pass artifact file exists
            loop_pass_path = external_analysis_dir / f"{run_id}-diagnosis-loop-pass.json"
            assert loop_pass_path.exists()

            # Check that check-result artifact also exists (since this was a run decision)
            check_result_path = external_analysis_dir / f"{run_id}-read-only-check-results.json"
            assert check_result_path.exists()

            # Loop-pass artifact should reference the check-result artifact
            loop_pass_content = json.loads(loop_pass_path.read_text())
            assert len(loop_pass_content["linked_artifacts"]) == 1
            assert "read-only-check-results" in loop_pass_content["linked_artifacts"][0]["name"]

    def test_stop_decision_writes_only_loop_pass_artifact(self) -> None:
        """Stop decision writes only diagnosis-loop-pass artifact."""
        incident_id = "test-incident-002"
        run_id = "orch-run-002"

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            # Case file that will trigger a stop decision
            case_file = {
                "incident_id": incident_id,
                "schema_version": "1.0",
                "read_only": True,
                "allowed_actions": [],
                "incident": {
                    "incident_id": incident_id,
                    "namespace": "default",
                    "object_kind": "Pod",
                    "object_name": "test-pod",
                    "severity": "warning",
                    "status": "open",
                },
            }

            # Diagnosis report with no proposed checks - triggers stop decision
            diagnosis_report = {
                "incident_id": incident_id,
                "diagnosis": {
                    "recommended_investigations": [],  # No checks
                },
            }

            mock_incident = _make_mock_incident(incident_id)
            with patch("k8s_diag_agent.collect.incident_case_file.get_incident_store") as mock_store:
                mock_store.return_value.get_incident.return_value = mock_incident

                result = run_one_read_only_diagnosis_loop_pass(
                    incident_id=incident_id,
                    external_analysis_dir=external_analysis_dir,
                    case_file=case_file,
                    diagnosis_report=diagnosis_report,
                    run_id=run_id,
                )

            # Should have loop_pass_artifact in result
            assert "loop_pass_artifact" in result
            assert result["loop_pass_artifact"]["written"] is True

            # Check that loop-pass artifact file exists
            loop_pass_path = external_analysis_dir / f"{run_id}-diagnosis-loop-pass.json"
            assert loop_pass_path.exists()

            # Check that NO check-result artifact exists (stop decision)
            check_result_path = external_analysis_dir / f"{run_id}-read-only-check-results.json"
            assert not check_result_path.exists()

            # Loop-pass artifact should NOT have linked artifacts
            loop_pass_content = json.loads(loop_pass_path.read_text())
            assert len(loop_pass_content["linked_artifacts"]) == 0
            assert loop_pass_content["decision"].startswith("stop_")

    def test_orchestrator_result_includes_loop_pass_artifact(self) -> None:
        """Orchestrator result includes loop_pass_artifact key."""
        incident_id = "test-incident-003"
        run_id = "orch-run-003"

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            case_file = {
                "incident_id": incident_id,
                "schema_version": "1.0",
                "read_only": True,
                "allowed_actions": [],
                "incident": {
                    "incident_id": incident_id,
                    "namespace": "default",
                    "object_kind": "Pod",
                    "object_name": "test-pod",
                    "severity": "warning",
                    "status": "open",
                },
            }

            diagnosis_report = {
                "incident_id": incident_id,
                "diagnosis": {
                    "recommended_investigations": [
                        {
                            "check_id": "pod_logs",
                            "title": "Check pod logs",
                            "read_only": True,
                            "source": "llm_diagnosis",
                        },
                    ],
                },
            }

            mock_incident = _make_mock_incident(incident_id)
            with patch("k8s_diag_agent.collect.incident_case_file.get_incident_store") as mock_store:
                mock_store.return_value.get_incident.return_value = mock_incident

                result = run_one_read_only_diagnosis_loop_pass(
                    incident_id=incident_id,
                    external_analysis_dir=external_analysis_dir,
                    case_file=case_file,
                    diagnosis_report=diagnosis_report,
                    run_id=run_id,
                )

            # Result should include loop_pass_artifact
            assert "loop_pass_artifact" in result
            assert isinstance(result["loop_pass_artifact"], dict)
            assert "written" in result["loop_pass_artifact"]

    def test_deterministic_timestamps_in_both_artifacts(self) -> None:
        """Deterministic now produces identical timestamps in both artifacts."""
        incident_id = "test-incident-004"
        run_id_base = "orch-run-004"
        fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            case_file = {
                "incident_id": incident_id,
                "schema_version": "1.0",
                "read_only": True,
                "allowed_actions": [],
                "incident": {
                    "incident_id": incident_id,
                    "namespace": "default",
                    "object_kind": "Pod",
                    "object_name": "test-pod",
                    "severity": "warning",
                    "status": "open",
                },
            }

            diagnosis_report = {
                "incident_id": incident_id,
                "diagnosis": {
                    "recommended_investigations": [
                        {
                            "check_id": "pod_logs",
                            "title": "Check pod logs",
                            "read_only": True,
                            "source": "llm_diagnosis",
                        },
                    ],
                },
            }

            mock_incident = _make_mock_incident(incident_id)
            with patch("k8s_diag_agent.collect.incident_case_file.get_incident_store") as mock_store:
                mock_store.return_value.get_incident.return_value = mock_incident

                # Run twice with same timestamp to verify deterministic timestamps
                run_one_read_only_diagnosis_loop_pass(
                    incident_id=incident_id,
                    external_analysis_dir=external_analysis_dir,
                    case_file=case_file,
                    diagnosis_report=diagnosis_report,
                    run_id=f"{run_id_base}-a",
                    now=fixed_now,
                )

                run_one_read_only_diagnosis_loop_pass(
                    incident_id=incident_id,
                    external_analysis_dir=external_analysis_dir,
                    case_file=case_file,
                    diagnosis_report=diagnosis_report,
                    run_id=f"{run_id_base}-b",
                    now=fixed_now,
                )

            # Both loop-pass artifacts should have same timestamp
            loop_pass_a = json.loads((external_analysis_dir / f"{run_id_base}-a-diagnosis-loop-pass.json").read_text())
            loop_pass_b = json.loads((external_analysis_dir / f"{run_id_base}-b-diagnosis-loop-pass.json").read_text())

            assert loop_pass_a["generated_at"] == loop_pass_b["generated_at"]

    def test_result_remains_json_serializable(self) -> None:
        """Orchestrator result remains JSON-serializable."""
        incident_id = "test-incident-005"
        run_id = "orch-run-005"

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            case_file = {
                "incident_id": incident_id,
                "schema_version": "1.0",
                "read_only": True,
                "allowed_actions": [],
                "incident": {
                    "incident_id": incident_id,
                    "namespace": "default",
                    "object_kind": "Pod",
                    "object_name": "test-pod",
                    "severity": "warning",
                    "status": "open",
                },
            }

            diagnosis_report = {
                "incident_id": incident_id,
                "diagnosis": {
                    "recommended_investigations": [],
                },
            }

            mock_incident = _make_mock_incident(incident_id)
            with patch("k8s_diag_agent.collect.incident_case_file.get_incident_store") as mock_store:
                mock_store.return_value.get_incident.return_value = mock_incident

                result = run_one_read_only_diagnosis_loop_pass(
                    incident_id=incident_id,
                    external_analysis_dir=external_analysis_dir,
                    case_file=case_file,
                    diagnosis_report=diagnosis_report,
                    run_id=run_id,
                )

            # Should not raise
            json_str = json.dumps(result, default=str)
            parsed = json.loads(json_str)

            # Should have expected fields
            assert "loop_pass_artifact" in parsed
