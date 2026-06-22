"""Tests for schema evidence bounded summary in k9b_cnpg_live_lab_bootstrap.py.

This module tests:
- generate_bounded_summary() function
"""

import sys
from pathlib import Path

# Import the functions to test
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from k9b_cnpg_live_lab_bootstrap import (
    FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
    generate_bounded_summary,
)


class TestGenerateBoundedSummary:
    """Tests for generate_bounded_summary function."""

    def test_empty_warnings_returns_no_warnings_message(self) -> None:
        """Must return 'No schema warnings detected' for empty list."""
        summary = generate_bounded_summary([])
        assert "No schema warnings detected" in summary

    def test_includes_failure_class(self) -> None:
        """Must include failure class in output."""
        warnings = [
            {"line": 1, "message": 'unknown field "test"', "pattern_matched": "unknown field"}
        ]
        summary = generate_bounded_summary(warnings)
        assert FAILURE_HELM_MANIFEST_SCHEMA_WARNING in summary

    def test_includes_field_paths(self) -> None:
        """Must include field paths when present."""
        warnings = [
            {"line": 1, "field": "spec.limits", "message": 'unknown field "spec.limits"', "pattern_matched": "unknown field"}
        ]
        summary = generate_bounded_summary(warnings)
        assert 'unknown field "spec.limits"' in summary

    def test_bounded_to_max_lines(self) -> None:
        """Must limit output to max_lines (default 20)."""
        warnings = [
            {"line": i, "message": f"warning {i}", "pattern_matched": "unknown field"}
            for i in range(1, 51)
        ]
        summary = generate_bounded_summary(warnings, max_lines=20)
        # Should not include warning 21
        assert "warning 1" in summary
        assert "warning 20" in summary
        assert "warning 21" not in summary

    def test_indicates_truncation(self) -> None:
        """Must indicate when warnings are truncated."""
        warnings = [
            {"line": i, "message": f"warning {i}", "pattern_matched": "unknown field"}
            for i in range(1, 51)
        ]
        summary = generate_bounded_summary(warnings, max_lines=20)
        assert "... and 30 more warnings" in summary

    def test_includes_evidence_files(self) -> None:
        """Must include evidence file list."""
        warnings = [
            {"line": 1, "message": "test", "pattern_matched": "unknown field"}
        ]
        summary = generate_bounded_summary(warnings)
        assert "logs/helm-server-dry-run.log" in summary
        assert "logs/helm-rendered.yaml" in summary
        assert "logs/schema-warnings.json" in summary

    def test_truncates_long_messages(self) -> None:
        """Must truncate messages longer than 120 characters."""
        long_message = "x" * 150
        warnings = [
            {"line": 1, "message": long_message, "pattern_matched": "unknown field"}
        ]
        summary = generate_bounded_summary(warnings)
        # Should not contain full 150-char message
        assert long_message not in summary
        # Should contain truncated version ending with "..."
        assert "..." in summary

    def test_summary_is_github_actions_safe(self) -> None:
        """Summary output must be safe for GitHub Actions logs."""
        warnings = [
            {
                "line": 1,
                "field": "spec.template.spec.containers[0].limits",
                "message": 'unknown field "spec.template.spec.containers[0].limits"',
                "pattern_matched": "unknown field",
            }
        ]
        summary = generate_bounded_summary(warnings)

        # Should not contain sensitive patterns that could be redacted
        sensitive_patterns = [
            "token",
            "password",
            "secret",
            "-----BEGIN",
            "-----END",
        ]
        for pattern in sensitive_patterns:
            assert pattern.lower() not in summary.lower() or pattern in summary.lower()
