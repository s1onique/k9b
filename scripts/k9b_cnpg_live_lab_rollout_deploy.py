#!/usr/bin/env python3
"""Deployment and PVC JSON check functions for CNPG Live Lab.

This module contains deployment and PVC state check functions using JSON parsing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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


@dataclass
class DeploymentRolloutState:
    """Detailed rollout state for a single deployment."""

    name: str
    namespace: str
    desired_replicas: int
    updated_replicas: int
    available_replicas: int
    total_replicas: int
    observed_generation: int | None
    generation: int | None
    old_replicas: int
    unavailable_replicas: int | None
    complete: bool
    blocked_reason: str


def _check_deployment_complete_from_json(deployments_json: str) -> tuple[bool, list[DeploymentRolloutState], str]:
    """Check if all deployments have completed rollout from JSON.

    A deployment is rollout-complete only when ALL of the following are true:
    - observedGeneration >= metadata.generation (controller has processed the update)
    - updatedReplicas >= desired_replicas (all replicas are running the new version)
    - availableReplicas >= desired_replicas (all replicas are available)
    - No old replicas remain (old replicas = max(total_replicas - updated_replicas, 0) == 0)
    - unavailableReplicas == 0 (when present)

    Args:
        deployments_json: JSON string of deployments list

    Returns:
        Tuple of (all_complete, list of deployment states, summary message)
    """
    try:
        data = json.loads(deployments_json)
        if not isinstance(data, dict):
            return False, [], "Failed to parse deployments JSON"
    except (json.JSONDecodeError, TypeError):
        return False, [], "Failed to parse deployments JSON"

    items = data.get("items", [])
    states: list[DeploymentRolloutState] = []
    incomplete: list[str] = []

    for deploy in items:
        metadata = deploy.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "")
        generation = metadata.get("generation")

        spec = deploy.get("spec", {})
        # desired_replicas defaults to 1 if not specified (K8s Deployment default)
        desired_replicas = spec.get("replicas", 1)

        status = deploy.get("status", {})
        # Handle missing fields conservatively: absence means 0
        updated_replicas = status.get("updatedReplicas", 0)
        available_replicas = status.get("availableReplicas", 0)
        total_replicas = status.get("replicas", 0)
        observed_generation = status.get("observedGeneration")
        unavailable_replicas = status.get("unavailableReplicas")

        # Compute old replicas (replicas from previous version)
        old_replicas = max(total_replicas - updated_replicas, 0)

        # Check each completion criterion
        blocked_reason = ""
        complete = True

        # 1. observedGeneration must be >= generation when generation is present
        if generation is not None and observed_generation is not None:
            if observed_generation < generation:
                blocked_reason = f"observedGeneration={observed_generation} < generation={generation}"
                complete = False
        elif generation is not None and observed_generation is None:
            # observedGeneration absent means controller hasn't processed - not complete
            blocked_reason = f"observedGeneration missing (generation={generation} present)"
            complete = False

        # 2. updatedReplicas must be >= desired_replicas
        if complete and updated_replicas < desired_replicas:
            blocked_reason = f"updatedReplicas={updated_replicas} < desired={desired_replicas}"
            complete = False

        # 3. availableReplicas must be >= desired_replicas
        if complete and available_replicas < desired_replicas:
            blocked_reason = f"availableReplicas={available_replicas} < desired={desired_replicas}"
            complete = False

        # 4. No old replicas remain
        if complete and old_replicas > 0:
            blocked_reason = f"old replicas remain: {old_replicas}"
            complete = False

        # 5. unavailableReplicas must be 0 (when present)
        if complete and unavailable_replicas is not None and unavailable_replicas > 0:
            blocked_reason = f"unavailableReplicas={unavailable_replicas}"
            complete = False

        state = DeploymentRolloutState(
            name=name,
            namespace=namespace,
            desired_replicas=desired_replicas,
            updated_replicas=updated_replicas,
            available_replicas=available_replicas,
            total_replicas=total_replicas,
            observed_generation=observed_generation,
            generation=generation,
            old_replicas=old_replicas,
            unavailable_replicas=unavailable_replicas,
            complete=complete,
            blocked_reason=blocked_reason,
        )
        states.append(state)

        if not complete:
            incomplete.append(f"{name}: {blocked_reason}")

    all_complete = all(s.complete for s in states)

    if all_complete:
        if states:
            summary = f"All {len(states)} deployment(s) rollout-complete"
        else:
            summary = "No deployments to check"
    else:
        summary = f"Deployment(s) not complete: {', '.join(incomplete)}"

    return all_complete, states, summary


def _check_rollout_success_from_json(pods_json: str, deployments_json: str, pvc_json: str) -> bool:
    """Check if rollout succeeded from JSON (all replicas ready).

    DEPRECATED: This function uses weak semantics (at least one available).
    Use _check_deployment_complete_from_json() for strict rollout-complete checks.
    """
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
