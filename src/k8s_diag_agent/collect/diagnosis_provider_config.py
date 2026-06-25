"""Configuration for diagnosis provider runtime settings.

This module provides a bounded config object for diagnosis provider runtime settings
used by the incident one-pass diagnosis service.

Design constraints:
- Required fields are explicit (provider_name, model, base_url)
- Secrets come from environment variables
- Missing required config fails closed
- Unsupported provider_name fails closed
- Timeout is bounded (1-300 seconds)
- Output size is bounded (100-100000 chars)

Secret injection model:
- When using Helm secretKeyRef, K9B_DIAGNOSIS_API_KEY contains the raw secret value
  directly (Kubernetes injects the Secret key value as the env var value).
- The get_api_key() method returns the raw value directly.
- to_safe_dict() never includes the raw API key value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# Default bounds
DEFAULT_TIMEOUT_SECONDS = 120
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 300

DEFAULT_MAX_OUTPUT_CHARS = 50000
MIN_MAX_OUTPUT_CHARS = 100
MAX_MAX_OUTPUT_CHARS = 100000

# Environment variable names for diagnosis provider
ENV_DIAGNOSIS_PROVIDER_NAME = "K9B_DIAGNOSIS_PROVIDER_NAME"
ENV_DIAGNOSIS_MODEL = "K9B_DIAGNOSIS_MODEL"
ENV_DIAGNOSIS_BASE_URL = "K9B_DIAGNOSIS_BASE_URL"
ENV_DIAGNOSIS_API_KEY = "K9B_DIAGNOSIS_API_KEY"
ENV_DIAGNOSIS_TIMEOUT = "K9B_DIAGNOSIS_TIMEOUT_SECONDS"
ENV_DIAGNOSIS_MAX_OUTPUT = "K9B_DIAGNOSIS_MAX_OUTPUT_CHARS"

# Supported provider names
SUPPORTED_PROVIDERS = frozenset({"openai_compatible", "gigachat", "qwen"})


@dataclass(frozen=True)
class DiagnosisProviderConfig:
    """Bounded config object for diagnosis provider runtime settings.

    When using Helm secretKeyRef, K9B_DIAGNOSIS_API_KEY contains the raw secret value
    directly (Kubernetes injects the Secret key value as the env var value).
    """

    provider_name: str
    model: str
    base_url: str
    _api_key: str | None = None  # Raw API key value (not env var name)
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        required: bool = False,
    ) -> DiagnosisProviderConfig | None:
        """Parse diagnosis provider config from environment variables.

        Args:
            env: Environment variables dict (defaults to os.environ)
            required: If True, raises RuntimeError on missing required fields.
                     If False, returns None when required fields are missing.

        Returns:
            DiagnosisProviderConfig instance, or None if not configured.

        Raises:
            RuntimeError: If required=True and required fields are missing.
            ValueError: If timeout or max_output_chars are out of bounds.
        """
        source: dict[str, str] = dict(env) if env is not None else dict(os.environ)

        provider_name = source.get(ENV_DIAGNOSIS_PROVIDER_NAME, "").strip()
        model = source.get(ENV_DIAGNOSIS_MODEL, "").strip()
        base_url = source.get(ENV_DIAGNOSIS_BASE_URL, "").strip()
        api_key = source.get(ENV_DIAGNOSIS_API_KEY, "").strip() or None

        # Check required fields
        missing: list[str] = []
        if not provider_name:
            missing.append(ENV_DIAGNOSIS_PROVIDER_NAME)
        if not model:
            missing.append(ENV_DIAGNOSIS_MODEL)
        if not base_url:
            missing.append(ENV_DIAGNOSIS_BASE_URL)

        if missing:
            if required:
                raise RuntimeError(
                    f"Missing required diagnosis provider environment variables: {', '.join(missing)}. "
                    f"Set K9B_DIAGNOSIS_PROVIDER_NAME, K9B_DIAGNOSIS_MODEL, and K9B_DIAGNOSIS_BASE_URL "
                    f"to configure the diagnosis provider."
                )
            return None

        # Validate provider name
        normalized_provider = provider_name.lower()
        if normalized_provider not in SUPPORTED_PROVIDERS:
            if required:
                supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
                raise ValueError(
                    f"Unsupported diagnosis provider '{provider_name}'. "
                    f"Supported providers: {supported}"
                )
            return None

        # Parse timeout with bounds
        timeout_str = source.get(ENV_DIAGNOSIS_TIMEOUT, "").strip()
        timeout_seconds = cls._parse_timeout(timeout_str)

        # Parse max_output_chars with bounds
        max_output_str = source.get(ENV_DIAGNOSIS_MAX_OUTPUT, "").strip()
        max_output_chars = cls._parse_max_output(max_output_str)

        return cls(
            provider_name=normalized_provider,
            model=model,
            base_url=base_url,
            _api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_output_chars=max_output_chars,
        )

    @staticmethod
    def _parse_timeout(value: str | None) -> int:
        """Parse timeout with bounds."""
        if not value or not value.strip():
            return DEFAULT_TIMEOUT_SECONDS
        try:
            parsed = int(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"{ENV_DIAGNOSIS_TIMEOUT} must be an integer but got '{value}'"
            ) from exc
        if parsed < MIN_TIMEOUT_SECONDS or parsed > MAX_TIMEOUT_SECONDS:
            raise ValueError(
                f"{ENV_DIAGNOSIS_TIMEOUT} must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds, "
                f"got {parsed}"
            )
        return parsed

    @staticmethod
    def _parse_max_output(value: str | None) -> int:
        """Parse max_output_chars with bounds."""
        if not value or not value.strip():
            return DEFAULT_MAX_OUTPUT_CHARS
        try:
            parsed = int(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"{ENV_DIAGNOSIS_MAX_OUTPUT} must be an integer but got '{value}'"
            ) from exc
        if parsed < MIN_MAX_OUTPUT_CHARS or parsed > MAX_MAX_OUTPUT_CHARS:
            raise ValueError(
                f"{ENV_DIAGNOSIS_MAX_OUTPUT} must be between {MIN_MAX_OUTPUT_CHARS} and {MAX_MAX_OUTPUT_CHARS}, "
                f"got {parsed}"
            )
        return parsed

    def get_api_key(self) -> str | None:
        """Get the configured API key.

        Returns:
            The raw API key value, or None if not configured.
            When using Helm secretKeyRef, K9B_DIAGNOSIS_API_KEY contains the raw secret.
        """
        return self._api_key

    def to_safe_dict(self) -> dict[str, Any]:
        """Convert to dict for logging without raw secrets.

        Returns:
            Dict with safe metadata (no API key values, no raw base_url).
        """
        return {
            "provider_name": self.provider_name,
            "model": self.model,
            "base_url_present": bool(self.base_url),
            "api_key_present": self._api_key is not None,
            "timeout_seconds": self.timeout_seconds,
            "max_output_chars": self.max_output_chars,
        }


__all__ = [
    "DiagnosisProviderConfig",
    "DEFAULT_TIMEOUT_SECONDS",
    "MIN_TIMEOUT_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "DEFAULT_MAX_OUTPUT_CHARS",
    "MIN_MAX_OUTPUT_CHARS",
    "MAX_MAX_OUTPUT_CHARS",
    "SUPPORTED_PROVIDERS",
    "ENV_DIAGNOSIS_PROVIDER_NAME",
    "ENV_DIAGNOSIS_MODEL",
    "ENV_DIAGNOSIS_BASE_URL",
    "ENV_DIAGNOSIS_API_KEY",
    "ENV_DIAGNOSIS_TIMEOUT",
    "ENV_DIAGNOSIS_MAX_OUTPUT",
]
