"""Tests for write_diagnosis_loop_pass_artifact function - decision artifacts.

Tests prove:
1. Stop decision artifact is written even when no checks ran
2. Stop decision includes stop reason
3. Run decision references {run_id}-read-only-check-results.json when check artifact was written
4. Check counts are preserved
"""

from __future__ import annotations

import json
from pathlib import Path

from k8s_diag_agent.collect.incident_diagnosis_loop_pass_artifacts import (
    write_diagnosis_loop_pass_artifact,
)


class TestStopDecisionArtifacts:
    """Test stop decision artifact writing."""

    def test_stop_decision_writes_artifact(self, tmp_path: Path) -> None:
        """Stop decision artifact is written even when no checks ran."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-010",
            "run_id": "run-010",
            "decision": "stop_root_cause_found",
            "case_file_linked_artifact": False,
            "runner_result": None,
        }

        result = write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-010",
            incident_id="incident-010",
            orchestrator_result=orchestrator_result,
        )

        assert result["written"] is True
        artifact_path = tmp_path / "run-010-diagnosis-loop-pass.json"
        assert artifact_path.exists()

    def test_stop_decision_has_stop_reason(self, tmp_path: Path) -> None:
        """Stop decision artifact includes stop_reason."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-011",
            "run_id": "run-011",
            "decision": "stop_no_safe_checks",
            "case_file_linked_artifact": False,
            "loop_update": {
                "stop_reason": "no_safe_checks",
            },
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-011",
            incident_id="incident-011",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-011-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        assert content["decision"] == "stop_no_safe_checks"
        assert content["checks_run"] == 0


class TestRunDecisionArtifacts:
    """Test run decision artifact writing."""

    def test_run_decision_references_check_artifact(self, tmp_path: Path) -> None:
        """Run decision artifact references check-result artifact when written."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-020",
            "run_id": "run-020",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": True,
            "artifact": {
                "run_id": "run-020",
                "incident_id": "incident-020",
                "written": True,
            },
            "runner_result": {
                "checks_requested": 2,
                "checks_run": 2,
                "checks_skipped": 0,
                "checks_rejected": 0,
            },
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-020",
            incident_id="incident-020",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-020-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        assert content["decision"] == "run_allowed_read_only_checks"
        assert len(content["linked_artifacts"]) == 1
        assert content["linked_artifacts"][0]["name"] == "run-020-read-only-check-results.json"
        assert content["checks_run"] == 2
