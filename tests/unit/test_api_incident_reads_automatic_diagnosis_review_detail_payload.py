"""Tests for automatic_diagnosis_review in incident detail payload.

Tests cover:
- detail includes automatic_diagnosis_review
- unavailable when no dir
- available with packet
- safety fields in detail payload
"""

from __future__ import annotations

from pathlib import Path

from k8s_diag_agent.collect.incident_diagnosis_review_packet import (
    REVIEW_PACKET_ARTIFACT_TYPE,
)
from k8s_diag_agent.ui.api_incident_reads import build_incident_detail_payload

from .automatic_diagnosis_review_fixtures import (
    write_review_packet,
)
from .incident_lifecycle_fixtures import make_full_incident


class TestIncidentDetailPayloadWithAutoReview:
    """Tests for automatic_diagnosis_review in detail payload."""

    def test_detail_includes_automatic_diagnosis_review_field(self) -> None:
        """Prove incident detail payload includes automatic_diagnosis_review field."""
        incident = make_full_incident(incident_id="test-incident")

        result = build_incident_detail_payload(incident)

        assert "automatic_diagnosis_review" in result

    def test_detail_automatic_diagnosis_review_unavailable_when_no_dir(self) -> None:
        """Prove automatic_diagnosis_review is unavailable when no external_analysis_dir."""
        incident = make_full_incident(incident_id="test-incident")

        result = build_incident_detail_payload(incident, external_analysis_dir=None)

        assert result["automatic_diagnosis_review"]["available"] is False
        assert (
            result["automatic_diagnosis_review"]["unavailable_reason"] == "no_review_packet"
        )

    def test_detail_automatic_diagnosis_review_available_with_packet(
        self,
        temp_external_dir: Path,
    ) -> None:
        """Prove automatic_diagnosis_review is available when packet exists."""
        # Write a packet
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
        )

        incident = make_full_incident(incident_id="test-incident")

        result = build_incident_detail_payload(incident, external_analysis_dir=temp_external_dir)

        assert result["automatic_diagnosis_review"]["available"] is True
        assert (
            result["automatic_diagnosis_review"]["artifact_type"]
            == REVIEW_PACKET_ARTIFACT_TYPE
        )

    def test_detail_automatic_diagnosis_review_safety_fields(
        self,
        temp_external_dir: Path,
    ) -> None:
        """Prove automatic_diagnosis_review has safety fields set correctly."""
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
        )

        incident = make_full_incident(incident_id="test-incident")

        result = build_incident_detail_payload(incident, external_analysis_dir=temp_external_dir)

        assert result["automatic_diagnosis_review"]["read_only"] is True
        assert (
            result["automatic_diagnosis_review"]["review_required_before_any_action"] is True
        )
        assert result["automatic_diagnosis_review"]["no_remediation_attempted"] is True


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
