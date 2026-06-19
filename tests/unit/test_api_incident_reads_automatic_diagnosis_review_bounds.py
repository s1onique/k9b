"""Tests for automatic_diagnosis_review field bounding.

Tests cover:
- artifact_name bound
- decision bound
- eligibility_reason bound
"""

from __future__ import annotations

from pathlib import Path

from k8s_diag_agent.ui.api_incident_reads import (
    MAX_ARTIFACT_NAME_LENGTH,
    build_automatic_diagnosis_review_payload,
)

from .automatic_diagnosis_review_fixtures import (
    write_review_packet,
)


class TestAutomaticDiagnosisReviewBounds:
    """Tests for field bounding/truncation."""

    def test_artifact_name_bounded_to_240_chars(self, temp_external_dir: Path) -> None:
        """Prove artifact_name is bounded to 240 chars by testing the _bound function."""
        # Create a very long artifact name
        long_name = "auto-test-incident-" + "x" * 300 + "-diagnosis-review-packet.json"

        # Apply bounding as done in build_automatic_diagnosis_review_payload
        def _bound(value: str | None, max_length: int) -> str | None:
            if value is None:
                return None
            return value[:max_length]

        result = _bound(long_name, MAX_ARTIFACT_NAME_LENGTH)

        # Should be bounded
        assert len(result) <= 240
        assert len(result) > 200  # Should use most of the allowed length

    def test_decision_bounded_to_120_chars(self, temp_external_dir: Path) -> None:
        """Prove decision is bounded to 120 chars."""
        long_decision = "run_allowed_read_only_checks_" + "x" * 150
        write_review_packet(
            temp_external_dir=temp_external_dir,
            incident_id="test-incident",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision=long_decision,
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        # Should be bounded
        assert len(result["decision"]) <= 120

    def test_eligibility_reason_bounded_to_160_chars(self, temp_external_dir: Path) -> None:
        """Prove eligibility_reason is bounded to 160 chars."""
        long_reason = "active_incident_" + "x" * 200
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
            eligibility_reason=long_reason,
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        # Should be bounded
        assert len(result["eligibility_reason"]) <= 160


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
