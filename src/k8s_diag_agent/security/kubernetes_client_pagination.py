"""Pagination helpers for Kubernetes client."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .kubernetes_client_constants import DEFAULT_LIMIT, DEFAULT_MAX_ITEMS
from .kubernetes_client_errors import KubernetesApiResponseTooLargeError
from .kubernetes_client_models import DeploymentProjection, EventProjection, PaginationMetadata, PodProjection

if TYPE_CHECKING:
    from .kubernetes_client import KubernetesReadClient

_logger = logging.getLogger(__name__)


def _check_response_size(client: KubernetesReadClient, response: Any) -> None:
    """Check if response exceeds size limits."""
    try:
        serialized = json.dumps(response.to_dict())
        size = len(serialized.encode("utf-8"))
        if size > client._max_response_bytes:
            raise KubernetesApiResponseTooLargeError(
                f"Response too large: {size} bytes exceeds limit of {client._max_response_bytes}",
                response_size=size,
                max_size=client._max_response_bytes,
            )
    except KubernetesApiResponseTooLargeError:
        raise
    except Exception:  # noqa: BLE001
        pass


def list_namespaced_pods_projected(
    client: KubernetesReadClient,
    *,
    namespace: str,
    label_selector: str | None = None,
    field_selector: str | None = None,
    limit: int = DEFAULT_LIMIT,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> tuple[list[PodProjection], PaginationMetadata]:
    """List pods with pagination."""
    all_pods: list[PodProjection] = []
    continue_token: str | None = None
    remaining = 0
    truncated = False

    while True:
        try:
            response = client.core_v1.list_namespaced_pod(
                namespace=namespace, label_selector=label_selector,
                field_selector=field_selector, limit=limit,
                _continue=continue_token, timeout_seconds=client._timeout_seconds,
            )
            for item in response.items:
                if len(all_pods) >= max_items:
                    truncated = True
                    remaining = response.metadata.remaining_item_count or 0
                    break
                all_pods.append(PodProjection.from_dict(item.to_dict()))
            if truncated:
                break
            continue_token = response.metadata._continue
            if not continue_token:
                break
            _check_response_size(client, response)
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to list pods in %s: %s", namespace, type(exc).__name__)
            break

    return all_pods, PaginationMetadata(
        total=len(all_pods), remaining=remaining, truncated=truncated,
        continuation_token=continue_token, items_returned=len(all_pods),
    )


def list_namespaced_events_projected(
    client: KubernetesReadClient,
    *,
    namespace: str,
    field_selector: str | None = None,
    limit: int = DEFAULT_LIMIT,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> tuple[list[EventProjection], PaginationMetadata]:
    """List events with pagination."""
    all_events: list[EventProjection] = []
    continue_token: str | None = None
    remaining = 0
    truncated = False

    while True:
        try:
            response = client.core_v1.list_namespaced_event(
                namespace=namespace, field_selector=field_selector,
                limit=limit, _continue=continue_token, timeout_seconds=client._timeout_seconds,
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
            _check_response_size(client, response)
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to list events in %s: %s", namespace, type(exc).__name__)
            break

    return all_events, PaginationMetadata(
        total=len(all_events), remaining=remaining, truncated=truncated,
        continuation_token=continue_token, items_returned=len(all_events),
    )


def list_namespaced_deployments_projected(
    client: KubernetesReadClient,
    *,
    namespace: str,
    label_selector: str | None = None,
    field_selector: str | None = None,
    limit: int = DEFAULT_LIMIT,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> tuple[list[DeploymentProjection], PaginationMetadata]:
    """List deployments with pagination and projection."""
    all_deployments: list[DeploymentProjection] = []
    continue_token: str | None = None
    remaining = 0
    truncated = False

    while True:
        try:
            response = client.apps_v1.list_namespaced_deployment(
                namespace=namespace,
                label_selector=label_selector,
                field_selector=field_selector,
                limit=limit,
                _continue=continue_token,
                timeout_seconds=client._timeout_seconds,
            )
            for item in response.items:
                if len(all_deployments) >= max_items:
                    truncated = True
                    remaining = response.metadata.remaining_item_count or 0
                    break
                all_deployments.append(DeploymentProjection.from_dict(item.to_dict()))
            if truncated:
                break
            continue_token = response.metadata._continue
            if not continue_token:
                break
            _check_response_size(client, response)
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to list deployments in %s: %s", namespace, type(exc).__name__)
            break

    return all_deployments, PaginationMetadata(
        total=len(all_deployments),
        remaining=remaining,
        truncated=truncated,
        continuation_token=continue_token,
        items_returned=len(all_deployments),
    )


__all__ = [
    "list_namespaced_deployments_projected",
    "list_namespaced_events_projected",
    "list_namespaced_pods_projected",
]
