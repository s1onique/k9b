"""Tests for runtime structured logs verifier.

This module tests the verify_runtime_structured_logs.py script which enforces
the JSONL-only runtime log contract for the scheduler.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_runtime_structured_logs import validate_file, validate_line

# Test data
VALID_JSON_LINE = json.dumps({
    "timestamp": "2026-01-01T10:00:00Z",
    "component": "health-scheduler",
    "severity": "INFO",
    "message": "Starting scheduler",
})

INVALID_NON_JSON = "This is not JSON"
MISSING_REQUIRED_FIELD = json.dumps({
    "timestamp": "2026-01-01T10:00:00Z",
    "component": "health-scheduler",
    # missing severity and message
})

INVALID_SEVERITY = json.dumps({
    "timestamp": "2026-01-01T10:00:00Z",
    "component": "health-scheduler",
    "severity": "INVALID",
    "message": "Test",
})


class TestValidateLine:
    """Tests for validate_line function."""

    def test_valid_json_line(self) -> None:
        """Valid JSON with all required fields passes."""
        errors = validate_line(VALID_JSON_LINE, 1)
        assert errors == []

    def test_empty_line_skipped(self) -> None:
        """Empty lines are skipped (no errors)."""
        errors = validate_line("", 1)
        assert errors == []
        errors = validate_line("   ", 1)
        assert errors == []

    def test_non_json_line_fails(self) -> None:
        """Non-JSON lines fail with clear error message."""
        errors = validate_line(INVALID_NON_JSON, 2)
        assert len(errors) == 1
        assert "non-json runtime log line" in errors[0]
        assert "line 2" in errors[0]

    def test_missing_required_fields_fails(self) -> None:
        """JSON missing required fields fails."""
        errors = validate_line(MISSING_REQUIRED_FIELD, 3)
        assert len(errors) == 1
        assert "missing required fields" in errors[0]
        assert "severity" in errors[0] or "message" in errors[0]

    def test_invalid_severity_fails(self) -> None:
        """Invalid severity values fail."""
        errors = validate_line(INVALID_SEVERITY, 4)
        assert len(errors) == 1
        assert "invalid severity" in errors[0]
        assert "INVALID" in errors[0]

    def test_deprecated_alias_raw_line_fails(self) -> None:
        """Raw 'Deprecated LLM provider alias' line fails (this was the bug)."""
        errors = validate_line("Deprecated LLM provider alias used", 5)
        assert len(errors) == 1
        assert "non-json" in errors[0]

    def test_kubectl_raw_error_fails(self) -> None:
        """Raw 'kubectl failed' line fails (this was the bug)."""
        line = "kubectl failed with exit code 1: argv=['kubectl', 'version', '--output', 'json']"
        errors = validate_line(line, 6)
        assert len(errors) == 1
        assert "non-json" in errors[0]


class TestValidateFile:
    """Tests for validate_file function."""

    def test_valid_file_passes(self, tmp_path: Path) -> None:
        """File with all valid JSON lines passes."""
        file = tmp_path / "valid.log"
        file.write_text(
            VALID_JSON_LINE + "\n"
            + json.dumps({
                "timestamp": "2026-01-01T10:00:01Z",
                "component": "health-loop",
                "severity": "WARNING",
                "message": "Warning",
            }) + "\n"
        )
        passed, errors = validate_file(file)
        assert passed is True
        assert errors == []

    def test_mixed_file_fails(self, tmp_path: Path) -> None:
        """File with mixed JSON and raw lines fails."""
        file = tmp_path / "mixed.log"
        file.write_text(VALID_JSON_LINE + "\n" + "Raw text line\n" + VALID_JSON_LINE + "\n")
        passed, errors = validate_file(file)
        assert passed is False
        assert len(errors) == 1
        assert "line 2" in errors[0]

    def test_strict_severity_check(self, tmp_path: Path) -> None:
        """All valid severities pass, invalid fails."""
        valid_severities = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for sev in valid_severities:
            line = json.dumps({
                "timestamp": "2026-01-01T10:00:00Z",
                "component": "test",
                "severity": sev,
                "message": "Test",
            })
            errors = validate_line(line, 1)
            assert errors == [], f"Severity {sev} should be valid"

        invalid_line = json.dumps({
            "timestamp": "2026-01-01T10:00:00Z",
            "component": "test",
            "severity": "Notice",
            "message": "Test",
        })
        errors = validate_line(invalid_line, 1)
        assert len(errors) == 1
        assert "invalid severity" in errors[0]

    def test_known_bad_fixture_fails(self) -> None:
        """The known bad fixture from the original bug fails."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "runtime_logs_mixed.log"
        assert fixture_path.exists(), f"fixture missing: {fixture_path}"
        passed, errors = validate_file(fixture_path)
        assert passed is False, "runtime_logs_mixed.log should fail validation"
        # Should catch the two raw lines
        assert len(errors) == 2

    def test_structured_fixture_passes(self) -> None:
        """The structured fixture passes (proves conversion works)."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "runtime_logs_structured.log"
        assert fixture_path.exists(), f"fixture missing: {fixture_path}"
        passed, errors = validate_file(fixture_path)
        assert passed is True, f"runtime_logs_structured.log should pass: {errors}"
