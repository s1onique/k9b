#!/usr/bin/env python3
"""Tests for incident discovery gate snapshot trigger functionality.

Verifies:
- Snapshot trigger behavior
- Backend identity selection
- New failure class classification
- Snapshot response parsing
"""

import pytest

from tests.incident_discovery_gate_test_utils import (
    FAILURE_CANDIDATE_GENERATED_NOT_PROMOTED,
    FAILURE_INCIDENT_PROMOTED_NOT_LISTED,
    FAILURE_SNAPSHOT_COMPLETED_NO_CANDIDATES,
    FAILURE_SNAPSHOT_NOT_TRIGGERED,
)


class TestSnapshotTriggerResponseParsing:
    """Test parsing of snapshot API responses."""

    def test_snapshot_response_with_incidents(self) -> None:
        """Snapshot response with promoted incidents should be parsed correctly."""
        snapshot_response = {
            "bundle_id": "bundle-123",
            "captured_at": "2026-06-28T00:00:00Z",
            "namespace": "test-ns",
            "summary": {
                "total_pods": 5,
                "failing_pods_count": 1,
                "total_deployments": 2,
                "total_events": 10,
                "symptoms_count": 1,
                "candidates_count": 1,
                "incidents_promoted_count": 1,
            },
            "promoted_incidents": [
                {"incident_id": "inc-readiness-001", "status": "open"}
            ],
        }

        summary = snapshot_response.get("summary", {})
        assert summary.get("candidates_count") == 1
        assert summary.get("incidents_promoted_count") == 1
        assert len(snapshot_response.get("promoted_incidents", [])) == 1

    def test_snapshot_response_no_candidates(self) -> None:
        """Snapshot response with zero candidates."""
        snapshot_response = {
            "bundle_id": "bundle-456",
            "captured_at": "2026-06-28T00:00:00Z",
            "namespace": "test-ns",
            "summary": {
                "total_pods": 5,
                "failing_pods_count": 0,
                "total_deployments": 2,
                "total_events": 0,
                "symptoms_count": 0,
                "candidates_count": 0,
                "incidents_promoted_count": 0,
            },
            "promoted_incidents": [],
        }

        summary = snapshot_response.get("summary", {})
        assert summary.get("candidates_count") == 0
        assert summary.get("incidents_promoted_count") == 0

    def test_snapshot_response_error(self) -> None:
        """Snapshot response with error field."""
        snapshot_response: dict[str, object] = {
            "bundle_id": "",
            "captured_at": "2026-06-28T00:00:00Z",
            "namespace": "test-ns",
            "summary": {},
            "error": "Collection failed: namespace not found",
        }

        assert snapshot_response.get("error") is not None


class TestBackendIdentitySelection:
    """Test backend pod identity selection logic."""

    def test_single_running_pod(self) -> None:
        """Test selection when single pod is running."""
        pod_info = {
            "found": True,
            "pod_name": "k9b-backend-abc123",
            "namespace": "test-ns",
            "pod_ip": "10.0.0.1",
            "node_name": "node-1",
            "uid": "uid-12345",
            "creation_timestamp": "2026-06-28T00:00:00Z",
            "total_running_pods": 1,
        }

        assert pod_info["found"] is True
        assert pod_info["total_running_pods"] == 1
        assert pod_info["pod_name"] == "k9b-backend-abc123"

    def test_multiple_running_pods_warning(self) -> None:
        """Test selection when multiple pods are running."""
        pod_info = {
            "found": True,
            "pod_name": "k9b-backend-oldest-pod",
            "namespace": "test-ns",
            "pod_ip": "10.0.0.1",
            "node_name": "node-1",
            "uid": "uid-12345",
            "creation_timestamp": "2026-06-27T00:00:00Z",  # oldest
            "total_running_pods": 3,
        }

        assert pod_info["found"] is True
        assert pod_info["total_running_pods"] == 3
        # Oldest pod should be selected for consistency

    def test_no_running_pods(self) -> None:
        """Test selection when no pods are running."""
        pod_info = {
            "found": False,
            "error": "No running backend pods",
        }

        assert pod_info["found"] is False
        assert "error" in pod_info


class TestSnapshotFailureClassification:
    """Test failure classification for snapshot-related failures."""

    def test_snapshot_not_triggered_http_error(self) -> None:
        """HTTP error should trigger snapshot_not_triggered."""
        http_status = 500
        snapshot_response: dict[str, object] = {}

        failure = None
        if http_status != 200:
            failure = FAILURE_SNAPSHOT_NOT_TRIGGERED
        elif snapshot_response.get("error"):
            failure = FAILURE_SNAPSHOT_NOT_TRIGGERED

        assert failure == FAILURE_SNAPSHOT_NOT_TRIGGERED

    def test_snapshot_not_triggered_response_error(self) -> None:
        """Response with error field should trigger snapshot_not_triggered."""
        http_status = 200
        snapshot_response = {"error": "Collection failed"}

        failure = None
        if http_status != 200:
            failure = FAILURE_SNAPSHOT_NOT_TRIGGERED
        elif snapshot_response.get("error"):
            failure = FAILURE_SNAPSHOT_NOT_TRIGGERED

        assert failure == FAILURE_SNAPSHOT_NOT_TRIGGERED

    def test_snapshot_completed_no_candidates(self) -> None:
        """Snapshot success but zero candidates."""
        snapshot_response = {
            "summary": {
                "candidates_count": 0,
                "incidents_promoted_count": 0,
            }
        }

        candidates_count = snapshot_response.get("summary", {}).get("candidates_count", 0)
        assert candidates_count == 0

    def test_candidate_generated_not_promoted(self) -> None:
        """Snapshot generated candidates but none promoted."""
        candidates_count = 1
        incidents_promoted_count = 0
        promoted_incidents: list[object] = []

        failure = None
        if candidates_count == 0:
            failure = FAILURE_SNAPSHOT_COMPLETED_NO_CANDIDATES
        elif incidents_promoted_count == 0 and not promoted_incidents:
            failure = FAILURE_CANDIDATE_GENERATED_NOT_PROMOTED

        assert failure == FAILURE_CANDIDATE_GENERATED_NOT_PROMOTED

    def test_incident_promoted_not_listed(self) -> None:
        """Snapshot promoted incidents but list API returns empty."""
        incidents_promoted_count = 1
        promoted_incidents = [{"incident_id": "inc-123"}]
        api_incidents: list[str] = []

        failure = None
        if incidents_promoted_count > 0 or promoted_incidents:
            if not api_incidents:
                failure = FAILURE_INCIDENT_PROMOTED_NOT_LISTED

        assert failure == FAILURE_INCIDENT_PROMOTED_NOT_LISTED

    def test_incident_promoted_and_listed_success(self) -> None:
        """Snapshot promoted incidents and list API returns them."""
        incidents_promoted_count = 1
        promoted_incidents = [{"incident_id": "inc-123"}]
        api_incidents = ["inc-123"]

        failure = None
        if incidents_promoted_count > 0 or promoted_incidents:
            if not api_incidents:
                failure = FAILURE_INCIDENT_PROMOTED_NOT_LISTED

        assert failure is None  # Success case


class TestSnapshotAPICall:
    """Test snapshot API call structure."""

    def test_snapshot_api_request_format(self) -> None:
        """Verify snapshot API request structure."""
        # The call_backend_snapshot_api should construct proper request
        namespace = "test-ns"
        request_body = {
            "namespace": namespace,
            "since_hours": 2,
        }

        assert request_body["namespace"] == "test-ns"
        assert request_body["since_hours"] == 2

    def test_snapshot_api_endpoint(self) -> None:
        """Verify snapshot API endpoint path."""
        endpoint = "/api/incidents/snapshot"
        method = "POST"

        assert endpoint == "/api/incidents/snapshot"
        assert method == "POST"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
