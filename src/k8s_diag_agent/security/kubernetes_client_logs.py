"""Pod log reading via Kubernetes Python client.

This module provides bounded pod log reading functionality.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from .kubernetes_client_constants import DEFAULT_LOG_BYTES, DEFAULT_LOG_TAIL_LINES
from .kubernetes_client_errors import translate_api_exception
from .kubernetes_client_models import BoundedPodLogResult

if TYPE_CHECKING:
    from .kubernetes_client import KubernetesReadClient

_logger = logging.getLogger(__name__)


def read_pod_logs_bounded(
    client: KubernetesReadClient,
    *,
    namespace: str,
    name: str,
    container: str | None = None,
    tail_lines: int = DEFAULT_LOG_TAIL_LINES,
    limit_bytes: int = DEFAULT_LOG_BYTES,
    previous: bool = False,
    since_seconds: int | None = None,
) -> BoundedPodLogResult:
    """Read pod logs with bounds.

    Args:
        client: The KubernetesReadClient instance
        namespace: Namespace name
        name: Pod name
        container: Container name (None for first container)
        tail_lines: Number of lines to fetch from the end
        limit_bytes: Maximum bytes to fetch
        previous: Get previous terminated container logs
        since_seconds: Fetch logs from the last N seconds

    Returns:
        Bounded pod log result with truncation metadata
    """
    start_time = time.monotonic()

    try:
        response = client.core_v1.read_namespaced_pod_log(
            name=name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
            limit_bytes=limit_bytes,
            previous=previous,
            since_seconds=since_seconds,
            _preload_content=True,
        )

        duration = time.monotonic() - start_time
        logs = response if isinstance(response, str) else ""

        truncated = len(logs) >= limit_bytes

        return BoundedPodLogResult(
            logs=logs,
            truncated=truncated,
            truncation_reason="limit_bytes" if truncated else None,
            bytes_read=len(logs.encode("utf-8")),
            bytes_limit=limit_bytes,
            tail_lines=tail_lines,
            duration_seconds=duration,
        )

    except Exception as exc:  # noqa: BLE001
        duration = time.monotonic() - start_time
        error = translate_api_exception(
            exc,
            resource="pod",
            namespace=namespace,
            operation="read_pod_log",
        )
        _logger.debug("Failed to read pod logs %s/%s: %s", namespace, name, error)
        return BoundedPodLogResult(
            logs="",
            truncated=False,
            truncation_reason=f"error: {error.message}",
            bytes_read=0,
            bytes_limit=limit_bytes,
            tail_lines=tail_lines,
            duration_seconds=duration,
        )


__all__ = ["read_pod_logs_bounded"]
