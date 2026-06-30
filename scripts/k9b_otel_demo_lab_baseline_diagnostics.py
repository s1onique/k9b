#!/usr/bin/env python3
"""Baseline readiness failure diagnostics for OTel Demo Lab.

This module classifies baseline readiness failures to distinguish:
1. Baseline contamination by scenario scheduling constraints
2. Leftover state from a previous release/run
3. Ordinary baseline failures (image pull, CrashLoop, insufficient resources, chart issue)

Pure functions for unit testing with fake Kubernetes objects/events.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Patterns for scheduling-related failures
_SCHEDULING_PATTERNS = [
    re.compile(r"unschedulable", re.IGNORECASE),
    re.compile(r"failedscheduling", re.IGNORECASE),
    re.compile(r"no.*node.*match", re.IGNORECASE),
    re.compile(r"no.*node.*label", re.IGNORECASE),
    re.compile(r"node.*selector", re.IGNORECASE),
    re.compile(r"required.*affinity", re.IGNORECASE),
    re.compile(r"tolerations", re.IGNORECASE),
    re.compile(r"pods.*not.*schedulable", re.IGNORECASE),
]

# Patterns for image pull failures
_IMAGE_PULL_PATTERNS = [
    re.compile(r"imagepullbackoff", re.IGNORECASE),
    re.compile(r"errimagepull", re.IGNORECASE),
    re.compile(r"failed to pull image", re.IGNORECASE),
    re.compile(r"repository does not exist", re.IGNORECASE),
    re.compile(r"docker.*not.*found", re.IGNORECASE),
    re.compile(r"image.*not.*found", re.IGNORECASE),
]

# Patterns for crash loop failures
_CRASH_LOOP_PATTERNS = [
    re.compile(r"crashloopbackoff", re.IGNORECASE),
    re.compile(r"error.*crash", re.IGNORECASE),
    re.compile(r"back-off.*restarting", re.IGNORECASE),
    re.compile(r"non-zero exit code", re.IGNORECASE),
]

# Patterns for resource-related failures
_RESOURCE_PATTERNS = [
    re.compile(r"insufficient.*memory", re.IGNORECASE),
    re.compile(r"insufficient.*cpu", re.IGNORECASE),
    re.compile(r"outofmemory", re.IGNORECASE),
    re.compile(r"evicted", re.IGNORECASE),
    re.compile(r"disk pressure", re.IGNORECASE),
    re.compile(r"node.*pressure", re.IGNORECASE),
]

# Patterns for contamination by scenario injection
_SCENARIO_CONTAMINATION_PATTERNS = [
    re.compile(r"k9b\.dev/otel-lab-node", re.IGNORECASE),
]


@dataclass
class BaselineFailure:
    """Classified baseline readiness failure."""
    
    # Failure classification
    failure_class: str
    failure_reason: str
    
    # Evidence for diagnosis
    stuck_deployments: list[str] = field(default_factory=list)
    deployment_details: dict[str, dict[str, Any]] = field(default_factory=dict)
    pod_phases: dict[str, str] = field(default_factory=dict)
    waiting_reasons: dict[str, str] = field(default_factory=dict)
    scheduling_events: list[str] = field(default_factory=list)
    image_pull_errors: list[str] = field(default_factory=list)
    crash_errors: list[str] = field(default_factory=list)
    
    # Raw event lines if no useful events found
    raw_stuck_deployments: list[str] = field(default_factory=list)
    
    # Classification confidence
    is_scheduling_contamination: bool = False
    is_scenario_leftover: bool = False
    is_image_pull: bool = False
    is_crash_loop: bool = False
    is_resource_issue: bool = False
    is_unknown: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for artifact serialization."""
        return {
            "failure_class": self.failure_class,
            "failure_reason": self.failure_reason,
            "stuck_deployments": self.stuck_deployments,
            "deployment_details": self.deployment_details,
            "pod_phases": self.pod_phases,
            "waiting_reasons": self.waiting_reasons,
            "scheduling_events": self.scheduling_events,
            "image_pull_errors": self.image_pull_errors,
            "crash_errors": self.crash_errors,
            "raw_stuck_deployments": self.raw_stuck_deployments,
            "is_scheduling_contamination": self.is_scheduling_contamination,
            "is_scenario_leftover": self.is_scenario_leftover,
            "is_image_pull": self.is_image_pull,
            "is_crash_loop": self.is_crash_loop,
            "is_resource_issue": self.is_resource_issue,
            "is_unknown": self.is_unknown,
        }


def _classify_from_events(events_text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """Extract scheduling, image pull, crash, and other events from text.
    
    Returns:
        Tuple of (scheduling_events, image_pull_events, crash_events, other_events)
    """
    scheduling: list[str] = []
    image_pull: list[str] = []
    crash: list[str] = []
    other: list[str] = []
    
    for line in events_text.split("\n"):
        line_lower = line.lower()
        
        if any(p.search(line) for p in _SCHEDULING_PATTERNS):
            scheduling.append(line.strip())
        elif any(p.search(line) for p in _IMAGE_PULL_PATTERNS):
            image_pull.append(line.strip())
        elif any(p.search(line) for p in _CRASH_LOOP_PATTERNS):
            crash.append(line.strip())
        elif any(p.search(line) for p in _RESOURCE_PATTERNS):
            other.append(line.strip())
        elif "failed" in line_lower or "error" in line_lower or "backoff" in line_lower:
            other.append(line.strip())
    
    return scheduling, image_pull, crash, other


def _extract_pod_info(pod: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """Extract phase and waiting reason from pod.
    
    Returns:
        Tuple of (pod_name, phase, waiting_reason)
    """
    metadata = pod.get("metadata", {})
    status = pod.get("status", {})
    
    pod_name = metadata.get("name", "unknown")
    phase = status.get("phase", "Unknown")
    
    # Get waiting reason from container statuses
    waiting_reason = None
    container_statuses = status.get("containerStatuses", [])
    for cs in container_statuses:
        waiting = cs.get("state", {}).get("waiting", {})
        if waiting:
            waiting_reason = waiting.get("reason", "")
            break
    
    return pod_name, phase, waiting_reason


def _has_scheduling_constraints(
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
                if _is_scenario_specific_toleration(t)
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


def _is_scenario_specific_toleration(toleration: dict[str, Any]) -> bool:
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
    
    # Default Kubernetes toleration keys
    default_keys = {
        "node.kubernetes.io/not-ready",
        "node.kubernetes.io/unreachable",
        "node.kubernetes.io/disk-pressure",
        "node.kubernetes.io/memory-pressure",
        "node.kubernetes.io/pid-pressure",
        "node.kubernetes.io/unschedulable",
        "node.kubernetes.io/network-unavailable",
    }
    
    # Check if it's a default key (exact match or prefix match for sub-keys)
    for default_key in default_keys:
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


def classify_baseline_failure(
    pods_data: dict[str, Any] | None = None,
    deployments_data: dict[str, Any] | None = None,
    events_text: str | None = None,
    stuck_deployment_names: list[str] | None = None,
) -> BaselineFailure:
    """Classify a baseline readiness failure from collected artifacts.
    
    This is a pure function that can be tested with fake Kubernetes objects.
    
    Args:
        pods_data: PodList JSON from kubectl get pods -o json
        deployments_data: DeploymentList JSON from kubectl get deployments -o json
        events_text: Events text from kubectl get events
        stuck_deployment_names: List of deployment names that failed readiness
        
    Returns:
        BaselineFailure with classification and evidence
    """
    # Initialize result
    result = BaselineFailure(
        failure_class="baseline_readiness_timeout",
        failure_reason="Baseline readiness timeout",
    )
    
    # Track what we find
    scheduling_events: list[str] = []
    image_pull_events: list[str] = []
    crash_events: list[str] = []
    
    # Process events if available
    if events_text:
        sched, img, crash, _ = _classify_from_events(events_text)
        scheduling_events.extend(sched)
        image_pull_events.extend(img)
        crash_events.extend(crash)
        result.scheduling_events = scheduling_events
        result.image_pull_errors = image_pull_events
        result.crash_errors = crash_events
    
    # Process pods if available
    if pods_data and "items" in pods_data:
        for pod in pods_data["items"]:
            pod_name, phase, waiting_reason = _extract_pod_info(pod)
            result.pod_phases[pod_name] = phase
            if waiting_reason:
                result.waiting_reasons[pod_name] = waiting_reason
                
                # Classify based on waiting reason
                waiting_lower = waiting_reason.lower()
                if any(p.search(waiting_lower) for p in _IMAGE_PULL_PATTERNS):
                    result.is_image_pull = True
                elif any(p.search(waiting_lower) for p in _CRASH_LOOP_PATTERNS):
                    result.is_crash_loop = True
                elif any(p.search(waiting_lower) for p in _SCHEDULING_PATTERNS):
                    result.is_scheduling_contamination = True
            
            # Check for scheduling constraints in pod spec
            # Pass is_live_pod=True since this is a live pod from the cluster
            pod_spec = pod.get("spec", {})
            _, constraints = _has_scheduling_constraints(pod_spec, is_live_pod=True)
            if constraints:
                result.deployment_details[pod_name] = {
                    "has_scheduling_constraints": True,
                    "constraints": constraints,
                }
    
    # Process deployments if available
    if deployments_data and "items" in deployments_data:
        for deploy in deployments_data["items"]:
            deploy_name = deploy.get("metadata", {}).get("name", "unknown")
            if deploy_name in (stuck_deployment_names or []):
                result.stuck_deployments.append(deploy_name)
                
                # Extract pod template scheduling constraints
                template = deploy.get("spec", {}).get("template", {})
                _, constraints = _has_scheduling_constraints(template)
                if constraints:
                    result.deployment_details[deploy_name] = {
                        "has_scheduling_constraints": True,
                        "constraints": constraints,
                    }
    
    # If no structured data, record raw stuck deployments
    if stuck_deployment_names and not pods_data and not deployments_data:
        result.raw_stuck_deployments = stuck_deployment_names
    
    # Classification logic
    # 1. Check for scenario contamination (scheduling constraints present)
    deployment_has_scheduling = any(
        d.get("has_scheduling_constraints", False)
        for d in result.deployment_details.values()
    )
    
    # Check if any scheduling constraints contain scenario-specific labels
    scenario_contamination = False
    for deploy_info in result.deployment_details.values():
        constraints = deploy_info.get("constraints", {})
        ns_value = constraints.get("nodeSelector", {}).get("k9b.dev/otel-lab-node")
        if ns_value:
            scenario_contamination = True
            break
    
    if deployment_has_scheduling or scenario_contamination:
        result.is_scheduling_contamination = True
        result.failure_class = "baseline_contamination_scheduling"
        result.failure_reason = (
            "Baseline contaminated: deployment has pre-existing scheduling constraints. "
            "This may be from a previous scenario injection that was not cleaned up."
        )
        return result
    
    # 2. Check for scheduling events
    if scheduling_events:
        result.is_scheduling_contamination = True
        result.failure_class = "baseline_scheduling_failure"
        result.failure_reason = "Baseline failed due to scheduling constraints (FailedScheduling events present)"
        return result
    
    # 3. Check for image pull errors
    if image_pull_events:
        result.is_image_pull = True
        result.failure_class = "baseline_image_pull_failure"
        result.failure_reason = "Baseline failed due to image pull errors"
        return result
    
    # 4. Check for crash loop errors
    if crash_events:
        result.is_crash_loop = True
        result.failure_class = "baseline_crash_loop_failure"
        result.failure_reason = "Baseline failed due to container crash loop"
        return result
    
    # 5. Check for resource issues
    for line in events_text.split("\n") if events_text else []:
        if any(p.search(line) for p in _RESOURCE_PATTERNS):
            result.is_resource_issue = True
            result.failure_class = "baseline_resource_failure"
            result.failure_reason = "Baseline failed due to resource constraints"
            return result
    
    # 6. Unknown failure - include raw stuck deployments
    result.is_unknown = True
    result.failure_class = "baseline_readiness_timeout"
    result.failure_reason = f"Baseline readiness timeout for: {', '.join(stuck_deployment_names or ['unknown'])}"
    
    return result


def check_baseline_purity(
    deployment: dict[str, Any],
    scenario: str | None = None,
    pods_data: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Check if baseline deployment is pure (no scenario contamination).
    
    This function inspects a deployment object AND live pods to detect if
    scheduling constraints are already present before scenario injection.
    
    Args:
        deployment: Deployment object from kubectl get deployment -o json
        scenario: Selected incident scenario (e.g., "unschedulable-shipping")
        pods_data: Optional PodList JSON from kubectl get pods -o json
            Used to detect contamination on live pods (e.g., shipping stuck Pending
            with impossible nodeSelector from a previous run).
        
    Returns:
        Tuple of (is_pure, error_message). is_pure=True means no contamination.
    """
    if scenario != "unschedulable-shipping":
        # No purity check needed for other scenarios
        return True, ""
    
    # Extract pod template from deployment
    pod_template = deployment.get("spec", {}).get("template", {})
    spec = pod_template.get("spec", {})
    
    errors: list[str] = []
    
    # Check nodeSelector on deployment template
    node_selector = spec.get("nodeSelector")
    if node_selector:
        # Check if it contains the scenario-specific label
        if "k9b.dev/otel-lab-node" in node_selector:
            errors.append(
                f"Baseline contaminated before unschedulable-shipping injection: "
                f"shipping deployment template has pre-existing nodeSelector with "
                f"k9b.dev/otel-lab-node={node_selector.get('k9b.dev/otel-lab-node')}"
            )
        else:
            errors.append(
                f"Baseline has pre-existing nodeSelector on deployment template: {node_selector}"
            )
    
    # Check affinity on deployment template
    affinity = spec.get("affinity")
    if affinity:
        errors.append("Baseline has pre-existing affinity configuration on deployment template")
    
    # Check tolerations on deployment template (only non-default)
    tolerations = spec.get("tolerations")
    if tolerations:
        scenario_tolerations = [
            t for t in tolerations
            if _is_scenario_specific_toleration(t)
        ]
        if scenario_tolerations:
            errors.append(f"Baseline has scenario-specific tolerations: {scenario_tolerations}")
    
    # Check live pods for contamination
    # This catches cases where shipping is already stuck Pending from a previous run
    if pods_data and "items" in pods_data:
        for pod in pods_data["items"]:
            pod_name = pod.get("metadata", {}).get("name", "")
            
            # Only check shipping pods
            if not pod_name.startswith("shipping"):
                continue
            
            pod_spec = pod.get("spec", {})
            pod_node_selector = pod_spec.get("nodeSelector")
            
            if pod_node_selector and "k9b.dev/otel-lab-node" in pod_node_selector:
                phase = pod.get("status", {}).get("phase", "Unknown")
                value = pod_node_selector.get("k9b.dev/otel-lab-node")
                errors.append(
                    f"Baseline contaminated: live shipping pod '{pod_name}' has "
                    f"k9b.dev/otel-lab-node={value} (phase={phase}). "
                    f"This may be contamination from a previous run that was not cleaned up."
                )
    
    if errors:
        return False, "; ".join(errors)
    
    return True, ""


# Re-exports for backward compatibility
__all__ = [
    "BaselineFailure",
    "classify_baseline_failure",
    "check_baseline_purity",
    "_has_scheduling_constraints",
    "_extract_pod_info",
]
