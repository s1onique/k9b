"""Main module for scheduler health gate.

This gate checks scheduler health BEFORE incident discovery to fail fast
when the scheduler is unhealthy instead of waiting 120 seconds for
incidents that will never be produced.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .types import SchedulerHealthResult

# Failure class constants
FAILURE_SCHEDULER_NOT_READY = "scheduler_not_ready"
FAILURE_SCHEDULER_CRASH_LOOP = "scheduler_crash_loop"
FAILURE_SCHEDULER_MISSING = "scheduler_missing"

# Scheduler deployment name pattern
SCHEDULER_DEPLOYMENT_NAME = "k9b-scheduler"

# Fallback pod selector (used if derivation from deployment fails)
SCHEDULER_POD_SELECTOR = "app.kubernetes.io/name=k9b-scheduler"


def _run_kubectl(
    kubeconfig: str,
    namespace: str,
    args: list[str],
    timeout: int = 30,
) -> tuple[int, str, str]:
    """Run kubectl command and return (returncode, stdout, stderr)."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace, *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "kubectl command timed out"
    except Exception as e:
        return 1, "", str(e)


def _get_scheduler_deployment_status(
    kubeconfig: str,
    namespace: str,
) -> dict[str, Any]:
    """Get scheduler deployment status."""
    # Try to get the deployment
    rc, stdout, _ = _run_kubectl(
        kubeconfig, namespace,
        ["get", "deployment", SCHEDULER_DEPLOYMENT_NAME, "-o", "json"]
    )
    
    if rc != 0:
        return {
            "found": False,
            "name": SCHEDULER_DEPLOYMENT_NAME,
            "error": "deployment not found",
        }
    
    try:
        data = json.loads(stdout)
        status = data.get("status", {})
        spec_replicas = data.get("spec", {}).get("replicas", 0)
        
        # Get conditions for availability
        conditions = status.get("conditions", [])
        available_condition = None
        for cond in conditions:
            if cond.get("type") == "Available":
                available_condition = cond
                break
        
        return {
            "found": True,
            "name": SCHEDULER_DEPLOYMENT_NAME,
            "replicas": spec_replicas,
            "ready_replicas": status.get("readyReplicas", 0),
            "available_replicas": status.get("availableReplicas", 0),
            "updated_replicas": status.get("updatedReplicas", 0),
            "available_condition": available_condition,
        }
    except (json.JSONDecodeError, KeyError) as e:
        return {
            "found": True,
            "name": SCHEDULER_DEPLOYMENT_NAME,
            "error": f"failed to parse deployment status: {e}",
        }


def _get_scheduler_pod_selector(
    kubeconfig: str,
    namespace: str,
    deployment_name: str,
) -> str:
    """Derive pod selector from Deployment.spec.selector.
    
    Uses the canonical relationship between Deployment and Pods per Kubernetes model.
    Falls back to hard-coded selector if derivation fails.
    """
    rc, stdout, _ = _run_kubectl(
        kubeconfig, namespace,
        ["get", "deployment", deployment_name, "-o", "json"]
    )
    
    if rc != 0:
        return SCHEDULER_POD_SELECTOR
    
    try:
        data = json.loads(stdout)
        selector = data.get("spec", {}).get("selector", {})
        labels = selector.get("matchLabels", {})
        
        if labels:
            selector_parts = [f"{k}={v}" for k, v in sorted(labels.items())]
            return ",".join(selector_parts)
        
        return SCHEDULER_POD_SELECTOR
    except (json.JSONDecodeError, KeyError):
        return SCHEDULER_POD_SELECTOR


def _get_scheduler_pods(
    kubeconfig: str,
    namespace: str,
    selector: str,
) -> dict[str, Any]:
    """Get scheduler pods with full status.
    
    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        selector: Pod selector (derived from Deployment.spec.selector)
    """
    rc, stdout, _ = _run_kubectl(
        kubeconfig, namespace,
        ["get", "pods", "-l", selector, "-o", "json"]
    )
    
    if rc != 0:
        return {"items": [], "error": "failed to get scheduler pods"}
    
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"items": [], "error": "failed to parse pods JSON"}


def _get_namespace_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get recent namespace events related to scheduler."""
    rc, stdout, _ = _run_kubectl(
        kubeconfig, namespace,
        ["get", "events", "--sort-by=.lastTimestamp", "-o", "json"]
    )
    
    if rc != 0:
        return []
    
    try:
        data = json.loads(stdout)
        events = data.get("items", [])
        
        # Filter to scheduler-related events
        scheduler_events = [
            e for e in events
            if "scheduler" in e.get("involvedObject", {}).get("name", "").lower()
            or "scheduler" in e.get("reason", "").lower()
        ]
        
        # Return last N events
        return scheduler_events[-limit:]
    except json.JSONDecodeError:
        return []


def _collect_scheduler_logs(
    kubeconfig: str,
    namespace: str,
    selector: str,
    tail_lines: int = 100,
) -> dict[str, str]:
    """Collect scheduler logs from all pods.
    
    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        selector: Pod selector (derived from Deployment.spec.selector)
        tail_lines: Number of log lines to retrieve
    """
    logs: dict[str, str] = {}
    
    pods_data = _get_scheduler_pods(kubeconfig, namespace, selector)
    for pod in pods_data.get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "unknown")
        
        rc, stdout, _ = _run_kubectl(
            kubeconfig, namespace,
            ["logs", f"pod/{pod_name}", "--tail", str(tail_lines)]
        )
        logs[pod_name] = stdout if rc == 0 else f"<logs unavailable: exit code {rc}>"
        
        # Also get previous log if available
        rc_prev, stdout_prev, _ = _run_kubectl(
            kubeconfig, namespace,
            ["logs", f"pod/{pod_name}", "--previous", "--tail", str(tail_lines)]
        )
        if rc_prev == 0 and stdout_prev:
            logs[f"{pod_name}.previous"] = stdout_prev
    
    return logs


def _check_crash_loop(pods_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Check for CrashLoopBackOff or crashed containers."""
    crash_loop_pods: list[dict[str, Any]] = []
    
    for pod in pods_data.get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "")
        phase = pod.get("status", {}).get("phase", "")
        
        container_statuses = pod.get("status", {}).get("containerStatuses", [])
        for cs in container_statuses:
            container_name = cs.get("name", "")
            restart_count = cs.get("restartCount", 0)
            state = cs.get("state", {})
            
            waiting = state.get("waiting", {})
            waiting_reason = waiting.get("reason", "")
            
            terminated = state.get("terminated", {})
            last_state = cs.get("lastState", {})
            last_terminated = last_state.get("terminated", {})
            
            # Check CrashLoopBackOff
            if waiting_reason == "CrashLoopBackOff":
                crash_loop_pods.append({
                    "pod": pod_name,
                    "container": container_name,
                    "reason": waiting_reason,
                    "restart_count": restart_count,
                    "message": waiting.get("message", ""),
                    "phase": phase,
                })
            
            # Check Error state
            elif waiting_reason == "Error":
                crash_loop_pods.append({
                    "pod": pod_name,
                    "container": container_name,
                    "reason": waiting_reason,
                    "restart_count": restart_count,
                    "message": waiting.get("message", ""),
                    "phase": phase,
                })
            
            # Check terminated with non-zero exit
            elif terminated:
                exit_code = terminated.get("exitCode", 0)
                reason = terminated.get("reason", "")
                if exit_code != 0 and reason in ("Error", "Completed", ""):
                    crash_loop_pods.append({
                        "pod": pod_name,
                        "container": container_name,
                        "reason": f"exit_code_{exit_code}",
                        "exit_code": exit_code,
                        "restart_count": restart_count,
                        "phase": phase,
                    })
            
            # Check lastState.terminated
            elif last_terminated:
                exit_code = last_terminated.get("exitCode", 0)
                reason = last_terminated.get("reason", "")
                if exit_code != 0 and reason in ("Error", "Completed", ""):
                    crash_loop_pods.append({
                        "pod": pod_name,
                        "container": container_name,
                        "reason": f"previous_exit_code_{exit_code}",
                        "exit_code": exit_code,
                        "restart_count": restart_count,
                        "phase": phase,
                    })
    
    return crash_loop_pods


def _check_waiting_pods(pods_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Check for pods in waiting state."""
    waiting_pods: list[dict[str, Any]] = []
    
    for pod in pods_data.get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "")
        phase = pod.get("status", {}).get("phase", "")
        
        container_statuses = pod.get("status", {}).get("containerStatuses", [])
        for cs in container_statuses:
            state = cs.get("state", {})
            waiting = state.get("waiting", {})
            waiting_reason = waiting.get("reason", "")
            
            if waiting_reason and waiting_reason not in ("CrashLoopBackOff", "Error"):
                # Only include non-crash-loop waiting states
                waiting_pods.append({
                    "pod": pod_name,
                    "container": cs.get("name", ""),
                    "reason": waiting_reason,
                    "message": waiting.get("message", ""),
                    "phase": phase,
                })
    
    return waiting_pods


def _check_terminated_pods(pods_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Check for terminated pods."""
    terminated_pods: list[dict[str, Any]] = []
    
    for pod in pods_data.get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "")
        phase = pod.get("status", {}).get("phase", "")
        
        # Pod-level terminated state
        if phase == "Succeeded":
            terminated_pods.append({
                "pod": pod_name,
                "reason": "pod_succeeded",
                "phase": phase,
            })
        elif phase == "Failed":
            terminated_pods.append({
                "pod": pod_name,
                "reason": "pod_failed",
                "phase": phase,
            })
    
    return terminated_pods


def run_scheduler_health_gate(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
) -> SchedulerHealthResult:
    """Check scheduler health and classify failures.
    
    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        artifact_dir: Directory for artifacts
        
    Returns:
        SchedulerHealthResult with classification and diagnostics
    """
    result = SchedulerHealthResult()
    result.scheduler_diagnosis["timestamp"] = datetime.now(UTC).isoformat()
    
    # Create artifact directory
    scheduler_dir = artifact_dir / "provider-smoke" / "scheduler-health"
    scheduler_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Check deployment existence
    print("Checking scheduler deployment...", flush=True)
    deployment_status = _get_scheduler_deployment_status(kubeconfig, namespace)
    result.deployment_found = deployment_status.get("found", False)
    result.deployment_name = SCHEDULER_DEPLOYMENT_NAME
    result.scheduler_diagnosis["deployment"] = deployment_status
    
    if not deployment_status.get("found"):
        # Scheduler deployment not found
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_MISSING
        result.failure_reason = "scheduler_deployment_not_found"
        result.failure_details = f"Deployment {SCHEDULER_DEPLOYMENT_NAME} not found in namespace {namespace}"
        result.scheduler_diagnosis["failure_class"] = result.failure_class
        result.scheduler_diagnosis["failure_reason"] = result.failure_reason
        result.scheduler_diagnosis["failure_details"] = result.failure_details
        
        print(f"SCHEDULER HEALTH GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Reason: {result.failure_reason}", flush=True)
        print(f"  Details: {result.failure_details}", flush=True)
        
        # Collect events before returning
        result.namespace_events = _get_namespace_events(kubeconfig, namespace)
        result.scheduler_diagnosis["namespace_events_count"] = len(result.namespace_events)
        
        # Write artifacts
        _write_result_artifact(scheduler_dir, result, kubeconfig, namespace)
        return result
    
    # Derive pod selector from deployment (canonical Kubernetes relationship)
    pod_selector = _get_scheduler_pod_selector(kubeconfig, namespace, SCHEDULER_DEPLOYMENT_NAME)
    result.scheduler_diagnosis["pod_selector"] = pod_selector
    
    # Step 2: Get pod status using derived selector
    print("Checking scheduler pods...", flush=True)
    pods_data = _get_scheduler_pods(kubeconfig, namespace, pod_selector)
    result.scheduler_pods_json = json.dumps(pods_data)
    result.pod_count = len(pods_data.get("items", []))
    result.scheduler_diagnosis["pods"] = {
        "count": result.pod_count,
        "raw": "collected",
    }
    
    # Step 3: Check crash loop FIRST (highest priority)
    crash_loop_pods = _check_crash_loop(pods_data)
    result.crash_loop_pods = crash_loop_pods
    result.scheduler_diagnosis["crash_loop_pods"] = crash_loop_pods
    
    if crash_loop_pods:
        first_crash = crash_loop_pods[0]
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_CRASH_LOOP
        result.failure_reason = "scheduler_crash_loop"
        result.failure_details = (
            f"Scheduler pod {first_crash['pod']} container {first_crash['container']} "
            f"is in {first_crash['reason']} after {first_crash['restart_count']} restarts"
        )
        result.scheduler_diagnosis["failure_class"] = result.failure_class
        result.scheduler_diagnosis["failure_reason"] = result.failure_reason
        result.scheduler_diagnosis["failure_details"] = result.failure_details
        
        print(f"SCHEDULER HEALTH GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Reason: {result.failure_reason}", flush=True)
        print(f"  Details: {result.failure_details}", flush=True)
        
        # Collect events before returning
        result.namespace_events = _get_namespace_events(kubeconfig, namespace)
        result.scheduler_diagnosis["namespace_events_count"] = len(result.namespace_events)
        
        _write_result_artifact(scheduler_dir, result, kubeconfig, namespace, pod_selector)
        return result
    
    # Step 4: Check deployment readiness
    ready_replicas = deployment_status.get("ready_replicas", 0) or 0
    available_replicas = deployment_status.get("available_replicas", 0) or 0
    spec_replicas = deployment_status.get("replicas", 1) or 1
    result.ready_replicas = ready_replicas
    result.available_replicas = available_replicas
    
    print("Scheduler deployment status:", flush=True)
    print(f"  Ready replicas: {ready_replicas}/{spec_replicas}", flush=True)
    print(f"  Available replicas: {available_replicas}/{spec_replicas}", flush=True)
    
    # Step 5: Check for other waiting pods
    result.waiting_pods = _check_waiting_pods(pods_data)
    result.scheduler_diagnosis["waiting_pods"] = result.waiting_pods
    
    # Step 6: Check for terminated pods
    result.terminated_pods = _check_terminated_pods(pods_data)
    result.scheduler_diagnosis["terminated_pods"] = result.terminated_pods
    
    # Step 7: Determine health based on ready replicas
    # Fail when deployment expects replicas but none are ready
    if spec_replicas > 0 and ready_replicas == 0:
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_NOT_READY
        # Distinguish between no pods and pods but none ready
        if result.pod_count == 0:
            result.failure_reason = "scheduler_no_pods"
            result.failure_details = (
                f"Scheduler deployment expects {spec_replicas} replica(s) but has no pods running."
            )
        else:
            result.failure_reason = "scheduler_no_ready_replicas"
            result.failure_details = (
                f"Scheduler has {result.pod_count} pod(s) but 0 ready replicas. "
                f"Check waiting/terminated containers."
            )
        result.scheduler_diagnosis["failure_class"] = result.failure_class
        result.scheduler_diagnosis["failure_reason"] = result.failure_reason
        result.scheduler_diagnosis["failure_details"] = result.failure_details
        
        print(f"SCHEDULER HEALTH GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Reason: {result.failure_reason}", flush=True)
        print(f"  Details: {result.failure_details}", flush=True)
        
        # Collect events before returning
        result.namespace_events = _get_namespace_events(kubeconfig, namespace)
        result.scheduler_diagnosis["namespace_events_count"] = len(result.namespace_events)
        
        _write_result_artifact(scheduler_dir, result, kubeconfig, namespace, pod_selector)
        return result
    
    if ready_replicas < spec_replicas:
        # Partial readiness - this could be a transient state
        # We'll consider it healthy but log a warning
        print(f"WARNING: Scheduler has partial readiness ({ready_replicas}/{spec_replicas})", flush=True)
        result.passed = True
        result.failure_class = ""
    
    # Step 8: Get namespace events
    result.namespace_events = _get_namespace_events(kubeconfig, namespace)
    result.scheduler_diagnosis["namespace_events_count"] = len(result.namespace_events)
    
    # Scheduler is healthy
    result.passed = True
    result.failure_class = ""
    print("SCHEDULER HEALTH GATE PASSED", flush=True)
    
    _write_result_artifact(scheduler_dir, result, kubeconfig, namespace, pod_selector)
    return result


def _write_result_artifact(
    scheduler_dir: Path,
    result: SchedulerHealthResult,
    kubeconfig: str,
    namespace: str,
    pod_selector: str = SCHEDULER_POD_SELECTOR,
) -> None:
    """Write result artifacts to disk.
    
    Args:
        scheduler_dir: Directory for scheduler artifacts
        result: Scheduler health result
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        pod_selector: Pod selector for log collection
    """
    # Write main result JSON
    result_path = scheduler_dir / "scheduler-health-result.json"
    result_path.write_text(json.dumps(result.to_dict(), indent=2))
    print(f"Result artifact: {result_path}", flush=True)
    
    # Write bounded summary
    summary_lines: list[str] = [
        f"Scheduler Health Gate Result: {'PASSED' if result.passed else 'FAILED'}",
        f"Failure class: {result.failure_class}",
        f"Failure reason: {result.failure_reason}",
        f"Failure details: {result.failure_details}",
        "",
        f"Deployment: {result.deployment_name}",
        f"Found: {result.deployment_found}",
        f"Pod count: {result.pod_count}",
        f"Ready replicas: {result.ready_replicas}",
        f"Available replicas: {result.available_replicas}",
        "",
        f"Crash loop pods: {len(result.crash_loop_pods)}",
    ]
    
    for crash in result.crash_loop_pods:
        summary_lines.append(
            f"  - {crash['pod']}/{crash['container']}: "
            f"{crash['reason']} (restarts={crash['restart_count']})"
        )
    
    summary_lines.extend([
        "",
        f"Waiting pods: {len(result.waiting_pods)}",
    ])
    
    for waiting in result.waiting_pods:
        summary_lines.append(
            f"  - {waiting['pod']}/{waiting['container']}: "
            f"{waiting['reason']}"
        )
    
    summary_lines.extend([
        "",
        f"Namespace events (scheduler-related): {len(result.namespace_events)}",
    ])
    
    # Write bounded summary
    summary_path = scheduler_dir / "bounded-summary.txt"
    summary_path.write_text("\n".join(summary_lines))
    print(f"Summary artifact: {summary_path}", flush=True)
    
    # Write raw pods JSON for debugging
    if result.scheduler_pods_json:
        pods_path = scheduler_dir / "scheduler-pods.json"
        pods_path.write_text(result.scheduler_pods_json)
        print(f"Pods artifact: {pods_path}", flush=True)
    
    # Collect logs once, write to both locations
    logs = _collect_scheduler_logs(kubeconfig, namespace, pod_selector)
    
    # Write to artifact directory (uploadable)
    logs_dir = scheduler_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    for pod_name, log_content in logs.items():
        (logs_dir / f"{pod_name}.log").write_text(log_content)
    print(f"Logs artifact: {logs_dir}/", flush=True)
    
    # Also write to RUNNER_TEMP as extra debug copy
    runner_temp = os.environ.get("RUNNER_TEMP", "/tmp")
    debug_dir = Path(runner_temp) / "k9b-scheduler-health-debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    for pod_name, log_content in logs.items():
        (debug_dir / f"{pod_name}.log").write_text(log_content)
    print(f"Debug logs: {debug_dir}/", flush=True)
