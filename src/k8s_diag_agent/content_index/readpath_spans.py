"""Content index read path span recording helpers.

This module provides functions for recording OTel spans during content index
read operations.

Schema Version: k9b.content_index.v1

Ownership:
    - record_fallback_span: Record a fallback span with reason attributes
    - record_success_span: Record a successful index read span
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


# =============================================================================
# Span Attribute Helpers
# =============================================================================


def record_fallback_span(
    span_name: str,
    reason: str,
    enabled: bool,
    schema_version: str | None = None,
) -> None:
    """Record a fallback span with appropriate attributes.

    Args:
        span_name: Name of the span (e.g., "k9b.content_index.fallback").
        reason: Bounded fallback reason code.
        enabled: Whether index was enabled.
        schema_version: Schema version from index if available.
    """
    from ..observability.internal_spans import internal_span

    attrs: dict[str, str | bool] = {
        "k9b.content_index.enabled": str(enabled),
        "k9b.content_index.available": "false",
        "k9b.content_index.fallback.reason": reason,
    }
    if schema_version:
        attrs["k9b.content_index.schema_version"] = schema_version

    with internal_span(span_name, attributes=attrs):
        pass


def record_success_span(
    span_name: str,
    enabled: bool,
    schema_version: str,
    count: int,
) -> None:
    """Record a successful index read span.

    Args:
        span_name: Name of the span (e.g., "k9b.content_index.project_response").
        enabled: Whether index was enabled.
        schema_version: Schema version from index.
        count: Number of items returned.
    """
    from ..observability.internal_spans import internal_span

    attrs: dict[str, str | bool | int] = {
        "k9b.content_index.enabled": str(enabled),
        "k9b.content_index.available": "true",
        "k9b.content_index.schema_version": schema_version,
        "k9b.result.count": count,
    }

    with internal_span(span_name, attributes=attrs):
        pass
