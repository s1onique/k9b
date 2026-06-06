"""Shared structured logging helpers for discovery strategies.

This module provides common utilities for emitting structured log events
during CRD discovery. It avoids circular imports by lazily loading the
structured logging implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


# Lazily initialized emit function to avoid circular imports
_log_emit_fn: Callable[..., dict[str, Any]] | None = None


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
) -> None:
    """Emit a structured WARNING event for discovery strategy failures.

    This function detects Forbidden RBAC errors and marks them as such
    in the structured log metadata, enabling UI counters and alert
    grouping to classify them correctly.

    Args:
        component: The component name (e.g., "alertmanager-discovery")
        strategy_name: The discovery strategy that failed
        errors: Tuple of error strings from the strategy
        cluster_context: Optional cluster context for context tagging
    """
    if not errors:
        return

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
    except Exception:
        # Structured logging failure is non-fatal - callers use module logger as fallback
        pass
