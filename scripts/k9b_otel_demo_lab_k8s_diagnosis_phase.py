#!/usr/bin/env python3
"""Kubernetes diagnosis phase facade for the OTel demo lab.

This module is a thin facade that orchestrates the K8s multi-pass
diagnosis phase by delegating to focused sibling modules:

- k9b_otel_demo_lab_k8s_diagnosis_phase_artifacts: Artifact I/O helpers
- k9b_otel_demo_lab_k8s_diagnosis_phase_checks: Preflight checks and validation
- k9b_otel_demo_lab_k8s_diagnosis_phase_p4c: P4c diagnosis-loop execution

This preserves import compatibility for existing callers while
keeping each module focused and LLM-friendly.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_artifacts import (
    get_diagnosis_dir,
    write_diagnosis_evidence,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_PASSES,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_contract import create_initial_evidence
from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import (
    _check_root_cause_terms,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_checks import (
    check_live_lab_and_log,
    load_detection_evidence,
    validate_and_extract,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_failures import (
    _collect_failures,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c import (
    build_phase_result,
    compute_p4c_outcome_for_phase,
    extract_scheduling_evidence_p4c,
    merge_diagnosis_result,
    validate_p4c_root_cause,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_config import (
    DEFAULT_K9B_NAMESPACE,
)

# Backward compatibility alias for tests and downstream contracts that import
# _merge_diagnosis_result from the facade. The function lives in the p4c module
# but must remain importable from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase
# to preserve the facade contract.
_merge_diagnosis_result = merge_diagnosis_result
from scripts.k9b_otel_demo_lab_k8s_diagnosis_render import (
    log as _log,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_render import (
    log_diagnosis_result,
    log_phase_footer,
    log_step,
    log_term_check,
    log_validation_result,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import (
    run_diagnosis_loop,
)
from scripts.k9b_otel_demo_lab_p4c_forensic_dump import (
    FORENSIC_DUMP_ENABLED,
    dump_backend_incident_detail_before_loop,
    dump_backend_runtime_provenance,
    dump_p4c_outcome_input,
    dump_p4c_runtime_provenance,
)
from scripts.k9b_otel_demo_lab_p4c_forensic_dump_evidence import (
    write_forensic_summary,
)
from scripts.k9b_otel_demo_lab_types import LabConfig, LabPhaseResult

__all__ = [
    "phase_p4c_verify_k8s_mult_pass_diagnosis",
    "create_initial_evidence",
    "get_diagnosis_dir",
    "write_diagnosis_evidence",
    "run_diagnosis_loop",
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
    
    # FRESHNESS GUARD: Print tested revision before P4c starts
    freshness_result, is_fresh = check_live_lab_and_log(config, artifact_dir)
    evidence = create_initial_evidence(config.namespace)
    
    # Record freshness check in evidence
    evidence["freshness_check"] = freshness_result
    
    if not is_fresh:
        # Fail early - stale code detected
        _log("FATAL: Live-lab freshness check failed - running stale code")
        for err in freshness_result.get("errors", []):
            _log(f"  - {err}")
        evidence["failure_reason"] = "stale_live_lab_code"
        evidence["validation_success"] = False
        write_diagnosis_evidence(diagnosis_dir, evidence)
        return build_phase_result(evidence, start, diagnosis_dir, success=False)
    
    # FORENSIC DUMP: Capture backend and p4c runtime provenance at phase start
    provenance: dict[str, Any] = {}
    if FORENSIC_DUMP_ENABLED:
        _log("  [FORENSIC] Starting P4c forensic dump")
        provenance["backend"] = dump_backend_runtime_provenance(
            artifact_dir, kubeconfig=config.kubeconfig
        )
        provenance["p4c_script"] = dump_p4c_runtime_provenance(artifact_dir)
    
    # Step 1: Read P3c detection evidence
    log_step(1, "Reading P3c detection evidence")
    detection_evidence = load_detection_evidence(artifact_dir, detection_artifacts, evidence)
    if detection_evidence is None:
        write_diagnosis_evidence(diagnosis_dir, evidence)
        return build_phase_result(evidence, start, diagnosis_dir, success=False)
    
    # Store detection_evidence in evidence dict so scheduling extraction can access it
    evidence["detection_evidence"] = detection_evidence
    
    # Step 2: Validate P3c evidence
    log_step(2, "Validating P3c evidence")
    incident_id, candidate_class = validate_and_extract(detection_evidence, evidence, diagnosis_dir)
    if incident_id is None:
        return build_phase_result(evidence, start, diagnosis_dir, success=False)
    
    _log(f"  Valid P3c evidence: incident_id={incident_id}, candidate_class={candidate_class}")
    
    # Step 3: Trigger diagnosis loop
    log_step(3, "Triggering k9b automatic diagnosis loop")
    evidence["diagnosis_started"] = time.time()
    
    # Use k9b backend namespace for backend-targeted diagnosis, not the incident namespace.
    # The backend runs in k9b namespace, but incidents may be in otel-demo namespace.
    # kubectl exec against deploy/k9b-backend must use -n k9b to find the deployment.
    # NOTE: This uses run_diagnosis_loop directly so that tests can patch at the facade level.
    external_analysis_dir = artifact_dir / "external-analysis"
    external_analysis_dir.mkdir(parents=True, exist_ok=True)
    
    diagnosis_result = run_diagnosis_loop(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
        max_passes=DEFAULT_MAX_PASSES,
        max_checks_per_pass=DEFAULT_MAX_CHECKS_PER_PASS,
        kubeconfig=config.kubeconfig,
        namespace=DEFAULT_K9B_NAMESPACE,
        artifact_dir=artifact_dir,
    )
    
    evidence = merge_diagnosis_result(evidence, diagnosis_result)
    
    # FORENSIC DUMP: Dump backend incident detail after diagnosis loop
    if FORENSIC_DUMP_ENABLED and evidence.get("backend_incident_detail"):
        dump_backend_incident_detail_before_loop(
            artifact_dir,
            evidence.get("backend_incident_detail"),
            incident_id,
        )
    
    # Step 3b: Fail immediately if real loop was not invoked
    # This is the most common P4c failure - the diagnosis loop never ran.
    # Fail fast with a clear message instead of cascading through term checks.
    if not evidence.get("real_loop_invoked", False):
        failure_reason = evidence.get("failure_reason") or "automatic_diagnosis_loop_disabled"
        evidence["failure_reason"] = failure_reason
        evidence["validation_success"] = False
        write_diagnosis_evidence(diagnosis_dir, evidence)
        log_step(3, "Validating k9b automatic diagnosis loop invocation")
        _log(f"  FATAL: {failure_reason}")
        duration = time.time() - start
        log_phase_footer(duration)
        return build_phase_result(evidence, start, diagnosis_dir, success=False, term_checks={})
    
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
    
    # Step 6: Extract structured scheduling_evidence (must come before Step 6b validation)
    log_step(6, "Extracting structured scheduling evidence (P4c)")
    evidence = extract_scheduling_evidence_p4c(detection_evidence, evidence)
    
    # Step 6b: P4c root-cause validation - check scheduling markers using extracted evidence
    log_step("6b", "Validating scheduling root-cause evidence (P4c)")
    evidence = validate_p4c_root_cause(evidence)
    
    # Step 7: Compute normalized P4c outcome
    # FORENSIC DUMP: Dump raw P4c outcome input immediately before compute_p4c_outcome
    if FORENSIC_DUMP_ENABLED:
        provenance["p4c_input"] = dump_p4c_outcome_input(
            artifact_dir, evidence, incident_id,
        )
        provenance["scheduling_evidence"] = evidence.get("scheduling_evidence")
        provenance["detection_evidence_summary"] = {
            "matching_signals_count": len(detection_evidence.get("matching_signals", [])),
            "has_scheduling_evidence": "scheduling_evidence" in evidence,
        }
        write_forensic_summary(
            artifact_dir, incident_id, None,
            ["backend", "p4c_script", "p4c_input"], provenance,
        )
    
    p4c_outcome, evidence = compute_p4c_outcome_for_phase(evidence)

    write_diagnosis_evidence(diagnosis_dir, evidence)
    duration = time.time() - start
    log_diagnosis_result(evidence["validation_success"], evidence, term_checks)
    log_phase_footer(duration)

    return build_phase_result(
        evidence, start, diagnosis_dir, success=evidence["validation_success"], term_checks=term_checks
    )
