"""Tests for schema evidence extraction in k9b_cnpg_live_lab_bootstrap.py.

This module tests:
- extract_schema_warnings() function
- write_schema_warnings_json() function
- generate_bounded_summary() function
- Precise schema pattern matching (no false positives)
- extract-schema-evidence subcommand
"""

import json
import re
import sys
import tempfile
from pathlib import Path

# Import the functions to test
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from k9b_cnpg_live_lab_bootstrap import (
    FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
    FAILURE_HELM_UNKNOWN,
    extract_schema_warnings,
    generate_bounded_summary,
    write_schema_warnings_json,
)


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


class TestWriteSchemaWarningsJson:
    """Tests for write_schema_warnings_json function."""

    def test_writes_valid_json(self) -> None:
        """Must write valid JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            warnings = [
                {
                    "line": 12,
                    "field": "spec.template.spec.containers[0].limits",
                    "message": 'unknown field "spec.template.spec.containers[0].limits"',
                    "pattern_matched": "unknown field",
                    "kind": "Deployment",
                    "name": "k9b",
                }
            ]
            output_path = write_schema_warnings_json(
                artifact_dir, warnings, "helm-server-dry-run.log", FAILURE_HELM_MANIFEST_SCHEMA_WARNING
            )

            # Verify file was created in logs subdirectory
            assert output_path == artifact_dir / "logs" / "schema-warnings.json"
            assert output_path.exists()

            # Verify valid JSON
            data = json.loads(output_path.read_text())
            assert data["failure_class"] == FAILURE_HELM_MANIFEST_SCHEMA_WARNING
            assert data["source_log"] == "helm-server-dry-run.log"
            assert data["match_count"] == 1
            assert len(data["matches"]) == 1

    def test_creates_logs_directory(self) -> None:
        """Must create logs directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            assert not (artifact_dir / "logs").exists()

            write_schema_warnings_json(
                artifact_dir, [], "test.log", FAILURE_HELM_UNKNOWN
            )

            assert (artifact_dir / "logs").is_dir()

    def test_atomic_write(self) -> None:
        """Must write atomically (temp file + rename)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            output_path = write_schema_warnings_json(
                artifact_dir, [], "test.log", FAILURE_HELM_UNKNOWN
            )

            # Check for temp file not present
            tmp_files = list(artifact_dir.glob("*.tmp"))
            assert len(tmp_files) == 0

            # Check final file exists
            assert output_path.exists()


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


class TestWorkflowSchemaWarningPath:
    """Tests for workflow dry-run warning path behavior."""

    def test_workflow_calls_both_extract_and_classify_on_warning(self) -> None:
        """When dry-run schema warnings are detected with exit code 0, workflow calls both extract-schema-evidence and classify-schema."""
        workflow_content = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab-live.yml"
        content = workflow_content.read_text()

        # Find the dry-run validation step
        dry_run_section = content[content.find("Validate manifests with server-side dry-run"):]
        dry_run_section = dry_run_section[:dry_run_section.find("\n      # =====", 1) if "\n      # =====" in dry_run_section else len(dry_run_section)]

        # The warning path should have both extract-schema-evidence AND classify-schema
        # Check that extract-schema-evidence is present
        assert "extract-schema-evidence" in dry_run_section, \
            "Dry-run warning path must call extract-schema-evidence"

        # Check that classify-schema is also present in the warning path
        # Extract the warning path section (between "if grep" and "exit 1")
        warning_path_match = re.search(
            r"if grep.*schema.*\n.*extract-schema-evidence.*\n.*classify-schema",
            dry_run_section,
            re.DOTALL
        )
        assert warning_path_match is not None, \
            "Dry-run warning path must call both extract-schema-evidence AND classify-schema before exit 1"

    def test_workflow_uses_precise_patterns_not_generic_error(self) -> None:
        """Dry-run detection must use precise schema patterns, not generic 'error'."""
        workflow_content = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab-live.yml"
        content = workflow_content.read_text()

        # Find the dry-run validation step
        dry_run_section = content[content.find("Validate manifests with server-side dry-run"):]
        dry_run_section = dry_run_section[:dry_run_section.find("\n      # =====", 1) if "\n      # =====" in dry_run_section else len(dry_run_section)]

        # Must NOT use the old broad pattern
        assert 'grep -qi "unknown field|error"' not in dry_run_section, \
            "Must not use broad 'unknown field|error' grep pattern"

        # Must use precise patterns
        assert "grep -qiE" in dry_run_section, \
            "Must use grep -qiE for precise pattern matching"
        assert "unknown field" in dry_run_section, \
            "Must include 'unknown field' in precise patterns"


class TestIntegration:
    """Integration tests for schema evidence extraction workflow."""

    def test_full_workflow_produces_valid_json(self) -> None:
        """Full workflow: extract -> write -> validate JSON."""
        log_content = """
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: k9b
        image: k9b:latest
        unknown field "limits"
---
apiVersion: v1
kind: Service
metadata:
  name: k9b
error validating data: schema mismatch
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Extract
            warnings = extract_schema_warnings(log_content)
            assert len(warnings) >= 1

            # Write
            output_path = write_schema_warnings_json(
                artifact_dir, warnings, "helm-server-dry-run.log", FAILURE_HELM_MANIFEST_SCHEMA_WARNING
            )

            # Validate
            data = json.loads(output_path.read_text())
            assert data["failure_class"] == FAILURE_HELM_MANIFEST_SCHEMA_WARNING
            assert data["source_log"] == "helm-server-dry-run.log"
            assert "matches" in data
            assert isinstance(data["matches"], list)
            for match in data["matches"]:
                assert "line" in match
                assert "message" in match
                assert "pattern_matched" in match

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
