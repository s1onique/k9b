"""Kubernetes Python client boundary for read-only production paths.

This module is a compatibility facade that re-exports from focused submodules:
- kubernetes_client_config.py: get_cached_kubernetes_client, clear_client_cache
- kubernetes_client_translation.py: translate_api_exception
- kubernetes_client_pods.py: Pod list/read helpers
- kubernetes_client_events.py: Event readers
- kubernetes_client_deployments.py: Deployment/env/namespace readers
- kubernetes_client_crds.py: CRD discovery/list helpers

Production scheduler/health-loop/incident-evidence paths MUST use this client
instead of kubectl subprocess calls.

Bounded kubectl remains as fallback/debug seam only.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from .kubernetes_client_constants import (
    DEFAULT_ACTIVE_PODS_MAX,
    DEFAULT_EVICTED_PODS_REPORTED_MAX,
    DEFAULT_FAILED_PODS_REPORTED_MAX,
    DEFAULT_FAILED_PODS_SCANNED_MAX,
    DEFAULT_LIMIT,
    DEFAULT_LOG_BYTES,
    DEFAULT_LOG_TAIL_LINES,
    DEFAULT_MAX_ITEMS,
    DEFAULT_POD_PAGE_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
)
from .kubernetes_client_errors import (
    KubernetesApiNotFoundError,
    KubernetesApiPermissionError,
    KubernetesApiResponseTooLargeError,
    KubernetesApiTimeoutError,
    KubernetesClientError,
    KubernetesClientUnavailableError,
)
from .kubernetes_client_models import (
    CrdSummary,
    DeploymentProjection,
    EventProjection,
    NamespaceProjection,
    NodeSummary,
    PaginationMetadata,
    PodProjection,
    PodSummary,
    SecretProjection,
    ServiceAccountProjection,
    StatefulSetSummary,
)
from .kubernetes_client_translation import translate_api_exception

if TYPE_CHECKING:
    from kubernetes.client import ApiClient, AppsV1Api, CoreV1Api, CustomObjectsApi

_logger = logging.getLogger(__name__)

# Module-level client cache keyed by (kubeconfig, context)
_client_cache: dict[tuple[str | None, str | None], KubernetesReadClient] = {}


def clear_client_cache() -> None:
    """Clear the client cache. Useful for testing."""
    global _client_cache
    _client_cache.clear()


def get_cached_kubernetes_client(
    *,
    kubeconfig: str | None = None,
    context: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> KubernetesReadClient:
    """Get or create a cached KubernetesReadClient keyed by (kubeconfig, context).

    Args:
        kubeconfig: Path to kubeconfig file (None for in-cluster/config default)
        context: Kubernetes context name (None for default context)
        timeout_seconds: API timeout in seconds

    Returns:
        Cached or newly created KubernetesReadClient
    """
    global _client_cache
    cache_key = (kubeconfig, context)

    if cache_key not in _client_cache:
        _client_cache[cache_key] = KubernetesReadClient(
            kubeconfig=kubeconfig,
            context=context,
            timeout_seconds=timeout_seconds,
        )
        _logger.debug(
            "Created new cached Kubernetes client for key: kubeconfig=%s, context=%s",
            kubeconfig,
            context,
        )

    return _client_cache[cache_key]


class KubernetesReadClient:
    """Read-only Kubernetes API client with typed projections and pagination.

    This client provides a safe interface for production code to read from
    Kubernetes without:
    - Shell subprocess overhead
    - kubectl formatting/parsing boundaries
    - Unbounded response handling
    """

    def __init__(
        self,
        *,
        kubeconfig: str | None = None,
        context: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int | None = None,
    ):
        """Initialize the Kubernetes read client."""
        self._kubeconfig = kubeconfig
        self._context = context
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes or (10 * 1024 * 1024)
        self._client: ApiClient | None = None
        self._core_v1: CoreV1Api | None = None
        self._apps_v1: AppsV1Api | None = None
        self._custom_objects: CustomObjectsApi | None = None
        self._config_loaded = False

    def _ensure_config(self) -> None:
        """Lazy-load Kubernetes configuration and API clients."""
        if self._config_loaded:
            return
        try:
            from kubernetes import client, config
        except ImportError as exc:
            raise KubernetesClientError(
                "kubernetes package not installed. Install with: pip install kubernetes",
                cause=exc,
            ) from exc
        try:
            if self._kubeconfig or self._context:
                config.load_kube_config(config_file=self._kubeconfig, context=self._context)
            elif os.environ.get("KUBERNETES_SERVICE_HOST"):
                config.load_incluster_config()
            else:
                config.load_kube_config(context=self._context)
        except Exception as exc:
            raise KubernetesClientUnavailableError(
                f"Failed to load Kubernetes config: {exc}",
                cause=exc,
            ) from exc
        self._client = client.ApiClient()
        self._core_v1 = client.CoreV1Api(api_client=self._client)
        self._apps_v1 = client.AppsV1Api(api_client=self._client)
        self._custom_objects = client.CustomObjectsApi(api_client=self._client)
        self._config_loaded = True
        _logger.debug("Kubernetes config loaded successfully")

    @property
    def core_v1(self) -> CoreV1Api:
        """Get the CoreV1Api instance."""
        self._ensure_config()
        assert self._core_v1 is not None
        return self._core_v1

    @property
    def apps_v1(self) -> AppsV1Api:
        """Get the AppsV1Api instance."""
        self._ensure_config()
        assert self._apps_v1 is not None
        return self._apps_v1

    @property
    def custom_objects(self) -> CustomObjectsApi:
        """Get the CustomObjectsApi instance."""
        self._ensure_config()
        assert self._custom_objects is not None
        return self._custom_objects

    def list_namespaced_custom_objects(
        self,
        *,
        group: str,
        version: str,
        plural: str,
        namespace: str,
        label_selector: str | None = None,
        field_selector: str | None = None,
        limit: int = DEFAULT_LIMIT,
        max_items: int = DEFAULT_MAX_ITEMS,
    ) -> tuple[list[dict[str, Any]], PaginationMetadata]:
        """List custom objects in a namespace using the CustomObjectsApi."""
        self._ensure_config()
        all_items: list[dict[str, Any]] = []
        continue_token: str | None = None
        remaining = 0
        truncated = False
        custom_api = self.custom_objects

        while True:
            try:
                response = custom_api.list_namespaced_custom_object(
                    group=group, version=version, plural=plural, namespace=namespace,
                    label_selector=label_selector, field_selector=field_selector,
                    limit=limit, _continue=continue_token,
                )
                items = response.get("items") or []
                all_items.extend(items)
                continue_token = response.get("metadata", {}).get("continue")
                remaining = response.get("metadata", {}).get("remainingItemCount") or 0

                if len(all_items) >= max_items:
                    truncated = True
                    remaining = max(0, remaining - (len(all_items) - max_items))
                    all_items = all_items[:max_items]
                    break

                if not continue_token:
                    break
            except Exception as exc:  # noqa: BLE001
                _logger.debug("Failed custom object list %s/%s/%s: %s", group, version, plural, type(exc).__name__)
                break

        return all_items, PaginationMetadata(
            total=len(all_items), remaining=remaining, truncated=truncated,
            continuation_token=continue_token, items_returned=len(all_items),
        )

    def read_namespace_uid(self, name: str) -> str | None:
        """Read the UID of a namespace by name."""
        self._ensure_config()
        try:
            namespace = self.core_v1.read_namespace(name)
            uid: str | None = str(namespace.metadata.uid) if namespace.metadata else None
            return uid
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to read namespace %s: %s", name, type(exc).__name__)
            return None

    def read_deployment_env_value(self, *, namespace: str, deployment: str,
            container: str | None = None, env_name: str) -> str | None:
        """Read an environment variable value from a Deployment spec."""
        from .kubernetes_client_deployments import read_deployment_env_value
        self._ensure_config()
        return read_deployment_env_value(
            self._apps_v1, namespace=namespace, deployment=deployment,
            timeout_seconds=self._timeout_seconds, container=container, env_name=env_name,
        )

    def list_namespaced_pods_projected(self, *, namespace: str,
            label_selector: str | None = None, field_selector: str | None = None,
            limit: int = DEFAULT_LIMIT, max_items: int = DEFAULT_MAX_ITEMS,
            ) -> tuple[list[PodProjection], PaginationMetadata]:
        """List pods in a namespace with pagination and projection."""
        self._ensure_config()
        from .kubernetes_client_pods import list_namespaced_pods_projected
        return list_namespaced_pods_projected(
            self._core_v1, namespace=namespace, timeout_seconds=self._timeout_seconds,
            max_response_bytes=self._max_response_bytes, label_selector=label_selector,
            field_selector=field_selector, limit=limit, max_items=max_items,
        )

    def list_namespaced_events_projected(self, *, namespace: str,
            field_selector: str | None = None, limit: int = DEFAULT_LIMIT,
            max_items: int = DEFAULT_MAX_ITEMS) -> tuple[list[EventProjection], PaginationMetadata]:
        """List events in a namespace with pagination and projection."""
        self._ensure_config()
        from .kubernetes_client_events import list_namespaced_events_projected
        return list_namespaced_events_projected(
            self._core_v1, namespace=namespace, timeout_seconds=self._timeout_seconds,
            field_selector=field_selector, limit=limit, max_items=max_items,
        )

    def list_namespaced_deployments_projected(self, *, namespace: str,
            label_selector: str | None = None, field_selector: str | None = None,
            limit: int = DEFAULT_LIMIT, max_items: int = DEFAULT_MAX_ITEMS,
            ) -> tuple[list[DeploymentProjection], PaginationMetadata]:
        """List deployments in a namespace with pagination and projection."""
        self._ensure_config()
        from .kubernetes_client_deployments import list_namespaced_deployments_projected
        return list_namespaced_deployments_projected(
            self._apps_v1, namespace=namespace, timeout_seconds=self._timeout_seconds,
            label_selector=label_selector, field_selector=field_selector,
            limit=limit, max_items=max_items,
        )

    def read_namespaced_deployment_projected(self, *, namespace: str,
            name: str) -> DeploymentProjection | None:
        """Read a deployment and project it."""
        self._ensure_config()
        try:
            deploy = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            return DeploymentProjection.from_dict(deploy.to_dict())
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to read deployment %s/%s: %s", namespace, name, type(exc).__name__)
            return None

    def read_namespaced_secret_projected(self, *, namespace: str,
            name: str) -> SecretProjection | None:
        """Read a secret metadata and project it (no data)."""
        self._ensure_config()
        try:
            secret = self.core_v1.read_namespaced_secret(name=name, namespace=namespace)
            return SecretProjection.from_dict(secret.to_dict())
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to read secret %s/%s: %s", namespace, name, type(exc).__name__)
            return None

    def read_namespaced_service_account_projected(self, *, namespace: str,
            name: str) -> ServiceAccountProjection | None:
        """Read a service account and project it."""
        self._ensure_config()
        try:
            sa = self.core_v1.read_namespaced_service_account(name=name, namespace=namespace)
            return ServiceAccountProjection.from_dict(sa.to_dict())
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to read SA %s/%s: %s", namespace, name, type(exc).__name__)
            return None

    def list_all_namespaces_pods_summaries(self, *, page_limit: int = DEFAULT_POD_PAGE_LIMIT,
            max_active_pods: int = DEFAULT_ACTIVE_PODS_MAX,
            exclude_terminal: bool = True) -> tuple[list[PodSummary], PaginationMetadata]:
        """List all pods across all namespaces with pagination, projecting compact summaries."""
        self._ensure_config()
        from .kubernetes_client_pods import list_all_namespaces_pods_summaries
        return list_all_namespaces_pods_summaries(
            self._core_v1, timeout_seconds=self._timeout_seconds,
            page_limit=page_limit, max_active_pods=max_active_pods, exclude_terminal=exclude_terminal,
        )

    def sample_failed_pods_bounded(self, *, page_limit: int = DEFAULT_POD_PAGE_LIMIT,
            max_scanned: int = DEFAULT_FAILED_PODS_SCANNED_MAX,
            max_failed_reported: int = DEFAULT_FAILED_PODS_REPORTED_MAX,
            max_evicted_reported: int = DEFAULT_EVICTED_PODS_REPORTED_MAX,
            ) -> tuple[list[PodSummary], dict[str, Any]]:
        """Sample failed and evicted pods with bounded collection."""
        self._ensure_config()
        from .kubernetes_client_pods import sample_failed_pods_bounded
        return sample_failed_pods_bounded(
            self._core_v1, timeout_seconds=self._timeout_seconds,
            page_limit=page_limit, max_scanned=max_scanned,
            max_failed_reported=max_failed_reported, max_evicted_reported=max_evicted_reported,
        )

    def list_warning_events_for_all_namespaces(self, *, limit: int,
            timeout_seconds: int | None = None) -> list[EventProjection]:
        """List warning events across all namespaces with the Python client."""
        self._ensure_config()
        from .kubernetes_client_events import list_warning_events_for_all_namespaces
        timeout = timeout_seconds or self._timeout_seconds
        return list_warning_events_for_all_namespaces(self._core_v1, timeout_seconds=timeout, limit=limit)

    def list_namespaced_deployments(self, namespace: str, *,
            timeout_seconds: int | None = None) -> list[DeploymentProjection]:
        """List deployments in a namespace with the Python client."""
        self._ensure_config()
        timeout = timeout_seconds or self._timeout_seconds
        try:
            response = self.apps_v1.list_namespaced_deployment(namespace=namespace, _request_timeout=timeout)
        except Exception as exc:
            raise translate_api_exception(exc, resource="deployment", namespace=namespace,
                operation="list_namespaced_deployments") from exc
        return [DeploymentProjection.from_dict(item.to_dict()) for item in (response.items or [])]

    def list_namespaced_statefulsets(self, namespace: str, *,
            timeout_seconds: int | None = None) -> list[StatefulSetSummary]:
        """List statefulsets in a namespace with the Python client."""
        self._ensure_config()
        timeout = timeout_seconds or self._timeout_seconds
        try:
            response = self.apps_v1.list_namespaced_stateful_set(namespace=namespace, _request_timeout=timeout)
        except Exception as exc:
            raise translate_api_exception(exc, resource="statefulset", namespace=namespace,
                operation="list_namespaced_statefulsets") from exc
        return [StatefulSetSummary.from_dict(item.to_dict()) for item in (response.items or [])]

    def list_namespaced_pods(self, namespace: str, *, label_selector: str | None = None,
            field_selector: str | None = None, timeout_seconds: int | None = None) -> list[PodSummary]:
        """List pods in a namespace with the Python client."""
        self._ensure_config()
        timeout = timeout_seconds or self._timeout_seconds
        try:
            response = self.core_v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector,
                field_selector=field_selector, _request_timeout=timeout)
        except Exception as exc:
            raise translate_api_exception(exc, resource="pod", namespace=namespace,
                operation="list_namespaced_pods") from exc
        return [PodSummary.from_pod_dict(item.to_dict()) for item in (response.items or [])]

    def list_nodes(self, *, timeout_seconds: int | None = None) -> list[NodeSummary]:
        """List all nodes with the Python client."""
        self._ensure_config()
        timeout = timeout_seconds or self._timeout_seconds
        try:
            response = self.core_v1.list_node(_request_timeout=timeout)
        except Exception as exc:
            raise translate_api_exception(exc, resource="node", operation="list_nodes") from exc
        return [NodeSummary.from_dict(item.to_dict()) for item in (response.items or [])]

    def list_crds(self, *, timeout_seconds: int | None = None) -> list[CrdSummary]:
        """List all CustomResourceDefinitions with the Python client."""
        from .kubernetes_client_crds import list_crds
        self._ensure_config()
        timeout = timeout_seconds or self._timeout_seconds
        return list_crds(self._client, timeout_seconds=timeout)


def create_kubernetes_read_client(*, kubeconfig: str | None = None, context: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> KubernetesReadClient:
    """Factory function to create a KubernetesReadClient."""
    return KubernetesReadClient(kubeconfig=kubeconfig, context=context, timeout_seconds=timeout_seconds)


__all__ = [
    "KubernetesReadClient", "create_kubernetes_read_client",
    "clear_client_cache", "get_cached_kubernetes_client",
    "KubernetesApiNotFoundError", "KubernetesApiPermissionError",
    "KubernetesApiResponseTooLargeError", "KubernetesApiTimeoutError",
    "KubernetesClientError", "KubernetesClientUnavailableError", "translate_api_exception",
    "CrdSummary", "DeploymentProjection", "EventProjection", "NamespaceProjection",
    "NodeSummary", "PaginationMetadata", "PodProjection", "PodSummary",
    "SecretProjection", "ServiceAccountProjection", "StatefulSetSummary",
    "DEFAULT_ACTIVE_PODS_MAX", "DEFAULT_EVICTED_PODS_REPORTED_MAX",
    "DEFAULT_FAILED_PODS_REPORTED_MAX", "DEFAULT_FAILED_PODS_SCANNED_MAX",
    "DEFAULT_LIMIT", "DEFAULT_LOG_BYTES", "DEFAULT_LOG_TAIL_LINES",
    "DEFAULT_MAX_ITEMS", "DEFAULT_POD_PAGE_LIMIT", "DEFAULT_TIMEOUT_SECONDS",
]
