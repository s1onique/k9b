"""Tests for incident snapshot API endpoint.

These tests verify:
- Backend route success with mock collector data
- Backend route failure with sanitized error
- Backend route redaction
- No sentinel patterns in API response
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from k8s_diag_agent.collect.api_incident import (
    IncidentSnapshotRequest,
    IncidentSnapshotResponse,
    handle_incident_snapshot,
)

# =============================================================================
# Mock Fixtures
# =============================================================================

FAKE_BUNDLE_DATA = {
    "metadata": {
        "bundle_id": "test-bundle-001",
        "captured_at": "2024-01-15T12:00:00+00:00",
        "namespace": "default",
        "since_hours": 2,
        "context": None,
        "total_pods": 5,
        "total_events": 3,
        "total_deployments": 2,
        "failing_pods_count": 2,
        "symptoms_count": 3,
    },
    "pods": [
        {
            "name": "healthy-pod",
            "namespace": "default",
            "phase": "running",
            "health_status": "running",
            "restart_count": 0,
            "node": "node-1",
            "image_refs": ["nginx:1.21"],
            "reason": None,
            "message": None,
            "is_failing": False,
        },
        {
            "name": "crashloop-pod",
            "namespace": "default",
            "phase": "running",
            "health_status": "crash_loop",
            "restart_count": 5,
            "node": "node-1",
            "image_refs": ["broken:v1"],
            "reason": "CrashLoopBackOff",
            "message": "Back-off 5m40s restarting",
            "is_failing": True,
        },
    ],
    "events": [
        {
            "namespace": "default",
            "name": "event-1",
            "type": "Warning",
            "reason": "BackOff",
            "message": "Back-off restarting container crashloop-pod",
            "involved_object_kind": "Pod",
            "involved_object_name": "crashloop-pod",
            "count": 3,
            "last_timestamp": "2024-01-15T12:00:00Z",
        },
    ],
    "deployments": [
        {
            "name": "nginx-deployment",
            "namespace": "default",
            "replicas": 3,
            "available_replicas": 3,
            "ready_replicas": 3,
            "updated_replicas": 3,
            "available": True,
        },
    ],
    "symptoms": [
        {
            "symptom_type": "crash_loop",
            "pod_name": "crashloop-pod",
            "message": "Pod crashloop-pod in CrashLoopBackOff",
            "severity": "error",
        },
    ],
    "collection_errors": [],
}


# =============================================================================
# Test Cases
# =============================================================================


class TestHandleIncidentSnapshot(unittest.TestCase):
    """Test the incident snapshot handler with mock data."""

    @patch("k8s_diag_agent.collect.incident_collectors.kubectl")
    def test_success_returns_bundle(self, mock_kubectl: unittest.mock.MagicMock) -> None:
        """Test that successful collection returns a bundle with summary."""
        # Configure mock to return fake pod data
        mock_kubectl.return_value = json.dumps({
            "apiVersion": "v1",
            "items": [
                {
                    "metadata": {"name": "test-pod", "namespace": "default"},
                    "status": {"phase": "Running", "containerStatuses": []},
                    "spec": {"nodeName": "node-1", "containers": [{"image": "nginx:v1"}]},
                }
            ],
        })

        request = IncidentSnapshotRequest(namespace="default", since_hours=2)
        response = handle_incident_snapshot(request)

        self.assertTrue(response.bundle_id.startswith("default-"))
        self.assertEqual(response.namespace, "default")
        self.assertEqual(response.summary["total_pods"], 1)
        self.assertEqual(response.error, None)
        self.assertIsNotNone(response.bundle)

    def test_error_returns_sanitized_message(self) -> None:
        """Test that errors are sanitized before returning."""
        # Use a request that will fail (invalid namespace would require actual kubectl)
        # Instead test with a mock that raises an exception
        with patch(
            "k8s_diag_agent.collect.api_incident.collect_incident_snapshot",
            side_effect=RuntimeError("kubectl connection refused"),
        ):
            request = IncidentSnapshotRequest(namespace="default")
            response = handle_incident_snapshot(request)

            self.assertEqual(response.bundle_id, "")
            self.assertIsNotNone(response.error)
            self.assertIn("kubectl", response.error.lower())
            # Error should be sanitized (no raw exception details)
            self.assertNotIn("Traceback", response.error)

    def test_response_to_dict(self) -> None:
        """Test that IncidentSnapshotResponse.to_dict() works correctly."""
        response = IncidentSnapshotResponse(
            bundle_id="test-001",
            captured_at="2024-01-15T12:00:00Z",
            namespace="default",
            summary={"total_pods": 5},
            bundle={"metadata": {}},
        )

        data = response.to_dict()

        self.assertEqual(data["bundle_id"], "test-001")
        self.assertEqual(data["namespace"], "default")
        self.assertEqual(data["summary"]["total_pods"], 5)
        self.assertIn("bundle", data)
        self.assertNotIn("error", data)

    def test_response_to_dict_with_error(self) -> None:
        """Test that error responses include error field."""
        response = IncidentSnapshotResponse(
            bundle_id="",
            captured_at="2024-01-15T12:00:00Z",
            namespace="default",
            summary={},
            error="Collection failed",
        )

        data = response.to_dict()

        self.assertEqual(data["error"], "Collection failed")
        self.assertNotIn("bundle", data)


class TestSentinelPatternsInResponse(unittest.TestCase):
    """Test that sensitive sentinel patterns do not appear in API responses."""

    _SENTINEL_PATTERNS = (
        "KUBE_SECRET_TOKEN_abc123",
        "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "api_key=sk-abcdefghijk",
        "client_secret=super_secret_value",
        "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "Authorization: Bearer sk-abc123",
    )

    def _contains_sentinel(self, value: str | None) -> bool:
        """Check if a string contains any sentinel test patterns."""
        if not value:
            return False
        return any(sentinel in value for sentinel in self._SENTINEL_PATTERNS)

    def _check_dict_for_sentinels(self, data: dict, path: str = "") -> list[str]:
        """Recursively check a dict for sentinel patterns."""
        violations: list[str] = []
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if isinstance(value, str):
                if self._contains_sentinel(value):
                    violations.append(f"{current_path}: contains sentinel")
            elif isinstance(value, dict):
                violations.extend(self._check_dict_for_sentinels(value, current_path))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, str) and self._contains_sentinel(item):
                        violations.append(f"{current_path}[{i}]: contains sentinel")
                    elif isinstance(item, dict):
                        violations.extend(self._check_dict_for_sentinels(item, f"{current_path}[{i}]"))
        return violations

    @patch("k8s_diag_agent.collect.incident_collectors.kubectl")
    def test_response_no_sentinels(self, mock_kubectl: unittest.mock.MagicMock) -> None:
        """API response should not contain any sentinel patterns."""
        # Return pods with embedded credentials
        mock_kubectl.return_value = json.dumps({
            "apiVersion": "v1",
            "items": [
                {
                    "metadata": {"name": "leaky-pod", "namespace": "default"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "state": {
                                    "waiting": {
                                        "reason": "CrashLoopBackOff",
                                        "message": "Failed auth: api_key=sk-abcdefghijk token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
                                    }
                                },
                            }
                        ],
                    },
                    "spec": {"containers": [{"image": "app:v1"}]},
                }
            ],
        })

        request = IncidentSnapshotRequest(namespace="default")
        response = handle_incident_snapshot(request)

        # Convert response to dict for checking
        data = response.to_dict()
        violations = self._check_dict_for_sentinels(data)

        self.assertEqual(
            violations,
            [],
            f"Response contains sentinel patterns: {violations}",
        )


if __name__ == "__main__":
    unittest.main()
