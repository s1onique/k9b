#!/usr/bin/env python3
"""Backend health gate for provider smoke testing.

Polls /api/health with bounded retries and classifies failures.
Fails fast if backend returns persistent HTTP 500.

Exit codes:
    0 - Backend health check passed (HTTP 200)
    1 - Backend health check failed (classified with failure artifact written)

Usage:
    python scripts/check_backend_health_gate.py \
        --kubeconfig <path> \
        --namespace <ns> \
        --deployment <name> \
        --container <name> \
        --port <port> \
        --max-retries <n> \
        --retry-interval <s> \
        --artifact-dir <path>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Failure class constants
FAILURE_BACKEND_HEALTH_500 = "backend_health_500"
FAILURE_BACKEND_HEALTH_TIMEOUT = "backend_health_timeout"
FAILURE_BACKEND_HEALTH_INVALID_RESPONSE = "backend_health_invalid_response"
FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR = "backend_health_transport_error"


@dataclass
class HealthCheckResult:
    """Structured result from backend health check."""
    
    # Classification
    failure_class: str = ""
    passed: bool = False
    
    # HTTP details
    http_status: int = 0
    final_http_code: str = ""
    
    # Timing
    poll_count: int = 0
    total_elapsed_seconds: float = 0
    
    # Error details
    transport_error: str = ""
    
    # All HTTP statuses seen (for diagnostics)
    http_statuses_seen: list[str] = field(default_factory=list)
    
    # Diagnostics for JSON artifact
    diagnostics: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "failure_class": self.failure_class,
            "passed": self.passed,
            "http_status": self.http_status,
            "final_http_code": self.final_http_code,
            "poll_count": self.poll_count,
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "transport_error": self.transport_error,
            "http_statuses_seen": self.http_statuses_seen,
            "diagnostics": self.diagnostics,
        }


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


def _get_pod_info(
    kubeconfig: str,
    namespace: str,
    label_selector: str = "app.kubernetes.io/name=k9b",
) -> dict:
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
            data: dict[str, Any] = json.loads(result.stdout)
            return data
    except Exception:
        pass
    
    return {"items": []}


def _collect_backend_diagnostics(
    kubeconfig: str,
    namespace: str,
) -> dict:
    """Collect sanitized backend diagnostics."""
    diagnostics: dict = {
        "timestamp": datetime.now(UTC).isoformat(),
    }
    
    # Get pods with app label
    pods_data = _get_pod_info(kubeconfig, namespace)
    
    for pod in pods_data.get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "unknown")
        
        # Pod-level info
        pod_info: dict = {
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
            
            cs_info = {"name": container_name}
            
            if "waiting" in state:
                waiting = state["waiting"]
                cs_info["state"] = "waiting"
                cs_info["reason"] = waiting.get("reason", "")
                cs_info["message"] = waiting.get("message", "")[:200]  # Truncate
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
) -> dict:
    """Collect sanitized scheduler diagnostics."""
    diagnostics: dict = {
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
                
                pod_info: dict = {
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
                    
                    cs_info = {"name": container_name}
                    
                    if "waiting" in state:
                        waiting = state["waiting"]
                        cs_info["state"] = "waiting"
                        cs_info["reason"] = waiting.get("reason", "")
                        cs_info["message"] = waiting.get("message", "")[:200]
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


def _get_provider_config_status(
    kubeconfig: str,
    namespace: str,
) -> dict:
    """Get sanitized provider config status (booleans only, no secrets).
    
    Detection rules:
    - diagnosis_provider_secret_ref_present: K9B_DIAGNOSIS_API_KEY via secretKeyRef
    - small_provider_secret_ref_present: K9B_EXTERNAL_ANALYSIS_API_KEY via secretKeyRef
    - diagnosis_provider_enabled: diagnosis provider config detected (via any indicator)
    - base_url_present: any BASE_URL env var detected
    - model_present: any MODEL env var detected
    """
    status: dict = {
        "diagnosis_provider_enabled": False,
        "diagnosis_provider_secret_ref_present": False,
        "small_provider_secret_ref_present": False,
        "base_url_present": False,
        "model_present": False,
        "api_key_present": False,
    }
    
    # Get deployment JSON for comprehensive inspection
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "get", "deployment", "-n", namespace,
        "-o", "json",
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return status
        
        deploy_data = json.loads(result.stdout)
        
        for item in deploy_data.get("items", []):
            for container in item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []):
                # Check env vars for presence indicators
                env_names = [e.get("name", "") for e in container.get("env", [])]
                for env_name in env_names:
                    # Diagnosis provider enabled indicator
                    if "DIAGNOSIS_PROVIDER_ENABLED" in env_name.upper():
                        status["diagnosis_provider_enabled"] = True
                    if "K9B_DIAGNOSIS" in env_name.upper():
                        status["diagnosis_provider_enabled"] = True
                    # Base URL presence
                    if "BASE_URL" in env_name.upper() or "EXTERNAL_ANALYSIS_BASE_URL" in env_name.upper():
                        status["base_url_present"] = True
                    # Model presence
                    if "MODEL" in env_name.upper() or "EXTERNAL_ANALYSIS_MODEL" in env_name.upper():
                        status["model_present"] = True
                
                # Check secretKeyRef for PROOF-BASED detection
                for env in container.get("env", []):
                    env_name = env.get("name", "")
                    env_src = env.get("valueFrom", {})
                    
                    if "secretKeyRef" in env_src:
                        secret_name = env_src.get("secretKeyRef", {}).get("name", "")
                        secret_key = env_src.get("secretKeyRef", {}).get("key", "")
                        
                        # Proof-based detection:
                        # K9B_DIAGNOSIS_API_KEY + secretKeyRef -> diagnosis_provider_secret_ref_present
                        if env_name == "K9B_DIAGNOSIS_API_KEY":
                            status["diagnosis_provider_secret_ref_present"] = True
                            status["diagnosis_provider_enabled"] = True
                            status["api_key_present"] = True
                        
                        # K9B_EXTERNAL_ANALYSIS_API_KEY + secretKeyRef -> small_provider_secret_ref_present
                        if env_name == "K9B_EXTERNAL_ANALYSIS_API_KEY":
                            status["small_provider_secret_ref_present"] = True
                            status["api_key_present"] = True
                        
                        # Any other API key via secretKeyRef
                        if "API_KEY" in env_name.upper() or env_name.endswith("_KEY"):
                            status["api_key_present"] = True
                        
                        # Diagnosis secret name (regardless of key)
                        if "diagnosis" in secret_name.lower() or "k9b-diagnosis" in secret_name.lower():
                            # But only set enabled if it's actually used for diagnosis
                            if env_name.startswith("K9B_DIAGNOSIS"):
                                status["diagnosis_provider_enabled"] = True
                
                # Also check envFrom for secretRef (alternative pattern)
                for env_from in container.get("envFrom", []):
                    secret_ref = env_from.get("secretRef", {})
                    secret_name = secret_ref.get("name", "")
                    if "diagnosis" in secret_name.lower() or "k9b-diagnosis" in secret_name.lower():
                        status["diagnosis_provider_enabled"] = True
    except Exception:
        pass
    
    return status


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
        result.failure_class = FAILURE_BACKEND_HEALTH_INVALID_RESPONSE
    
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
        status_data = {
            "failure_class": result.failure_class,
            "passed": result.passed,
            "final_http_code": result.final_http_code,
            "poll_count": result.poll_count,
            "max_retries": max_retries,
            "total_elapsed_seconds": round(result.total_elapsed_seconds, 1),
            "http_statuses_seen": http_statuses_seen,
            "transport_error": result.transport_error,
            "timestamp": datetime.now(UTC).isoformat(),
            "diagnostics": result.diagnostics,
            # NOTE: Raw logs omitted - they may contain provider secrets/topology.
            # Logs are collected separately for debugging but NOT included in artifacts.
        }
        
        # Write separate debug logs to RUNNER_TEMP (NOT in lab-artifacts/live)
        # This keeps raw logs outside the upload boundary
        import os
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
        summary_lines = [
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
    
    return result


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backend health gate for provider smoke testing"
    )
    parser.add_argument(
        "--kubeconfig", required=True,
        help="Path to kubeconfig"
    )
    parser.add_argument(
        "--namespace", required=True,
        help="Kubernetes namespace"
    )
    parser.add_argument(
        "--deployment", default="k9b-backend",
        help="Backend deployment name"
    )
    parser.add_argument(
        "--container", default="backend",
        help="Backend container name"
    )
    parser.add_argument(
        "--port", type=int, default=8080,
        help="Backend port"
    )
    parser.add_argument(
        "--max-retries", type=int, default=30,
        help="Maximum polling attempts"
    )
    parser.add_argument(
        "--retry-interval", type=int, default=5,
        help="Seconds between retries"
    )
    parser.add_argument(
        "--artifact-dir", default="./lab-artifacts/live",
        help="Artifact directory"
    )
    
    args = parser.parse_args()
    
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    print("=== Backend Health Gate ===", flush=True)
    print(f"Namespace: {args.namespace}", flush=True)
    print(f"Deployment: {args.deployment}", flush=True)
    print(f"Container: {args.container}", flush=True)
    print(f"Max retries: {args.max_retries} x {args.retry_interval}s = {args.max_retries * args.retry_interval}s", flush=True)
    print("", flush=True)
    
    result = run_health_gate(
        kubeconfig=args.kubeconfig,
        namespace=args.namespace,
        deployment=args.deployment,
        container=args.container,
        port=args.port,
        max_retries=args.max_retries,
        retry_interval=args.retry_interval,
        artifact_dir=artifact_dir,
    )
    
    # Write result artifact
    result_data = result.to_dict()
    result_path = artifact_dir / "provider-smoke" / "backend-health" / "health-check-result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result_data, indent=2))
    
    if result.passed:
        print("\nBackend health gate PASSED", flush=True)
        print(f"HTTP 200 after {result.poll_count} polls ({result.total_elapsed_seconds:.1f}s)", flush=True)
        return 0
    else:
        print(f"\nBackend health gate FAILED: {result.failure_class}", flush=True)
        print(f"Final HTTP: {result.final_http_code}", flush=True)
        print("Artifacts: lab-artifacts/live/provider-smoke/backend-health/", flush=True)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
