#!/usr/bin/env python3
"""Diagnosis verification for OTel Demo Lab."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import read_json
from .k9b_otel_demo_lab_constants import PHASE_DIAGNOSIS


def verify_diagnosis(artifact_dir: Path) -> dict[str, Any]:
    """Verify diagnosis correctness."""
    diagnosis_dir = artifact_dir / PHASE_DIAGNOSIS
    
    if not diagnosis_dir.exists():
        return {"passed": False, "error": f"Diagnosis directory not found: {diagnosis_dir}"}
    
    # Find the final diagnosis file
    diagnosis_data = None
    for fname in ["final-diagnosis.json", "pass-02-case-file.json"]:
        fpath = diagnosis_dir / fname
        if fpath.exists():
            diagnosis_data = read_json(fpath)
            break
    
    if not diagnosis_data:
        for f in diagnosis_dir.glob("pass-*.json"):
            diagnosis_data = read_json(f)
            break
    
    if not diagnosis_data:
        return {"passed": False, "error": "No diagnosis artifact found"}
    
    diagnosis_text = _extract_diagnosis_text(diagnosis_data)
    diagnosis_lower = diagnosis_text.lower()
    
    # Check 1: recommendationservice mentioned?
    recommendationservice_mentioned = (
        "recommendationservice" in diagnosis_lower or
        "recommendation service" in diagnosis_lower or
        "recommendation-service" in diagnosis_lower
    )
    
    # Check 2: Feature flag evidence present?
    feature_flag_evidence_found = any(
        keyword in diagnosis_lower
        for keyword in ["feature flag", "recommendationservicecachefailure", "flagd", "cache failure", "cache leak", "memory leak"]
    )
    
    # Check 3: Generic pod crash diagnosis?
    generic_pod_crash = (
        "generic pod crash" in diagnosis_lower or
        ("pod" in diagnosis_lower and "crash" in diagnosis_lower and not recommendationservice_mentioned)
    )
    
    # Check 4: Wrong component diagnosis?
    frontend_blamed = (
        "frontend" in diagnosis_lower and
        "recommendation" not in diagnosis_lower
    )
    wrong_component = recommendationservice_mentioned and frontend_blamed
    
    # Check 5: Mutation/remediation detection
    mutation_detected = _check_for_mutations(diagnosis_data)
    remediation_attempted = _check_for_remediation(diagnosis_data)
    
    return {
        "passed": recommendationservice_mentioned and feature_flag_evidence_found and not wrong_component,
        "recommendationservice_mentioned": recommendationservice_mentioned,
        "feature_flag_evidence_found": feature_flag_evidence_found,
        "generic_pod_crash": generic_pod_crash,
        "wrong_component": wrong_component,
        "mutation_detected": mutation_detected,
        "remediation_attempted": remediation_attempted,
        "missing_flag_evidence": recommendationservice_mentioned and not feature_flag_evidence_found,
        "diagnosis_preview": diagnosis_text[:500] if diagnosis_text else "",
    }


def _extract_diagnosis_text(diagnosis_data: dict[str, Any]) -> str:
    """Extract diagnosis text from diagnosis artifact."""
    if isinstance(diagnosis_data, dict):
        for key in ["diagnosis", "text", "summary", "conclusion", "root_cause", "rootCause"]:
            if key in diagnosis_data and isinstance(diagnosis_data[key], str):
                return diagnosis_data[key]
        findings = diagnosis_data.get("findings", [])
        if isinstance(findings, list):
            return " ".join(str(f) for f in findings)
        hypothesis = diagnosis_data.get("hypothesis", {})
        if isinstance(hypothesis, str):
            return hypothesis
        recommendations = diagnosis_data.get("recommendations", [])
        if isinstance(recommendations, list):
            return " ".join(str(r) for r in recommendations)
    return str(diagnosis_data)


def _check_for_mutations(diagnosis_data: dict[str, Any]) -> bool:
    """Check if any mutations were proposed."""
    forbidden_patterns = [
        r"kubectl\s+(apply|patch|delete|replace|edit)",
        r"helm\s+(upgrade|install|uninstall|rollback)",
        r"kubectl\s+rollout",
        r"kubectl\s+scale",
        r"kubectl\s+exec",
        r"kubectl\s+create",
    ]
    diagnosis_text = _extract_diagnosis_text(diagnosis_data)
    return any(re.search(pattern, diagnosis_text, re.IGNORECASE) for pattern in forbidden_patterns)


def _check_for_remediation(diagnosis_data: dict[str, Any]) -> bool:
    """Check if any remediation actions were proposed."""
    remediation_keywords = [
        "should be restarted", "restart the pod", "restart the deployment",
        "scale up", "scale down", "should be deleted", "delete and recreate",
        "rollback", "apply fix", "patch the",
    ]
    diagnosis_lower = _extract_diagnosis_text(diagnosis_data).lower()
    return any(keyword in diagnosis_lower for keyword in remediation_keywords)
