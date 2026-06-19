"""Tests for automatic_diagnosis_review when packet exists.

Tests cover:
- available when packet exists
- bounded summary fields
- artifact_name filename only
- safety metadata always true
"""

from __future__ import annotations

from pathlib import Path

from k8s_diag_agent.collect.incident_diagnosis_review_packet import (
    REVIEW_PACKET_ARTIFACT_TYPE,
)
from k8s_diag_agent.ui.api_incident_reads import build_automatic_diagnosis_review_payload
from tests.unit.conftest import write_review_packet  # noqa: F401


class TestAutomaticDiagnosisReviewAvailable:
    """Tests for available state when packet exists."""

    def test_returns_available_when_packet_exists(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove returns available when packet exists."""
        write_review_packet(
            temp_external_dir=temp_external_dir,
            incident_id="test-incident",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=2,
            checks_skipped=0,
            checks_rejected=1,
            eligible=True,
            eligibility_reason="active_incident",
            sample_case_file=sample_case_file,
            sample_orchestrator_result=sample_orchestrator_result,
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        assert result["available"] is True
        assert result["artifact_type"] == REVIEW_PACKET_ARTIFACT_TYPE

    def test_includes_bounded_summary_fields(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove includes bounded summary fields."""
        write_review_packet(
            temp_external_dir=temp_external_dir,
            incident_id="test-incident",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=2,
            checks_skipped=0,
            checks_rejected=1,
            eligible=True,
            eligibility_reason="active_incident",
            sample_case_file=sample_case_file,
            sample_orchestrator_result=sample_orchestrator_result,
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        assert result["checks_requested"] == 3
        assert result["checks_run"] == 2
        assert result["checks_rejected"] == 1
        assert result["eligible"] is True
        assert result["eligibility_reason"] == "active_incident"
        assert result["decision"] == "run_allowed_read_only_checks"

    def test_artifact_name_is_filename_only(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove artifact_name is filename only, no path."""
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

        # artifact_name should be just a filename, not a path
        assert "/" not in result["artifact_name"]
        assert "\\" not in result["artifact_name"]
        assert (
            result["artifact_name"]
            == "auto-test-incident-20260619-080000-abc123-diagnosis-review-packet.json"
        )

    def test_safety_metadata_is_always_true(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove safety metadata fields are always True."""
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

        assert result["read_only"] is True
        assert result["review_required_before_any_action"] is True
        assert result["no_remediation_attempted"] is True


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
