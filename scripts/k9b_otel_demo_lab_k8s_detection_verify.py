#!/usr/bin/env python3
"""Standalone verifier for K8s incident discovery.

This module provides a verification function that can be called
after the detection phase to verify that k9b discovered the
shipping incident.

P3c Discovery Validation Semantics:
- Validates incident discovery (scope check only)
- Accepts deployment_unavailable as a valid symptom-level incident
- Does NOT validate root-cause evidence (that's P4c's job)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_detection_constants import ACCEPTED_CANDIDATE_CLASSES


def verify_unschedulable_shipping_incident_discovered(
    artifact_dir: Path,
) -> dict[str, Any]:
    """Verify that k9b discovered the shipping incident.
    
    This is a standalone verifier that can be called after detection phase.
    
    P3c validates ONLY discovery (scope check). It accepts deployment_unavailable
    as a valid symptom-level incident and does NOT require root-cause evidence.
    Root-cause validation is deferred to P4c.
    
    Args:
        artifact_dir: Directory containing detection artifacts
        
    Returns:
        Verification result with pass/fail and details
    """
    detection_evidence_path = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery" / "detection-evidence.json"
    
    if not detection_evidence_path.exists():
        return {
            "verified": False,
            "reason": "detection_evidence_not_found",
            "path": str(detection_evidence_path),
        }
    
    evidence = json.loads(detection_evidence_path.read_text())
    
    # Check discovery success
    if not evidence.get("discovery_success"):
        return {
            "verified": False,
            "reason": evidence.get("failure_reason", "discovery_failed"),
            "evidence": evidence,
        }
    
    # Check incident ID
    if not evidence.get("incident_id"):
        return {
            "verified": False,
            "reason": "no_incident_id",
            "evidence": evidence,
        }
    
    # Check candidate class - MUST be accepted
    # deployment_unavailable is explicitly accepted as a valid symptom-level discovery
    candidate_class = evidence.get("candidate_class", "")
    if candidate_class not in ACCEPTED_CANDIDATE_CLASSES:
        return {
            "verified": False,
            "reason": f"candidate_class_rejected:{candidate_class}",
            "evidence": evidence,
        }
    
    # Check shipping reference
    if not evidence.get("shipping_reference_found"):
        return {
            "verified": False,
            "reason": "no_shipping_reference",
            "evidence": evidence,
        }
    
    # Check namespace
    if not evidence.get("namespace_matches"):
        return {
            "verified": False,
            "reason": "namespace_mismatch",
            "evidence": evidence,
        }
    
    # NOTE: We do NOT check validation_success here anymore.
    # P3c is for discovery only. The validation_success field previously
    # checked for evidence/RCA details, but that's P4c's responsibility.
    # deployment_unavailable is a valid P3c discovery result even without
    # scheduling-specific evidence - that evidence is checked in P4c.
    
    return {
        "verified": True,
        "incident_id": evidence.get("incident_id"),
        "candidate_class": candidate_class,
        "namespace": evidence.get("target_namespace"),
        "discovery_verdict": {
            "phase": "p3c-k8s-discovery",
            "success": True,
            "candidate_class": candidate_class,
            "root_cause_final": False,  # P3c is symptom-level only
            "root_cause_validation_deferred_to": "P4c",
        },
        "evidence": evidence,
    }
