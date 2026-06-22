"""Tests for schema evidence JSON output in k9b_cnpg_live_lab_bootstrap.py.

This module tests:
- write_schema_warnings_json() function
"""

import json
import sys
import tempfile
from pathlib import Path

# Import the functions to test
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from k9b_cnpg_live_lab_bootstrap import (
    FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
    FAILURE_HELM_UNKNOWN,
    write_schema_warnings_json,
)


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
