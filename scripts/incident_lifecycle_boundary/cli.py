"""CLI entrypoint for the incident lifecycle boundary verifier.

This module orchestrates all boundary checks and formats output.
"""

from __future__ import annotations

import sys

from incident_lifecycle_boundary.artifact_ids import check_artifact_id_contract
from incident_lifecycle_boundary.artifact_paths import check_artifact_path_contract
from incident_lifecycle_boundary.common import (
    DOMAIN_ADAPTER_MODULE,
    DOMAIN_MODULE,
    EVIDENCE_MODULE,
    REPO_ROOT,
    TRANSITIONS_MODULE,
    iter_python_files,
)
from incident_lifecycle_boundary.event_mappings import check_lifecycle_event_mappings
from incident_lifecycle_boundary.evidence_types import check_evidence_type_contract
from incident_lifecycle_boundary.forbidden_imports import check_forbidden_imports
from incident_lifecycle_boundary.rejection_reasons import (
    check_reason_allowlist,
    check_rejection_reason_type_alias,
)
from incident_lifecycle_boundary.status_projection import (
    EXCLUDED_FROM_STATUS_CHECKS,
    check_status_assignments,
)
from incident_lifecycle_boundary.transition_adapter_calls import (
    check_transition_adapter_uses_lifecycle_core,
)


def main(argv: list[str] | None = None) -> int:
    """Run boundary checks."""
    if argv is None:
        argv = sys.argv

    errors: list[str] = []

    # Check domain module exists
    if not DOMAIN_MODULE.exists():
        errors.append(f"Domain module not found: {DOMAIN_MODULE}")
        print("\n".join(errors))
        return 2

    # Check 1: Domain module imports (no forbidden dependencies)
    import_errors = check_forbidden_imports(str(DOMAIN_MODULE))
    if import_errors:
        errors.extend(import_errors)

    # Check 2: Rejection reasons are in allowlist (domain module only)
    reason_errors = check_reason_allowlist(str(DOMAIN_MODULE))
    if reason_errors:
        errors.extend(reason_errors)

    # Check 2b: TransitionRejectionReason alias is properly typed
    type_alias_errors = check_rejection_reason_type_alias(str(DOMAIN_MODULE))
    if type_alias_errors:
        errors.extend(type_alias_errors)

    # Check 3: Status assignments (repo-wide)
    python_files = iter_python_files(REPO_ROOT)
    status_errors: list[str] = []
    for filepath in python_files:
        # Skip files excluded from status checks (legacy files being phased out)
        if str(filepath) in EXCLUDED_FROM_STATUS_CHECKS:
            continue
        file_errors = check_status_assignments(str(filepath))
        status_errors.extend(file_errors)

    if status_errors:
        errors.extend(status_errors)

    # Check 4: Transition adapter calls typed lifecycle core (transitions module only)
    if TRANSITIONS_MODULE.exists():
        transition_errors = check_transition_adapter_uses_lifecycle_core(str(TRANSITIONS_MODULE))
        errors.extend(transition_errors)

    # Check 5: Event and actor mappings are complete (domain + adapter modules)
    if DOMAIN_ADAPTER_MODULE.exists():
        event_mapping_errors = check_lifecycle_event_mappings(
            domain_filepath=str(DOMAIN_MODULE),
            adapter_filepath=str(DOMAIN_ADAPTER_MODULE),
        )
        errors.extend(event_mapping_errors)

    # Check 6: Evidence role/kind contracts are typed and complete
    if EVIDENCE_MODULE.exists():
        evidence_errors = check_evidence_type_contract(
            evidence_filepath=str(EVIDENCE_MODULE),
            repo_root=REPO_ROOT,
        )
        errors.extend(evidence_errors)

    # Check 7: Artifact/evidence ID contracts are branded and serialized safely
    if EVIDENCE_MODULE.exists():
        artifact_id_errors = check_artifact_id_contract(str(EVIDENCE_MODULE))
        errors.extend(artifact_id_errors)

    # Check 8: Artifact path/reference contracts are branded and LLM-safe
    if EVIDENCE_MODULE.exists():
        path_errors = check_artifact_path_contract(
            evidence_filepath=str(EVIDENCE_MODULE),
            repo_root=REPO_ROOT,
        )
        errors.extend(path_errors)

    # Report results
    if errors:
        print("BOUNDARY VERIFICATION FAILED")
        print("=" * 60)
        for error in errors:
            print(f"  {error}")
        print("=" * 60)
        print(f"Found {len(errors)} boundary violation(s)")
        return 1
    else:
        print("BOUNDARY VERIFICATION PASSED")
        print("=" * 60)
        print("  Domain module has no forbidden imports")
        print("  Rejection reasons are in allowlist")
        print("  No direct .status mutations detected outside allowed files")
        print("  Transition adapter calls typed lifecycle core functions")
        print("  Event and actor mappings are complete")
        print("  Evidence role/kind contracts are typed and complete")
        print("  Artifact/evidence ID contracts are branded and serialized safely")
        print("  Artifact path/reference contracts are branded and LLM-safe")
        print("  Module is isolated from IO, Kubernetes, HTTP dependencies")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
