"""Normalized error types for Kubernetes API client operations.

These errors wrap Kubernetes client exceptions and transport errors to provide
consistent error handling across all Kubernetes API operations.

Do not leak raw exception objects into incident artifacts.
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


class KubernetesClientError(Exception):
    """Base class for Kubernetes client errors."""

    def __init__(
        self,
        message: str,
        *,
        resource: str | None = None,
        namespace: str | None = None,
        operation: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.resource = resource
        self.namespace = namespace
        self.operation = operation
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        """Convert to artifact-compatible dict."""
        result: dict[str, Any] = {
            "error_type": self.__class__.__name__,
            "message": self.message,
        }
        if self.resource:
            result["resource"] = self.resource
        if self.namespace:
            result["namespace"] = self.namespace
        if self.operation:
            result["operation"] = self.operation
        return result


class KubernetesClientUnavailableError(KubernetesClientError):
    """Raised when the Kubernetes API server is unreachable.

    This includes connection refused, DNS resolution failures, and timeouts
    during connection establishment.
    """

    def __init__(
        self,
        message: str = "Kubernetes API server is unreachable",
        *,
        resource: str | None = None,
        namespace: str | None = None,
        operation: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(
            message,
            resource=resource,
            namespace=namespace,
            operation=operation,
            cause=cause,
        )


class KubernetesApiPermissionError(KubernetesClientError):
    """Raised when the client lacks permission for an API operation.

    This corresponds to HTTP 403 Forbidden responses from the Kubernetes API.
    """

    def __init__(
        self,
        message: str,
        *,
        resource: str | None = None,
        namespace: str | None = None,
        operation: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(
            message,
            resource=resource,
            namespace=namespace,
            operation=operation,
            cause=cause,
        )


class KubernetesApiNotFoundError(KubernetesClientError):
    """Raised when the requested resource does not exist.

    This corresponds to HTTP 404 Not Found responses from the Kubernetes API.
    """

    def __init__(
        self,
        message: str,
        *,
        resource: str | None = None,
        namespace: str | None = None,
        operation: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(
            message,
            resource=resource,
            namespace=namespace,
            operation=operation,
            cause=cause,
        )


class KubernetesApiTimeoutError(KubernetesClientError):
    """Raised when an API operation times out.

    This corresponds to timeout errors during API requests.
    """

    def __init__(
        self,
        message: str,
        *,
        resource: str | None = None,
        namespace: str | None = None,
        operation: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(
            message,
            resource=resource,
            namespace=namespace,
            operation=operation,
            cause=cause,
        )


class KubernetesApiResponseTooLargeError(KubernetesClientError):
    """Raised when an API response exceeds configured size limits.

    This is a safety check to prevent memory exhaustion from large responses.
    """

    def __init__(
        self,
        message: str,
        *,
        resource: str | None = None,
        namespace: str | None = None,
        operation: str | None = None,
        response_size: int | None = None,
        max_size: int | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(
            message,
            resource=resource,
            namespace=namespace,
            operation=operation,
            cause=cause,
        )
        self.response_size = response_size
        self.max_size = max_size


class KubernetesApiTooManyRequestsError(KubernetesClientError):
    """Raised when the API server returns HTTP 429 Too Many Requests.

    This indicates rate limiting is active.
    """

    def __init__(
        self,
        message: str = "Too many requests - rate limited",
        *,
        resource: str | None = None,
        namespace: str | None = None,
        operation: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(
            message,
            resource=resource,
            namespace=namespace,
            operation=operation,
            cause=cause,
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
    "KubernetesClientError",
    "KubernetesClientUnavailableError",
    "KubernetesApiPermissionError",
    "KubernetesApiNotFoundError",
    "KubernetesApiTimeoutError",
    "KubernetesApiResponseTooLargeError",
    "KubernetesApiTooManyRequestsError",
    "translate_api_exception",
]
