"""Validators for golden-case production adapter.

This module provides validation functions for the production adapter.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# =============================================================================
# Constants
# =============================================================================

# Forbidden patterns that indicate wrong diagnosis
_FORBIDDEN_CONCLUSION_PATTERNS = [
    (re.compile(r"\bImagePullBackOff\b", re.IGNORECASE), "image_pull_failure"),
    (re.compile(r"\bErrImagePull\b", re.IGNORECASE), "image_pull_failure"),
    (re.compile(r"\bPVC\b", re.IGNORECASE), "pvc_storage_failure"),
    (re.compile(r"\bPersistentVolumeClaim\b", re.IGNORECASE), "pvc_storage_failure"),
    (re.compile(r"\bFailedScheduling\b", re.IGNORECASE), "node_scheduling_failure"),
    (re.compile(r"\bregistry.*auth\b", re.IGNORECASE), "registry_auth_failure"),
    (re.compile(r"\bcnpg.*operator.*fail\b", re.IGNORECASE), "cnpg_operator_failure"),
]

# Forbidden mutation patterns
_MUTATION_PATTERNS = [
    re.compile(r"kubectl\s+apply", re.IGNORECASE),
    re.compile(r"kubectl\s+delete", re.IGNORECASE),
    re.compile(r"helm\s+upgrade", re.IGNORECASE),
    re.compile(r"helm\s+install", re.IGNORECASE),
    re.compile(r"kubectl\s+edit", re.IGNORECASE),
    re.compile(r"kubectl\s+replace", re.IGNORECASE),
    re.compile(r"kubectl\s+patch", re.IGNORECASE),
    re.compile(r"kubectl\s+rollout", re.IGNORECASE),
]


# =============================================================================
# Validation Functions
# =============================================================================


def load_case_bundle(case_dir: Path) -> tuple[dict, dict]:
    """Load and validate golden-case bundle.

    Args:
        case_dir: Path to the golden-case bundle directory

    Returns:
        Tuple of (manifest, expected)

    Raises:
        FileNotFoundError: If required files are missing
    """
    manifest_path = case_dir / "manifest.json"
    expected_path = case_dir / "expected.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    if not expected_path.exists():
        raise FileNotFoundError(f"Expected not found: {expected_path}")

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)

    return manifest, expected


def validate_required_evidence(case_dir: Path, manifest: dict) -> list[str]:
    """Validate that all required evidence files exist.

    Args:
        case_dir: Path to the golden-case bundle directory
        manifest: Golden-case manifest.json

    Returns:
        List of missing evidence file paths (empty if all present)
    """
    missing: list[str] = []
    required_files = manifest.get("expected_evidence_files", [])

    if not required_files:
        # Fallback to required_evidence mapping
        required_files = list(manifest.get("required_evidence", {}).values())

    for rel_path in required_files:
        file_path = case_dir / rel_path
        if not file_path.exists():
            missing.append(rel_path)

    return missing


def validate_sanitizer_findings(case_dir: Path) -> tuple[bool, str | None]:
    """Validate that sanitizer findings show successful sanitization.

    Args:
        case_dir: Path to the golden-case bundle directory

    Returns:
        Tuple of (is_valid, error_message)
    """
    findings_path = case_dir / "sanitizer-findings.json"

    if not findings_path.exists():
        return False, "sanitizer-findings.json not found"

    try:
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"sanitizer-findings.json is invalid JSON: {e}"

    if not findings.get("success", False):
        return False, "sanitizer-findings.json shows success=false"

    if findings.get("fatal_count", 0) > 0:
        return False, f"sanitizer-findings.json shows fatal_count={findings['fatal_count']}"

    if not findings.get("verification_passed", False):
        return False, "sanitizer-findings.json shows verification_passed=false"

    return True, None


def validate_provenance(manifest: dict) -> tuple[bool, str | None]:
    """Validate that provenance fields are present and valid.

    Args:
        manifest: Golden-case manifest.json

    Returns:
        Tuple of (is_valid, error_message)
    """
    source_kind = manifest.get("source_kind", "")

    # For committed golden cases, we expect live_sanitized_artifact
    if source_kind == "representative_fixture":
        # Accept but warn - case is not yet promoted
        return True, None

    if source_kind != "live_sanitized_artifact":
        return False, f"source_kind is '{source_kind}', expected 'live_sanitized_artifact'"

    provenance = manifest.get("provenance", {})
    if not provenance.get("artifacts_hash"):
        return False, "provenance.artifacts_hash is missing"

    if not provenance.get("github_artifact_digest"):
        return False, "provenance.github_artifact_digest is missing"

    return True, None


# =============================================================================
# Safety Enforcement
# =============================================================================


def check_for_forbidden_conclusions(diagnosis: dict) -> list[str]:
    """Check diagnosis for forbidden primary cause conclusions.

    Args:
        diagnosis: Diagnosis output dict

    Returns:
        List of forbidden conclusions detected
    """
    forbidden: list[str] = []

    root_cause = diagnosis.get("root_cause", "")
    description = diagnosis.get("description", "")

    for pattern, label in _FORBIDDEN_CONCLUSION_PATTERNS:
        if pattern.search(root_cause) or pattern.search(description):
            forbidden.append(label)

    return forbidden


def check_for_mutation_proposals(diagnosis: dict) -> list[str]:
    """Check diagnosis for mutation/remediation proposals.

    Args:
        diagnosis: Diagnosis output dict

    Returns:
        List of mutation proposal patterns detected
    """
    mutation: list[str] = []

    description = diagnosis.get("description", "")
    next_checks = diagnosis.get("next_checks", [])

    for pattern in _MUTATION_PATTERNS:
        if pattern.search(description):
            mutation.append(f"description: {pattern.pattern}")

    # Check next_checks against ALL mutation patterns
    for i, check in enumerate(next_checks):
        if isinstance(check, dict):
            method = check.get("method", "")
            if method:
                for p in _MUTATION_PATTERNS:
                    if p.search(method):
                        mutation.append(f"next_check[{i}].method: {p.pattern}")
                        break  # One violation per method is enough

    return mutation


def enforce_safety(diagnosis: dict) -> tuple[bool, list[str]]:
    """Enforce safety constraints on diagnosis output.

    Args:
        diagnosis: Diagnosis output dict

    Returns:
        Tuple of (is_safe, error_messages)
    """
    errors: list[str] = []

    # Check forbidden conclusions
    forbidden = check_for_forbidden_conclusions(diagnosis)
    if forbidden:
        errors.append(f"Forbidden conclusions detected: {', '.join(forbidden)}")

    # Check mutation proposals
    mutation = check_for_mutation_proposals(diagnosis)
    if mutation:
        errors.append(f"Mutation proposals detected: {', '.join(mutation)}")

    # Check read_only flag
    if not diagnosis.get("read_only", False):
        errors.append("read_only is not True")

    # Check for forbidden_actions_observed
    forbidden_observed = diagnosis.get("forbidden_actions_observed", [])
    if forbidden_observed:
        errors.append(f"forbidden_actions_observed is non-empty: {forbidden_observed}")

    # Check for mutation_proposals_observed
    mutation_observed = diagnosis.get("mutation_proposals_observed", [])
    if mutation_observed:
        errors.append(f"mutation_proposals_observed is non-empty: {mutation_observed}")

    return len(errors) == 0, errors
