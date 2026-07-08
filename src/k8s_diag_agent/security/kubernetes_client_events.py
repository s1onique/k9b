"""Event reading helpers for Kubernetes client."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .kubernetes_client_constants import DEFAULT_LIMIT, DEFAULT_MAX_ITEMS
from .kubernetes_client_event_models import EventProjection
from .kubernetes_client_pagination_models import PaginationMetadata

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

# Sentinel datetime for sorting events with no timestamp
_MIN_DATETIME = datetime.min.replace(tzinfo=UTC) if hasattr(datetime, "min") else None


def list_namespaced_events_projected(
    core_v1: Any,
    *,
    namespace: str,
    timeout_seconds: int,
    field_selector: str | None = None,
    limit: int = DEFAULT_LIMIT,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> tuple[list[EventProjection], PaginationMetadata]:
    """List events in a namespace with pagination."""
    all_events: list[EventProjection] = []
    continue_token: str | None = None
    remaining = 0
    truncated = False

    while True:
        try:
            response = core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector=field_selector,
                limit=limit,
                _continue=continue_token,
                _request_timeout=timeout_seconds,
            )
            for item in response.items:
                if len(all_events) >= max_items:
                    truncated = True
                    remaining = response.metadata.remaining_item_count or 0
                    break
                all_events.append(EventProjection.from_dict(item.to_dict()))
            if truncated:
                break
            continue_token = response.metadata._continue
            if not continue_token:
                break
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to list events in %s: %s", namespace, type(exc).__name__)
            break

    return all_events, PaginationMetadata(
        total=len(all_events),
        remaining=remaining,
        truncated=truncated,
        continuation_token=continue_token,
        items_returned=len(all_events),
    )


def list_warning_events_for_all_namespaces(
    core_v1: Any,
    *,
    timeout_seconds: int,
    limit: int,
) -> list[EventProjection]:
    """List warning events across all namespaces with the Python client."""
    max_collect = min(limit * 20, DEFAULT_MAX_ITEMS)

    all_events: list[Any] = []
    continue_token: str | None = None

    while len(all_events) < max_collect:
        page_size = min(limit * 5, max_collect - len(all_events))
        response = core_v1.list_event_for_all_namespaces(
            field_selector="type=Warning",
            limit=page_size,
            _continue=continue_token,
            _request_timeout=timeout_seconds,
        )
        if response.items:
            all_events.extend(response.items)
        continue_token = (
            response.metadata._continue
            if hasattr(response.metadata, "_continue")
            else None
        )
        if not continue_token:
            break

    def _event_sort_key(e: Any) -> Any:
        ts = e.last_timestamp or e.event_time
        if ts is None and e.metadata:
            ts = e.metadata.creation_timestamp
        return ts if ts is not None else _MIN_DATETIME

    all_events.sort(key=_event_sort_key, reverse=True)
    return [EventProjection.from_dict(e.to_dict()) for e in all_events[:limit]]


__all__ = [
    "list_namespaced_events_projected",
    "list_warning_events_for_all_namespaces",
]
