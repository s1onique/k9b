"""Tests for evidence type reporting."""

from __future__ import annotations

from scripts.incident_lifecycle_boundary.evidence_types_report import (
    format_evidence_type_report,
)


class TestEvidenceTypeReport:
    """Tests for evidence type report formatting."""

    def test_empty_errors_shows_pass(self) -> None:
        """Empty error list shows success message."""
        result = format_evidence_type_report([])
        assert "✓" in result or "passed" in result.lower()

    def test_single_error_format(self) -> None:
        """Single error is formatted with bullet point."""
        result = format_evidence_type_report(["EvidenceRoleCode alias missing"])
        assert "EvidenceRoleCode alias missing" in result

    def test_multiple_errors_format(self) -> None:
        """Multiple errors are each formatted with bullet points."""
        errors = [
            "EvidenceRoleCode alias missing",
            "EvidenceKindCode has unexpected values: ['unknown']",
        ]
        result = format_evidence_type_report(errors)
        assert "EvidenceRoleCode alias missing" in result
        assert "EvidenceKindCode has unexpected values" in result

    def test_error_contains_file_path(self) -> None:
        """Error message with file path is preserved."""
        errors = ["/path/to/file.py: EvidenceRoleCode alias missing"]
        result = format_evidence_type_report(errors)
        assert "/path/to/file.py" in result


if __name__ == "__main__":
    import unittest
    unittest.main()
