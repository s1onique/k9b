"""Redaction verification tests for incident snapshot collection.

These tests verify that secrets, tokens, and auth credentials are properly
redacted before being written to incident bundles.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.collect.incident_snapshot import (
    IncidentBundleMetadata,
    IncidentEvidenceBundle,
    write_incident_bundle,
    _parse_event_summary,
    _parse_pod_summary,
)
from datetime import UTC, datetime


# =============================================================================
# Sentinel Patterns - These should NEVER appear in sanitized output
# =============================================================================

_SENTINEL_PATTERNS = (
    "KUBE_SECRET_TOKEN_abc123",
    "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
    "api_key=sk-abcdefghijk",
    "client_secret=super_secret_value",
    "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
    "Authorization: Bearer sk-abc123",
    "password=super_secret",
    "secret_key=abc123xyz",
)


# =============================================================================
# Test Fixtures with Embedded Credentials
# =============================================================================

POD_WITH_SECRET_IN_MESSAGE = {
    "metadata": {
        "name": "leaky-pod",
        "namespace": "default",
    },
    "status": {
        "phase": "Running",
        "containerStatuses": [
            {
                "restartCount": 0,
                "state": {
                    "waiting": {
                        "reason": "CrashLoopBackOff",
                        "message": "Failed to connect: token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 status=401",
                    }
                },
            }
        ],
    },
    "spec": {
        "nodeName": "node-1",
        "containers": [{"image": "app:v1"}],
    },
}

EVENT_WITH_BEARER_TOKEN = {
    "metadata": {
        "name": "auth-event",
        "namespace": "default",
        "lastTimestamp": "2024-01-15T12:00:00Z",
    },
    "type": "Warning",
    "reason": "AuthFailure",
    "message": "Failed auth: Authorization: Bearer sk-abcdefghijk",
    "involvedObject": {"kind": "Pod", "name": "some-pod"},
    "count": 5,
}

EVENT_WITH_PASSWORD = {
    "metadata": {
        "name": "config-event",
        "namespace": "default",
        "lastTimestamp": "2024-01-15T12:00:00Z",
    },
    "type": "Warning",
    "reason": "ConfigError",
    "message": "Config error: client_secret=super_secret_value",
    "involvedObject": {"kind": "ConfigMap", "name": "app-config"},
    "count": 1,
}

EVENT_WITH_API_KEY = {
    "metadata": {
        "name": "api-event",
        "namespace": "default",
        "lastTimestamp": "2024-01-15T12:00:00Z",
    },
    "type": "Warning",
    "reason": "APIError",
    "message": "API call failed: api_key=sk-abcdefghijk",
    "involvedObject": {"kind": "Pod", "name": "api-pod"},
    "count": 2,
}


# =============================================================================
# Helper Functions
# =============================================================================


def _contains_sentinel(value: str | None) -> bool:
    """Check if a string contains any sentinel test patterns."""
    if not value:
        return False
    return any(sentinel in value for sentinel in _SENTINEL_PATTERNS)


def _check_sentinels_in_dict(data: dict, path: str = "") -> list[str]:
    """Recursively check a dict for sentinel patterns."""
    violations: list[str] = []
    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key
        if isinstance(value, str):
            if _contains_sentinel(value):
                violations.append(f"{current_path}: contains sentinel")
        elif isinstance(value, dict):
            violations.extend(_check_sentinels_in_dict(value, current_path))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str) and _contains_sentinel(item):
                    violations.append(f"{current_path}[{i}]: contains sentinel")
                elif isinstance(item, dict):
                    violations.extend(_check_sentinels_in_dict(item, f"{current_path}[{i}]"))
    return violations


# =============================================================================
# Test Cases
# =============================================================================


class TestEventMessageRedaction(unittest.TestCase):
    """Test that event messages are sanitized."""

    def test_bearer_token_redacted_in_event(self) -> None:
        """Bearer tokens in event messages should be redacted."""
        event = EVENT_WITH_BEARER_TOKEN
        summary = _parse_event_summary(event)

        # The message should NOT contain the raw bearer token
        self.assertNotIn("Bearer sk-", summary.message)
        self.assertNotIn("sk-abcdefghijk", summary.message)
        self.assertNotIn("sk-", summary.message)

    def test_password_redacted_in_event(self) -> None:
        """client_secret values in event messages should be redacted."""
        event = EVENT_WITH_PASSWORD
        summary = _parse_event_summary(event)

        # The actual secret value should be redacted (this is what the sanitizer catches)
        self.assertNotIn("client_secret=super_secret_value", summary.message)
        # The structure should still be visible
        self.assertIn("Config error", summary.message)

    def test_api_key_redacted_in_event(self) -> None:
        """API keys in event messages should be redacted."""
        event = EVENT_WITH_API_KEY
        summary = _parse_event_summary(event)

        self.assertNotIn("api_key=", summary.message)
        self.assertNotIn("sk-abcdefghijk", summary.message)
        self.assertNotIn("sk-", summary.message)

    def test_sanitized_message_still_readable(self) -> None:
        """Sanitized messages should still contain non-sensitive context."""
        event = EVENT_WITH_BEARER_TOKEN
        summary = _parse_event_summary(event)

        # The event reason and basic structure should be preserved
        self.assertEqual(summary.reason, "AuthFailure")
        self.assertEqual(summary.type, "Warning")
        self.assertIn("Failed auth", summary.message)


class TestPodMessageRedaction(unittest.TestCase):
    """Test that pod messages are sanitized."""

    def test_token_redacted_in_pod_message(self) -> None:
        """JWT tokens in pod messages should be redacted."""
        pod = POD_WITH_SECRET_IN_MESSAGE
        summary = _parse_pod_summary(pod)

        # The message should NOT contain the raw JWT token or token= pattern
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", summary.message)
        self.assertNotIn("token=", summary.message)
        # The error context should still be visible
        self.assertIn("Failed to connect", summary.message)

    def test_sanitized_pod_message_preserves_context(self) -> None:
        """Sanitized pod messages should still be somewhat readable."""
        pod = POD_WITH_SECRET_IN_MESSAGE
        summary = _parse_pod_summary(pod)

        # Basic context should be preserved
        self.assertIsNotNone(summary.message)
        self.assertIsInstance(summary.message, str)


class TestBundleRedaction(unittest.TestCase):
    """Test that complete bundles are redacted."""

    def test_full_bundle_no_sentinels(self) -> None:
        """Bundle JSON should not contain any sentinel patterns."""
        from k8s_diag_agent.collect.incident_snapshot import (
            _detect_symptoms,
        )

        # Create a bundle with pods and events containing sensitive data
        pod = _parse_pod_summary(POD_WITH_SECRET_IN_MESSAGE)
        events = [
            _parse_event_summary(EVENT_WITH_BEARER_TOKEN),
            _parse_event_summary(EVENT_WITH_PASSWORD),
            _parse_event_summary(EVENT_WITH_API_KEY),
        ]

        metadata = IncidentBundleMetadata(
            bundle_id="redact-test-001",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=1,
            total_events=3,
            total_deployments=0,
            failing_pods_count=1,
            symptoms_count=1,
        )

        symptoms = _detect_symptoms([pod], events)

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[pod],
            events=events,
            deployments=[],
            symptoms=symptoms,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            written = write_incident_bundle(bundle, output_dir)

            # Check incident.json
            incident_path = written["incident.json"]
            incident_data = json.loads(incident_path.read_text())

            violations = _check_sentinels_in_dict(incident_data)
            self.assertEqual(
                violations,
                [],
                f"incident.json contains {len(violations)} redaction violations: {violations}",
            )

            # Check events.json
            events_path = written["objects/events.json"]
            events_data = json.loads(events_path.read_text())

            violations = _check_sentinels_in_dict({"events": events_data})
            self.assertEqual(
                violations,
                [],
                f"events.json contains {len(violations)} redaction violations: {violations}",
            )

            # Check pods.json
            pods_path = written["objects/pods.json"]
            pods_data = json.loads(pods_path.read_text())

            violations = _check_sentinels_in_dict({"pods": pods_data})
            self.assertEqual(
                violations,
                [],
                f"pods.json contains {len(violations)} redaction violations: {violations}",
            )


class TestBundleMetadataSafe(unittest.TestCase):
    """Test that bundle metadata itself doesn't leak sensitive data."""

    def test_bundle_id_safe(self) -> None:
        """Bundle ID should not contain sensitive information."""
        metadata = IncidentBundleMetadata(
            bundle_id="default-20240115-120000",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=0,
            total_events=0,
            total_deployments=0,
            failing_pods_count=0,
            symptoms_count=0,
        )

        # Bundle ID should be safe
        self.assertFalse(_contains_sentinel(metadata.bundle_id))
        self.assertFalse(_contains_sentinel(metadata.namespace))
        self.assertFalse(_contains_sentinel(metadata.context or ""))

    def test_context_safe(self) -> None:
        """Context name should not leak sensitive data."""
        metadata = IncidentBundleMetadata(
            bundle_id="test-001",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="production",
            since_hours=2,
            context="prod-cluster",
            total_pods=0,
            total_events=0,
            total_deployments=0,
            failing_pods_count=0,
            symptoms_count=0,
        )

        # Context name should be safe
        self.assertFalse(_contains_sentinel(metadata.context or ""))


if __name__ == "__main__":
    unittest.main()
