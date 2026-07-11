"""Alias, hierarchy, factory, exception, and omission self-tests."""

from __future__ import annotations

from scripts.incident_lifecycle_boundary.redaction_aliases import (
    check_alias_declarations,
    check_type_hierarchy,
)
from scripts.incident_lifecycle_boundary.redaction_self_test_sources import (
    PRIVACY_MODULE_VALID,
)
from scripts.incident_lifecycle_boundary.redaction_types_check import (
    EXPECTED_HIERARCHY,
    REQUIRED_PRIVACY_TYPES,
    check_exception_definition,
    check_privacy_state_factories,
    check_safe_omission_constant,
)
from scripts.incident_lifecycle_boundary.redaction_types_self_test import evaluate_fixture


def run_aliases_self_test() -> tuple[int, int, int]:
    """Run alias + hierarchy checks through production checkers."""
    accepted = rejected = failed = 0
    print("\n[1] Aliases + hierarchy subsystem (production checkers):")

    passed, _ = evaluate_fixture(
        name="accepted: valid privacy module passes alias+hierarchy",
        content=PRIVACY_MODULE_VALID,
        expected_pass=True,
        expected_errors_containing=[],
        check_func=lambda p: check_alias_declarations(p, set(REQUIRED_PRIVACY_TYPES)) + check_type_hierarchy(p, EXPECTED_HIERARCHY),
    )
    accepted += 1
    failed += 0 if passed else 1

    broken = PRIVACY_MODULE_VALID.replace(
        'SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)\n',
        "",
    )
    passed, _ = evaluate_fixture(
        name="rejected: missing SafeEvidenceExcerpt surfaces diagnostic",
        content=broken,
        expected_pass=False,
        expected_errors_containing=["Missing expected NewType alias"],
        check_func=lambda p: check_alias_declarations(p, set(REQUIRED_PRIVACY_TYPES)) + check_type_hierarchy(p, EXPECTED_HIERARCHY),
    )
    rejected += 1
    failed += 0 if passed else 1
    return accepted, rejected, failed


def run_factory_exception_omission_self_test() -> tuple[int, int, int]:
    """Run factory / exception / omission checks through production checkers."""
    accepted = rejected = failed = 0
    print("\n[2] Type/factory/exception/omission subsystem (production checkers):")

    passed, _ = evaluate_fixture(
        name="accepted: factory + exception + omission all present",
        content=PRIVACY_MODULE_VALID,
        expected_pass=True,
        expected_errors_containing=[],
        check_func=lambda p: check_privacy_state_factories(p) + check_exception_definition(p) + check_safe_omission_constant(p),
    )
    accepted += 1
    failed += 0 if passed else 1

    cases = [
        (
            "rejected: missing factory diagnostic",
            PRIVACY_MODULE_VALID.replace("def project_raw_evidence_text_for_llm", "def _removed_"),
            ["Missing factory function"],
            check_privacy_state_factories,
        ),
        (
            "rejected: missing exception diagnostic",
            PRIVACY_MODULE_VALID.replace("class UnsafeEvidenceTextError(ValueError):\n    pass\n", ""),
            ["Missing exception class"],
            check_exception_definition,
        ),
        (
            "rejected: missing SAFE_OMISSION_MARKER diagnostic",
            PRIVACY_MODULE_VALID.replace(
                'SAFE_OMISSION_MARKER = "[REDACTED:UNSAFE_EVIDENCE]"\n',
                "",
            ),
            ["Missing constant"],
            check_safe_omission_constant,
        ),
    ]
    for name, content, expected, check_func in cases:
        passed, _ = evaluate_fixture(
            name=name,
            content=content,
            expected_pass=False,
            expected_errors_containing=expected,
            check_func=check_func,
        )
        rejected += 1
        failed += 0 if passed else 1
    return accepted, rejected, failed
