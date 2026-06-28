#!/usr/bin/env python3
"""OTel Demo Lab phases - one function per phase.

This module contains the implementation of each lab phase.
Import individual phase functions from this module.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import (
    kubectl_events,
    kubectl_json,
    log,
    write_json_artifact,
    write_text_artifact,
)
from .k9b_lab_common_readiness import (
    collect_namespace_snapshot,
    wait_for_deployments_ready,
)
from .k9b_otel_demo_lab_constants import (
    PHASE_CLUSTER_BASELINE,
    PHASE_DIAGNOSIS,
    PHASE_DISCOVERY,
    PHASE_INJECTED,
    PHASE_OTEL_BASELINE,
    PHASE_VERIFICATION,
    REQUIRED_DEPLOYMENTS,
)
from .k9b_otel_demo_lab_types import LabConfig, LabPhaseResult


def phase0_cluster_baseline(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 0: Collect cluster and k9b baseline."""
    start = time.time()
    phase_dir = artifact_dir / PHASE_CLUSTER_BASELINE
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    artifacts: dict[str, Any] = {}
    
    # Get cluster nodes
    nodes_result = kubectl_json(config.kubeconfig, "nodes")
    if nodes_result.success and nodes_result.data:
        nodes_path = write_json_artifact(phase_dir, "nodes.json", nodes_result.data)
        artifacts["nodes"] = str(nodes_path)
    
    # Get namespaces
    ns_result = kubectl_json(config.kubeconfig, "namespaces")
    if ns_result.success and ns_result.data:
        ns_path = write_json_artifact(phase_dir, "namespaces.json", ns_result.data)
        artifacts["namespaces"] = str(ns_path)
    
    # Get k9b pods if it exists
    k9b_ns = "k9b"  # k9b namespace
    k9b_result = kubectl_json(config.kubeconfig, "pods", k9b_ns)
    if k9b_result.success and k9b_result.data:
        k9b_path = write_json_artifact(phase_dir, "k9b-pods.json", k9b_result.data)
        artifacts["k9b_pods"] = str(k9b_path)
    
    # Get k9b service
    k9b_svc_result = kubectl_json(config.kubeconfig, "services", k9b_ns)
    if k9b_svc_result.success and k9b_svc_result.data:
        k9b_svc_path = write_json_artifact(phase_dir, "k9b-service.json", k9b_svc_result.data)
        artifacts["k9b_service"] = str(k9b_svc_path)
    
    duration = time.time() - start
    return LabPhaseResult(
        phase=PHASE_CLUSTER_BASELINE,
        success=True,
        message=f"Cluster baseline collected: {len(artifacts)} artifacts",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def phase1_deploy_otel_demo(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 1: Deploy OpenTelemetry Demo via Helm."""
    start = time.time()
    phase_dir = artifact_dir / PHASE_OTEL_BASELINE
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    log(f"Adding Helm repo: {config.helm_repo_name} -> {config.helm_repo_url}")
    
    # Add Helm repo with proper URL
    add_repo_cmd = ["helm", "repo", "add", config.helm_repo_name, config.helm_repo_url]
    result = subprocess.run(add_repo_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return LabPhaseResult(
            phase=PHASE_OTEL_BASELINE,
            success=False,
            message=f"Failed to add Helm repo: {result.stderr}",
            duration_seconds=time.time() - start,
        )
    
    # Update Helm repos
    subprocess.run(["helm", "repo", "update"], capture_output=True)
    
    # Write Helm install log
    helm_log_path = phase_dir / "helm-install.log"
    
    # Install OTel Demo using chart reference
    install_cmd = [
        "helm", "upgrade", "--install", config.helm_release,
        config.helm_chart,
        "--namespace", config.namespace,
        "--create-namespace",
        "--version", config.helm_chart_version,
        "--values", "-",  # Use stdin for values
    ]
    
    # Minimal values to enable feature flags
    values = """
recommendation:
  featureFlags:
    - name: recommendationServiceCacheFailure
      enabled: false
flagd:
  enabled: true
"""
    
    log(f"Installing OTel Demo to namespace {config.namespace}")
    log(f"Command: {' '.join(install_cmd)}")
    
    result = subprocess.run(
        install_cmd,
        input=values,
        capture_output=True,
        text=True,
    )
    
    helm_log_path.write_text(result.stdout + "\n" + result.stderr)
    
    artifacts = {
        "helm_install_log": str(helm_log_path),
        "helm_returncode": result.returncode,
    }
    
    if result.returncode != 0:
        return LabPhaseResult(
            phase=PHASE_OTEL_BASELINE,
            success=False,
            message=f"Helm install failed: {result.stderr[:500]}",
            artifacts=artifacts,
            duration_seconds=time.time() - start,
        )
    
    log("OTel Demo Helm installation completed")
    
    duration = time.time() - start
    return LabPhaseResult(
        phase=PHASE_OTEL_BASELINE,
        success=True,
        message="OTel Demo deployed successfully",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def phase1b_baseline_readiness(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Wait for OTel Demo baseline to be ready and collect artifacts."""
    start = time.time()
    phase_dir = artifact_dir / PHASE_OTEL_BASELINE
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    log(f"Waiting for {len(REQUIRED_DEPLOYMENTS)} deployments to be ready...")
    
    # Wait for deployments
    ready, status = wait_for_deployments_ready(
        config.kubeconfig,
        config.namespace,
        REQUIRED_DEPLOYMENTS,
        timeout_seconds=config.readiness_timeout,
        poll_interval=config.readiness_poll_interval,
    )
    
    artifacts: dict[str, Any] = {}
    
    if not ready:
        # Collect state for diagnosis
        collect_namespace_snapshot(
            config.kubeconfig,
            config.namespace,
            phase_dir,
            include_previous_logs=True,
        )
        
        return LabPhaseResult(
            phase="phase1-baseline",
            success=False,
            message=f"Readiness timeout: {status}",
            artifacts=artifacts,
            duration_seconds=time.time() - start,
        )
    
    log("Baseline deployments are ready")
    
    # Collect baseline artifacts
    pods_result = kubectl_json(config.kubeconfig, "pods", config.namespace)
    if pods_result.success and pods_result.data:
        pods_path = write_json_artifact(phase_dir, "pods.json", pods_result.data)
        artifacts["pods"] = str(pods_path)
    
    deploy_result = kubectl_json(config.kubeconfig, "deployments", config.namespace)
    if deploy_result.success and deploy_result.data:
        deploy_path = write_json_artifact(phase_dir, "deployments.json", deploy_result.data)
        artifacts["deployments"] = str(deploy_path)
    
    svc_result = kubectl_json(config.kubeconfig, "services", config.namespace)
    if svc_result.success and svc_result.data:
        svc_path = write_json_artifact(phase_dir, "services.json", svc_result.data)
        artifacts["services"] = str(svc_path)
    
    events_result = kubectl_events(config.kubeconfig, config.namespace)
    if events_result.success:
        events_path = write_text_artifact(phase_dir, "events.txt", events_result.stdout)
        artifacts["events"] = str(events_path)
    
    # Write readiness result
    readiness_result = {
        "success": True,
        "message": status,
        "deployments_checked": len(REQUIRED_DEPLOYMENTS),
        "deployments": REQUIRED_DEPLOYMENTS,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    readiness_path = write_json_artifact(phase_dir, "readiness-result.json", readiness_result)
    artifacts["readiness_result"] = str(readiness_path)
    
    duration = time.time() - start
    return LabPhaseResult(
        phase="phase1-baseline",
        success=True,
        message=f"Baseline ready: {status}",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def phase2_inject_incident(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 2: Inject the recommendation cache failure incident."""
    from .k9b_otel_demo_lab_evidence import collect_injection_evidence
    from .k9b_otel_demo_lab_inject import inject_recommendation_cache_failure
    from .k9b_otel_demo_lab_traffic import record_traffic_plan
    
    start = time.time()
    phase_dir = artifact_dir / PHASE_INJECTED
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    # Inject the incident
    injection_result = inject_recommendation_cache_failure(
        config.kubeconfig,
        artifact_dir,
        enable=True,
    )
    
    artifacts: dict[str, Any] = {
        "injection_result": injection_result.evidence,
    }
    
    if not injection_result.success:
        return LabPhaseResult(
            phase=PHASE_INJECTED,
            success=False,
            message=f"Injection failed: {injection_result.error}",
            artifacts=artifacts,
            duration_seconds=time.time() - start,
        )
    
    log(f"Injection successful: {injection_result.method}")
    
    # Wait for incident to propagate
    log(f"Waiting {config.incident_wait_seconds}s for incident to propagate...")
    time.sleep(config.incident_wait_seconds)
    
    # Generate traffic (scaffold mode: records plan, doesn't actually hit frontend)
    traffic_result = record_traffic_plan(
        config.kubeconfig,
        artifact_dir,
        duration_seconds=30,
    )
    artifacts["traffic"] = traffic_result
    
    # Collect injection evidence
    evidence_artifacts = collect_injection_evidence(
        config.kubeconfig,
        artifact_dir,
    )
    artifacts.update({k: str(v) for k, v in evidence_artifacts.items()})
    
    duration = time.time() - start
    return LabPhaseResult(
        phase=PHASE_INJECTED,
        success=True,
        message=f"Incident injected: {injection_result.method}",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def phase3_incident_discovery(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 3: Run k9b incident discovery gate."""
    start = time.time()
    phase_dir = artifact_dir / PHASE_DISCOVERY
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect current state for incident discovery
    pods_result = kubectl_json(config.kubeconfig, "pods", config.namespace)
    events_result = kubectl_events(config.kubeconfig, config.namespace)
    
    artifacts: dict[str, Any] = {}
    
    if pods_result.success and pods_result.data:
        pods_path = write_json_artifact(phase_dir, "pods.json", pods_result.data)
        artifacts["pods"] = str(pods_path)
    
    if events_result.success:
        events_path = write_text_artifact(phase_dir, "events.txt", events_result.stdout)
        artifacts["events"] = str(events_path)
    
    # Try to call k9b incident discovery API if available
    # This would integrate with the k9b backend when deployed
    discovery_result: dict[str, Any] = {
        "message": "Incident discovery gate - k9b API integration placeholder",
        "phase": PHASE_DISCOVERY,
        "timestamp": datetime.now(UTC).isoformat(),
        "incidents_found": [],
    }
    
    # Check for incident indicators in collected artifacts
    incidents_found: list[dict[str, Any]] = []
    
    # Look for restart storms, CrashLoopBackOff, etc.
    if pods_result.success and pods_result.data:
        for pod in pods_result.data.get("items", []):
            pod_name = pod.get("metadata", {}).get("name", "")
            if "recommendation" in pod_name.lower():
                container_statuses = pod.get("status", {}).get("containerStatuses", [])
                for cs in container_statuses:
                    restart_count = cs.get("restartCount", 0)
                    state = cs.get("state", {})
                    if "waiting" in state:
                        waiting_reason = state["waiting"].get("reason", "")
                        if restart_count > 0 or waiting_reason:
                            incidents_found.append({
                                "pod": pod_name,
                                "container": cs.get("name", ""),
                                "restart_count": restart_count,
                                "waiting_reason": waiting_reason,
                            })
    
    discovery_result["incidents_found"] = incidents_found
    
    discovery_path = write_json_artifact(phase_dir, "incidents-list.json", discovery_result)
    artifacts["incidents"] = str(discovery_path)
    
    # Write selected incident
    if incidents_found:
        selected = incidents_found[0]
        write_text_artifact(phase_dir, "selected-incident.json", json.dumps(selected))
        write_text_artifact(phase_dir, "selected-incident-id.txt", selected.get("pod", ""))
    
    duration = time.time() - start
    return LabPhaseResult(
        phase=PHASE_DISCOVERY,
        success=True,
        message=f"Discovery complete: {len(incidents_found)} incidents found",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def phase4_diagnosis(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 4: Run diagnosis (scaffold mode)."""
    start = time.time()
    phase_dir = artifact_dir / PHASE_DIAGNOSIS
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    artifacts: dict[str, Any] = {}
    
    # In scaffold mode, we generate a fake diagnosis
    diagnosis = _generate_fake_diagnosis(artifact_dir, phase_dir)
    
    # Write final diagnosis
    diagnosis_path = write_json_artifact(phase_dir, "final-diagnosis.json", diagnosis)
    artifacts["final_diagnosis"] = str(diagnosis_path)
    
    duration = time.time() - start
    return LabPhaseResult(
        phase=PHASE_DIAGNOSIS,
        success=True,
        message="Scaffold mode diagnosis generated",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def _generate_fake_diagnosis(artifact_dir: Path, phase_dir: Path) -> dict[str, Any]:
    """Generate a scaffold-mode fake diagnosis."""
    return {
        "schema_version": "1.0",
        "provider": "fake-provider",
        "mode": "scaffold",
        "phase": "diagnosis",
        "timestamp": datetime.now(UTC).isoformat(),
        "namespace": "otel-demo",
        "status": "complete",
        "summary": "Diagnosis identifies recommendationservice cache failure due to feature flag misconfiguration",
        "root_cause": (
            "The recommendationservice is experiencing cache failures caused by the "
            "recommendationServiceCacheFailure feature flag being enabled in flagd. "
            "This causes the recommendation service to accumulate cache entries until OOM."
        ),
        "confidence": "high",
        "evidence": [
            "recommendationservice pod shows 503 errors in liveness probe",
            "feature flag recommendationServiceCacheFailure is set to 'true' in flagd configmap",
            "frontend logs show connection errors to recommendationservice",
            "events show Unhealthy liveness probe warnings for recommendationservice",
        ],
        "affected_component": "recommendationservice",
        "feature_flag": "recommendationServiceCacheFailure",
        "next_checks": [
            {"check": "Review flagd configuration history", "purpose": "Identify if flag was changed intentionally"},
            {"check": "Check for recent flag changes", "purpose": "Correlate with symptom timeline"},
            {"check": "Examine recommendationservice logs for cache-related errors", "purpose": "Confirm cache failure behavior"},
        ],
        "remediation": {
            "attempted": False,
            "suggested": False,
            "reason": "Scaffold mode - diagnosis only",
        },
        "safe_to_investigate": True,
        "requires_mutations": False,
    }


def phase5_verification(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 5: Verify with oracle."""
    start = time.time()
    phase_dir = artifact_dir / PHASE_VERIFICATION
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    # Import verification module
    from .k9b_otel_demo_lab_verify import verify_otel_demo_lab
    
    # Run verification
    verification_result = verify_otel_demo_lab(artifact_dir)
    
    artifacts: dict[str, Any] = {
        "verification_passed": verification_result.passed,
        "failure_classes": verification_result.failure_classes,
    }
    
    # Write verification result
    verification_path = write_json_artifact(phase_dir, "verification-result.json", {
        "passed": verification_result.passed,
        "failure_classes": verification_result.failure_classes,
        "details": verification_result.details,
        "recommendationservice_found": verification_result.recommendationservice_found,
        "feature_flag_evidence_found": verification_result.feature_flag_evidence_found,
        "mutation_detected": verification_result.mutation_detected,
        "remediation_attempted": verification_result.remediation_attempted,
    })
    artifacts["verification_result"] = str(verification_path)
    
    duration = time.time() - start
    return LabPhaseResult(
        phase=PHASE_VERIFICATION,
        success=verification_result.passed,
        message=f"Verification: {'PASSED' if verification_result.passed else 'FAILED'}",
        artifacts=artifacts,
        duration_seconds=duration,
    )
