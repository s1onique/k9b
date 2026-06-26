#!/usr/bin/env python3
"""Deployment and PVC JSON check functions for CNPG Live Lab.

This module contains deployment and PVC state check functions using JSON parsing.
"""

from __future__ import annotations

import json
from typing import Any


def _check_pvc_pending_from_json(pvc_json: str) -> list[dict[str, Any]]:
    """Check if any PVCs are stuck in Pending state (from JSON)."""
    try:
        data = json.loads(pvc_json)
        if not isinstance(data, dict):
            return []
    except (json.JSONDecodeError, TypeError):
        return []

    items = data.get("items", [])
    affected = []

    for pvc in items:
        phase = pvc.get("status", {}).get("phase", "")
        if phase == "Pending":
            affected.append({
                "pvc": pvc.get("metadata", {}).get("name", ""),
                "storage_class": pvc.get("spec", {}).get("storageClassName", ""),
                "access_modes": pvc.get("spec", {}).get("accessModes", []),
            })

    return affected


def _check_deployment_replica_failure_from_json(deployments_json: str) -> list[dict[str, Any]]:
    """Check if any deployment replicas have failed (from JSON)."""
    try:
        data = json.loads(deployments_json)
        if not isinstance(data, dict):
            return []
    except (json.JSONDecodeError, TypeError):
        return []

    items = data.get("items", [])
    affected = []

    for deploy in items:
        deploy_name = deploy.get("metadata", {}).get("name", "")
        status = deploy.get("status", {})
        replicas = status.get("replicas", 0)
        available = status.get("availableReplicas", 0)

        if replicas > 0 and available == 0:
            affected.append({
                "deployment": deploy_name,
                "replicas": replicas,
                "available": available,
            })

    return affected


def _check_deployment_progress_deadline_from_json(deployments_json: str) -> list[dict[str, Any]]:
    """Check if any deployment has exceeded progress deadline (from JSON)."""
    try:
        data = json.loads(deployments_json)
        if not isinstance(data, dict):
            return []
    except (json.JSONDecodeError, TypeError):
        return []

    items = data.get("items", [])
    affected = []

    for deploy in items:
        deploy_name = deploy.get("metadata", {}).get("name", "")
        status = deploy.get("status", {})
        conditions = status.get("conditions", [])

        for cond in conditions:
            if cond.get("type") == "Progressing" and cond.get("status") == "Unknown":
                reason = cond.get("reason", "")
                if reason == "ProgressDeadlineExceeded":
                    affected.append({
                        "deployment": deploy_name,
                        "reason": reason,
                        "message": cond.get("message", ""),
                    })

    return affected


def _check_rollout_success_from_json(pods_json: str, deployments_json: str, pvc_json: str) -> bool:
    """Check if rollout succeeded from JSON (all replicas ready)."""
    try:
        deploys_data = json.loads(deployments_json)
        for deploy in deploys_data.get("items", []):
            status = deploy.get("status", {})
            available = status.get("availableReplicas", 0)
            replicas = status.get("replicas", 0)
            if replicas > 0 and available < 1:
                return False
        return True
    except (json.JSONDecodeError, TypeError):
        return False
