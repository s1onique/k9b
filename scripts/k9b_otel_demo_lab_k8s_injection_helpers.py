#!/usr/bin/env python3
"""Kubectl helper functions for K8s incident injection.

This module contains utility functions for kubectl operations:
- Deployment scaling
- Pod template extraction
- JSON artifact writing
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from scripts.k9b_lab_common_helpers import (
    KubectlResult,
    kubectl_scale,
    write_json_artifact,
)

if TYPE_CHECKING:
    from scripts.k9b_otel_demo_lab_types import LabPhaseResult


def _extract_pod_template(deployment: dict[str, Any]) -> dict[str, Any]:
    """Extract the pod template from a deployment spec.
    
    Args:
        deployment: Deployment dict from Kubernetes API
        
    Returns:
        Pod template dict
    """
    spec = deployment.get("spec", {})
    template = spec.get("template", {})
    return cast(dict[str, Any], template)


def _extract_node_selector(pod_template: dict[str, Any]) -> dict[str, str] | None:
    """Extract the nodeSelector from a pod template.
    
    Args:
        pod_template: Pod template dict
        
    Returns:
        Node selector dict or None if not present
    """
    spec = pod_template.get("spec", {})
    node_selector: dict[str, str] | None = spec.get("nodeSelector")
    return node_selector


def _kubectl_scale(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    replicas: int,
) -> KubectlResult:
    """Scale a deployment to the specified replica count.
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace
        deployment: Deployment name
        replicas: Target replica count
        
    Returns:
        KubectlResult with success status and output
    """
    return cast(KubectlResult, kubectl_scale(kubeconfig, namespace, deployment, replicas))


def _write_injection_artifacts(
    injection_dir: Path,
    evidence: dict[str, Any],
    previous_template: dict[str, Any] | None,
) -> dict[str, Any]:
    """Write injection artifacts to disk.
    
    Args:
        injection_dir: Directory for injection artifacts
        evidence: Evidence dict
        previous_template: Previous pod template if captured
        
    Returns:
        Dict of artifact paths
    """
    artifact_paths: dict[str, Any] = {}
    
    # Write evidence
    evidence_path = injection_dir / "injection-evidence.json"
    write_json_artifact(injection_dir, "injection-evidence.json", evidence)
    artifact_paths["evidence"] = str(evidence_path)
    
    # Write previous template if captured
    if previous_template:
        template_path = injection_dir / "previous-pod-template.json"
        write_json_artifact(injection_dir, "previous-pod-template.json", previous_template)
        artifact_paths["previous_template"] = str(template_path)
    
    return artifact_paths


def _fail_phase(
    phase_dir: Path,
    start: float,
    error_msg: str,
    evidence: dict[str, Any],
) -> LabPhaseResult:
    """Create a failed phase result.
    
    Args:
        phase_dir: Phase directory
        start: Start time (time.time())
        error_msg: Error message
        evidence: Evidence dict
        
    Returns:
        LabPhaseResult with failure info
    """
    import time as time_module

    from scripts.k9b_otel_demo_lab_types import LabPhaseResult  # noqa: F401

    duration = time_module.time() - start
    
    injection_dir = phase_dir / "p2b-k8s-injection"
    injection_dir.mkdir(parents=True, exist_ok=True)
    evidence["error"] = error_msg
    write_json_artifact(injection_dir, "injection-evidence.json", evidence)
    
    return LabPhaseResult(
        phase="p2b-k8s-injection",
        success=False,
        message=f"Injection failed: {error_msg}",
        artifacts={
            "injection_dir": str(injection_dir),
            "error": error_msg,
        },
        duration_seconds=duration,
    )
