"""Convenience functions for bounded kubectl collection."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import datetime

from .kubectl_invocation import DEFAULT_TIMEOUT_SECONDS

_logger = logging.getLogger(__name__)

# Default chunk size for large collections
DEFAULT_CHUNK_SIZE = 500

# Resources that should ALWAYS use --chunk-size
_ALWAYS_CHUNKED = frozenset({
    "pods",
    "events",
    "nodes",
    "services",
    "endpoints",
    "persistentvolumeclaims",
    "persistentvolumes",
    "configmaps",
    "secrets",
    "ingresses",
    "jobs",
    "cronjobs",
    "daemonsets",
    "replicasets",
    "deployments",
    "statefulsets",
    "horizontalpodautoscalers",
    "poddisruptionbudgets",
    "networkpolicies",
    "serviceaccounts",
    "roles",
    "rolebindings",
    "clusterroles",
    "clusterrolebindings",
    "limitranges",
    "resourcequotas",
    "namespaces",
})


def build_bounded_kubectl_get(
    resource: str,
    namespace: str | None = None,
    all_namespaces: bool = False,
    output_format: str = "json",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    field_selector: str | None = None,
    label_selector: str | None = None,
    sort_by: str | None = None,
    field_manager: str | None = None,
    context: str | None = None,
) -> list[str]:
    """Build a bounded kubectl get command with safe defaults.

    This function constructs kubectl commands that:
    - Use --chunk-size for large collections
    - Include --request-timeout
    - Prefer namespace-scoped calls
    - Use field/label selectors when possible
    """
    cmd = ["kubectl", "get", resource]

    if all_namespaces:
        cmd.append("--all-namespaces")
    elif namespace:
        cmd.extend(["-n", namespace])

    if output_format:
        cmd.extend(["-o", output_format])

    cmd.extend(["--request-timeout", str(timeout_seconds)])

    if resource in _ALWAYS_CHUNKED or all_namespaces:
        cmd.extend(["--chunk-size", str(chunk_size)])

    if field_selector:
        cmd.extend(["--field-selector", field_selector])

    if label_selector:
        cmd.extend(["--label-selector", label_selector])

    if sort_by:
        cmd.extend(["--sort-by", sort_by])

    if field_manager:
        cmd.extend(["--field-manager", field_manager])

    return cmd


def collect_events_bounded(
    run_kubectl_func: Callable[..., str],
    context: str | None = None,
    namespace: str | None = None,
    since_hours: int | None = None,
    event_type: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_events: int = 100,
    run_id: str | None = None,
) -> list[dict[str, object]]:
    """Collect events with bounded output using field selectors."""
    field_selectors: list[str] = []

    if event_type:
        field_selectors.append(f"type={event_type}")

    cmd = ["kubectl", "get", "events"]

    if namespace:
        cmd.extend(["-n", namespace])
    else:
        cmd.append("--all-namespaces")

    if field_selectors:
        cmd.extend(["--field-selector", ",".join(field_selectors)])

    cmd.extend(["-o", "json"])
    cmd.extend(["--request-timeout", str(timeout_seconds)])
    cmd.extend(["--chunk-size", str(min(max_events * 2, DEFAULT_CHUNK_SIZE))])
    cmd.extend(["--sort-by", ".metadata.creationTimestamp"])

    output = run_kubectl_func(cmd, timeout_seconds=timeout_seconds, run_id=run_id)

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        _logger.warning("Failed to parse events JSON: %s", exc)
        return []

    items = payload.get("items", []) if isinstance(payload, dict) else []

    if since_hours:
        cutoff = time.time() - (since_hours * 3600)
        filtered = []
        for item in items:
            metadata = item.get("metadata", {})
            creation_ts = metadata.get("creationTimestamp")
            if creation_ts:
                try:
                    dt = datetime.fromisoformat(creation_ts.replace("Z", "+00:00"))
                    if dt.timestamp() >= cutoff:
                        filtered.append(item)
                except (ValueError, TypeError):
                    filtered.append(item)
            else:
                filtered.append(item)
        items = filtered

    return items[:max_events]


def collect_pods_bounded(
    run_kubectl_func: Callable[..., str],
    context: str | None = None,
    namespace: str | None = None,
    all_namespaces: bool = False,
    label_selector: str | None = None,
    field_selector: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_pods: int = 500,
    run_id: str | None = None,
) -> list[dict[str, object]]:
    """Collect pods with bounded output using selectors."""
    cmd = ["kubectl", "get", "pods"]

    if all_namespaces:
        cmd.append("--all-namespaces")
    elif namespace:
        cmd.extend(["-n", namespace])

    if label_selector:
        cmd.extend(["--label-selector", label_selector])

    if field_selector:
        cmd.extend(["--field-selector", field_selector])

    cmd.extend(["-o", "json"])
    cmd.extend(["--request-timeout", str(timeout_seconds)])
    cmd.extend(["--chunk-size", str(min(max_pods * 2, DEFAULT_CHUNK_SIZE))])

    output = run_kubectl_func(cmd, timeout_seconds=timeout_seconds, run_id=run_id)

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        _logger.warning("Failed to parse pods JSON: %s", exc)
        return []

    items = payload.get("items", []) if isinstance(payload, dict) else []
    return items[:max_pods]
