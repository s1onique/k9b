"""Pod reading helpers for Kubernetes client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .kubernetes_client_constants import (
    DEFAULT_ACTIVE_PODS_MAX,
    DEFAULT_EVICTED_PODS_REPORTED_MAX,
    DEFAULT_FAILED_PODS_REPORTED_MAX,
    DEFAULT_FAILED_PODS_SCANNED_MAX,
    DEFAULT_LIMIT,
    DEFAULT_MAX_ITEMS,
    DEFAULT_POD_PAGE_LIMIT,
)
from .kubernetes_client_errors import KubernetesApiResponseTooLargeError
from .kubernetes_client_pagination_models import PaginationMetadata
from .kubernetes_client_pod_models import PodProjection, PodSummary

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


def list_namespaced_pods_projected(
    core_v1: Any,
    *,
    namespace: str,
    timeout_seconds: int,
    max_response_bytes: int,
    label_selector: str | None = None,
    field_selector: str | None = None,
    limit: int = DEFAULT_LIMIT,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> tuple[list[PodProjection], PaginationMetadata]:
    """List pods in a namespace with pagination and projection."""
    import json

    all_pods: list[PodProjection] = []
    continue_token: str | None = None
    remaining = 0
    truncated = False

    def _check_size(response: Any) -> None:
        """Check if response exceeds size limits."""
        try:
            serialized = json.dumps(response.to_dict())
            size = len(serialized.encode("utf-8"))
            if size > max_response_bytes:
                raise KubernetesApiResponseTooLargeError(
                    f"Response too large: {size} bytes exceeds limit of {max_response_bytes}",
                    response_size=size,
                    max_size=max_response_bytes,
                )
        except KubernetesApiResponseTooLargeError:
            raise
        except Exception:  # noqa: BLE001
            pass

    while True:
        try:
            response = core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector,
                field_selector=field_selector,
                limit=limit,
                _continue=continue_token,
                _request_timeout=timeout_seconds,
            )
            _check_size(response)
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
        except KubernetesApiResponseTooLargeError:
            raise
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to list pods in %s: %s", namespace, type(exc).__name__)
            break

    return all_pods, PaginationMetadata(
        total=len(all_pods),
        remaining=remaining,
        truncated=truncated,
        continuation_token=continue_token,
        items_returned=len(all_pods),
    )


def list_all_namespaces_pods_summaries(
    core_v1: Any,
    *,
    timeout_seconds: int,
    page_limit: int = DEFAULT_POD_PAGE_LIMIT,
    max_active_pods: int = DEFAULT_ACTIVE_PODS_MAX,
    exclude_terminal: bool = True,
) -> tuple[list[PodSummary], PaginationMetadata]:
    """List all pods across all namespaces with pagination, projecting compact summaries.

    Args:
        core_v1: CoreV1Api instance
        timeout_seconds: API timeout
        page_limit: Items per API page (default 200)
        max_active_pods: Maximum active pods to collect (default 1000)
        exclude_terminal: If True, exclude Succeeded and Failed phases (default True)

    Returns:
        Tuple of (list of PodSummary, pagination metadata with truncation info)
    """
    all_pods: list[PodSummary] = []
    continue_token: str | None = None
    remaining = 0
    truncated = False

    # Field selector for non-terminal pods when exclude_terminal=True
    # IMPORTANT: Only exclude Succeeded pods. Failed/Evicted pods are diagnostically
    # relevant for K9B and should remain in non-running / failed-pod sampling.
    if exclude_terminal:
        field_selector = "status.phase!=Succeeded"
    else:
        field_selector = None

    while True:
        try:
            response = core_v1.list_pod_for_all_namespaces(
                field_selector=field_selector,
                limit=page_limit,
                _continue=continue_token,
                _request_timeout=timeout_seconds,
            )
            # Process page items immediately and release response
            for item in response.items:
                if len(all_pods) >= max_active_pods:
                    truncated = True
                    remaining = response.metadata.remaining_item_count or 0
                    break
                # Project to compact summary - no full pod storage
                pod_dict = item.to_dict()
                # Defensive client-side filter: belt-and-suspenders for API compatibility
                # Edge cases: older API versions, custom schedulers, mock responses
                # IMPORTANT: Only exclude Succeeded pods client-side. Failed/Evicted pods
                # are diagnostically relevant for K9B and should remain visible.
                if exclude_terminal:
                    phase = str(pod_dict.get("status", {}).get("phase") or "")
                    if phase == "Succeeded":
                        continue
                all_pods.append(PodSummary.from_pod_dict(pod_dict))
            if truncated:
                break
            continue_token = response.metadata._continue
            if not continue_token:
                break
            # Release response before next iteration
            del response
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to list pods across all namespaces: %s", type(exc).__name__)
            break

    return all_pods, PaginationMetadata(
        total=len(all_pods),
        remaining=remaining,
        truncated=truncated,
        continuation_token=continue_token,
        items_returned=len(all_pods),
    )


def sample_failed_pods_bounded(
    core_v1: Any,
    *,
    timeout_seconds: int,
    page_limit: int = DEFAULT_POD_PAGE_LIMIT,
    max_scanned: int = DEFAULT_FAILED_PODS_SCANNED_MAX,
    max_failed_reported: int = DEFAULT_FAILED_PODS_REPORTED_MAX,
    max_evicted_reported: int = DEFAULT_EVICTED_PODS_REPORTED_MAX,
) -> tuple[list[PodSummary], dict[str, Any]]:
    """Sample failed and evicted pods with bounded collection.

    Args:
        core_v1: CoreV1Api instance
        timeout_seconds: API timeout
        page_limit: Items per API page (default 200)
        max_scanned: Maximum pods to scan before stopping (default 500)
        max_failed_reported: Maximum failed pods in result (default 50)
        max_evicted_reported: Maximum evicted pods in result (default 20)

    Returns:
        Tuple of (list of PodSummary, metadata dict with truncation flags)
    """
    failed_pods: list[PodSummary] = []
    evicted_pods: list[PodSummary] = []
    scanned_count = 0
    continue_token: str | None = None

    # Field selector for Failed pods (Evicted pods have phase=Failed)
    field_selector = "status.phase=Failed"

    while scanned_count < max_scanned:
        try:
            response = core_v1.list_pod_for_all_namespaces(
                field_selector=field_selector,
                limit=page_limit,
                _continue=continue_token,
                _request_timeout=timeout_seconds,
            )
            for item in response.items:
                # Check scan limit BEFORE incrementing and processing
                # This ensures we scan exactly max_scanned pods
                if scanned_count >= max_scanned:
                    break
                scanned_count += 1
                summary = PodSummary.from_pod_dict(item.to_dict())
                # Separate evicted from other failed pods
                # Evicted pods have reason="Evicted" in their status
                if summary.reason == "Evicted":
                    if len(evicted_pods) < max_evicted_reported:
                        evicted_pods.append(summary)
                else:
                    if len(failed_pods) < max_failed_reported:
                        failed_pods.append(summary)
            continue_token = response.metadata._continue
            # Release response before next iteration
            del response
            if not continue_token:
                break
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to list failed pods: %s", type(exc).__name__)
            break

    # Combine results: evicted first, then other failed
    all_results = evicted_pods + failed_pods

    metadata = {
        "scanned": scanned_count,
        "scanned_limit": max_scanned,
        "evicted_count": len(evicted_pods),
        "evicted_limit": max_evicted_reported,
        "failed_count": len(failed_pods),
        "failed_limit": max_failed_reported,
        "evicted_truncated": len(evicted_pods) == max_evicted_reported,
        "failed_truncated": len(failed_pods) == max_failed_reported,
        "scan_truncated": scanned_count >= max_scanned,
    }

    return all_results, metadata


__all__ = [
    "list_all_namespaces_pods_summaries",
    "list_namespaced_pods_projected",
    "sample_failed_pods_bounded",
]
