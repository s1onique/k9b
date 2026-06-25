"""Kubernetes diagnostics collection for backend health gate."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from typing import Any, cast

# Secret patterns for sanitization in message snippets
_API_KEY_PATTERNS_REDACT = [
    r"sk-[a-zA-Z0-9_\-]{20,}",  # OpenAI API key
    r"sk-proj-[a-zA-Z0-9_\-]{20,}",  # OpenAI project key
    r"sk-ant-[a-zA-Z0-9_\-]{20,}",  # Anthropic API key
    r"Bearer\s+[a-zA-Z0-9_\-]{20,}",  # Bearer token
]

_PRIVATE_IP_PATTERNS_REDACT = [
    r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",  # 10.x.x.x
    r"\b172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b",  # 172.16-31.x.x
    r"\b192\.168\.\d{1,3}\.\d{1,3}\b",  # 192.168.x.x
]

_PRIVATE_URL_PATTERNS_REDACT = [
    r"https?://[^\s]*\.(internal|private|local)[^\s]*",  # Internal/private URLs
]


def _sanitize_message_snippet(message: str | None, max_len: int = 100) -> str:
    """Sanitize a message snippet by redacting secrets and truncating.
    
    Args:
        message: Raw message from container state
        max_len: Maximum length of output
        
    Returns:
        Sanitized message with secrets redacted and truncated
    """
    if not message:
        return ""
    
    sanitized = message
    
    # Redact API keys first
    for pattern in _API_KEY_PATTERNS_REDACT:
        sanitized = re.sub(pattern, "<REDACTED_API_KEY>", sanitized)
    
    # Redact private IPs
    for pattern in _PRIVATE_IP_PATTERNS_REDACT:
        sanitized = re.sub(pattern, "<REDACTED_PRIVATE_IP>", sanitized)
    
    # Redact private/internal URLs
    for pattern in _PRIVATE_URL_PATTERNS_REDACT:
        sanitized = re.sub(pattern, "<REDACTED_PRIVATE_URL>", sanitized)
    
    # Truncate
    if len(sanitized) > max_len:
        sanitized = sanitized[:max_len] + "..."
    
    return sanitized


def _kubectl_exec_health(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    container: str,
    port: int,
) -> tuple[int, str]:
    """Execute health check inside backend container.
    
    Returns:
        Tuple of (http_code_int_or_0, error_message_or_empty)
        - On success: (200, "") or (500, "")
        - On curl failure: (0, "error message")
    """
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "exec", "-n", namespace,
        f"deploy/{deployment}",
        "-c", container,
        "--",
        "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
        f"http://localhost:{port}/api/health",
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        http_code_str = result.stdout.strip()
        
        if not http_code_str or not http_code_str.isdigit():
            # Curl failed or returned non-numeric
            error_msg = result.stderr.strip() or "curl returned empty/non-numeric"
            if result.returncode != 0:
                return 0, error_msg
            return 0, f"unexpected output: {http_code_str}"
        
        return int(http_code_str), ""
    
    except subprocess.TimeoutExpired:
        return 0, "curl timeout"
    except Exception as e:
        return 0, str(e)


def _kubectl_exec_health_details(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    container: str,
    port: int,
) -> tuple[dict | None, str]:
    """Execute health details check inside backend container.
    
    This endpoint provides self-diagnosis when /api/health returns 500.
    
    Returns:
        Tuple of (parsed_json_dict_or_None, error_message_or_empty)
        - On success: ({...}, "")
        - On failure: (None, "error message")
    """
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "exec", "-n", namespace,
        f"deploy/{deployment}",
        "-c", container,
        "--",
        "curl", "-s", "-m", "10",
        f"http://localhost:{port}/api/health/details",
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        
        if result.returncode != 0:
            return None, f"curl failed: {result.stderr.strip()}"
        
        response = result.stdout.strip()
        if not response:
            return None, "empty response"
        
        try:
            data = json.loads(response)
            return data, ""
        except json.JSONDecodeError as e:
            return None, f"invalid JSON: {e}"
    
    except subprocess.TimeoutExpired:
        return None, "curl timeout"
    except Exception as e:
        return None, str(e)


def _get_pod_info(
    kubeconfig: str,
    namespace: str,
    label_selector: str = "app.kubernetes.io/name=k9b",
) -> dict[str, Any]:
    """Get backend pod info using kubectl."""
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "get", "pods", "-n", namespace,
        "-l", label_selector,
        "-o", "json",
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return cast(dict[str, Any], data)
    except Exception:
        pass
    
    return {"items": []}


def _collect_backend_diagnostics(
    kubeconfig: str,
    namespace: str,
) -> dict[str, Any]:
    """Collect sanitized backend diagnostics."""
    diagnostics: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
    }
    
    # Get pods with app label
    pods_data = _get_pod_info(kubeconfig, namespace)
    
    for pod in pods_data.get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "unknown")
        
        # Pod-level info
        pod_info: dict[str, Any] = {
            "name": pod_name,
            "phase": pod.get("status", {}).get("phase", "Unknown"),
        }
        
        # Restart count
        restart_count = 0
        for cs in pod.get("status", {}).get("containerStatuses", []):
            restart_count += cs.get("restartCount", 0)
        pod_info["restart_count"] = restart_count
        
        # Container states
        container_states = []
        for cs in pod.get("status", {}).get("containerStatuses", []):
            container_name = cs.get("name", "unknown")
            state = cs.get("state", {})
            
            cs_info: dict[str, Any] = {"name": container_name}
            
            if "waiting" in state:
                waiting = state["waiting"]
                cs_info["state"] = "waiting"
                cs_info["reason"] = waiting.get("reason", "")
                cs_info["message_snippet"] = _sanitize_message_snippet(waiting.get("message", ""), max_len=200)
            elif "running" in state:
                cs_info["state"] = "running"
            elif "terminated" in state:
                terminated = state["terminated"]
                cs_info["state"] = "terminated"
                cs_info["exit_code"] = terminated.get("exitCode", 0)
                cs_info["reason"] = terminated.get("reason", "")
            else:
                cs_info["state"] = "unknown"
            
            container_states.append(cs_info)
        
        pod_info["containers"] = container_states
        diagnostics[f"pod_{pod_name}"] = pod_info
    
    return diagnostics


def _collect_scheduler_diagnostics(
    kubeconfig: str,
    namespace: str,
) -> dict[str, Any]:
    """Collect sanitized scheduler diagnostics."""
    diagnostics: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
    }
    
    # Get scheduler pods
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "get", "pods", "-n", namespace,
        "-l", "app.kubernetes.io/name=k9b-scheduler",
        "-o", "json",
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            pods_data = json.loads(result.stdout)
            
            for pod in pods_data.get("items", []):
                pod_name = pod.get("metadata", {}).get("name", "unknown")
                
                pod_info: dict[str, Any] = {
                    "name": pod_name,
                    "phase": pod.get("status", {}).get("phase", "Unknown"),
                }
                
                # Restart count
                restart_count = 0
                for cs in pod.get("status", {}).get("containerStatuses", []):
                    restart_count += cs.get("restartCount", 0)
                pod_info["restart_count"] = restart_count
                
                # Container states
                container_states = []
                for cs in pod.get("status", {}).get("containerStatuses", []):
                    container_name = cs.get("name", "unknown")
                    state = cs.get("state", {})
                    
                    cs_info: dict[str, Any] = {"name": container_name}
                    
                    if "waiting" in state:
                        waiting = state["waiting"]
                        cs_info["state"] = "waiting"
                        cs_info["reason"] = waiting.get("reason", "")
                        cs_info["message_snippet"] = _sanitize_message_snippet(waiting.get("message", ""), max_len=200)
                    elif "running" in state:
                        cs_info["state"] = "running"
                    elif "terminated" in state:
                        terminated = state["terminated"]
                        cs_info["state"] = "terminated"
                        cs_info["exit_code"] = terminated.get("exitCode", 0)
                    else:
                        cs_info["state"] = "unknown"
                    
                    container_states.append(cs_info)
                
                pod_info["containers"] = container_states
                diagnostics[f"pod_{pod_name}"] = pod_info
    except Exception:
        pass
    
    return diagnostics


def _collect_backend_logs(
    kubeconfig: str,
    namespace: str,
    container: str = "backend",
    tail_lines: int = 50,
) -> str:
    """Collect recent backend logs (sanitized - no raw API responses)."""
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "logs", "-n", namespace,
        "-l", "app.kubernetes.io/name=k9b",
        "-c", container,
        "--tail", str(tail_lines),
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Return last N lines, truncated
        lines = result.stdout.strip().split("\n")
        return "\n".join(lines[-tail_lines:])
    except Exception as e:
        return f"<logs unavailable: {e}>"


def _collect_scheduler_logs(
    kubeconfig: str,
    namespace: str,
    tail_lines: int = 50,
) -> str:
    """Collect recent scheduler logs (sanitized)."""
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "logs", "-n", namespace,
        "-l", "app.kubernetes.io/name=k9b-scheduler",
        "--tail", str(tail_lines),
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = result.stdout.strip().split("\n")
        return "\n".join(lines[-tail_lines:])
    except Exception as e:
        return f"<logs unavailable: {e}>"
