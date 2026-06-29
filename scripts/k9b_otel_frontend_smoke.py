#!/usr/bin/env python3
"""OTel Demo frontend smoke test and URL resolution.

This module provides:
1. resolve_service_http_url: Resolve HTTP URL from Kubernetes Service
2. k9b_otel_frontend_smoke: Smoke test for OTel frontend-proxy service
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import kubectl_json, log

# HTTP port name patterns for common services
_HTTP_PORT_NAMES = {"http", "service", "frontend-proxy", "web", "http-web", "http1"}
# Common non-HTTP ports to skip
_NON_HTTP_PORTS = {9090, 9093, 4317, 4318, 8888, 3000, 5432, 6379, 9200}


@dataclass
class FrontendSmokeResult:
    """Result of frontend smoke test."""
    
    passed: bool
    success_count: int = 0
    failure_count: int = 0
    target_url: str = ""
    target_service: str = ""
    target_namespace: str = ""
    target_port: int = 0
    failure_class: str | None = None
    message: str = ""
    duration_seconds: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "target_url": self.target_url,
            "target_service": self.target_service,
            "target_namespace": self.target_namespace,
            "target_port": self.target_port,
            "failure_class": self.failure_class,
            "message": self.message,
            "duration_seconds": self.duration_seconds,
        }


# Failure class constants
FAILURE_FRONTEND_SERVICE_NOT_FOUND = "frontend_service_not_found"
FAILURE_FRONTEND_PORT_NOT_FOUND = "frontend_port_not_found"
FAILURE_FRONTEND_SMOKE_NO_SUCCESS = "frontend_smoke_no_success"
FAILURE_FRONTEND_SMOKE_TOO_FEW_SUCCESS = "frontend_smoke_too_few_success"


def resolve_service_http_url(
    kubeconfig: str, namespace: str, service: str
) -> tuple[str | None, int | None, str | None]:
    """Resolve HTTP URL from Kubernetes Service.
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: Service namespace
        service: Service name
        
    Returns:
        Tuple of (url, port, error). url is None if resolution fails.
        port is the resolved HTTP port number.
        error is None on success, or an error message.
    """
    svc_result = kubectl_json(kubeconfig, "services", namespace)
    
    if not svc_result.success or not svc_result.data:
        return None, None, f"Failed to get services in namespace {namespace}"
    
    # Find the service
    svc = None
    for item in svc_result.data.get("items", []):
        if item.get("metadata", {}).get("name") == service:
            svc = item
            break
    
    if not svc:
        return None, None, f"Service {service} not found in namespace {namespace}"
    
    # Extract ports
    ports = svc.get("spec", {}).get("ports", [])
    
    if not ports:
        return None, None, f"Service {service} has no ports defined"
    
    # Find HTTP port
    http_port = _find_http_port(ports)
    
    if http_port is None:
        return None, None, f"No HTTP port found for service {service}"
    
    # Build URL
    fqdn = f"{service}.{namespace}.svc.cluster.local"
    url = f"http://{fqdn}:{http_port}/"
    
    return url, http_port, None


def _find_http_port(ports: list[dict[str, Any]]) -> int | None:
    """Find the HTTP port from a list of service ports.
    
    Logic:
    1. Look for port with name matching HTTP patterns
    2. Look for port 8080 (common for OTel frontend-proxy)
    3. Look for first port that is not a known non-HTTP port
    4. Fall back to first port
    
    Returns:
        Port number or None if no valid port found.
    """
    if not ports:
        return None
    
    # First pass: look for named HTTP ports
    for p in ports:
        port_name = p.get("name", "").lower()
        if port_name in _HTTP_PORT_NAMES:
            return p.get("port")
    
    # Second pass: look for port 8080
    for p in ports:
        if p.get("port") == 8080:
            return 8080
    
    # Third pass: skip known non-HTTP ports
    for p in ports:
        port_num: int | None = p.get("port")
        if port_num and port_num not in _NON_HTTP_PORTS:
            return port_num
    
    # Fallback: first port
    return ports[0].get("port")


def run_frontend_smoke(
    kubeconfig: str,
    namespace: str,
    service: str,
    min_successes: int = 3,
    max_retries: int = 10,
    retry_interval: int = 10,
    artifact_dir: Path | None = None,
) -> FrontendSmokeResult:
    """Run frontend smoke test against OTel frontend-proxy service.
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: OTel Demo namespace
        service: Service name (e.g., "frontend-proxy")
        min_successes: Minimum successful requests to pass
        max_retries: Maximum number of retry attempts
        retry_interval: Seconds between retries
        artifact_dir: Optional directory for artifacts
        
    Returns:
        FrontendSmokeResult with pass/fail and details
    """
    start = time.time()
    
    result = FrontendSmokeResult(
        passed=False,
        target_service=service,
        target_namespace=namespace,
        message="Starting frontend smoke test",
    )
    
    # Resolve service URL
    url, port, error = resolve_service_http_url(kubeconfig, namespace, service)
    
    if error or not url:
        result.failure_class = FAILURE_FRONTEND_SERVICE_NOT_FOUND
        result.message = f"Failed to resolve frontend service: {error}"
        result.duration_seconds = time.time() - start
        _write_result(result, artifact_dir)
        return result
    
    result.target_url = url
    result.target_port = port or 8080
    
    log(f"Frontend smoke: target URL = {url}")
    
    # Create smoke traffic pod
    success_count = 0
    failure_count = 0
    
    for attempt in range(max_retries):
        log(f"Frontend smoke attempt {attempt + 1}/{max_retries}")
        
        # Use kubectl exec with a temp pod to curl the frontend
        smoke_result = _curl_service(kubeconfig, namespace, url)
        
        if smoke_result.success:
            success_count += 1
            log(f"Frontend smoke attempt {attempt + 1}: SUCCESS")
        else:
            failure_count += 1
            log(f"Frontend smoke attempt {attempt + 1}: FAILED - {smoke_result.error}")
        
        # Check if we have enough successes
        if success_count >= min_successes:
            result.passed = True
            result.success_count = success_count
            result.failure_count = failure_count
            result.message = f"Frontend smoke passed: {success_count} successes after {attempt + 1} attempts"
            result.duration_seconds = time.time() - start
            _write_result(result, artifact_dir)
            return result
        
        # Wait before next attempt
        if attempt < max_retries - 1:
            time.sleep(retry_interval)
    
    # Exhausted retries without enough successes
    result.success_count = success_count
    result.failure_count = failure_count
    
    if success_count == 0:
        result.failure_class = FAILURE_FRONTEND_SMOKE_NO_SUCCESS
        result.message = f"Frontend smoke failed: 0 successes after {max_retries} attempts"
    else:
        result.failure_class = FAILURE_FRONTEND_SMOKE_TOO_FEW_SUCCESS
        result.message = f"Frontend smoke failed: only {success_count}/{min_successes} required successes"
    
    result.duration_seconds = time.time() - start
    _write_result(result, artifact_dir)
    return result


@dataclass
class SmokeCurlResult:
    """Result of a single curl attempt."""
    success: bool
    http_code: int = 0
    error: str = ""


def _curl_service(kubeconfig: str, namespace: str, url: str) -> SmokeCurlResult:
    """Curl a service from a temporary pod.
    
    Returns:
        SmokeCurlResult with success status and HTTP code.
    """
    pod_name = f"k9b-frontend-smoke-{int(time.time())}"
    
    # Create a temporary pod for smoke test
    pod_manifest = f"""apiVersion: v1
kind: Pod
metadata:
  name: {pod_name}
  namespace: {namespace}
  labels:
    app: k9b-frontend-smoke
    created-by: k9b-otel-demo-lab
spec:
  restartPolicy: Never
  containers:
  - name: curl
    image: curlimages/curl:latest
    command: ["/bin/sh", "-c"]
    args:
      - |
        code=$(curl -s -o /dev/null -w "%{{http_code}}" --max-time 30 {url})
        echo "HTTP_CODE=$code"
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
            return SmokeCurlResult(success=False, error=f"Failed to create pod: {apply_result.stderr}")
        
        # Wait for pod to complete
        max_wait = 60
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
        
        # Parse HTTP code from logs
        http_code = 0
        for line in logs_result.stdout.split("\n"):
            if "HTTP_CODE=" in line:
                try:
                    http_code = int(line.split("HTTP_CODE=")[1].strip())
                except (ValueError, IndexError):
                    pass
        
        # Check if request was successful (2xx or 3xx)
        success = 200 <= http_code < 400
        
        return SmokeCurlResult(success=success, http_code=http_code)
        
    except subprocess.TimeoutExpired:
        return SmokeCurlResult(success=False, error="Timeout during smoke test")
    except Exception as e:
        return SmokeCurlResult(success=False, error=str(e))
    finally:
        # Fail-safe cleanup: ignore deletion errors to avoid masking real result
        try:
            subprocess.run(
                ["kubectl", "--kubeconfig", kubeconfig, "delete", "pod", pod_name,
                 "-n", namespace, "--wait=false"],
                capture_output=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            pass


def _write_result(result: FrontendSmokeResult, artifact_dir: Path | None) -> None:
    """Write smoke result to artifact directory."""
    if not artifact_dir:
        return
    
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifact_dir / "frontend-smoke-result.json"
    result_path.write_text(json.dumps(result.to_dict(), indent=2))


# CLI entry point
def main() -> int:
    """CLI entry point for frontend smoke test."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run OTel frontend smoke test")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    parser.add_argument("--namespace", default="otel-demo", help="OTel Demo namespace")
    parser.add_argument("--service", default="frontend-proxy", help="Frontend service name")
    parser.add_argument("--artifact-dir", required=True, help="Artifact directory")
    parser.add_argument("--min-successes", type=int, default=3, help="Minimum successful requests")
    parser.add_argument("--max-retries", type=int, default=10, help="Maximum retry attempts")
    parser.add_argument("--retry-interval", type=int, default=10, help="Retry interval in seconds")
    
    args = parser.parse_args()
    
    result = run_frontend_smoke(
        kubeconfig=args.kubeconfig,
        namespace=args.namespace,
        service=args.service,
        min_successes=args.min_successes,
        max_retries=args.max_retries,
        retry_interval=args.retry_interval,
        artifact_dir=Path(args.artifact_dir),
    )
    
    print(f"Frontend Smoke: {'PASSED' if result.passed else 'FAILED'}")
    print(f"Target URL: {result.target_url}")
    print(f"Successes: {result.success_count}, Failures: {result.failure_count}")
    print(f"Message: {result.message}")
    
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
