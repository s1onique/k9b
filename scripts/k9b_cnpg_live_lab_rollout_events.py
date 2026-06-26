#!/usr/bin/env python3
"""Event-based rollout check functions for CNPG Live Lab.

This module contains event-based check functions for detecting rollout issues.
"""

from __future__ import annotations

import json


def _is_transient_volume_binding_conflict(reason: str, message: str) -> bool:
    """Detect transient VolumeBinding PreBind conflict that should be retried.

    This catches the scheduler PreBind race condition where the PVC object changes
    while the scheduler tries to bind or reserve volume state. Kubernetes should
    retry this automatically, so we treat it as nonfatal.

    Args:
        reason: Event reason (e.g., "FailedScheduling")
        message: Event message containing the error details

    Returns:
        True if this is a transient VolumeBinding PreBind conflict, False otherwise
    """
    msg_lower = message.lower()
    return (
        reason == "FailedScheduling"
        and "prebind plugin" in msg_lower
        and "volumebinding" in msg_lower
        and "object has been modified" in msg_lower
        and ("please apply your changes" in msg_lower or "to the latest version" in msg_lower)
    )


def _check_failed_scheduling_from_events(events_json: str) -> tuple[bool, str, str]:
    """Check if events indicate failed scheduling (non-transient).

    Args:
        events_json: JSON string of events list

    Returns:
        Tuple of (is_fatal, reason, message)
    """
    if not events_json:
        return False, "", ""

    try:
        data = json.loads(events_json)
        for event in data.get("items", []):
            reason = event.get("reason", "")
            msg = event.get("message", "") or ""
            involved = event.get("involvedObject", {})
            pod_name = involved.get("name", "")

            # Check if this is a transient VolumeBinding PreBind race
            if _is_transient_volume_binding_conflict(reason, msg):
                # Return nonfatal but still include pod name in message for diagnostics
                prefixed_msg = f"{pod_name}: {msg}" if pod_name else msg
                return False, "", prefixed_msg

            # Look for scheduling failures
            if reason in ("FailedScheduling", "InsufficientMemory", "InsufficientCPU",
                          "InsufficientDisk", "InsufficientPods", "NodeAffinity",
                          "TaintToleration", "PodToleration", "Unschedulable"):
                # Fatal scheduling failure
                if pod_name:
                    msg = f"{pod_name}: {msg}"
                return True, reason, msg

    except (json.JSONDecodeError, TypeError):
        pass

    return False, "", ""


def _check_readiness_probe_failed_from_events(events_json: str) -> tuple[bool, str, str]:
    """Check if events indicate readiness/liveness probe failures.

    Args:
        events_json: JSON string of events list

    Returns:
        Tuple of (is_fatal, reason, message)
    """
    if not events_json:
        return False, "", ""

    try:
        data = json.loads(events_json)
        for event in data.get("items", []):
            reason = event.get("reason", "")
            msg = event.get("message", "") or ""

            # Look for readiness/liveness probe failures
            if reason in ("Unhealthy", "ReadinessProbeFailed", "LivenessProbeFailed"):
                # Must have readiness/liveness context
                msg_lower = msg.lower()
                if any(term in msg_lower for term in ["readiness", "liveness", "probe", "health"]):
                    involved = event.get("involvedObject", {})
                    pod_name = involved.get("name", "")
                    if pod_name:
                        msg = f"{pod_name}: {msg}"
                    return True, reason, msg

    except (json.JSONDecodeError, TypeError):
        pass

    return False, "", ""


def _detect_transient_volume_binding_conflict(events_json: str) -> tuple[bool, str, str]:
    """Scan events JSON for transient VolumeBinding PreBind conflict.

    Returns: (has_transient, message, pod_name)
    """
    if not events_json:
        return False, "", ""

    try:
        data = json.loads(events_json)
        for event in data.get("items", []):
            if event.get("reason") == "FailedScheduling":
                msg = event.get("message", "") or ""
                if _is_transient_volume_binding_conflict("FailedScheduling", msg):
                    involved = event.get("involvedObject", {})
                    obj_name = involved.get("name", "unknown")
                    return True, msg, obj_name
    except (json.JSONDecodeError, TypeError):
        pass

    return False, "", ""
