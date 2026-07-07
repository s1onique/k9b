"""Unit tests for Alertmanager endpoint verification.

Tests cover:
- Healthy/ready verification scenarios
- Failure handling (unhealthy, unreadiness)
- Connection errors and timeouts
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    verify_alertmanager_endpoint,
)


class TestVerificationHealthy:
    """Tests for successful verification scenarios."""

    def test_verification_healthy_and_ready(self) -> None:
        """Test verification passes when both endpoints return success."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            # Mock responses for both endpoints and status
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = json.dumps({
                "status": "success",
                "data": {"versionInfo": {"version": "0.25.0"}}
            }).encode()

            mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

            result = verify_alertmanager_endpoint("http://alertmanager:9093", timeout_seconds=5.0)

        assert result.healthy is True
        assert result.ready is True
        assert result.version == "0.25.0"
        assert result.error is None


class TestVerificationFailures:
    """Tests for verification failure scenarios."""

    def test_verification_failure_healthy(self) -> None:
        """Test verification fails when /-/healthy fails."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 503
            mock_response.reason = "Service Unavailable"

            mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

            result = verify_alertmanager_endpoint("http://alertmanager:9093", timeout_seconds=5.0)

        assert result.healthy is False
        assert result.ready is False
        assert result.error is not None

    def test_verification_failure_ready(self) -> None:
        """Test verification fails when /-/ready fails but /-/healthy succeeds."""
        call_count = [0]

        def side_effect(url: Any, timeout: float | None = None) -> MagicMock:
            url_str = str(url)
            call_count[0] += 1

            if call_count[0] == 1:  # First call: /-/healthy
                mock_response = MagicMock()
                mock_response.status = 200
                mock_response.__enter__ = MagicMock(return_value=mock_response)
                mock_response.__exit__ = MagicMock(return_value=False)
                return mock_response
            elif call_count[0] == 2:  # Second call: /-/ready - fail
                from http.client import HTTPMessage
                headers = HTTPMessage()
                raise urllib.error.HTTPError(
                    url=url_str,
                    code=500,
                    msg="Internal Server Error",
                    hdrs=headers,
                    fp=None,
                )
            else:  # Third call: version info
                mock_response = MagicMock()
                mock_response.status = 200
                mock_response.read.return_value = json.dumps({
                    "status": "success",
                    "data": {"versionInfo": {"version": "0.25.0"}}
                }).encode()
                mock_response.__enter__ = MagicMock(return_value=mock_response)
                mock_response.__exit__ = MagicMock(return_value=False)
                return mock_response

        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = verify_alertmanager_endpoint("http://alertmanager:9093", timeout_seconds=5.0)

        assert result.healthy is True
        assert result.ready is False
        assert result.error is not None
        assert "500" in result.error


class TestVerificationErrors:
    """Tests for error handling during verification."""

    def test_verification_connection_error(self) -> None:
        """Test verification handles connection errors gracefully."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            result = verify_alertmanager_endpoint("http://alertmanager:9093", timeout_seconds=5.0)

        assert result.healthy is False
        assert result.ready is False
        assert result.error is not None
        assert "Connection failed" in result.error

    def test_verification_timeout(self) -> None:
        """Test verification handles timeout gracefully."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("timed out")

            result = verify_alertmanager_endpoint("http://alertmanager:9093", timeout_seconds=5.0)

        assert result.healthy is False
        assert result.ready is False
        assert result.error is not None
        assert "timed out" in result.error
