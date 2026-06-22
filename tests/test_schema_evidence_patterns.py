"""Tests for schema evidence pattern extraction in k9b_cnpg_live_lab_bootstrap.py.

This module tests:
- extract_schema_warnings() function
- Precise schema pattern matching (no false positives)
"""

import sys
from pathlib import Path

# Import the functions to test
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from k9b_cnpg_live_lab_bootstrap import extract_schema_warnings


class TestExtractSchemaWarnings:
    """Tests for extract_schema_warnings function."""

    def test_extracts_unknown_field_with_field_path(self) -> None:
        """Must extract 'unknown field' with field path."""
        log_content = """
some unrelated line
error: unknown field "spec.template.spec.containers[0].limits"
another line
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0]["field"] == "spec.template.spec.containers[0].limits"
        assert warnings[0]["pattern_matched"] == "unknown field"

    def test_extracts_multiple_unknown_fields(self) -> None:
        """Must extract multiple 'unknown field' warnings."""
        log_content = """
unknown field "spec.template.spec.containers[0].limits"
unknown field "spec.template.spec.containers[0].allowPrivilegeEscalation"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 2
        assert warnings[0]["field"] == "spec.template.spec.containers[0].limits"
        assert warnings[1]["field"] == "spec.template.spec.containers[0].allowPrivilegeEscalation"

    def test_extracts_strict_decoding_error(self) -> None:
        """Must extract 'strict decoding error' pattern."""
        log_content = """
some output
strict decoding error: field not recognized
more output
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0]["pattern_matched"] == "strict decoding error"

    def test_extracts_validation_error(self) -> None:
        """Must extract 'error validating data' pattern."""
        log_content = """
kubectl apply
error validating data: kind TestObject not found
kubectl apply failed
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0]["pattern_matched"] == "error validating data"

    def test_extracts_validationerror(self) -> None:
        """Must extract 'ValidationError' pattern (word boundary)."""
        log_content = """
ValidationError: invalid schema
"""
        warnings = extract_schema_warnings(log_content)
        # Should match because ValidationError has word boundary after it
        assert len(warnings) == 1
        assert "ValidationError" in warnings[0]["pattern_matched"]

    def test_extracts_field_not_declared_in_schema(self) -> None:
        """Must extract 'field not declared in schema' pattern."""
        log_content = """
some field not declared in schema
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0]["pattern_matched"] == "field not declared in schema"

    def test_includes_line_numbers(self) -> None:
        """Must include line numbers for each warning."""
        log_content = """line1
line2
unknown field "test"
line4
another unknown field "other"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 2
        assert warnings[0]["line"] == 3
        assert warnings[1]["line"] == 5

    def test_includes_message_text(self) -> None:
        """Must include full message text."""
        log_content = 'unknown field "spec.template.spec.containers[0].limits"\n'
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert "unknown field" in warnings[0]["message"]
        assert "spec.template.spec.containers[0].limits" in warnings[0]["message"]

    def test_no_false_positive_generic_error(self) -> None:
        """Must NOT trigger on generic 'error' word."""
        log_content = """
error handling request
error connecting to server
some error occurred
"""
        warnings = extract_schema_warnings(log_content)
        # Should not match generic "error" - only specific patterns
        assert len(warnings) == 0

    def test_no_false_positive_error_word_in_sentence(self) -> None:
        """Must NOT trigger on 'error' embedded in other words."""
        log_content = """
This is not an error, it's a warning
The error message was unhelpful
No terror here
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 0

    def test_case_insensitive_matching(self) -> None:
        """Must match patterns case-insensitively."""
        log_content = """
UNKNOWN FIELD "test"
Error Validating Data
VALIDATIONERROR
"""
        warnings = extract_schema_warnings(log_content)
        # Should match UNKNOWN FIELD and Error Validating Data
        assert len(warnings) >= 2

    def test_extracts_kind_name_from_context(self) -> None:
        """Must extract resource kind and name from context."""
        log_content = """
error from Deployment/k9b: unknown field "spec.limits"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0]["kind"] == "Deployment"
        assert warnings[0]["name"] == "k9b"

    def test_handles_empty_content(self) -> None:
        """Must handle empty log content gracefully."""
        warnings = extract_schema_warnings("")
        assert warnings == []

    def test_handles_no_matching_patterns(self) -> None:
        """Must return empty list when no patterns match."""
        log_content = """
This is just some normal output
No schema errors here
Everything is fine
"""
        warnings = extract_schema_warnings(log_content)
        assert warnings == []


class TestPrecisionPatterns:
    """Tests for precise pattern matching - no false positives."""

    def test_does_not_match_error_in_words(self) -> None:
        """Must not match 'error' when embedded in other words."""
        test_cases = [
            "terrorist attack",
            "error_handler function",
            "error-prone code",
            "no error handling",
            "erroneous data",
            "the error log",
        ]
        for content in test_cases:
            warnings = extract_schema_warnings(content)
            assert len(warnings) == 0, f"False positive on: {content}"

    def test_matches_only_valid_patterns(self) -> None:
        """Must only match documented schema validation patterns."""
        valid_patterns = [
            "unknown field",
            "strict decoding error",
            "ValidationError",
            "error validating data",
            "field not declared in schema",
        ]
        for pattern in valid_patterns:
            warnings = extract_schema_warnings(pattern)
            assert len(warnings) >= 1, f"Pattern not matched: {pattern}"

    def test_pattern_word_boundary_on_validationerror(self) -> None:
        """ValidationError must have word boundary to avoid false matches."""
        # Should match
        assert len(extract_schema_warnings("ValidationError")) == 1
        # Should NOT match (no word boundary)
        assert len(extract_schema_warnings("ValidationErrors")) == 0
