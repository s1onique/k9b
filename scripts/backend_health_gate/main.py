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
    FAILURE_BACKEND_HEALTH_500,
    FAILURE_BACKEND_HEALTH_TIMEOUT,
    FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR,
)
from .k8s_diagnostics import (
    _collect_backend_diagnostics,
    _collect_backend_logs,
    _collect_scheduler_diagnostics,
    _collect_scheduler_logs,
    _kubectl_exec_health,
    _kubectl_exec_health_details,
)
from .types import HealthCheckResult


def run_health_gate(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    container: str,
    port: int,
    max_retries: int,
    retry_interval: int,
    artifact_dir: Path,
) -> HealthCheckResult:
    """Run the backend health gate with bounded polling.
    
    Returns:
        HealthCheckResult with classification and diagnostics
    """
    result = HealthCheckResult()
    start_time = time.time()
    http_statuses_seen: list[str] = []
    
    # Create artifact directory
    health_dir = artifact_dir / "provider-smoke" / "backend-health"
    health_dir.mkdir(parents=True, exist_ok=True)
    
    for attempt in range(1, max_retries + 1):
        result.poll_count = attempt
        
        http_code, error_msg = _kubectl_exec_health(
            kubeconfig, namespace, deployment, container, port
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
            kubeconfig, namespace, deployment, container, port
        )
        
        # Normalize and validate backend health details
        # This ensures only allowlisted fields/values make it into the artifact
        backend_health_failed = result.final_http_code == "500"
        normalized_details, details_conclusive = _normalize_backend_health_details(
            health_details, backend_health_failed
        )
        
        if health_details and details_conclusive:
            # Backend provided conclusive self-diagnosis
            print(f"Backend provided conclusive health details: primary_failure={normalized_details.get('primary_failure_class', 'unknown')}", flush=True)
            
            health_deps: dict[str, Any] = normalized_details
            
            # Merge Kubernetes-state as supplementary diagnostics
            # This provides outer layer info even when backend endpoint succeeds
            health_deps["kubernetes_state_fallback"] = {
                "backend_diags_available": bool(backend_diags),
                "scheduler_diags_available": bool(scheduler_diags),
                "provider_status": provider_status,
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
            
            health_deps["backend_details_error"] = details_error if not health_details else ""
        
        deps_path = health_dir / "health-dependencies.json"
        deps_path.write_text(json.dumps(health_deps, indent=2))
        print(f"Health dependencies artifact: {deps_path}", flush=True)
    
    return result
