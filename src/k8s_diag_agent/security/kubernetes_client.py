"""Kubernetes Python client boundary for read-only production paths.

This module provides a typed Kubernetes API client that:
1. Uses in-cluster config when available, kubeconfig otherwise
2. Exposes read-only operations with typed projection models
3. Supports pagination with continue tokens
4. Normalizes errors to domain-specific types

Production scheduler/health-loop/incident-evidence paths MUST use this client
instead of kubectl subprocess calls.

Bounded kubectl remains as fallback/debug seam only.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from .kubernetes_client_constants import (
    DEFAULT_LIMIT,
    DEFAULT_LOG_BYTES,
    DEFAULT_LOG_TAIL_LINES,
    DEFAULT_MAX_ITEMS,
    DEFAULT_TIMEOUT_SECONDS,
)
from .kubernetes_client_errors import (
    KubernetesApiNotFoundError,
    KubernetesApiPermissionError,
    KubernetesApiResponseTooLargeError,
    KubernetesApiTimeoutError,
    KubernetesClientError,
    KubernetesClientUnavailableError,
    translate_api_exception,
)
from .kubernetes_client_models import (
    DeploymentProjection,
    EventProjection,
    NamespaceProjection,
    PaginationMetadata,
    PodProjection,
    SecretProjection,
    ServiceAccountProjection,
)
from .kubernetes_client_pagination import (
    list_namespaced_deployments_projected,
    list_namespaced_events_projected,
    list_namespaced_pods_projected,
)

if TYPE_CHECKING:
    from kubernetes.client import ApiClient, AppsV1Api, CoreV1Api, CustomObjectsApi

_logger = logging.getLogger(__name__)

# Module-level client cache keyed by (kubeconfig, context)
_client_cache: dict[tuple[str | None, str | None], KubernetesReadClient] = {}
_cache_lock = None  # Simple module-level cache without locks for single-threaded use


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
            raise KubernetesClientUnavailableError(f"Failed to load Kubernetes config: {exc}", cause=exc) from exc
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
        # mypy needs explicit assertion for property returning from _ensure_config
        assert self._custom_objects is not None, "custom_objects should be initialized by _ensure_config"
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
        """List custom objects in a namespace using the CustomObjectsApi.

        This is the preferred method for reading CRDs like ExternalSecret.
        Results are bounded by max_items to prevent unbounded memory growth.

        Returns:
            Tuple of (items, pagination_metadata) where metadata includes truncation info.
        """
        self._ensure_config()
        all_items: list[dict[str, Any]] = []
        continue_token: str | None = None
        remaining = 0
        truncated = False
        # Use property to get properly typed CustomObjectsApi
        custom_api = self.custom_objects

        while True:
            try:
                response = custom_api.list_namespaced_custom_object(
                    group=group,
                    version=version,
                    plural=plural,
                    namespace=namespace,
                    label_selector=label_selector,
                    field_selector=field_selector,
                    limit=limit,
                    _continue=continue_token,
                )
                items = response.get("items") or []
                all_items.extend(items)
                continue_token = response.get("metadata", {}).get("continue")
                remaining = response.get("metadata", {}).get("remainingItemCount") or 0

                # Check max_items bound
                if len(all_items) >= max_items:
                    truncated = True
                    remaining = max(0, remaining - (len(all_items) - max_items))
                    all_items = all_items[:max_items]
                    _logger.debug(
                        "Custom objects list truncated at %d items (max_items=%d)",
                        len(all_items), max_items,
                    )
                    break

                if not continue_token:
                    break
            except Exception as exc:  # noqa: BLE001
                _logger.debug(
                    "Failed to list custom objects %s/%s/%s in %s: %s",
                    group, version, plural, namespace, type(exc).__name__,
                )
                break

        return all_items, PaginationMetadata(
            total=len(all_items),
            remaining=remaining,
            truncated=truncated,
            continuation_token=continue_token,
            items_returned=len(all_items),
        )

    def read_namespace_uid(self, name: str) -> str | None:
        """Read the UID of a namespace by name."""
        self._ensure_config()
        try:
            namespace = self.core_v1.read_namespace(name)
            uid: str | None = namespace.metadata.uid
            return uid
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to read namespace %s: %s", name, type(exc).__name__)
            return None

    def read_deployment_env_value(
        self,
        *,
        namespace: str,
        deployment: str,
        container: str | None = None,
        env_name: str,
    ) -> str | None:
        """Read an environment variable value from a Deployment spec.

        Raises:
            KubernetesApiPermissionError: If RBAC denies read access
            KubernetesApiNotFoundError: If deployment not found
            KubernetesClientError: Other API errors (unavailable, timeout, etc.)
        """
        self._ensure_config()
        try:
            deploy = self.apps_v1.read_namespaced_deployment(name=deployment, namespace=namespace)
            containers = deploy.spec.template.spec.containers
            target = containers[0] if containers else None
            if container:
                for c in containers:
                    if c.name == container:
                        target = c
                        break
            if target and target.env:
                for env in target.env:
                    if env.name == env_name:
                        value: str | None = env.value
                        return value
            return None
        except Exception as exc:
            _logger.debug("Failed to read deployment env %s/%s %s: %s", namespace, deployment, env_name, type(exc).__name__)
            raise translate_api_exception(
                exc,
                resource="deployment",
                namespace=namespace,
                operation="read_deployment_env_value",
            ) from exc

    def list_namespaced_pods_projected(
        self,
        *,
        namespace: str,
        label_selector: str | None = None,
        field_selector: str | None = None,
        limit: int = DEFAULT_LIMIT,
        max_items: int = DEFAULT_MAX_ITEMS,
    ) -> tuple[list[PodProjection], PaginationMetadata]:
        """List pods in a namespace with pagination and projection."""
        self._ensure_config()
        return list_namespaced_pods_projected(self, namespace=namespace, label_selector=label_selector,
            field_selector=field_selector, limit=limit, max_items=max_items)

    def list_namespaced_events_projected(
        self,
        *,
        namespace: str,
        field_selector: str | None = None,
        limit: int = DEFAULT_LIMIT,
        max_items: int = DEFAULT_MAX_ITEMS,
    ) -> tuple[list[EventProjection], PaginationMetadata]:
        """List events in a namespace with pagination and projection."""
        self._ensure_config()
        return list_namespaced_events_projected(self, namespace=namespace, field_selector=field_selector,
            limit=limit, max_items=max_items)

    def list_namespaced_deployments_projected(
        self,
        *,
        namespace: str,
        label_selector: str | None = None,
        field_selector: str | None = None,
        limit: int = DEFAULT_LIMIT,
        max_items: int = DEFAULT_MAX_ITEMS,
    ) -> tuple[list[DeploymentProjection], PaginationMetadata]:
        """List deployments in a namespace with pagination and projection."""
        self._ensure_config()
        return list_namespaced_deployments_projected(
            self,
            namespace=namespace,
            label_selector=label_selector,
            field_selector=field_selector,
            limit=limit,
            max_items=max_items,
        )

    def read_namespaced_deployment_projected(
        self,
        *,
        namespace: str,
        name: str,
    ) -> DeploymentProjection | None:
        """Read a deployment and project it."""
        self._ensure_config()
        try:
            deploy = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            return DeploymentProjection.from_dict(deploy.to_dict())
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to read deployment %s/%s: %s", namespace, name, type(exc).__name__)
            return None

    def read_namespaced_secret_projected(
        self,
        *,
        namespace: str,
        name: str,
    ) -> SecretProjection | None:
        """Read a secret metadata and project it (no data)."""
        self._ensure_config()
        try:
            secret = self.core_v1.read_namespaced_secret(name=name, namespace=namespace)
            return SecretProjection.from_dict(secret.to_dict())
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to read secret %s/%s: %s", namespace, name, type(exc).__name__)
            return None

    def read_namespaced_service_account_projected(
        self,
        *,
        namespace: str,
        name: str,
    ) -> ServiceAccountProjection | None:
        """Read a service account and project it."""
        self._ensure_config()
        try:
            sa = self.core_v1.read_namespaced_service_account(name=name, namespace=namespace)
            return ServiceAccountProjection.from_dict(sa.to_dict())
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Failed to read service account %s/%s: %s", namespace, name, type(exc).__name__)
            return None


def create_kubernetes_read_client(*, kubeconfig: str | None = None, context: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> KubernetesReadClient:
    """Factory function to create a KubernetesReadClient.
    
    Note: For production use with kubeconfig/context, use get_cached_kubernetes_client()
    which properly caches clients by (kubeconfig, context) identity.
    """
    return KubernetesReadClient(kubeconfig=kubeconfig, context=context, timeout_seconds=timeout_seconds)


def get_cached_kubernetes_client(*, kubeconfig: str | None = None, context: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> KubernetesReadClient:
    """Get or create a cached KubernetesReadClient keyed by (kubeconfig, context).

    This function caches clients by their configuration identity, ensuring that:
    - Calls with the same (kubeconfig, context) return the same client instance
    - Different kubeconfig/context combinations get different cached clients
    - The cache respects the module-level singleton pattern for in-cluster access

    For in-cluster access (kubeconfig=None, context=None), a single client is reused.
    For specific kubeconfig/context combinations, each unique combination is cached.

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
        _logger.debug("Created new cached Kubernetes client for key: kubeconfig=%s, context=%s",
                      kubeconfig, context)

    return _client_cache[cache_key]


def clear_client_cache() -> None:
    """Clear the client cache. Useful for testing."""
    global _client_cache
    _client_cache.clear()


__all__ = [
    "AppsV1Api", "ApiClient", "CoreV1Api", "clear_client_cache",
    "create_kubernetes_read_client", "get_cached_kubernetes_client",
    "DEFAULT_LIMIT", "DEFAULT_LOG_BYTES", "DEFAULT_LOG_TAIL_LINES", "DEFAULT_MAX_ITEMS",
    "DEFAULT_TIMEOUT_SECONDS", "DeploymentProjection", "EventProjection",
    "KubernetesApiNotFoundError", "KubernetesApiPermissionError",
    "KubernetesApiResponseTooLargeError", "KubernetesApiTimeoutError",
    "KubernetesClientError", "KubernetesClientUnavailableError", "KubernetesReadClient",
    "NamespaceProjection", "PaginationMetadata", "PodProjection",
    "SecretProjection", "ServiceAccountProjection", "translate_api_exception",
]
