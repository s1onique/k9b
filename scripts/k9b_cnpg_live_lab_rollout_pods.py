#!/usr/bin/env python3
"""JSON-based pod rollout check functions for CNPG Live Lab.

This module contains pod state check functions using JSON parsing.
"""

from __future__ import annotations

import json
from typing import Any


def _check_image_pull_backoff_from_pods(pods_json: str) -> list[dict[str, Any]]:
    """Check if any pods are in ImagePullBackOff state (from JSON)."""
    try:
        data = json.loads(pods_json)
        if not isinstance(data, dict):
            return []
    except (json.JSONDecodeError, TypeError):
        return []

    items = data.get("items", [])
    affected = []

    for pod in items:
        pod_name = pod.get("metadata", {}).get("name", "")
        container_statuses = pod.get("status", {}).get("containerStatuses", [])
        for cs in container_statuses:
            state = cs.get("state", {})
            waiting = state.get("waiting", {})
            reason = waiting.get("reason", "")
            if reason in ("ImagePullBackOff", "ErrImagePull"):
                affected.append({
                    "pod": pod_name,
                    "container": cs.get("name", ""),
                    "reason": reason,
                    "message": waiting.get("message", ""),
                })

        init_container_statuses = pod.get("status", {}).get("initContainerStatuses", [])
        for cs in init_container_statuses:
            state = cs.get("state", {})
            waiting = state.get("waiting", {})
            reason = waiting.get("reason", "")
            if reason in ("ImagePullBackOff", "ErrImagePull"):
                affected.append({
                    "pod": pod_name,
                    "container": cs.get("name", ""),
                    "reason": reason,
                    "message": waiting.get("message", ""),
                })

    return affected


def _check_crash_loop_from_pods(pods_json: str) -> list[dict[str, Any]]:
    """Check if any pods are in CrashLoopBackOff state or have crashed containers (from JSON).

    Detects:
    - Containers in CrashLoopBackOff waiting state
    - Containers that terminated with non-zero exit code (container_exit_nonzero)
    - Containers with Error waiting reason
    - Containers with restartCount > 0 and terminated exit code != 0

    This check has HIGHER precedence than readiness_probe_failed per contract:
    - image_pull_error
    - pod_crash_loop / container_exit_nonzero  <-- this check
    - oom_killed
    - readiness_probe_failed
    """
    try:
        data = json.loads(pods_json)
        if not isinstance(data, dict):
            return []
    except (json.JSONDecodeError, TypeError):
        return []

    items = data.get("items", [])
    affected = []

    for pod in items:
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

            # Check for CrashLoopBackOff waiting state
            if waiting_reason == "CrashLoopBackOff":
                affected.append({
                    "pod": pod_name,
                    "container": container_name,
                    "reason": waiting_reason,
                    "restart_count": restart_count,
                    "message": waiting.get("message", ""),
                    "phase": phase,
                })
                continue

            # Check for Error waiting state (container exited immediately)
            if waiting_reason == "Error":
                affected.append({
                    "pod": pod_name,
                    "container": container_name,
                    "reason": waiting_reason,
                    "restart_count": restart_count,
                    "message": waiting.get("message", ""),
                    "phase": phase,
                })
                continue

            # Check for terminated containers with non-zero exit code
            # This captures evidence of container crashes even if not in CrashLoopBackOff
            if terminated:
                exit_code = terminated.get("exitCode", 0)
                reason = terminated.get("reason", "")
                # Non-zero exit with Error/Completed/empty reason indicates crash
                if exit_code != 0 and reason in ("Error", "Completed", ""):
                    affected.append({
                        "pod": pod_name,
                        "container": container_name,
                        "reason": f"exit_code_{exit_code}",
                        "exit_code": exit_code,
                        "restart_count": restart_count,
                        "started_at": terminated.get("startedAt", ""),
                        "finished_at": terminated.get("finishedAt", ""),
                        "phase": phase,
                    })
                    continue

            # Check lastState.terminated for restart evidence
            if last_terminated:
                exit_code = last_terminated.get("exitCode", 0)
                reason = last_terminated.get("reason", "")
                # If previous termination was non-zero, this is crash evidence
                if exit_code != 0 and reason in ("Error", "Completed", ""):
                    affected.append({
                        "pod": pod_name,
                        "container": container_name,
                        "reason": f"previous_exit_code_{exit_code}",
                        "exit_code": exit_code,
                        "restart_count": restart_count,
                        "previous_started_at": last_terminated.get("startedAt", ""),
                        "previous_finished_at": last_terminated.get("finishedAt", ""),
                        "phase": phase,
                    })
                    continue

        # Check init containers with same logic
        init_container_statuses = pod.get("status", {}).get("initContainerStatuses", [])
        for cs in init_container_statuses:
            container_name = cs.get("name", "")
            restart_count = cs.get("restartCount", 0)
            state = cs.get("state", {})
            waiting = state.get("waiting", {})
            waiting_reason = waiting.get("reason", "")
            terminated = state.get("terminated", {})
            last_state = cs.get("lastState", {})
            last_terminated = last_state.get("terminated", {})

            # Check for CrashLoopBackOff waiting state
            if waiting_reason == "CrashLoopBackOff":
                affected.append({
                    "pod": pod_name,
                    "container": container_name,
                    "reason": waiting_reason,
                    "restart_count": restart_count,
                    "message": waiting.get("message", ""),
                    "phase": phase,
                })
                continue

            # Check for Error waiting state (init container exited immediately)
            if waiting_reason == "Error":
                affected.append({
                    "pod": pod_name,
                    "container": container_name,
                    "reason": waiting_reason,
                    "restart_count": restart_count,
                    "message": waiting.get("message", ""),
                    "phase": phase,
                })
                continue

            # Check for terminated init containers with non-zero exit code
            if terminated:
                exit_code = terminated.get("exitCode", 0)
                reason = terminated.get("reason", "")
                if exit_code != 0 and reason in ("Error", "Completed", ""):
                    affected.append({
                        "pod": pod_name,
                        "container": container_name,
                        "reason": f"exit_code_{exit_code}",
                        "exit_code": exit_code,
                        "restart_count": restart_count,
                        "started_at": terminated.get("startedAt", ""),
                        "finished_at": terminated.get("finishedAt", ""),
                        "phase": phase,
                    })
                    continue

    return affected


def _check_failed_scheduling_from_pods(pods_json: str) -> list[dict[str, Any]]:
    """Check if any pods have failed scheduling from pod status (from JSON)."""
    try:
        data = json.loads(pods_json)
        if not isinstance(data, dict):
            return []
    except (json.JSONDecodeError, TypeError):
        return []

    items = data.get("items", [])
    affected = []

    for pod in items:
        pod_name = pod.get("metadata", {}).get("name", "")
        phase = pod.get("status", {}).get("phase", "")

        if phase == "Pending":
            conditions = pod.get("status", {}).get("conditions", [])
            for cond in conditions:
                if cond.get("type") == "PodScheduled" and cond.get("status") == "False":
                    affected.append({
                        "pod": pod_name,
                        "reason": cond.get("reason", ""),
                        "message": cond.get("message", ""),
                    })

    return affected


def _check_readiness_probe_failed_from_pods(pods_json: str) -> list[dict[str, Any]]:
    """Check if readiness probes have failed (from JSON).

    Detects:
    - Pod status conditions Ready/ContainersReady with status=False
    - ContainersNotReady waiting reason (container not ready)

    NOTE: Container exit codes are handled by _check_crash_loop_from_pods which
    has higher precedence. This function only detects TRUE readiness probe
    failures (not container crashes).

    Failure precedence contract:
    - image_pull_error
    - pod_crash_loop / container_exit_nonzero  (handled by crash_loop check)
    - oom_killed
    - readiness_probe_failed  <-- this check (only detects probe issues)
    """
    try:
        data = json.loads(pods_json)
        if not isinstance(data, dict):
            return []
    except (json.JSONDecodeError, TypeError):
        return []

    items = data.get("items", [])
    affected = []

    for pod in items:
        pod_name = pod.get("metadata", {}).get("name", "")

        # Check Pod status conditions (canonical Kubernetes readiness check)
        conditions = pod.get("status", {}).get("conditions", [])
        for cond in conditions:
            cond_type = cond.get("type", "")
            cond_status = cond.get("status", "")
            if cond_type in ("Ready", "ContainersReady") and cond_status == "False":
                affected.append({
                    "pod": pod_name,
                    "condition_type": cond_type,
                    "reason": cond.get("reason", "ContainersNotReady"),
                    "message": cond.get("message", ""),
                })

        container_statuses = pod.get("status", {}).get("containerStatuses", [])
        for cs in container_statuses:
            state = cs.get("state", {})
            waiting = state.get("waiting", {})
            waiting_reason = waiting.get("reason", "")

            # Check for ContainersNotReady waiting reason
            # This indicates readiness probe failed (container started but not ready)
            if waiting_reason == "ContainersNotReady":
                affected.append({
                    "pod": pod_name,
                    "container": cs.get("name", ""),
                    "reason": waiting_reason,
                    "message": waiting.get("message", ""),
                })

    return affected
