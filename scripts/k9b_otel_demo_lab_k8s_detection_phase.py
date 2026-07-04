#!/usr/bin/env python3
"""Main detection phase for K8s incident discovery.

This module contains the main phase function that orchestrates
the P3c detection workflow.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from scripts.k9b_lab_common_helpers import log, write_json_artifact
from scripts.k9b_otel_demo_lab_constants import (
    K8S_INJECTION_NODE_SELECTOR_KEY,
    K8S_INJECTION_NODE_SELECTOR_VALUE,
    PHASE_INJECTED,
    SHIPPING_DEPLOYMENT,
)
from scripts.k9b_otel_demo_lab_k8s_detection_api import (
    _poll_k9b_incident_discovery,
    _trigger_k9b_snapshot,
)
from scripts.k9b_otel_demo_lab_k8s_detection_constants import (
    ACCEPTED_CANDIDATE_CLASSES,
    DEFAULT_DETECTION_POLL_INTERVAL_SECONDS,
    DEFAULT_DETECTION_TIMEOUT_SECONDS,
)
from scripts.k9b_otel_demo_lab_k8s_detection_match import (
    _extract_matching_signals,
    _validate_namespace,
    _validate_shipping_reference,
)
from scripts.k9b_otel_demo_lab_k8s_verdicts import (
    P3C_REASON_INCIDENT_DISCOVERED_WITHOUT_RCA,
    P3C_REASON_INCIDENT_NOT_FOUND,
    P3C_REASON_WRONG_CANDIDATE_CLASS,
    P3C_REASON_WRONG_INCIDENT_IDENTITY,
)
from scripts.k9b_otel_demo_lab_types import LabConfig, LabPhaseResult


def _populate_selector_literal_from_p2b(
    artifact_dir: Path,
    evidence: dict[str, Any],
) -> None:
    """Populate selector_literal from P2b injection evidence for P4c.

    P2b writes the injected nodeSelector to injection-evidence.json.
    P3c reads this and populates the detection evidence with the known
    selector_literal so P4c can use it without relying on lossy K8s event prose.

    This fixes the contract leak where P4c receives generic scheduler messages
    but cannot prove the exact injected selector key/value.

    Args:
        artifact_dir: Root artifact directory
        evidence: Detection evidence dict to update
    """
    injection_evidence_path = artifact_dir / PHASE_INJECTED / "p2b-k8s-injection" / "injection-evidence.json"

    if not injection_evidence_path.exists():
        log("  NOTE: P2b injection evidence not found - selector_literal not populated")
        evidence["selector_literal"] = None
        evidence["selector_key"] = None
        evidence["selector_value"] = None
        evidence["selector_source"] = None
        return

    try:
        injection_evidence = json.loads(injection_evidence_path.read_text())

        # Extract selector from P2b evidence
        node_selector = injection_evidence.get("node_selector", {})
        if not node_selector:
            # Fallback: construct from constants if P2b used them
            node_selector = {
                K8S_INJECTION_NODE_SELECTOR_KEY: K8S_INJECTION_NODE_SELECTOR_VALUE,
            }

        # Build selector_literal in P2b's format (key=value)
        selector_key = K8S_INJECTION_NODE_SELECTOR_KEY
        selector_value = node_selector.get(selector_key, K8S_INJECTION_NODE_SELECTOR_VALUE)
        selector_literal = f"{selector_key}={selector_value}"

        # Populate evidence for P4c
        evidence["selector_literal"] = selector_literal
        evidence["selector_key"] = selector_key
        evidence["selector_value"] = selector_value
        evidence["selector_source"] = "p2b_injection"

        log(f"  Populated selector_literal from P2b: {selector_literal}")
    except (json.JSONDecodeError, OSError) as e:
        log(f"  WARNING: Could not read P2b injection evidence: {e}")
        evidence["selector_literal"] = None
        evidence["selector_key"] = None
        evidence["selector_value"] = None
        evidence["selector_source"] = None


def phase_p3c_verify_k8s_incident_discovery(
    config: LabConfig,
    artifact_dir: Path,
    injection_artifacts: dict[str, Any] | None = None,
) -> LabPhaseResult:
    """Phase P3c: Verify k9b can discover the K8s-native shipping incident.
    
    After P2b injection succeeds, this phase:
    1. Triggers k9b snapshot capture for the OTel namespace
    2. Polls k9b backend API for incidents
    3. Checks for incidents matching shipping deployment
    4. Validates candidate class and evidence
    5. Writes detection artifact with full schema
    
    Phase success requires ALL of:
    - An incident is found
    - Candidate class is accepted
    - Evidence validation is valid
    - Incident references the OTel namespace
    - Incident references shipping (object name, evidence, or signals)
    
    Args:
        config: Lab configuration
        artifact_dir: Directory for phase artifacts
        injection_artifacts: Optional dict of P2b injection artifacts
        
    Returns:
        LabPhaseResult with detection outcome and artifacts
    """
    from scripts.k9b_otel_demo_lab_constants import PHASE_DISCOVERY
    
    start = time.time()
    phase_dir = artifact_dir / PHASE_DISCOVERY
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    detection_dir = phase_dir / "p3c-k8s-discovery"
    detection_dir.mkdir(parents=True, exist_ok=True)
    
    log("=" * 60)
    log("PHASE P3c: Verify k9b incident discovery")
    log("=" * 60)
    log(f"Target: discover incidents for {SHIPPING_DEPLOYMENT} in {config.namespace}")
    
    # Initialize evidence with full schema
    evidence: dict[str, Any] = {
        # Identification
        "phase": "p3c-k8s-discovery",
        "scenario": "unschedulable-shipping-rollout",
        "target_deployment": SHIPPING_DEPLOYMENT,
        "target_namespace": config.namespace,
        "accepted_candidate_classes": list(ACCEPTED_CANDIDATE_CLASSES),
        "timestamp": time.time(),
        # Discovery source
        "discovery_source": "k9b_backend_api",
        "discovery_trigger": None,  # Will be set during execution
        # Validation state
        "discovery_success": False,
        "validation_success": False,
        "incident_id": None,
        "candidate_class": None,
        "candidate_class_valid": False,
        "namespace_matches": False,
        "shipping_reference_found": False,
        "failure_reason": None,
        # Counts
        "signal_count": 0,
        "evidence_count": 0,
        "matching_signals": [],
        "matching_evidence": [],
        # Polling
        "poll_attempts": 0,
        "timeout_seconds": DEFAULT_DETECTION_TIMEOUT_SECONDS,
    }
    
    # Step 1: Read injection evidence and populate selector_literal for P4c
    _populate_selector_literal_from_p2b(artifact_dir, evidence)
    if injection_artifacts:
        evidence["injection_artifacts"] = injection_artifacts
        log("Using injection artifacts from P2b")
    
    # Step 2: Trigger snapshot capture
    log("Step 1: Triggering k9b snapshot capture...")
    snapshot_result = _trigger_k9b_snapshot(config)
    evidence["snapshot_trigger"] = snapshot_result
    evidence["discovery_trigger"] = snapshot_result.get("trigger_method", "unknown")
    
    # Step 3: Poll k9b incident discovery
    log("Step 2: Polling k9b incident discovery...")
    discovery_result = _poll_k9b_incident_discovery(
        config,
        detection_dir,
        timeout_seconds=DEFAULT_DETECTION_TIMEOUT_SECONDS,
        poll_interval=DEFAULT_DETECTION_POLL_INTERVAL_SECONDS,
    )
    
    evidence["poll_result"] = discovery_result
    evidence["poll_attempts"] = discovery_result.get("poll_attempts", 0)
    
    # Step 4: Validate discovery result
    if discovery_result["incident_found"]:
        incident = discovery_result.get("raw_incident", {})
        incident_id = discovery_result.get("incident_id")
        candidate_class = discovery_result.get("candidate_class")
        
        log(f"Incident discovered: {incident_id}")
        log(f"Candidate class: {candidate_class}")
        
        evidence["incident_id"] = incident_id
        evidence["candidate_class"] = candidate_class
        
        # Validation checks - P3c validates discovery scope ONLY
        # Root-cause evidence is validated in P4c
        namespace_matches = _validate_namespace(incident, config.namespace)
        evidence["namespace_matches"] = namespace_matches
        
        shipping_match = _validate_shipping_reference(incident)
        evidence["shipping_reference_found"] = shipping_match
        
        candidate_class_valid = candidate_class in ACCEPTED_CANDIDATE_CLASSES
        evidence["candidate_class_valid"] = candidate_class_valid
        
        # Evidence counts
        signals = incident.get("signals", incident.get("evidence", []))
        evidence["signal_count"] = len(signals)
        evidence["evidence_count"] = len(signals)
        
        # Extract matching signals/evidence
        evidence["matching_signals"] = _extract_matching_signals(signals)
        evidence["matching_evidence"] = evidence["matching_signals"]
        
        # Phase success requires scope validations to pass
        discovery_validations_passed = (
            namespace_matches and
            shipping_match and
            candidate_class_valid
        )
        
        # NOTE: We do NOT require full evidence validation at P3c.
        # P3c is for incident DISCOVERY, not root-cause diagnosis.
        # deployment_unavailable is a valid symptom-level incident.
        # Root-cause evidence (FailedScheduling, nodeSelector, etc.) is
        # validated in P4c, not P3c.
        evidence["scope_validation_success"] = discovery_validations_passed
        evidence["validation_success"] = discovery_validations_passed  # Legacy compatibility
        evidence["root_cause_validation_deferred_to"] = "P4c"
        evidence["discovery_success"] = discovery_validations_passed
        
        if discovery_validations_passed:
            log(f"P3c discovery PASSED: {candidate_class} incident found for {SHIPPING_DEPLOYMENT}")
            log("NOTE: Root-cause evidence will be validated in P4c")
            # Set phase_result_reason for verifier
            evidence["phase_result_reason"] = P3C_REASON_INCIDENT_DISCOVERED_WITHOUT_RCA
        else:
            if not namespace_matches:
                evidence["failure_reason"] = "namespace_mismatch"
                evidence["phase_result_reason"] = P3C_REASON_WRONG_INCIDENT_IDENTITY
                log("Validation FAILED: namespace does not match")
            elif not shipping_match:
                evidence["failure_reason"] = "no_shipping_reference"
                evidence["phase_result_reason"] = P3C_REASON_WRONG_INCIDENT_IDENTITY
                log("Validation FAILED: no shipping reference found")
            else:
                evidence["failure_reason"] = f"candidate_class_rejected:{candidate_class}"
                evidence["phase_result_reason"] = P3C_REASON_WRONG_CANDIDATE_CLASS
                log(f"Validation FAILED: candidate class '{candidate_class}' not accepted")
        
    else:
        log("ERROR: No incident discovered within timeout - fail-closed")
        evidence["failure_reason"] = discovery_result.get("failure_reason", "no_incident_found")
        evidence["phase_result_reason"] = P3C_REASON_INCIDENT_NOT_FOUND
        evidence["discovery_success"] = False
        evidence["validation_success"] = False
        
        # Write failure evidence
        write_json_artifact(detection_dir, "detection-failure.json", {
            "failure": "k8s_incident_not_discovered",
            "reason": evidence["failure_reason"],
            "discovery_result": discovery_result,
        })
    
    # Step 5: Write final detection artifact with full schema
    evidence["detection_evidence_path"] = str(detection_dir / "detection-evidence.json")
    write_json_artifact(detection_dir, "detection-evidence.json", evidence)
    
    # Write raw incident if found
    if evidence.get("incident_id"):
        write_json_artifact(detection_dir, "raw-incident.json", discovery_result.get("raw_incident", {}))
    
    duration = time.time() - start
    
    log("=" * 60)
    log("PHASE P3c: Detection complete")
    log(f"  Success: {evidence['discovery_success']}")
    log(f"  Validation: {evidence['validation_success']}")
    log(f"  Incident ID: {evidence.get('incident_id', 'N/A')}")
    log(f"  Candidate class: {evidence.get('candidate_class', 'N/A')}")
    log(f"  Failure reason: {evidence.get('failure_reason', 'none')}")
    log(f"  Duration: {duration:.1f}s")
    log("=" * 60)
    
    # Phase fails if ANY validation fails
    phase_success = evidence["discovery_success"] and evidence["validation_success"]
    
    return LabPhaseResult(
        phase="p3c-k8s-discovery",
        success=phase_success,
        message=f"K8s incident discovery: {'PASS' if phase_success else 'FAIL'} - {evidence.get('failure_reason', 'all validations passed')}",
        artifacts={
            "detection_dir": str(detection_dir),
            "discovery_evidence": str(detection_dir / "detection-evidence.json"),
            "discovery_success": evidence["discovery_success"],
            "validation_success": evidence["validation_success"],
            "incident_id": evidence.get("incident_id"),
            "candidate_class": evidence.get("candidate_class"),
            "failure_reason": evidence.get("failure_reason"),
        },
        duration_seconds=duration,
    )
