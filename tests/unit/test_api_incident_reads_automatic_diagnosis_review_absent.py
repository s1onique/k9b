"""Tests for automatic_diagnosis_review when no packet exists.

Tests cover:
- dir None
- dir missing
- no packet for incident
"""

from __future__ import annotations

from pathlib import Path

from k8s_diag_agent.ui.api_incident_reads import build_automatic_diagnosis_review_payload


class TestAutomaticDiagnosisReviewAbsent:
    """Tests for unavailable state when no packet exists."""

    def test_returns_unavailable_when_dir_is_none(self) -> None:
        """Prove returns unavailable when external_analysis_dir is None."""
        result = build_automatic_diagnosis_review_payload(None, "test-incident")

        assert result["available"] is False
        assert result["unavailable_reason"] == "no_review_packet"

    def test_returns_unavailable_when_dir_does_not_exist(
        self, temp_external_dir: Path
    ) -> None:
        """Prove returns unavailable when directory doesn't exist."""
        nonexistent_dir = temp_external_dir.parent / "nonexistent"
        result = build_automatic_diagnosis_review_payload(nonexistent_dir, "test-incident")

        assert result["available"] is False
        assert result["unavailable_reason"] == "no_review_packet"

    def test_returns_unavailable_when_no_packet_for_incident(
        self, temp_external_dir: Path
    ) -> None:
        """Prove returns unavailable when no packet exists for incident."""
        result = build_automatic_diagnosis_review_payload(
            temp_external_dir, "nonexistent-incident"
        )

        assert result["available"] is False
        assert result["unavailable_reason"] == "no_review_packet"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
