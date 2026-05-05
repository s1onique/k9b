"""Tests for health artifact readers (HealthProposal typed reader).

These tests verify:
- Valid proposal loads typed object
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

from k8s_diag_agent.health.adaptation import HealthProposal
from k8s_diag_agent.health.artifact_readers import (
    HealthProposalArtifactReadError,
    read_health_proposal_artifact,
    try_read_health_proposal_artifact,
)
from k8s_diag_agent.models import ConfidenceLevel


class TestReadHealthProposalArtifact:
    """Tests for strict reader read_health_proposal_artifact()."""

    def test_valid_proposal_loads_typed_object(self, tmp_path: Path) -> None:
        """Valid proposal JSON should parse into HealthProposal."""
        proposal_data = {
            "proposal_id": "run-123-proposal-1",
            "source_run_id": "run-123",
            "source_artifact_path": "/some/review.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Raise threshold from 10 to 15.",
            "rationale": "Too many warnings.",
            "confidence": "medium",
            "expected_benefit": "Reduced noise.",
            "rollback_note": "Revert to 10.",
            "promotion_payload": {"threshold": 15},
            "lifecycle_history": [],
        }
        artifact_path = tmp_path / "proposal.json"
        artifact_path.write_text(json.dumps(proposal_data), encoding="utf-8")

        result = read_health_proposal_artifact(artifact_path)

        assert isinstance(result, HealthProposal)
        assert result.proposal_id == "run-123-proposal-1"
        assert result.target == "health.trigger_policy.warning_event_threshold"
        assert result.confidence == ConfidenceLevel.MEDIUM

    def test_malformed_json_raises_json_decode_error(self, tmp_path: Path) -> None:
        """Malformed JSON should raise json.JSONDecodeError."""
        artifact_path = tmp_path / "malformed.json"
        artifact_path.write_text("{ not valid json", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            read_health_proposal_artifact(artifact_path)

    def test_missing_file_raises_os_error(self, tmp_path: Path) -> None:
        """Missing file should raise OSError."""
        missing_path = tmp_path / "nonexistent.json"

        with pytest.raises(OSError):
            read_health_proposal_artifact(missing_path)

    def test_non_object_json_raises_value_error(self, tmp_path: Path) -> None:
        """JSON array instead of object should raise ValueError."""
        artifact_path = tmp_path / "array.json"
        artifact_path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ValueError) as ctx:
            read_health_proposal_artifact(artifact_path)
        assert "mapping" in str(ctx.value).lower()

    def test_missing_required_confidence_field_raises_value_error(self, tmp_path: Path) -> None:
        """Missing confidence field should raise ValueError from from_dict."""
        proposal_data = {
            "proposal_id": "p1",
            "source_run_id": "run-123",
            "source_artifact_path": "/review.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Change it.",
            "rationale": "Because.",
            # Missing confidence
            "expected_benefit": "Benefit.",
            "rollback_note": "Rollback.",
        }
        artifact_path = tmp_path / "no-confidence.json"
        artifact_path.write_text(json.dumps(proposal_data), encoding="utf-8")

        with pytest.raises(ValueError) as ctx:
            read_health_proposal_artifact(artifact_path)
        assert "confidence" in str(ctx.value).lower()

    def test_invalid_confidence_value_raises_value_error(self, tmp_path: Path) -> None:
        """Invalid confidence value should raise ValueError."""
        proposal_data = {
            "proposal_id": "p1",
            "source_run_id": "run-123",
            "source_artifact_path": "/review.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Change it.",
            "rationale": "Because.",
            "confidence": "super-high",  # Invalid
            "expected_benefit": "Benefit.",
            "rollback_note": "Rollback.",
        }
        artifact_path = tmp_path / "bad-confidence.json"
        artifact_path.write_text(json.dumps(proposal_data), encoding="utf-8")

        with pytest.raises(ValueError) as ctx:
            read_health_proposal_artifact(artifact_path)
        assert "confidence" in str(ctx.value).lower()


class TestTryReadHealthProposalArtifact:
    """Tests for optional reader try_read_health_proposal_artifact()."""

    def test_valid_proposal_returns_typed_object(self, tmp_path: Path) -> None:
        """Valid proposal should return HealthProposal."""
        proposal_data = {
            "proposal_id": "run-123-proposal-2",
            "source_run_id": "run-123",
            "source_artifact_path": "/review.json",
            "target": "health.noise_filters.ignored_reasons",
            "proposed_change": "Add reason X to ignore list.",
            "rationale": "Noisy.",
            "confidence": "low",
            "expected_benefit": "Less noise.",
            "rollback_note": "Remove reason.",
            "promotion_payload": {"reason": "X"},
            "lifecycle_history": [
                {"status": "pending", "timestamp": "2024-01-01T00:00:00Z"}
            ],
        }
        artifact_path = tmp_path / "valid-proposal.json"
        artifact_path.write_text(json.dumps(proposal_data), encoding="utf-8")

        result = try_read_health_proposal_artifact(artifact_path)

        assert result is not None
        assert isinstance(result, HealthProposal)
        assert result.proposal_id == "run-123-proposal-2"
        assert result.confidence == ConfidenceLevel.LOW

    def test_malformed_json_returns_none_with_logging(self, tmp_path: Path, caplog: object) -> None:
        """Malformed JSON should return None and log warning."""
        import logging

        artifact_path = tmp_path / "malformed.json"
        artifact_path.write_text("{ broken", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_health_proposal_artifact(artifact_path, run_id="run-123")

        assert result is None
        # Check that logging captured the warning
        assert any(
            "Skipped malformed" in record.message or "malformed" in record.message.lower()
            for record in caplog.records
        )

    def test_malformed_json_returns_none_silently_without_logging(
        self, tmp_path: Path, caplog: object
    ) -> None:
        """With log_failures=False, should return None without logging."""
        artifact_path = tmp_path / "silent-malformed.json"
        artifact_path.write_text("{ broken", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_health_proposal_artifact(
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

        result = try_read_health_proposal_artifact(missing_path)

        assert result is None

    def test_missing_file_silent_with_log_failures_false(self, tmp_path: Path, caplog: object) -> None:
        """With log_failures=False, missing file should return None silently."""
        import logging

        missing_path = tmp_path / "nonexistent.json"

        with caplog.at_level(logging.WARNING):
            result = try_read_health_proposal_artifact(
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

        result = try_read_health_proposal_artifact(artifact_path)

        assert result is None

    def test_missing_required_field_returns_none(self, tmp_path: Path) -> None:
        """Missing required field (confidence) should return None."""
        proposal_data = {
            "proposal_id": "p1",
            "source_run_id": "run-123",
            "source_artifact_path": "/review.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Change it.",
            "rationale": "Because.",
            # Missing confidence
            "expected_benefit": "Benefit.",
            "rollback_note": "Rollback.",
        }
        artifact_path = tmp_path / "no-confidence.json"
        artifact_path.write_text(json.dumps(proposal_data), encoding="utf-8")

        result = try_read_health_proposal_artifact(artifact_path)

        assert result is None

    def test_log_failures_true_logs_warning_with_safe_message(
        self, tmp_path: Path, caplog: object
    ) -> None:
        """With log_failures=True, should log warning containing safe metadata."""
        import logging

        artifact_path = tmp_path / "bad-proposal.json"
        artifact_path.write_text("{ broken", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_health_proposal_artifact(
                artifact_path,
                run_id="run-123",
                artifact_kind="health-proposal",
                log_failures=True,
            )

        assert result is None
        # Check that warning was logged
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) > 0
        # Check log message contains safe metadata (filename and kind)
        record = warning_records[0]
        assert "health-proposal" in record.message or "bad-proposal.json" in record.message
        assert "Skipped malformed" in record.message
        # Verify no raw content in the log message
        assert "{" not in record.message or "broken" not in record.message

    def test_roundtrip_serialization_preserves_fields(self, tmp_path: Path) -> None:
        """Roundtrip: to_dict -> write -> read should preserve all fields."""
        # Create a minimal proposal for roundtrip test
        proposal = HealthProposal(
            proposal_id="roundtrip-test",
            source_run_id="run-456",
            source_artifact_path="/path/to/review.json",
            target="health.baseline_policy.watched_releases",
            proposed_change="Allow v2.0.0.",
            rationale="Version drift detected.",
            confidence=ConfidenceLevel.HIGH,
            expected_benefit="Stop baseline alerts.",
            rollback_note="Remove version.",
            promotion_payload={"release_key": "my-release", "versions": ["v2.0.0"]},
            lifecycle_history=(),  # Empty tuple for simpler test
            artifact_id="0192a1b8-test-uuid",
        )

        # Write to disk
        artifact_path = tmp_path / "roundtrip.json"
        artifact_path.write_text(json.dumps(proposal.to_dict(), indent=2), encoding="utf-8")

        # Read back
        result = try_read_health_proposal_artifact(artifact_path)

        assert result is not None
        assert result.proposal_id == "roundtrip-test"
        assert result.source_run_id == "run-456"
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.artifact_id == "0192a1b8-test-uuid"
        assert result.promotion_payload.get("release_key") == "my-release"

    def test_log_failures_false_does_not_log_raw_content(
        self, tmp_path: Path, caplog: object
    ) -> None:
        """log_failures=False should never log raw proposal content."""
        import logging

        # Create a valid proposal with sensitive-looking content
        proposal_data = {
            "proposal_id": "p1",
            "source_run_id": "run-123",
            "source_artifact_path": "/review.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Change it to 100.",
            "rationale": "Because secrets were exposed.",
            "confidence": "medium",
            "expected_benefit": "Security improvement.",
            "rollback_note": "Revert.",
            "promotion_payload": {"threshold": 100, "admin_token": "super-secret-value"},
        }
        artifact_path = tmp_path / "sensitive-proposal.json"
        artifact_path.write_text(json.dumps(proposal_data), encoding="utf-8")

        # Read with valid data (should succeed, no logging)
        with caplog.at_level(logging.WARNING):
            result = try_read_health_proposal_artifact(
                artifact_path, run_id="run-123", log_failures=False
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


class TestHealthProposalArtifactReadError:
    """Tests for HealthProposalArtifactReadError exception."""

    def test_exception_carrying_safe_path(self) -> None:
        """Exception should include safe path (basename) not full path."""
        from pathlib import Path as PathType

        path = PathType("/some/long/path/to/proposal.json")
        exc = HealthProposalArtifactReadError(
            message="Test error",
            path=path,
        )

        assert "proposal.json" in str(exc)
        assert "/some/long/path" not in str(exc)

    def test_exception_with_cause(self) -> None:
        """Exception should chain underlying cause."""
        cause = ValueError("Original cause")
        exc = HealthProposalArtifactReadError(
            message="Read failed",
            path=Path("/test.json"),
            cause=cause,
        )

        assert exc.cause is cause
        assert exc.path == Path("/test.json")
