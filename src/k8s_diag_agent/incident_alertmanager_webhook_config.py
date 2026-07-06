"""Configuration for Alertmanager webhook ingestion.

This module provides configuration for the Alertmanager webhook endpoint
that accepts and normalizes Alertmanager notification payloads.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Default constants
DEFAULT_ENABLED = False
DEFAULT_SOURCE_INSTANCE = "alertmanager-main"
DEFAULT_MAX_PAYLOAD_BYTES = 262144  # 256 KiB


@dataclass(frozen=True)
class AlertmanagerWebhookConfig:
    """Configuration for Alertmanager webhook ingestion.

    This configuration controls:
    - Whether the webhook endpoint is enabled (fail-closed by default)
    - Bearer token authentication (required when enabled)
    - Source instance identifier
    - Payload size limits

    Design principles:
    - Fail-closed by default (disabled unless explicitly enabled)
    - Token file takes precedence over inline token
    - Never log or persist token values
    """
    # Whether the webhook endpoint is enabled
    enabled: bool = DEFAULT_ENABLED

    # Bearer token for authentication (if enabled)
    bearer_token: str | None = None

    # Source instance identifier for normalized signals
    source_instance: str = DEFAULT_SOURCE_INSTANCE

    # Maximum payload size in bytes
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES

    def is_authenticated(self) -> bool:
        """Return True if authentication is configured.

        Authentication is considered configured if a bearer token is set.
        """
        return bool(self.bearer_token)

    def requires_auth(self) -> bool:
        """Return True if authentication is required.

        Authentication is required when the webhook is enabled.
        If enabled but no token is configured, requests should be rejected fail-closed.
        """
        return self.enabled


def parse_alertmanager_webhook_config(
    env_prefix: str = "K9B_ALERTMANAGER_WEBHOOK_",
) -> AlertmanagerWebhookConfig:
    """Parse Alertmanager webhook configuration from environment variables.

    Environment variables:
        K9B_ALERTMANAGER_WEBHOOK_ENABLED: "true" or "false" (default: false)
        K9B_ALERTMANAGER_WEBHOOK_TOKEN: Inline bearer token
        K9B_ALERTMANAGER_WEBHOOK_TOKEN_FILE: Path to file containing bearer token
        K9B_ALERTMANAGER_WEBHOOK_SOURCE_INSTANCE: Source instance identifier
        K9B_ALERTMANAGER_WEBHOOK_MAX_PAYLOAD_BYTES: Maximum payload size in bytes

    Priority: token file wins over inline token.

    Args:
        env_prefix: Environment variable prefix (default: K9B_ALERTMANAGER_WEBHOOK_)

    Returns:
        AlertmanagerWebhookConfig with parsed values
    """
    # Parse enabled
    enabled_raw = os.environ.get(f"{env_prefix}ENABLED", "").lower()
    enabled = enabled_raw in ("true", "1", "yes")

    # Parse token - file wins over inline
    bearer_token: str | None = None

    # Check token file first
    token_file_path = os.environ.get(f"{env_prefix}TOKEN_FILE")
    if token_file_path:
        token_file = Path(token_file_path)
        if token_file.exists():
            bearer_token = token_file.read_text().strip()

    # Fall back to inline token if no file token
    if not bearer_token:
        inline_token = os.environ.get(f"{env_prefix}TOKEN", "")
        if inline_token:
            bearer_token = inline_token

    # Parse source instance
    source_instance = os.environ.get(
        f"{env_prefix}SOURCE_INSTANCE",
        DEFAULT_SOURCE_INSTANCE,
    )

    # Parse max payload bytes
    max_payload_bytes_str = os.environ.get(f"{env_prefix}MAX_PAYLOAD_BYTES", "")
    if max_payload_bytes_str:
        try:
            max_payload_bytes = int(max_payload_bytes_str)
            # Sanity check: must be positive
            if max_payload_bytes <= 0:
                max_payload_bytes = DEFAULT_MAX_PAYLOAD_BYTES
        except ValueError:
            max_payload_bytes = DEFAULT_MAX_PAYLOAD_BYTES
    else:
        max_payload_bytes = DEFAULT_MAX_PAYLOAD_BYTES

    return AlertmanagerWebhookConfig(
        enabled=enabled,
        bearer_token=bearer_token,
        source_instance=source_instance,
        max_payload_bytes=max_payload_bytes,
    )


# Global config instance (lazy-loaded)
_config: AlertmanagerWebhookConfig | None = None


def get_alertmanager_webhook_config() -> AlertmanagerWebhookConfig:
    """Get the global Alertmanager webhook configuration.

    Configuration is parsed once on first access and cached.

    Returns:
        AlertmanagerWebhookConfig instance
    """
    global _config
    if _config is None:
        _config = parse_alertmanager_webhook_config()
    return _config


def reset_alertmanager_webhook_config() -> None:
    """Reset the global configuration (for testing).

    This allows tests to inject different configuration without
    affecting the global state.
    """
    global _config
    _config = None


def set_alertmanager_webhook_config(config: AlertmanagerWebhookConfig) -> None:
    """Set the global Alertmanager webhook configuration (for testing).

    Args:
        config: The configuration to set
    """
    global _config
    _config = config


__all__ = [
    "AlertmanagerWebhookConfig",
    "parse_alertmanager_webhook_config",
    "get_alertmanager_webhook_config",
    "reset_alertmanager_webhook_config",
    "set_alertmanager_webhook_config",
    "DEFAULT_ENABLED",
    "DEFAULT_SOURCE_INSTANCE",
    "DEFAULT_MAX_PAYLOAD_BYTES",
]
