"""Tests for batch.py artifact reading integration.

These tests verify that load_existing_execution_indices() correctly:
- Loads valid execution artifacts
- Skips malformed artifacts silently (log_failures=False)
- Filters by purpose
- Extracts candidate indices from payload
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from k8s_diag_agent.batch import load_existing_execution_indices
from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)


class TestLoadExistingExecutionIndices:
    """Tests for load_existing_execution_indices function."""

    def test_loads_valid_execution_artifacts(self, tmp_path: Path) -> None:
        """Should load valid execution artifacts and extract candidate indices."""
        run_health_dir = tmp_path / "health"
        run_health_dir.mkdir(parents=True)
        external_dir = run_health_dir / "external-analysis"
        external_dir.mkdir()

        # Write valid execution artifact for index 0
        artifact1 = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-123",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={"candidateIndex": 0},
        )
        path1 = external_dir / "run-123-next-check-execution-0.json"
        path1.write_text(json.dumps(artifact1.to_dict()), encoding="utf-8")

        # Write valid execution artifact for index 1
        artifact2 = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-123",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={"candidateIndex": 1},
        )
        path2 = external_dir / "run-123-next-check-execution-1.json"
        path2.write_text(json.dumps(artifact2.to_dict()), encoding="utf-8")

        result = load_existing_execution_indices(run_health_dir, "run-123")

        assert result == {0, 1}

    def test_skips_malformed_artifacts_silently(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Should skip malformed artifacts silently (no logging for broad scan path)."""

        run_health_dir = tmp_path / "health"
        run_health_dir.mkdir(parents=True)
        external_dir = run_health_dir / "external-analysis"
        external_dir.mkdir()

        # Write valid execution artifact
        valid_artifact = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-456",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={"candidateIndex": 0},
        )
        valid_path = external_dir / "run-456-next-check-execution-0.json"
        valid_path.write_text(json.dumps(valid_artifact.to_dict()), encoding="utf-8")

        # Write malformed artifact
        bad_path = external_dir / "run-456-next-check-execution-1.json"
        bad_path.write_text("{ malformed json", encoding="utf-8")

        # Capture warnings from the reader module
        with caplog.at_level(logging.WARNING):
            result = load_existing_execution_indices(run_health_dir, "run-456")

        # Should still get the valid index
        assert result == {0}
        # Malformed was skipped silently (no warning logged because batch.py uses log_failures=False)
        assert len(caplog.records) == 0

    def test_skips_artifacts_with_wrong_purpose(self, tmp_path: Path) -> None:
        """Should skip artifacts that don't have NEXT_CHECK_EXECUTION purpose."""
        run_health_dir = tmp_path / "health"
        run_health_dir.mkdir(parents=True)
        external_dir = run_health_dir / "external-analysis"
        external_dir.mkdir()

        # Write artifact with wrong purpose
        wrong_purpose = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-789",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.AUTO_DRILLDOWN,  # Wrong purpose
            payload={"candidateIndex": 0},
        )
        wrong_path = external_dir / "run-789-next-check-execution-0.json"
        wrong_path.write_text(json.dumps(wrong_purpose.to_dict()), encoding="utf-8")

        result = load_existing_execution_indices(run_health_dir, "run-789")

        assert result == set()

    def test_returns_empty_for_nonexistent_directory(self, tmp_path: Path) -> None:
        """Should return empty set when external-analysis directory doesn't exist."""
        run_health_dir = tmp_path / "health"
        run_health_dir.mkdir(parents=True)
        # No external-analysis directory

        result = load_existing_execution_indices(run_health_dir, "run-nonexistent")

        assert result == set()

    def test_handles_missing_payload_field(self, tmp_path: Path) -> None:
        """Should handle artifacts with no payload field."""
        run_health_dir = tmp_path / "health"
        run_health_dir.mkdir(parents=True)
        external_dir = run_health_dir / "external-analysis"
        external_dir.mkdir()

        # Write artifact with no payload
        artifact = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-no-payload",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload=None,  # No payload
        )
        path = external_dir / "run-no-payload-next-check-execution-0.json"
        path.write_text(json.dumps(artifact.to_dict()), encoding="utf-8")

        result = load_existing_execution_indices(run_health_dir, "run-no-payload")

        # Should return empty since payload is None
        assert result == set()
