#!/usr/bin/env python3
"""Kubernetes diagnosis phase facade for the OTel demo lab.

This module is a thin facade that orchestrates the K8s multi-pass
diagnosis phase by delegating to focused sibling modules:

- diagnosis_contract: Evidence schema and factory functions
- diagnosis_runner: Diagnosis loop execution
- diagnosis_artifacts: Artifact I/O helpers
- diagnosis_render: UI rendering and logging

This preserves import compatibility for existing callers while
keeping each module focused and LLM-friendly.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_artifacts import (
    get_diagnosis_dir,
    get_p3c_evidence_path,
    write_diagnosis_evidence,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_PASSES,
    DIAGNOSIS_SOURCE_REAL,
    MIN_REQUIRED_PASSES,
    PHASE_NAME,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_contract import create_initial_evidence
from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import (
    _check_read_only_contract,
    _check_root_cause_terms,
    _validate_discovery_evidence,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_render import (
    log as _log,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_render import (
    log_diagnosis_result,
    log_phase_footer,
    log_phase_header,
    log_step,
    log_term_check,
    log_validation_result,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import run_diagnosis_loop
from scripts.k9b_otel_demo_lab_types import LabConfig, LabPhaseResult

__all__ = [
    "phase_p4c_verify_k8s_mult_pass_diagnosis",
    "create_initial_evidence",
    "run_diagnosis_loop",
    "write_diagnosis_evidence",
    "get_diagnosis_dir",
]


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
    """
    start = time.time()
    diagnosis_dir = get_diagnosis_dir(artifact_dir)
    
    log_phase_header()
    _log(f"Target: diagnose shipping incident in {config.namespace}")
    evidence = create_initial_evidence(config.namespace)
    
    # Step 1: Read P3c detection evidence
    log_step(1, "Reading P3c detection evidence")
    detection_evidence = _load_detection_evidence(artifact_dir, detection_artifacts, evidence)
    if detection_evidence is None:
        write_diagnosis_evidence(diagnosis_dir, evidence)
        return _build_result(evidence, start, diagnosis_dir, success=False)
    
    # Step 2: Validate P3c evidence
    log_step(2, "Validating P3c evidence")
    incident_id, candidate_class = _validate_and_extract(detection_evidence, evidence, diagnosis_dir)
    if incident_id is None:
        return _build_result(evidence, start, diagnosis_dir, success=False)
    
    _log(f"  Valid P3c evidence: incident_id={incident_id}, candidate_class={candidate_class}")
    
    # Step 3: Trigger diagnosis loop
    log_step(3, "Triggering k9b automatic diagnosis loop")
    evidence["diagnosis_started"] = time.time()
    external_analysis_dir = artifact_dir / "external-analysis"
    external_analysis_dir.mkdir(parents=True, exist_ok=True)
    
    diagnosis_result = run_diagnosis_loop(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
        max_passes=DEFAULT_MAX_PASSES,
        max_checks_per_pass=DEFAULT_MAX_CHECKS_PER_PASS,
        kubeconfig=config.kubeconfig,
        namespace=config.namespace,
    )
    
    evidence = _merge_diagnosis_result(evidence, diagnosis_result)
    
    # Step 3b: Fail immediately if real loop was not invoked
    # This is the most common P4c failure - the diagnosis loop never ran.
    # Fail fast with a clear message instead of cascading through term checks.
    if not evidence.get("real_loop_invoked", False):
        # Default to automatic_diagnosis_loop_disabled when no specific reason is set
        failure_reason = evidence.get("failure_reason") or "automatic_diagnosis_loop_disabled"
        loop_check_reason = evidence.get("loop_enabled_check_reason", "")
        
        # Provide specific guidance based on the failure reason
        if failure_reason == "automatic_loop_env_rbac_denied":
            failure_msg = (
                "automatic_loop_env_rbac_denied: "
                "Cannot read k9b-scheduler deployment to verify loop config. "
                "The GitHub runner identity lacks 'get' permission on deployments.apps in namespace k9b. "
                f"Check error: {evidence.get('loop_enabled_check_error', 'N/A')}"
            )
        elif failure_reason == "automatic_loop_env_read_failed":
            failure_msg = (
                "automatic_loop_env_read_failed: "
                "Cannot read k9b-scheduler deployment (network/timeout/not found). "
                "Verify the k9b namespace and scheduler deployment exist. "
                f"Check error: {evidence.get('loop_enabled_check_error', 'N/A')}"
            )
        elif failure_reason == "automatic_diagnosis_loop_disabled":
            failure_msg = (
                "automatic_diagnosis_loop_disabled: "
                "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED must be set to true "
                "on the k9b-scheduler deployment (not backend). "
                "Ensure scheduler deployment has this env var configured."
            )
        else:
            failure_msg = (
                f"{failure_reason}: "
                "Automatic diagnosis loop was not invoked. "
                f"Check reason: {loop_check_reason or failure_reason}"
            )
        
        evidence["failure_reason"] = failure_msg
        evidence["validation_success"] = False
        write_diagnosis_evidence(diagnosis_dir, evidence)
        log_step(3, "Validating k9b automatic diagnosis loop invocation")
        _log(f"  FATAL: {failure_msg}")
        duration = time.time() - start
        log_phase_footer(duration)
        return _build_result(evidence, start, diagnosis_dir, success=False, term_checks={})
    
    # Step 4: Check root-cause terms
    log_step(4, "Checking root-cause terms in diagnosis")
    term_checks = _check_root_cause_terms(evidence["root_cause_summary"])
    evidence["root_cause_matches"] = term_checks
    evidence.update(term_checks)
    for term, found in term_checks.items():
        log_term_check(term, found)
    
    # Step 5: Validate success criteria
    log_step(5, "Validating diagnosis success criteria")
    failures = _collect_failures(evidence, term_checks)
    evidence["validation_success"] = len(failures) == 0
    
    if evidence["validation_success"]:
        log_validation_result(True, "diagnosis meets all success criteria")
    else:
        evidence["failure_reason"] = "; ".join(failures)
        log_validation_result(False, evidence["failure_reason"])
    
    # Step 6: P4c root-cause validation - check scheduling markers
    # This is the key P4c validation that distinguishes symptom-level discovery (P3c)
    # from root-cause diagnosis (P4c)
    log_step(6, "Validating scheduling root-cause evidence (P4c)")
    from scripts.k9b_otel_demo_lab_k8s_verdicts import (
        SCHEDULING_ROOT_CAUSE_MARKERS,
        validate_unschedulable_shipping_root_cause,
    )
    root_cause_verdict = validate_unschedulable_shipping_root_cause(evidence)
    evidence["p4c_verdict"] = root_cause_verdict.to_dict()
    
    if root_cause_verdict.success:
        _log(f"  P4c root-cause validation PASSED: scheduling markers found: {list(root_cause_verdict.matched_evidence)}")
    else:
        _log("  P4c root-cause validation FAILED: missing scheduling root-cause evidence")
        _log(f"  Required markers: {list(SCHEDULING_ROOT_CAUSE_MARKERS)}")
        if not evidence["failure_reason"]:
            evidence["failure_reason"] = "missing_scheduling_root_cause_evidence"
        else:
            evidence["failure_reason"] = evidence["failure_reason"] + "; missing_scheduling_root_cause_evidence"
        evidence["validation_success"] = False
    
    write_diagnosis_evidence(diagnosis_dir, evidence)
    duration = time.time() - start
    log_diagnosis_result(evidence["validation_success"], evidence, term_checks)
    log_phase_footer(duration)
    
    return _build_result(evidence, start, diagnosis_dir, success=evidence["validation_success"], term_checks=term_checks)


def _load_detection_evidence(
    artifact_dir: Path,
    detection_artifacts: dict[str, Any] | None,
    evidence: dict[str, Any],
) -> dict[str, Any] | None:
    """Load P3c detection evidence from file or artifacts."""
    path = get_p3c_evidence_path(artifact_dir)
    if path.exists():
        evidence["detection_evidence_path"] = str(path)
        _log(f"  Loaded detection evidence from {path}")
        loaded: dict[str, Any] = json.loads(path.read_text())
        return loaded
    if detection_artifacts:
        evidence["detection_evidence_path"] = "provided_via_artifacts"
        _log("  Using provided detection artifacts")
        provided: dict[str, Any] = detection_artifacts
        return provided
    _log("ERROR: No P3c detection evidence found - fail-closed")
    evidence["failure_reason"] = "p3c_evidence_missing"
    evidence["loop_status"] = "skipped"
    return None


def _validate_and_extract(
    detection_evidence: dict[str, Any],
    evidence: dict[str, Any],
    diagnosis_dir: Path,
) -> tuple[str | None, str | None]:
    """Validate P3c evidence and extract incident info."""
    is_valid, error_msg = _validate_discovery_evidence(detection_evidence)
    if not is_valid:
        _log(f"ERROR: P3c evidence validation failed: {error_msg}")
        evidence["failure_reason"] = error_msg
        evidence["loop_status"] = "skipped"
        return None, None
    
    incident_id = detection_evidence.get("incident_id")
    candidate_class = detection_evidence.get("candidate_class")
    evidence["incident_id"] = incident_id
    evidence["candidate_class"] = candidate_class
    return incident_id, candidate_class


def _merge_diagnosis_result(evidence: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Merge diagnosis loop result into evidence."""
    evidence["diagnosis_completed"] = time.time()
    evidence["loop_status"] = result.get("status", "unknown")
    evidence["loop_status_detail"] = result
    evidence["diagnosis_source"] = result.get("diagnosis_source", DIAGNOSIS_SOURCE_REAL)
    evidence["simulation_used"] = result.get("simulation_used", False)
    evidence["automatic_loop_enabled"] = result.get("automatic_loop_enabled", False)
    evidence["real_loop_invoked"] = result.get("real_loop_invoked", False)
    evidence["real_pass_artifacts_found"] = result.get("real_pass_artifacts_found", False)
    evidence["pass_artifact_paths"] = result.get("pass_artifact_paths", [])
    evidence["provider_invocation_attempted"] = result.get("provider_invocation_attempted", False)
    evidence["review_packet_found"] = result.get("review_packet_found", False)
    evidence["diagnosis_loop_module"] = result.get("diagnosis_loop_module")
    evidence["pass_count"] = result.get("pass_count", 0)
    evidence["pass_run_ids"] = result.get("pass_run_ids", [])
    evidence["requested_checks"] = result.get("requested_checks", [])
    evidence["executed_checks"] = result.get("executed_checks", [])
    evidence["root_cause_summary"] = result.get("root_cause_summary", "")
    evidence["raw_diagnosis_artifact_path"] = result.get("artifact_path")
    evidence["review_packet_path"] = result.get("review_packet_path")
    
    # Include detailed loop enabled check results for diagnostics
    if result.get("loop_enabled_check_reason"):
        evidence["loop_enabled_check_reason"] = result.get("loop_enabled_check_reason")
    if result.get("loop_enabled_check_error"):
        evidence["loop_enabled_check_error"] = result.get("loop_enabled_check_error")
    
    if result.get("failure_reason"):
        evidence["failure_reason"] = result.get("failure_reason")
    return evidence


def _collect_failures(evidence: dict[str, Any], term_checks: dict[str, bool]) -> list[str]:
    """Collect validation failure reasons."""
    failures: list[str] = []
    if evidence["simulation_used"]:
        failures.append("simulation_used_but_not_allowed")
    if not evidence["real_loop_invoked"]:
        failures.append("real_loop_not_invoked")
    if not evidence["real_pass_artifacts_found"]:
        failures.append("real_pass_artifacts_missing")
    if evidence["pass_count"] < MIN_REQUIRED_PASSES:
        failures.append(f"insufficient_passes: {evidence['pass_count']} < {MIN_REQUIRED_PASSES}")
    
    executed = evidence.get("executed_checks", [])
    is_read_only, violations = _check_read_only_contract(executed)
    evidence["read_only"] = is_read_only
    evidence["read_only_violations"] = violations
    if not is_read_only:
        failures.append(f"read_only_contract_violated: {violations}")
    
    for term, found in term_checks.items():
        if not found:
            failures.append(f"missing_root_cause_term: {term}")
    return failures


def _build_result(
    evidence: dict[str, Any],
    start_time: float,
    diagnosis_dir: Path,
    success: bool,
    term_checks: dict[str, bool] | None = None,
) -> LabPhaseResult:
    """Build phase result."""
    duration = time.time() - start_time
    # Always include key fields for failure diagnostics, even on failure
    artifacts: dict[str, Any] = {
        "diagnosis_dir": str(diagnosis_dir),
        "diagnosis_evidence": str(diagnosis_dir / "diagnosis-evidence.json"),
        "validation_success": success,
        "pass_count": evidence.get("pass_count", 0),
        "pass_run_ids": evidence.get("pass_run_ids", []),
        "root_cause_matches": term_checks or evidence.get("root_cause_matches", {}),
        "incident_id": evidence.get("incident_id"),
        "failure_reason": evidence.get("failure_reason"),
    }
    return LabPhaseResult(
        phase=PHASE_NAME,
        success=success,
        message=f"Multi-pass diagnosis: {'PASS' if success else 'FAIL'} - {evidence.get('failure_reason', 'all validations passed' if success else 'unknown failure')}",
        artifacts=artifacts,
        duration_seconds=duration,
    )
