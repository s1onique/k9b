#!/usr/bin/env python3
"""Polling and symptom detection for K8s incident injection.

This module handles polling for evidence of unschedulable pod symptoms
including Pending pods and FailedScheduling events.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from scripts.k9b_lab_common_helpers import kubectl_events, kubectl_json, log
from scripts.k9b_otel_demo_lab_k8s_injection_types import (
    DEFAULT_MAX_POLL_ATTEMPTS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)


def _poll_for_symptoms(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    artifact_dir: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Poll for evidence of unschedulable pod symptoms.
    
    Uses robust pod lookup strategy:
    1. First try label selector (app=shipping)
    2. Fallback: list pods in namespace, filter by name prefix shipping-*
    3. Check ownerReference to verify ownership
    
    For events: query Pod events (not Deployment), filter by pod name prefix.
    
    Returns a dict with:
    - symptom_found: bool
    - symptom_type: str (Pending, FailedScheduling, or None)
    - poll_attempts: int
    - deployment_unavailable: bool
    - final_state: dict
    """
    result: dict[str, Any] = {
        "symptom_found": False,
        "symptom_type": None,
        "poll_attempts": 0,
        "timeout_seconds": timeout_seconds,
        "poll_interval_seconds": poll_interval,
        "check_history": [],
        "deployment_unavailable": False,
        "pod_lookup_method": None,
    }
    
    max_attempts = min(timeout_seconds // poll_interval, DEFAULT_MAX_POLL_ATTEMPTS)
    start_poll = time.time()
    
    for attempt in range(max_attempts):
        result["poll_attempts"] = attempt + 1
        elapsed = time.time() - start_poll
        
        log(f"  Poll attempt {attempt + 1}/{max_attempts} (elapsed: {elapsed:.0f}s)...")
        
        poll_entry: dict[str, Any] = {
            "attempt": attempt + 1,
            "elapsed_seconds": elapsed,
        }
        
        # Step 1: Robust pod lookup (label selector with fallback to prefix filter)
        pods: list[dict[str, Any]] = []
        
        # Primary: try label selector
        pods_result = kubectl_json(
            kubeconfig,
            "pod",
            namespace,
            extra_args=["-l", "app=shipping", "-o", "json"],
        )
        
        if pods_result.success and pods_result.data:
            items = pods_result.data.get("items", [])
            # Fallback when label selector returns no pods
            if items:
                pods = items
                poll_entry["pod_lookup_method"] = "label_selector"
            else:
                # Fallback: list all pods, filter by name prefix
                all_pods_result = kubectl_json(kubeconfig, "pod", namespace, extra_args=["-o", "json"])
                if all_pods_result.success and all_pods_result.data:
                    all_pods = all_pods_result.data.get("items", [])
                    pods = _filter_pods_by_ownership(all_pods, deployment)
                    poll_entry["pod_lookup_method"] = "prefix_filter"
                else:
                    pods = []
        else:
            # Fallback: list all pods, filter by name prefix
            all_pods_result = kubectl_json(kubeconfig, "pod", namespace, extra_args=["-o", "json"])
            if all_pods_result.success and all_pods_result.data:
                all_pods = all_pods_result.data.get("items", [])
                pods = _filter_pods_by_ownership(all_pods, deployment)
                poll_entry["pod_lookup_method"] = "prefix_filter"
            else:
                pods = []
        
        poll_entry["pods_found"] = len(pods)
        
        # Step 2: Check pod status for Pending
        for pod in pods:
            pod_name = pod.get("metadata", {}).get("name", "unknown")
            phase = pod.get("status", {}).get("phase", "Unknown")
            conditions = pod.get("status", {}).get("conditions", [])
            
            poll_entry["pod_status"] = {
                "name": pod_name,
                "phase": phase,
                "conditions": conditions,
            }
            
            if phase == "Pending":
                # Check for scheduling condition
                for cond in conditions:
                    if cond.get("type") == "PodScheduled" and cond.get("status") == "False":
                        reason = cond.get("reason", "Unknown")
                        message = cond.get("message", "")
                        
                        if reason == "Unschedulable":
                            result["symptom_found"] = True
                            result["symptom_type"] = "FailedScheduling"
                            poll_entry["symptom_detected"] = {
                                "type": "FailedScheduling",
                                "reason": reason,
                                "message": message,
                            }
                            log(f"  Found FailedScheduling for pod {pod_name}: {reason}")
                            break
                        elif reason != "SchedulingGated":
                            # Any other reason for not being scheduled could be a symptom
                            result["symptom_found"] = True
                            result["symptom_type"] = "Pending"
                            poll_entry["symptom_detected"] = {
                                "type": "Pending",
                                "reason": reason,
                                "message": message,
                            }
                            log(f"  Found Pending pod {pod_name}: {reason}")
                            break
            
            if result["symptom_found"]:
                break
        
        # Step 3: Check deployment status for unavailable replicas
        deployment_result = kubectl_json(
            kubeconfig,
            "deployment",
            namespace,
            extra_args=[deployment, "-o", "json"],
        )
        
        if deployment_result.success and deployment_result.data:
            status = deployment_result.data.get("status", {})
            replicas = status.get("replicas", 0)
            ready_replicas = status.get("readyReplicas", 0)
            unavailable_replicas = status.get("unavailableReplicas", 0)
            
            poll_entry["deployment_status"] = {
                "replicas": replicas,
                "readyReplicas": ready_replicas,
                "unavailableReplicas": unavailable_replicas,
            }
            
            # Deployment is unavailable if ready < desired or has unavailable
            if replicas > 0 and (ready_replicas < replicas or unavailable_replicas > 0):
                poll_entry["deployment_unavailable"] = True
                result["deployment_unavailable"] = True
                log(f"  Deployment unavailable: {ready_replicas}/{replicas} ready, {unavailable_replicas} unavailable")
        
        # Step 4: Check FailedScheduling events (Pod events, not Deployment events)
        events_result = kubectl_events(
            kubeconfig,
            namespace,
            extra_args=["--field-selector", "reason=FailedScheduling,involvedObject.kind=Pod"],
        )
        
        if events_result.success and events_result.stdout:
            event_lines = events_result.stdout.strip().split("\n")
            for line in event_lines:
                if "shipping-" in line and ("FailedScheduling" in line or "Unschedulable" in line):
                    poll_entry["failed_scheduling_event"] = line.strip()
                    if not result["symptom_found"]:
                        result["symptom_found"] = True
                        result["symptom_type"] = "FailedScheduling"
                    log(f"  Found scheduling event for shipping pod: {line.strip()[:100]}...")
                    break
        
        # Alternative: also check events without kind filter
        if not poll_entry.get("failed_scheduling_event"):
            events_result2 = kubectl_events(
                kubeconfig,
                namespace,
                extra_args=["--field-selector", "reason=FailedScheduling"],
            )
            
            if events_result2.success and events_result2.stdout:
                event_lines = events_result2.stdout.strip().split("\n")
                for line in event_lines:
                    if "shipping-" in line:
                        poll_entry["failed_scheduling_event"] = line.strip()
                        if not result["symptom_found"]:
                            result["symptom_found"] = True
                            result["symptom_type"] = "FailedScheduling"
                        log(f"  Found scheduling event: {line.strip()[:100]}...")
                        break
        
        result["check_history"].append(poll_entry)
        
        if result["symptom_found"]:
            break
        
        time.sleep(poll_interval)
    
    result["total_elapsed_seconds"] = time.time() - start_poll
    
    # Add summary
    result["summary"] = {
        "symptom_found": result["symptom_found"],
        "symptom_type": result["symptom_type"],
        "deployment_unavailable": result["deployment_unavailable"],
        "poll_attempts": result["poll_attempts"],
        "total_elapsed_seconds": result["total_elapsed_seconds"],
    }
    
    return result


def _filter_pods_by_ownership(
    all_pods: list[dict[str, Any]],
    deployment_name: str,
) -> list[dict[str, Any]]:
    """Filter pods by ownership relationship to deployment.
    
    This is the robust fallback when label selectors don't work.
    Filters by:
    1. Pod name prefix matching deployment name + "-"
    2. OwnerReference chain: Pod -> ReplicaSet -> Deployment
    
    Args:
        all_pods: All pods in namespace
        deployment_name: Name of deployment to match
        
    Returns:
        Pods owned by the specified deployment
    """
    matching_pods: list[dict[str, Any]] = []
    
    for pod in all_pods:
        pod_name = pod.get("metadata", {}).get("name", "")
        owner_references = pod.get("metadata", {}).get("ownerReferences", [])
        
        # Strategy 1: Name prefix matching (shipping-*)
        if not pod_name.startswith(f"{deployment_name}-"):
            continue
        
        # Strategy 2: Verify ownership chain
        for owner in owner_references:
            owner_kind = owner.get("kind", "")
            owner_name = owner.get("name", "")
            
            # Pod -> ReplicaSet -> Deployment chain
            if owner_kind == "ReplicaSet" and owner_name.startswith(f"{deployment_name}-"):
                matching_pods.append(pod)
                break
            elif owner_kind == "ReplicaSet" and deployment_name in owner_name:
                matching_pods.append(pod)
                break
    
    return matching_pods
