"""Tests for health/artifact_readers.py - HealthAssessmentArtifact typed readers.

This module tests the typed artifact reader boundary for HealthAssessmentArtifact.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from k8s_diag_agent.health.artifact_readers import (
    HealthAssessmentArtifactReadError,
    read_health_assessment_artifact,
    try_read_health_assessment_artifact,
)
from k8s_diag_agent.health.loop import HealthAssessmentArtifact, HealthRating


def _make_valid_assessment(
    run_label: str = "test-run",
    run_id: str = "test-run-20260505T120000Z",
    cluster_id: str = "test-cluster",
    label: str = "test-cluster",
    health_rating: str = "healthy",
) -> dict:
    """Create a valid HealthAssessmentArtifact dict for testing."""
    return {
        "run_label": run_label,
        "run_id": run_id,
        "timestamp": "2026-05-05T12:00:00Z",
        "context": "test-context",
        "label": label,
        "cluster_id": cluster_id,
        "snapshot_path": "/path/to/snapshot.json",
        "assessment": {
            "observed_signals": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
        },
        "missing_evidence": [],
        "health_rating": health_rating,
        "notes": None,
        "artifact_path": "/path/to/assessment.json",
    }


class TestReadHealthAssessmentArtifact:
    """Tests for the strict reader."""

    def test_valid_assessment_loads_and_returns_typed_object(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Valid assessment should load and return typed HealthAssessmentArtifact."""
        assessment_data = _make_valid_assessment()
        assessment_path = tmp_path / "assessment.json"
        assessment_path.write_text(json.dumps(assessment_data), encoding="utf-8")

        result = read_health_assessment_artifact(assessment_path)

        assert isinstance(result, HealthAssessmentArtifact)
        assert result.run_label == "test-run"
        assert result.run_id == "test-run-20260505T120000Z"
        assert result.cluster_id == "test-cluster"
        assert result.health_rating == HealthRating.HEALTHY

    def test_malformed_json_fails_with_json_decode_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed JSON should raise JSONDecodeError."""
        assessment_path = tmp_path / "malformed.json"
        assessment_path.write_text("{ invalid json }", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            read_health_assessment_artifact(assessment_path)

    def test_non_object_json_fails(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-object JSON (array, number) should raise ValueError."""
        # Array instead of object
        assessment_path = tmp_path / "array.json"
        assessment_path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ValueError, match="not a mapping"):
            read_health_assessment_artifact(assessment_path)

    def test_unreadable_missing_file_raises_os_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing file should raise OSError (FileNotFoundError)."""
        nonexistent = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            read_health_assessment_artifact(nonexistent)

    def test_roundtrip_with_all_fields(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Assessment with various fields should roundtrip correctly."""
        assessment_data = {
            "run_label": "full-test-run",
            "run_id": "full-run-20260505T120000Z",
            "timestamp": "2026-05-05T12:00:00Z",
            "context": "full-context",
            "label": "full-cluster",
            "cluster_id": "full-cluster-id",
            "snapshot_path": "/path/to/snapshot.json",
            "assessment": {
                "observed_signals": [],
                "findings": [{"id": "1", "description": "test finding"}],
                "hypotheses": [],
                "next_evidence_to_collect": [],
            },
            "missing_evidence": ["missing-telemetry-1", "missing-telemetry-2"],
            "health_rating": "degraded",
            "notes": "Test notes",
            "artifact_path": "/path/to/assessment.json",
        }
        assessment_path = tmp_path / "full.json"
        assessment_path.write_text(json.dumps(assessment_data), encoding="utf-8")

        result = read_health_assessment_artifact(assessment_path)

        assert result.run_label == "full-test-run"
        assert result.cluster_id == "full-cluster-id"
        assert result.health_rating == HealthRating.DEGRADED
        assert len(result.missing_evidence) == 2
        assert result.notes == "Test notes"

    def test_empty_assessment_field_becomes_empty_dict(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing or null assessment field should become empty dict."""
        assessment_data = _make_valid_assessment()
        assessment_data["assessment"] = None
        assessment_path = tmp_path / "empty-assessment.json"
        assessment_path.write_text(json.dumps(assessment_data), encoding="utf-8")

        result = read_health_assessment_artifact(assessment_path)

        assert result.assessment == {}

    def test_invalid_health_rating_defaults_to_unknown(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Invalid health_rating value should default to UNKNOWN."""
        assessment_data = _make_valid_assessment(health_rating="invalid-rating")
        assessment_path = tmp_path / "invalid-rating.json"
        assessment_path.write_text(json.dumps(assessment_data), encoding="utf-8")

        result = read_health_assessment_artifact(assessment_path)

        assert result.health_rating == HealthRating.UNKNOWN


class TestTryReadHealthAssessmentArtifact:
    """Tests for the optional reader with graceful fallback."""

    def test_valid_assessment_returns_typed_object(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Valid assessment should return typed object (no logging on success)."""
        assessment_data = _make_valid_assessment(cluster_id="valid-cluster")
        assessment_path = tmp_path / "valid.json"
        assessment_path.write_text(json.dumps(assessment_data), encoding="utf-8")

        result = try_read_health_assessment_artifact(
            assessment_path,
            run_id="run-valid",
            artifact_kind="health-assessment",
        )

        assert result is not None
        assert isinstance(result, HealthAssessmentArtifact)
        assert result.cluster_id == "valid-cluster"

    def test_malformed_json_returns_none_and_logs(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed JSON should return None and log warning with safe metadata."""
        assessment_path = tmp_path / "bad.json"
        assessment_path.write_text("{ not valid }", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_health_assessment_artifact(
                assessment_path,
                run_id="run-789",
                artifact_kind="health-assessment",
            )

        assert result is None
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert "Skipped malformed" in log_record.message
        assert "health-assessment" in log_record.message
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

        result = try_read_health_assessment_artifact(
            nonexistent,
            run_id="run-missing",
            artifact_kind="health-assessment",
        )

        assert result is None

    def test_log_failures_false_returns_none_without_logging(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When log_failures=False, should return None without logging."""
        assessment_path = tmp_path / "bad.json"
        assessment_path.write_text("{ not valid }", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_health_assessment_artifact(
                assessment_path,
                run_id="run-silent",
                artifact_kind="health-assessment",
                log_failures=False,  # Silent mode
            )

        assert result is None
        # No warning should be logged
        assert len(caplog.records) == 0

    def test_log_failures_false_with_valid_assessment(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Valid assessment should return object even with log_failures=False."""
        assessment_data = _make_valid_assessment(cluster_id="valid-silent")
        assessment_path = tmp_path / "valid.json"
        assessment_path.write_text(json.dumps(assessment_data), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_health_assessment_artifact(
                assessment_path,
                run_id="run-valid",
                artifact_kind="health-assessment",
                log_failures=False,
            )

        assert result is not None
        assert result.cluster_id == "valid-silent"
        # No warning for valid assessment
        assert len(caplog.records) == 0

    def test_array_json_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Array JSON should return None."""
        assessment_path = tmp_path / "array.json"
        assessment_path.write_text("[1, 2, 3]", encoding="utf-8")

        result = try_read_health_assessment_artifact(
            assessment_path,
            artifact_kind="health-assessment",
        )

        assert result is None

    def test_log_failures_true_logs_warning_with_safe_message(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When log_failures=True, should log warning with safe metadata."""
        assessment_path = tmp_path / "bad.json"
        assessment_path.write_text("invalid json", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_health_assessment_artifact(
                assessment_path,
                run_id="run-safe",
                artifact_kind="health-assessment",
                log_failures=True,
            )

        assert result is None
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        # Check safe metadata is logged
        assert "health-assessment" in log_record.message
        assert "bad.json" in log_record.message
        # Check error type is logged
        assert log_record.__dict__.get("error") == "JSONDecodeError"
        # Check run_id is logged
        assert log_record.__dict__.get("run_id") == "run-safe"


class TestHealthAssessmentArtifactReadError:
    """Tests for the custom exception class."""

    def test_exception_carrying_safe_path(self) -> None:
        """HealthAssessmentArtifactReadError should use basename only in message."""
        path = Path("/some/long/path/to/assessment.json")
        exc = HealthAssessmentArtifactReadError(
            "Failed to read assessment",
            path=path,
        )

        assert "assessment.json" in str(exc)
        assert "/some/long/path" not in str(exc)

    def test_exception_without_path(self) -> None:
        """HealthAssessmentArtifactReadError should handle None path."""
        exc = HealthAssessmentArtifactReadError("Failed to read assessment")

        assert "Failed to read assessment" in str(exc)
        assert "path=None" in str(exc)

    def test_exception_with_cause(self) -> None:
        """HealthAssessmentArtifactReadError should chain cause properly."""
        path = Path("/path/to/assessment.json")
        cause = ValueError("Invalid value")
        exc = HealthAssessmentArtifactReadError(
            "Failed to read assessment",
            path=path,
            cause=cause,
        )

        assert exc.path == path
        assert exc.cause == cause
        assert "assessment.json" in str(exc)

    def test_roundtrip_preserves_all_fields(self, tmp_path: Path) -> None:
        """Roundtrip should preserve all HealthAssessmentArtifact fields."""
        assessment_data = {
            "run_label": "roundtrip-test",
            "run_id": "roundtrip-20260505T120000Z",
            "timestamp": "2026-05-05T12:00:00Z",
            "context": "roundtrip-context",
            "label": "roundtrip-cluster",
            "cluster_id": "roundtrip-cluster-id",
            "snapshot_path": "/snapshots/roundtrip.json",
            "assessment": {
                "observed_signals": [
                    {"id": "sig1", "description": "signal 1", "severity": "medium"}
                ],
                "findings": [
                    {"id": "find1", "description": "finding 1", "layer": "workload"}
                ],
                "hypotheses": [
                    {
                        "id": "hyp1",
                        "description": "hypothesis 1",
                        "confidence": "medium",
                    }
                ],
                "next_evidence_to_collect": [
                    {"description": "check 1", "owner": "platform"}
                ],
            },
            "missing_evidence": ["evidence-1", "evidence-2"],
            "health_rating": "healthy",
            "notes": "Roundtrip test notes",
            "artifact_path": "/assessments/roundtrip.json",
        }
        assessment_path = tmp_path / "roundtrip.json"
        assessment_path.write_text(json.dumps(assessment_data), encoding="utf-8")

        # Read with strict reader
        result = read_health_assessment_artifact(assessment_path)

        # Convert to dict and verify
        result_dict = result.to_dict()
        assert result_dict["run_label"] == "roundtrip-test"
        assert result_dict["cluster_id"] == "roundtrip-cluster-id"
        assert result_dict["health_rating"] == "healthy"
        assert result_dict["notes"] == "Roundtrip test notes"
        assert len(result_dict["missing_evidence"]) == 2

        # Verify assessment dict is preserved
        assert "observed_signals" in result_dict["assessment"]
