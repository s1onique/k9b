"""Bounded pod collection helpers for live cluster snapshots.

This module provides memory-safe pod collection using the Kubernetes Python client
with pagination and compact projections. It replaces kubectl get pods --all-namespaces
which causes OOM on large clusters.
"""
from __future__ import annotations

import logging
from typing import Any

from ..security.kubernetes_client import (
    DEFAULT_ACTIVE_PODS_MAX,
    DEFAULT_POD_PAGE_LIMIT,
    get_cached_kubernetes_client,
)
from ..security.kubernetes_client_models import PodSummary
from .cluster_snapshot import PodHealthCounts

_logger = logging.getLogger(__name__)


def collect_pods_bounded(
    context: str,
) -> tuple[list[PodSummary], dict[str, Any]]:
    """Collect pods using bounded Python client with pagination.

    This replaces the old kubectl approach that caused OOM on large clusters:
    - Uses server-side pagination with limit/continue
    - Projects only diagnostically-relevant fields
    - Excludes terminal phases by default
    - Hard-caps results to prevent memory growth

    Args:
        context: Kubernetes context name for client cache lookup

    Returns:
        Tuple of (list of PodSummary, pagination metadata dict)
    """
    try:
        # Get cached client for this context (propagated for multi-cluster scenarios)
        client = get_cached_kubernetes_client(context=context)
        summaries, pagination = client.list_all_namespaces_pods_summaries(
            page_limit=DEFAULT_POD_PAGE_LIMIT,
            max_active_pods=DEFAULT_ACTIVE_PODS_MAX,
            exclude_terminal=True,
        )
        metadata = {
            "truncated": pagination.truncated,
            "remaining": pagination.remaining,
            "items_returned": pagination.items_returned,
        }
        return summaries, metadata
    except Exception as exc:
        _logger.debug("Failed to collect pods via Python client: %s", type(exc).__name__)
        # Fall back to empty list on error - caller handles gracefully
        return [], {"truncated": False, "remaining": 0, "items_returned": 0}


def summarize_pod_health_from_summaries(
    summaries: list[PodSummary],
) -> PodHealthCounts:
    """Summarize pod health from PodSummary list.

    Args:
        summaries: List of PodSummary from bounded collection

    Returns:
        PodHealthCounts with phase distribution and diagnostic flags
    """
    pending = 0
    crash_loop_backoff = 0
    image_pull_backoff = 0
    completed_job_pods = 0
    non_running = 0

    for pod in summaries:
        phase = pod.phase or "Unknown"
        # Count non-running pods
        if phase not in ("Running", "Succeeded"):
            non_running += 1
        # Count pending
        if phase == "Pending":
            pending += 1
        # Count completed job pods (Succeeded phase)
        if phase == "Succeeded":
            completed_job_pods += 1
        # Check for crash loop and image pull backoff reasons
        if "CrashLoopBackOff" in pod.waiting_reasons or "Error" in pod.terminated_reasons:
            crash_loop_backoff += 1
        if any(r in pod.waiting_reasons for r in ("ImagePullBackOff", "ErrImagePull")):
            image_pull_backoff += 1

    return PodHealthCounts(
        non_running=non_running,
        pending=pending,
        crash_loop_backoff=crash_loop_backoff,
        image_pull_backoff=image_pull_backoff,
        completed_job_pods=completed_job_pods,
    )
