"""Tests for DrilldownArtifact typed reader.

These tests verify:
- Valid drilldown artifact loads typed object
- Malformed JSON raises/returns None
- Missing/invalid fields raises/returns None
- Non-object JSON fails/skips
- log_failures=False suppresses warnings
- log_failures=True logs safe metadata
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from k8s_diag_agent.health.artifact_readers import (
    DrilldownArtifactReadError,
    read_drilldown_artifact,
    try_read_drilldown_artifact,
)
from k8s_diag_agent.health.drilldown import DrilldownArtifact
from k8s_diag_agent.health.review import collect_drilldown_candidates


def _make_valid_drilldown_data(run_id: str = "run-123", label: str = "test-cluster") -> dict:
    """Create a valid DrilldownArtifact dict for testing."""
    return {
        "run_label": "test-run",
        "run_id": run_id,
        "timestamp": "2026-01-02T00:00:00Z",
        "snapshot_timestamp": "2026-01-01T00:00:00Z",
        "context": "test-context",
        "label": label,
        "cluster_id": "cluster-123",
        "trigger_reasons": ["crashloopbackoff", "imagepullbackoff"],
        "missing_evidence": ["pod_logs"],
        "evidence_summary": {"warnings": 5, "pods": 3},
        "affected_namespaces": ["default"],
        "affected_workloads": [],
        "warning_events": [
            {
                "namespace": "default",
                "reason": "BackOff",
                "message": "Container restarting",
                "count": 10,
                "last_seen": "2026-01-01T12:00:00Z",
            }
        ],
        "non_running_pods": [
            {
                "namespace": "default",
                "name": "test-pod",
                "phase": "CrashLoopBackOff",
                "reason": "CrashLoopBackOff",
            }
        ],
        "pod_descriptions": {},
        "rollout_status": [],
        "collection_timestamps": {},
        "pattern_details": {},
        "image_pull_secret_insight": None,
    }


class TestReadDrilldownArtifact:
    """Tests for strict reader read_drilldown_artifact()."""

    def test_valid_drilldown_loads_typed_object(self, tmp_path: Path) -> None:
        """Valid drilldown JSON should parse into DrilldownArtifact."""
        artifact_data = _make_valid_drilldown_data()
        artifact_path = tmp_path / "drilldown.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

        result = read_drilldown_artifact(artifact_path)

        assert isinstance(result, DrilldownArtifact)
        assert result.run_id == "run-123"
        assert result.label == "test-cluster"
        assert result.cluster_id == "cluster-123"
        assert "crashloopbackoff" in result.trigger_reasons
        assert len(result.warning_events) == 1
        assert len(result.non_running_pods) == 1

    def test_malformed_json_raises_json_decode_error(self, tmp_path: Path) -> None:
        """Malformed JSON should raise json.JSONDecodeError."""
        artifact_path = tmp_path / "malformed.json"
        artifact_path.write_text("{ not valid json", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            read_drilldown_artifact(artifact_path)

    def test_missing_file_raises_os_error(self, tmp_path: Path) -> None:
        """Missing file should raise OSError."""
        missing_path = tmp_path / "nonexistent.json"

        with pytest.raises(OSError):
            read_drilldown_artifact(missing_path)

    def test_non_object_json_raises_value_error(self, tmp_path: Path) -> None:
        """JSON array instead of object should raise ValueError."""
        artifact_path = tmp_path / "array.json"
        artifact_path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ValueError) as ctx:
            read_drilldown_artifact(artifact_path)
        assert "mapping" in str(ctx.value).lower()

    def test_missing_required_timestamp_field_raises_value_error(self, tmp_path: Path) -> None:
        """Missing required timestamp field should raise ValueError from from_dict."""
        artifact_data = _make_valid_drilldown_data()
        del artifact_data["timestamp"]  # Remove required field
        artifact_path = tmp_path / "no-timestamp.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

        with pytest.raises(ValueError) as ctx:
            read_drilldown_artifact(artifact_path)
        assert "timestamp" in str(ctx.value).lower()

    def test_invalid_timestamp_raises_value_error(self, tmp_path: Path) -> None:
        """Invalid timestamp format should raise ValueError."""
        artifact_data = _make_valid_drilldown_data()
        artifact_data["timestamp"] = "not-a-timestamp"
        artifact_path = tmp_path / "bad-timestamp.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

        with pytest.raises(ValueError) as ctx:
            read_drilldown_artifact(artifact_path)
        assert "timestamp" in str(ctx.value).lower()


class TestTryReadDrilldownArtifact:
    """Tests for optional reader try_read_drilldown_artifact()."""

    def test_valid_drilldown_returns_typed_object(self, tmp_path: Path) -> None:
        """Valid drilldown should return DrilldownArtifact."""
        artifact_data = _make_valid_drilldown_data(run_id="run-456", label="prod-cluster")
        artifact_path = tmp_path / "valid-drilldown.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

        result = try_read_drilldown_artifact(artifact_path)

        assert result is not None
        assert isinstance(result, DrilldownArtifact)
        assert result.run_id == "run-456"
        assert result.label == "prod-cluster"

    def test_malformed_json_returns_none_with_logging(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Malformed JSON should return None and log warning."""
        artifact_path = tmp_path / "malformed.json"
        artifact_path.write_text("{ broken", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_drilldown_artifact(artifact_path, run_id="run-123")

        assert result is None
        # Check that logging captured the warning
        assert any(
            "Skipped malformed" in record.message or "malformed" in record.message.lower()
            for record in caplog.records
        )

    def test_malformed_json_returns_none_silently_without_logging(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """With log_failures=False, should return None without logging."""
        artifact_path = tmp_path / "silent-malformed.json"
        artifact_path.write_text("{ broken", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_drilldown_artifact(
                artifact_path, run_id="run-123", log_failures=False
            )

        assert result is None
        # No warnings should be logged
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
        ]
        assert not any("malformed" in msg.lower() for msg in warning_messages)

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        """Missing file should return None."""
        missing_path = tmp_path / "nonexistent.json"

        result = try_read_drilldown_artifact(missing_path)

        assert result is None

    def test_missing_file_silent_with_log_failures_false(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """With log_failures=False, missing file should return None silently."""
        missing_path = tmp_path / "nonexistent.json"

        with caplog.at_level(logging.WARNING):
            result = try_read_drilldown_artifact(
                missing_path, run_id="run-123", log_failures=False
            )

        assert result is None
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
        ]
        assert not any("malformed" in msg.lower() for msg in warning_messages)

    def test_non_object_json_returns_none(self, tmp_path: Path) -> None:
        """Non-object JSON (array) should return None."""
        artifact_path = tmp_path / "array.json"
        artifact_path.write_text("[1, 2, 3]", encoding="utf-8")

        result = try_read_drilldown_artifact(artifact_path)

        assert result is None

    def test_missing_required_field_returns_none(self, tmp_path: Path) -> None:
        """Missing required field (timestamp) should return None."""
        artifact_data = _make_valid_drilldown_data()
        del artifact_data["timestamp"]
        artifact_path = tmp_path / "no-timestamp.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

        result = try_read_drilldown_artifact(artifact_path)

        assert result is None

    def test_log_failures_true_logs_warning_with_safe_message(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """With log_failures=True, should log warning containing safe metadata."""
        artifact_path = tmp_path / "bad-drilldown.json"
        artifact_path.write_text("{ broken", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_drilldown_artifact(
                artifact_path,
                run_id="run-123",
                artifact_kind="drilldown",
                log_failures=True,
            )

        assert result is None
        # Check that warning was logged
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) > 0
        # Check log message contains safe metadata (filename and kind)
        record = warning_records[0]
        assert "drilldown" in record.message or "bad-drilldown.json" in record.message
        assert "Skipped malformed" in record.message
        # Verify no raw content in the log message
        assert "{" not in record.message or "broken" not in record.message

    def test_roundtrip_serialization_preserves_fields(self, tmp_path: Path) -> None:
        """Roundtrip: to_dict -> write -> read should preserve all fields."""
        # Create a valid drilldown
        artifact_data = _make_valid_drilldown_data(run_id="roundtrip-run", label="roundtrip-cluster")
        artifact_path = tmp_path / "roundtrip.json"
        artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")

        # Read back
        result = try_read_drilldown_artifact(artifact_path)

        assert result is not None
        assert result.run_id == "roundtrip-run"
        assert result.label == "roundtrip-cluster"
        assert result.cluster_id == "cluster-123"
        assert "crashloopbackoff" in result.trigger_reasons
        assert len(result.warning_events) == 1
        assert len(result.non_running_pods) == 1

    def test_log_failures_false_does_not_log_raw_content(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """log_failures=False should never log raw drilldown content."""
        # Create a valid drilldown with sensitive-looking content
        artifact_data = _make_valid_drilldown_data()
        artifact_data["pod_descriptions"] = {
            "default/test-pod": "Sensitive logs showing secret_value=ABC123"
        }
        artifact_path = tmp_path / "sensitive-drilldown.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

        # Read with valid data (should succeed, no logging)
        with caplog.at_level(logging.WARNING):
            result = try_read_drilldown_artifact(
                artifact_path, run_id="run-123", log_failures=False
            )

        assert result is not None
        # Verify no sensitive values leaked into logs
        all_log_text = " ".join(record.message for record in caplog.records)
        all_extra = " ".join(
            str(getattr(record, "extra", {})) for record in caplog.records
        )
        assert "ABC123" not in all_log_text
        assert "ABC123" not in all_extra
        assert "secret_value" not in all_log_text
        assert "secret_value" not in all_extra


class TestDrilldownArtifactReadError:
    """Tests for DrilldownArtifactReadError exception."""

    def test_exception_carrying_safe_path(self) -> None:
        """Exception should include safe path (basename) not full path."""
        path = Path("/some/long/path/to/drilldown.json")
        exc = DrilldownArtifactReadError(
            message="Test error",
            path=path,
        )

        assert "drilldown.json" in str(exc)
        assert "/some/long/path" not in str(exc)

    def test_exception_with_cause(self) -> None:
        """Exception should chain underlying cause."""
        cause = ValueError("Original cause")
        exc = DrilldownArtifactReadError(
            message="Read failed",
            path=Path("/test.json"),
            cause=cause,
        )

        assert exc.cause is cause
        assert exc.path == Path("/test.json")


class TestDrilldownArtifactReaderCallsiteBehavior:
    """Tests for DrilldownArtifact reader behavior at call sites."""

    def test_multiple_artifacts_scanned_preserves_valid_skips_invalid(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Scanning multiple artifacts should preserve valid, skip invalid."""
        # Create mix of valid and invalid artifacts
        valid_data = _make_valid_drilldown_data(run_id="scan-test", label="valid-1")
        (tmp_path / "valid-1.json").write_text(json.dumps(valid_data), encoding="utf-8")

        # Invalid JSON
        (tmp_path / "invalid-1.json").write_text("{ broken", encoding="utf-8")

        valid_data2 = _make_valid_drilldown_data(run_id="scan-test", label="valid-2")
        (tmp_path / "valid-2.json").write_text(json.dumps(valid_data2), encoding="utf-8")

        # Missing required field - timestamp is truly required (no fallback)
        invalid_data = _make_valid_drilldown_data()
        del invalid_data["timestamp"]
        (tmp_path / "invalid-2.json").write_text(json.dumps(invalid_data), encoding="utf-8")

        # Scan with log_failures=False (silent scan like collect_drilldown_candidates)
        artifacts = []
        for path in sorted(tmp_path.glob("*.json")):
            artifact = try_read_drilldown_artifact(path, log_failures=False)
            if artifact is not None:
                artifacts.append(artifact)

        # Should have exactly 2 valid artifacts
        assert len(artifacts) == 2
        assert artifacts[0].label == "valid-1"
        assert artifacts[1].label == "valid-2"

        # No warnings should be logged
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
        ]
        assert not any("malformed" in msg.lower() for msg in warning_messages)

    def test_legacy_dict_compatibility_not_needed_for_current_artifacts(self, tmp_path: Path) -> None:
        """Current DrilldownArtifact schema should parse all valid artifacts.

        Note: Unlike HealthProposal, DrilldownArtifact does not have the same
        legacy fallback requirement because its schema is stable and all
        existing artifacts should pass from_dict validation.
        """
        # Create artifact with all expected fields
        artifact_data = _make_valid_drilldown_data()
        artifact_path = tmp_path / "current-schema.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

        result = try_read_drilldown_artifact(artifact_path)

        assert result is not None
        assert result.run_id == "run-123"


class TestCollectDrilldownCandidatesCallsite:
    """Direct tests for collect_drilldown_candidates() call site migration."""

    def test_collect_drilldown_candidates_returns_only_valid_artifacts(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """collect_drilldown_candidates should return exactly 2 valid artifacts, skip malformed."""
        # Create 2 valid artifacts
        valid_data1 = _make_valid_drilldown_data(run_id="call-site-test", label="cluster-prod")
        (tmp_path / "call-site-test-cluster-prod.json").write_text(json.dumps(valid_data1), encoding="utf-8")

        valid_data2 = _make_valid_drilldown_data(run_id="call-site-test", label="cluster-staging")
        (tmp_path / "call-site-test-cluster-staging.json").write_text(json.dumps(valid_data2), encoding="utf-8")

        # Create 1 malformed JSON file
        (tmp_path / "malformed.json").write_text("{ broken", encoding="utf-8")

        # Create 1 dict missing required field (timestamp)
        invalid_data = _make_valid_drilldown_data()
        del invalid_data["timestamp"]
        (tmp_path / "call-site-test-no-timestamp.json").write_text(json.dumps(invalid_data), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            candidates = collect_drilldown_candidates(tmp_path)

        # Should have exactly 2 valid candidates
        assert len(candidates) == 2
        assert candidates[0].artifact.label == "cluster-prod"
        assert candidates[1].artifact.label == "cluster-staging"
        assert candidates[0].artifact.run_id == "call-site-test"
        assert candidates[1].artifact.run_id == "call-site-test"

        # No warnings should be logged because collect_drilldown_candidates uses log_failures=False
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
        ]
        assert not any("malformed" in msg.lower() for msg in warning_messages)

    def test_collect_drilldown_candidates_empty_dir_returns_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """collect_drilldown_candidates on empty directory returns empty tuple."""
        with caplog.at_level(logging.WARNING):
            candidates = collect_drilldown_candidates(tmp_path)

        assert len(candidates) == 0
        # No warnings for empty directory
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
        ]
        assert not any("malformed" in msg.lower() for msg in warning_messages)

    def test_collect_drilldown_candidates_nonexistent_dir_returns_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """collect_drilldown_candidates on nonexistent directory returns empty tuple."""
        nonexistent = tmp_path / "nonexistent"
        with caplog.at_level(logging.WARNING):
            candidates = collect_drilldown_candidates(nonexistent)

        assert len(candidates) == 0
        # No warnings for nonexistent directory
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
        ]
        assert not any("malformed" in msg.lower() for msg in warning_messages)