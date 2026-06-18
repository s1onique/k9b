"""Fake in-memory handlers for read-only checks.

This module provides deterministic fake handlers for testing the check runner.
Each handler produces fake evidence without calling Kubernetes.

Design constraints:
- Pure functions only
- No external dependencies
- Deterministic with injected timestamps
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol


__all__ = [
    "ReadOnlyCheckHandler",
    "FAKE_HANDLERS",
    "DEFAULT_MAX_CHECKS_TO_RUN",
    "DEFAULT_MAX_RESULT_CHARS",
    "DEFAULT_MAX_SUMMARY_CHARS",
]


# =============================================================================
# Constants
# =============================================================================

DEFAULT_MAX_CHECKS_TO_RUN = 5
DEFAULT_MAX_RESULT_CHARS = 2000
DEFAULT_MAX_SUMMARY_CHARS = 500


# =============================================================================
# Handler Protocol
# =============================================================================


class ReadOnlyCheckHandler(Protocol):
    """Protocol for read-only check handlers."""

    def __call__(self, check: Mapping[str, object], *, now: datetime) -> Mapping[str, object]:
        """Execute a fake read-only check.

        Args:
            check: The validated check spec
            now: Injected timestamp for deterministic results

        Returns:
            Dict with 'summary', 'observations', and any other evidence keys
        """
        ...


# =============================================================================
# Utility
# =============================================================================


def _truncate(s: str, max_chars: int) -> str:
    """Truncate string to max_chars, adding ellipsis if truncated."""
    if len(s) <= max_chars:
        return s
    return s[:max_chars - 3] + "..."


def _make_fake_evidence(summary: str, observations: list[str]) -> dict[str, Any]:
    """Create bounded fake evidence dict."""
    return {
        "summary": _truncate(summary, DEFAULT_MAX_SUMMARY_CHARS),
        "observations": observations,
        "fake_handler": True,
        "no_kubernetes_call": True,
    }


# =============================================================================
# Fake Handlers
# =============================================================================


def _fake_pod_logs_handler(check: Mapping[str, object], *, now: datetime) -> Mapping[str, object]:
    """Fake handler for pod_logs check."""
    params = check.get("parameters", {})
    namespace = params.get("namespace", "unknown")
    object_name = params.get("object_name", "unknown")
    container = params.get("container", "default")

    summary = f"Fake pod logs checked for {namespace}/{object_name} (container: {container})"
    return _make_fake_evidence(
        summary=summary,
        observations=[
            "fake handler only - no Kubernetes call was made",
            f"timestamp: {now.isoformat()}",
            f"requested namespace: {namespace}",
            f"requested object: {object_name}",
        ],
    )


def _fake_pod_events_handler(check: Mapping[str, object], *, now: datetime) -> Mapping[str, object]:
    """Fake handler for pod_events check."""
    params = check.get("parameters", {})
    namespace = params.get("namespace", "unknown")
    object_name = params.get("object_name", "unknown")
    object_kind = params.get("object_kind", "Pod")

    summary = f"Fake events checked for {namespace}/{object_name} ({object_kind})"
    return _make_fake_evidence(
        summary=summary,
        observations=[
            "fake handler only - no Kubernetes call was made",
            f"timestamp: {now.isoformat()}",
            f"requested namespace: {namespace}",
            f"requested object: {object_name}",
            f"requested kind: {object_kind}",
        ],
    )


def _fake_deployment_status_handler(check: Mapping[str, object], *, now: datetime) -> Mapping[str, object]:
    """Fake handler for deployment_status check."""
    params = check.get("parameters", {})
    namespace = params.get("namespace", "unknown")
    object_name = params.get("object_name", "unknown")

    summary = f"Fake deployment status checked for {namespace}/{object_name}"
    return _make_fake_evidence(
        summary=summary,
        observations=[
            "fake handler only - no Kubernetes call was made",
            f"timestamp: {now.isoformat()}",
            f"requested namespace: {namespace}",
            f"requested deployment: {object_name}",
        ],
    )


def _fake_node_status_handler(check: Mapping[str, object], *, now: datetime) -> Mapping[str, object]:
    """Fake handler for node_status check."""
    params = check.get("parameters", {})
    node_name = params.get("node_name", "unknown")

    summary = f"Fake node status checked for {node_name}"
    return _make_fake_evidence(
        summary=summary,
        observations=[
            "fake handler only - no Kubernetes call was made",
            f"timestamp: {now.isoformat()}",
            f"requested node: {node_name}",
        ],
    )


def _fake_service_endpoints_handler(check: Mapping[str, object], *, now: datetime) -> Mapping[str, object]:
    """Fake handler for service_endpoints check."""
    params = check.get("parameters", {})
    namespace = params.get("namespace", "unknown")
    object_name = params.get("object_name", "unknown")

    summary = f"Fake service endpoints checked for {namespace}/{object_name}"
    return _make_fake_evidence(
        summary=summary,
        observations=[
            "fake handler only - no Kubernetes call was made",
            f"timestamp: {now.isoformat()}",
            f"requested namespace: {namespace}",
            f"requested service: {object_name}",
        ],
    )


# Registry of fake handlers for known read-only check IDs
FAKE_HANDLERS: dict[str, ReadOnlyCheckHandler] = {
    "pod_logs": _fake_pod_logs_handler,
    "pod_events": _fake_pod_events_handler,
    "deployment_status": _fake_deployment_status_handler,
    "node_status": _fake_node_status_handler,
    "service_endpoints": _fake_service_endpoints_handler,
}
