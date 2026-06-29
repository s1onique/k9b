#!/usr/bin/env python3
"""Provider preflight gate for OTel Demo Lab.

This module implements the P0b phase that checks k9b backend's diagnosis provider
status BEFORE expensive OTel Demo install/injection/traffic phases.

The gate checks via Service path first, then falls back to exec-local curl:
1. Service path check: http://k9b-backend.k9b:8080/api/health/details (from temp curl pod)
2. Optional exec-local fallback: localhost:8080 inside backend pod (if Service fails)

This pattern is CNPG-style common gate semantics:
- provider disabled and diagnosis required -> fail early as provider_disabled_required
- provider configured but unavailable -> fail early as provider_unavailable
- provider not initialized -> fail early as provider_not_initialized
- provider healthy -> continue

This prevents the scenario where OTel Demo install succeeds but provider smoke
fails late because the k9b backend's diagnosis provider is not functional.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .k9b_otel_demo_lab_constants import (
    K9B_BACKEND_CONTAINER,
    K9B_BACKEND_DEPLOYMENT,
    K9B_BACKEND_PORT,
    K9B_NAMESPACE,
)


@dataclass
class ProviderPreflightResult:
    """Result of provider preflight check."""
    
    passed: bool
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


# Failure class constants
FAILURE_PROVIDER_DISABLED_REQUIRED = "provider_disabled_required"
FAILURE_PROVIDER_UNAVAILABLE = "provider_unavailable"
FAILURE_PROVIDER_NOT_INITIALIZED = "provider_not_initialized"
FAILURE_PROVIDER_CONNECTION_FAILED = "provider_connection_failed"
FAILURE_PROVIDER_CONFIG_ERROR = "provider_config_error"


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


def run_provider_preflight(
    kubeconfig: str,
    namespace: str,
    service: str,
    port: int,
    artifact_dir: Path,
    require_provider_configured: bool = True,
    require_provider_invocation_possible: bool = True,
    timeout_seconds: int = 30,
) -> ProviderPreflightResult:
    """Run provider preflight check against k9b backend.
    
    Uses Service-path check first (CNPG-style common gate semantics),
    then falls back to exec-local if needed.
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: k9b namespace
        service: k9b backend service name (used for Service-path check)
        port: k9b backend port
        artifact_dir: Directory to write artifacts
        require_provider_configured: If True, provider must be configured
        require_provider_invocation_possible: If True, provider invocation must be possible
        timeout_seconds: Timeout for health check
        
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
        # Step 1: Service-path check using temp curl pod (CNPG-style)
        success, body, http_code = _curl_service_pod(
            kubeconfig, namespace, health_url, timeout_seconds
        )
        result.check_method = "service"
        
        if not success or http_code != 200:
            # Step 2: Fall back to exec-local if Service check failed
            exec_health_url = f"http://localhost:{port}/api/health/details"
            exec_cmd = [
                "kubectl", "--kubeconfig", kubeconfig, "exec", "-n", namespace,
                f"deploy/{K9B_BACKEND_DEPLOYMENT}", "-c", K9B_BACKEND_CONTAINER, "--",
                "curl", "-sS", "-f",
                exec_health_url,
                "--max-time", str(timeout_seconds),
            ]
            
            exec_result = subprocess.run(
                exec_cmd, capture_output=True, text=True, timeout=timeout_seconds + 5
            )
            
            if exec_result.returncode == 0:
                body = exec_result.stdout
                result.check_method = "exec-local"
            else:
                # Both checks failed
                result.failure_class = FAILURE_PROVIDER_CONNECTION_FAILED
                result.message = f"Provider preflight failed: Service check HTTP {http_code}, exec check failed: {exec_result.stderr[:200]}"
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
        
        # Extract provider status from health details
        result.provider_enabled = health_details.get("provider_enabled", False)
        result.provider_configured = health_details.get("provider_configured", False)
        result.provider_invocation_attempted = health_details.get("provider_invocation_attempted", False)
        result.provider_name = health_details.get("provider_name", "")
        result.provider_status = health_details.get("provider_status", "unknown")
        result.provider_phase = health_details.get("phase", "unknown")
        result.diagnosis_provider_enabled = health_details.get("diagnosis_provider_enabled", False)
        
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


# Default service name for CLI
_DEFAULT_SERVICE = "k9b-backend"


def main() -> int:
    """CLI entry point for provider preflight."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run k9b provider preflight check")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    parser.add_argument("--namespace", default=K9B_NAMESPACE, help="k9b namespace")
    parser.add_argument("--service", default=_DEFAULT_SERVICE, help="k9b backend service")
    parser.add_argument("--port", type=int, default=K9B_BACKEND_PORT, help="k9b backend port")
    parser.add_argument("--artifact-dir", required=True, help="Artifact directory")
    parser.add_argument(
        "--require-provider-configured",
        action="store_true",
        default=True,
        help="Require provider to be configured",
    )
    parser.add_argument(
        "--require-provider-invocation-possible",
        action="store_true",
        default=True,
        help="Require provider invocation to be possible",
    )
    
    args = parser.parse_args()
    
    result = run_provider_preflight(
        kubeconfig=args.kubeconfig,
        namespace=args.namespace,
        service=args.service,
        port=args.port,
        artifact_dir=Path(args.artifact_dir),
        require_provider_configured=args.require_provider_configured,
        require_provider_invocation_possible=args.require_provider_invocation_possible,
    )
    
    print(f"Provider Preflight: {'PASSED' if result.passed else 'FAILED'}")
    print(f"Check method: {result.check_method}")
    print(f"Failure class: {result.failure_class}")
    print(f"Message: {result.message}")
    
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
