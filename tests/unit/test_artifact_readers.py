"""Tests for external_analysis/artifact_readers.py.

This module tests the typed artifact reader boundary for ExternalAnalysisArtifact.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.artifact_readers import (
    read_external_analysis_artifact,
    try_read_external_analysis_artifact,
)


class TestReadExternalAnalysisArtifact:
    """Tests for the strict reader."""

    def test_valid_artifact_loads_and_returns_typed_object(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Valid artifact should load and return typed ExternalAnalysisArtifact."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-123",
            cluster_label="prod",
            run_label="test-run",
            summary="Test analysis",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
        )
        artifact_path = tmp_path / "artifact.json"
        artifact_path.write_text(json.dumps(artifact.to_dict()), encoding="utf-8")

        result = read_external_analysis_artifact(artifact_path)

        assert isinstance(result, ExternalAnalysisArtifact)
        assert result.tool_name == "test-tool"
        assert result.run_id == "run-123"
        assert result.cluster_label == "prod"
        assert result.status == ExternalAnalysisStatus.SUCCESS
        assert result.purpose == ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION

    def test_malformed_json_fails_with_json_decode_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed JSON should raise JSONDecodeError."""
        artifact_path = tmp_path / "malformed.json"
        artifact_path.write_text("{ invalid json }", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            read_external_analysis_artifact(artifact_path)

    def test_missing_required_field_fails_with_value_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing required fields should raise ValueError from from_dict.

        Note: from_dict() uses defaults for some fields (empty string),
        but invalid timestamp format raises ValueError.
        """
        # Invalid timestamp format should raise ValueError
        incomplete = {
            "tool_name": "test",
            "run_id": "run-123",
            "cluster_label": "prod",
            "timestamp": "not-a-valid-timestamp",
        }
        artifact_path = tmp_path / "incomplete.json"
        artifact_path.write_text(json.dumps(incomplete), encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid timestamp"):
            read_external_analysis_artifact(artifact_path)

    def test_non_object_json_fails(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-object JSON (array, number) should raise ValueError."""
        # Array instead of object
        artifact_path = tmp_path / "array.json"
        artifact_path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ValueError, match="not a mapping"):
            read_external_analysis_artifact(artifact_path)

    def test_unreadable_missing_file_raises_os_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing file should raise OSError."""
        nonexistent = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            read_external_analysis_artifact(nonexistent)

    def test_roundtrip_with_all_fields(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Artifact with all fields should roundtrip correctly."""
        artifact = ExternalAnalysisArtifact(
            tool_name="full-tool",
            run_id="run-full",
            cluster_label="staging",
            run_label="full-test",
            summary="Complete analysis",
            findings=("finding1", "finding2"),
            suggested_next_checks=("check1", "check2"),
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="output text",
            provider="llamacpp",
            duration_ms=1500,
            purpose=ExternalAnalysisPurpose.AUTO_DRILLDOWN,
            payload={"key": "value"},
        )
        artifact_path = tmp_path / "full.json"
        artifact_path.write_text(json.dumps(artifact.to_dict()), encoding="utf-8")

        result = read_external_analysis_artifact(artifact_path)

        assert result.tool_name == "full-tool"
        assert result.findings == ("finding1", "finding2")
        assert result.suggested_next_checks == ("check1", "check2")
        assert result.provider == "llamacpp"
        assert result.duration_ms == 1500
        assert result.payload == {"key": "value"}


class TestTryReadExternalAnalysisArtifact:
    """Tests for the optional reader with graceful fallback."""

    def test_valid_artifact_returns_typed_object(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Valid artifact should return typed object (no logging on success)."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-456",
            cluster_label="dev",
            status=ExternalAnalysisStatus.SUCCESS,
        )
        artifact_path = tmp_path / "valid.json"
        artifact_path.write_text(json.dumps(artifact.to_dict()), encoding="utf-8")

        result = try_read_external_analysis_artifact(
            artifact_path,
            run_id="run-456",
            artifact_kind="next-check-execution",
        )

        assert result is not None
        assert isinstance(result, ExternalAnalysisArtifact)
        assert result.run_id == "run-456"

    def test_malformed_json_returns_none_and_logs(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed JSON should return None and log warning with safe metadata."""
        artifact_path = tmp_path / "bad.json"
        artifact_path.write_text("{ not valid }", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_external_analysis_artifact(
                artifact_path,
                run_id="run-789",
                artifact_kind="next-check-execution",
            )

        assert result is None
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert "Skipped malformed" in log_record.message
        assert "next-check-execution" in log_record.message
        # Verify run_id is in the extra dict (accessible via __dict__)
        assert log_record.__dict__.get("run_id") == "run-789"
        # Verify no sensitive content in logs
        assert "{" not in log_record.message
        assert "not valid" not in log_record.message

    def test_missing_file_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing file should return None."""
        nonexistent = tmp_path / "missing.json"

        result = try_read_external_analysis_artifact(
            nonexistent,
            run_id="run-missing",
            artifact_kind="next-check-execution",
        )

        assert result is None

    def test_log_failures_false_returns_none_without_logging(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When log_failures=False, should return None without logging."""
        artifact_path = tmp_path / "bad.json"
        artifact_path.write_text("{ not valid }", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_external_analysis_artifact(
                artifact_path,
                run_id="run-silent",
                artifact_kind="next-check-execution",
                log_failures=False,  # Silent mode
            )

        assert result is None
        # No warning should be logged
        assert len(caplog.records) == 0

    def test_log_failures_false_with_valid_artifact(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Valid artifact should return object even with log_failures=False."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-valid",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
        )
        artifact_path = tmp_path / "valid.json"
        artifact_path.write_text(json.dumps(artifact.to_dict()), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_external_analysis_artifact(
                artifact_path,
                run_id="run-valid",
                artifact_kind="next-check-execution",
                log_failures=False,
            )

        assert result is not None
        assert result.run_id == "run-valid"
        # No warning for valid artifact
        assert len(caplog.records) == 0

    def test_incomplete_artifact_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Artifact with invalid data that fails from_dict should return None."""
        # Invalid status value will fail from_dict parsing
        incomplete = {
            "tool_name": "test",
            "run_id": "run-incomplete",
            "cluster_label": "prod",
            "status": "not-a-valid-status",
        }
        artifact_path = tmp_path / "incomplete.json"
        artifact_path.write_text(json.dumps(incomplete), encoding="utf-8")

        result = try_read_external_analysis_artifact(
            artifact_path,
            run_id="run-incomplete",
            artifact_kind="next-check-execution",
        )

        assert result is None

    def test_array_json_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Array JSON should return None."""
        artifact_path = tmp_path / "array.json"
        artifact_path.write_text("[1, 2, 3]", encoding="utf-8")

        result = try_read_external_analysis_artifact(
            artifact_path,
            artifact_kind="next-check-execution",
        )

        assert result is None


class TestTimestampInvariant:
    """Tests for timestamp handling invariant.

    from_dict() always supplies a timestamp:
    - If timestamp field is present and valid: uses that value
    - If timestamp field is missing or None: uses current time (default_factory)
    - If timestamp field is invalid: raises ValueError

    This invariant ensures server_feedback handlers can always call .timestamp.isoformat().
    """

    def test_from_dict_supplies_timestamp_when_missing(
        self, tmp_path: Path
    ) -> None:
        """from_dict should supply current timestamp when field is missing."""
        # Artifact without timestamp field
        minimal = {
            "tool_name": "test",
            "run_id": "run-timestamp",
            "cluster_label": "prod",
        }
        artifact_path = tmp_path / "no-timestamp.json"
        artifact_path.write_text(json.dumps(minimal), encoding="utf-8")

        result = read_external_analysis_artifact(artifact_path)

        # Should have a timestamp (default_factory used)
        assert result.timestamp is not None
        # Should be a valid datetime
        assert result.timestamp.year >= 2020

    def test_from_dict_uses_explicit_timestamp(
        self, tmp_path: Path
    ) -> None:
        """from_dict should use explicit timestamp when provided."""
        explicit_ts = "2024-01-15T10:30:00Z"
        with_ts = {
            "tool_name": "test",
            "run_id": "run-explicit-ts",
            "cluster_label": "prod",
            "timestamp": explicit_ts,
        }
        artifact_path = tmp_path / "with-timestamp.json"
        artifact_path.write_text(json.dumps(with_ts), encoding="utf-8")

        result = read_external_analysis_artifact(artifact_path)

        # Should use the explicit timestamp
        assert result.timestamp is not None
        assert result.timestamp.year == 2024
        assert result.timestamp.month == 1
        assert result.timestamp.day == 15

    def test_server_feedback_can_always_call_isoformat(
        self, tmp_path: Path
    ) -> None:
        """server_feedback handlers can always call .timestamp.isoformat().

        This is a regression test ensuring the invariant that from_dict()
        always produces an artifact with a valid timestamp.
        """
        # Minimal artifact without timestamp (as might be written by older code)
        minimal = {
            "tool_name": "test",
            "run_id": "run-feedback",
            "cluster_label": "prod",
        }
        artifact_path = tmp_path / "minimal.json"
        artifact_path.write_text(json.dumps(minimal), encoding="utf-8")

        result = try_read_external_analysis_artifact(artifact_path)

        assert result is not None
        # This is what server_feedback does: timestamp = execution_artifact.timestamp.isoformat()
        timestamp_str = result.timestamp.isoformat()
        assert isinstance(timestamp_str, str)
        assert "T" in timestamp_str  # ISO format contains T separator


class TestRegressionCallSites:
    """Regression tests proving previous fallback behavior is preserved."""

    def test_batch_execution_indices_still_work(self, tmp_path: Path) -> None:
        """Test that batch.py pattern still works: skip malformed artifacts."""
        from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisPurpose

        external_dir = tmp_path / "external-analysis"
        external_dir.mkdir()

        # Write a valid execution artifact
        valid_artifact = ExternalAnalysisArtifact(
            tool_name="runner",
            run_id="run-batch-test",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={"candidateIndex": 0},
        )
        valid_path = external_dir / "run-batch-test-next-check-execution-0.json"
        valid_path.write_text(json.dumps(valid_artifact.to_dict()), encoding="utf-8")

        # Write a malformed artifact
        bad_path = external_dir / "run-batch-test-next-check-execution-1.json"
        bad_path.write_text("{ malformed", encoding="utf-8")

        # Read both - should skip bad and get valid
        from k8s_diag_agent.external_analysis.artifact_readers import (
            try_read_external_analysis_artifact,
        )

        indices = set()
        for path in external_dir.glob("run-batch-test-next-check-execution-*.json"):
            artifact = try_read_external_analysis_artifact(
                path,
                run_id="run-batch-test",
                artifact_kind="next-check-execution",
            )
            if artifact is None:
                continue
            if artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION:
                continue
            payload = artifact.payload
            if payload:
                idx = payload.get("candidateIndex")
                if isinstance(idx, int):
                    indices.add(idx)

        assert 0 in indices
        # Malformed artifact was skipped
        assert len(indices) == 1

    def test_promotion_artifact_preserves_run_id_filter(self, tmp_path: Path) -> None:
        """Test that promotion pattern still works: filter by run_id."""
        from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisPurpose

        external_dir = tmp_path / "external-analysis"
        external_dir.mkdir()

        # Write artifact for different run
        other_artifact = ExternalAnalysisArtifact(
            tool_name="promoter",
            run_id="run-other",
            cluster_label="staging",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
            payload={"runId": "run-other", "description": "other"},
        )
        other_path = external_dir / "run-other-next-check-promotion-0.json"
        other_path.write_text(json.dumps(other_artifact.to_dict()), encoding="utf-8")

        # Write artifact for target run
        target_artifact = ExternalAnalysisArtifact(
            tool_name="promoter",
            run_id="run-target",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
            payload={"runId": "run-target", "description": "target"},
        )
        target_path = external_dir / "run-target-next-check-promotion-0.json"
        target_path.write_text(json.dumps(target_artifact.to_dict()), encoding="utf-8")

        from k8s_diag_agent.external_analysis.artifact_readers import (
            try_read_external_analysis_artifact,
        )

        # Filter to only run-target promotions
        promotions = []
        for path in external_dir.glob("*-next-check-promotion-*.json"):
            artifact = try_read_external_analysis_artifact(
                path,
                run_id="run-target",
                artifact_kind="next-check-promotion",
            )
            if artifact is None:
                continue
            if artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION:
                continue
            payload = artifact.payload
            if payload and payload.get("runId") == "run-target":
                promotions.append(artifact)

        assert len(promotions) == 1
        assert promotions[0].run_id == "run-target"
