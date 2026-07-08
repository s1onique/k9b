"""CRD reading helpers for Kubernetes client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .kubernetes_client_crd_models import CrdSummary
from .kubernetes_client_translation import translate_api_exception

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


def list_crds(
    api_client: Any,
    *,
    timeout_seconds: int,
) -> list[CrdSummary]:
    """List all CustomResourceDefinitions with the Python client.

    This replaces: kubectl get crds -o json

    Note: CRD listing requires cluster-scope RBAC permissions.
    Raises KubernetesApiPermissionError if RBAC denies access.

    Args:
        api_client: ApiClient instance
        timeout_seconds: API timeout

    Returns:
        List of CrdSummary

    Raises:
        KubernetesApiPermissionError: If RBAC denies CRD access
        KubernetesClientError: Other API errors
    """
    try:
        from kubernetes.client import ApiextensionsV1Api
    except ImportError as exc:
        from .kubernetes_client_errors import KubernetesClientError
        raise KubernetesClientError(
            "apiextensions client not available. Upgrade kubernetes package.",
            cause=exc,
        ) from exc

    try:
        apiextensions = ApiextensionsV1Api(api_client=api_client)
        response = apiextensions.list_custom_resource_definition(
            _request_timeout=timeout_seconds,
        )
    except Exception as exc:
        raise translate_api_exception(
            exc,
            resource="CustomResourceDefinition",
            operation="list_crds",
        ) from exc

    return [CrdSummary.from_dict(item.to_dict()) for item in (response.items or [])]


__all__ = [
    "list_crds",
]
