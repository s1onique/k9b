"""Kubernetes diagnosis phase: P4c diagnosis loop execution.

This module provides P4c diagnosis-loop execution, extraction call-site wiring,
and outcome handling. Extracted to support LLM-friendly file sizes.
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contract_types import (
    normalize_p4c_outcome_for_dict,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    compute_p4c_outcome,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_PASSES,
    DIAGNOSIS_SOURCE_REAL,
    MIN_REQUIRED_PASSES,
    PHASE_NAME,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_render import (
    log as _log,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_render import (
    log_step,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import run_diagnosis_loop
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_config import (
    DEFAULT_K9B_NAMESPACE,
)
from scripts.k9b_otel_demo_lab_k8s_verdicts import (
    SCHEDULING_ROOT_CAUSE_MARKERS,
    validate_unschedulable_shipping_root_cause,
)
from scripts.k9b_otel_demo_lab_types import LabPhaseResult


def run_diagnosis_loop_for_phase(
    incident_id: str,
    artifact_dir: Path,
    kubeconfig: str | None,
) -> dict[str, Any]:
    """Run the diagnosis loop for the phase.

    Args:
        incident_id: The incident ID
        artifact_dir: Artifact directory
        kubeconfig: Path to kubeconfig

    Returns:
        Diagnosis loop result dict
    """
    external_analysis_dir = artifact_dir / "external-analysis"
    external_analysis_dir.mkdir(parents=True, exist_ok=True)

    # Use k9b backend namespace for backend-targeted diagnosis, not the incident namespace.
    # The backend runs in k9b namespace, but incidents may be in otel-demo namespace.
    # kubectl exec against deploy/k9b-backend must use -n k9b to find the deployment.
    return run_diagnosis_loop(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
        max_passes=DEFAULT_MAX_PASSES,
        max_checks_per_pass=DEFAULT_MAX_CHECKS_PER_PASS,
        kubeconfig=kubeconfig,
        namespace=DEFAULT_K9B_NAMESPACE,
        artifact_dir=artifact_dir,
    )


def _extract_selector_literal_from_failed_scheduling_signal(sig: object) -> str | None:
    """Extract selector_literal from a FailedScheduling signal.

    Parses selector constraints from FailedScheduling messages which contain
    node affinity/selector mismatch details. Supports multiple formats:

    - "node(s) didn't match Pod's node affinity/selector"
    - "node(s) didn't satisfy Pod's node affinity"
    - node affinity expressions with key=value constraints

    Args:
        sig: FailedScheduling signal (Mapping with 'message'/'reason' fields)

    Returns:
        Selector literal string (e.g., "k9b.dev/otel-lab-node=missing") or None
    """
    # Nil-safe: handle non-mapping inputs gracefully
    if not isinstance(sig, Mapping):
        return None

    message = str(sig.get("message", ""))
    reason = str(sig.get("reason", ""))

    # Check for FailedScheduling
    if reason != "FailedScheduling" and "failedscheduling" not in message.lower():
        return None

    # Extract selector key=value from common patterns in FailedScheduling messages
    # Pattern 1: "constraint key=value" or "constraint key=value, ..."
    constraint_pattern = r"\b([a-zA-Z0-9._/-]+)=([a-zA-Z0-9._-]+)\b"
    matches = re.findall(constraint_pattern, message)

    for key, value in matches:
        # Look for the specific lab label or any structured label constraint
        if "k9b.dev/otel-lab-node" in key or key.startswith("k9b.dev/"):
            return f"{key}={value}"

    # Pattern 2: nodeSelector/affinity expressions with the label
    # e.g., "pod has node selector or affinity that no node satisfies"
    if "node affinity/selector" in message.lower() or "nodeSelector" in message:
        # Try to find the label mentioned
        lab_label_match = re.search(r"([a-zA-Z0-9._/-]+\.[a-zA-Z0-9._/-]+)=([a-zA-Z0-9._-]+)", message)
        if lab_label_match:
            return f"{lab_label_match.group(1)}={lab_label_match.group(2)}"

    return None


def merge_diagnosis_result(evidence: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Merge diagnosis loop result into evidence.

    Args:
        evidence: Evidence dict to update
        result: Diagnosis loop result

    Returns:
        Updated evidence dict
    """
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
    # EVIDENCE PRESERVATION: Copy accumulated review artifact paths from all passes.
    # This is the fallback observable pass evidence when pass_run_ids are not available.
    evidence["review_artifact_paths"] = result.get("review_artifact_paths", [])

    # Critical for compute_p4c_outcome: terminal no-checks detection
    evidence["terminal_no_checks_accepted"] = result.get("terminal_no_checks_accepted", False)
    evidence["terminal_decision_reached"] = result.get("terminal_decision_reached", False)
    evidence["premature_terminal_no_checks"] = result.get("premature_terminal_no_checks", False)

    # Include detailed loop enabled check results for diagnostics
    if result.get("loop_enabled_check_reason"):
        evidence["loop_enabled_check_reason"] = result.get("loop_enabled_check_reason")
    if result.get("loop_enabled_check_error"):
        evidence["loop_enabled_check_error"] = result.get("loop_enabled_check_error")

    # Include backend-targeted diagnosis metadata
    if result.get("backend_targeted_invocation") is not None:
        evidence["backend_targeted_invocation"] = result.get("backend_targeted_invocation")
    if result.get("targeted_invocation_result"):
        evidence["targeted_invocation_result"] = result.get("targeted_invocation_result")
    if result.get("targeted_poll_result"):
        evidence["targeted_poll_result"] = result.get("targeted_poll_result")
    if result.get("backend_incident_detail"):
        evidence["backend_incident_detail"] = result.get("backend_incident_detail")

    if result.get("failure_reason"):
        evidence["failure_reason"] = result.get("failure_reason")
    return evidence


def extract_scheduling_evidence_p4c(
    detection_evidence_local: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Extract structured scheduling evidence (P4c extraction).

    Args:
        detection_evidence_local: Local copy of detection evidence
        evidence: Evidence dict to update

    Returns:
        Updated evidence dict
    """
    # P4c DIAGNOSTIC: Log the raw signals structure to understand live artifact shape
    matching_signals_raw = detection_evidence_local.get("matching_signals", [])
    sample = matching_signals_raw[0] if matching_signals_raw else None
    sample_info = f"keys={list(sample.keys())}" if isinstance(sample, dict) else "N/A"
    _log(f"  DIAGNOSTIC: matching_signals count={len(matching_signals_raw)}, first_signal={sample_info}")

    # CRITICAL FIX: Get backend_incident_detail and detection selector_literal
    # to join FailedScheduling evidence from backend with selector from P3c
    backend_incident_detail = evidence.get("backend_incident_detail")
    
    # Try to get selector_literal from P3c detection evidence first
    detection_selector_literal = detection_evidence_local.get("selector_literal") or (
        f"{detection_evidence_local.get('selector_key')}={detection_evidence_local.get('selector_value')}"
        if detection_evidence_local.get("selector_key") and detection_evidence_local.get("selector_value")
        else None
    )
    
    # If still None, extract selector_literal from backend FailedScheduling signals
    # This handles the case where P3c detection doesn't populate selector evidence
    # but the backend signals contain the scheduling failure with nodeSelector mismatch
    if detection_selector_literal is None and backend_incident_detail is not None:
        # Use Mapping for nil-safe boundary checking (handles dict subclasses, etc.)
        if isinstance(backend_incident_detail, Mapping):
            raw = backend_incident_detail.get("raw", {})
            # raw can be a Mapping (dict) or Sequence (list) - only process if Mapping
            if isinstance(raw, Mapping):
                signals = raw.get("signals", [])
                if isinstance(signals, Sequence) and not isinstance(signals, str):
                    for sig in signals:
                        if isinstance(sig, Mapping):
                            selector = _extract_selector_literal_from_failed_scheduling_signal(sig)
                            if selector:
                                detection_selector_literal = selector
                                _log(f"  Extracted selector_literal from backend signal: {detection_selector_literal}")
                                break

    # =================================================================
    # P4c CALL-SITE INVARIANT LOGGING (freshness guard for live lab)
    # =================================================================
    # Log extract_scheduling_root_cause signature and invariants BEFORE calling it
    # This proves the runtime has the fixed extractor with required parameters.
    _log("  [INVARIANT] extract_scheduling_root_cause call-site pre-flight:")

    # 1. Function signature inspection
    import inspect as _inspect
    try:
        from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
            extract_scheduling_root_cause,
        )
        sig = _inspect.signature(extract_scheduling_root_cause)
        params = list(sig.parameters.keys())
        has_backend = "backend_incident_detail" in params
        has_selector = "detection_evidence_selector_literal" in params
        _log(f"    function signature: {params}")
        _log(f"    has backend_incident_detail param: {has_backend}")
        _log(f"    has detection_evidence_selector_literal param: {has_selector}")
    except (ValueError, TypeError) as e:
        _log(f"    signature inspection failed: {e}")

    # 2. Log backend_incident_detail type and shape (defensive: nil-safe as extractor)
    if backend_incident_detail is not None:
        _log(f"    backend_incident_detail type: {type(backend_incident_detail).__name__}")
        if isinstance(backend_incident_detail, dict):
            backend_keys = list(backend_incident_detail.keys())
            _log(f"    backend_incident_detail keys: {backend_keys[:10]}")  # Limit to first 10
            # Defensive: raw may be None, list, string - handle all cases
            raw = backend_incident_detail.get("raw") if isinstance(backend_incident_detail, dict) else None
            raw_signals = raw.get("signals", []) if isinstance(raw, dict) else []
            if not isinstance(raw_signals, list):
                raw_signals = []
            _log(f"    backend_incident_detail.raw.signals count: {len(raw_signals)}")
            # Log first FailedScheduling signal
            try:
                from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
                    _is_failed_scheduling_signal,
                )
                failed_count = 0
                for sig_item in raw_signals:
                    if isinstance(sig_item, dict):
                        if _is_failed_scheduling_signal(sig_item):
                            failed_count += 1
                            if failed_count == 1:
                                _log(f"    backend first FailedScheduling signal: reason={sig_item.get('reason')}, message={str(sig_item.get('message', ''))[:80]}...")
                if failed_count == 0:
                    _log("    backend FailedScheduling signals: 0 (none found)")
                else:
                    _log(f"    backend FailedScheduling signals: {failed_count}")
            except ImportError:
                pass  # Extractor may not have this helper
        else:
            _log("    backend_incident_detail shape: non-dict")
    else:
        _log("    backend_incident_detail: None")

    # 3. Log detection_evidence_selector_literal value
    _log(f"    detection_evidence_selector_literal: {detection_selector_literal}")

    # 4. Log detection_evidence path used
    detection_path = evidence.get("detection_evidence_path", "unknown")
    _log(f"    detection_evidence path: {detection_path}")

    # Create a minimal incident-like dict for extract_scheduling_root_cause
    incident_for_extraction = {
        "namespace": evidence.get("target_namespace", detection_evidence_local.get("target_namespace", "otel-demo")),
        "object_kind": "deployment",
        "object_name": "shipping",
        "signals": matching_signals_raw,
    }

    # Extract scheduling evidence with backend incident detail and selector literal
    try:
        from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
            check_scheduling_root_cause_complete,
            extract_scheduling_root_cause,
        )
        scheduling_evidence_obj = extract_scheduling_root_cause(
            incident=incident_for_extraction,
            case_file={"events": matching_signals_raw},
            backend_incident_detail=backend_incident_detail,
            detection_evidence_selector_literal=detection_selector_literal,
        )

        if scheduling_evidence_obj.root_cause_summary:
            evidence["scheduling_evidence"] = scheduling_evidence_obj.to_dict()
            _log(f"  Extracted scheduling_evidence: {scheduling_evidence_obj.root_cause_summary[:100]}...")
            _log(f"  DIAGNOSTIC: scheduling_evidence completeness={check_scheduling_root_cause_complete(scheduling_evidence_obj)}")
            _log(f"  DIAGNOSTIC: selector_key={scheduling_evidence_obj.selector_key}, selector_value={scheduling_evidence_obj.selector_value}")
            _log(f"  DIAGNOSTIC: failed_scheduling={scheduling_evidence_obj.failed_scheduling}, unschedulable={scheduling_evidence_obj.unschedulable}")
            _log(f"  DIAGNOSTIC: selector_literal={scheduling_evidence_obj.selector_literal}")
        else:
            _log("  No scheduling_evidence extracted from detection_evidence")
    except Exception as e:
        _log(f"  WARNING: Could not extract scheduling_evidence: {e}")
        # Don't fail the phase - let compute_p4c_outcome handle the missing evidence

    return evidence


def validate_p4c_root_cause(evidence: dict[str, Any]) -> dict[str, Any]:
    """Validate P4c root-cause evidence.

    Args:
        evidence: Evidence dict

    Returns:
        P4c verdict dict
    """
    root_cause_verdict = validate_unschedulable_shipping_root_cause(evidence)
    evidence["p4c_verdict"] = root_cause_verdict.to_dict()

    if root_cause_verdict.success:
        _log(f"  P4c root-cause validation PASSED: scheduling markers found: {list(root_cause_verdict.matched_evidence)}")
    else:
        _log("  P4c root-cause validation FAILED: missing scheduling root-cause evidence")
        _log(f"  Required markers: {list(SCHEDULING_ROOT_CAUSE_MARKERS)}")
        if not evidence.get("failure_reason"):
            evidence["failure_reason"] = "missing_scheduling_root_cause_evidence"
        else:
            evidence["failure_reason"] = evidence["failure_reason"] + "; missing_scheduling_root_cause_evidence"
        evidence["validation_success"] = False

    return evidence


def compute_p4c_outcome_for_phase(evidence: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    """Compute normalized P4c outcome.

    This is the SINGLE AUTHORITATIVE SOURCE for P4c success/failure determination.
    All downstream validation and lab-result rendering must use this normalized outcome.

    LAB-STRICT MODE: accept_terminal_single_pass=False enforces multi-pass root-cause
    diagnosis contract. Terminal single-pass before required passes is a FAILURE.

    Args:
        evidence: Evidence dict

    Returns:
        Tuple of (p4c_outcome, updated_evidence)
    """
    log_step(7, "Computing normalized P4c outcome")
    p4c_outcome = compute_p4c_outcome(
        evidence,
        accept_terminal_single_pass=False,  # LAB-STRICT: require multi-pass diagnosis
        min_required_passes=MIN_REQUIRED_PASSES,
        require_root_cause_terms=True,  # LAB-STRICT: require scheduling root-cause evidence
    )
    evidence["p4c_outcome"] = {
        "success": p4c_outcome.success,
        "mode": p4c_outcome.mode,
        "pass_count": p4c_outcome.pass_count,
        "pass_run_ids": list(p4c_outcome.pass_run_ids),
        "review_artifact_paths": list(p4c_outcome.review_artifact_paths),
        "terminal_decision": p4c_outcome.terminal_decision,
        "read_only_constraints_satisfied": p4c_outcome.read_only_constraints_satisfied,
        "root_cause_evidence_satisfied": p4c_outcome.root_cause_evidence_satisfied,
        "root_cause_evidence_reason": p4c_outcome.root_cause_evidence_reason,
        "failure_reasons": list(p4c_outcome.failure_reasons),
    }

    # Update validation_success to match normalized outcome
    evidence["validation_success"] = p4c_outcome.success

    # Terminal single-pass success: clear stale legacy failure_reason
    # The normalized outcome is the authoritative source; legacy validation
    # may have set failure_reason before compute_p4c_outcome() ran
    if p4c_outcome.success:
        # Success: clear any stale legacy failure_reason
        evidence["failure_reason"] = None
    else:
        # Failure: use normalized failure_reasons from outcome
        evidence["failure_reason"] = "; ".join(p4c_outcome.failure_reasons) if p4c_outcome.failure_reasons else evidence.get("failure_reason")

    # Log the normalized outcome
    if p4c_outcome.success:
        _log(f"  P4c normalized outcome: SUCCESS (mode={p4c_outcome.mode})")
        _log(f"    pass_count={p4c_outcome.pass_count}, pass_run_ids={list(p4c_outcome.pass_run_ids)}")
    else:
        _log("  P4c normalized outcome: FAILURE")
        _log(f"    mode={p4c_outcome.mode}, failures={list(p4c_outcome.failure_reasons)}")

    return p4c_outcome, evidence


def build_phase_result(
    evidence: dict[str, Any],
    start_time: float,
    diagnosis_dir: Path,
    success: bool,
    term_checks: dict[str, bool] | None = None,
) -> LabPhaseResult:
    """Build phase result.

    Args:
        evidence: Evidence dict
        start_time: Start time
        diagnosis_dir: Diagnosis directory
        success: Whether phase succeeded
        term_checks: Optional term check results

    Returns:
        LabPhaseResult
    """
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
    # Include normalized P4c outcome if computed
    # Normalize to handle shape mismatches (tuple vs list, nested lists, etc.)
    p4c_outcome_raw = evidence.get("p4c_outcome")
    p4c_outcome = normalize_p4c_outcome_for_dict(p4c_outcome_raw)
    if p4c_outcome:
        artifacts["p4c_outcome"] = p4c_outcome
        # Normalize pass_run_ids from outcome if empty
        if not artifacts["pass_run_ids"] and p4c_outcome.get("pass_run_ids"):
            artifacts["pass_run_ids"] = p4c_outcome["pass_run_ids"]
    return LabPhaseResult(
        phase=PHASE_NAME,
        success=success,
        message=f"Multi-pass diagnosis: {'PASS' if success else 'FAIL'} - {evidence.get('failure_reason', 'all validations passed' if success else 'unknown failure')}",
        artifacts=artifacts,
        duration_seconds=duration,
    )


__all__ = [
    "run_diagnosis_loop_for_phase",
    "merge_diagnosis_result",
    "extract_scheduling_evidence_p4c",
    "validate_p4c_root_cause",
    "compute_p4c_outcome_for_phase",
    "build_phase_result",
]
