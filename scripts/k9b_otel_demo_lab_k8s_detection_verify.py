#!/usr/bin/env python3
"""Standalone verifier for K8s incident discovery.

This module provides a verification function that can be called
after the detection phase to verify that k9b discovered the
shipping incident.

P3c Discovery Validation Semantics:
- Validates incident discovery (scope check only)
- Accepts deployment_unavailable, pending_pod, warning_event_burst as valid symptom-level incidents
- Does NOT validate root-cause evidence (that's P4c's job)

Phase Result Reasons:
- incident_discovered: Incident found with matching scope
- incident_not_found: No incident discovered within timeout
- wrong_incident_identity: Incident found but wrong namespace/object
- wrong_candidate_class: Incident found but candidate class not accepted
- stale_incident: Incident found but appears to be from previous run
- incident_discovered_without_rca_evidence_yet: Discovery succeeded, RCA deferred to P4c
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_detection_constants import ACCEPTED_CANDIDATE_CLASSES
from scripts.k9b_otel_demo_lab_k8s_verdicts import (
    P3C_REASON_INCIDENT_DISCOVERED,
    P3C_REASON_INCIDENT_DISCOVERED_WITHOUT_RCA,
    P3C_REASON_INCIDENT_NOT_FOUND,
    P3C_REASON_STALE_INCIDENT,
    P3C_REASON_WRONG_CANDIDATE_CLASS,
    P3C_REASON_WRONG_INCIDENT_IDENTITY,
)


def verify_unschedulable_shipping_incident_discovered(
    artifact_dir: Path,
) -> dict[str, Any]:
    """Verify that k9b discovered the shipping incident.
    
    This is a standalone verifier that can be called after detection phase.
    
    P3c validates ONLY discovery (scope check). It accepts deployment_unavailable,
    pending_pod, and warning_event_burst as valid symptom-level incidents and
    does NOT require root-cause evidence. Root-cause validation is deferred to P4c.
    
    Args:
        artifact_dir: Directory containing detection artifacts
        
    Returns:
        Verification result with pass/fail and details
    """
    detection_evidence_path = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery" / "detection-evidence.json"
    
    if not detection_evidence_path.exists():
        return {
            "verified": False,
            "reason": P3C_REASON_INCIDENT_NOT_FOUND,
            "phase_result_reason": "detection_evidence_not_found",
            "path": str(detection_evidence_path),
            "phase": "p3c-k8s-discovery",
        }
    
    evidence = json.loads(detection_evidence_path.read_text())
    
    # Check discovery success
    if not evidence.get("discovery_success"):
        failure_reason = evidence.get("failure_reason", "discovery_failed")
        return {
            "verified": False,
            "reason": failure_reason,
            "phase_result_reason": failure_reason,
            "evidence": evidence,
            "phase": "p3c-k8s-discovery",
        }
    
    # Check incident ID
    if not evidence.get("incident_id"):
        return {
            "verified": False,
            "reason": P3C_REASON_INCIDENT_NOT_FOUND,
            "phase_result_reason": "no_incident_id",
            "evidence": evidence,
            "phase": "p3c-k8s-discovery",
        }
    
    # Check candidate class - MUST be accepted
    # deployment_unavailable is explicitly accepted as a valid symptom-level discovery
    candidate_class = evidence.get("candidate_class", "")
    if candidate_class not in ACCEPTED_CANDIDATE_CLASSES:
        return {
            "verified": False,
            "reason": P3C_REASON_WRONG_CANDIDATE_CLASS,
            "phase_result_reason": f"{P3C_REASON_WRONG_CANDIDATE_CLASS}:{candidate_class}",
            "candidate_class": candidate_class,
            "accepted_candidate_classes": list(ACCEPTED_CANDIDATE_CLASSES),
            "evidence": evidence,
            "phase": "p3c-k8s-discovery",
        }
    
    # Check shipping reference
    if not evidence.get("shipping_reference_found"):
        return {
            "verified": False,
            "reason": P3C_REASON_WRONG_INCIDENT_IDENTITY,
            "phase_result_reason": "no_shipping_reference",
            "evidence": evidence,
            "phase": "p3c-k8s-discovery",
        }
    
    # Check namespace
    if not evidence.get("namespace_matches"):
        return {
            "verified": False,
            "reason": P3C_REASON_WRONG_INCIDENT_IDENTITY,
            "phase_result_reason": "namespace_mismatch",
            "evidence": evidence,
            "phase": "p3c-k8s-discovery",
        }
    
    # Check for stale incident
    incident_timestamp = evidence.get("timestamp")
    injection_timestamp = evidence.get("injection_timestamp")
    is_stale = False
    if incident_timestamp and injection_timestamp:
        if isinstance(incident_timestamp, (int, float)) and incident_timestamp < injection_timestamp:
            is_stale = True
    
    if is_stale:
        return {
            "verified": False,
            "reason": P3C_REASON_STALE_INCIDENT,
            "phase_result_reason": P3C_REASON_STALE_INCIDENT,
            "incident_timestamp": incident_timestamp,
            "injection_timestamp": injection_timestamp,
            "evidence": evidence,
            "phase": "p3c-k8s-discovery",
        }
    
    # NOTE: We do NOT check validation_success here anymore.
    # P3c is for discovery only. The validation_success field previously
    # checked for evidence/RCA details, but that's P4c's responsibility.
    # deployment_unavailable is a valid P3c discovery result even without
    # scheduling-specific evidence - that evidence is checked in P4c.
    
    # Check if RCA evidence was present (informational only, not required for P3c)
    rca_evidence_present = _check_rca_evidence_present(evidence)
    
    return {
        "verified": True,
        "incident_id": evidence.get("incident_id"),
        "candidate_class": candidate_class,
        "namespace": evidence.get("target_namespace"),
        "phase_result_reason": P3C_REASON_INCIDENT_DISCOVERED if rca_evidence_present else P3C_REASON_INCIDENT_DISCOVERED_WITHOUT_RCA,
        "discovery_verdict": {
            "phase": "p3c-k8s-discovery",
            "success": True,
            "candidate_class": candidate_class,
            "root_cause_final": False,  # P3c is symptom-level only
            "root_cause_validation_deferred_to": "P4c",
            "rca_evidence_present": rca_evidence_present,
        },
        "evidence_summary": {
            "signal_count": evidence.get("signal_count", 0),
            "evidence_count": evidence.get("evidence_count", 0),
            "matching_signals_count": len(evidence.get("matching_signals", [])),
            "rca_evidence_present": rca_evidence_present,
        },
        "all_candidate_incidents_considered": _get_candidate_incidents(evidence),
        "rejection_reasons": _get_rejection_reasons(evidence),
        "evidence": evidence,
        "phase": "p3c-k8s-discovery",
    }


def _check_rca_evidence_present(evidence: dict[str, Any]) -> bool:
    """Check if RCA evidence is present in the incident (informational only).
    
    This does NOT affect P3c pass/fail - it's just informational for the artifact.
    """
    RCA_MARKERS = ["FailedScheduling", "Unschedulable", "nodeSelector", "k9b.dev/otel-lab-node"]
    
    root_cause_summary = evidence.get("root_cause_summary", "")
    evidence_str = json.dumps(evidence.get("matching_signals", []))
    
    for marker in RCA_MARKERS:
        if marker.lower() in root_cause_summary.lower() or marker.lower() in evidence_str.lower():
            return True
    
    return False


def _get_candidate_incidents(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Get list of all candidate incidents considered."""
    candidates = evidence.get("all_candidates", [])
    if candidates:
        return candidates
    
    # If no candidates stored, return just the matched one
    if evidence.get("incident_id"):
        return [{
            "incident_id": evidence.get("incident_id"),
            "candidate_class": evidence.get("candidate_class"),
            "matched": True,
        }]
    
    return []


def _get_rejection_reasons(evidence: dict[str, Any]) -> list[str]:
    """Get rejection reasons for non-matching candidates."""
    rejections = evidence.get("rejection_reasons", [])
    if rejections:
        return rejections
    
    # Build rejection reasons from validation failures
    reasons = []
    if not evidence.get("namespace_matches"):
        reasons.append("wrong_namespace")
    if not evidence.get("shipping_reference_found"):
        reasons.append("no_shipping_reference")
    if evidence.get("candidate_class") not in ACCEPTED_CANDIDATE_CLASSES:
        reasons.append(f"wrong_candidate_class:{evidence.get('candidate_class')}")
    
    return reasons
