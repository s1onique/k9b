#!/usr/bin/env python3
"""Incident matching and validation for K8s detection.

This module contains the strict matching logic for identifying
shipping-related incidents and validating discovery results.
"""

from __future__ import annotations

import json
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_detection_constants import (
    ACCEPTED_CANDIDATE_CLASSES,
    FAILED_SCHEDULING_PATTERNS,
)


def _match_shipping_incident(
    incident: dict[str, Any],
    namespace: str,
) -> bool:
    """Check if an incident matches the shipping deployment.
    
    Requires a POSITIVE match on shipping - no fallback to generic matching.
    A valid match must include at least one of:
    - object_name == "shipping"
    - object_name starts with "shipping-"
    - evidence/signal mentions "shipping"
    - evidence/signal mentions "FailedScheduling" AND namespace context
    - evidence/signal mentions "Unschedulable" AND namespace context
    
    Namespace mismatch always rejects.
    
    Args:
        incident: Incident dict from k9b
        namespace: Expected namespace
        
    Returns:
        True only if incident is a positive shipping match
    """
    # Check namespace - required for match
    incident_namespace = incident.get("namespace") or incident.get("metadata", {}).get("namespace", "")
    if incident_namespace and incident_namespace != namespace:
        return False
    
    # Extract object info
    object_name = incident.get("object_name") or incident.get("objectName") or incident.get("name", "")
    object_kind = incident.get("object_kind") or incident.get("objectKind") or incident.get("kind", "")
    
    # Positive match 1: object_name is "shipping" or starts with "shipping-"
    if object_name == "shipping":
        return True
    if object_name.startswith("shipping-"):
        return True
    
    # Positive match 2: object_kind is Deployment and object_name contains shipping
    if object_kind.lower() == "deployment" and "shipping" in object_name.lower():
        return True
    
    # Positive match 3: Check evidence/signals for shipping mention
    evidence = incident.get("evidence", []) or incident.get("signals", [])
    evidence_str = json.dumps(evidence).lower()
    
    # Must have shipping in evidence AND one of the failure patterns
    has_shipping = "shipping" in evidence_str
    has_failure_pattern = any(p.lower() in evidence_str for p in FAILED_SCHEDULING_PATTERNS)
    
    if has_shipping and has_failure_pattern:
        return True
    
    # Positive match 4: evidence mentions FailedScheduling/Unschedulable specifically
    if has_failure_pattern:
        # Only match if we can tie it to shipping context
        # Check if evidence mentions the specific pod name pattern
        for item in evidence:
            item_str = json.dumps(item).lower()
            if ("shipping-" in item_str or object_name.startswith("shipping-")) and has_failure_pattern:
                return True
    
    # DO NOT match on generic pending/failed status alone
    # This was the bug - rejecting unrelated same-namespace incidents
    
    return False


def _validate_namespace(
    incident: dict[str, Any],
    expected_namespace: str,
) -> bool:
    """Validate that incident references the expected namespace.
    
    Args:
        incident: Incident dict
        expected_namespace: Expected namespace
        
    Returns:
        True if namespace matches or is empty (accepts all)
    """
    incident_namespace: str = incident.get("namespace") or incident.get("metadata", {}).get("namespace", "") or ""
    if not incident_namespace:
        # Empty namespace means no filtering - accept
        return True
    return incident_namespace == expected_namespace


def _validate_shipping_reference(
    incident: dict[str, Any],
) -> bool:
    """Validate that incident references shipping specifically.
    
    Args:
        incident: Incident dict
        
    Returns:
        True if shipping reference found
    """
    object_name = incident.get("object_name") or incident.get("name", "")
    
    # Check object name
    if object_name == "shipping" or object_name.startswith("shipping-"):
        return True
    
    # Check evidence
    evidence = incident.get("evidence", []) or incident.get("signals", [])
    for item in evidence:
        item_str = json.dumps(item).lower()
        if "shipping" in item_str:
            return True
    
    return False


def _extract_matching_signals(
    signals: list[Any],
) -> list[dict[str, Any]]:
    """Extract signals that match shipping/failure patterns.
    
    Args:
        signals: List of signals/evidence
        
    Returns:
        List of matching signal dicts
    """
    matching = []
    for signal in signals:
        signal_str = json.dumps(signal).lower()
        is_matching = (
            "shipping" in signal_str or
            "failedscheduling" in signal_str or
            "unschedulable" in signal_str or
            "pending" in signal_str
        )
        if is_matching:
            if isinstance(signal, dict):
                matching.append(signal)
            else:
                matching.append({"raw": signal})
    return matching


def _validate_discovery_evidence(
    incident: dict[str, Any],
    candidate_class: str | None,
    namespace: str,
) -> dict[str, Any]:
    """Validate that discovered incident has appropriate evidence.
    
    This validation is consistent with _match_shipping_incident():
    - shipping reference may be in object_name, signals, or evidence
    - evidence/signals must exist
    - candidate class must be accepted
    
    Args:
        incident: Incident dict
        candidate_class: Candidate class from discovery
        namespace: Expected namespace
        
    Returns:
        Validation result dict
    """
    import json

    validation: dict[str, Any] = {
        "valid": False,
        "checks": [],
    }
    
    # Check 1: Has incident ID
    incident_id = incident.get("id") or incident.get("incident_id")
    has_id = bool(incident_id)
    validation["checks"].append({"check": "has_incident_id", "passed": has_id})
    
    # Check 2: Has candidate class
    has_class = bool(candidate_class)
    validation["checks"].append({"check": "has_candidate_class", "passed": has_class})
    
    # Check 3: Candidate class is accepted
    class_accepted = candidate_class in ACCEPTED_CANDIDATE_CLASSES if candidate_class else False
    validation["checks"].append({
        "check": "candidate_class_accepted",
        "passed": class_accepted,
        "value": candidate_class,
    })
    
    # Check 4: Has signals or evidence (required for validation)
    signals = incident.get("signals", incident.get("evidence", []))
    has_evidence = len(signals) > 0
    validation["checks"].append({
        "check": "has_evidence",
        "passed": has_evidence,
        "evidence_count": len(signals),
    })
    
    # Check 5: References shipping (consistent with _match_shipping_incident)
    # Shipping reference may be in object_name, signals, or evidence
    object_name = incident.get("object_name", "") or incident.get("name", "")
    evidence_str = json.dumps(signals).lower()
    
    # Check object_name for shipping
    has_shipping_in_name = object_name == "shipping" or object_name.startswith("shipping-")
    
    # Check evidence/signals for shipping
    has_shipping_in_evidence = "shipping" in evidence_str
    
    # Check for failure patterns in evidence
    has_failure_in_evidence = any(
        p.lower() in evidence_str for p in FAILED_SCHEDULING_PATTERNS
    )
    
    # Shipping reference found if in name OR in evidence with failure pattern
    shipping_reference_found = has_shipping_in_name or (has_shipping_in_evidence and has_failure_in_evidence)
    
    validation["checks"].append({
        "check": "references_shipping",
        "passed": shipping_reference_found,
        "has_shipping_in_name": has_shipping_in_name,
        "has_shipping_in_evidence": has_shipping_in_evidence,
        "object_name": object_name,
    })
    
    # Check 6: Namespace matches when present
    incident_namespace = incident.get("namespace", "") or incident.get("metadata", {}).get("namespace", "")
    namespace_matches = not incident_namespace or incident_namespace == namespace
    validation["checks"].append({
        "check": "namespace_matches",
        "passed": namespace_matches,
        "incident_namespace": incident_namespace,
        "expected_namespace": namespace,
    })
    
    validation["valid"] = all(c["passed"] for c in validation["checks"])
    return validation
