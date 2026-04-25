"""Structured logging helpers for effective scheduler configuration.

This module provides utilities for emitting one-time structured log events
that surface the effective non-secret runtime settings at scheduler startup.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from ..external_analysis.config import ExternalAnalysisSettings
from .loop import HealthRunConfig


def _sanitize_url_for_logging(url: str | None) -> str | None:
    """Strip credentials and query strings from URLs for safe logging.

    Args:
        url: The URL to sanitize

    Returns:
        Sanitized URL with host/port/path only, or None if input is None
    """
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        # Reconstruct with only scheme, host, port, and path
        netloc = parsed.hostname or ""
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        sanitized = f"{parsed.scheme}://{netloc}{parsed.path}"
        return sanitized.rstrip("/")
    except Exception:
        # Fallback: just strip common secret patterns
        result = url
        # Remove common credential patterns
        import re
        result = re.sub(r"(?://)[^/]*:[^/]*@", "//", result)
        # Remove query strings
        result = re.sub(r"\?.*$", "", result)
        return result


def _build_effective_scheduler_config_log(
    config: HealthRunConfig,
    interval_seconds: int | None,
    max_runs: int | None,
    run_once: bool,
) -> dict[str, Any]:
    """Build the effective scheduler configuration log entry.

    This helper extracts safe, non-secret runtime settings for observability.
    It does not change scheduler behavior and avoids forcing side effects.

    Args:
        config: The loaded HealthRunConfig
        interval_seconds: Scheduler interval setting
        max_runs: Maximum runs limit
        run_once: Whether running in single-shot mode

    Returns:
        Dictionary suitable for structured log metadata
    """
    result: dict[str, Any] = {
        "event": "scheduler-config",
        # Core scheduler settings
        "run_label": config.run_label,
        "every_seconds": interval_seconds,
        "runs_dir": str(config.output_dir),
        "max_runs": max_runs,
        "loop_mode": "once" if run_once else "interval",
    }

    # Targets/clusters
    target_count = len(config.targets)
    if target_count > 0:
        result["cluster_count"] = target_count
        target_labels = [t.label for t in config.targets[:5]]  # Limit to 5 for log size
        result["cluster_labels"] = target_labels
        if target_count > 5:
            result["cluster_labels_truncated"] = True

    # External analysis settings
    _add_external_analysis_fields(result, config.external_analysis)

    return result


def _add_external_analysis_fields(
    result: dict[str, Any],
    external_analysis: ExternalAnalysisSettings,
) -> None:
    """Add external analysis fields to the log entry.

    Extracts safe fields without creating network sessions or forcing provider initialization.
    """
    result["external_analysis_enabled"] = any([
        external_analysis.policy.manual,
        external_analysis.policy.degraded_health,
        external_analysis.policy.suspicious_comparison,
    ])

    # Adapter names (safe - no credentials)
    adapter_names = [a.name for a in external_analysis.adapters if a.enabled]
    if adapter_names:
        result["external_analysis_adapters"] = adapter_names

    # Auto drilldown settings
    auto_dd = external_analysis.auto_drilldown
    if auto_dd.enabled:
        result["auto_drilldown_enabled"] = True
        if auto_dd.provider:
            result["auto_drilldown_provider"] = auto_dd.provider
        result["auto_drilldown_max_per_run"] = auto_dd.max_per_run

    # Review enrichment settings
    review = external_analysis.review_enrichment
    if review.enabled:
        result["review_enrichment_enabled"] = True
        if review.provider:
            result["review_enrichment_provider"] = review.provider

    # Alertmanager settings
    _add_alertmanager_fields(result, external_analysis)

    # UI settings
    _add_ui_fields(result)


def _add_alertmanager_fields(
    result: dict[str, Any],
    external_analysis: ExternalAnalysisSettings,
) -> None:
    """Add Alertmanager-related fields to the log entry."""
    am = external_analysis.alertmanager

    # Alertmanager integration enabled
    am_enabled = am.enabled
    if not am_enabled:
        result["alertmanager_enabled"] = False
        return

    result["alertmanager_enabled"] = True

    # Endpoint (sanitized - no credentials)
    if am.endpoint:
        result["alertmanager_endpoint"] = _sanitize_url_for_logging(am.endpoint)

    # Auth info (sanitized)
    if am.auth.has_auth():
        has_bearer = bool(am.auth.bearer_token)
        has_basic = bool(am.auth.username)
        auth_types: list[str] = []
        if has_bearer:
            auth_types.append("bearer")
        if has_basic:
            auth_types.append("basic")
        result["alertmanager_auth"] = auth_types
        # Never log the actual credentials

    result["alertmanager_timeout_seconds"] = am.timeout_seconds
    result["alertmanager_max_alerts_snapshot"] = am.max_alerts_in_snapshot
    result["alertmanager_max_alerts_compact"] = am.max_alerts_in_compact


def _add_ui_fields(result: dict[str, Any]) -> None:
    """Add UI-related fields to the log entry."""
    # Check for UI index generation via environment
    ui_disabled = os.environ.get("HEALTH_DISABLE_UI_INDEX")
    result["ui_index_enabled"] = not _env_is_truthy(ui_disabled)

    # Check for diagnostic pack build trigger
    diag_pack_enabled = os.environ.get("HEALTH_BUILD_DIAGNOSTIC_PACK")
    result["diagnostic_pack_enabled"] = _env_is_truthy(diag_pack_enabled)


def _env_is_truthy(value: str | None) -> bool:
    """Check if an environment variable is set to a truthy value."""
    if not value:
        return False
    return value.strip().lower() in ("true", "1", "yes")


def _log_effective_scheduler_config(
    config: HealthRunConfig,
    interval_seconds: int | None,
    max_runs: int | None,
    run_once: bool,
    log_fn: Callable[..., None],
) -> None:
    """Emit the effective scheduler configuration log event.

    This function should be called once at scheduler startup, after config
    has been resolved but before the first run begins.

    Args:
        config: The loaded HealthRunConfig
        interval_seconds: Scheduler interval setting
        max_runs: Maximum runs limit
        run_once: Whether running in single-shot mode
        log_fn: Function to call for logging (e.g., scheduler._log_event)
    """
    metadata = _build_effective_scheduler_config_log(
        config=config,
        interval_seconds=interval_seconds,
        max_runs=max_runs,
        run_once=run_once,
    )

    # Extend with llama.cpp-specific settings if available in environment
    _add_llamacpp_fields(metadata)

    log_fn(
        "INFO",
        "Effective scheduler config",
        **metadata,
    )


def _add_llamacpp_fields(metadata: dict[str, Any]) -> None:
    """Add llama.cpp configuration fields from environment if available.

    Uses LlamaCppProviderConfig.from_env() to parse effective config including defaults.
    This is pure parsing - no network sessions or provider initialization.

    Args:
        metadata: Dictionary to extend with llama.cpp fields
    """
    from ..llm.llamacpp_provider import LlamaCppProviderConfig

    base_url = os.environ.get("LLAMA_CPP_BASE_URL")
    model = os.environ.get("LLAMA_CPP_MODEL")

    # Only include llama.cpp section if both required env vars are present
    if not base_url or not model:
        return

    try:
        # Use from_env to get effective config including defaults
        # This is pure parsing - no network calls
        llamacpp_config = LlamaCppProviderConfig.from_env(dict(os.environ))
    except RuntimeError:
        # Missing required env vars - skip logging
        return

    metadata["llamacpp_enabled"] = True
    metadata["llamacpp_base_url"] = _sanitize_url_for_logging(llamacpp_config.base_url)
    metadata["llamacpp_model"] = llamacpp_config.model

    # Always log effective values (including defaults)
    metadata["llamacpp_timeout_seconds"] = llamacpp_config.timeout_seconds
    metadata["llamacpp_max_tokens_auto_drilldown"] = llamacpp_config.max_tokens_auto_drilldown
    metadata["llamacpp_max_tokens_review_enrichment"] = llamacpp_config.max_tokens_review_enrichment
    metadata["llamacpp_response_format_json"] = llamacpp_config.response_format_json

    # Generation settings for structured JSON output
    metadata["llamacpp_temperature"] = llamacpp_config.temperature
    if llamacpp_config.top_p is not None:
        metadata["llamacpp_top_p"] = llamacpp_config.top_p
    if llamacpp_config.top_k is not None:
        metadata["llamacpp_top_k"] = llamacpp_config.top_k
    if llamacpp_config.repeat_penalty is not None:
        metadata["llamacpp_repeat_penalty"] = llamacpp_config.repeat_penalty
    if llamacpp_config.seed is not None:
        metadata["llamacpp_seed"] = llamacpp_config.seed
    if llamacpp_config.stop is not None:
        metadata["llamacpp_stop_count"] = len(llamacpp_config.stop)
    metadata["llamacpp_enable_thinking"] = llamacpp_config.enable_thinking

    # API key presence indicator (never log the actual key)
    if llamacpp_config.api_key:
        metadata["llamacpp_has_api_key"] = True
