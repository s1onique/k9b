#!/usr/bin/env python3
"""Main diagnosis phase for K8s multi-pass incident diagnosis.

This module contains the P4c phase function that:
1. Reads P3c detection evidence
2. Triggers automatic diagnosis loop with multi-pass requirement
3. Validates diagnosis contains root-cause terms
4. Writes diagnosis evidence artifact
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
    PHASE_DIAGNOSIS,
    SHIPPING_DEPLOYMENT,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    ARTIFACT_DIR,
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_PASSES,
    DIAGNOSIS_SOURCE_REAL,
    DIAGNOSIS_SOURCE_SIMULATED,
    FAILURE_REASON_LOOP_DISABLED,
    FAILURE_REASON_LOOP_ERROR,
    FAILURE_REASON_LOOP_IMPORT_FAILED,
    FAILURE_REASON_PASS_ARTIFACTS_MISSING,
    MIN_REQUIRED_PASSES,
    PHASE_NAME,
    SIMULATION_ENV_VAR,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import (
    _check_read_only_contract,
    _check_root_cause_terms,
    _validate_discovery_evidence,
)
from scripts.k9b_otel_demo_lab_types import LabConfig, LabPhaseResult


def phase_p4c_verify_k8s_mult_pass_diagnosis(
    config: LabConfig,
    artifact_dir: Path,
    detection_artifacts: dict[str, Any] | None = None,
) -> LabPhaseResult:
    """Phase P4c: Multi-pass automatic diagnosis for K8s incident.
    
    After P3c discovery succeeds, this phase:
    1. Reads P3c detection evidence
    2. Triggers k9b automatic diagnosis loop
    3. Requires at least 2 diagnosis passes
    4. Validates root-cause terms in final diagnosis
    5. Writes diagnosis evidence artifact
    
    Phase success requires ALL of:
    - P3c evidence is valid and present
    - Incident ID is available
    - Diagnosis loop ran with >= 2 passes
    - Final diagnosis contains required root-cause terms:
      - shipping
      - nodeSelector or scheduling constraint
      - k9b.dev/otel-lab-node
      - missing / unschedulable / no matching node
    
    Args:
        config: Lab configuration
        artifact_dir: Directory for phase artifacts
        detection_artifacts: Optional dict of P3c detection artifacts
        
    Returns:
        LabPhaseResult with diagnosis outcome and artifacts
    """
    start = time.time()
    phase_dir = artifact_dir / PHASE_DIAGNOSIS
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    diagnosis_dir = phase_dir / ARTIFACT_DIR
    diagnosis_dir.mkdir(parents=True, exist_ok=True)
    
    log("=" * 60)
    log("PHASE P4c: Multi-pass K8s incident diagnosis")
    log("=" * 60)
    log(f"Target: diagnose shipping incident in {config.namespace}")
    
    # Initialize evidence with full schema including metadata fields
    evidence: dict[str, Any] = {
        # Identification
        "phase": PHASE_NAME,
        "scenario": "unschedulable-shipping-rollout",
        "target_deployment": SHIPPING_DEPLOYMENT,
        "target_namespace": config.namespace,
        "timestamp": time.time(),
        # Diagnosis source metadata (required by verifier)
        "diagnosis_source": DIAGNOSIS_SOURCE_REAL,
        "simulation_used": False,
        "automatic_loop_enabled": False,
        "real_loop_invoked": False,
        "real_pass_artifacts_found": False,
        "pass_artifact_paths": [],
        "provider_invocation_attempted": False,
        "review_packet_found": False,
        "diagnosis_loop_module": None,
        # Loop status
        "loop_status": None,
        # Pass tracking
        "pass_count": 0,
        "pass_run_ids": [],
        "min_required_passes": MIN_REQUIRED_PASSES,
        # Safety contract
        "read_only": True,
        "read_only_violations": [],
        "allowed_actions": [],
        "requested_checks": [],
        "executed_checks": [],
        # Diagnosis output
        "diagnosis_started": None,
        "diagnosis_completed": None,
        "loop_status_detail": None,
        "root_cause_summary": "",
        "root_cause_matches": {},
        # Root-cause term checks
        "mentions_shipping": False,
        "mentions_node_selector": False,
        "mentions_selector_key": False,
        "mentions_selector_value": False,
        "mentions_no_matching_node": False,
        # Validation state
        "validation_success": False,
        "failure_reason": None,
        # Paths
        "detection_evidence_path": None,
        "raw_diagnosis_artifact_path": None,
        "review_packet_path": None,
    }
    
    # Step 1: Read P3c detection evidence
    log("Step 1: Reading P3c detection evidence...")
    detection_evidence_path = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery" / "detection-evidence.json"
    
    if detection_evidence_path.exists():
        detection_evidence = json.loads(detection_evidence_path.read_text())
        evidence["detection_evidence_path"] = str(detection_evidence_path)
        log(f"  Loaded detection evidence from {detection_evidence_path}")
    elif detection_artifacts:
        detection_evidence = detection_artifacts
        evidence["detection_evidence_path"] = "provided_via_artifacts"
        log("  Using provided detection artifacts")
    else:
        log("ERROR: No P3c detection evidence found - fail-closed")
        evidence["failure_reason"] = "p3c_evidence_missing"
        evidence["loop_status"] = "skipped"
        _write_diagnosis_artifact(diagnosis_dir, evidence)
        return _build_failure_result(evidence, start, diagnosis_dir)
    
    # Step 2: Validate P3c evidence
    log("Step 2: Validating P3c evidence...")
    is_valid, error_msg = _validate_discovery_evidence(detection_evidence)
    
    if not is_valid:
        log(f"ERROR: P3c evidence validation failed: {error_msg}")
        evidence["failure_reason"] = error_msg
        evidence["loop_status"] = "skipped"
        _write_diagnosis_artifact(diagnosis_dir, evidence)
        return _build_failure_result(evidence, start, diagnosis_dir)
    
    # Extract incident info from P3c
    incident_id = detection_evidence.get("incident_id")
    candidate_class = detection_evidence.get("candidate_class")
    
    evidence["incident_id"] = incident_id
    evidence["candidate_class"] = candidate_class
    
    log(f"  Valid P3c evidence: incident_id={incident_id}, candidate_class={candidate_class}")
    
    # Step 3: Trigger automatic diagnosis loop
    log("Step 3: Triggering k9b automatic diagnosis loop...")
    evidence["diagnosis_started"] = time.time()
    
    # Get external analysis directory from config or artifact_dir
    external_analysis_dir = artifact_dir / "external-analysis"
    external_analysis_dir.mkdir(parents=True, exist_ok=True)
    
    # Run the automatic diagnosis loop
    diagnosis_result = _run_diagnosis_loop(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
        max_passes=DEFAULT_MAX_PASSES,
        max_checks_per_pass=DEFAULT_MAX_CHECKS_PER_PASS,
    )
    
    evidence["diagnosis_completed"] = time.time()
    evidence["loop_status"] = diagnosis_result.get("status", "unknown")
    evidence["loop_status_detail"] = diagnosis_result
    
    # Propagate real-loop metadata from diagnosis_result into evidence
    evidence["diagnosis_source"] = diagnosis_result.get("diagnosis_source", DIAGNOSIS_SOURCE_REAL)
    evidence["simulation_used"] = diagnosis_result.get("simulation_used", False)
    evidence["automatic_loop_enabled"] = diagnosis_result.get("automatic_loop_enabled", False)
    evidence["real_loop_invoked"] = diagnosis_result.get("real_loop_invoked", False)
    evidence["real_pass_artifacts_found"] = diagnosis_result.get("real_pass_artifacts_found", False)
    evidence["pass_artifact_paths"] = diagnosis_result.get("pass_artifact_paths", [])
    evidence["provider_invocation_attempted"] = diagnosis_result.get("provider_invocation_attempted", False)
    evidence["review_packet_found"] = diagnosis_result.get("review_packet_found", False)
    evidence["diagnosis_loop_module"] = diagnosis_result.get("diagnosis_loop_module")
    
    # Extract pass information
    evidence["pass_count"] = diagnosis_result.get("pass_count", 0)
    evidence["pass_run_ids"] = diagnosis_result.get("pass_run_ids", [])
    evidence["requested_checks"] = diagnosis_result.get("requested_checks", [])
    evidence["executed_checks"] = diagnosis_result.get("executed_checks", [])
    
    # Extract root-cause summary if available
    root_cause_summary = diagnosis_result.get("root_cause_summary", "")
    evidence["root_cause_summary"] = root_cause_summary
    
    # Extract artifact paths
    evidence["raw_diagnosis_artifact_path"] = diagnosis_result.get("artifact_path")
    evidence["review_packet_path"] = diagnosis_result.get("review_packet_path")
    
    # Propagate failure reason if present
    if diagnosis_result.get("failure_reason"):
        evidence["failure_reason"] = diagnosis_result.get("failure_reason")
    
    # Step 4: Check root-cause term matches
    log("Step 4: Checking root-cause terms in diagnosis...")
    term_checks = _check_root_cause_terms(root_cause_summary)
    evidence["root_cause_matches"] = term_checks
    evidence.update(term_checks)
    
    for term, found in term_checks.items():
        log(f"  {term}: {'FOUND' if found else 'MISSING'}")
    
    # Step 5: Validate overall success (must match verifier criteria)
    log("Step 5: Validating diagnosis success criteria...")
    
    failures: list[str] = []
    
    # Check real loop requirements (required by verifier)
    if evidence["simulation_used"]:
        failures.append("simulation_used_but_not_allowed")
    
    if not evidence["real_loop_invoked"]:
        failures.append("real_loop_not_invoked")
    
    if not evidence["real_pass_artifacts_found"]:
        failures.append("real_pass_artifacts_missing")
    
    # Check pass count
    if evidence["pass_count"] < MIN_REQUIRED_PASSES:
        failures.append(f"insufficient_passes: {evidence['pass_count']} < {MIN_REQUIRED_PASSES}")
    
    # Check read-only contract
    executed_checks = evidence.get("executed_checks", [])
    is_read_only, read_only_violations = _check_read_only_contract(executed_checks)
    evidence["read_only"] = is_read_only
    evidence["read_only_violations"] = read_only_violations
    
    if not is_read_only:
        failures.append(f"read_only_contract_violated: {read_only_violations}")
    
    # Check root-cause terms
    for term, found in term_checks.items():
        if not found:
            failures.append(f"missing_root_cause_term: {term}")
    
    all_validations_passed = len(failures) == 0
    evidence["validation_success"] = all_validations_passed
    
    if all_validations_passed:
        log("Validation PASSED: diagnosis meets all success criteria")
    else:
        evidence["failure_reason"] = "; ".join(failures)
        log(f"Validation FAILED: {evidence['failure_reason']}")
    
    # Write final diagnosis artifact
    _write_diagnosis_artifact(diagnosis_dir, evidence)
    
    duration = time.time() - start
    
    log("=" * 60)
    log("PHASE P4c: Diagnosis complete")
    log(f"  Success: {evidence['validation_success']}")
    log(f"  Incident ID: {incident_id}")
    log(f"  Pass count: {evidence['pass_count']}")
    log(f"  Pass run IDs: {evidence['pass_run_ids']}")
    log(f"  Root cause matches: {term_checks}")
    log(f"  Failure reason: {evidence.get('failure_reason', 'none')}")
    log(f"  Duration: {duration:.1f}s")
    log("=" * 60)
    
    return LabPhaseResult(
        phase=PHASE_NAME,
        success=evidence["validation_success"],
        message=f"Multi-pass diagnosis: {'PASS' if evidence['validation_success'] else 'FAIL'} - {evidence.get('failure_reason', 'all validations passed')}",
        artifacts={
            "diagnosis_dir": str(diagnosis_dir),
            "diagnosis_evidence": str(diagnosis_dir / "diagnosis-evidence.json"),
            "validation_success": evidence["validation_success"],
            "pass_count": evidence["pass_count"],
            "pass_run_ids": evidence["pass_run_ids"],
            "root_cause_matches": term_checks,
            "incident_id": incident_id,
            "failure_reason": evidence.get("failure_reason"),
        },
        duration_seconds=duration,
    )


def _run_diagnosis_loop(
    incident_id: str,
    external_analysis_dir: Path,
    max_passes: int = DEFAULT_MAX_PASSES,
    max_checks_per_pass: int = DEFAULT_MAX_CHECKS_PER_PASS,
    allow_simulation: bool = False,
) -> dict[str, Any]:
    """Run the automatic diagnosis loop for an incident.
    
    This function triggers the k9b automatic diagnosis loop and collects
    multi-pass diagnostic information. By default, it FAILS CLOSED if
    the real loop is unavailable. Simulation is only allowed when
    explicitly enabled via allow_simulation=True.
    
    Args:
        incident_id: The incident ID to diagnose
        external_analysis_dir: Directory for diagnosis artifacts
        max_passes: Maximum passes to allow
        max_checks_per_pass: Maximum checks per pass
        allow_simulation: If True, allow simulation fallback for testing.
                          NEVER set this in production/live-lab.
        
    Returns:
        Dict with diagnosis loop results. On failure, includes
        `diagnosis_source`, `failure_reason`, `simulation_used`.
    """
    import os
    
    result: dict[str, Any] = {
        "diagnosis_source": DIAGNOSIS_SOURCE_REAL,
        "simulation_used": False,
        "automatic_loop_enabled": False,
        "real_loop_invoked": False,
        "real_pass_artifacts_found": False,
        "pass_artifact_paths": [],
        "provider_invocation_attempted": False,
        "review_packet_found": False,
        "diagnosis_loop_module": None,
        "status": "unknown",
        "incident_id": incident_id,
        "pass_count": 0,
        "pass_run_ids": [],
        "requested_checks": [],
        "executed_checks": [],
        "root_cause_summary": "",
        "artifact_path": None,
        "review_packet_path": None,
        "failure_reason": None,
    }
    
    # Check for simulation env var (test-only override)
    simulation_env = os.environ.get(SIMULATION_ENV_VAR, "").lower()
    if simulation_env == "true":
        log(f"  NOTE: {SIMULATION_ENV_VAR}=true (TEST MODE ONLY)")
        allow_simulation = True
    
    try:
        # Import the automatic diagnosis loop module
        # Use lazy import to avoid circular dependencies
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
            collect_automatic_diagnosis_evidence,
            is_automatic_diagnosis_loop_enabled,
        )
        
        result["diagnosis_loop_module"] = "k8s_diag_agent.collect.incident_diagnosis_auto_loop"
        result["automatic_loop_enabled"] = is_automatic_diagnosis_loop_enabled()
        
        # Check if automatic diagnosis is enabled - FAIL CLOSED
        if not result["automatic_loop_enabled"]:
            log("  ERROR: K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED not set")
            result["failure_reason"] = FAILURE_REASON_LOOP_DISABLED
            result["status"] = "disabled"
            
            # Only use simulation if explicitly allowed (test-only)
            if allow_simulation:
                log("  NOTE: allow_simulation=True - using simulation (TEST ONLY)")
                return _simulate_diagnosis_loop(
                    incident_id,
                    external_analysis_dir,
                    max_passes,
                )
            return result
        
        # Real loop is enabled - invoke it
        result["real_loop_invoked"] = True
        log("  Invoking k9b automatic diagnosis loop...")
        
        # Collect evidence for this incident
        incident_result = collect_automatic_diagnosis_evidence(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
        )
        
        result["provider_invocation_attempted"] = True
        result["status"] = "completed" if incident_result.eligible else "ineligible"
        
        if incident_result.eligible:
            result["pass_count"] = 1
            result["pass_run_ids"] = [incident_result.run_id] if incident_result.run_id else []
            result["executed_checks"] = [incident_result.checks_run] if incident_result.checks_run else []
        
        # Check for review packet
        if incident_result.review_packet_name:
            review_path = external_analysis_dir / "diagnosis-review" / incident_result.review_packet_name
            result["review_packet_path"] = str(review_path)
            result["review_packet_found"] = review_path.exists()
            
            # Try to load the diagnosis summary from the review packet
            if result["review_packet_found"]:
                try:
                    review_data = json.loads(review_path.read_text())
                    result["root_cause_summary"] = _extract_root_cause_from_review(review_data)
                except (json.JSONDecodeError, OSError):
                    pass
        
        # Count real pass artifacts by reading JSON and filtering by incident_id
        pass_artifacts_dir = external_analysis_dir / "diagnosis-loop-passes"
        if pass_artifacts_dir.exists():
            pass_artifact_paths: list[Path] = []
            pass_run_ids: list[str] = []
            
            for pass_file in pass_artifacts_dir.glob("*.json"):
                try:
                    pass_data = json.loads(pass_file.read_text())
                    # Filter by incident_id in the JSON content
                    if pass_data.get("incident_id") == incident_id:
                        pass_artifact_paths.append(pass_file)
                        run_id = pass_data.get("run_id")
                        if run_id:
                            pass_run_ids.append(run_id)
                except (json.JSONDecodeError, OSError):
                    continue
            
            result["pass_artifact_paths"] = [str(p) for p in pass_artifact_paths]
            result["real_pass_artifacts_found"] = len(pass_artifact_paths) > 0
            result["pass_count"] = len(pass_artifact_paths)
            result["pass_run_ids"] = pass_run_ids
            result["artifact_path"] = str(pass_artifacts_dir)
        
        # Check if pass artifacts were found - FAIL CLOSED if missing
        if not result["real_pass_artifacts_found"] and result["pass_count"] < MIN_REQUIRED_PASSES:
            result["failure_reason"] = FAILURE_REASON_PASS_ARTIFACTS_MISSING
            log(f"  ERROR: No diagnosis pass artifacts found for incident {incident_id}")
            return result
        
        log(f"  Real diagnosis loop completed: {result['pass_count']} passes found")
        return result
        
    except ImportError as e:
        log(f"  ERROR: Import error - {e}")
        result["failure_reason"] = FAILURE_REASON_LOOP_IMPORT_FAILED
        result["status"] = f"import_error: {e}"
        
        # Only use simulation if explicitly allowed (test-only)
        if allow_simulation:
            log("  NOTE: allow_simulation=True - using simulation (TEST ONLY)")
            return _simulate_diagnosis_loop(
                incident_id,
                external_analysis_dir,
                max_passes,
            )
        return result
        
    except Exception as e:
        log(f"  ERROR: Diagnosis loop error - {e}")
        result["failure_reason"] = FAILURE_REASON_LOOP_ERROR
        result["status"] = f"error: {e}"
        
        # Only use simulation if explicitly allowed (test-only)
        if allow_simulation:
            log("  NOTE: allow_simulation=True - using simulation (TEST ONLY)")
            return _simulate_diagnosis_loop(
                incident_id,
                external_analysis_dir,
                max_passes,
            )
        return result


def _simulate_diagnosis_loop(
    incident_id: str,
    external_analysis_dir: Path,
    max_passes: int,
) -> dict[str, Any]:
    """Simulate multi-pass diagnosis loop for lab verification.
    
    This function provides a simulated diagnosis loop that:
    1. Runs exactly 2 passes (meeting minimum requirement)
    2. Provides realistic root-cause summary
    3. Includes read-only check evidence
    
    IMPORTANT: This function is for TESTING ONLY. It returns
    simulation metadata so the verifier can reject it.
    
    Args:
        incident_id: The incident ID being diagnosed
        external_analysis_dir: Directory for diagnosis artifacts
        max_passes: Maximum passes to allow
        
    Returns:
        Simulated diagnosis result with simulation metadata
    """
    from datetime import UTC, datetime
    
    log("  Running simulated diagnosis loop (2 passes) - TEST ONLY")
    
    # Simulate pass 1: Initial diagnosis with partial evidence
    pass1_run_id = f"sim-{incident_id[:8]}-pass1"
    pass1_time = datetime.now(UTC).isoformat()
    
    # Simulate pass 2: Follow-up with full evidence
    pass2_run_id = f"sim-{incident_id[:8]}-pass2"
    pass2_time = datetime.now(UTC).isoformat()
    
    # Create simulated loop pass artifacts
    loop_passes_dir = external_analysis_dir / "diagnosis-loop-passes"
    loop_passes_dir.mkdir(parents=True, exist_ok=True)
    
    pass1_artifact = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "run_id": pass1_run_id,
        "timestamp": pass1_time,
        "pass_number": 1,
        "decision": "run_allowed_read_only_checks",
        "checks_requested": 3,
        "checks_run": 3,
        "read_only": True,
    }
    
    pass2_artifact = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "run_id": pass2_run_id,
        "timestamp": pass2_time,
        "pass_number": 2,
        "decision": "stop_root_cause_found",
        "checks_requested": 2,
        "checks_run": 2,
        "read_only": True,
    }
    
    # Write pass artifacts
    (loop_passes_dir / f"{pass1_run_id}.json").write_text(json.dumps(pass1_artifact, indent=2))
    (loop_passes_dir / f"{pass2_run_id}.json").write_text(json.dumps(pass2_artifact, indent=2))
    
    # Simulated root-cause summary matching the expected root cause
    root_cause_summary = (
        f"Root cause identified: The {SHIPPING_DEPLOYMENT} Deployment "
        f"has an impossible nodeSelector requiring label "
        f"'{K8S_INJECTION_NODE_SELECTOR_KEY}={K8S_INJECTION_NODE_SELECTOR_VALUE}'. "
        f"No node in the cluster has this label, causing the shipping-* Pod "
        f"to remain in Pending state with status 'unschedulable'. "
        f"The nodeSelector prevents scheduling because there is no matching node."
    )
    
    # Create simulated review packet
    review_dir = external_analysis_dir / "diagnosis-review"
    review_dir.mkdir(parents=True, exist_ok=True)
    
    review_artifact = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "collector_run_id": f"sim-collector-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now(UTC).isoformat(),
        "root_cause_summary": root_cause_summary,
        "diagnosis_conclusion": {
            "component": SHIPPING_DEPLOYMENT,
            "issue": "unschedulable_pod",
            "root_cause": f"impossible nodeSelector: {K8S_INJECTION_NODE_SELECTOR_KEY}={K8S_INJECTION_NODE_SELECTOR_VALUE}",
            "evidence": [
                "PendingPod for shipping-* with reason Unschedulable",
                "FailedScheduling event indicating no matching node",
                f"nodeSelector: {K8S_INJECTION_NODE_SELECTOR_KEY}: {K8S_INJECTION_NODE_SELECTOR_VALUE}",
                "No nodes with required label exist in cluster",
            ],
        },
        "read_only": True,
        "allowed_actions": [],
    }
    
    review_filename = f"review-{incident_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
    (review_dir / review_filename).write_text(json.dumps(review_artifact, indent=2))
    
    # Return result with simulation metadata for verifier to detect
    return {
        # Simulation metadata - used by verifier to reject
        "diagnosis_source": DIAGNOSIS_SOURCE_SIMULATED,
        "simulation_used": True,
        "automatic_loop_enabled": False,
        "real_loop_invoked": False,
        "real_pass_artifacts_found": False,
        "pass_artifact_paths": [],
        "provider_invocation_attempted": False,
        "review_packet_found": True,
        "diagnosis_loop_module": None,
        "failure_reason": None,
        # Diagnosis results
        "status": "completed",
        "incident_id": incident_id,
        "pass_count": 2,
        "pass_run_ids": [pass1_run_id, pass2_run_id],
        "requested_checks": [
            "kubectl_get_deployment_shipping",
            "kubectl_get_pods",
            "kubectl_get_events",
            "kubectl_get_nodes",
        ],
        "executed_checks": [
            "kubectl_get_deployment_shipping",
            "kubectl_get_pods",
            "kubectl_get_events",
            "kubectl_get_nodes",
        ],
        "root_cause_summary": root_cause_summary,
        "artifact_path": str(loop_passes_dir),
        "review_packet_path": str(review_dir / review_filename),
    }


def _extract_root_cause_from_review(review_data: dict[str, Any]) -> str:
    """Extract root cause summary from diagnosis review packet.
    
    Args:
        review_data: Review packet data
        
    Returns:
        Root cause summary string
    """
    # Try various paths where root cause might be stored
    if "root_cause_summary" in review_data:
        return str(review_data["root_cause_summary"])
    
    if "diagnosis_conclusion" in review_data:
        conclusion = review_data["diagnosis_conclusion"]
        if isinstance(conclusion, dict):
            return str(conclusion.get("summary", str(conclusion)))
    
    if "summary" in review_data:
        return str(review_data["summary"])
    
    return str(review_data)


def _write_diagnosis_artifact(diagnosis_dir: Path, evidence: dict[str, Any]) -> None:
    """Write diagnosis evidence artifact.
    
    Args:
        diagnosis_dir: Directory to write artifact
        evidence: Evidence dict to write
    """
    artifact_path = diagnosis_dir / "diagnosis-evidence.json"
    write_json_artifact(diagnosis_dir, "diagnosis-evidence.json", evidence)
    log(f"  Wrote diagnosis evidence to {artifact_path}")


def _build_failure_result(
    evidence: dict[str, Any],
    start_time: float,
    diagnosis_dir: Path,
) -> LabPhaseResult:
    """Build a failure result for phase.
    
    Args:
        evidence: Evidence dict with failure info
        start_time: Phase start time
        diagnosis_dir: Directory with artifacts
        
    Returns:
        LabPhaseResult indicating failure
    """
    duration = time.time() - start_time
    
    return LabPhaseResult(
        phase=PHASE_NAME,
        success=False,
        message=f"Multi-pass diagnosis: FAIL - {evidence.get('failure_reason', 'unknown failure')}",
        artifacts={
            "diagnosis_dir": str(diagnosis_dir),
            "diagnosis_evidence": str(diagnosis_dir / "diagnosis-evidence.json"),
            "validation_success": False,
            "pass_count": evidence.get("pass_count", 0),
            "failure_reason": evidence.get("failure_reason"),
        },
        duration_seconds=duration,
    )
