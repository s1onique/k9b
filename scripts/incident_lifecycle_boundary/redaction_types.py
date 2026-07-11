"""Canonical ACT-local privacy-state verifier and self-test CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.incident_lifecycle_boundary.redaction_aliases import (
    check_alias_declarations,
    check_type_hierarchy,
)
from scripts.incident_lifecycle_boundary.redaction_boundaries import (
    check_protected_boundary_imports,
)
from scripts.incident_lifecycle_boundary.redaction_constructors import (
    check_trusted_constructor_usage,
)
from scripts.incident_lifecycle_boundary.redaction_self_test_runner import run_self_tests
from scripts.incident_lifecycle_boundary.redaction_serialization import (
    check_serializer_explicit_conversion,
)
from scripts.incident_lifecycle_boundary.redaction_types_check import (
    EXPECTED_HIERARCHY,
    REQUIRED_PRIVACY_TYPES,
    REQUIRED_PROJECTOR,
    check_exception_definition,
    check_privacy_state_factories,
    check_projector_parameter_type,
    check_safe_omission_constant,
)

PRIVACY_STATE_MODULE = "k8s_diag_agent/collect/incident_evidence_redaction.py"
LLM_SAFE_MODULE = "k8s_diag_agent/collect/incident_evidence_llm_safe.py"


def verify_redaction_types(repo_root: Path) -> tuple[bool, list[str]]:
    """Run all redaction-type verification checks against a source tree."""
    errors: list[str] = []

    privacy_module_path = repo_root / PRIVACY_STATE_MODULE
    if privacy_module_path.exists():
        errors.extend(check_alias_declarations(str(privacy_module_path), set(REQUIRED_PRIVACY_TYPES)))
        errors.extend(check_type_hierarchy(str(privacy_module_path), EXPECTED_HIERARCHY))
        errors.extend(check_privacy_state_factories(str(privacy_module_path)))
        errors.extend(check_exception_definition(str(privacy_module_path)))
        errors.extend(check_safe_omission_constant(str(privacy_module_path)))
    else:
        errors.append(f"Privacy-state module not found at {PRIVACY_STATE_MODULE}")

    llm_safe_module_path = repo_root / LLM_SAFE_MODULE
    if llm_safe_module_path.exists():
        errors.extend(check_projector_parameter_type(str(llm_safe_module_path), REQUIRED_PROJECTOR))
        errors.extend(check_serializer_explicit_conversion(str(llm_safe_module_path), "RedactedEvidenceSummary"))
    else:
        errors.append(f"LLM safe module not found at {LLM_SAFE_MODULE}")

    errors.extend(check_protected_boundary_imports(repo_root))
    errors.extend(check_trusted_constructor_usage(repo_root))
    return len(errors) == 0, errors


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for self-tests and production-tree verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root to verify (default: production src/ tree).",
    )
    args = parser.parse_args(argv if argv is not None else None)

    if args.self_test:
        _accepted, _rejected, failed = run_self_tests()
        return 0 if failed == 0 else 1

    repo_root = args.repo_root.resolve() if args.repo_root is not None else Path(__file__).parents[2] / "src"
    success, errors = verify_redaction_types(repo_root)
    if errors:
        print("Redaction-types verification errors:")
        for error in errors:
            print(f"  - {error}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
