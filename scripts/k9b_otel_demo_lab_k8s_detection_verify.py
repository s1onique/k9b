#!/usr/bin/env python3
"""Standalone verifier for K8s incident discovery.

This module provides a verification function that can be called
after the detection phase to verify that k9b discovered the
shipping incident.
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
    
    # Check validation success
    if not evidence.get("validation_success"):
        return {
            "verified": False,
            "reason": "validation_failed",
            "evidence": evidence,
        }
    
    # Check incident ID
    if not evidence.get("incident_id"):
        return {
            "verified": False,
            "reason": "no_incident_id",
            "evidence": evidence,
        }
    
    # Check candidate class
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
    
    return {
        "verified": True,
        "incident_id": evidence.get("incident_id"),
        "candidate_class": candidate_class,
        "namespace": evidence.get("target_namespace"),
        "evidence": evidence,
    }
