"""Dependency injection provider for incident one-pass diagnosis service.

This module provides a registry for injectable dependencies used by the
HTTP API route handler. Tests can override these to inject fake providers,
handlers, and artifact writers without modifying the handler code.

Production default: All providers return None, causing fail-closed behavior
if no LLM provider is configured.

For production, call init_production_diagnosis_provider() during backend startup
to wire the real OpenAI-compatible diagnosis provider from environment config.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .incident_diagnosis_service import ArtifactWriter, DiagnosisProvider
    from .incident_read_only_check_runner import ReadOnlyCheckHandler

logger = logging.getLogger(__name__)

# Global provider registry
_diagnosis_provider: DiagnosisProvider | None = None
_fake_handlers: dict[str, ReadOnlyCheckHandler] | None = None
_artifact_writer: ArtifactWriter | None = None
_golden_case_mode: bool = False
_golden_case_manifest: dict[str, Any] | None = None
_golden_case_case_dir: Path | None = None
_golden_case_evidence_provider: Any = None
_production_provider_init_attempted: bool = False


def get_diagnosis_provider() -> DiagnosisProvider | None:
    """Get the current diagnosis provider."""
    return _diagnosis_provider


def set_diagnosis_provider(provider: DiagnosisProvider | None) -> None:
    """Set a custom diagnosis provider (for testing)."""
    global _diagnosis_provider
    _diagnosis_provider = provider


def get_fake_handlers() -> dict[str, ReadOnlyCheckHandler] | None:
    """Get the current fake handlers."""
    return _fake_handlers


def set_fake_handlers(handlers: dict[str, ReadOnlyCheckHandler] | None) -> None:
    """Set custom fake handlers (for testing)."""
    global _fake_handlers
    _fake_handlers = handlers


def get_artifact_writer() -> ArtifactWriter | None:
    """Get the current artifact writer."""
    return _artifact_writer


def set_artifact_writer(writer: ArtifactWriter | None) -> None:
    """Set a custom artifact writer (for testing)."""
    global _artifact_writer
    _artifact_writer = writer


def is_golden_case_mode() -> bool:
    """Get whether golden-case mode is enabled."""
    return _golden_case_mode


def get_golden_case_manifest() -> dict[str, Any] | None:
    """Get the golden-case manifest (if in golden-case mode)."""
    return _golden_case_manifest


def get_golden_case_case_dir() -> Path | None:
    """Get the golden-case case directory (if in golden-case mode)."""
    return _golden_case_case_dir


def get_golden_case_evidence_provider() -> Any:
    """Get the golden-case evidence provider (if in golden-case mode)."""
    return _golden_case_evidence_provider


def set_golden_case_context(
    enabled: bool,
    manifest: dict[str, Any] | None = None,
    case_dir: Path | None = None,
    evidence_provider: Any = None,
) -> None:
    """Set golden-case context for ACT-local verification.

    Args:
        enabled: Whether golden-case mode is enabled
        manifest: Golden-case manifest dict
        case_dir: Path to golden-case fixture directory
        evidence_provider: Golden-case evidence provider instance
    """
    global _golden_case_mode, _golden_case_manifest, _golden_case_case_dir, _golden_case_evidence_provider
    _golden_case_mode = enabled
    _golden_case_manifest = manifest
    _golden_case_case_dir = case_dir
    _golden_case_evidence_provider = evidence_provider


def reset_providers() -> None:
    """Reset all providers to default (None)."""
    global _diagnosis_provider, _fake_handlers, _artifact_writer
    global _golden_case_mode, _golden_case_manifest, _golden_case_case_dir, _golden_case_evidence_provider
    global _production_provider_init_attempted
    _diagnosis_provider = None
    _fake_handlers = None
    _artifact_writer = None
    _golden_case_mode = False
    _golden_case_manifest = None
    _golden_case_case_dir = None
    _golden_case_evidence_provider = None
    _production_provider_init_attempted = False


def init_production_diagnosis_provider() -> bool:
    """Initialize production diagnosis provider from environment config.

    This function should be called during backend startup to wire the real
    OpenAI-compatible diagnosis provider from environment variables.

    The following environment variables are required:
    - K9B_DIAGNOSIS_PROVIDER_NAME: Provider name (openai_compatible, gigachat, qwen)
    - K9B_DIAGNOSIS_MODEL: Model name
    - K9B_DIAGNOSIS_BASE_URL: Base URL for the provider API

    Optional environment variables:
    - K9B_DIAGNOSIS_API_KEY: Raw API key value (injected via secretKeyRef or set directly)
    - K9B_DIAGNOSIS_TIMEOUT_SECONDS: Request timeout (1-300, default 120)
    - K9B_DIAGNOSIS_MAX_OUTPUT_CHARS: Max output chars (100-100000, default 50000)

    Returns:
        True if provider was initialized, False if not configured.

    Logs:
        - WARNING if provider is not configured (not an error, allows fail-closed behavior)
        - INFO with safe config metadata on successful initialization
    """
    global _diagnosis_provider, _production_provider_init_attempted

    if _production_provider_init_attempted:
        # Already attempted, return current state
        return _diagnosis_provider is not None

    _production_provider_init_attempted = True

    # Import here to avoid circular dependencies
    from .diagnosis_provider_config import DiagnosisProviderConfig
    from .diagnosis_provider_runtime import build_diagnosis_provider_from_config

    # Parse config from environment
    try:
        config = DiagnosisProviderConfig.from_env(required=False)
    except (RuntimeError, ValueError) as exc:
        logger.warning(
            "Failed to parse diagnosis provider config: %s",
            exc,
        )
        return False

    if config is None:
        logger.debug(
            "Diagnosis provider not configured (K9B_DIAGNOSIS_PROVIDER_NAME, "
            "K9B_DIAGNOSIS_MODEL, or K9B_DIAGNOSIS_BASE_URL not set)"
        )
        return False

    # Build provider from config
    try:
        inner_provider = build_diagnosis_provider_from_config(config)
    except ValueError as exc:
        logger.warning(
            "Failed to build diagnosis provider: %s",
            exc,
        )
        return False

    if inner_provider is None:
        logger.debug("Diagnosis provider build returned None")
        return False

    # Wrap with invocation tracking for live-lab smoke testing
    # This allows the service to prove provider.complete() was actually called
    from .diagnosis_provider_runtime import InvocationTrackingDiagnosisProvider

    provider = InvocationTrackingDiagnosisProvider(inner_provider)

    # Register provider
    _diagnosis_provider = provider
    safe_config = config.to_safe_dict()
    # Log with base_url_present instead of raw base_url for security
    logger.info(
        "Production diagnosis provider initialized: provider=%s model=%s base_url_present=%s "
        "timeout=%ds api_key_present=%s",
        safe_config["provider_name"],
        safe_config["model"],
        safe_config.get("base_url_present", False),
        safe_config["timeout_seconds"],
        safe_config["api_key_present"],
    )

    return True


def is_production_provider_initialized() -> bool:
    """Check if production provider initialization was attempted.

    Returns:
        True if init_production_diagnosis_provider() was called.
    """
    return _production_provider_init_attempted


def get_provider_config_status() -> dict[str, Any]:
    """Get safe provider configuration status for diagnostics.

    Returns:
        Dict with safe configuration metadata (no raw secrets, no raw base_url).
    """
    from .diagnosis_provider_config import DiagnosisProviderConfig

    try:
        config = DiagnosisProviderConfig.from_env(required=False)
    except (RuntimeError, ValueError):
        return {
            "config_present": False,
            "config_error": True,
        }

    if config is None:
        return {
            "config_present": False,
        }

    return {
        "config_present": True,
        "provider_name": config.provider_name,
        "model": config.model,
        # Redact base_url - only indicate presence for security
        "base_url_present": config.base_url is not None and len(config.base_url) > 0,
        "api_key_present": config.get_api_key() is not None,
        "timeout_seconds": config.timeout_seconds,
        "max_output_chars": config.max_output_chars,
    }


__all__ = [
    "get_diagnosis_provider",
    "set_diagnosis_provider",
    "get_fake_handlers",
    "set_fake_handlers",
    "get_artifact_writer",
    "set_artifact_writer",
    "is_golden_case_mode",
    "get_golden_case_manifest",
    "get_golden_case_case_dir",
    "get_golden_case_evidence_provider",
    "set_golden_case_context",
    "reset_providers",
    "init_production_diagnosis_provider",
    "is_production_provider_initialized",
    "get_provider_config_status",
]
