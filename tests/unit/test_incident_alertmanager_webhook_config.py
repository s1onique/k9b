"""Unit tests for Alertmanager webhook configuration."""

from __future__ import annotations

import os
import tempfile

from k8s_diag_agent.incident_alertmanager_webhook_config import (
    DEFAULT_MAX_PAYLOAD_BYTES,
    DEFAULT_SOURCE_INSTANCE,
    AlertmanagerWebhookConfig,
    get_alertmanager_webhook_config,
    parse_alertmanager_webhook_config,
    reset_alertmanager_webhook_config,
    set_alertmanager_webhook_config,
)


class TestAlertmanagerWebhookConfig:
    """Tests for AlertmanagerWebhookConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AlertmanagerWebhookConfig()
        assert config.enabled is False
        assert config.bearer_token is None
        assert config.source_instance == DEFAULT_SOURCE_INSTANCE
        assert config.max_payload_bytes == DEFAULT_MAX_PAYLOAD_BYTES

    def test_enabled_config(self):
        """Test enabled configuration."""
        config = AlertmanagerWebhookConfig(
            enabled=True,
            bearer_token="test-token",
            source_instance="custom-instance",
            max_payload_bytes=1024,
        )
        assert config.enabled is True
        assert config.bearer_token == "test-token"
        assert config.source_instance == "custom-instance"
        assert config.max_payload_bytes == 1024

    def test_is_authenticated(self):
        """Test is_authenticated method."""
        config_no_token = AlertmanagerWebhookConfig(enabled=True)
        assert config_no_token.is_authenticated() is False

        config_with_token = AlertmanagerWebhookConfig(
            enabled=True,
            bearer_token="test-token",
        )
        assert config_with_token.is_authenticated() is True

    def test_requires_auth(self):
        """Test requires_auth method."""
        config_disabled = AlertmanagerWebhookConfig(enabled=False)
        assert config_disabled.requires_auth() is False

        config_enabled = AlertmanagerWebhookConfig(enabled=True)
        assert config_enabled.requires_auth() is True


class TestParseAlertmanagerWebhookConfig:
    """Tests for parse_alertmanager_webhook_config function."""

    def setup_method(self):
        """Reset global config before each test."""
        reset_alertmanager_webhook_config()
        # Clear environment variables
        for key in list(os.environ.keys()):
            if key.startswith("K9B_ALERTMANAGER_WEBHOOK_"):
                del os.environ[key]

    def teardown_method(self):
        """Clean up environment after each test."""
        for key in list(os.environ.keys()):
            if key.startswith("K9B_ALERTMANAGER_WEBHOOK_"):
                del os.environ[key]
        reset_alertmanager_webhook_config()

    def test_parse_disabled_by_default(self):
        """Test that webhook is disabled by default."""
        config = parse_alertmanager_webhook_config()
        assert config.enabled is False
        assert config.bearer_token is None

    def test_parse_enabled_flag(self):
        """Test parsing enabled flag."""
        os.environ["K9B_ALERTMANAGER_WEBHOOK_ENABLED"] = "true"
        config = parse_alertmanager_webhook_config()
        assert config.enabled is True

        os.environ["K9B_ALERTMANAGER_WEBHOOK_ENABLED"] = "false"
        config = parse_alertmanager_webhook_config()
        assert config.enabled is False

        os.environ["K9B_ALERTMANAGER_WEBHOOK_ENABLED"] = "1"
        config = parse_alertmanager_webhook_config()
        assert config.enabled is True

        os.environ["K9B_ALERTMANAGER_WEBHOOK_ENABLED"] = "yes"
        config = parse_alertmanager_webhook_config()
        assert config.enabled is True

    def test_parse_inline_token(self):
        """Test parsing inline bearer token."""
        os.environ["K9B_ALERTMANAGER_WEBHOOK_TOKEN"] = "my-secret-token"
        config = parse_alertmanager_webhook_config()
        assert config.bearer_token == "my-secret-token"

    def test_parse_token_file_wins_over_inline(self):
        """Test that token file takes precedence over inline token."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".token") as f:
            f.write("file-token")
            token_file = f.name

        try:
            os.environ["K9B_ALERTMANAGER_WEBHOOK_TOKEN"] = "inline-token"
            os.environ["K9B_ALERTMANAGER_WEBHOOK_TOKEN_FILE"] = token_file
            config = parse_alertmanager_webhook_config()
            assert config.bearer_token == "file-token"
        finally:
            os.unlink(token_file)

    def test_parse_source_instance(self):
        """Test parsing source instance."""
        os.environ["K9B_ALERTMANAGER_WEBHOOK_SOURCE_INSTANCE"] = "custom-alertmanager"
        config = parse_alertmanager_webhook_config()
        assert config.source_instance == "custom-alertmanager"

    def test_parse_max_payload_bytes(self):
        """Test parsing max payload bytes."""
        os.environ["K9B_ALERTMANAGER_WEBHOOK_MAX_PAYLOAD_BYTES"] = "1024"
        config = parse_alertmanager_webhook_config()
        assert config.max_payload_bytes == 1024

    def test_parse_invalid_max_payload_bytes(self):
        """Test that invalid max payload bytes uses default."""
        os.environ["K9B_ALERTMANAGER_WEBHOOK_MAX_PAYLOAD_BYTES"] = "invalid"
        config = parse_alertmanager_webhook_config()
        assert config.max_payload_bytes == DEFAULT_MAX_PAYLOAD_BYTES

    def test_parse_negative_max_payload_bytes(self):
        """Test that negative max payload bytes uses default."""
        os.environ["K9B_ALERTMANAGER_WEBHOOK_MAX_PAYLOAD_BYTES"] = "-100"
        config = parse_alertmanager_webhook_config()
        assert config.max_payload_bytes == DEFAULT_MAX_PAYLOAD_BYTES


class TestGlobalConfig:
    """Tests for global configuration management."""

    def setup_method(self):
        """Reset global config before each test."""
        reset_alertmanager_webhook_config()

    def teardown_method(self):
        """Clean up after each test."""
        reset_alertmanager_webhook_config()

    def test_get_config_caches(self):
        """Test that get_config caches the result."""
        config1 = get_alertmanager_webhook_config()
        config2 = get_alertmanager_webhook_config()
        assert config1 is config2

    def test_set_config(self):
        """Test setting global config."""
        custom_config = AlertmanagerWebhookConfig(
            enabled=True,
            bearer_token="custom",
            source_instance="custom-instance",
        )
        set_alertmanager_webhook_config(custom_config)
        config = get_alertmanager_webhook_config()
        assert config is custom_config
        assert config.enabled is True
        assert config.bearer_token == "custom"
