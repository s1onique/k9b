#!/usr/bin/env python3
"""Backend API functions for K8s incident discovery.

This module handles k9b backend API interactions:
- Snapshot trigger (POST /api/incidents/snapshot)
- Incident polling (GET /api/incidents)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from scripts.incident_discovery_gate.collect import (
    call_backend_incidents_api,
    call_backend_snapshot_api,
    get_backend_pod_info,
)
from scripts.k9b_lab_common_helpers import log
from scripts.k9b_otel_demo_lab_constants import K9B_NAMESPACE, SHIPPING_DEPLOYMENT
from scripts.k9b_otel_demo_lab_k8s_detection_constants import (
    DEFAULT_BACKEND_PORT,
    DEFAULT_DETECTION_POLL_INTERVAL_SECONDS,
    DEFAULT_DETECTION_TIMEOUT_SECONDS,
    DEFAULT_MAX_DETECTION_ATTEMPTS,
)
from scripts.k9b_otel_demo_lab_types import LabConfig


def _trigger_k9b_snapshot(config: LabConfig) -> dict[str, Any]:
    """Trigger k9b snapshot capture for the target namespace.
    
    Calls POST /api/incidents/snapshot on the k9b backend to capture
    a snapshot bundle for the OTel namespace.
    
    Args:
        config: Lab configuration
        
    Returns:
        Dict with snapshot trigger result
    """
    result: dict[str, Any] = {
        "triggered": False,
        "trigger_method": "snapshot_api",
        "namespace": config.namespace,
        "backend_namespace": K9B_NAMESPACE,
        "http_status": None,
        "response": None,
        "error": None,
        "pod_name": None,
    }
    
    # Get backend pod info - use k9b namespace for backend pod
    backend_namespace = K9B_NAMESPACE
    backend_deployment = "k9b-backend"
    backend_container = "backend"
    
    pod_info = get_backend_pod_info(config.kubeconfig, backend_namespace, backend_deployment)
    if not pod_info.get("found"):
        result["error"] = f"Could not find backend pod: {pod_info.get('error', 'unknown')}"
        result["trigger_method"] = "snapshot_api_failed"
        return result
    
    pod_name = pod_info.get("pod_name")
    result["pod_name"] = pod_name
    
    # Call snapshot API
    response, http_status, actual_pod = call_backend_snapshot_api(
        kubeconfig=config.kubeconfig,
        namespace=backend_namespace,
        backend_deployment=backend_deployment,
        backend_container=backend_container,
        backend_port=DEFAULT_BACKEND_PORT,
        snapshot_namespace=config.namespace,
        backend_pod_name=pod_name,
    )
    
    result["triggered"] = True
    result["http_status"] = http_status
    result["response"] = response
    result["actual_pod"] = actual_pod
    
    if http_status not in (200, 201):
        result["error"] = f"Snapshot API returned HTTP {http_status}"
    
    return result


def _get_k9b_incidents(
    config: LabConfig,
    poll_entry: dict[str, Any],
) -> list[dict[str, Any]]:
    """Get incidents from k9b backend API.
    
    Calls GET /api/incidents via kubectl exec on the backend pod.
    This is the canonical k9b incident discovery endpoint.
    
    Args:
        config: Lab configuration
        poll_entry: Poll entry to annotate
        
    Returns:
        List of incident dicts from k9b
    """
    # Use k9b namespace for backend pod, not incident namespace
    backend_namespace = K9B_NAMESPACE
    backend_deployment = "k9b-backend"
    backend_container = "backend"
    
    # Get backend pod for consistent reads
    pod_info = get_backend_pod_info(config.kubeconfig, backend_namespace, backend_deployment)
    if not pod_info.get("found"):
        poll_entry["error"] = f"Could not find backend pod: {pod_info.get('error', 'unknown')}"
        return []
    
    pod_name = pod_info.get("pod_name")
    poll_entry["backend_pod"] = pod_name
    
    # Call incidents API
    response_body, http_status = call_backend_incidents_api(
        kubeconfig=config.kubeconfig,
        namespace=backend_namespace,
        backend_deployment=backend_deployment,
        backend_container=backend_container,
        backend_port=DEFAULT_BACKEND_PORT,
        backend_pod_name=pod_name,
    )
    
    poll_entry["api_http_status"] = http_status
    
    if http_status != 200:
        poll_entry["error"] = f"API returned HTTP {http_status}"
        return []
    
    try:
        data = json.loads(response_body)
        incidents: list[dict[str, Any]] = data.get("incidents", [])
        poll_entry["source"] = "k9b_backend_api"
        return incidents
    except json.JSONDecodeError as e:
        poll_entry["error"] = f"Invalid JSON: {e}"
        return []


def _poll_k9b_incident_discovery(
    config: LabConfig,
    artifact_dir: Path,
    timeout_seconds: int = DEFAULT_DETECTION_TIMEOUT_SECONDS,
    poll_interval: int = DEFAULT_DETECTION_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Poll k9b incident discovery for shipping deployment incidents.
    
    Calls GET /api/incidents on the k9b backend to retrieve discovered incidents.
    
    Args:
        config: Lab configuration
        artifact_dir: Directory for artifacts
        timeout_seconds: Maximum time to wait
        poll_interval: Time between polls
        
    Returns:
        Dict with discovery result including incident_id, candidate_class, etc.
    """
    from scripts.k9b_otel_demo_lab_k8s_detection_match import _match_shipping_incident
    
    result: dict[str, Any] = {
        "incident_found": False,
        "incident_id": None,
        "candidate_class": None,
        "namespace": config.namespace,
        "target_deployment": SHIPPING_DEPLOYMENT,
        "poll_attempts": 0,
        "timeout_seconds": timeout_seconds,
        "poll_interval_seconds": poll_interval,
        "check_history": [],
        "discovery_source": "k9b_backend_api",
    }
    
    max_attempts = min(timeout_seconds // poll_interval, DEFAULT_MAX_DETECTION_ATTEMPTS)
    start_poll = time.time()
    
    for attempt in range(max_attempts):
        result["poll_attempts"] = attempt + 1
        elapsed = time.time() - start_poll
        
        log(f"  Discovery poll {attempt + 1}/{max_attempts} (elapsed: {elapsed:.0f}s)...")
        
        poll_entry: dict[str, Any] = {
            "attempt": attempt + 1,
            "elapsed_seconds": elapsed,
        }
        
        # Get incidents from k9b backend API
        incidents = _get_k9b_incidents(config, poll_entry)
        
        if incidents:
            poll_entry["incidents_count"] = len(incidents)
            
            # Look for shipping-related incident
            for incident in incidents:
                incident_match = _match_shipping_incident(incident, config.namespace)
                
                if incident_match:
                    result["incident_found"] = True
                    result["incident_id"] = incident.get("id") or incident.get("incident_id")
                    result["candidate_class"] = incident.get("candidate_class") or incident.get("class")
                    result["raw_incident"] = incident
                    poll_entry["matched_incident"] = result["incident_id"]
                    log(f"  Found matching incident: {result['incident_id']}")
                    break
        
        result["check_history"].append(poll_entry)
        
        if result["incident_found"]:
            break
        
        time.sleep(poll_interval)
    
    result["total_elapsed_seconds"] = time.time() - start_poll
    
    if not result["incident_found"]:
        result["failure_reason"] = "no_matching_incident_found"
    
    return result
