#!/usr/bin/env python3
"""Standalone verifier for K8s multi-pass diagnosis.

This module provides a verification function that can be called
after the diagnosis phase to verify that k9b's automatic diagnosis
loop performed multi-pass diagnosis and identified the root cause.

P4c Root-Cause Validation Semantics:
- Validates root-cause evidence (scheduling markers)
- Requires scheduling-specific evidence (FailedScheduling, nodeSelector, etc.)
- Separated from P3c discovery validation
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    DIAGNOSIS_SOURCE_REAL,
    DIAGNOSIS_SOURCE_SIMULATED,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import (
    _validate_diagnosis_evidence,
    _validate_discovery_evidence,
    check_insufficient_passes,
    check_missing_root_cause_terms,
    check_read_only_violations,
)
from scripts.k9b_otel_demo_lab_k8s_verdicts import (
    SCHEDULING_ROOT_CAUSE_MARKERS,
    validate_unschedulable_shipping_root_cause,
)


def verify_unschedulable_shipping_mult_pass_diagnosis(
    artifact_dir: Path,
) -> dict[str, Any]:
    """Verify that k9b performed multi-pass diagnosis for the shipping incident.
    
    This is a standalone verifier that can be called after diagnosis phase.
    
    P4c validates root-cause evidence with scheduling-specific markers.
    This is SEPARATE from P3c's discovery validation.
    
    Verifier passes only if ALL of:
    - P3c detection evidence exists and is valid
    - Diagnosis evidence exists
    - Diagnosis loop ran with >= 2 passes
    - Final diagnosis mentions shipping
    - Final diagnosis mentions nodeSelector or scheduling constraint
    - Final diagnosis mentions k9b.dev/otel-lab-node
    - Final diagnosis mentions missing/no matching node/unschedulable
    - Read-only contract is maintained (no mutating checks)
    - Scheduling root-cause markers present (FailedScheduling, nodeSelector, etc.)
    
    Args:
        artifact_dir: Directory containing diagnosis artifacts
        
    Returns:
        Verification result with pass/fail and details
    """
    # Check P3c detection evidence first
    detection_evidence_path = (
        artifact_dir / "phase3-discovery" / "p3c-k8s-discovery" / "detection-evidence.json"
    )
    
    if not detection_evidence_path.exists():
        return {
            "verified": False,
            "reason": "p3c_evidence_not_found",
            "path": str(detection_evidence_path),
        }
    
    detection_evidence = json.loads(detection_evidence_path.read_text())
    
    # Validate P3c discovery
    is_valid_p3c, p3c_error = _validate_discovery_evidence(detection_evidence)
    if not is_valid_p3c:
        return {
            "verified": False,
            "reason": f"p3c_validation_failed: {p3c_error}",
            "detection_evidence": detection_evidence,
        }
    
    # Check diagnosis evidence
    diagnosis_evidence_path = (
        artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "diagnosis-evidence.json"
    )
    
    if not diagnosis_evidence_path.exists():
        return {
            "verified": False,
            "reason": "diagnosis_evidence_not_found",
            "path": str(diagnosis_evidence_path),
        }
    
    diagnosis_evidence = json.loads(diagnosis_evidence_path.read_text())
    
    # Check incident ID matches P3c
    p3c_incident_id = detection_evidence.get("incident_id")
    diagnosis_incident_id = diagnosis_evidence.get("incident_id")
    
    if p3c_incident_id and diagnosis_incident_id and p3c_incident_id != diagnosis_incident_id:
        return {
            "verified": False,
            "reason": "incident_id_mismatch",
            "p3c_incident_id": p3c_incident_id,
            "diagnosis_incident_id": diagnosis_incident_id,
        }
    
    # Validate diagnosis evidence structure
    is_valid_diagnosis, diagnosis_failures = _validate_diagnosis_evidence(diagnosis_evidence)
    if not is_valid_diagnosis:
        return {
            "verified": False,
            "reason": "diagnosis_validation_failed",
            "failures": diagnosis_failures,
            "diagnosis_evidence": diagnosis_evidence,
        }
    
    # Check for simulation usage - REJECT simulation
    diagnosis_source = diagnosis_evidence.get("diagnosis_source", DIAGNOSIS_SOURCE_REAL)
    simulation_used = diagnosis_evidence.get("simulation_used", False)
    
    if simulation_used or diagnosis_source == DIAGNOSIS_SOURCE_SIMULATED:
        return {
            "verified": False,
            "reason": "simulation_used_but_not_allowed",
            "diagnosis_source": diagnosis_source,
            "simulation_used": simulation_used,
            "failure_reason": "Simulation is not allowed in live-lab verification",
        }
    
    # Check real loop invocation
    real_loop_invoked = diagnosis_evidence.get("real_loop_invoked", False)
    if not real_loop_invoked:
        return {
            "verified": False,
            "reason": "real_loop_not_invoked",
            "real_loop_invoked": real_loop_invoked,
            "failure_reason": "Real k9b automatic diagnosis loop was not invoked",
        }
    
    # Check real pass artifacts
    real_pass_artifacts_found = diagnosis_evidence.get("real_pass_artifacts_found", False)
    if not real_pass_artifacts_found:
        return {
            "verified": False,
            "reason": "real_pass_artifacts_missing",
            "real_pass_artifacts_found": real_pass_artifacts_found,
            "pass_artifact_paths": diagnosis_evidence.get("pass_artifact_paths", []),
            "failure_reason": "Real pass artifacts from k9b diagnosis loop not found",
        }
    
    # Check pass count with specific error reason
    has_min_passes, actual_pass_count, min_required = check_insufficient_passes(diagnosis_evidence)
    if not has_min_passes:
        return {
            "verified": False,
            "reason": "insufficient_passes",
            "pass_count": actual_pass_count,
            "min_required": min_required,
        }
    
    # Check read-only contract with specific error reason
    is_read_only, read_only_violations = check_read_only_violations(diagnosis_evidence)
    if not is_read_only:
        return {
            "verified": False,
            "reason": "read_only_contract_violated",
            "violations": read_only_violations,
            "executed_checks": diagnosis_evidence.get("executed_checks", []),
        }
    
    # Check root-cause terms with specific error reason
    all_terms_present, term_checks = check_missing_root_cause_terms(diagnosis_evidence)
    if not all_terms_present:
        missing_terms = [k for k, v in term_checks.items() if not v]
        return {
            "verified": False,
            "reason": "missing_root_cause_terms",
            "missing_terms": missing_terms,
            "term_checks": term_checks,
            "root_cause_summary": diagnosis_evidence.get("root_cause_summary", ""),
        }
    
    # P4c Root-Cause Validation: Check for scheduling-specific markers
    # This is the key P4c validation that distinguishes symptom-level discovery (P3c)
    # from root-cause diagnosis (P4c)
    root_cause_verdict = validate_unschedulable_shipping_root_cause(diagnosis_evidence)
    
    if not root_cause_verdict.success:
        return {
            "verified": False,
            "reason": "missing_scheduling_root_cause_evidence",
            "p4c_verdict": root_cause_verdict.to_dict(),
            "root_cause_summary": diagnosis_evidence.get("root_cause_summary", ""),
            "required_markers": list(SCHEDULING_ROOT_CAUSE_MARKERS),
            "diagnosis_evidence": diagnosis_evidence,
        }
    
    # All checks passed
    return {
        "verified": True,
        "incident_id": diagnosis_incident_id,
        "candidate_class": diagnosis_evidence.get("candidate_class"),
        "namespace": diagnosis_evidence.get("target_namespace"),
        "pass_count": actual_pass_count,
        "pass_run_ids": diagnosis_evidence.get("pass_run_ids", []),
        "root_cause_matches": term_checks,
        "read_only": diagnosis_evidence.get("read_only", True),
        "root_cause_summary": diagnosis_evidence.get("root_cause_summary", ""),
        "p4c_verdict": root_cause_verdict.to_dict(),
        "diagnosis_evidence": diagnosis_evidence,
    }
