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

This module is a thin compatibility façade that imports from split modules.
For LLM-friendly reading, see:
- provider_preflight_models.py - result types and serialization
- provider_preflight_curl.py - curl retry logic
- provider_preflight_health.py - health response evaluation and JSON classification
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from scripts.lab_common.constants import (
    DEFAULT_K9B_BACKEND_CONTAINER,
    DEFAULT_K9B_BACKEND_DEPLOYMENT,
    DEFAULT_K9B_BACKEND_PORT,
    FAILURE_PROVIDER_CONFIG_ERROR,
    FAILURE_PROVIDER_CONNECTION_FAILED,
    FAILURE_PROVIDER_DISABLED_REQUIRED,
    FAILURE_PROVIDER_HEALTH_CONNECTION_FAILED,
    FAILURE_PROVIDER_HEALTH_DNS_FAILED,
    FAILURE_PROVIDER_HEALTH_EMPTY_BODY,
    FAILURE_PROVIDER_HEALTH_INVALID_JSON,
    FAILURE_PROVIDER_HEALTH_NO_HTTP_RESPONSE,
    FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
    FAILURE_PROVIDER_HEALTH_TIMEOUT,
    FAILURE_PROVIDER_HEALTH_TRANSPORT_ERROR,
    FAILURE_PROVIDER_HEALTH_UNHEALTHY,
    FAILURE_PROVIDER_NOT_INITIALIZED,
    FAILURE_PROVIDER_UNAVAILABLE,
    PREFLIGHT_RETRY_DEADLINE_SECONDS,
)
from scripts.lab_common.provider_curl_helpers import (  # noqa: F401
    CurlResult,
    _is_retryable,
)
from scripts.lab_common.provider_preflight_curl import (
    _curl_exec_pod_with_retry,
    _curl_service_pod_with_retry,
)

# Re-export private helpers for backward compatibility with existing tests
# These functions were moved from this module to specialized modules
from scripts.lab_common.provider_preflight_health import (  # noqa: F401
    _evaluate_health_response,
    _evaluate_provider_state,
)
from scripts.lab_common.provider_preflight_models import ProviderPreflightResult

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
    "FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED",
    "FAILURE_PROVIDER_HEALTH_EMPTY_BODY",
    "DEFAULT_K9B_BACKEND_DEPLOYMENT",
    "DEFAULT_K9B_BACKEND_CONTAINER",
    "DEFAULT_K9B_BACKEND_PORT",
    # Also expose _classify_json_parse_failure for tests
    "_classify_json_parse_failure",
    "_looks_like_curl_framing_suffix",
]


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


# Import from split modules for backward compatibility
from scripts.lab_common.provider_preflight_health import (
    _classify_json_parse_failure as _classify_json_parse_failure,
)
from scripts.lab_common.provider_preflight_health import (
    _looks_like_curl_framing_suffix as _looks_like_curl_framing_suffix,
)


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


def _write_result(result: ProviderPreflightResult, artifact_dir: Path) -> None:
    """Write preflight result to artifact directory."""
    result_path = artifact_dir / "provider-preflight-result.json"
    import json
    with open(result_path, "w") as f:
        json.dump(result.to_dict(), f, indent=2)
