"""P4c diagnosis verification for OTel demo lab contract verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.otel_lab_contracts.constants import (
    P4C_REASON_DIAGNOSIS_RCA_VALID,
    SCHEDULING_ROOT_CAUSE_MARKERS,
)
from scripts.otel_lab_contracts.models import ContractCheck, VerificationReport


def find_p4c_artifacts(artifact_dir: Path) -> list[Path]:
    """Find P4c diagnosis artifacts."""
    diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
    if not diagnosis_dir.exists():
        return []
    return list(diagnosis_dir.glob("**/*.json"))


def verify_p4c_diagnosis(artifact_dir: Path, report: VerificationReport) -> bool:
    """Verify P4c diagnosis contract.

    This verifier uses the SINGLE AUTHORITATIVE SOURCE for P4c outcome determination:
    the normalized p4c_outcome embedded in diagnosis-evidence.json.

    If p4c_outcome is present, success/failure is determined solely by that normalized
    outcome. This prevents the split-brain failure where:
    - Backend-targeted diagnosis accepts terminal single-pass as valid
    - Legacy multipass validator still requires pass_count >= 2

    Legacy behavior (when p4c_outcome is not present):
    - Multi-pass (standard): pass_count >= 2, root-cause terms in diagnosis prose
    - Terminal single-pass: terminal_no_checks_accepted=True, pass_count >= 1,
      scheduling evidence from deterministic K8s evidence (not diagnosis prose)
    """
    diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
    diagnosis_evidence_path = diagnosis_dir / "diagnosis-evidence.json"

    if not diagnosis_evidence_path.exists():
        report.add_error(f"diagnosis-evidence.json not found at {diagnosis_evidence_path}")
        return False

    try:
        evidence = json.loads(diagnosis_evidence_path.read_text())
    except json.JSONDecodeError as e:
        report.add_error(f"Failed to parse diagnosis-evidence.json: {e}")
        return False

    # Check real loop invoked
    real_loop_invoked = evidence.get("real_loop_invoked", False)
    if not real_loop_invoked:
        report.add_error("P4c: real_loop_invoked is False - simulation not allowed")
        return False

    # Use normalized p4c_outcome if present - this is the single authoritative source
    p4c_outcome = evidence.get("p4c_outcome")
    if p4c_outcome:
        # Normalized outcome is present - use it as the single authoritative source
        outcome_success = p4c_outcome.get("success", False)
        outcome_mode = p4c_outcome.get("mode", "unknown")
        outcome_pass_count = p4c_outcome.get("pass_count", 0)
        outcome_pass_run_ids = p4c_outcome.get("pass_run_ids", [])
        outcome_failure_reasons = p4c_outcome.get("failure_reasons", [])

        if outcome_success:
            # Success via normalized outcome - accept terminal or multipass
            report.add_check(
                ContractCheck(
                    name="p4c_diagnosis",
                    passed=True,
                    phase="p4c",
                    reason=P4C_REASON_DIAGNOSIS_RCA_VALID,
                    details={
                        "incident_id": evidence.get("incident_id"),
                        "pass_count": outcome_pass_count,
                        "pass_run_ids": outcome_pass_run_ids,
                        "success_mode": outcome_mode,
                        "p4c_outcome_source": "normalized",
                    },
                )
            )
            return True
        else:
            # Failure via normalized outcome - report all failure reasons
            for reason in outcome_failure_reasons:
                report.add_error(f"P4c normalized outcome failure: {reason}")
            return False

    # Fallback: legacy validation (when p4c_outcome is not present)
    # Check for terminal no-checks single-pass mode
    terminal_no_checks_accepted = evidence.get("terminal_no_checks_accepted", False)
    pass_count = evidence.get("pass_count", 0)
    is_terminal_mode = (
        terminal_no_checks_accepted
        and pass_count >= 1
        and evidence.get("real_pass_artifacts_found", False)
    )

    # Terminal single-pass mode: bypass multi-pass requirements
    if is_terminal_mode:
        # For terminal no-checks, scheduling evidence comes from deterministic K8s evidence
        # Check P3c/P2b artifacts for scheduling-specific markers
        scheduling_markers_found = _check_scheduling_markers_from_evidence(evidence)
        
        if not scheduling_markers_found:
            report.add_error(
                f"P4c: Terminal single-pass mode requires scheduling markers in evidence. "
                f"Expected one of: {SCHEDULING_ROOT_CAUSE_MARKERS}"
            )
            return False

        report.add_check(
            ContractCheck(
                name="p4c_diagnosis",
                passed=True,
                phase="p4c",
                reason=P4C_REASON_DIAGNOSIS_RCA_VALID,
                details={
                    "incident_id": evidence.get("incident_id"),
                    "pass_count": pass_count,
                    "success_mode": "terminal_no_checks_single_pass",
                    "scheduling_markers_found": scheduling_markers_found,
                    "terminal_no_checks_accepted": True,
                },
            )
        )
        return True

    # Standard multi-pass mode
    # Check shipping identity
    root_cause_summary = str(evidence.get("root_cause_summary", ""))
    if "shipping" not in root_cause_summary.lower():
        report.add_error("P4c root_cause_summary does not reference 'shipping'")
        return False

    # Check scheduling root-cause markers
    scheduling_markers_found = [marker for marker in SCHEDULING_ROOT_CAUSE_MARKERS if marker.lower() in root_cause_summary.lower()]

    if not scheduling_markers_found:
        report.add_error(f"P4c: No scheduling root-cause markers found in root_cause_summary. Expected one of: {SCHEDULING_ROOT_CAUSE_MARKERS}")
        return False

    # Check pass count
    if pass_count < 2:
        report.add_error(f"P4c: pass_count={pass_count} < 2")
        return False

    # Check read-only contract
    executed_checks = evidence.get("executed_checks", [])
    mutating_patterns = ["apply", "delete", "patch", "scale", "rollout", "edit", "replace", "create"]
    has_mutating = any(any(p in str(check).lower() for p in mutating_patterns) for check in executed_checks)

    if has_mutating:
        report.add_error(f"P4c: Mutating commands found in executed_checks: {executed_checks}")
        return False

    # Check phase result reason
    phase_reason = evidence.get("phase_result_reason", "")
    if not any(r in str(phase_reason).lower() for r in ["diagnosis_rca_valid", "rca_valid"]):
        report.add_warning(f"P4c phase_result_reason '{phase_reason}' not in standard set")

    report.add_check(
        ContractCheck(
            name="p4c_diagnosis",
            passed=True,
            phase="p4c",
            reason=phase_reason or P4C_REASON_DIAGNOSIS_RCA_VALID,
            details={
                "incident_id": evidence.get("incident_id"),
                "pass_count": pass_count,
                "success_mode": "multi_pass",
                "scheduling_markers_found": scheduling_markers_found,
                "read_only": evidence.get("read_only", True),
            },
        )
    )
    return True


def _check_scheduling_markers_from_evidence(evidence: dict[str, Any]) -> list[str]:
    """Check for scheduling markers in P3c/P2b evidence for terminal no-checks mode.

    For terminal no-checks single-pass, scheduling evidence comes from
    deterministic K8s evidence (P2b injection, P3c discovery) rather than
    diagnosis prose. Check the evidence for scheduling-specific markers.

    Args:
        evidence: Diagnosis evidence dict

    Returns:
        List of scheduling markers found
    """
    found: list[str] = []

    # Check P3c detection evidence if available
    detection_evidence = evidence.get("detection_evidence")
    if isinstance(detection_evidence, dict):
        found.extend(_find_scheduling_markers_in_dict(detection_evidence))

    # Check for scheduling markers in the root_cause_summary (may still have them)
    root_cause_summary = str(evidence.get("root_cause_summary", "")).lower()
    for marker in SCHEDULING_ROOT_CAUSE_MARKERS:
        if marker.lower() in root_cause_summary:
            found.append(marker)

    # Check p4c_verdict for matched evidence
    p4c_verdict = evidence.get("p4c_verdict", {})
    if isinstance(p4c_verdict, dict):
        matched = p4c_verdict.get("matched_evidence", [])
        if isinstance(matched, list):
            found.extend(matched)

    # Deduplicate and return
    return list(dict.fromkeys(found))


def _find_scheduling_markers_in_dict(data: dict[str, Any], _depth: int = 0) -> list[str]:
    """Recursively search for scheduling markers in a dict.

    Args:
        data: Dict to search
        _depth: Current recursion depth (prevents infinite loops)

    Returns:
        List of scheduling markers found
    """
    if _depth > 5:
        return []  # Prevent infinite recursion

    found: list[str] = []

    # Check string values for markers
    for key, value in data.items():
        if isinstance(value, str):
            value_lower = value.lower()
            for marker in SCHEDULING_ROOT_CAUSE_MARKERS:
                if marker.lower() in value_lower:
                    found.append(marker)
        elif isinstance(value, dict):
            found.extend(_find_scheduling_markers_in_dict(value, _depth + 1))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    item_lower = item.lower()
                    for marker in SCHEDULING_ROOT_CAUSE_MARKERS:
                        if marker.lower() in item_lower:
                            found.append(marker)
                elif isinstance(item, dict):
                    found.extend(_find_scheduling_markers_in_dict(item, _depth + 1))

    return found
