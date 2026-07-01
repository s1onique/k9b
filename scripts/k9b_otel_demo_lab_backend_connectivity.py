#!/usr/bin/env python3
"""Backend connectivity preflight gate (P0c) for k9b OTel demo lab.

This module provides the P0c phase that checks if the k9b scheduler can reach
the backend's /api/incidents endpoint BEFORE expensive OTel demo install phases.

This catches the --unsafe-bind misconfiguration (backend binding only to 127.0.0.1)
before P4c collapses into real_pass_artifacts_missing.

The check runs from a scheduler pod exec to verify the scheduler can reach the backend
via the Kubernetes Service (k9b-backend.k9b.svc.cluster.local:8080).
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .k9b_otel_demo_lab_constants import (
    FAILURE_BACKEND_INCIDENTS_ENDPOINT_UNHEALTHY,
    FAILURE_BACKEND_SERVICE_UNREACHABLE,
    K9B_BACKEND_PORT,
    K9B_BACKEND_SERVICE,
)


@dataclass
class BackendConnectivityResult:
    """Result of backend connectivity preflight check."""
    
    passed: bool = False
    failure_class: str | None = None
    message: str = ""
    backend_reachable: bool = False
    incidents_endpoint_status: int | None = None
    incidents_total: int | None = None
    incidents_found: list[dict[str, Any]] = field(default_factory=list)
    check_method: str = ""  # "scheduler-exec" or "service-pod"
    duration_seconds: float = 0.0
    attempt_count: int = 0  # Number of attempts made
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failure_class": self.failure_class,
            "message": self.message,
            "backend_reachable": self.backend_reachable,
            "incidents_endpoint_status": self.incidents_endpoint_status,
            "incidents_total": self.incidents_total,
            "incidents_found": self.incidents_found,
            "check_method": self.check_method,
            "duration_seconds": self.duration_seconds,
            "attempt_count": self.attempt_count,
        }


def run_backend_connectivity_preflight(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
    scheduler_namespace: str | None = None,
    scheduler_deployment: str = "k9b-scheduler",
    scheduler_container: str = "scheduler",
    backend_service: str = K9B_BACKEND_SERVICE,
    backend_port: int = K9B_BACKEND_PORT,
    timeout_seconds: int = 30,
) -> BackendConnectivityResult:
    """Run backend connectivity preflight check.

    This checks if the scheduler can reach the backend's /api/incidents endpoint.
    The check is performed by executing Python code inside the scheduler pod to
    make an HTTP request to the backend service.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: k9b namespace where k9b is deployed
        artifact_dir: Directory to write artifacts
        scheduler_namespace: Namespace of scheduler pod (defaults to namespace)
        scheduler_deployment: Name of scheduler deployment
        scheduler_container: Name of scheduler container
        backend_service: Backend service DNS name
        backend_port: Backend service port
        timeout_seconds: Timeout for the check

    Returns:
        BackendConnectivityResult with pass/fail and details
    """
    start = time.time()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    result = BackendConnectivityResult(
        passed=False,
        message="Starting backend connectivity preflight",
        check_method="unknown",
    )
    
    if scheduler_namespace is None:
        scheduler_namespace = namespace
    
    backend_url = f"http://{backend_service}.{namespace}.svc.cluster.local:{backend_port}/api/incidents"
    
    # Python code to run inside scheduler pod
    # Requires: HTTP 200, payload is dict, payload contains "incidents" key, incidents is list
    python_check = f'''
import json
import urllib.request
import urllib.error

try:
    with urllib.request.urlopen("{backend_url}", timeout=5) as r:
        status = r.status
        payload = json.load(r)
        
        # Validate response shape
        if status != 200:
            print(json.dumps({{
                "reachable": True,
                "healthy": False,
                "status": status,
                "total": 0,
                "incidents": [],
                "failure_class": "backend_incidents_endpoint_unhealthy",
                "error": f"HTTP {{status}} - expected 200",
            }}))
        elif not isinstance(payload, dict):
            print(json.dumps({{
                "reachable": True,
                "healthy": False,
                "status": status,
                "total": 0,
                "incidents": [],
                "failure_class": "backend_incidents_endpoint_unexpected_shape",
                "error": "payload is not a dict",
            }}))
        elif "incidents" not in payload:
            print(json.dumps({{
                "reachable": True,
                "healthy": False,
                "status": status,
                "total": payload.get("total", 0),
                "incidents": [],
                "failure_class": "backend_incidents_endpoint_unexpected_shape",
                "error": "payload missing 'incidents' key",
            }}))
        elif not isinstance(payload.get("incidents"), list):
            print(json.dumps({{
                "reachable": True,
                "healthy": False,
                "status": status,
                "total": payload.get("total", 0),
                "incidents": [],
                "failure_class": "backend_incidents_endpoint_unexpected_shape",
                "error": "payload.incidents is not a list",
            }}))
        else:
            print(json.dumps({{
                "reachable": True,
                "healthy": True,
                "status": status,
                "total": payload.get("total", 0),
                "incidents": payload.get("incidents", []),
                "failure_class": None,
                "error": None,
            }}))
except urllib.error.HTTPError as e:
    print(json.dumps({{
        "reachable": True,
        "healthy": False,
        "status": e.code,
        "total": 0,
        "incidents": [],
        "failure_class": "backend_incidents_endpoint_unhealthy",
        "error": f"HTTPError {{e.code}}",
    }}))
except Exception as e:
    print(json.dumps({{
        "reachable": False,
        "healthy": False,
        "status": None,
        "total": 0,
        "incidents": [],
        "failure_class": "backend_service_unreachable_from_scheduler",
        "error": str(e),
    }}))
'''
    
    kubectl_cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "-n", scheduler_namespace,
        "exec", f"deploy/{scheduler_deployment}",
        "-c", scheduler_container,
        "--", "python", "-c", python_check,
    ]
    
    deadline = time.time() + timeout_seconds
    attempt = 0
    
    while time.time() < deadline:
        attempt += 1
        
        try:
            proc = subprocess.run(
                kubectl_cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    check_result = json.loads(proc.stdout.strip())
                    
                    is_reachable = check_result.get("reachable", False)
                    is_healthy = check_result.get("healthy", False)
                    result.backend_reachable = is_reachable
                    result.incidents_endpoint_status = check_result.get("status")
                    result.incidents_total = check_result.get("total", 0)
                    result.incidents_found = check_result.get("incidents", [])
                    result.check_method = "scheduler-exec"
                    
                    if is_reachable and is_healthy:
                        # Full success: reachable AND healthy (HTTP 200 + valid payload)
                        result.passed = True
                        result.failure_class = None
                        result.message = (
                            f"Backend reachable via Service: HTTP {result.incidents_endpoint_status}, "
                            f"{result.incidents_total} incident(s) found"
                        )
                        result.duration_seconds = time.time() - start
                        result.attempt_count = attempt
                        _write_result(result, artifact_dir)
                        return result
                    
                    if is_reachable and not is_healthy:
                        # Reachable but unhealthy (HTTP error or bad payload shape)
                        # This is probably a real contract/config failure, not Service warm-up.
                        result.passed = False
                        result.failure_class = check_result.get(
                            "failure_class",
                            FAILURE_BACKEND_INCIDENTS_ENDPOINT_UNHEALTHY
                        )
                        error_msg = check_result.get("error", "Unknown error")
                        result.message = f"Backend /api/incidents unhealthy: {error_msg}"
                        result.duration_seconds = time.time() - start
                        result.attempt_count = attempt
                        _write_result(result, artifact_dir)
                        return result
                    
                    # Not reachable: retry transient scheduler -> backend Service connectivity failures.
                    # Do not return here. Let the loop sleep with exponential backoff and retry.
                    result.passed = False
                    result.failure_class = FAILURE_BACKEND_SERVICE_UNREACHABLE
                    error_msg = check_result.get("error", "Unknown error")
                    result.message = f"Backend unreachable from scheduler: {error_msg}"
                    
                except json.JSONDecodeError:
                    # Retry on parse errors
                    pass
        
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            # Retry on execution errors
            pass
        
        # Sleep with exponential backoff
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        sleep_for = min(2 ** min(attempt - 1, 3), remaining)
        if sleep_for > 0:
            time.sleep(sleep_for)
    
    # All retries exhausted
    result.passed = False
    result.failure_class = FAILURE_BACKEND_SERVICE_UNREACHABLE
    result.message = f"Backend connectivity check failed after {attempt} attempts"
    result.duration_seconds = time.time() - start
    result.attempt_count = attempt
    _write_result(result, artifact_dir)
    return result


def _write_result(result: BackendConnectivityResult, artifact_dir: Path) -> None:
    """Write preflight result to artifact directory."""
    result_path = artifact_dir / "backend-connectivity-result.json"
    result_path.write_text(json.dumps(result.to_dict(), indent=2))
