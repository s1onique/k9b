"""Projector and serializer self-tests for the redaction verifier."""

from __future__ import annotations

from scripts.incident_lifecycle_boundary.redaction_self_test_sources import LLM_SAFE_MODULE_VALID
from scripts.incident_lifecycle_boundary.redaction_serialization import (
    check_serializer_explicit_conversion,
)
from scripts.incident_lifecycle_boundary.redaction_types_check import (
    REQUIRED_PROJECTOR,
    check_projector_parameter_type,
)
from scripts.incident_lifecycle_boundary.redaction_types_self_test import evaluate_fixture


def run_projector_serializer_self_test() -> tuple[int, int, int]:
    """Run projector + serializer checks through production checkers."""
    accepted = rejected = failed = 0
    print("\n[3] Projector + serializer subsystem (production checkers):")

    passed, _ = evaluate_fixture(
        name="accepted: projector keyword-only LLMSafeEvidenceText",
        content=LLM_SAFE_MODULE_VALID,
        expected_pass=True,
        expected_errors_containing=[],
        check_func=lambda p: check_projector_parameter_type(p, REQUIRED_PROJECTOR),
    )
    accepted += 1
    failed += 0 if passed else 1

    projector_cases = [
        (
            "rejected: projector missing summary parameter",
            LLM_SAFE_MODULE_VALID.replace("    summary: LLMSafeEvidenceText,\n", ""),
            ["missing 'summary' parameter"],
        ),
        (
            "rejected: projector summary typed as RedactedEvidenceText",
            LLM_SAFE_MODULE_VALID.replace(
                "    summary: LLMSafeEvidenceText,\n",
                "    summary: 'RedactedEvidenceText',\n",
            ),
            ["must have type annotation 'LLMSafeEvidenceText'"],
        ),
    ]
    for name, content, expected in projector_cases:
        passed, _ = evaluate_fixture(
            name=name,
            content=content,
            expected_pass=False,
            expected_errors_containing=expected,
            check_func=lambda p: check_projector_parameter_type(p, REQUIRED_PROJECTOR),
        )
        rejected += 1
        failed += 0 if passed else 1

    serializer_pass = """\
from dataclasses import dataclass
@dataclass
class RedactedEvidenceSummary:
    artifact_id: str
    summary: str
    def to_dict(self):
        return {"summary": str(self.summary)}
"""
    passed, _ = evaluate_fixture(
        name="accepted: serializer uses str(self.summary)",
        content=serializer_pass,
        expected_pass=True,
        expected_errors_containing=[],
        check_func=lambda p: check_serializer_explicit_conversion(p, "RedactedEvidenceSummary"),
    )
    accepted += 1
    failed += 0 if passed else 1

    serializer_fail = serializer_pass.replace(
        'return {"summary": str(self.summary)}',
        'return {"artifact_id": self.artifact_id}',
    )
    passed, _ = evaluate_fixture(
        name="rejected: serializer missing summary field",
        content=serializer_fail,
        expected_pass=False,
        expected_errors_containing=["summary", "Missing"],
        check_func=lambda p: check_serializer_explicit_conversion(p, "RedactedEvidenceSummary"),
    )
    rejected += 1
    failed += 0 if passed else 1
    return accepted, rejected, failed
