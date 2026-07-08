"""Error translation helpers for Kubernetes API exceptions.

This module contains the translate_api_exception function which is critical
for maintaining the error contract. Do not modify error translation behavior
without considering downstream impact.
"""

from __future__ import annotations

from .kubernetes_client_errors import (
    KubernetesApiNotFoundError,
    KubernetesApiPermissionError,
    KubernetesApiTimeoutError,
    KubernetesApiTooManyRequestsError,
    KubernetesClientError,
    KubernetesClientUnavailableError,
)


def translate_api_exception(
    exc: Exception,
    *,
    resource: str | None = None,
    namespace: str | None = None,
    operation: str | None = None,
) -> KubernetesClientError:
    """Translate a Kubernetes client exception to a normalized error.

    Args:
        exc: The original exception (ApiException or transport error)
        resource: The resource type being operated on
        namespace: The namespace (if applicable)
        operation: The operation being performed

    Returns:
        A normalized KubernetesClientError subclass
    """
    # Handle ApiException from kubernetes client
    if hasattr(exc, "status"):
        status = exc.status
        if status == 403:
            reason = getattr(exc, "reason", "Forbidden")
            return KubernetesApiPermissionError(
                f"Permission denied: {reason}",
                resource=resource,
                namespace=namespace,
                operation=operation,
                cause=exc,
            )
        elif status == 404:
            body = getattr(exc, "body", "")
            return KubernetesApiNotFoundError(
                f"Resource not found: {body}",
                resource=resource,
                namespace=namespace,
                operation=operation,
                cause=exc,
            )
        elif status == 408:
            return KubernetesApiTimeoutError(
                "Request timed out",
                resource=resource,
                namespace=namespace,
                operation=operation,
                cause=exc,
            )
        elif status == 429:
            return KubernetesApiTooManyRequestsError(
                "Too many requests",
                resource=resource,
                namespace=namespace,
                operation=operation,
                cause=exc,
            )
        elif status >= 500:
            return KubernetesClientUnavailableError(
                f"Server error: {status}",
                resource=resource,
                namespace=namespace,
                operation=operation,
                cause=exc,
            )
        else:
            return KubernetesClientError(
                f"API error: {status}",
                resource=resource,
                namespace=namespace,
                operation=operation,
                cause=exc,
            )

    # Handle transport/socket errors
    exc_name = type(exc).__name__.lower()
    if any(term in exc_name for term in ["timeout", "timedout", "connect", "socket", "dns"]):
        return KubernetesClientUnavailableError(
            f"Connection failed: {exc}",
            resource=resource,
            namespace=namespace,
            operation=operation,
            cause=exc,
        )

    # Default: wrap as generic error
    return KubernetesClientError(
        str(exc),
        resource=resource,
        namespace=namespace,
        operation=operation,
        cause=exc,
    )


__all__ = [
    "translate_api_exception",
]
