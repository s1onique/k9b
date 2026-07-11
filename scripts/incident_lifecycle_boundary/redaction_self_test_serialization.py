"""Focused serializer self-test fixtures for multi-return behavior."""

from __future__ import annotations

from scripts.incident_lifecycle_boundary.redaction_serialization import (
    check_serializer_explicit_conversion,
)
from scripts.incident_lifecycle_boundary.redaction_types_self_test import evaluate_fixture


def run_serializer_multi_return_self_test() -> tuple[int, int, int]:
    """Exercise every required serializer return-path fixture."""
    accepted = rejected = failed = 0
    print("\n[6] Serializer return-path subsystem (production checker):")

    valid_two_returns = """\
from dataclasses import dataclass
@dataclass
class RedactedEvidenceSummary:
    summary: str
    def to_dict(self, flag: bool):
        if flag:
            return {"summary": str(self.summary)}
        return {"artifact_id": "x", "summary": str(self.summary)}
"""
    invalid_cases = [
        (
            "one valid and one missing-summary return",
            valid_two_returns.replace(
                'return {"artifact_id": "x", "summary": str(self.summary)}',
                'return {"artifact_id": "x"}',
            ),
            ["must include", "summary"],
        ),
        (
            "one valid and one bare-summary return",
            valid_two_returns.replace(
                'return {"artifact_id": "x", "summary": str(self.summary)}',
                'return {"artifact_id": "x", "summary": self.summary}',
            ),
            ["str(self.summary)"],
        ),
        (
            "indirect variable return rejected conservatively",
            """\
from dataclasses import dataclass
@dataclass
class RedactedEvidenceSummary:
    summary: str
    def to_dict(self):
        payload = {"summary": str(self.summary)}
        return payload
""",
            ["literal dict"],
        ),
        (
            "no return statement",
            """\
from dataclasses import dataclass
@dataclass
class RedactedEvidenceSummary:
    summary: str
    def to_dict(self):
        payload = {"summary": str(self.summary)}
""",
            ["return"],
        ),
    ]

    passed, _ = evaluate_fixture(
        name="accepted: two valid literal-dict returns",
        content=valid_two_returns,
        expected_pass=True,
        expected_errors_containing=[],
        check_func=lambda p: check_serializer_explicit_conversion(p, "RedactedEvidenceSummary"),
    )
    accepted += 1
    failed += 0 if passed else 1

    for label, content, expected in invalid_cases:
        passed, _ = evaluate_fixture(
            name=f"rejected: {label}",
            content=content,
            expected_pass=False,
            expected_errors_containing=expected,
            check_func=lambda p: check_serializer_explicit_conversion(p, "RedactedEvidenceSummary"),
        )
        rejected += 1
        failed += 0 if passed else 1
    return accepted, rejected, failed
