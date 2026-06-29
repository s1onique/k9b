#!/usr/bin/env python3
"""Provider smoke health gates (P1, P1b).

These phases verify k9b backend and scheduler health before incident discovery.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from .backend_health_gate import run_health_gate
from .backend_health_gate.prerequisites import (
    _check_deployment_exists,
    _check_deployment_ready,
    _check_namespace_exists,
    _check_service_exists,
)
from .k9b_otel_demo_lab_constants import (
    FAILURE_BACKEND_DEPLOYMENT_MISSING,
    FAILURE_BACKEND_NAMESPACE_MISSING,
    FAILURE_BACKEND_ROLLOUT_NOT_READY,
    FAILURE_BACKEND_SERVICE_MISSING,
    K9B_BACKEND_CONTAINER,
    K9B_BACKEND_DEPLOYMENT,
    K9B_BACKEND_PORT,
    K9B_BACKEND_SERVICE,
    K9B_NAMESPACE,
    PHASE_BACKEND_HEALTH,
    PHASE_SCHEDULER_HEALTH,
)
from .k9b_otel_demo_lab_types import LabConfig, LabPhaseResult
from .k9b_provider_preflight import (
    run_provider_preflight,
)

# BackendHealth: alias for run_health_gate to maintain contract with OTel workflow tests.
run_backend_health = run_health_gate


def phase_p0_k9b_backend_prerequisite(
    config: LabConfig, artifact_dir: Path
) -> LabPhaseResult:
    """Phase P0: Verify k9b backend prerequisites exist (fail-fast).
    
    This phase checks if the k9b namespace, service, and deployment exist
    before any expensive OTel Demo install/injection/traffic phases.
    
    This prevents the scenario where OTel Demo install succeeds but provider
    smoke P1 fails because the k9b backend namespace doesn't exist.
    """
    from .k9b_lab_common_helpers import log, write_json_artifact
    
    start = time.time()
    phase_dir = artifact_dir / "phase0-cluster" / "k9b-backend-prerequisite"
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    artifacts: dict[str, str] = {}
    failure_class: str | None = None
    failure_reason: str | None = None
    kubernetes_error: str = ""
    
    log("=== Phase P0: k9b Backend Prerequisite Check ===")
    log(f"Checking namespace: {K9B_NAMESPACE}")
    log(f"Checking service: {K9B_BACKEND_SERVICE}")
    log(f"Checking deployment: {K9B_BACKEND_DEPLOYMENT}")
    
    # Check namespace
    ns_exists, ns_error = _check_namespace_exists(config.kubeconfig, K9B_NAMESPACE)
    if not ns_exists:
        failure_class = FAILURE_BACKEND_NAMESPACE_MISSING
        failure_reason = f"k9b namespace '{K9B_NAMESPACE}' does not exist"
        kubernetes_error = ns_error
        log(f"Namespace check FAILED: {ns_error}")
    else:
        log(f"Namespace '{K9B_NAMESPACE}' exists")
        
        # Check service
        svc_exists, svc_error = _check_service_exists(config.kubeconfig, K9B_NAMESPACE, K9B_BACKEND_SERVICE)
        if not svc_exists:
            failure_class = FAILURE_BACKEND_SERVICE_MISSING
            failure_reason = f"k9b backend service '{K9B_BACKEND_SERVICE}' does not exist"
            kubernetes_error = svc_error
            log(f"Service check FAILED: {svc_error}")
        else:
            log(f"Service '{K9B_BACKEND_SERVICE}' exists")
            
            # Check deployment
            deploy_exists, deploy_error = _check_deployment_exists(
                config.kubeconfig, K9B_NAMESPACE, K9B_BACKEND_DEPLOYMENT
            )
            if not deploy_exists:
                failure_class = FAILURE_BACKEND_DEPLOYMENT_MISSING
                failure_reason = f"k9b backend deployment '{K9B_BACKEND_DEPLOYMENT}' does not exist"
                kubernetes_error = deploy_error
                log(f"Deployment check FAILED: {deploy_error}")
            else:
                log(f"Deployment '{K9B_BACKEND_DEPLOYMENT}' exists")
                
                # Check deployment is ready
                deploy_ready, ready_error = _check_deployment_ready(
                    config.kubeconfig, K9B_NAMESPACE, K9B_BACKEND_DEPLOYMENT,
                    timeout_seconds=60
                )
                if not deploy_ready:
                    failure_class = FAILURE_BACKEND_ROLLOUT_NOT_READY
                    failure_reason = f"k9b backend deployment '{K9B_BACKEND_DEPLOYMENT}' not ready: {ready_error}"
                    kubernetes_error = ready_error
                    log(f"Deployment ready check FAILED: {ready_error}")
                else:
                    log(f"Deployment '{K9B_BACKEND_DEPLOYMENT}' is ready")
    
    duration = time.time() - start
    
    # Write prerequisite check result artifact
    if failure_class:
        prereq_result = {
            "failure_class": failure_class,
            "passed": False,
            "message": failure_reason,
            "target": {
                "namespace": K9B_NAMESPACE,
                "service": K9B_BACKEND_SERVICE,
                "deployment": K9B_BACKEND_DEPLOYMENT,
                "port": K9B_BACKEND_PORT,
            },
            "kubernetes_error": kubernetes_error,
            "retryable": False,  # Missing prerequisites are not retryable
            "phase": "p0-k9b-backend-prerequisite",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        prereq_path = write_json_artifact(phase_dir, "prerequisite-failure.json", prereq_result)
        artifacts["prerequisite_failure"] = str(prereq_path)
        
        return LabPhaseResult(
            phase="p0-k9b-backend-prerequisite",
            success=False,
            message=failure_reason or "Prerequisite check failed",
            artifacts=artifacts,
            duration_seconds=duration,
        )
    
    # Prerequisite passed
    prereq_result = {
        "passed": True,
        "message": "k9b backend prerequisites verified",
        "target": {
            "namespace": K9B_NAMESPACE,
            "service": K9B_BACKEND_SERVICE,
            "deployment": K9B_BACKEND_DEPLOYMENT,
            "port": K9B_BACKEND_PORT,
        },
        "phase": "p0-k9b-backend-prerequisite",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    prereq_path = write_json_artifact(phase_dir, "prerequisite-pass.json", prereq_result)
    artifacts["prerequisite_pass"] = str(prereq_path)
    
    return LabPhaseResult(
        phase="p0-k9b-backend-prerequisite",
        success=True,
        message="k9b backend prerequisites verified",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def phase_p1_backend_health_gate(
    config: LabConfig, artifact_dir: Path
) -> LabPhaseResult:
    """Phase P1: Backend Health Gate - verify k9b backend is healthy.
    
    This is a fail-fast gate that checks if the k9b backend /api/health returns HTTP 200.
    """
    from .backend_health_gate import run_health_gate
    
    start = time.time()
    # NOTE: artifact_dir is expected to already include "provider-smoke" subpath
    # The backend-health constant is just "backend-health", not the full path
    phase_dir = artifact_dir / "provider-smoke" / PHASE_BACKEND_HEALTH
    phase_dir.mkdir(parents=True, exist_ok=True)

    from .k9b_lab_common_helpers import log
    log("=== Phase P1: Backend Health Gate ===")
    log(f"Checking k9b backend health at {K9B_BACKEND_SERVICE}.{K9B_NAMESPACE}:{K9B_BACKEND_PORT}")

    try:
        result = run_health_gate(
            kubeconfig=config.kubeconfig,
            namespace=K9B_NAMESPACE,
            deployment=K9B_BACKEND_DEPLOYMENT,
            container=K9B_BACKEND_CONTAINER,
            port=K9B_BACKEND_PORT,
            max_retries=30,
            retry_interval=5,
            artifact_dir=phase_dir,
        )

        result_data = result.to_dict()
        result_path = phase_dir / "health-check-result.json"
        result_path.write_text(json.dumps(result_data, indent=2))

        duration = time.time() - start

        if result.passed:
            log(f"Backend health gate PASSED: HTTP 200 after {result.poll_count} polls")
            return LabPhaseResult(
                phase="p1-backend-health",
                success=True,
                message=f"Backend healthy: HTTP 200 after {result.poll_count} polls ({result.total_elapsed_seconds:.1f}s)",
                artifacts={"health_check_result": str(result_path)},
                duration_seconds=duration,
            )
        else:
            log(f"Backend health gate FAILED: {result.failure_class}")
            return LabPhaseResult(
                phase="p1-backend-health",
                success=False,
                message=f"Backend unhealthy: {result.failure_class}",
                artifacts={"health_check_result": str(result_path)},
                duration_seconds=duration,
            )
    except Exception as e:
        duration = time.time() - start
        log(f"Backend health gate error: {e}")
        return LabPhaseResult(
            phase="p1-backend-health",
            success=False,
            message=f"Backend health check error: {e}",
            artifacts={},
            duration_seconds=duration,
        )


def phase_p1b_scheduler_health_gate(
    config: LabConfig, artifact_dir: Path
) -> LabPhaseResult:
    """Phase P1b: Scheduler Health Gate - verify k9b scheduler is healthy.
    
    This is a fail-fast gate that checks if the k9b scheduler deployment is Ready.
    """
    from .scheduler_health_gate import run_scheduler_health_gate

    start = time.time()
    phase_dir = artifact_dir / "provider-smoke" / PHASE_SCHEDULER_HEALTH
    phase_dir.mkdir(parents=True, exist_ok=True)

    from .k9b_lab_common_helpers import log
    log("=== Phase P1b: Scheduler Health Gate ===")
    log(f"Checking k9b scheduler health in namespace {K9B_NAMESPACE}")

    try:
        result = run_scheduler_health_gate(
            kubeconfig=config.kubeconfig,
            namespace=K9B_NAMESPACE,
            artifact_dir=phase_dir,
        )

        result_data = result.to_dict()
        result_path = phase_dir / "scheduler-health-result.json"
        result_path.write_text(json.dumps(result_data, indent=2))

        duration = time.time() - start

        if result.passed:
            log(f"Scheduler health gate PASSED: {result.ready_replicas} ready replicas")
            return LabPhaseResult(
                phase="p1b-scheduler-health",
                success=True,
                message=f"Scheduler healthy: {result.ready_replicas} ready replicas",
                artifacts={"scheduler_health_result": str(result_path)},
                duration_seconds=duration,
            )
        else:
            log(f"Scheduler health gate FAILED: {result.failure_class}")
            return LabPhaseResult(
                phase="p1b-scheduler-health",
                success=False,
                message=f"Scheduler unhealthy: {result.failure_class}",
                artifacts={"scheduler_health_result": str(result_path)},
                duration_seconds=duration,
            )
    except Exception as e:
        duration = time.time() - start
        log(f"Scheduler health gate error: {e}")
        return LabPhaseResult(
            phase="p1b-scheduler-health",
            success=False,
            message=f"Scheduler health check error: {e}",
            artifacts={},
            duration_seconds=duration,
        )


def phase_p0b_provider_preflight(
    config: LabConfig, artifact_dir: Path
) -> LabPhaseResult:
    """Phase P0b: Provider Preflight Gate - verify k9b backend diagnosis provider.

    This phase checks the k9b backend's diagnosis provider status BEFORE
    expensive OTel Demo install/injection/traffic phases.

    Distinguishes between:
    - provider disabled and diagnosis optional -> skip
    - provider disabled but diagnosis required -> fail early as provider_disabled_required
    - provider configured but unavailable -> fail early as provider_unavailable
    - provider not initialized -> fail early as provider_not_initialized
    - provider healthy -> continue

    This prevents the scenario where OTel Demo install succeeds but provider
    smoke P1 fails because the k9b backend's diagnosis provider is not functional.
    """
    from .k9b_lab_common_helpers import log

    start = time.time()
    phase_dir = artifact_dir / "phase0-cluster" / "provider-preflight"
    phase_dir.mkdir(parents=True, exist_ok=True)

    log("=== Phase P0b: Provider Preflight Gate ===")
    log("Checking k9b backend diagnosis provider status")

    # Run provider preflight
    result = run_provider_preflight(
        kubeconfig=config.kubeconfig,
        namespace=K9B_NAMESPACE,
        service=K9B_BACKEND_SERVICE,
        port=K9B_BACKEND_PORT,
        artifact_dir=phase_dir,
        require_provider_configured=True,
        require_provider_invocation_possible=True,
        timeout_seconds=30,
    )

    duration = time.time() - start

    if result.passed:
        log(f"Provider preflight PASSED: provider configured={result.provider_configured}")
        return LabPhaseResult(
            phase="p0b-provider-preflight",
            success=True,
            message=f"Provider preflight passed: {result.message}",
            artifacts={"provider_preflight_result": str(phase_dir / "provider-preflight-result.json")},
            duration_seconds=duration,
        )
    else:
        log(f"Provider preflight FAILED: {result.failure_class} - {result.message}")
        return LabPhaseResult(
            phase="p0b-provider-preflight",
            success=False,
            message=f"Provider preflight failed: {result.failure_class} - {result.message}",
            artifacts={"provider_preflight_result": str(phase_dir / "provider-preflight-result.json")},
            duration_seconds=duration,
        )
