#!/usr/bin/env python3
"""Artifact-level privacy regression tests for backend health gate.

Verifies that status.json and health-dependencies.json do not contain
raw secrets, private IPs, or internal URLs.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.backend_health_gate.k8s_diagnostics import (
    _collect_backend_diagnostics,
    _collect_scheduler_diagnostics,
    _sanitize_message_snippet,
)


class TestArtifactPrivacy:
    """Test that uploadable artifacts contain no raw secrets/private endpoints."""

    def _make_pod_with_waiting_message(self, message: str) -> dict:
        """Create a mock pod with waiting container state."""
        return {
            "metadata": {"name": "test-pod-abc123"},
            "status": {
                "phase": "Pending",
                "containerStatuses": [{
                    "name": "backend",
                    "restartCount": 0,
                    "state": {
                        "waiting": {
                            "reason": "Error",
                            "message": message,
                        }
                    },
                }],
            },
        }

    def test_collect_backend_diagnostics_no_raw_secrets_in_message(self):
        """Backend diagnostics container waiting messages do not contain raw secrets."""
        mock_pods = {"items": [self._make_pod_with_waiting_message(
            "Failed to connect to https://api.internal.example.com: Connection refused - API key sk-12345678901234567890"
        )]}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_pods), stderr="")
            diagnostics = _collect_backend_diagnostics("/fake/kubeconfig", "test-ns")

        # Serialize as JSON (simulating status.json writing)
        diag_json = json.dumps(diagnostics)

        # Verify raw secrets are NOT present
        assert "sk-12345678901234567890" not in diag_json, "Raw API key should not appear in artifact"
        assert "api.internal.example.com" not in diag_json, "Internal URL should not appear in artifact"

        # Verify redaction markers ARE present
        assert "<REDACTED_API_KEY>" in diag_json or "<REDACTED_PRIVATE_URL>" in diag_json

    def test_collect_backend_diagnostics_no_private_ips_in_message(self):
        """Backend diagnostics container waiting messages do not contain private IPs."""
        test_cases = [
            ("10.0.0.5:8080", "10.x.x.x"),
            ("172.16.0.100:443", "172.16-31.x.x"),
            ("192.168.1.50:9090", "192.168.x.x"),
        ]

        for private_endpoint, description in test_cases:
            mock_pods = {"items": [self._make_pod_with_waiting_message(
                f"Connection failed to {private_endpoint}"
            )]}

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_pods), stderr="")
                diagnostics = _collect_backend_diagnostics("/fake/kubeconfig", "test-ns")

            diag_json = json.dumps(diagnostics)

            assert private_endpoint not in diag_json, f"{description} ({private_endpoint}) should not appear in artifact"
            assert "<REDACTED_PRIVATE_IP>" in diag_json, f"{description} should use <REDACTED_PRIVATE_IP> marker"

    def test_collect_scheduler_diagnostics_no_raw_secrets_in_message(self):
        """Scheduler diagnostics container waiting messages do not contain raw secrets."""
        mock_pods = {"items": [self._make_pod_with_waiting_message(
            "Failed to connect to https://api.internal.example.com: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        )]}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_pods), stderr="")
            diagnostics = _collect_scheduler_diagnostics("/fake/kubeconfig", "test-ns")

        diag_json = json.dumps(diagnostics)

        # Verify raw secrets are NOT present
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in diag_json, "Raw Bearer token should not appear in artifact"
        assert "api.internal.example.com" not in diag_json, "Internal URL should not appear in artifact"

        # Verify redaction markers ARE present
        assert "<REDACTED_API_KEY>" in diag_json or "<REDACTED_PRIVATE_URL>" in diag_json

    def test_collect_scheduler_diagnostics_no_private_ips_in_message(self):
        """Scheduler diagnostics container waiting messages do not contain private IPs."""
        mock_pods = {"items": [self._make_pod_with_waiting_message(
            "Failed to connect to 10.255.255.1:6443"
        )]}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_pods), stderr="")
            diagnostics = _collect_scheduler_diagnostics("/fake/kubeconfig", "test-ns")

        diag_json = json.dumps(diagnostics)

        assert "10.255.255.1" not in diag_json, "Private IP should not appear in artifact"
        assert "<REDACTED_PRIVATE_IP>" in diag_json

    def test_sanitize_message_snippet_redacts_all_sensitive_patterns(self):
        """_sanitize_message_snippet properly redacts API keys, IPs, and URLs."""
        raw_message = (
            "Failed to connect to 10.0.0.5:8080 via https://api.internal.example.com "
            "with key sk-12345678901234567890"
        )

        # Use longer max_len to avoid truncation cutting off the marker
        sanitized = _sanitize_message_snippet(raw_message, max_len=200)

        # Verify none of the raw values appear
        assert "10.0.0.5" not in sanitized
        assert "api.internal.example.com" not in sanitized
        assert "sk-12345678901234567890" not in sanitized

        # Verify redaction markers are present (may be truncated if message is long)
        assert "<REDACTED_PRIVATE_IP>" in sanitized
        assert "<REDACTED_PRIVATE_URL>" in sanitized
        assert "<REDACTED_API_KEY>" in sanitized

    def test_sanitize_message_snippet_handles_empty_message(self):
        """_sanitize_message_snippet handles empty messages gracefully."""
        assert _sanitize_message_snippet("") == ""
        assert _sanitize_message_snippet(None) == ""

    def test_sanitize_message_snippet_truncates_long_messages(self):
        """_sanitize_message_snippet truncates long messages."""
        long_message = "A" * 200
        sanitized = _sanitize_message_snippet(long_message, max_len=100)
        assert len(sanitized) <= 103  # 100 + "..."


class TestStatusJsonSimulation:
    """Simulate status.json writing to verify full artifact privacy."""

    def _make_mock_status_data(self, backend_diags: dict, scheduler_diags: dict) -> dict:
        """Create mock status_data structure as written to status.json."""
        return {
            "failure_class": "dependency_backend_pending",
            "passed": False,
            "final_http_code": "500",
            "poll_count": 3,
            "max_retries": 30,
            "total_elapsed_seconds": 15.0,
            "http_statuses_seen": ["500", "500", "500"],
            "transport_error": "",
            "diagnostics": {
                "backend": backend_diags,
                "scheduler": scheduler_diags,
            },
        }

    def test_status_json_simulated_no_raw_secrets(self):
        """Simulated status.json does not contain raw secrets in diagnostics."""
        from scripts.backend_health_gate.k8s_diagnostics import _collect_backend_diagnostics, _collect_scheduler_diagnostics

        mock_backend_pods = {"items": [{
            "metadata": {"name": "k9b-backend-xyz"},
            "status": {
                "phase": "Pending",
                "containerStatuses": [{
                    "name": "backend",
                    "restartCount": 0,
                    "state": {
                        "waiting": {
                            "reason": "Error",
                            "message": "Failed to connect to 10.0.0.5: Connection refused - API key sk-abcdefghijklmnopqrst",
                        }
                    },
                }],
            },
        }]}

        mock_scheduler_pods = {"items": [{
            "metadata": {"name": "k9b-scheduler-abc"},
            "status": {
                "phase": "Running",
                "containerStatuses": [{
                    "name": "scheduler",
                    "restartCount": 0,
                    "state": {"running": {}},
                }],
            },
        }]}

        with patch("subprocess.run") as mock_run:
            def side_effect(*args, **kwargs):
                cmd = args[0]
                if "-l" in cmd and "k9b-scheduler" in " ".join(cmd):
                    return MagicMock(returncode=0, stdout=json.dumps(mock_scheduler_pods), stderr="")
                return MagicMock(returncode=0, stdout=json.dumps(mock_backend_pods), stderr="")

            mock_run.side_effect = side_effect
            backend_diags = _collect_backend_diagnostics("/fake", "test")
            scheduler_diags = _collect_scheduler_diagnostics("/fake", "test")

        status_data = self._make_mock_status_data(backend_diags, scheduler_diags)
        status_json = json.dumps(status_data, indent=2)

        # Verify no raw secrets
        assert "sk-abcdefghijklmnopqrst" not in status_json
        assert "10.0.0.5" not in status_json

        # Verify redaction markers present
        assert "<REDACTED_PRIVATE_IP>" in status_json
        assert "<REDACTED_API_KEY>" in status_json


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
