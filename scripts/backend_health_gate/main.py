"""Main module for backend health gate."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .classification import (
    _collect_health_dependencies,
    _get_provider_config_status,
    _normalize_backend_health_details,
)
from .constants import (
    FAILURE_BACKEND_DEPLOYMENT_MISSING,
    FAILURE_BACKEND_HEALTH_500,
    FAILURE_BACKEND_HEALTH_TIMEOUT,
    FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR,
    FAILURE_BACKEND_NAMESPACE_MISSING,
    FAILURE_BACKEND_ROLLOUT_NOT_READY,
    FAILURE_BACKEND_SERVICE_MISSING,
    K9B_BACKEND_SERVICE,
)
from .k8s_diagnostics import (
    _collect_backend_diagnostics,
    _collect_backend_logs,
    _collect_scheduler_diagnostics,
    _collect_scheduler_logs,
    _kubectl_exec_health,
    _kubectl_exec_health_details,
)
from .prerequisites import (
    _check_deployment_exists,
    _check_deployment_ready,
    _check_namespace_exists,
    _check_service_exists,
)
from .types import HealthCheckResult


def _write_prerequisite_failure(
    health_dir: Path,
    failure_class: str,
    namespace: str,
    service: str,
    deployment: str,
    port: int,
    error_message: str,
    kubernetes_error: str = "",
) -> None:
    """Write prerequisite failure artifact with detailed metadata."""
    status_data: dict[str, Any] = {
        "failure_class": failure_class,
        "passed": False,
        "final_http_code": "N/A",
        "poll_count": 0,
        "total_elapsed_seconds": 0,
        "http_statuses_seen": [],
        "transport_error": error_message,
        "timestamp": "",
        "diagnostics": {},
        "target": {
            "namespace": namespace,
            "service": service,
            "deployment": deployment,
            "port": port,
            "attempted_url": f"http://{service}.{namespace}.svc.cluster.local:{port}/api/health",
        },
        "kubernetes_error": kubernetes_error,
        "retryable": False,  # Missing prerequisites are not retryable
        "phase": "prerequisite_check",
    }
    
    status_path = health_dir / "status.json"
    status_path.write_text(json.dumps(status_data, indent=2))
    
    # Write bounded summary
    summary_lines = [
        "Backend Health Gate Result: FAILED (prerequisite check)",
        f"Failure class: {failure_class}",
        f"Reason: {error_message}",
        f"Namespace: {namespace}",
        f"Service: {service}",
        f"Deployment: {deployment}",
        f"Port: {port}",
        "Retryable: false",
    ]
    if kubernetes_error:
        summary_lines.append(f"Kubernetes error: {kubernetes_error}")
    
    summary_path = health_dir / "bounded-summary.txt"
    summary_path.write_text("\n".join(summary_lines))


def run_health_gate(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    port: int,
    max_retries: int,
    retry_interval: int,
    artifact_dir: Path,
    *,
    container: str | None = None,
    service: str | None = None,
) -> HealthCheckResult:
    """Run the backend health gate with bounded polling.
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: Kubernetes namespace
        deployment: Deployment name
        port: Backend port
        max_retries: Maximum polling retries
        retry_interval: Seconds between retries
        artifact_dir: Directory for artifacts
        container: Optional container name (defaults to deployment name)
        service: Optional service name (defaults to K9B_BACKEND_SERVICE constant)
    
    Returns:
        HealthCheckResult with classification and diagnostics
    """
    # Resolve defaults
    svc_name = service if service is not None else K9B_BACKEND_SERVICE
    container_name = container if container is not None else deployment
    result = HealthCheckResult()
    start_time = time.time()
    http_statuses_seen: list[str] = []
    
    # Create artifact directory
    # NOTE: artifact_dir is expected to already include the phase subpath (e.g., "provider-smoke/backend-health")
    # Do NOT double-nest by adding "provider-smoke/backend-health" again here.
    health_dir = artifact_dir
    health_dir.mkdir(parents=True, exist_ok=True)
    
    # Phase 0: Prerequisite checks - fail fast if namespace/service/deployment missing
    # This prevents wasting time on HTTP polling when the backend doesn't exist
    
    # Check namespace exists
    ns_exists, ns_error = _check_namespace_exists(kubeconfig, namespace)
    if not ns_exists:
        print(f"Namespace '{namespace}' does not exist: {ns_error}", flush=True)
        result.failure_class = FAILURE_BACKEND_NAMESPACE_MISSING
        result.transport_error = ns_error
        result.final_http_code = "N/A"
        result.total_elapsed_seconds = time.time() - start_time
        result.http_statuses_seen = [f"ERR:namespace_not_found:{namespace}"]
        _write_prerequisite_failure(
            health_dir=health_dir,
            failure_class=FAILURE_BACKEND_NAMESPACE_MISSING,
            namespace=namespace,
            service=svc_name,
            deployment=deployment,
            port=port,
            error_message=f"k9b namespace '{namespace}' does not exist",
            kubernetes_error=ns_error,
        )
        return result
    
    # Check service exists
    svc_exists, svc_error = _check_service_exists(kubeconfig, namespace, svc_name)
    if not svc_exists:
        print(f"Service '{svc_name}' does not exist: {svc_error}", flush=True)
        result.failure_class = FAILURE_BACKEND_SERVICE_MISSING
        result.transport_error = svc_error
        result.final_http_code = "N/A"
        result.total_elapsed_seconds = time.time() - start_time
        result.http_statuses_seen = [f"ERR:service_not_found:{svc_name}"]
        _write_prerequisite_failure(
            health_dir=health_dir,
            failure_class=FAILURE_BACKEND_SERVICE_MISSING,
            namespace=namespace,
            service=svc_name,
            deployment=deployment,
            port=port,
            error_message=f"k9b backend service '{svc_name}' does not exist",
            kubernetes_error=svc_error,
        )
        return result
    
    # Check deployment exists
    deploy_exists, deploy_error = _check_deployment_exists(kubeconfig, namespace, deployment)
    if not deploy_exists:
        print(f"Deployment '{deployment}' does not exist: {deploy_error}", flush=True)
        result.failure_class = FAILURE_BACKEND_DEPLOYMENT_MISSING
        result.transport_error = deploy_error
        result.final_http_code = "N/A"
        result.total_elapsed_seconds = time.time() - start_time
        result.http_statuses_seen = [f"ERR:deployment_not_found:{deployment}"]
        _write_prerequisite_failure(
            health_dir=health_dir,
            failure_class=FAILURE_BACKEND_DEPLOYMENT_MISSING,
            namespace=namespace,
            service=svc_name,
            deployment=deployment,
            port=port,
            error_message=f"k9b backend deployment '{deployment}' does not exist",
            kubernetes_error=deploy_error,
        )
        return result
    
    # Check deployment is ready
    deploy_ready, ready_error = _check_deployment_ready(kubeconfig, namespace, deployment, timeout_seconds=60)
    if not deploy_ready:
        print(f"Deployment '{deployment}' not ready: {ready_error}", flush=True)
        result.failure_class = FAILURE_BACKEND_ROLLOUT_NOT_READY
        result.transport_error = ready_error
        result.final_http_code = "N/A"
        result.total_elapsed_seconds = time.time() - start_time
        result.http_statuses_seen = [f"ERR:rollout_not_ready:{deployment}"]
        _write_prerequisite_failure(
            health_dir=health_dir,
            failure_class=FAILURE_BACKEND_ROLLOUT_NOT_READY,
            namespace=namespace,
            service=svc_name,
            deployment=deployment,
            port=port,
            error_message=f"k9b backend deployment '{deployment}' rollout not complete: {ready_error}",
            kubernetes_error=ready_error,
        )
        return result
    
    # Prerequisite checks passed - proceed with HTTP health polling
    for attempt in range(1, max_retries + 1):
        result.poll_count = attempt
        
        http_code, error_msg = _kubectl_exec_health(
            kubeconfig, namespace, deployment, container_name, port
        )
        
        status_str = str(http_code) if http_code > 0 else f"ERR:{error_msg[:50]}"
        http_statuses_seen.append(status_str)
        
        elapsed = time.time() - start_time
        print(f"[{elapsed:.1f}s] Attempt {attempt}/{max_retries}: HTTP {http_code} (error: {error_msg or 'none'})", flush=True)
        
        if http_code == 200:
            # Health check passed
            result.passed = True
            result.http_status = 200
            result.final_http_code = "200"
            result.total_elapsed_seconds = elapsed
            result.http_statuses_seen = http_statuses_seen
            result.failure_class = ""
            break
        
        elif http_code > 0 and http_code != 200:
            # Backend returned non-200 (likely 500)
            result.final_http_code = str(http_code)
            
            if attempt < max_retries:
                time.sleep(retry_interval)
            continue
        
        else:
            # Transport error
            result.transport_error = error_msg
            result.final_http_code = f"ERR:{error_msg[:30]}"
            
            if attempt < max_retries:
                time.sleep(retry_interval)
            continue
    
    result.total_elapsed_seconds = time.time() - start_time
    result.http_statuses_seen = http_statuses_seen
    
    # Classify failure
    if result.passed:
        pass  # Already set above
    elif result.transport_error:
        result.failure_class = FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR
    elif result.final_http_code == "500":
        result.failure_class = FAILURE_BACKEND_HEALTH_500
    elif result.poll_count >= max_retries:
        # All retries exhausted
        if result.final_http_code.startswith("ERR"):
            result.failure_class = FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR
        elif result.final_http_code == "500":
            result.failure_class = FAILURE_BACKEND_HEALTH_500
        else:
            result.failure_class = FAILURE_BACKEND_HEALTH_TIMEOUT
    else:
        result.failure_class = "backend_health_invalid_response"
    
    # Collect diagnostics on failure
    if not result.passed:
        print(f"\n=== Backend health gate FAILED: {result.failure_class} ===", flush=True)
        
        # Collect sanitized diagnostics
        backend_diags = _collect_backend_diagnostics(kubeconfig, namespace)
        scheduler_diags = _collect_scheduler_diagnostics(kubeconfig, namespace)
        provider_status = _get_provider_config_status(kubeconfig, namespace)
        backend_logs = _collect_backend_logs(kubeconfig, namespace)
        scheduler_logs = _collect_scheduler_logs(kubeconfig, namespace)
        
        result.diagnostics = {
            "backend": backend_diags,
            "scheduler": scheduler_diags,
            "provider_config": provider_status,
        }
        
        # Write status.json artifact
        # NOTE: Raw logs are NOT included in uploadable artifacts.
        # Logs can contain provider endpoints, secrets, or topology.
        # For debugging, logs are written to separate non-uploadable files.
        status_data: dict[str, Any] = {
            "failure_class": result.failure_class,
            "passed": result.passed,
            "final_http_code": result.final_http_code,
            "poll_count": result.poll_count,
            "max_retries": max_retries,
            "total_elapsed_seconds": round(result.total_elapsed_seconds, 1),
            "http_statuses_seen": http_statuses_seen,
            "transport_error": result.transport_error,
            "timestamp": result.diagnostics.get("backend", {}).get("timestamp", ""),
            "diagnostics": result.diagnostics,
            "target": {
                "namespace": namespace,
                "service": svc_name,
                "deployment": deployment,
                "port": port,
                "attempted_url": f"http://localhost:{port}/api/health",
            },
            # NOTE: Raw logs omitted - they may contain provider secrets/topology.
            # Logs are collected separately for debugging but NOT included in artifacts.
        }
        
        # Write separate debug logs to RUNNER_TEMP (NOT in lab-artifacts/live)
        # This keeps raw logs outside the upload boundary
        runner_temp = os.environ.get("RUNNER_TEMP", "/tmp")
        debug_logs_dir = Path(runner_temp) / "k9b-backend-health-debug"
        debug_logs_dir.mkdir(parents=True, exist_ok=True)
        (debug_logs_dir / "backend-tail.txt").write_text(backend_logs[-2000:] if backend_logs else "")
        (debug_logs_dir / "scheduler-tail.txt").write_text(scheduler_logs[-2000:] if scheduler_logs else "")
        
        status_path = health_dir / "status.json"
        status_path.write_text(json.dumps(status_data, indent=2))
        print(f"Status artifact: {status_path}", flush=True)
        
        # Write bounded summary
        summary_path = health_dir / "bounded-summary.txt"
        summary_lines: list[str] = [
            "Backend Health Gate Result: FAILED",
            f"Failure class: {result.failure_class}",
            f"Final HTTP code: {result.final_http_code}",
            f"Namespace: {namespace}",
            f"Deployment: {deployment}",
            f"Port: {port}",
            f"Polls: {result.poll_count}/{max_retries}",
            f"Elapsed: {result.total_elapsed_seconds:.1f}s",
            f"HTTP statuses seen: {', '.join(http_statuses_seen[-5:])}",
            f"Transport error: {result.transport_error or 'none'}",
            "",
            "Provider config status (booleans only):",
            f"  diagnosis_provider_enabled: {provider_status['diagnosis_provider_enabled']}",
            f"  diagnosis_provider_secret_ref_present: {provider_status['diagnosis_provider_secret_ref_present']}",
            f"  small_provider_secret_ref_present: {provider_status['small_provider_secret_ref_present']}",
            f"  base_url_present: {provider_status['base_url_present']}",
            f"  model_present: {provider_status['model_present']}",
            f"  api_key_present: {provider_status['api_key_present']}",
            "",
            "Backend container states:",
        ]
        
        # Add container states from diagnostics
        for key, val in backend_diags.items():
            if key.startswith("pod_"):
                summary_lines.append(f"  {key}: phase={val.get('phase')}, restarts={val.get('restart_count', 0)}")
                for cs in val.get("containers", []):
                    state_info = cs.get("state", "unknown")
                    if cs.get("reason"):
                        state_info += f" ({cs['reason']})"
                    summary_lines.append(f"    - {cs['name']}: {state_info}")
        
        summary_path.write_text("\n".join(summary_lines))
        print(f"Summary artifact: {summary_path}", flush=True)
        
        # Try to get health details from backend endpoint first
        # This provides backend-owned self-diagnosis
        health_details, details_error = _kubectl_exec_health_details(
            kubeconfig, namespace, deployment, container_name, port
        )
        
        # Normalize and validate backend health details
        # This ensures only allowlisted fields/values make it into the artifact
        backend_health_failed = result.final_http_code == "500"
        normalized_details, details_conclusive = _normalize_backend_health_details(
            health_details, backend_health_failed
        )
        
        if health_details and details_conclusive:
            # Backend provided conclusive self-diagnosis
            primary_failure = normalized_details.get('primary_failure_class', 'unknown')
            print(f"Backend provided conclusive health details: primary_failure={primary_failure}", flush=True)
            
            # Print provider phase for diagnosis
            for dep in normalized_details.get("dependencies", []):
                if dep.get("dependency_name") == "diagnosis_provider":
                    provider_status_str = dep.get("status", "unknown")
                    provider_phase = dep.get("phase", "unknown")
                    provider_reason_code = dep.get("reason_code", "unknown")
                    provider_failure_class = dep.get("failure_class", "")
                    print(f"  diagnosis_provider: status={provider_status_str}, reason_code={provider_reason_code}, phase={provider_phase}" +
                          (f", failure_class={provider_failure_class}" if provider_failure_class else ""), flush=True)
            health_deps: dict[str, Any] = normalized_details
            
            # Merge Kubernetes-state as supplementary diagnostics
            # This provides outer layer info even when backend endpoint succeeds
            health_deps["kubernetes_state_fallback"] = {
                "backend_diags_available": bool(backend_diags),
                "scheduler_diags_available": bool(scheduler_diags),
                "provider_status": provider_status_str,
            }
        else:
            # Backend endpoint unavailable or inconclusive - use Kubernetes-state heuristics
            print("Backend health details inconclusive or unavailable, using Kubernetes-state fallback", flush=True)
            
            # Collect K8s-state based classification
            health_deps = _collect_health_dependencies(backend_diags, scheduler_diags, provider_status)
            health_deps["source"] = "kubernetes_state_fallback"
            
            # If we got a response but it was inconclusive, merge it as supplemental
            if health_details and not details_conclusive:
                print(f"Backend details inconclusive: {normalized_details.get('inconclusive_reasons', [])}", flush=True)
                health_deps["backend_endpoint_inconclusive"] = normalized_details
                
                # Log diagnosis_provider fields even when primary_failure_class is absent
                # This helps with debugging even when overall result is inconclusive
                for dep in normalized_details.get("dependencies", []):
                    if dep.get("dependency_name") == "diagnosis_provider":
                        provider_status_str = dep.get("status", "unknown")
                        provider_phase = dep.get("phase", "unknown")
                        provider_reason_code = dep.get("reason_code", "unknown")
                        print(f"  diagnosis_provider (from inconclusive details): status={provider_status_str}, reason_code={provider_reason_code}, phase={provider_phase}", flush=True)
            
            health_deps["backend_details_error"] = details_error if not health_details else ""
        
        deps_path = health_dir / "health-dependencies.json"
        deps_path.write_text(json.dumps(health_deps, indent=2))
        print(f"Health dependencies artifact: {deps_path}", flush=True)
    
    return result
