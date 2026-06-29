"""Provider preflight gate for k9b live labs.

This module provides the P0b phase that checks k9b backend's diagnosis provider
status BEFORE expensive lab install/injection/traffic phases.

Both CNPG and OTel labs should use run_provider_preflight() instead of
implementing their own provider preflight logic.

The gate checks via Service path first, then falls back to exec-local curl:
1. Service path check: http://k9b-backend.k9b:8080/api/health/details (from temp curl pod)
2. Optional exec-local fallback: localhost:8080 inside backend pod (if Service fails)

Failure classification:
- provider disabled and diagnosis required -> provider_disabled_required
- provider configured but unavailable -> provider_unavailable
- provider not initialized -> provider_not_initialized
- provider healthy -> continue
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Import the canonical parser
from scripts.lab_common.constants import (
    DEFAULT_K9B_BACKEND_CONTAINER,
    DEFAULT_K9B_BACKEND_DEPLOYMENT,
    DEFAULT_K9B_BACKEND_PORT,
    FAILURE_PROVIDER_CONFIG_ERROR,
    FAILURE_PROVIDER_CONNECTION_FAILED,
    FAILURE_PROVIDER_DISABLED_REQUIRED,
    FAILURE_PROVIDER_NOT_INITIALIZED,
    FAILURE_PROVIDER_UNAVAILABLE,
)
from scripts.lab_common.provider_status import ProviderStatus, parse_provider_status_from_health_details

# Re-export for backward compatibility
__all__ = [
    "ProviderPreflightResult",
    "run_provider_preflight",
    "FAILURE_PROVIDER_DISABLED_REQUIRED",
    "FAILURE_PROVIDER_UNAVAILABLE",
    "FAILURE_PROVIDER_NOT_INITIALIZED",
    "FAILURE_PROVIDER_CONNECTION_FAILED",
    "FAILURE_PROVIDER_CONFIG_ERROR",
    "DEFAULT_K9B_BACKEND_DEPLOYMENT",
    "DEFAULT_K9B_BACKEND_CONTAINER",
    "DEFAULT_K9B_BACKEND_PORT",
]


# =============================================================================
# Result types
# =============================================================================

@dataclass
class ProviderPreflightResult:
    """Result of provider preflight check."""
    
    passed: bool = False
    failure_class: str | None = None
    message: str = ""
    provider_enabled: bool = False
    provider_configured: bool = False
    provider_invocation_attempted: bool = False
    provider_name: str = ""
    provider_status: str = ""
    provider_phase: str = ""
    diagnosis_provider_enabled: bool = False
    requires_diagnosis: bool = False
    duration_seconds: float = 0.0
    check_method: str = ""  # "service" or "exec-local"
    parsed_status: ProviderStatus = field(default_factory=ProviderStatus)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failure_class": self.failure_class,
            "message": self.message,
            "provider_enabled": self.provider_enabled,
            "provider_configured": self.provider_configured,
            "provider_invocation_attempted": self.provider_invocation_attempted,
            "provider_name": self.provider_name,
            "provider_status": self.provider_status,
            "provider_phase": self.provider_phase,
            "diagnosis_provider_enabled": self.diagnosis_provider_enabled,
            "requires_diagnosis": self.requires_diagnosis,
            "duration_seconds": self.duration_seconds,
            "check_method": self.check_method,
        }


# =============================================================================
# Curl helpers
# =============================================================================

def _curl_service_pod(
    kubeconfig: str,
    namespace: str,
    target_url: str,
    timeout_seconds: int = 30,
) -> tuple[bool, str, int]:
    """Curl a URL from a temporary curlimages/curl pod.
    
    Returns:
        Tuple of (success, response_body, http_code)
    """
    pod_name = f"k9b-provider-preflight-{int(time.time())}"
    
    pod_manifest = f"""apiVersion: v1
kind: Pod
metadata:
  name: {pod_name}
  namespace: {namespace}
  labels:
    app: k9b-provider-preflight
spec:
  restartPolicy: Never
  containers:
  - name: curl
    image: curlimages/curl:latest
    command: ["/bin/sh", "-c"]
    args:
      - |
        code=$(curl -s -o /tmp/response.txt -w "%{{http_code}}" --max-time {timeout_seconds} {target_url})
        echo "HTTP_CODE=$code"
        cat /tmp/response.txt
"""
    try:
        # Apply pod
        apply_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "apply", "-f", "-"],
            input=pod_manifest,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if apply_result.returncode != 0:
            return False, f"Failed to create pod: {apply_result.stderr}", 0
        
        # Wait for pod to complete
        max_wait = timeout_seconds + 30
        elapsed = 0
        while elapsed < max_wait:
            phase_result = subprocess.run(
                ["kubectl", "--kubeconfig", kubeconfig, "get", "pod", pod_name,
                 "-n", namespace, "-o", "jsonpath={.status.phase}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if phase_result.returncode == 0:
                phase = phase_result.stdout.strip()
                if phase == "Succeeded":
                    break
                elif phase == "Failed":
                    break
            
            time.sleep(5)
            elapsed += 5
        
        # Get pod logs
        logs_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "logs", pod_name, "-n", namespace],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # Parse HTTP code and body from logs
        http_code = 0
        body = logs_result.stdout
        
        for line in logs_result.stdout.split("\n"):
            if "HTTP_CODE=" in line:
                try:
                    http_code = int(line.split("HTTP_CODE=")[1].strip())
                except (ValueError, IndexError):
                    pass
        
        return 200 <= http_code < 400, body, http_code
        
    finally:
        # Fail-safe cleanup: ignore deletion errors
        try:
            subprocess.run(
                ["kubectl", "--kubeconfig", kubeconfig, "delete", "pod", pod_name,
                 "-n", namespace, "--wait=false"],
                capture_output=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            pass


def _curl_exec_pod(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    container: str,
    target_url: str,
    timeout_seconds: int = 30,
) -> tuple[bool, str, int]:
    """Curl a URL from inside a pod via exec.
    
    Returns:
        Tuple of (success, response_body, http_code)
    """
    exec_cmd = [
        "kubectl", "--kubeconfig", kubeconfig, "exec", "-n", namespace,
        f"deploy/{deployment}", "-c", container, "--",
        "curl", "-sS", "-f",
        target_url,
        "--max-time", str(timeout_seconds),
    ]
    
    exec_result = subprocess.run(
        exec_cmd, capture_output=True, text=True, timeout=timeout_seconds + 5
    )
    
    if exec_result.returncode == 0:
        return True, exec_result.stdout, 200
    
    return False, exec_result.stderr, 0


# =============================================================================
# Main preflight function
# =============================================================================

def run_provider_preflight(
    kubeconfig: str,
    namespace: str,
    service: str,
    port: int,
    artifact_dir: Path,
    require_provider_configured: bool = True,
    require_provider_invocation_possible: bool = True,
    timeout_seconds: int = 30,
    backend_deployment: str = DEFAULT_K9B_BACKEND_DEPLOYMENT,
    backend_container: str = DEFAULT_K9B_BACKEND_CONTAINER,
) -> ProviderPreflightResult:
    """Run provider preflight check against k9b backend.
    
    Uses Service-path check first, then falls back to exec-local if needed.
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: k9b namespace
        service: k9b backend service name (used for Service-path check)
        port: k9b backend port
        artifact_dir: Directory to write artifacts
        require_provider_configured: If True, provider must be configured
        require_provider_invocation_possible: If True, provider invocation must be possible
        timeout_seconds: Timeout for health check
        backend_deployment: Name of the backend deployment (for exec fallback)
        backend_container: Name of the backend container (for exec fallback)
        
    Returns:
        ProviderPreflightResult with pass/fail and details
    """
    start = time.time()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    result = ProviderPreflightResult(
        passed=False, 
        message="Starting provider preflight",
        check_method="unknown",
    )
    
    health_url = f"http://{service}.{namespace}.svc.cluster.local:{port}/api/health/details"
    
    try:
        # Step 1: Service-path check using temp curl pod
        success, body, http_code = _curl_service_pod(
            kubeconfig, namespace, health_url, timeout_seconds
        )
        result.check_method = "service"
        
        if not success or http_code != 200:
            # Step 2: Fall back to exec-local if Service check failed
            exec_health_url = f"http://localhost:{port}/api/health/details"
            exec_success, exec_body, exec_code = _curl_exec_pod(
                kubeconfig, namespace, backend_deployment, backend_container,
                exec_health_url, timeout_seconds
            )
            
            if exec_success:
                body = exec_body
                result.check_method = "exec-local"
            else:
                # Both checks failed
                result.failure_class = FAILURE_PROVIDER_CONNECTION_FAILED
                result.message = f"Provider preflight failed: Service check HTTP {http_code}, exec check failed: {exec_body[:200]}"
                result.duration_seconds = time.time() - start
                _write_result(result, artifact_dir)
                return result
        
        # Parse health details response
        try:
            health_details = json.loads(body)
        except json.JSONDecodeError:
            result.failure_class = FAILURE_PROVIDER_CONFIG_ERROR
            result.message = f"Invalid JSON response from /api/health/details (HTTP {http_code})"
            result.duration_seconds = time.time() - start
            _write_result(result, artifact_dir)
            return result
        
        # Parse provider status using canonical parser
        result.parsed_status = parse_provider_status_from_health_details(health_details)
        
        # Populate result fields from parsed status
        result.provider_enabled = result.parsed_status.provider_enabled
        result.provider_configured = result.parsed_status.provider_configured
        result.provider_invocation_attempted = result.parsed_status.provider_invocation_attempted
        result.provider_name = result.parsed_status.provider_name
        result.provider_status = result.parsed_status.provider_status
        result.provider_phase = result.parsed_status.provider_phase
        result.diagnosis_provider_enabled = result.parsed_status.diagnosis_provider_enabled
        
        # Check primary_failure for dependency_provider_connection_failed
        primary_failure = health_details.get("primary_failure_class", "")
        
        # Determine pass/fail based on provider state
        result = _evaluate_provider_state(
            result=result,
            primary_failure=primary_failure,
            require_provider_configured=require_provider_configured,
            require_provider_invocation_possible=require_provider_invocation_possible,
        )
        
    except subprocess.TimeoutExpired:
        result.failure_class = FAILURE_PROVIDER_CONNECTION_FAILED
        result.message = f"Provider preflight timed out after {timeout_seconds}s"
        result.duration_seconds = time.time() - start
        _write_result(result, artifact_dir)
        return result
    except Exception as e:
        result.failure_class = FAILURE_PROVIDER_CONNECTION_FAILED
        result.message = f"Provider preflight error: {str(e)}"
        result.duration_seconds = time.time() - start
        _write_result(result, artifact_dir)
        return result
    
    result.duration_seconds = time.time() - start
    _write_result(result, artifact_dir)
    return result


def _evaluate_provider_state(
    result: ProviderPreflightResult,
    primary_failure: str,
    require_provider_configured: bool,
    require_provider_invocation_possible: bool,
) -> ProviderPreflightResult:
    """Evaluate provider state and determine pass/fail."""
    
    # Check for dependency provider connection failure
    if primary_failure == "dependency_provider_connection_failed":
        result.failure_class = FAILURE_PROVIDER_UNAVAILABLE
        result.message = "Diagnosis provider unavailable: dependency_provider_connection_failed"
        result.passed = False
        return result
    
    # Provider disabled but diagnosis required
    if not result.provider_enabled and require_provider_configured:
        result.failure_class = FAILURE_PROVIDER_DISABLED_REQUIRED
        result.message = "Diagnosis provider disabled but required"
        result.passed = False
        return result
    
    # Provider not configured
    if not result.provider_configured and require_provider_configured:
        result.failure_class = FAILURE_PROVIDER_UNAVAILABLE
        result.message = "Diagnosis provider not configured"
        result.passed = False
        return result
    
    # Provider not initialized
    if result.provider_phase in ("not_initialized", "unknown"):
        if require_provider_invocation_possible:
            result.failure_class = FAILURE_PROVIDER_NOT_INITIALIZED
            result.message = f"Diagnosis provider not initialized (phase={result.provider_phase})"
            result.passed = False
            return result
    
    # Provider unavailable status
    if result.provider_status in ("unavailable", "failed", "error"):
        result.failure_class = FAILURE_PROVIDER_UNAVAILABLE
        result.message = f"Diagnosis provider unavailable (status={result.provider_status})"
        result.passed = False
        return result
    
    # All checks passed
    result.passed = True
    result.message = "Provider preflight passed"
    result.failure_class = None
    return result


def _write_result(result: ProviderPreflightResult, artifact_dir: Path) -> None:
    """Write preflight result to artifact directory."""
    result_path = artifact_dir / "provider-preflight-result.json"
    result_path.write_text(json.dumps(result.to_dict(), indent=2))
