"""Tests for content index projection API conversion.

Tests that index projections are correctly converted to API payloads.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.content_index.readpath_projection import (
    _DEFAULT_AUTO_DIAGNOSIS_LOOP_SUMMARY,
    _DEFAULT_AUTO_DIAGNOSIS_REVIEW,
    _DEFAULT_REVIEW_PACKET,
    index_detail_to_api_payload,
    index_summary_to_api_payload,
    safe_index_detail_to_api_payload,
    safe_index_summary_to_api_payload,
)


class TestIndexSummaryToApiPayload:
    """Test summary projection to API payload conversion."""

    def test_valid_summary_projection(self) -> None:
        """Test conversion of valid summary projection."""
        projection = {
            "incident_id": "incident-001",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "candidate_class": "CrashLoopBackOff",
            "severity": "high",
            "status": "open",
            "first_observed_at": "2024-01-01T00:00:00+00:00",
            "last_observed_at": "2024-01-01T00:01:00+00:00",
            "signal_count": 5,
            "evidence_count": 3,
            "latest_snapshot_bundle_id": "bundle-123",
        }

        result = index_summary_to_api_payload(projection)

        assert result["incident_id"] == "incident-001"
        assert result["namespace"] == "default"
        assert result["object_kind"] == "Pod"
        assert result["object_name"] == "test-pod"
        assert result["candidate_class"] == "CrashLoopBackOff"
        assert result["severity"] == "high"
        assert result["status"] == "open"
        assert result["first_observed_at"] == "2024-01-01T00:00:00+00:00"
        assert result["last_observed_at"] == "2024-01-01T00:01:00+00:00"
        assert result["signal_count"] == 5
        assert result["evidence_count"] == 3
        assert result["latest_snapshot_bundle_id"] == "bundle-123"
        assert result["review_packet"] == _DEFAULT_REVIEW_PACKET

    def test_minimal_summary_projection(self) -> None:
        """Test conversion of minimal summary projection with required fields only."""
        projection = {
            "incident_id": "incident-002",
            "namespace": "kube-system",
            "object_kind": "Deployment",
            "object_name": "coredns",
            "candidate_class": "DeploymentUnavailable",
            "severity": "medium",
            "status": "investigating",
        }

        result = index_summary_to_api_payload(projection)

        assert result["incident_id"] == "incident-002"
        assert result["namespace"] == "kube-system"
        assert result["object_kind"] == "Deployment"
        assert result["object_name"] == "coredns"
        # Missing optional fields get defaults
        assert result["signal_count"] == 0
        assert result["evidence_count"] == 0
        assert result["latest_snapshot_bundle_id"] is None
        assert result["review_packet"] == _DEFAULT_REVIEW_PACKET

    def test_missing_required_field_raises(self) -> None:
        """Test that missing required field raises ValueError."""
        projection = {
            "incident_id": "incident-003",
            "namespace": "default",
            # Missing object_kind, object_name, candidate_class, severity, status
        }

        with pytest.raises(ValueError, match="Missing required field"):
            index_summary_to_api_payload(projection)

    def test_suppression_fields_preserved(self) -> None:
        """Test that suppression fields are preserved when present."""
        projection = {
            "incident_id": "incident-004",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "candidate_class": "CrashLoopBackOff",
            "severity": "low",
            "status": "suppressed",
            "suppressed_reason": "known issue",
            "duplicate_of": "incident-001",
            "resolved_at": "2024-01-01T12:00:00+00:00",
            "resolution_notes": "Fixed by updating image",
        }

        result = index_summary_to_api_payload(projection)

        assert result["suppressed_reason"] == "known issue"
        assert result["duplicate_of"] == "incident-001"
        assert result["resolved_at"] == "2024-01-01T12:00:00+00:00"
        assert result["resolution_notes"] == "Fixed by updating image"


class TestIndexDetailToApiPayload:
    """Test detail projection to API payload conversion."""

    def test_valid_detail_projection(self) -> None:
        """Test conversion of valid detail projection."""
        projection = {
            "incident_id": "incident-001",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "candidate_class": "CrashLoopBackOff",
            "severity": "high",
            "status": "open",
            "source_candidate_id": "candidate-001",
            "first_observed_at": "2024-01-01T00:00:00+00:00",
            "last_observed_at": "2024-01-01T00:01:00+00:00",
            "signal_count": 5,
            "evidence_count": 3,
        }

        result = index_detail_to_api_payload(projection)

        assert result["incident_id"] == "incident-001"
        assert result["source_candidate_id"] == "candidate-001"
        # Empty lists for unavailable data
        assert result["signals"] == []
        assert result["evidence_needed"] == []
        assert result["evidence_links"] == []
        assert result["events"] == []
        assert result["evidence_artifacts"] == []
        assert result["suggested_checks"] == []
        # Default diagnosis reviews
        assert result["automatic_diagnosis_review"] == _DEFAULT_AUTO_DIAGNOSIS_REVIEW
        assert result["automatic_diagnosis_loop_summary"] == _DEFAULT_AUTO_DIAGNOSIS_LOOP_SUMMARY

    def test_missing_required_field_raises(self) -> None:
        """Test that missing required field raises ValueError."""
        projection = {
            "incident_id": "incident-002",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            # Missing source_candidate_id
        }

        with pytest.raises(ValueError, match="Missing required field"):
            index_detail_to_api_payload(projection)


class TestSafeConversion:
    """Test safe conversion wrappers that return None on error."""

    def test_safe_summary_with_valid_projection(self) -> None:
        """Test safe summary conversion with valid projection."""
        projection = {
            "incident_id": "incident-001",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "candidate_class": "CrashLoopBackOff",
            "severity": "high",
            "status": "open",
        }

        result = safe_index_summary_to_api_payload(projection, "test_reason")

        assert result is not None
        assert result["incident_id"] == "incident-001"

    def test_safe_summary_with_missing_field_returns_none(self) -> None:
        """Test safe summary conversion with missing field returns None."""
        projection = {
            "incident_id": "incident-001",
            # Missing other required fields
        }

        result = safe_index_summary_to_api_payload(projection, "test_reason")

        assert result is None

    def test_safe_detail_with_valid_projection(self) -> None:
        """Test safe detail conversion with valid projection."""
        projection = {
            "incident_id": "incident-001",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "candidate_class": "CrashLoopBackOff",
            "severity": "high",
            "status": "open",
            "source_candidate_id": "candidate-001",
        }

        result = safe_index_detail_to_api_payload(projection, "test_reason")

        assert result is not None
        assert result["incident_id"] == "incident-001"

    def test_safe_detail_with_missing_field_returns_none(self) -> None:
        """Test safe detail conversion with missing field returns None."""
        projection = {
            "incident_id": "incident-001",
            # Missing other required fields
        }

        result = safe_index_detail_to_api_payload(projection, "test_reason")

        assert result is None


class TestDefaultValues:
    """Test that default values are correct for missing fields."""

    def test_default_review_packet(self) -> None:
        """Test default review packet structure."""
        assert _DEFAULT_REVIEW_PACKET["status"] == "unknown"
        assert _DEFAULT_REVIEW_PACKET["id"] is None
        assert _DEFAULT_REVIEW_PACKET["generated_at"] is None
        assert _DEFAULT_REVIEW_PACKET["error_message"] is None

    def test_default_auto_diagnosis_review(self) -> None:
        """Test default automatic diagnosis review structure."""
        assert _DEFAULT_AUTO_DIAGNOSIS_REVIEW["available"] is False
        assert _DEFAULT_AUTO_DIAGNOSIS_REVIEW["unavailable_reason"] == "no_review_packet"
        assert _DEFAULT_AUTO_DIAGNOSIS_REVIEW["provider_status"] is None

    def test_default_auto_diagnosis_loop_summary(self) -> None:
        """Test default automatic diagnosis loop summary structure."""
        assert _DEFAULT_AUTO_DIAGNOSIS_LOOP_SUMMARY["status"] == "not_run"
        assert _DEFAULT_AUTO_DIAGNOSIS_LOOP_SUMMARY["read_only"] is True
        assert _DEFAULT_AUTO_DIAGNOSIS_LOOP_SUMMARY["review_required_before_any_action"] is True
        assert _DEFAULT_AUTO_DIAGNOSIS_LOOP_SUMMARY["no_remediation_attempted"] is True
