#!/usr/bin/env python3
"""JSON parsing helpers for CNPG Live Lab bootstrap.

This module contains pure JSON parsing functions for classifying
Helm wait timeout failures from kubectl JSON output.
"""

from __future__ import annotations


def _parse_crash_loop_from_pods(pods_json_str: str) -> bool:
    """Parse pod JSON and detect actual CrashLoopBackOff state."""
    import json

    try:
        pods_data = json.loads(pods_json_str)
        if not isinstance(pods_data, dict):
            return False

        items = pods_data.get("items", [])
        for pod in items:
            container_statuses = pod.get("status", {}).get("containerStatuses", [])
            for cs in container_statuses:
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                reason = waiting.get("reason", "")
                if reason == "CrashLoopBackOff":
                    return True

            init_container_statuses = pod.get("status", {}).get("initContainerStatuses", [])
            for cs in init_container_statuses:
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                reason = waiting.get("reason", "")
                if reason == "CrashLoopBackOff":
                    return True

        return False
    except (json.JSONDecodeError, TypeError):
        return False


def _parse_image_pull_failure_from_pods(pods_json_str: str) -> bool:
    """Parse pod JSON and detect image pull failures."""
    import json

    try:
        pods_data = json.loads(pods_json_str)
        if not isinstance(pods_data, dict):
            return False

        items = pods_data.get("items", [])
        for pod in items:
            container_statuses = pod.get("status", {}).get("containerStatuses", [])
            for cs in container_statuses:
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                reason = waiting.get("reason", "")
                if reason in ("ImagePullBackOff", "ErrImagePull"):
                    return True

            init_container_statuses = pod.get("status", {}).get("initContainerStatuses", [])
            for cs in init_container_statuses:
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                reason = waiting.get("reason", "")
                if reason in ("ImagePullBackOff", "ErrImagePull"):
                    return True

        return False
    except (json.JSONDecodeError, TypeError):
        return False


def _parse_probe_failure_from_pods(pods_json_str: str) -> bool:
    """Parse pod JSON and detect readiness/liveness probe failures."""
    import json

    try:
        pods_data = json.loads(pods_json_str)
        if not isinstance(pods_data, dict):
            return False

        items = pods_data.get("items", [])
        for pod in items:
            container_statuses = pod.get("status", {}).get("containerStatuses", [])
            for cs in container_statuses:
                last_state = cs.get("lastState", {})
                terminated = last_state.get("terminated", {})
                exit_code = terminated.get("exitCode", 0)
                reason = terminated.get("reason", "")
                if exit_code != 0 and reason in ("Error", "Completed", ""):
                    return True

        return False
    except (json.JSONDecodeError, TypeError):
        return False


def _parse_deployment_not_ready_from_deployments(deployments_json_str: str) -> bool:
    """Parse deployment JSON and detect unavailable replicas."""
    import json

    try:
        data = json.loads(deployments_json_str)
        if not isinstance(data, dict):
            return False

        items = data.get("items", [])
        for deploy in items:
            status = deploy.get("status", {})
            replicas = status.get("replicas", 0)
            available = status.get("availableReplicas", 0)
            if replicas > 0 and available == 0:
                return True

        return False
    except (json.JSONDecodeError, TypeError):
        return False


def _parse_pvc_pending_from_pods(pods_json_str: str, events_str: str) -> bool:
    """Parse pod and event JSON to detect PVC pending state."""
    import json

    try:
        pods_data = json.loads(pods_json_str)
        if not isinstance(pods_data, dict):
            return False

        items = pods_data.get("items", [])
        for pod in items:
            phase = pod.get("status", {}).get("phase", "")
            if phase == "Pending":
                conditions = pod.get("status", {}).get("conditions", [])
                for cond in conditions:
                    reason = cond.get("reason", "")
                    if "pvc" in reason.lower() or "volume" in reason.lower():
                        return True

        events_lower = events_str.lower()
        if ("pending" in events_lower and "pvc" in events_lower) or \
           ("waiting" in events_lower and "volume" in events_lower):
            return True

        return False
    except (json.JSONDecodeError, TypeError):
        return False
