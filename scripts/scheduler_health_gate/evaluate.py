"""Evaluation module for scheduler health gate.

This module contains pure health decision logic functions that evaluate
scheduler state and return structured results.
"""

from __future__ import annotations

from typing import Any

from .contracts import (
    FAILURE_SCHEDULER_CRASH_LOOP,
    FAILURE_SCHEDULER_MISSING,
    FAILURE_SCHEDULER_NOT_READY,
    SCHEDULER_DEPLOYMENT_NAME,
)

# =============================================================================
# Pod state evaluation
# =============================================================================


def check_crash_loop(pods_data: dict[str, Any]) -> list[dict[str, Any]]:
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
            
            # Extract lastState.terminated details for evidence capture
            last_exit_code = last_terminated.get("exitCode", 0) if last_terminated else None
            last_exit_reason = last_terminated.get("reason", "") if last_terminated else ""
            last_exit_message = last_terminated.get("message", "") if last_terminated else ""
            
            # Check CrashLoopBackOff
            if waiting_reason == "CrashLoopBackOff":
                crash_loop_pods.append({
                    "pod": pod_name,
                    "container": container_name,
                    "reason": waiting_reason,
                    "restart_count": restart_count,
                    "message": waiting.get("message", ""),
                    "phase": phase,
                    # Include previous termination details for crash loop evidence
                    "last_exit_code": last_exit_code,
                    "last_exit_reason": last_exit_reason,
                    "last_exit_message": last_exit_message,
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
                    # Include previous termination details for crash loop evidence
                    "last_exit_code": last_exit_code,
                    "last_exit_reason": last_exit_reason,
                    "last_exit_message": last_exit_message,
                })
            
            # Check terminated with non-zero exit
            elif terminated:
                exit_code = terminated.get("exitCode", 0)
                exit_reason = terminated.get("reason", "")
                exit_message = terminated.get("message", "")
                if exit_code != 0 and exit_reason in ("Error", "Completed", ""):
                    crash_loop_pods.append({
                        "pod": pod_name,
                        "container": container_name,
                        "reason": f"exit_code_{exit_code}",
                        "exit_code": exit_code,
                        "exit_reason": exit_reason,
                        "exit_message": exit_message,
                        "restart_count": restart_count,
                        "phase": phase,
                    })
            
            # Check lastState.terminated
            elif last_terminated:
                exit_code = last_terminated.get("exitCode", 0)
                exit_reason = last_terminated.get("reason", "")
                exit_message = last_terminated.get("message", "")
                if exit_code != 0 and exit_reason in ("Error", "Completed", ""):
                    crash_loop_pods.append({
                        "pod": pod_name,
                        "container": container_name,
                        "reason": f"previous_exit_code_{exit_code}",
                        "exit_code": exit_code,
                        "exit_reason": exit_reason,
                        "exit_message": exit_message,
                        "restart_count": restart_count,
                        "phase": phase,
                    })
    
    return crash_loop_pods


def check_waiting_pods(pods_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Check for pods in waiting state (excluding CrashLoopBackOff and Error)."""
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


def check_terminated_pods(pods_data: dict[str, Any]) -> list[dict[str, Any]]:
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


# =============================================================================
# Health evaluation
# =============================================================================


def evaluate_scheduler_health(
    deployment_status: dict[str, Any],
    pods_data: dict[str, Any],
) -> tuple[bool, str, str, str]:
    """Evaluate scheduler health from deployment and pod status.
    
    Returns:
        tuple of (passed, failure_class, failure_reason, failure_details)
    """
    # Check for missing deployment
    if not deployment_status.get("found"):
        return (
            False,
            FAILURE_SCHEDULER_MISSING,
            "scheduler_deployment_not_found",
            f"Deployment {SCHEDULER_DEPLOYMENT_NAME} not found",
        )
    
    # Check crash loop first
    crash_loop_pods = check_crash_loop(pods_data)
    if crash_loop_pods:
        first_crash = crash_loop_pods[0]
        return (
            False,
            FAILURE_SCHEDULER_CRASH_LOOP,
            "scheduler_crash_loop",
            f"Scheduler pod {first_crash['pod']} container {first_crash['container']} "
            f"is in {first_crash['reason']} after {first_crash['restart_count']} restarts",
        )
    
    # Check readiness
    ready_replicas = deployment_status.get("ready_replicas", 0) or 0
    spec_replicas = deployment_status.get("replicas", 1) or 1
    pod_count = len(pods_data.get("items", []))
    
    if spec_replicas > 0 and ready_replicas == 0:
        if pod_count == 0:
            return (
                False,
                FAILURE_SCHEDULER_NOT_READY,
                "scheduler_no_pods",
                f"Scheduler deployment expects {spec_replicas} replica(s) but has no pods running.",
            )
        else:
            return (
                False,
                FAILURE_SCHEDULER_NOT_READY,
                "scheduler_no_ready_replicas",
                f"Scheduler has {pod_count} pod(s) but 0 ready replicas. "
                f"Check waiting/terminated containers.",
            )
    
    # Scheduler is healthy
    return (True, "", "", "")
