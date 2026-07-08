"""Configuration loading and caching for Kubernetes client.

Handles kubeconfig loading, context selection, and client caching.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kubernetes.client import ApiClient, AppsV1Api, CoreV1Api, CustomObjectsApi

_logger = logging.getLogger(__name__)


def _load_kubernetes_config(
    *,
    kubeconfig: str | None = None,
    context: str | None = None,
) -> tuple[ApiClient, CoreV1Api, AppsV1Api, CustomObjectsApi]:
    """Load Kubernetes configuration and return API client instances.

    Args:
        kubeconfig: Path to kubeconfig file (None for in-cluster/config default)
        context: Kubernetes context name (None for default context)

    Returns:
        Tuple of (ApiClient, CoreV1Api, AppsV1Api, CustomObjectsApi)

    Raises:
        KubernetesClientError: If kubernetes package not installed
        KubernetesClientUnavailableError: If config loading fails
    """
    from kubernetes import client, config

    try:
        if kubeconfig or context:
            config.load_kube_config(config_file=kubeconfig, context=context)
        elif os.environ.get("KUBERNETES_SERVICE_HOST"):
            config.load_incluster_config()
        else:
            config.load_kube_config(context=context)
    except Exception as exc:
        from .kubernetes_client_errors import KubernetesClientUnavailableError
        raise KubernetesClientUnavailableError(
            f"Failed to load Kubernetes config: {exc}",
            cause=exc,
        ) from exc

    api_client = client.ApiClient()
    core_v1 = client.CoreV1Api(api_client=api_client)
    apps_v1 = client.AppsV1Api(api_client=api_client)
    custom_objects = client.CustomObjectsApi(api_client=api_client)

    _logger.debug("Kubernetes config loaded successfully")
    return api_client, core_v1, apps_v1, custom_objects


__all__ = [
    "_load_kubernetes_config",
]
