"""Unit tests for Alertmanager webhook handler."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.incident_alert_signal import AlertSignal
from k8s_diag_agent.incident_alertmanager_webhook import (
    WebhookAuthError,
    WebhookDisabledError,
    WebhookError,
    WebhookPayloadError,
    WebhookResponse,
    handle_alertmanager_webhook,
    parse_payload,
    validate_bearer_token,
    validate_payload_size,
)


class TestValidateBearerToken:
    """Tests for validate_bearer_token function."""

    def test_valid_token(self):
        """Test valid bearer token returns True."""
        result = validate_bearer_token(
            auth_header="Bearer test-token",
            expected_token="test-token",
        )
        assert result is True

    def test_missing_token_config(self):
        """Test missing token config raises WebhookAuthError."""
        with pytest.raises(WebhookAuthError, match="No token configured"):
            validate_bearer_token(
                auth_header="Bearer test-token",
                expected_token=None,
            )

    def test_missing_auth_header(self):
        """Test missing auth header raises WebhookAuthError."""
        with pytest.raises(WebhookAuthError, match="Missing Authorization header"):
            validate_bearer_token(
                auth_header=None,
                expected_token="test-token",
            )

    def test_invalid_scheme(self):
        """Test invalid auth scheme raises WebhookAuthError."""
        with pytest.raises(WebhookAuthError, match="Invalid Authorization scheme"):
            validate_bearer_token(
                auth_header="Basic dXNlcjpwYXNz",
                expected_token="test-token",
            )

    def test_invalid_token(self):
        """Test invalid token raises WebhookAuthError."""
        with pytest.raises(WebhookAuthError, match="Invalid token"):
            validate_bearer_token(
                auth_header="Bearer wrong-token",
                expected_token="test-token",
            )


class TestValidatePayloadSize:
    """Tests for validate_payload_size function."""

    def test_valid_size(self):
        """Test valid payload size passes."""
        validate_payload_size(payload_bytes=100, max_bytes=1000)

    def test_equal_to_max(self):
        """Test payload equal to max passes."""
        validate_payload_size(payload_bytes=1000, max_bytes=1000)

    def test_too_large(self):
        """Test payload too large raises WebhookPayloadError."""
        with pytest.raises(WebhookPayloadError, match="Payload too large"):
            validate_payload_size(payload_bytes=2000, max_bytes=1000)


class TestParsePayload:
    """Tests for parse_payload function."""

    def test_valid_payload(self):
        """Test valid payload parses correctly."""
        raw_body = b'{"alerts": [{"labels": {"alertname": "Test"}}]}'
        payload = parse_payload(raw_body, max_bytes=1000)
        assert payload == {"alerts": [{"labels": {"alertname": "Test"}}]}

    def test_too_large(self):
        """Test payload too large raises WebhookPayloadError."""
        raw_body = b'{"alerts": []}'
        with pytest.raises(WebhookPayloadError, match="Payload too large"):
            parse_payload(raw_body, max_bytes=1)

    def test_invalid_json(self):
        """Test invalid JSON raises WebhookPayloadError."""
        raw_body = b"not valid json"
        with pytest.raises(WebhookPayloadError, match="Invalid JSON"):
            parse_payload(raw_body, max_bytes=1000)

    def test_non_object_payload(self):
        """Test non-object payload raises WebhookPayloadError."""
        raw_body = b'"just a string"'
        with pytest.raises(WebhookPayloadError, match="Payload must be a JSON object"):
            parse_payload(raw_body, max_bytes=1000)

    def test_missing_alerts_field(self):
        """Test payload without alerts field raises WebhookPayloadError."""
        raw_body = b'{"other": "data"}'
        with pytest.raises(WebhookPayloadError, match="Missing required 'alerts' field"):
            parse_payload(raw_body, max_bytes=1000)


class TestWebhookResponse:
    """Tests for WebhookResponse dataclass."""

    def test_to_dict(self):
        """Test to_dict conversion."""
        response = WebhookResponse(
            accepted=True,
            source_instance="test-instance",
            received_alert_count=5,
            normalized_signal_count=3,
            stored_signal_count=2,
            duplicate_signal_count=1,
            error_count=0,
            raw_payload_artifact_id="test-artifact-id",
        )
        result = response.to_dict()
        assert result["accepted"] is True
        assert result["source_instance"] == "test-instance"
        assert result["received_alert_count"] == 5
        assert result["normalized_signal_count"] == 3
        assert result["stored_signal_count"] == 2
        assert result["duplicate_signal_count"] == 1
        assert result["error_count"] == 0
        assert result["raw_payload_artifact_id"] == "test-artifact-id"

    def test_to_dict_with_errors(self):
        """Test to_dict with errors."""
        response = WebhookResponse(
            accepted=False,
            received_alert_count=5,
            normalized_signal_count=0,
            errors=[
                WebhookError(field="test", message="Test error"),
            ],
        )
        result = response.to_dict()
        assert result["accepted"] is False
        assert result["error_count"] == 1
        assert result["errors"][0]["field"] == "test"
        assert result["errors"][0]["message"] == "Test error"

    def test_to_error_dict(self):
        """Test to_error_dict conversion."""
        response = WebhookResponse(
            accepted=False,
            errors=[
                WebhookError(field="test", message="Test error"),
            ],
        )
        result = response.to_error_dict()
        assert result["accepted"] is False
        assert result["error"] == "invalid_payload"
        assert len(result["errors"]) == 1


class TestHandleAlertmanagerWebhook:
    """Tests for handle_alertmanager_webhook function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_webhook_disabled(self):
        """Test disabled webhook raises WebhookDisabledError."""
        from k8s_diag_agent.incident_alertmanager_webhook_config import (
            AlertmanagerWebhookConfig,
        )

        config = AlertmanagerWebhookConfig(enabled=False)

        with pytest.raises(WebhookDisabledError, match="disabled"):
            handle_alertmanager_webhook(
                auth_header=None,
                raw_body=b'{"alerts": []}',
                config=config,
                root=self.root,
            )

    def test_webhook_enabled_without_token_fails_closed(self):
        """Test webhook with enabled but no token fails closed (rejects request)."""
        from k8s_diag_agent.incident_alertmanager_webhook_config import (
            AlertmanagerWebhookConfig,
        )

        config = AlertmanagerWebhookConfig(enabled=True, bearer_token=None)

        # Fail-closed: enabled without token should reject
        with pytest.raises(WebhookAuthError, match="No token configured"):
            handle_alertmanager_webhook(
                auth_header=None,
                raw_body=b'{"alerts": []}',
                config=config,
                root=self.root,
            )

    def test_webhook_auth_required(self):
        """Test webhook with auth requires valid token."""
        from k8s_diag_agent.incident_alertmanager_webhook_config import (
            AlertmanagerWebhookConfig,
        )

        config = AlertmanagerWebhookConfig(enabled=True, bearer_token="secret-token")

        with pytest.raises(WebhookAuthError, match="Missing Authorization header"):
            handle_alertmanager_webhook(
                auth_header=None,
                raw_body=b'{"alerts": []}',
                config=config,
                root=self.root,
            )

        with pytest.raises(WebhookAuthError, match="Invalid token"):
            handle_alertmanager_webhook(
                auth_header="Bearer wrong-token",
                raw_body=b'{"alerts": []}',
                config=config,
                root=self.root,
            )

    def test_webhook_valid_request(self):
        """Test valid webhook request processing."""
        from k8s_diag_agent.incident_alertmanager_webhook_config import (
            AlertmanagerWebhookConfig,
        )

        config = AlertmanagerWebhookConfig(
            enabled=True,
            bearer_token="secret-token",
            source_instance="test-alertmanager",
        )

        # Create a mock alert signal
        mock_signal = AlertSignal(
            signal_id="test-signal-id",
            source_type="alertmanager",
            source_instance="test-alertmanager",
            status="firing",
            alertname="TestAlert",
            external_fingerprint="fp123",
            group_key="key123",
            receiver="test-receiver",
            severity="critical",
            labels={"alertname": "TestAlert"},
            annotations={},
            starts_at=datetime.now(UTC),
            ends_at=None,
            received_at=datetime.now(UTC),
            generator_url="http://example.com",
            external_url="http://example.com",
            raw_payload_artifact_id=None,
            truncation=None,
        )

        with patch(
            "k8s_diag_agent.incident_alertmanager_webhook.write_raw_payload_artifact"
        ) as mock_write_raw, patch(
            "k8s_diag_agent.incident_alertmanager_webhook.normalize_alertmanager_payload"
        ) as mock_normalize, patch(
            "k8s_diag_agent.incident_alertmanager_webhook.write_alert_signal_artifact"
        ) as mock_write_signal:
            mock_write_raw.return_value = MagicMock(
                success=True, artifact_id="raw-123"
            )
            mock_normalize.return_value = MagicMock(
                signals=[mock_signal], errors=[]
            )
            mock_write_signal.return_value = MagicMock(
                success=True, is_duplicate=False, artifact_id="signal-123"
            )

            response, status_code = handle_alertmanager_webhook(
                auth_header="Bearer secret-token",
                raw_body=b'{"alerts": [{"labels": {"alertname": "TestAlert"}}]}',
                config=config,
                root=self.root,
            )

            assert status_code == 200
            assert response.accepted is True
            assert response.received_alert_count == 1
            assert response.normalized_signal_count == 1
            assert response.stored_signal_count == 1
            assert response.raw_payload_artifact_id == "raw-123"

    def test_webhook_invalid_payload(self):
        """Test invalid payload returns 400."""
        from k8s_diag_agent.incident_alertmanager_webhook_config import (
            AlertmanagerWebhookConfig,
        )

        config = AlertmanagerWebhookConfig(enabled=True)

        with pytest.raises(WebhookPayloadError, match="Invalid JSON"):
            handle_alertmanager_webhook(
                auth_header=None,
                raw_body=b"not valid json",
                config=config,
                root=self.root,
            )
