"""Tests for artifact_id surfacing in proposal and notification API payloads.

This module verifies that:
1. Proposal payloads include artifactId when present
2. Notification payloads include artifactId when present
3. Legacy artifacts without artifact_id serialize cleanly with artifactId: null
4. Backend/frontend typing remains consistent
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.identity.artifact import new_artifact_id
from k8s_diag_agent.ui.api import (
    NotificationEntry,
    ProposalEntry,
    _serialize_notification,
    _serialize_proposal,
)
from k8s_diag_agent.ui.model import (
    NotificationView,
    ProposalView,
    _build_notification_history,
    _build_proposal_view,
)


class TestProposalArtifactIdSurfacing(unittest.TestCase):
    """Tests for artifact_id surfacing in proposal API payloads."""

    def test_serialize_proposal_includes_artifact_id_when_present(self) -> None:
        """Verify _serialize_proposal includes artifactId when artifact_id is set."""
        artifact_id = new_artifact_id()
        proposal_view = ProposalView(
            proposal_id="test-proposal-1",
            target="test-target",
            status="pending",
            confidence="medium",
            rationale="Test rationale",
            expected_benefit="Test benefit",
            source_run_id="test-run-1",
            latest_note=None,
            artifact_path="/path/to/proposal.json",
            review_path="/path/to/review.json",
            lifecycle_history=(),
            artifact_id=artifact_id,
        )

        result = _serialize_proposal(proposal_view)

        assert isinstance(result, dict)
        assert "artifactId" in result
        assert result["artifactId"] == artifact_id
        assert result["proposalId"] == "test-proposal-1"

    def test_serialize_proposal_legacy_without_artifact_id(self) -> None:
        """Verify _serialize_proposal handles legacy artifacts without artifact_id."""
        proposal_view = ProposalView(
            proposal_id="legacy-proposal-1",
            target="test-target",
            status="pending",
            confidence="medium",
            rationale="Legacy rationale",
            expected_benefit="Legacy benefit",
            source_run_id="legacy-run-1",
            latest_note=None,
            artifact_path="/path/to/legacy/proposal.json",
            review_path="/path/to/legacy/review.json",
            lifecycle_history=(),
            artifact_id=None,  # Legacy artifact
        )

        result = _serialize_proposal(proposal_view)

        assert isinstance(result, dict)
        # artifactId should be present but None for backward compatibility
        assert "artifactId" in result
        assert result["artifactId"] is None
        assert result["proposalId"] == "legacy-proposal-1"

    def test_build_proposal_view_extracts_artifact_id(self) -> None:
        """Verify _build_proposal_view extracts artifact_id from raw data."""
        artifact_id = new_artifact_id()
        raw_proposal = {
            "proposal_id": "test-proposal-2",
            "target": "test-target-2",
            "status": "checked",
            "confidence": "high",
            "rationale": "Another test",
            "expected_benefit": "Another benefit",
            "source_run_id": "test-run-2",
            "lifecycle_history": [],
            "artifact_path": "/path/to/proposal2.json",
            "review_artifact": "/path/to/review2.json",
            "artifact_id": artifact_id,
        }

        result = _build_proposal_view(raw_proposal)

        assert isinstance(result, ProposalView)
        assert result.artifact_id == artifact_id
        assert result.proposal_id == "test-proposal-2"

    def test_build_proposal_view_handles_missing_artifact_id(self) -> None:
        """Verify _build_proposal_view handles legacy data without artifact_id."""
        raw_proposal = {
            "proposal_id": "legacy-proposal-2",
            "target": "test-target",
            "status": "pending",
            "confidence": "low",
            "rationale": "Legacy",
            "expected_benefit": "Legacy benefit",
            "source_run_id": "legacy-run-2",
            "lifecycle_history": [],
            "artifact_path": "/path/to/legacy2.json",
            "review_artifact": "/path/to/legacy2-review.json",
            # No artifact_id field - legacy artifact
        }

        result = _build_proposal_view(raw_proposal)

        assert isinstance(result, ProposalView)
        assert result.artifact_id is None
        assert result.proposal_id == "legacy-proposal-2"


class TestNotificationArtifactIdSurfacing(unittest.TestCase):
    """Tests for artifact_id surfacing in notification API payloads."""

    def test_serialize_notification_includes_artifact_id_when_present(self) -> None:
        """Verify _serialize_notification includes artifactId when artifact_id is set."""
        artifact_id = new_artifact_id()
        notification_view = NotificationView(
            kind="info",
            summary="Test notification",
            timestamp="2026-04-23T00:00:00Z",
            run_id="test-run-1",
            cluster_label="test-cluster",
            context="test-context",
            details=(("key", "value"),),
            artifact_path="/path/to/notification.json",
            artifact_id=artifact_id,
        )

        result = _serialize_notification(notification_view)

        assert isinstance(result, dict)
        assert "artifactId" in result
        assert result["artifactId"] == artifact_id
        assert result["summary"] == "Test notification"

    def test_serialize_notification_legacy_without_artifact_id(self) -> None:
        """Verify _serialize_notification handles legacy artifacts without artifact_id."""
        notification_view = NotificationView(
            kind="warning",
            summary="Legacy notification",
            timestamp="2025-01-01T00:00:00Z",
            run_id="legacy-run-1",
            cluster_label="legacy-cluster",
            context="legacy-context",
            details=(("legacy", "data"),),
            artifact_path="/path/to/legacy/notification.json",
            artifact_id=None,  # Legacy artifact
        )

        result = _serialize_notification(notification_view)

        assert isinstance(result, dict)
        # artifactId should be present but None for backward compatibility
        assert "artifactId" in result
        assert result["artifactId"] is None
        assert result["summary"] == "Legacy notification"

    def test_build_notification_history_extracts_artifact_id(self) -> None:
        """Verify _build_notification_history extracts artifact_id from raw data."""
        artifact_id = new_artifact_id()
        raw_notifications = [
            {
                "kind": "info",
                "summary": "Notification 1",
                "timestamp": "2026-04-23T01:00:00Z",
                "run_id": "test-run",
                "cluster_label": "cluster-1",
                "context": "ctx-1",
                "details": [],
                "artifact_path": "/path/to/n1.json",
                "artifact_id": artifact_id,
            }
        ]

        result = _build_notification_history(raw_notifications)

        assert isinstance(result, tuple)
        assert len(result) == 1
        assert result[0].artifact_id == artifact_id
        assert result[0].summary == "Notification 1"

    def test_build_notification_history_handles_missing_artifact_id(self) -> None:
        """Verify _build_notification_history handles legacy data without artifact_id."""
        raw_notifications = [
            {
                "kind": "warning",
                "summary": "Legacy notification",
                "timestamp": "2025-01-01T00:00:00Z",
                "run_id": "legacy-run",
                "cluster_label": "legacy-cluster",
                "context": "legacy-ctx",
                "details": [],
                "artifact_path": "/path/to/legacy.json",
                # No artifact_id field - legacy artifact
            }
        ]

        result = _build_notification_history(raw_notifications)

        assert isinstance(result, tuple)
        assert len(result) == 1
        assert result[0].artifact_id is None
        assert result[0].summary == "Legacy notification"


class TestTypedDictContracts(unittest.TestCase):
    """Tests for TypedDict contract compliance."""

    def test_proposal_entry_typeddict_allows_artifact_id(self) -> None:
        """Verify ProposalEntry TypedDict accepts artifactId field."""
        entry: ProposalEntry = {
            "proposalId": "test-1",
            "target": "test-target",
            "status": "pending",
            "confidence": "medium",
            "rationale": "Test",
            "expectedBenefit": "Benefit",
            "sourceRunId": "run-1",
            "latestNote": None,
            "lifecycle": [],
            "artifacts": [],
            "artifactId": new_artifact_id(),
        }
        assert entry["artifactId"] is not None

    def test_proposal_entry_typeddict_allows_null_artifact_id(self) -> None:
        """Verify ProposalEntry TypedDict accepts null artifactId for legacy."""
        entry: ProposalEntry = {
            "proposalId": "legacy-1",
            "target": "legacy-target",
            "status": "pending",
            "confidence": "low",
            "rationale": "Legacy",
            "expectedBenefit": "Legacy",
            "sourceRunId": "run-legacy",
            "latestNote": None,
            "lifecycle": [],
            "artifacts": [],
            "artifactId": None,  # Legacy - no artifact_id
        }
        assert entry["artifactId"] is None

    def test_notification_entry_typeddict_allows_artifact_id(self) -> None:
        """Verify NotificationEntry TypedDict accepts artifactId field."""
        entry: NotificationEntry = {
            "kind": "info",
            "summary": "Test",
            "timestamp": "2026-04-23T00:00:00Z",
            "runId": "test-run",
            "clusterLabel": "cluster",
            "context": "ctx",
            "details": [],
            "artifactPath": "/path/to.json",
            "artifactId": new_artifact_id(),
        }
        assert entry["artifactId"] is not None

    def test_notification_entry_typeddict_allows_null_artifact_id(self) -> None:
        """Verify NotificationEntry TypedDict accepts null artifactId for legacy."""
        entry: NotificationEntry = {
            "kind": "warning",
            "summary": "Legacy",
            "timestamp": "2025-01-01T00:00:00Z",
            "runId": "legacy-run",
            "clusterLabel": "legacy-cluster",
            "context": "legacy-ctx",
            "details": [],
            "artifactPath": "/legacy.json",
            "artifactId": None,  # Legacy - no artifact_id
        }
        assert entry["artifactId"] is None


class TestBackwardCompatibility(unittest.TestCase):
    """Tests verifying backward compatibility with legacy artifacts."""

    def test_proposal_payload_without_artifact_id_serializes_cleanly(self) -> None:
        """Verify proposal from legacy data without artifact_id serializes without errors."""
        # Simulate a legacy artifact that doesn't have artifact_id in the raw data
        legacy_proposal = {
            "proposal_id": "legacy-no-artifact-id",
            "target": "legacy-target",
            "status": "proposed",
            "confidence": "medium",
            "rationale": "Legacy proposal without artifact_id",
            "expected_benefit": "Improvement",
            "source_run_id": "legacy-run-no-artifact",
            "lifecycle_history": [
                {"status": "proposed", "timestamp": "2025-01-01T00:00:00Z", "note": None}
            ],
            "artifact_path": "/legacy/proposal-no-artifact-id.json",
            "review_artifact": "/legacy/review-no-artifact-id.json",
            # Intentionally missing artifact_id
        }

        # Build the view (should handle missing field gracefully)
        proposal_view = _build_proposal_view(legacy_proposal)
        assert proposal_view.artifact_id is None

        # Serialize the view (should include artifactId: null)
        serialized = _serialize_proposal(proposal_view)
        assert "artifactId" in serialized
        assert serialized["artifactId"] is None

    def test_notification_payload_without_artifact_id_serializes_cleanly(self) -> None:
        """Verify notification from legacy data without artifact_id serializes without errors."""
        # Simulate a legacy notification that doesn't have artifact_id in the raw data
        legacy_notification = {
            "kind": "info",
            "summary": "Legacy notification without artifact_id",
            "timestamp": "2025-01-01T00:00:00Z",
            "run_id": "legacy-run-no-artifact",
            "cluster_label": "legacy-cluster",
            "context": "legacy-ctx",
            "details": [],
            "artifact_path": "/legacy/notification-no-artifact-id.json",
            # Intentionally missing artifact_id
        }

        # Build the views (should handle missing field gracefully)
        notification_views = _build_notification_history([legacy_notification])
        assert len(notification_views) == 1
        assert notification_views[0].artifact_id is None

        # Serialize the view (should include artifactId: null)
        serialized = _serialize_notification(notification_views[0])
        assert "artifactId" in serialized
        assert serialized["artifactId"] is None


if __name__ == "__main__":
    unittest.main()
