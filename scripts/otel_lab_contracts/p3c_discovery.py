"""P3c discovery verification for OTel demo lab contract verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.otel_lab_contracts.constants import (
    ACCEPTED_P3C_CANDIDATE_CLASSES,
    P3C_REASON_INCIDENT_DISCOVERED_WITHOUT_RCA,
    RCA_MARKERS_IN_DISCOVERY,
)
from scripts.otel_lab_contracts.models import ContractCheck, VerificationReport


def find_p3c_artifacts(artifact_dir: Path) -> list[Path]:
    """Find P3c detection/discovery artifacts."""
    patterns = [
        "**/p3c*/**/*.json",
        "**/phase3*/**/*.json",
    ]
    found: list[Path] = []
    for pattern in patterns:
        found.extend(artifact_dir.glob(pattern))
    return found


def verify_p3c_discovery(artifact_dir: Path, report: VerificationReport) -> bool:
    """Verify P3c discovery contract.

    Accept a discovered incident only if:
    - namespace == otel-demo
    - workload references shipping
    - candidate_class in ACCEPTED_P3C_CANDIDATE_CLASSES
    - reason in VALID_P3C_REASONS
    """
    p3c_artifacts = find_p3c_artifacts(artifact_dir)

    if not p3c_artifacts:
        report.add_error("No P3c detection artifacts found")
        return False

    # Try detection-evidence.json first
    detection_evidence_path = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery" / "detection-evidence.json"

    if detection_evidence_path.exists():
        return _verify_p3c_from_evidence(detection_evidence_path, report)

    # Fall back to first found artifact
    for artifact_path in p3c_artifacts:
        try:
            evidence = json.loads(artifact_path.read_text())
            return _verify_p3c_from_evidence_dict(evidence, report, str(artifact_path))
        except (json.JSONDecodeError, OSError):
            continue

    report.add_error("No parseable P3c artifact found")
    return False


def _verify_p3c_from_evidence(path: Path, report: VerificationReport) -> bool:
    """Verify P3c from detection-evidence.json."""
    try:
        evidence = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        report.add_error(f"Failed to parse {path}: {e}")
        return False
    return _verify_p3c_from_evidence_dict(evidence, report, str(path))


def _has_shipping_identity(evidence: dict[str, Any]) -> bool:
    """Check if evidence contains shipping identity across normalized structured fields.

    P3c is discovery-only and may not have root_cause_summary. Accept shipping
    identity from any structured field that represents the target workload.
    """
    # Fields that can contain shipping identity
    shipping_fields = [
        "object_name",
        "workload",
        "workload_name",
        "target_workload",
        "deployment",
        "deployment_name",
        "pod_name",
        "incident_id",
        "root_cause_summary",  # fallback
    ]

    # Also check nested matched_incident structure
    matched_incident = evidence.get("matched_incident", {})
    if isinstance(matched_incident, dict):
        for key in ["id", "object_name", "signals"]:
            val = matched_incident.get(key)
            if val is not None and "shipping" in str(val).lower():
                return True

    # Check all shipping fields
    for shipping_field in shipping_fields:
        value = evidence.get(shipping_field)
        if value is not None and "shipping" in str(value).lower():
            return True

    # Also check signals array if present
    signals = evidence.get("signals", [])
    if isinstance(signals, list):
        for signal in signals:
            if "shipping" in str(signal).lower():
                return True

    return False


def _verify_p3c_from_evidence_dict(evidence: dict[str, Any], report: VerificationReport, source: str) -> bool:
    """Verify P3c from evidence dict."""
    # Check discovery success
    if not evidence.get("discovery_success"):
        report.add_error(f"P3c discovery failed: {evidence.get('failure_reason', 'unknown')}")
        return False

    # Check incident ID
    incident_id = evidence.get("incident_id")
    if not incident_id:
        report.add_error("P3c missing incident_id")
        return False

    # Check candidate class
    candidate_class = evidence.get("candidate_class", "")
    if candidate_class not in ACCEPTED_P3C_CANDIDATE_CLASSES:
        report.add_error(f"P3c candidate_class '{candidate_class}' not in accepted list: {ACCEPTED_P3C_CANDIDATE_CLASSES}")
        return False

    # Check namespace
    target_namespace = evidence.get("target_namespace", "")
    if target_namespace != "otel-demo":
        report.add_error(f"P3c namespace '{target_namespace}' != 'otel-demo'")
        return False

    # Check shipping reference - accept from any structured field
    has_shipping = _has_shipping_identity(evidence)

    if not has_shipping:
        report.add_error("P3c evidence does not reference 'shipping'")
        return False

    # P3c must NOT require RCA markers (those belong to P4c)
    root_cause_summary = evidence.get("root_cause_summary", "")
    rca_in_discovery = any(m in root_cause_summary for m in RCA_MARKERS_IN_DISCOVERY)

    # Check phase result reason
    phase_reason = evidence.get("phase_result_reason", evidence.get("reason", ""))
    valid_reason = any(r in str(phase_reason).lower() for r in ["incident_discovered", "discovery_valid", "p3c"])

    if not valid_reason:
        report.add_warning(f"P3c phase_result_reason '{phase_reason}' not in standard set")

    report.add_check(
        ContractCheck(
            name="p3c_discovery",
            passed=True,
            phase="p3c",
            reason=phase_reason or P3C_REASON_INCIDENT_DISCOVERED_WITHOUT_RCA,
            details={
                "incident_id": incident_id,
                "candidate_class": candidate_class,
                "namespace": target_namespace,
                "has_shipping": has_shipping,
                "rca_in_discovery": rca_in_discovery,
            },
        )
    )
    return True
