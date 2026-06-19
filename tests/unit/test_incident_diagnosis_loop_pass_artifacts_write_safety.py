"""Tests for write_diagnosis_loop_pass_artifact function - safety.

Tests prove:
1. Action-control fields are stripped
2. Unsafe run_id is rejected (path traversal)
3. Unsafe run_id is rejected (slash-containing)
4. Input orchestrator_result is not mutated
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from k8s_diag_agent.collect.incident_diagnosis_loop_pass_artifacts import (
    write_diagnosis_loop_pass_artifact,
)


class TestSafetyFields:
    """Test safety field handling."""

    def test_action_fields_stripped(self, tmp_path: Path) -> None:
        """Action-control fields are stripped."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-040",
            "run_id": "run-040",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
            # These should be stripped
            "execute": "kubectl exec",
            "run": "some command",
            "mutate": True,
            "action": "delete",
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-040",
            incident_id="incident-040",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-040-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        # Action fields should be stripped from top level
        assert "execute" not in content
        assert "run" not in content
        assert "mutate" not in content
        assert "action" not in content


class TestUnsafeRunId:
    """Test unsafe run_id rejection."""

    def test_path_traversal_rejected(self) -> None:
        """Path traversal run_id is rejected."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-050",
            "run_id": "run-050",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                write_diagnosis_loop_pass_artifact(
                    external_analysis_dir=Path(tmpdir),
                    run_id="../etc/passwd",
                    incident_id="incident-050",
                    orchestrator_result=orchestrator_result,
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unsafe run_id" in str(e)

    def test_slash_in_run_id_rejected(self) -> None:
        """Slash in run_id is rejected."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-051",
            "run_id": "run-051",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                write_diagnosis_loop_pass_artifact(
                    external_analysis_dir=Path(tmpdir),
                    run_id="run/subpath",
                    incident_id="incident-051",
                    orchestrator_result=orchestrator_result,
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unsafe run_id" in str(e)


class TestInputNotMutated:
    """Test input is not mutated."""

    def test_orchestrator_result_not_mutated(self, tmp_path: Path) -> None:
        """Input orchestrator_result is not mutated."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-060",
            "run_id": "run-060",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
            "runner_result": {"checks_requested": 1, "checks_run": 1},
        }
        original_keys = set(orchestrator_result.keys())

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-060",
            incident_id="incident-060",
            orchestrator_result=orchestrator_result,
        )

        # Verify input is unchanged
        assert set(orchestrator_result.keys()) == original_keys
