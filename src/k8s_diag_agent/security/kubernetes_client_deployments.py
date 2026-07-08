"""Deployment reading helpers for Kubernetes client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .kubernetes_client_constants import DEFAULT_LIMIT, DEFAULT_MAX_ITEMS
from .kubernetes_client_pagination_models import PaginationMetadata
from .kubernetes_client_translation import translate_api_exception
from .kubernetes_client_workload_models import DeploymentProjection

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


def list_namespaced_deployments_projected(
    apps_v1: Any,
    *,
    namespace: str,
    timeout_seconds: int,
    label_selector: str | None = None,
    field_selector: str | None = None,
    limit: int = DEFAULT_LIMIT,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> tuple[list[DeploymentProjection], PaginationMetadata]:
    """List deployments in a namespace with pagination and projection."""
    all_deployments: list[DeploymentProjection] = []
    continue_token: str | None = None
    remaining = 0
    truncated = False

    while True:
        try:
            response = apps_v1.list_namespaced_deployment(
                namespace=namespace,
                label_selector=label_selector,
                field_selector=field_selector,
                limit=limit,
                _continue=continue_token,
                _request_timeout=timeout_seconds,
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
        except Exception as exc:  # noqa: BLE001
            _logger.debug(
                "Failed to list deployments in %s: %s",
                namespace,
                type(exc).__name__,
            )
            break

    return all_deployments, PaginationMetadata(
        total=len(all_deployments),
        remaining=remaining,
        truncated=truncated,
        continuation_token=continue_token,
        items_returned=len(all_deployments),
    )


def read_deployment_env_value(
    apps_v1: Any,
    *,
    namespace: str,
    deployment: str,
    timeout_seconds: int,
    container: str | None = None,
    env_name: str,
) -> str | None:
    """Read an environment variable value from a Deployment spec."""
    try:
        deploy = apps_v1.read_namespaced_deployment(
            name=deployment,
            namespace=namespace,
            _request_timeout=timeout_seconds,
        )
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
        _logger.debug(
            "Failed to read deployment env %s/%s %s: %s",
            namespace,
            deployment,
            env_name,
            type(exc).__name__,
        )
        raise translate_api_exception(
            exc,
            resource="deployment",
            namespace=namespace,
            operation="read_deployment_env_value",
        ) from exc


__all__ = [
    "list_namespaced_deployments_projected",
    "read_deployment_env_value",
]
