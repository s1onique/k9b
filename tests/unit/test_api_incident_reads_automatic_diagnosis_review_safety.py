"""Tests for automatic_diagnosis_review safety assertions.

Tests cover:
- no raw packet content
- no paths
- no action-control fields
"""

from __future__ import annotations

import json
from pathlib import Path

from k8s_diag_agent.ui.api_incident_reads import build_automatic_diagnosis_review_payload
from tests.unit.conftest import write_review_packet  # noqa: F401


class TestAutomaticDiagnosisReviewSafety:
    """Safety tests - forbidden fields must not appear."""

    def test_no_raw_packet_content_exposed(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove raw packet content is not exposed."""
        write_review_packet(
            temp_external_dir=temp_external_dir,
            incident_id="test-incident",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            sample_case_file=sample_case_file,
            sample_orchestrator_result=sample_orchestrator_result,
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        # These fields should NOT be in the result
        assert "case_file" not in result
        assert "runner_result" not in result
        assert "selected_checks" not in result
        # decision is ok, raw result is not
        assert "loop_result" not in result or "decision" in result

    def test_no_paths_exposed(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove absolute filesystem paths are not exposed."""
        write_review_packet(
            temp_external_dir=temp_external_dir,
            incident_id="test-incident",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            sample_case_file=sample_case_file,
            sample_orchestrator_result=sample_orchestrator_result,
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")
        result_str = json.dumps(result)

        # No absolute paths should be in the result
        assert "/some/path" not in result_str
        assert "/Volumes/" not in result_str
        assert "/Users/" not in result_str

    def test_no_action_control_fields(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove no action-control fields are exposed."""
        write_review_packet(
            temp_external_dir=temp_external_dir,
            incident_id="test-incident",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            sample_case_file=sample_case_file,
            sample_orchestrator_result=sample_orchestrator_result,
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")
        result_str = json.dumps(result)

        # No action-control fields should be in the result
        forbidden = ["apply", "delete", "patch", "scale", "restart", "rollout", "kubectl", "helm"]
        for field in forbidden:
            assert field not in result_str


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
