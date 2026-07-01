"""Provider preflight gate for k9b live labs.

This module provides the P0b phase that checks k9b backend's diagnosis provider
status BEFORE expensive lab install/injection/traffic phases.

Both CNPG and OTel labs should use run_provider_preflight() instead of
implementing their own provider preflight logic.

The gate checks via Service path first, then falls back to exec-local curl:
1. Service path check: http://k9b-backend.k9b:8080/api/health/details (from temp curl pod)
2. Optional exec-local fallback: localhost:8080 inside backend pod (if Service fails)

Retry behavior:
- Bounded retry for up to 60s with exponential backoff (1s, 2s, 4s, 8s, 8s...)
- HTTP 0 / connection failures are retried
- Invalid JSON after 2xx is retried
- After retries exhausted, classifies based on curl_rc:
  - curl_rc=7  -> provider_health_connection_failed
  - curl_rc=6  -> provider_health_dns_failed
  - curl_rc=28 -> provider_health_timeout
  - http=000   -> provider_health_no_http_response
  - 2xx invalid JSON -> provider_health_invalid_json
  - non-2xx JSON -> provider_health_unhealthy

Failure classification:
- provider disabled and diagnosis required -> provider_disabled_required
- provider configured but unavailable -> provider_unavailable
- provider not initialized -> provider_not_initialized
- transport/connection failure (HTTP 0) -> provider_health_transport_error (and subtypes)
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.lab_common.constants import (
    DEFAULT_K9B_BACKEND_CONTAINER,
    DEFAULT_K9B_BACKEND_DEPLOYMENT,
    DEFAULT_K9B_BACKEND_PORT,
    FAILURE_PROVIDER_CONFIG_ERROR,
    FAILURE_PROVIDER_CONNECTION_FAILED,
    FAILURE_PROVIDER_DISABLED_REQUIRED,
    FAILURE_PROVIDER_HEALTH_CONNECTION_FAILED,
    FAILURE_PROVIDER_HEALTH_DNS_FAILED,
    FAILURE_PROVIDER_HEALTH_INVALID_JSON,
    FAILURE_PROVIDER_HEALTH_NO_HTTP_RESPONSE,
    FAILURE_PROVIDER_HEALTH_TIMEOUT,
    FAILURE_PROVIDER_HEALTH_TRANSPORT_ERROR,
    FAILURE_PROVIDER_HEALTH_UNHEALTHY,
    FAILURE_PROVIDER_NOT_INITIALIZED,
    FAILURE_PROVIDER_UNAVAILABLE,
    PREFLIGHT_RETRY_DEADLINE_SECONDS,
    PREFLIGHT_RETRY_INITIAL_SLEEP_SECONDS,
    PREFLIGHT_RETRY_MAX_SLEEP_SECONDS,
)
from scripts.lab_common.provider_curl_helpers import (
    CurlResult,
    _curl_exec_pod,
    _curl_service_pod,
    _is_retryable,
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
    "FAILURE_PROVIDER_HEALTH_TRANSPORT_ERROR",
    "FAILURE_PROVIDER_HEALTH_CONNECTION_FAILED",
    "FAILURE_PROVIDER_HEALTH_DNS_FAILED",
    "FAILURE_PROVIDER_HEALTH_TIMEOUT",
    "FAILURE_PROVIDER_HEALTH_NO_HTTP_RESPONSE",
    "FAILURE_PROVIDER_HEALTH_INVALID_JSON",
    "FAILURE_PROVIDER_HEALTH_UNHEALTHY",
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


def _classify_curl_failure(curl_result: CurlResult) -> tuple[str, str]:
    """Classify a curl failure into a failure class and message.
    
    Args:
        curl_result: The failed curl result
        
    Returns:
        Tuple of (failure_class, message)
    """
    if curl_result.curl_rc is not None:
        if curl_result.curl_rc == 7:
            return FAILURE_PROVIDER_HEALTH_CONNECTION_FAILED, \
                f"Connection failed: curl_rc={curl_result.curl_rc}"
        elif curl_result.curl_rc == 6:
            return FAILURE_PROVIDER_HEALTH_DNS_FAILED, \
                f"DNS resolution failed: curl_rc={curl_result.curl_rc}"
        elif curl_result.curl_rc == 28:
            return FAILURE_PROVIDER_HEALTH_TIMEOUT, \
                f"Request timeout: curl_rc={curl_result.curl_rc}"
        elif curl_result.curl_rc != 0:
            return FAILURE_PROVIDER_HEALTH_TRANSPORT_ERROR, \
                f"Curl failed: curl_rc={curl_result.curl_rc}"
    
    if curl_result.http_code == 0:
        return FAILURE_PROVIDER_HEALTH_NO_HTTP_RESPONSE, \
            "No HTTP response received (HTTP 0)"
    
    return FAILURE_PROVIDER_HEALTH_TRANSPORT_ERROR, \
        f"Transport error: http_code={curl_result.http_code}"


# =============================================================================
# Main preflight function with retry support
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
    
    Uses Service-path check first with retry, then falls back to exec-local if needed.
    
    Retry behavior:
    - Bounded retry for up to 60s with exponential backoff
    - HTTP 0 / connection failures are retried
    - Invalid JSON after 2xx is retried
    - After retries exhausted, classifies based on curl_rc
    
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
    exec_health_url = f"http://localhost:{port}/api/health/details"
    
    try:
        # Step 1: Service-path check with retry
        curl_result = _curl_service_pod_with_retry(
            kubeconfig=kubeconfig,
            namespace=namespace,
            target_url=health_url,
            timeout_seconds=timeout_seconds,
        )
        result.check_method = "service"
        
        if curl_result.success and curl_result.http_code == 200:
            return _evaluate_health_response(
                result=result,
                curl_result=curl_result,
                start=start,
                artifact_dir=artifact_dir,
                require_provider_configured=require_provider_configured,
                require_provider_invocation_possible=require_provider_invocation_possible,
            )
        
        # Step 2: Fall back to exec-local with retry if Service check failed
        exec_result = _curl_exec_pod_with_retry(
            kubeconfig=kubeconfig,
            namespace=namespace,
            deployment=backend_deployment,
            container=backend_container,
            target_url=exec_health_url,
            timeout_seconds=timeout_seconds,
        )
        result.check_method = "exec-local"
        
        if exec_result.success and exec_result.http_code == 200:
            return _evaluate_health_response(
                result=result,
                curl_result=exec_result,
                start=start,
                artifact_dir=artifact_dir,
                require_provider_configured=require_provider_configured,
                require_provider_invocation_possible=require_provider_invocation_possible,
            )
        
        final_result = exec_result if not exec_result.success else curl_result
        failure_class, failure_message = _classify_curl_failure(final_result)
        
        result.failure_class = failure_class
        result.message = f"Provider preflight failed after {PREFLIGHT_RETRY_DEADLINE_SECONDS}s retry: {failure_message}"
        result.duration_seconds = time.time() - start
        _write_result(result, artifact_dir)
        return result
        
    except subprocess.TimeoutExpired:
        result.failure_class = FAILURE_PROVIDER_HEALTH_TIMEOUT
        result.message = f"Provider preflight timed out after {timeout_seconds}s"
        result.duration_seconds = time.time() - start
        _write_result(result, artifact_dir)
        return result
    except Exception as e:
        result.failure_class = FAILURE_PROVIDER_HEALTH_TRANSPORT_ERROR
        result.message = f"Provider preflight error: {str(e)}"
        result.duration_seconds = time.time() - start
        _write_result(result, artifact_dir)
        return result


def _curl_service_pod_with_retry(
    kubeconfig: str,
    namespace: str,
    target_url: str,
    timeout_seconds: int = 30,
) -> CurlResult:
    """Run _curl_service_pod with bounded retry and exponential backoff."""
    deadline = time.time() + PREFLIGHT_RETRY_DEADLINE_SECONDS
    attempt = 0
    sleep_s: float = float(PREFLIGHT_RETRY_INITIAL_SLEEP_SECONDS)
    last_result: CurlResult | None = None
    
    while time.time() < deadline:
        attempt += 1
        
        curl_result = _curl_service_pod(
            kubeconfig=kubeconfig,
            namespace=namespace,
            target_url=target_url,
            timeout_seconds=timeout_seconds,
        )
        last_result = curl_result
        
        if curl_result.success and curl_result.http_code == 200:
            try:
                json.loads(curl_result.body)
                return curl_result
            except json.JSONDecodeError:
                pass
        
        if not _is_retryable(curl_result):
            return curl_result
        
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        
        sleep_for = min(sleep_s, remaining)
        if sleep_for > 0:
            time.sleep(sleep_for)
        
        if sleep_s < PREFLIGHT_RETRY_MAX_SLEEP_SECONDS:
            sleep_s = min(sleep_s * 2, PREFLIGHT_RETRY_MAX_SLEEP_SECONDS)
    
    return last_result or CurlResult(
        success=False,
        body=f"Retry deadline exceeded after {attempt} attempts",
        http_code=0,
        curl_rc=None,
        stderr="Retry deadline exceeded",
    )


def _curl_exec_pod_with_retry(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    container: str,
    target_url: str,
    timeout_seconds: int = 30,
) -> CurlResult:
    """Run _curl_exec_pod with bounded retry and exponential backoff."""
    deadline = time.time() + PREFLIGHT_RETRY_DEADLINE_SECONDS
    attempt = 0
    sleep_s: float = float(PREFLIGHT_RETRY_INITIAL_SLEEP_SECONDS)
    last_result: CurlResult | None = None
    
    while time.time() < deadline:
        attempt += 1
        
        curl_result = _curl_exec_pod(
            kubeconfig=kubeconfig,
            namespace=namespace,
            deployment=deployment,
            container=container,
            target_url=target_url,
            timeout_seconds=timeout_seconds,
        )
        last_result = curl_result
        
        if curl_result.success and curl_result.http_code == 200:
            try:
                json.loads(curl_result.body)
                return curl_result
            except json.JSONDecodeError:
                pass
        
        if not _is_retryable(curl_result):
            return curl_result
        
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        
        sleep_for = min(sleep_s, remaining)
        if sleep_for > 0:
            time.sleep(sleep_for)
        
        if sleep_s < PREFLIGHT_RETRY_MAX_SLEEP_SECONDS:
            sleep_s = min(sleep_s * 2, PREFLIGHT_RETRY_MAX_SLEEP_SECONDS)
    
    return last_result or CurlResult(
        success=False,
        body=f"Retry deadline exceeded after {attempt} attempts",
        http_code=0,
        curl_rc=None,
        stderr="Retry deadline exceeded",
    )


def _evaluate_health_response(
    result: ProviderPreflightResult,
    curl_result: CurlResult,
    start: float,
    artifact_dir: Path,
    require_provider_configured: bool,
    require_provider_invocation_possible: bool,
) -> ProviderPreflightResult:
    """Evaluate a successful health response and determine provider state."""
    try:
        health_details = json.loads(curl_result.body)
    except json.JSONDecodeError as exc:
        # Enhanced diagnostics: include body prefix and JSON parse error
        # This helps distinguish HTML/SPA fallback from malformed JSON
        body_prefix = curl_result.body[:500] if curl_result.body else ""
        json_error_msg = f"line {exc.lineno}, col {exc.colno}: {exc.msg}" if hasattr(exc, 'lineno') else str(exc)
        
        # Classify as INVALID_JSON for 2xx responses with invalid JSON
        # This is distinct from transport/connection errors
        result.failure_class = FAILURE_PROVIDER_HEALTH_INVALID_JSON
        result.message = (
            f"Invalid JSON response from /api/health/details (HTTP {curl_result.http_code}). "
            f"JSON parse error: {json_error_msg}. "
            f"Body prefix (first 200 chars): {body_prefix[:200]!r}"
        )
        result.duration_seconds = time.time() - start
        _write_result(result, artifact_dir)
        return result
    
    result.parsed_status = parse_provider_status_from_health_details(health_details)
    
    result.provider_enabled = result.parsed_status.provider_enabled
    result.provider_configured = result.parsed_status.provider_configured
    result.provider_invocation_attempted = result.parsed_status.provider_invocation_attempted
    result.provider_name = result.parsed_status.provider_name
    result.provider_status = result.parsed_status.provider_status
    result.provider_phase = result.parsed_status.provider_phase
    result.diagnosis_provider_enabled = result.parsed_status.diagnosis_provider_enabled
    
    primary_failure = health_details.get("primary_failure_class", "")
    
    result = _evaluate_provider_state(
        result=result,
        primary_failure=primary_failure,
        require_provider_configured=require_provider_configured,
        require_provider_invocation_possible=require_provider_invocation_possible,
    )
    
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
    if primary_failure == "dependency_provider_connection_failed":
        result.failure_class = FAILURE_PROVIDER_UNAVAILABLE
        result.message = "Diagnosis provider unavailable: dependency_provider_connection_failed"
        result.passed = False
        return result
    
    if not result.provider_enabled and require_provider_configured:
        result.failure_class = FAILURE_PROVIDER_DISABLED_REQUIRED
        result.message = "Diagnosis provider disabled but required"
        result.passed = False
        return result
    
    if not result.provider_configured and require_provider_configured:
        result.failure_class = FAILURE_PROVIDER_UNAVAILABLE
        result.message = "Diagnosis provider not configured"
        result.passed = False
        return result
    
    if result.provider_phase in ("not_initialized", "unknown"):
        if require_provider_invocation_possible:
            result.failure_class = FAILURE_PROVIDER_NOT_INITIALIZED
            result.message = f"Diagnosis provider not initialized (phase={result.provider_phase})"
            result.passed = False
            return result
    
    if result.provider_status in ("unavailable", "failed", "error"):
        result.failure_class = FAILURE_PROVIDER_UNAVAILABLE
        result.message = f"Diagnosis provider unavailable (status={result.provider_status})"
        result.passed = False
        return result
    
    result.passed = True
    result.message = "Provider preflight passed"
    result.failure_class = None
    return result


def _write_result(result: ProviderPreflightResult, artifact_dir: Path) -> None:
    """Write preflight result to artifact directory."""
    result_path = artifact_dir / "provider-preflight-result.json"
    result_path.write_text(json.dumps(result.to_dict(), indent=2))
