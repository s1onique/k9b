"""Scheduling constraint helpers for baseline contamination detection.

This module provides pure functions to detect scheduling constraints on pods
and pod templates, distinguishing default Kubernetes tolerations from
scenario-specific contamination.
"""

from __future__ import annotations

from typing import Any

# Default Kubernetes toleration keys - these are automatically added by Kubernetes
# and should NOT be flagged as contamination
_DEFAULT_KUBERNETES_TOLERATION_KEYS = {
    "node.kubernetes.io/not-ready",
    "node.kubernetes.io/unreachable",
    "node.kubernetes.io/disk-pressure",
    "node.kubernetes.io/memory-pressure",
    "node.kubernetes.io/pid-pressure",
    "node.kubernetes.io/unschedulable",
    "node.kubernetes.io/network-unavailable",
}


def is_scenario_specific_toleration(toleration: dict[str, Any]) -> bool:
    """Check if a toleration is scenario-specific (not a default Kubernetes toleration).

    Default Kubernetes tolerations include:
    - node.kubernetes.io/not-ready
    - node.kubernetes.io/unreachable
    - node.kubernetes.io/disk-pressure
    - node.kubernetes.io/memory-pressure
    - node.kubernetes.io/pid-pressure
    - node.kubernetes.io/unschedulable
    - node.kubernetes.io/network-unavailable

    These are automatically added by Kubernetes and should not be considered contamination.
    """
    key = toleration.get("key", "")
    if not key:
        return False

    # Check if it's a default key (exact match or prefix match for sub-keys)
    for default_key in _DEFAULT_KUBERNETES_TOLERATION_KEYS:
        if key == default_key or key.startswith(f"{default_key}:"):
            return False

    # Check for scenario-specific patterns
    scenario_patterns = [
        "k9b.dev/",
        "otel-lab",
        "special-node",
    ]

    for pattern in scenario_patterns:
        if pattern.lower() in key.lower():
            return True

    # Any other custom toleration key is potentially scenario-specific
    return True


def has_scheduling_constraints(
    pod_or_template: dict[str, Any],
    *,
    is_live_pod: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """Check if a pod or pod template has scheduling constraints.

    Args:
        pod_or_template: Either a pod object or a pod template (spec.template.spec)
        is_live_pod: If True, this is a live pod object (not a deployment template).
            Live pods may have default Kubernetes tolerations that are not contamination.

    Returns:
        Tuple of (has_constraints, constraint_details)
    """
    # Determine if this is a full pod or a pod template by checking for "metadata"
    if "metadata" in pod_or_template:
        # This is a full pod object - get the spec
        spec = pod_or_template.get("spec", {})
    else:
        # This is already a pod template/spec
        spec = pod_or_template

    constraints: dict[str, Any] = {}
    has_constraints = False

    # Check nodeSelector - always suspicious for scheduling
    node_selector = spec.get("nodeSelector")
    if node_selector:
        has_constraints = True
        constraints["nodeSelector"] = node_selector

    # Check affinity - always suspicious for scheduling
    affinity = spec.get("affinity")
    if affinity:
        has_constraints = True
        constraints["affinity"] = affinity

    # Check tolerations
    # Only flag as contamination if scenario-specific or non-default
    # Default Kubernetes tolerations (node.kubernetes.io/not-ready, etc.) are normal
    tolerations = spec.get("tolerations")
    if tolerations:
        if is_live_pod:
            # For live pods, only flag scenario-specific tolerations
            scenario_tolerations = [
                t for t in tolerations
                if is_scenario_specific_toleration(t)
            ]
            if scenario_tolerations:
                has_constraints = True
                constraints["tolerations"] = scenario_tolerations
        else:
            # For deployment templates, flag any tolerations as potentially suspicious
            # (templates should not have scheduling constraints in baseline)
            has_constraints = True
            constraints["tolerations"] = tolerations

    return has_constraints, constraints
