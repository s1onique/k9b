"""Backing pod identity extraction for Alertmanager service deduplication.

This module provides functions to query Kubernetes EndpointSlices and legacy v1 Endpoints
to extract pod UIDs for service deduplication. Pod UIDs are preferred over pod IPs
because they are stable identifiers that persist across pod restarts.

Deduplication identity priority:
1. Pod UIDs from EndpointSlice targetRef (preferred, v1.21+)
2. Pod namespace/name from EndpointSlice targetRef (when UID missing)
3. Pod UIDs from legacy v1 Endpoints (fallback)
4. Service endpoint identity (only when no backing pod identity exists)
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field

# Module logger
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackingPodIdentity:
    """Identity derived from backing pods of a service.
    
    This is the canonical identity for deduplication: two services that resolve
    to the same set of backing pod UIDs represent the same logical Alertmanager.
    
    Attributes:
        kind: How the identity was derived (backing_pods, service_endpoint)
        uid_set: Frozen set of pod UIDs (when available)
        name_set: Frozen set of pod namespace/name strings (fallback when UID missing)
        service_names: Service names that contributed to this identity
    """
    kind: str  # "backing_pods" or "service_endpoint"
    uid_set: frozenset[str] = field(default_factory=frozenset)
    name_set: frozenset[str] = field(default_factory=frozenset)
    service_names: tuple[str, ...] = field(default_factory=tuple)


def get_service_backing_identity(
    namespace: str,
    service_name: str,
    context: str | None = None,
) -> BackingPodIdentity | None:
    """Get the backing pod identity for a service via EndpointSlices.
    
    This uses kubectl to query EndpointSlices for the service and extracts
    pod UIDs from targetRef. Pod UIDs are preferred because they are stable
    identifiers, unlike pod IPs which can change on restart.
    
    Fallback chain:
    1. Pod UIDs from EndpointSlice targetRef (preferred)
    2. Pod namespace/name from EndpointSlice targetRef (when UID missing)
    3. Legacy v1 Endpoints (when EndpointSlice unavailable or empty)
    
    Args:
        namespace: Kubernetes namespace
        service_name: Name of the service
        context: Kubernetes context (optional)
        
    Returns:
        BackingPodIdentity with uid_set/name_set, or None if query failed
    """
    context_args = []
    if context:
        context_args = ["--context", context]
    
    # Try EndpointSlices first (v1.21+ recommended)
    pod_identity = _get_endpointslice_backing_identity(
        namespace, service_name, context_args
    )
    
    if pod_identity is not None and (pod_identity.uid_set or pod_identity.name_set):
        return pod_identity
    
    # Fallback to legacy v1 Endpoints
    pod_identity = _get_endpoints_backing_identity(
        namespace, service_name, context_args
    )
    
    if pod_identity is not None and (pod_identity.uid_set or pod_identity.name_set):
        return pod_identity
    
    # No backing pod identity found
    return None


def _get_endpointslice_backing_identity(
    namespace: str,
    service_name: str,
    context_args: list[str],
) -> BackingPodIdentity | None:
    """Get backing pod identity from EndpointSlices.
    
    Aggregates all EndpointSlices for a service and builds a unique set
    of pod identities from targetRef.
    """
    try:
        cmd = [
            "kubectl", "get", "endpointslices",
            "-n", namespace,
            "-l", f"kubernetes.io/service-name={service_name}",
            "-o", "json",
        ] + context_args
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            _logger.debug(
                "Failed to get endpoint slices for %s/%s: %s",
                namespace, service_name, result.stderr[:200],
            )
            return None
        
        data = json.loads(result.stdout)
        pod_uids: set[str] = set()
        pod_names: set[str] = set()
        
        # Aggregate all slices
        for item in data.get("items", []):
            for endpoint in item.get("endpoints", []):
                target_ref = endpoint.get("targetRef", {})
                if target_ref.get("kind") == "Pod":
                    pod_namespace = target_ref.get("namespace", namespace)
                    pod_name = target_ref.get("name", "")
                    pod_uid = target_ref.get("uid")
                    
                    if pod_uid:
                        pod_uids.add(pod_uid)
                    if pod_name:
                        pod_names.add(f"{pod_namespace}/{pod_name}")
        
        if pod_uids or pod_names:
            return BackingPodIdentity(
                kind="backing_pods",
                uid_set=frozenset(pod_uids),
                name_set=frozenset(pod_names),
                service_names=(service_name,),
            )
        return None
        
    except subprocess.TimeoutExpired:
        _logger.debug("EndpointSlice query timed out for %s/%s", namespace, service_name)
        return None
    except (json.JSONDecodeError, OSError) as exc:
        _logger.debug("Error querying EndpointSlices for %s/%s: %s", namespace, service_name, exc)
        return None


def _get_endpoints_backing_identity(
    namespace: str,
    service_name: str,
    context_args: list[str],
) -> BackingPodIdentity | None:
    """Get backing pod identity from legacy v1 Endpoints.
    
    This is the fallback when EndpointSlices are unavailable or empty.
    """
    try:
        cmd = [
            "kubectl", "get", "endpoints",
            "-n", namespace,
            service_name,
            "-o", "json",
        ] + context_args
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            _logger.debug(
                "Failed to get endpoints for %s/%s: %s",
                namespace, service_name, result.stderr[:200],
            )
            return None
        
        data = json.loads(result.stdout)
        pod_uids: set[str] = set()
        pod_names: set[str] = set()
        
        for subset in data.get("subsets", []):
            for address in subset.get("addresses", []):
                target_ref = address.get("targetRef", {})
                if target_ref.get("kind") == "Pod":
                    pod_namespace = target_ref.get("namespace", namespace)
                    pod_name = target_ref.get("name", "")
                    pod_uid = target_ref.get("uid")
                    
                    if pod_uid:
                        pod_uids.add(pod_uid)
                    if pod_name:
                        pod_names.add(f"{pod_namespace}/{pod_name}")
        
        if pod_uids or pod_names:
            return BackingPodIdentity(
                kind="backing_pods",
                uid_set=frozenset(pod_uids),
                name_set=frozenset(pod_names),
                service_names=(service_name,),
            )
        return None
        
    except subprocess.TimeoutExpired:
        _logger.debug("Endpoints query timed out for %s/%s", namespace, service_name)
        return None
    except (json.JSONDecodeError, OSError) as exc:
        _logger.debug("Error querying Endpoints for %s/%s: %s", namespace, service_name, exc)
        return None
