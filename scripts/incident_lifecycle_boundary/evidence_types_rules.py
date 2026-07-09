"""Evidence type rules: type alias verification and contract checking.

This module provides functions to verify that evidence type aliases
exist and match the expected stable public contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .evidence_types_contract import (  # noqa: I001
    EXPECTED_EVIDENCE_KINDS,
    EXPECTED_EVIDENCE_ROLES,
)
from .evidence_types_scan import (  # noqa: I001
    check_evidence_dataclass_field_types,
    check_evidence_literal_usage,
    extract_evidence_kind_values,
    extract_evidence_role_values,
)


def check_evidence_type_aliases(filepath: str) -> list[str]:
    """Check that EvidenceRoleCode and EvidenceKindCode aliases exist and are properly typed.

    Verifies:
    - EvidenceRoleCode alias exists and contains values
    - EvidenceKindCode alias exists and contains values
    - Alias values match the expected stable public contract
    """
    errors: list[str] = []

    # Extract role values
    extracted_roles = extract_evidence_role_values(filepath)

    if not extracted_roles:
        errors.append(
            f"{filepath}: EvidenceRoleCode alias missing or empty. "
            f"Expected a Literal[...] with evidence role codes."
        )
    else:
        # Check against expected contract
        if extracted_roles != EXPECTED_EVIDENCE_ROLES:
            missing = EXPECTED_EVIDENCE_ROLES - extracted_roles
            extra = extracted_roles - EXPECTED_EVIDENCE_ROLES
            if missing:
                errors.append(
                    f"{filepath}: EvidenceRoleCode missing expected values: {sorted(missing)}"
                )
            if extra:
                errors.append(
                    f"{filepath}: EvidenceRoleCode has unexpected values: {sorted(extra)}"
                )

    # Extract kind values
    extracted_kinds = extract_evidence_kind_values(filepath)

    if not extracted_kinds:
        errors.append(
            f"{filepath}: EvidenceKindCode alias missing or empty. "
            f"Expected a Literal[...] with evidence kind codes."
        )
    else:
        # Check against expected contract
        if extracted_kinds != EXPECTED_EVIDENCE_KINDS:
            missing = EXPECTED_EVIDENCE_KINDS - extracted_kinds
            extra = extracted_kinds - EXPECTED_EVIDENCE_KINDS
            if missing:
                errors.append(
                    f"{filepath}: EvidenceKindCode missing expected values: {sorted(missing)}"
                )
            if extra:
                errors.append(
                    f"{filepath}: EvidenceKindCode has unexpected values: {sorted(extra)}"
                )

    return errors


def check_evidence_type_contract(evidence_filepath: str, repo_root: Path) -> list[str]:
    """Run all evidence type contract checks.

    Returns:
        List of error messages (empty if all checks pass).
    """
    errors: list[str] = []

    # Extract actual values from the evidence module
    extracted_roles = extract_evidence_role_values(evidence_filepath)
    extracted_kinds = extract_evidence_kind_values(evidence_filepath)

    # Use extracted values as allowed set for literal usage checks
    allowed_roles = frozenset(extracted_roles) if extracted_roles else EXPECTED_EVIDENCE_ROLES
    allowed_kinds = frozenset(extracted_kinds) if extracted_kinds else EXPECTED_EVIDENCE_KINDS

    # Check 1: Type aliases exist and are properly defined
    alias_errors = check_evidence_type_aliases(evidence_filepath)
    errors.extend(alias_errors)

    # Check 2: Dataclass fields are not widened to str/Any/object
    dataclass_errors = check_evidence_dataclass_field_types(evidence_filepath)
    errors.extend(dataclass_errors)

    # Check 3: Literal usage in evidence contexts (context-aware)
    literal_errors = check_evidence_literal_usage(
        evidence_filepath,
        repo_root,
        allowed_roles,
        allowed_kinds,
    )
    errors.extend(literal_errors)

    return errors


if __name__ == "__main__":
    sys.exit(0)
