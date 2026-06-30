"""P4c diagnosis verification for OTel demo lab contract verification."""

from __future__ import annotations

import json
from pathlib import Path

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

    Require diagnosis evidence to reference:
    - shipping
    - at least one scheduling root-cause marker
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
    pass_count = evidence.get("pass_count", 0)
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
                "scheduling_markers_found": scheduling_markers_found,
                "read_only": evidence.get("read_only", True),
            },
        )
    )
    return True
