"""Kubernetes diagnosis phase: preflight checks and validation helpers.

This module provides phase preflight checks, live-lab freshness checks,
and invariant validation wrappers. Extracted to support LLM-friendly file sizes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_artifacts import (
    get_p3c_evidence_path,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    MIN_REQUIRED_PASSES,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import (
    _check_root_cause_terms,
    _validate_discovery_evidence,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_failures import (
    _collect_failures,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_rendering import (
    render_phase_failure,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_render import (
    log as _log,
)
from scripts.k9b_otel_demo_lab_p4c_forensic_dump import (
    check_live_lab_freshness,
)


def check_live_lab_and_log(config: Any, artifact_dir: Path) -> tuple[dict[str, Any], bool]:
    """Perform live-lab freshness check and log results.

    Args:
        config: Lab config
        artifact_dir: Artifact directory

    Returns:
        Tuple of (freshness_result, is_fresh)
    """
    freshness = check_live_lab_freshness()
    freshness_result = {
        "git_sha": freshness.get("git_sha"),
        "is_fresh": freshness.get("is_fresh", False),
        "has_extractor_backend_param": freshness.get("has_extractor_backend_param", False),
        "has_extractor_selector_param": freshness.get("has_extractor_selector_param", False),
        "errors": freshness.get("errors", []),
    }
    return freshness_result, freshness.get("is_fresh", False)


def load_detection_evidence(
    artifact_dir: Path,
    detection_artifacts: dict[str, Any] | None,
    evidence: dict[str, Any],
) -> dict[str, Any] | None:
    """Load P3c detection evidence from file or artifacts.

    Args:
        artifact_dir: Root artifact directory
        detection_artifacts: Optional pre-loaded detection artifacts
        evidence: Evidence dict to update

    Returns:
        Detection evidence dict or None if not found
    """
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


def validate_and_extract(
    detection_evidence: dict[str, Any],
    evidence: dict[str, Any],
    diagnosis_dir: Path,
) -> tuple[str | None, str | None]:
    """Validate P3c evidence and extract incident info.

    Args:
        detection_evidence: Detection evidence dict
        evidence: Evidence dict to update
        diagnosis_dir: Diagnosis directory

    Returns:
        Tuple of (incident_id, candidate_class) or (None, None) if invalid
    """
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


def check_root_cause_terms(root_cause_summary: str) -> dict[str, bool]:
    """Check root-cause terms in diagnosis.

    Args:
        root_cause_summary: Root cause summary text

    Returns:
        Dict of term -> found
    """
    return _check_root_cause_terms(root_cause_summary)


def collect_validation_failures(
    evidence: dict[str, Any],
    term_checks: dict[str, bool],
) -> list[str]:
    """Collect validation failures.

    Args:
        evidence: Evidence dict
        term_checks: Term check results

    Returns:
        List of failure messages
    """
    return _collect_failures(evidence, term_checks)


def render_failure(
    failure_reason: str,
    evidence: dict[str, Any],
    incident_id: str,
) -> str:
    """Render failure message.

    Args:
        failure_reason: Failure reason
        evidence: Evidence dict
        incident_id: Incident ID

    Returns:
        Rendered failure message
    """
    return render_phase_failure(
        failure_reason=failure_reason,
        evidence=evidence,
        incident_id=incident_id,
        min_required_passes=MIN_REQUIRED_PASSES,
    )


__all__ = [
    "check_live_lab_and_log",
    "load_detection_evidence",
    "validate_and_extract",
    "check_root_cause_terms",
    "collect_validation_failures",
    "render_failure",
]
