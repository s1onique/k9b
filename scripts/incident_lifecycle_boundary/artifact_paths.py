"""Artifact path/reference type checks for the incident lifecycle boundary verifier.

This module verifies that artifact path/reference types crossing the incident boundary
are defined as branded NewType aliases and serialized correctly.

Design:
- SafeRelativeArtifactPath: relative paths safe for review/LLM boundaries
- LocalArtifactPath: local filesystem paths (implementation only)
- ExternalStorageRef: external storage references (s3://, gs://, etc.)
- ReviewPacketStorageRef: storage refs for review packet boundaries
- LLMSafeArtifactRef: artifact refs safe for LLM-facing outputs

Invariant:
- SafeRelativeArtifactPath is the only path-like value allowed in review-packet / LLM-safe artifact references.
- LocalArtifactPath is only used for filesystem read/write implementation details.
- ExternalStorageRef is only used for external object/storage references.

This module is a thin orchestrator that imports from specialized modules:
- artifact_path_constants: Regexes, constants, allowlists
- artifact_path_scan: Filesystem walking / AST discovery
- artifact_path_rules: Validation rules
"""

from __future__ import annotations

import sys
from pathlib import Path

from .artifact_path_constants import (
    LLM_REVIEW_MODULES,
    PATH_ALIASES,
    REQUIRED_CONSTRUCTORS,
    UNSAFE_CONSTRUCTOR_PATTERNS,
)
from .artifact_path_rules import (
    check_artifact_path_aliases,
    check_artifact_path_constructors,
    check_storage_ref_field_type,
    check_storage_ref_serialization,
    check_unsafe_literal_constructor_calls,
)
from .artifact_path_scan import (
    extract_constructor_functions,
    extract_path_newtype_aliases,
)


def check_llm_review_path_boundaries(repo_root: Path) -> list[str]:
    """Scan for violations of LLM/review path boundary rules.

    Checks:
    - No LocalArtifactPath in review/LLM modules
    - No direct safe_relative_artifact_path with unsafe string literals
    - No LocalArtifactPath converted to LLMSafeArtifactRef

    Args:
        repo_root: Root directory of the repository (can be actual repo or fake for testing)

    Returns:
        List of error messages for violations found
    """
    errors: list[str] = []

    for module_path in LLM_REVIEW_MODULES:
        # Check within repo_root directly (works for both real repo and fake test repos)
        full_path = repo_root / module_path
        if not full_path.exists():
            continue

        try:
            with open(full_path, encoding="utf-8") as f:
                source = f.read()
        except OSError:
            continue

        # Check for LocalArtifactPath usage in LLM/review modules
        if "LocalArtifactPath" in source:
            errors.append(
                f"{module_path}: LocalArtifactPath used in LLM/review module. "
                f"Use SafeRelativeArtifactPath or ReviewPacketStorageRef instead."
            )

        # Check for unsafe constructor patterns
        for pattern, description in UNSAFE_CONSTRUCTOR_PATTERNS:
            if pattern.search(source):
                errors.append(
                    f"{module_path}: Detected unsafe pattern: {description} in constructor call."
                )

    return errors


def check_artifact_path_contract(evidence_filepath: str, repo_root: Path) -> list[str]:
    """Run all artifact path/reference contract checks.

    Args:
        evidence_filepath: Path to incident_evidence.py
        repo_root: Root directory of the repository

    Returns:
        List of error messages (empty if all checks pass)
    """
    errors: list[str] = []

    # Check 1: Required NewType aliases exist
    alias_errors = check_artifact_path_aliases(evidence_filepath)
    errors.extend(alias_errors)

    # Check 2: Required constructor functions exist
    constructor_errors = check_artifact_path_constructors(evidence_filepath)
    errors.extend(constructor_errors)

    # Check 3: Check for unsafe literal constructor calls in evidence module
    unsafe_errors = check_unsafe_literal_constructor_calls(evidence_filepath)
    errors.extend(unsafe_errors)

    # Check 4: LLM/review boundary violations
    boundary_errors = check_llm_review_path_boundaries(repo_root)
    errors.extend(boundary_errors)

    # Check 5: EvidenceArtifact storage_ref field type usage
    storage_ref_errors = check_storage_ref_field_type(evidence_filepath)
    errors.extend(storage_ref_errors)

    # Check 6: EvidenceArtifact storage_ref serialization
    serialization_errors = check_storage_ref_serialization(evidence_filepath)
    errors.extend(serialization_errors)

    return errors


__all__ = [
    "PATH_ALIASES",
    "REQUIRED_CONSTRUCTORS",
    "check_artifact_path_aliases",
    "check_artifact_path_contract",
    "check_artifact_path_constructors",
    "check_llm_review_path_boundaries",
    "check_storage_ref_field_type",
    "check_storage_ref_serialization",
    "check_unsafe_literal_constructor_calls",
    "extract_constructor_functions",
    "extract_path_newtype_aliases",
]


if __name__ == "__main__":
    # Direct execution shows available aliases
    print("Artifact path/reference aliases required:")
    for alias in sorted(PATH_ALIASES):
        print(f"  - {alias}")
    print("\nRequired constructors:")
    for constructor in sorted(REQUIRED_CONSTRUCTORS):
        print(f"  - {constructor}()")
    sys.exit(0)
