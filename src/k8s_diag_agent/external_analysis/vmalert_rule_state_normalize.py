"""vmalert rule-state label derivation and string normalization helpers.

Moved from vmalert_rule_state.py as a focused extraction seam.
These helpers derive diagnostic context (namespace, workload, severity) from
alert labels and truncate strings to bounded lengths.
"""

from __future__ import annotations

from collections.abc import Mapping

# Severity mapping from common label conventions
_SEVERITY_PRIORITY: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "warning": 2,
    "info": 3,
    "debug": 4,
}

# Maximum string length for label and annotation fields
_MAX_STRING_LENGTH = 200


def _extract_severity_from_labels(labels: Mapping[str, str]) -> str | None:
    """Extract severity from labels using common conventions."""
    # Direct severity label
    severity = labels.get("severity")
    if severity:
        return severity.lower()

    # Kubernetes severity conventions
    for key in ("k8s_severity", "alertseverity", "priority"):
        sev = labels.get(key)
        if sev:
            return sev.lower()

    return None


def _derive_namespace_from_labels(labels: Mapping[str, str]) -> str | None:
    """Derive namespace from labels if present."""
    # Direct namespace label
    ns = labels.get("namespace")
    if ns:
        return ns

    # Kubernetes workload conventions
    for key in ("k8s_namespace", "ns", "kubernetes_namespace"):
        namespace = labels.get(key)
        if namespace:
            return namespace

    return None


def _derive_workload_from_labels(labels: Mapping[str, str]) -> str | None:
    """Derive workload/workload name from labels."""
    # Direct workload label
    wl = labels.get("workload")
    if wl:
        return wl

    # Kubernetes workload conventions
    for key in ("workload_name", "k8s_workload", "deployment", "statefulset", "daemonset"):
        workload = labels.get(key)
        if workload:
            return workload

    # Pod name can indicate workload
    pod = labels.get("pod")
    if pod:
        # Strip common suffixes: -hash, -random, -index
        # This is heuristic, not exact
        return pod.rsplit("-", 2)[0] if "-" in pod else pod

    return None


def _truncate_string(s: str | None, max_len: int) -> str | None:
    """Truncate string to max length."""
    if s is None:
        return None
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


__all__ = [
    "_MAX_STRING_LENGTH",
    "_SEVERITY_PRIORITY",
    "_derive_namespace_from_labels",
    "_derive_workload_from_labels",
    "_extract_severity_from_labels",
    "_truncate_string",
]
