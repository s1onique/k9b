"""Configuration for Alertmanager external signal integration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AlertmanagerAuth:
    """Authentication settings for Alertmanager."""
    bearer_token: str | None = None
    username: str | None = None
    password: str | None = None

    def has_auth(self) -> bool:
        return bool(self.bearer_token) or bool(self.username)


@dataclass(frozen=True)
class AlertmanagerConfig:
    """Configuration for Alertmanager integration."""
    enabled: bool = True
    endpoint: str | None = None
    timeout_seconds: float = 10.0
    auth: AlertmanagerAuth = field(default_factory=AlertmanagerAuth)
    max_alerts_in_snapshot: int = 200
    max_alerts_in_compact: int = 20
    max_string_length: int = 200

    def is_configured(self) -> bool:
        return bool(self.endpoint)


def parse_alertmanager_auth(raw: Mapping[str, Any] | None) -> AlertmanagerAuth:
    """Parse Alertmanager authentication settings."""
    if not isinstance(raw, Mapping):
        return AlertmanagerAuth()
    return AlertmanagerAuth(
        bearer_token=str(raw.get("bearer_token")) if raw.get("bearer_token") else None,
        username=str(raw.get("username")) if raw.get("username") else None,
        password=str(raw.get("password")) if raw.get("password") else None,
    )


def parse_alertmanager_config(raw: Mapping[str, Any] | None) -> AlertmanagerConfig:
    """Parse Alertmanager configuration from raw dict."""
    if not isinstance(raw, Mapping):
        return AlertmanagerConfig()
    enabled = bool(raw.get("enabled", True))
    endpoint = str(raw.get("endpoint")) if raw.get("endpoint") else None
    timeout_raw = raw.get("timeout_seconds")
    timeout_seconds = 10.0
    if isinstance(timeout_raw, (int, float)):
        timeout_seconds = max(1.0, float(timeout_raw))
    elif isinstance(timeout_raw, str):
        try:
            timeout_seconds = max(1.0, float(timeout_raw))
        except ValueError:
            timeout_seconds = 10.0
    auth = parse_alertmanager_auth(raw.get("auth"))
    max_alerts_raw = raw.get("max_alerts_in_snapshot")
    max_alerts_in_snapshot = 200
    if isinstance(max_alerts_raw, int) and max_alerts_raw > 0:
        max_alerts_in_snapshot = max_alerts_raw
    max_compact_raw = raw.get("max_alerts_in_compact")
    max_alerts_in_compact = 20
    if isinstance(max_compact_raw, int) and max_compact_raw > 0:
        max_alerts_in_compact = max_compact_raw
    max_string_raw = raw.get("max_string_length")
    max_string_length = 200
    if isinstance(max_string_raw, int) and max_string_raw > 0:
        max_string_length = max_string_raw
    return AlertmanagerConfig(
        enabled=enabled,
        endpoint=endpoint,
        timeout_seconds=timeout_seconds,
        auth=auth,
        max_alerts_in_snapshot=max_alerts_in_snapshot,
        max_alerts_in_compact=max_alerts_in_compact,
        max_string_length=max_string_length,
    )