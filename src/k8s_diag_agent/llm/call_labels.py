"""LLM call labeling for structured observability.

This module provides stable, deterministic call IDs for correlating
scheduler-time LLM calls in logs and artifacts.

Call ID format:
- auto-drilldown: {run_id}:{cluster_label}:auto-drilldown:{provider}
- review-enrichment: {run_id}:review-enrichment:{provider}
"""
from __future__ import annotations


def build_llm_call_id(
    run_id: str,
    operation: str,
    provider: str,
    *,
    cluster_label: str | None = None,
) -> str:
    """Build a deterministic LLM call ID.

    Args:
        run_id: The run identifier
        operation: The operation type ("auto-drilldown" or "review-enrichment")
        provider: The LLM provider name (e.g., "llamacpp")
        cluster_label: The cluster label for auto-drilldown (required for that operation)

    Returns:
        A deterministic call ID string

    Raises:
        ValueError: If cluster_label is missing for auto-drilldown operation
    """
    if operation == "auto-drilldown":
        if not cluster_label:
            raise ValueError("cluster_label is required for auto-drilldown call ID")
        return f"{run_id}:{cluster_label}:auto-drilldown:{provider}"
    elif operation == "review-enrichment":
        return f"{run_id}:review-enrichment:{provider}"
    else:
        # Generic format for other operations
        if cluster_label:
            return f"{run_id}:{cluster_label}:{operation}:{provider}"
        return f"{run_id}:{operation}:{provider}"


__all__ = ["build_llm_call_id"]