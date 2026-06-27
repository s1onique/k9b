"""Collection functions for incident discovery gate.

Provides kubectl-based collection for fixture verification, candidate detection,
and diagnostic snapshots.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any


def get_pod_status(
    kubeconfig: str,
    namespace: str,
    pod_name: str,
) -> dict[str, Any]:
    """Get pod status with full details.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        pod_name: Name of the pod

    Returns:
        Pod status dictionary with phase, conditions, containers
    """
    cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig,
        "get", "pod", pod_name,
        "-n", namespace,
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
            return {"found": False, "error": result.stderr.strip()}

        data = json.loads(result.stdout)
        return {
            "found": True,
            "name": data.get("metadata", {}).get("name", ""),
            "namespace": data.get("metadata", {}).get("namespace", ""),
            "phase": data.get("status", {}).get("phase", ""),
            "conditions": data.get("status", {}).get("conditions", []),
            "container_statuses": data.get("status", {}).get("containerStatuses", []),
            "pod_ip": data.get("status", {}).get("podIP", ""),
            "host_ip": data.get("status", {}).get("hostIP", ""),
            "start_time": data.get("status", {}).get("startTime", ""),
        }
    except subprocess.TimeoutExpired:
        return {"found": False, "error": "timeout"}
    except json.JSONDecodeError:
        return {"found": False, "error": "invalid_json"}
    except Exception as e:
        return {"found": False, "error": str(e)}


def list_pods_in_namespace(
    kubeconfig: str,
    namespace: str,
    label_selector: str | None = None,
) -> dict[str, Any]:
    """List all pods in namespace with optional label selector.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        label_selector: Optional label selector

    Returns:
        List of pods with status summary
    """
    cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig,
        "get", "pods",
        "-n", namespace,
        "-o", "json",
    ]

    if label_selector:
        cmd.extend(["-l", label_selector])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {"items": [], "error": result.stderr.strip()}

        data = json.loads(result.stdout)
        items = data.get("items", [])

        # Extract summary for each pod
        summaries = []
        for pod in items:
            name = pod.get("metadata", {}).get("name", "")
            phase = pod.get("status", {}).get("phase", "")
            container_statuses = pod.get("status", {}).get("containerStatuses", [])

            # Check for failure indicators
            not_ready = any(
                cs.get("ready", False) is False
                for cs in container_statuses
            )
            waiting = any(
                cs.get("state", {}).get("waiting") is not None
                for cs in container_statuses
            )
            terminated = any(
                cs.get("state", {}).get("terminated") is not None
                for cs in container_statuses
            )

            summaries.append({
                "name": name,
                "phase": phase,
                "not_ready": not_ready,
                "waiting": waiting,
                "terminated": terminated,
                "container_count": len(container_statuses),
                "ready_containers": sum(1 for cs in container_statuses if cs.get("ready", False)),
            })

        return {"items": summaries, "total": len(summaries)}

    except subprocess.TimeoutExpired:
        return {"items": [], "error": "timeout"}
    except json.JSONDecodeError:
        return {"items": [], "error": "invalid_json"}
    except Exception as e:
        return {"items": [], "error": str(e)}


def get_namespace_events(
    kubeconfig: str,
    namespace: str,
    max_events: int = 50,
) -> list[dict[str, Any]]:
    """Get recent events from namespace.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        max_events: Maximum number of events to return

    Returns:
        List of recent events
    """
    cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig,
        "get", "events",
        "-n", namespace,
        "--sort-by=", ".lastTimestamp",
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
            return []

        data = json.loads(result.stdout)
        items = data.get("items", [])

        # Return last max_events
        events = []
        for item in items[-max_events:]:
            events.append({
                "type": item.get("type", ""),
                "reason": item.get("reason", ""),
                "message": item.get("message", ""),
                "involved_object": item.get("involvedObject", {}).get("name", ""),
                "last_timestamp": item.get("lastTimestamp", ""),
                "count": item.get("count", 1),
            })

        return events

    except Exception:
        return []


def call_backend_incidents_api(
    kubeconfig: str,
    namespace: str,
    backend_deployment: str,
    backend_container: str,
    backend_port: int,
    timeout: int = 30,
    backend_pod_name: str | None = None,
) -> tuple[str, int]:
    """Call backend /api/incidents endpoint via kubectl exec.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        backend_deployment: Backend deployment name
        backend_container: Backend container name
        backend_port: Backend port
        timeout: Request timeout in seconds
        backend_pod_name: Optional explicit pod name for process-local state consistency.
            When provided, targets the specific pod; otherwise uses deployment (may hit any pod).

    Returns:
        Tuple of (response_body, http_status_code)
    """
    # Use explicit pod name if provided for process-local IncidentStore consistency
    if backend_pod_name:
        target = f"pod/{backend_pod_name}"
    else:
        target = f"deploy/{backend_deployment}"

    cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig,
        "exec", "-n", namespace,
        target,
        "-c", backend_container,
        "--",
        "curl", "-sS",
        f"http://localhost:{backend_port}/api/incidents",
        "-H", "Content-Type: application/json",
        "-w", "\\n%{http_code}",
        "--max-time", str(timeout),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 10,
        )

        output = result.stdout.strip()
        if not output:
            return '{"incidents":[]}', 0

        # Parse HTTP status from last line
        lines = output.split("\n")
        http_code_line = lines[-1]
        try:
            http_code = int(http_code_line)
        except ValueError:
            http_code = 0

        # Body is everything except last line
        body = "\n".join(lines[:-1]) if len(lines) > 1 else ""

        return body, http_code

    except subprocess.TimeoutExpired:
        return '{"incidents":[]}', 0
    except Exception:
        return '{"incidents":[]}', 0


def get_deployment_status(
    kubeconfig: str,
    namespace: str,
    deployment_name: str,
) -> dict[str, Any]:
    """Get deployment status.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        deployment_name: Deployment name

    Returns:
        Deployment status with ready replicas info
    """
    cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig,
        "get", "deployment", deployment_name,
        "-n", namespace,
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
            return {"found": False, "error": result.stderr.strip()}

        data = json.loads(result.stdout)
        status = data.get("status", {})

        return {
            "found": True,
            "name": deployment_name,
            "replicas": status.get("replicas", 0),
            "ready_replicas": status.get("readyReplicas", 0),
            "available_replicas": status.get("availableReplicas", 0),
            "unavailable_replicas": status.get("unavailableReplicas", 0),
        }

    except Exception as e:
        return {"found": False, "error": str(e)}


def collect_backend_logs(
    kubeconfig: str,
    namespace: str,
    backend_deployment: str,
    backend_container: str,
    tail_lines: int = 100,
) -> str:
    """Collect backend logs.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        backend_deployment: Backend deployment name
        backend_container: Backend container name
        tail_lines: Number of lines to tail

    Returns:
        Backend logs (last tail_lines lines)
    """
    cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig,
        "logs",
        "-n", namespace,
        f"deploy/{backend_deployment}",
        "-c", backend_container,
        f"--tail={tail_lines}",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout if result.returncode == 0 else ""

    except Exception:
        return ""


def collect_scheduler_logs(
    kubeconfig: str,
    namespace: str,
    tail_lines: int = 100,
) -> str:
    """Collect scheduler logs.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        tail_lines: Number of lines to tail

    Returns:
        Scheduler logs (last tail_lines lines)
    """
    # Get scheduler pods
    pod_cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig,
        "get", "pods",
        "-n", namespace,
        "-l", "app.kubernetes.io/name=k9b-scheduler",
        "-o", "json",
    ]

    try:
        result = subprocess.run(
            pod_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return ""

        data = json.loads(result.stdout)
        items = data.get("items", [])
        if not items:
            return ""

        # Get logs from first scheduler pod
        pod_name = items[0].get("metadata", {}).get("name", "")
        log_cmd = [
            "kubectl",
            "--kubeconfig", kubeconfig,
            "logs",
            "-n", namespace,
            f"pod/{pod_name}",
            f"--tail={tail_lines}",
        ]

        log_result = subprocess.run(
            log_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return log_result.stdout if log_result.returncode == 0 else ""

    except Exception:
        return ""


def get_backend_pod_info(
    kubeconfig: str,
    namespace: str,
    backend_deployment: str,
) -> dict[str, Any]:
    """Get backend pod name and identity info.

    This function selects a single backend pod and returns its identity
    for consistency checks. Since IncidentStore is process-local, all
    API calls in Phase 2c must go to the same pod.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        backend_deployment: Backend deployment name

    Returns:
        Dict with pod_name, namespace, pod_ip, node_name, and uid
    """
    cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig,
        "get", "pods",
        "-n", namespace,
        "-l", f"app={backend_deployment}",
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
            return {"found": False, "error": result.stderr.strip()}

        data = json.loads(result.stdout)
        items = data.get("items", [])

        # Filter to running pods only
        running_pods = [
            pod for pod in items
            if pod.get("status", {}).get("phase") == "Running"
        ]

        if not running_pods:
            return {"found": False, "error": "No running backend pods"}

        # Sort by creation timestamp to get the oldest (most stable) pod first
        sorted_pods = sorted(
            running_pods,
            key=lambda p: p.get("metadata", {}).get("creationTimestamp", ""),
        )
        pod = sorted_pods[0]

        return {
            "found": True,
            "pod_name": pod.get("metadata", {}).get("name", ""),
            "namespace": namespace,
            "pod_ip": pod.get("status", {}).get("podIP", ""),
            "node_name": pod.get("spec", {}).get("nodeName", ""),
            "uid": pod.get("metadata", {}).get("uid", ""),
            "creation_timestamp": pod.get("metadata", {}).get("creationTimestamp", ""),
            "total_running_pods": len(running_pods),
        }

    except subprocess.TimeoutExpired:
        return {"found": False, "error": "timeout"}
    except json.JSONDecodeError:
        return {"found": False, "error": "invalid_json"}
    except Exception as e:
        return {"found": False, "error": str(e)}


def call_backend_snapshot_api(
    kubeconfig: str,
    namespace: str,
    backend_deployment: str,
    backend_container: str,
    backend_port: int,
    snapshot_namespace: str,
    timeout: int = 60,
    backend_pod_name: str | None = None,
) -> tuple[dict[str, Any], int, str]:
    """Call backend POST /api/incidents/snapshot to trigger snapshot capture.

    This endpoint captures a snapshot bundle for the namespace, parses it,
    generates incident candidates, and promotes them to the in-memory IncidentStore.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        backend_deployment: Backend deployment name
        backend_container: Backend container name
        backend_port: Backend port
        snapshot_namespace: Namespace to capture snapshot for
        timeout: Request timeout in seconds
        backend_pod_name: Explicit backend pod name for process-local consistency.
            If provided, uses this pod directly. Otherwise selects one via get_backend_pod_info().

    Returns:
        Tuple of (response_dict, http_status_code, actual_pod_name)
    """
    # Use provided pod name or select one
    if backend_pod_name:
        pod_name = backend_pod_name
    else:
        pod_info = get_backend_pod_info(kubeconfig, namespace, backend_deployment)
        if not pod_info.get("found"):
            return {"error": f"Could not find backend pod: {pod_info.get('error', 'unknown')}"}, 0, ""
        pod_name = pod_info["pod_name"]

    # Build the request body
    request_body = json.dumps({
        "namespace": snapshot_namespace,
        "since_hours": 2,
    })

    # Build curl command
    cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig,
        "exec", "-n", namespace,
        f"pod/{pod_name}",
        "-c", backend_container,
        "--",
        "curl", "-sS",
        "-X", "POST",
        f"http://localhost:{backend_port}/api/incidents/snapshot",
        "-H", "Content-Type: application/json",
        "-d", request_body,
        "-w", "\\n%{http_code}",
        "--max-time", str(timeout),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 10,
        )

        output = result.stdout.strip()
        if not output:
            return {"error": "Empty response"}, 0, pod_name

        # Parse HTTP status from last line
        lines = output.split("\n")
        http_code_line = lines[-1]
        try:
            http_code = int(http_code_line)
        except ValueError:
            http_code = 0

        # Body is everything except last line
        body = "\n".join(lines[:-1]) if len(lines) > 1 else ""

        try:
            response_dict = json.loads(body)
            return response_dict, http_code, pod_name
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response", "raw": body[:500]}, http_code, pod_name

    except subprocess.TimeoutExpired:
        return {"error": "Request timeout"}, 0, pod_name
    except Exception as e:
        return {"error": str(e)}, 0, pod_name
