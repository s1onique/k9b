"""Tests for schema evidence workflow integration in k9b_cnpg_live_lab_bootstrap.py.

This module tests:
- Workflow dry-run warning path behavior
"""

import json
import sys
import tempfile
from pathlib import Path

# Import the functions to test
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from k9b_cnpg_live_lab_bootstrap import (
    FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
    extract_schema_warnings,
    write_schema_warnings_json,
)


class TestWorkflowSchemaWarningPath:
    """Tests for workflow dry-run warning path behavior."""

    def test_workflow_calls_both_extract_and_classify_on_warning(self) -> None:
        """When dry-run schema warnings are detected with exit code 0, workflow calls both extract-schema-evidence and classify-schema."""
        import re
        workflow_content = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-cnpg-incident-lab-live.yml"
        content = workflow_content.read_text()

        # Find the dry-run validation step
        dry_run_section = content[content.find("Validate manifests with server-side dry-run"):]
        dry_run_section = dry_run_section[:dry_run_section.find("\n      # =====", 1) if "\n      # =====" in dry_run_section else len(dry_run_section)]

        # The warning path should have both extract-schema-evidence AND classify-schema
        assert "extract-schema-evidence" in dry_run_section, \
            "Dry-run warning path must call extract-schema-evidence"

        # Check that classify-schema is also present in the warning path
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
