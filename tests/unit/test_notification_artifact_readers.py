"""Tests for health artifact readers (NotificationArtifact typed reader).

These tests verify:
- Valid notification loads typed object
- Malformed JSON raises/returns None
- Missing/invalid fields raises/returns None
- Non-object JSON fails/skips
- log_failures=False suppresses warnings
- log_failures=True logs safe metadata
- Direct call site tests for migrated ui/notifications.py functions
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from k8s_diag_agent.health.artifact_readers import (
    NotificationArtifactReadError,
    read_notification_artifact,
    try_read_notification_artifact,
)
from k8s_diag_agent.health.notifications import NotificationArtifact


class TestReadNotificationArtifact:
    """Tests for strict reader read_notification_artifact()."""

    def test_valid_notification_loads_typed_object(self, tmp_path: Path) -> None:
        """Valid notification JSON should parse into NotificationArtifact."""
        notification_data = {
            "kind": "degraded-health",
            "summary": "prod degraded (degraded)",
            "details": {"warnings": 5, "cluster": "prod", "context": "ns-default"},
            "run_id": "run-123",
            "cluster_label": "prod",
            "context": "ns-default",
            "timestamp": "20260407T120000",
        }
        artifact_path = tmp_path / "notification.json"
        artifact_path.write_text(json.dumps(notification_data), encoding="utf-8")

        result = read_notification_artifact(artifact_path)

        assert isinstance(result, NotificationArtifact)
        assert result.kind == "degraded-health"
        assert result.summary == "prod degraded (degraded)"
        assert result.run_id == "run-123"
        assert result.cluster_label == "prod"
        assert result.context == "ns-default"

    def test_malformed_json_raises_json_decode_error(self, tmp_path: Path) -> None:
        """Malformed JSON should raise json.JSONDecodeError."""
        artifact_path = tmp_path / "malformed.json"
        artifact_path.write_text("{ not valid json", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            read_notification_artifact(artifact_path)

    def test_missing_file_raises_os_error(self, tmp_path: Path) -> None:
        """Missing file should raise OSError."""
        missing_path = tmp_path / "nonexistent.json"

        with pytest.raises(OSError):
            read_notification_artifact(missing_path)

    def test_non_object_json_raises_value_error(self, tmp_path: Path) -> None:
        """JSON array instead of object should raise ValueError."""
        artifact_path = tmp_path / "array.json"
        artifact_path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ValueError) as ctx:
            read_notification_artifact(artifact_path)
        assert "mapping" in str(ctx.value).lower()

    def test_missing_kind_field_becomes_empty_string(self, tmp_path: Path) -> None:
        """Missing kind field becomes empty string (permissive from_dict)."""
        notification_data = {
            # Missing kind field - from_dict uses str(raw.get("kind") or "")
            "summary": "Test summary",
            "details": {},
        }
        artifact_path = tmp_path / "no-kind.json"
        artifact_path.write_text(json.dumps(notification_data), encoding="utf-8")

        result = read_notification_artifact(artifact_path)

        # from_dict is permissive: missing fields become ""
        assert result.kind == ""
        assert result.summary == "Test summary"

    def test_missing_summary_field_becomes_empty_string(self, tmp_path: Path) -> None:
        """Missing summary field becomes empty string (permissive from_dict)."""
        notification_data = {
            "kind": "test-kind",
            # Missing summary - from_dict uses str(raw.get("summary") or "")
            "details": {},
        }
        artifact_path = tmp_path / "no-summary.json"
        artifact_path.write_text(json.dumps(notification_data), encoding="utf-8")

        result = read_notification_artifact(artifact_path)

        # from_dict is permissive: missing fields become ""
        assert result.kind == "test-kind"
        assert result.summary == ""

    def test_roundtrip_with_all_fields(self, tmp_path: Path) -> None:
        """Notification with all fields should roundtrip correctly."""
        notification = NotificationArtifact(
            kind="external-analysis",
            summary="External analysis complete",
            details={"tool": "test", "status": "success"},
            run_id="run-full",
            cluster_label="staging",
            context="ns-default",
            timestamp="20260407T120000",
            artifact_id="0192a1b8-test-uuid",
        )
        artifact_path = tmp_path / "full.json"
        artifact_path.write_text(json.dumps(notification.to_dict()), encoding="utf-8")

        result = read_notification_artifact(artifact_path)

        assert result.kind == "external-analysis"
        assert result.summary == "External analysis complete"
        assert result.run_id == "run-full"
        assert result.cluster_label == "staging"
        assert result.context == "ns-default"
        assert result.artifact_id == "0192a1b8-test-uuid"
        assert result.details.get("tool") == "test"


class TestTryReadNotificationArtifact:
    """Tests for optional reader try_read_notification_artifact()."""

    def test_valid_notification_returns_typed_object(self, tmp_path: Path) -> None:
        """Valid notification should return NotificationArtifact."""
        notification_data = {
            "kind": "proposal-created",
            "summary": "Proposal created for test",
            "details": {"target": "test-policy"},
            "run_id": "run-456",
        }
        artifact_path = tmp_path / "valid-notification.json"
        artifact_path.write_text(json.dumps(notification_data), encoding="utf-8")

        result = try_read_notification_artifact(artifact_path)

        assert result is not None
        assert isinstance(result, NotificationArtifact)
        assert result.kind == "proposal-created"
        assert result.run_id == "run-456"

    def test_malformed_json_returns_none_with_logging(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed JSON should return None and log warning."""
        artifact_path = tmp_path / "malformed.json"
        artifact_path.write_text("{ broken", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_notification_artifact(artifact_path, run_id="run-123")

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
            result = try_read_notification_artifact(
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

        result = try_read_notification_artifact(missing_path)

        assert result is None

    def test_missing_file_silent_with_log_failures_false(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """With log_failures=False, missing file should return None silently."""
        missing_path = tmp_path / "nonexistent.json"

        with caplog.at_level(logging.WARNING):
            result = try_read_notification_artifact(
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

        result = try_read_notification_artifact(artifact_path)

        assert result is None

    def test_missing_required_field_returns_object_permissively(self, tmp_path: Path) -> None:
        """Missing optional fields return object (permissive from_dict)."""
        # Missing kind field - from_dict is permissive
        notification_data = {
            "summary": "Test summary",
            "details": {},
        }
        artifact_path = tmp_path / "no-kind.json"
        artifact_path.write_text(json.dumps(notification_data), encoding="utf-8")

        result = try_read_notification_artifact(artifact_path)

        # from_dict is permissive - missing fields become ""
        assert result is not None
        assert result.kind == ""

    def test_log_failures_true_logs_warning_with_safe_message(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """With log_failures=True, should log warning containing safe metadata."""
        artifact_path = tmp_path / "bad-notification.json"
        artifact_path.write_text("{ broken", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_notification_artifact(
                artifact_path,
                run_id="run-123",
                artifact_kind="notification",
                log_failures=True,
            )

        assert result is None
        # Check that warning was logged
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) > 0
        # Check log message contains safe metadata (filename and kind)
        record = warning_records[0]
        assert "notification" in record.message or "bad-notification.json" in record.message
        assert "Skipped malformed" in record.message
        # Verify no raw content in the log message
        assert "{" not in record.message or "broken" not in record.message

    def test_roundtrip_serialization_preserves_fields(self, tmp_path: Path) -> None:
        """Roundtrip: to_dict -> write -> read should preserve all fields."""
        notification = NotificationArtifact(
            kind="suspicious-comparison",
            summary="Comparison test",
            details={"reasons": ["reason1"], "differences": "diff1"},
            run_id="run-789",
            cluster_label="prod",
            context="cluster-prod",
            timestamp="20260407T120000",
            artifact_id="0192a1b8-test-uuid-2",
        )

        # Write to disk
        artifact_path = tmp_path / "roundtrip.json"
        artifact_path.write_text(json.dumps(notification.to_dict(), indent=2), encoding="utf-8")

        # Read back
        result = try_read_notification_artifact(artifact_path)

        assert result is not None
        assert result.kind == "suspicious-comparison"
        assert result.summary == "Comparison test"
        assert result.run_id == "run-789"
        assert result.cluster_label == "prod"
        assert result.context == "cluster-prod"
        assert result.artifact_id == "0192a1b8-test-uuid-2"
        assert result.details.get("reasons") == ["reason1"]

    def test_log_failures_false_does_not_log_raw_content(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """log_failures=False should never log raw notification content."""
        # Create a notification with sensitive-looking content
        notification_data = {
            "kind": "degraded-health",
            "summary": "Cluster compromised - secrets exposed",
            "details": {
                "warnings": 10,
                "cluster": "prod",
                "context": "ns-default",
                "admin_token": "super-secret-value",
            },
            "run_id": "run-sensitive",
            "cluster_label": "prod",
        }
        artifact_path = tmp_path / "sensitive-notification.json"
        artifact_path.write_text(json.dumps(notification_data), encoding="utf-8")

        # Read with valid data (should succeed, no logging)
        with caplog.at_level(logging.WARNING):
            result = try_read_notification_artifact(
                artifact_path, run_id="run-sensitive", log_failures=False
            )

        assert result is not None
        # Verify no secret values leaked into logs
        all_log_text = " ".join(record.message for record in caplog.records)
        all_extra = " ".join(
            str(getattr(record, "extra", {})) for record in caplog.records
        )
        assert "super-secret-value" not in all_log_text
        assert "super-secret-value" not in all_extra
        assert "admin_token" not in all_log_text
        assert "admin_token" not in all_extra


class TestNotificationArtifactReadError:
    """Tests for NotificationArtifactReadError exception."""

    def test_exception_carrying_safe_path(self) -> None:
        """Exception should include safe path (basename) not full path."""
        from pathlib import Path as PathType

        path = PathType("/some/long/path/to/notification.json")
        exc = NotificationArtifactReadError(
            message="Test error",
            path=path,
        )

        assert "notification.json" in str(exc)
        assert "/some/long/path" not in str(exc)

    def test_exception_with_cause(self) -> None:
        """Exception should chain underlying cause."""
        cause = ValueError("Original cause")
        exc = NotificationArtifactReadError(
            message="Read failed",
            path=Path("/test.json"),
            cause=cause,
        )

        assert exc.cause is cause
        assert exc.path == Path("/test.json")


class TestRegressionCallSites:
    """Regression tests proving previous fallback behavior is preserved."""

    def test_notification_scan_preserves_valid_skips_invalid(self, tmp_path: Path) -> None:
        """Test that notification scan pattern still works: skip malformed, keep valid."""
        notifications_dir = tmp_path / "notifications"
        notifications_dir.mkdir()

        # Write a valid notification
        valid_notification = NotificationArtifact(
            kind="degraded-health",
            summary="Valid notification",
            details={"cluster": "prod"},
            run_id="run-scan-test",
            cluster_label="prod",
        )
        valid_path = notifications_dir / "20260407T120000-degraded-health.json"
        valid_path.write_text(json.dumps(valid_notification.to_dict()), encoding="utf-8")

        # Write a malformed notification
        bad_path = notifications_dir / "20260407T120001-malformed.json"
        bad_path.write_text("{ malformed", encoding="utf-8")

        # Read both - should skip bad and get valid
        from k8s_diag_agent.health.artifact_readers import (
            try_read_notification_artifact,
        )

        valid_count = 0
        for path in notifications_dir.glob("*.json"):
            artifact = try_read_notification_artifact(
                path,
                run_id="run-scan-test",
                artifact_kind="notification",
                log_failures=False,  # Silent scan
            )
            if artifact is None:
                continue
            valid_count += 1

        assert valid_count == 1
        # Malformed notification was skipped

    def test_notification_with_artifact_id_loads_correctly(self, tmp_path: Path) -> None:
        """Test that notification with artifact_id loads correctly."""
        notification = NotificationArtifact(
            kind="external-analysis",
            summary="External analysis complete",
            details={"tool": "test"},
            run_id="run-id-test",
            cluster_label="prod",
            timestamp="20260407T120000",
            artifact_id="0192a1b8-unique-uuid",
        )
        artifact_path = tmp_path / "with-artifact-id.json"
        artifact_path.write_text(json.dumps(notification.to_dict()), encoding="utf-8")

        result = try_read_notification_artifact(artifact_path)

        assert result is not None
        assert result.artifact_id == "0192a1b8-unique-uuid"
        assert result.kind == "external-analysis"

    def test_legacy_notification_without_artifact_id_loads_correctly(self, tmp_path: Path) -> None:
        """Test that legacy notification without artifact_id loads correctly."""
        # Legacy format: no artifact_id field
        legacy_data = {
            "kind": "degraded-health",
            "summary": "Legacy notification",
            "details": {"cluster": "prod"},
            "run_id": "run-legacy",
            "cluster_label": "prod",
            "timestamp": "20260407T120000",
        }
        artifact_path = tmp_path / "legacy-notification.json"
        artifact_path.write_text(json.dumps(legacy_data), encoding="utf-8")

        result = try_read_notification_artifact(artifact_path)

        assert result is not None
        assert result.artifact_id is None
        assert result.kind == "degraded-health"
        assert result.run_id == "run-legacy"


class TestDirectCallSite:
    """Direct tests for migrated call sites in ui/notifications.py."""

    def test_load_notification_records_valid_and_legacy(self, tmp_path: Path) -> None:
        """Test _load_notification_records returns valid + legacy, skips malformed."""
        from k8s_diag_agent.ui.notifications import _load_notification_records

        # Setup notifications dir
        notifications_dir = tmp_path / "notifications"
        notifications_dir.mkdir()

        # Write valid notification
        valid_notification = NotificationArtifact(
            kind="degraded-health",
            summary="Valid notification",
            details={"cluster": "prod"},
            run_id="run-valid",
            cluster_label="prod",
            timestamp="20260407T120000",
        )
        valid_path = notifications_dir / "20260407T120000-degraded-health.json"
        valid_path.write_text(json.dumps(valid_notification.to_dict()), encoding="utf-8")

        # Write malformed notification
        bad_path = notifications_dir / "20260407T120001-malformed.json"
        bad_path.write_text("{ malformed", encoding="utf-8")

        # Write legacy notification (no artifact_id)
        legacy_data = {
            "kind": "warning",
            "summary": "Legacy notification",
            "details": {"cluster": "staging"},
            "run_id": "run-legacy",
            "cluster_label": "staging",
            "timestamp": "20260407T120002",
        }
        legacy_path = notifications_dir / "20260407T120002-warning.json"
        legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

        # Call the real migrated function
        records = _load_notification_records(notifications_dir)

        # Should have 2 records (valid + legacy), malformed skipped
        assert len(records) == 2
        kinds = {r[0].kind for r in records}
        assert kinds == {"degraded-health", "warning"}

    def test_load_notification_records_malformed_skipped_silently(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _load_notification_records silently skips malformed (no warnings)."""
        from k8s_diag_agent.ui.notifications import _load_notification_records

        notifications_dir = tmp_path / "notifications"
        notifications_dir.mkdir()

        # Write malformed notification
        bad_path = notifications_dir / "malformed.json"
        bad_path.write_text("{ malformed", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            records = _load_notification_records(notifications_dir)

        # Malformed skipped, no warnings logged
        assert len(records) == 0
        warning_messages = [
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert not any("malformed" in msg.lower() for msg in warning_messages)

    def test_count_matching_records_malformed_skipped_with_kind_filter(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _count_matching_records counts valid, skips malformed silently."""
        from k8s_diag_agent.ui.notifications import _count_matching_records

        notifications_dir = tmp_path / "notifications"
        notifications_dir.mkdir()

        # Write valid notification
        valid_notification = NotificationArtifact(
            kind="info",
            summary="Info notification",
            details={},
            run_id="run-info",
            cluster_label="prod",
            timestamp="20260407T120000",
        )
        valid_path = notifications_dir / "20260407T120000-info.json"
        valid_path.write_text(json.dumps(valid_notification.to_dict()), encoding="utf-8")

        # Write malformed notification
        bad_path = notifications_dir / "malformed.json"
        bad_path.write_text("{ invalid", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            # Pass kind_filter to force full parse (skips malformed)
            count = _count_matching_records(notifications_dir, kind_filter='info')

        # Count should be 1 (valid only), malformed skipped silently by full parse
        assert count == 1
        warning_messages = [
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert not any("malformed" in msg.lower() for msg in warning_messages)

    def test_load_notification_records_with_sensitive_content_not_logged(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that raw notification content is never logged."""
        from k8s_diag_agent.ui.notifications import _load_notification_records

        notifications_dir = tmp_path / "notifications"
        notifications_dir.mkdir()

        # Create notification with sensitive-looking content
        sensitive_data = {
            "kind": "degraded-health",
            "summary": "Cluster compromised - admin token exposed",
            "details": {
                "warnings": 10,
                "cluster": "prod",
                "context": "ns-default",
                "admin_token": "super-secret-value-12345",
                "kubeconfig": "secret-kubeconfig-content",
            },
            "run_id": "run-sensitive",
            "cluster_label": "prod",
            "timestamp": "20260407T120000",
        }
        sensitive_path = notifications_dir / "sensitive.json"
        sensitive_path.write_text(json.dumps(sensitive_data), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            records = _load_notification_records(notifications_dir)

        # Valid record loaded, no sensitive content in logs
        assert len(records) == 1
        all_log_text = " ".join(r.message for r in caplog.records)
        assert "super-secret-value-12345" not in all_log_text
        assert "secret-kubeconfig-content" not in all_log_text
        assert "admin_token" not in all_log_text
