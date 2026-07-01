# Copyright (c) 2025 Artem Chistyakov
# SPDX-License-Identifier: MIT

"""Curl helpers for provider preflight.

This module contains the curl helpers for checking k9b backend health.
It supports both Service-path checks and exec-local fallback.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass

from .constants import PREFLIGHT_RETRY_CONNECT_TIMEOUT, PREFLIGHT_RETRY_MAX_TIME


@dataclass
class CurlResult:
    """Result of a curl operation with detailed diagnostics."""

    success: bool
    body: str
    http_code: int
    curl_rc: int | None = None  # curl exit code
    stderr: str = ""  # sanitized stderr for diagnostics

    def is_transport_failure(self) -> bool:
        """Check if this is a transport/connection failure (HTTP 0)."""
        return self.http_code == 0 or self.curl_rc is not None and self.curl_rc != 0


def _curl_service_pod(
    kubeconfig: str,
    namespace: str,
    target_url: str,
    timeout_seconds: int = 30,
) -> CurlResult:
    """Curl a URL from a temporary curlimages/curl pod.
    
    Returns:
        CurlResult with detailed diagnostics
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
        # Resolve target host first for better diagnostics
        target_host=$(echo {target_url} | sed -e 's|http://||' -e 's|https://||' -e 's|/.*||')
        echo "RESOLVING_HOST=$target_host"
        nslookup "$target_host" 2>&1 || true
        echo "---CURL_START---"
        code=$(curl -s -o /tmp/response.txt -w "%{{http_code}}" \
            --connect-timeout {PREFLIGHT_RETRY_CONNECT_TIMEOUT} \
            --max-time {PREFLIGHT_RETRY_MAX_TIME} \
            {target_url})
        curl_exit=$?
        echo "CURL_EXIT=$curl_exit"
        echo "HTTP_CODE=$code"
        cat /tmp/response.txt 2>/dev/null || echo "NO_RESPONSE_BODY"
        echo "STDERR_BLOCK"
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
            return CurlResult(
                success=False,
                body=f"Failed to create pod: {apply_result.stderr}",
                http_code=0,
                curl_rc=None,
                stderr=apply_result.stderr[:200],
            )
        
        # Wait for pod to complete
        max_wait = timeout_seconds + 30
        elapsed = 0
        pod_phase = "Unknown"
        while elapsed < max_wait:
            phase_result = subprocess.run(
                ["kubectl", "--kubeconfig", kubeconfig, "get", "pod", pod_name,
                 "-n", namespace, "-o", "jsonpath={.status.phase}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if phase_result.returncode == 0:
                pod_phase = phase_result.stdout.strip()
                if pod_phase == "Succeeded":
                    break
                elif pod_phase == "Failed":
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
        
        # Parse diagnostics from logs
        http_code = 0
        curl_exit: int | None = None
        body = logs_result.stdout
        stderr_parts: list[str] = []
        
        for line in logs_result.stdout.split("\n"):
            if "HTTP_CODE=" in line:
                try:
                    http_code = int(line.split("HTTP_CODE=")[1].strip())
                except (ValueError, IndexError):
                    pass
            elif "CURL_EXIT=" in line:
                try:
                    curl_exit = int(line.split("CURL_EXIT=")[1].strip())
                except (ValueError, IndexError):
                    pass
            elif "RESOLVING_HOST=" in line or "---CURL_START---" in line or "NO_RESPONSE_BODY" in line or "STDERR_BLOCK" in line:
                # Skip diagnostic markers
                pass
            elif line.startswith("server ") or line.startswith("Address ") or ":" in line:
                # nslookup output, include for diagnostics
                stderr_parts.append(line)
        
        # Determine success/failure
        if pod_phase == "Unknown" and elapsed >= max_wait:
            # Pod never reached terminal state
            return CurlResult(
                success=False,
                body=f"Pod timeout: pod_phase={pod_phase} elapsed={elapsed}s max_wait={max_wait}s",
                http_code=0,
                curl_rc=None,
                stderr="Pod timeout",
            )
        
        success = curl_exit == 0 and 200 <= http_code < 400
        
        return CurlResult(
            success=success,
            body=body,
            http_code=http_code,
            curl_rc=curl_exit,
            stderr="\n".join(stderr_parts)[:200],
        )
        
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
) -> CurlResult:
    """Curl a URL from inside a pod via exec.
    
    Returns:
        CurlResult with detailed diagnostics
    """
    exec_cmd = [
        "kubectl", "--kubeconfig", kubeconfig, "exec", "-n", namespace,
        f"deploy/{deployment}", "-c", container, "--",
        "sh", "-c",
        # Always capture curl_rc first, then output HTTP code and body
        # Use exit 0 at end so kubectl exec return code doesn't mask curl failure
        f"""
code=$(curl -sS -o /tmp/resp.txt -w '%{{http_code}}' \
    --connect-timeout {PREFLIGHT_RETRY_CONNECT_TIMEOUT} \
    --max-time {PREFLIGHT_RETRY_MAX_TIME} \
    {target_url})
curl_rc=$?
echo CURL_EXIT=$curl_rc
echo HTTP_CODE=$code
cat /tmp/resp.txt 2>/dev/null || true
exit 0
""",
    ]
    
    exec_result = subprocess.run(
        exec_cmd, capture_output=True, text=True, timeout=timeout_seconds + 5
    )
    
    # Parse HTTP code and curl_rc from output
    http_code = 0
    curl_rc: int | None = None
    body_parts: list[str] = []
    
    for line in exec_result.stdout.split("\n"):
        if "CURL_EXIT=" in line:
            try:
                curl_rc = int(line.split("CURL_EXIT=")[1].strip())
            except (ValueError, IndexError):
                pass
        elif "HTTP_CODE=" in line:
            try:
                http_code = int(line.split("HTTP_CODE=")[1].strip())
            except (ValueError, IndexError):
                pass
        else:
            body_parts.append(line)
    
    body = "\n".join(body_parts)
    stderr = exec_result.stderr
    
    # Always check curl_rc, even if kubectl exec succeeded
    if curl_rc == 0:
        # curl succeeded, check if body is valid JSON
        try:
            json.loads(body)
            return CurlResult(
                success=True,
                body=body,
                http_code=http_code,
                curl_rc=0,
                stderr=stderr[:200],
            )
        except json.JSONDecodeError:
            # Valid HTTP response but invalid JSON - this is NOT a transport failure
            # It will be classified as invalid_json after retries
            return CurlResult(
                success=True,  # HTTP succeeded, but JSON is invalid
                body=body,
                http_code=http_code,
                curl_rc=0,
                stderr=stderr[:200],
            )
    
    # curl failed - parse failure details from stderr/stdout
    combined_output = stderr + exec_result.stdout
    
    if "could not resolve host" in combined_output.lower() or "name or service not known" in combined_output.lower():
        return CurlResult(
            success=False,
            body="DNS resolution failed inside pod",
            http_code=0,
            curl_rc=6,
            stderr="DNS resolution failed",
        )
    if "connection refused" in combined_output.lower():
        return CurlResult(
            success=False,
            body="Connection refused inside pod",
            http_code=0,
            curl_rc=7,
            stderr="Connection refused",
        )
    if "connection timed out" in combined_output.lower() or "timeout" in combined_output.lower():
        return CurlResult(
            success=False,
            body=f"Connection timed out after {timeout_seconds}s inside pod",
            http_code=0,
            curl_rc=28,
            stderr="Connection timeout",
        )
    
    return CurlResult(
        success=False,
        body=combined_output[:200] if combined_output else "Exec curl failed",
        http_code=http_code,
        curl_rc=curl_rc,
        stderr=stderr[:200],
    )


def _is_retryable(curl_result: CurlResult) -> bool:
    """Check if a curl result should be retried.
    
    Retry conditions:
    - HTTP 0 (no response) - likely service not ready
    - curl_rc != 0 (connection failures)
    - HTTP 200 but invalid JSON (service started but not fully ready)
    """
    if curl_result.http_code == 0:
        return True
    
    if curl_result.curl_rc is not None and curl_result.curl_rc != 0:
        return True
    
    # HTTP 2xx but invalid JSON - service may not be fully ready
    if 200 <= curl_result.http_code < 300:
        try:
            json.loads(curl_result.body)
            return False  # Valid JSON, no need to retry
        except json.JSONDecodeError:
            return True  # Invalid JSON, retry
    
    return False
