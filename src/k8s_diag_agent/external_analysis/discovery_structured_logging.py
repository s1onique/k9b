"""Shared structured logging helpers for discovery strategies.

This module provides common utilities for emitting structured log events
during CRD discovery. It avoids circular imports by lazily loading the
structured logging implementation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


# Lazily initialized emit function to avoid circular imports
_log_emit_fn: Callable[..., dict[str, Any]] | None = None

# Module logger for fallback diagnostics
_logger = logging.getLogger(__name__)


def _get_emit_fn() -> Callable[..., dict[str, Any]]:
    """Get the structured log emit function lazily.

    Returns:
        The emit_structured_log function from structured_logging module.
    """
    global _log_emit_fn
    if _log_emit_fn is None:
        from ..structured_logging import emit_structured_log
        _log_emit_fn = emit_structured_log
    return _log_emit_fn


def emit_discovery_strategy_failure(
    component: str,
    strategy_name: str,
    errors: tuple[str, ...],
    cluster_context: str | None = None,
) -> bool:
    """Emit a structured WARNING event for discovery strategy failures.

    This function detects Forbidden RBAC errors and marks them as such
    in the structured log metadata, enabling UI counters and alert
    grouping to classify them correctly.

    Args:
        component: The component name (e.g., "alertmanager-discovery")
        strategy_name: The discovery strategy that failed
        errors: Tuple of error strings from the strategy
        cluster_context: Optional cluster context for context tagging

    Returns:
        True if structured emission succeeded, False otherwise.
        When emission fails, discovery callers continue safely.
    """
    if not errors:
        return False

    # Determine if this is a Forbidden RBAC error
    # Forbidden errors indicate degraded discovery capability, not complete failure
    is_forbidden = any("forbidden" in e.lower() for e in errors)

    # Build structured metadata for the error event
    metadata = {
        "event": f"{component}-strategy-failed",
        "strategy": strategy_name,
        "error_count": len(errors),
        "reason": "forbidden" if is_forbidden else "kubectl-error",
    }

    if cluster_context:
        metadata["cluster_context"] = cluster_context

    # Emit structured log for the strategy failure
    try:
        emit_fn = _get_emit_fn()
        emit_fn(
            component=component,
            message=f"{component.replace('-', ' ').title()} strategy {strategy_name} completed with errors",
            run_label="",
            severity="WARNING",
            metadata=metadata,
        )
        return True
    except Exception as exc:
        # Bounded fallback: emit sanitized DEBUG diagnostic.
        # Do NOT interpolate raw error strings, exception repr, or Forbidden text.
        _logger.debug(
            "Discovery structured log emission failed for component=%s strategy=%s error_count=%s exception_type=%s",
            component,
            strategy_name,
            len(errors),
            type(exc).__name__,
        )
        return False


def safe_emit_discovery_failure(
    component: str,
    strategy_name: str,
    errors: tuple[str, ...],
    cluster_context: str | None = None,
) -> None:
    """Safely emit discovery strategy failure without leaking sensitive error text.

    This wrapper ensures that structured logging failures cannot leak raw
    kubectl/Forbidden/cluster error text through fallback exception paths.

    The function silently suppresses emitter failures and does NOT log exception
    text or raw error payloads. This prevents information disclosure when the
    structured logging system itself fails.

    Args:
        component: The component name (e.g., "alertmanager-discovery")
        strategy_name: The discovery strategy that failed
        errors: Tuple of error strings from the strategy
        cluster_context: Optional cluster context for context tagging
    """
    try:
        emit_discovery_strategy_failure(
            component=component,
            strategy_name=strategy_name,
            errors=errors,
            cluster_context=cluster_context,
        )
    except Exception:
        # Bounded fallback: catch any exception from emit_discovery_strategy_failure
        # to ensure discovery callers never fail due to structured log emission.
        # The inner emit already sanitized its fallback, so no raw text to leak here.
        pass
