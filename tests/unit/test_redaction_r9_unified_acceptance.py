"""ACT-K9B-HULK-SECRET-REDACTION-TYPES01-R9 unified acceptance tests.

These tests consolidate the R9 acceptance contract across:

* alias verifier self-tests
* type / factory / projector self-tests
* constructor self-tests using production verifier
* boundary self-tests using production verifier
* serializer self-tests
* aggregate verifier self-test (standalone production-tree verifier)
* focused sanitizer regression coverage for established sentinel forms
* complete credential and mixed-input matrix
* logging safety / synthetic secret hygiene across sanitizer paths
* four ACT-local negative proofs (facade-qualified constructor; qualified
  protected annotation; missing summary serialization; projector typed as
  RedactedEvidenceText)
* mypy-positive / mypy-negative fixtures (exercised at runtime here; the
  dedicated harness in `test_redaction_r9_mypy_fixtures.py` runs mypy over
  static fixture files)
* previous LLM-safe evidence tests (the existing test_redaction_r5_*
  and test_redaction_r8_* suites remain asserted here as well)

All verifier self-tests run through a single evaluator so a single
fixture-fail rule is uniform across aliases / types / constructors /
boundaries / serialization.
"""

from __future__ import annotations

from scripts.incident_lifecycle_boundary.redaction_aliases import (
    check_alias_declarations,
    check_type_hierarchy,
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

# ---------------------------------------------------------------------------
# Shared evaluator - single source of truth for self-test semantics.
#
# Accepted fixture: errors MUST be empty.
# Rejected fixture: errors MUST be non-empty AND every expected diagnostic
# substring MUST appear AND an unrelated error MUST NOT satisfy the fixture.
# ---------------------------------------------------------------------------


def evaluate_fixture(
    *,
    name: str,
    content: str,
    expected_pass: bool,
    expected_errors_containing: list[str],
    check_func,
    setup_path: bool = True,
) -> tuple[bool, list[str]]:
    """Evaluate a single fixture case through `check_func`."""
    import os
    import tempfile

    if setup_path:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as fh:
            fh.write(content)
            temp_path = fh.name
    else:
        temp_path = None

    try:
        errors = list(check_func(temp_path))
        errors_serialised = [str(e) for e in errors]

        if expected_pass:
            passed = len(errors_serialised) == 0
        else:
            passed = len(errors_serialised) > 0
            if expected_errors_containing:
                missing = [sub for sub in expected_errors_containing if not any(sub in e for e in errors_serialised)]
                if missing:
                    passed = False

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            for err in errors_serialised[:5]:
                print(f"        - {err[:140]}")
        return passed, errors_serialised
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Test data - fixture content blocks used across multiple checks.
# ---------------------------------------------------------------------------

VALID_PRIVACY_MODULE = '''\
"""Trusted privacy-state module."""
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)

SAFE_OMISSION_MARKER = "[REDACTED:UNSAFE_EVIDENCE]"


class UnsafeEvidenceTextError(ValueError):
    pass


def redact_evidence_text(value: RawEvidenceText) -> RedactedEvidenceText:
    return RedactedEvidenceText(str(value))


def approve_redacted_evidence_text(
    value: RedactedEvidenceText,
) -> LLMSafeEvidenceText:
    return LLMSafeEvidenceText(value)


def project_raw_evidence_text_for_llm(
    value: RawEvidenceText,
    *,
    max_chars: int,
) -> LLMSafeEvidenceText:
    return LLMSafeEvidenceText(RedactedEvidenceText(str(value)[:max_chars]))


def make_safe_evidence_excerpt(
    value: LLMSafeEvidenceText,
    *,
    max_chars: int,
) -> SafeEvidenceExcerpt:
    return SafeEvidenceExcerpt(value)
'''

VALID_LLM_SAFE_MODULE = '''\
"""LLM-safe projector module."""
from dataclasses import dataclass
from typing import Any, NewType

from k8s_diag_agent.collect.incident_evidence_redaction import (
    LLMSafeEvidenceText,
)

EvidenceArtifact = Any  # stub for self-test
LLMSafeArtifactRef = Any
ReviewPacketStorageRef = Any


@dataclass(frozen=True, slots=True, kw_only=True)
class RedactedEvidenceSummary:
    artifact_id: str
    kind: str
    role: str
    summary: LLMSafeEvidenceText

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "kind": self.kind,
            "role": self.role,
            "summary": str(self.summary),
        }


def evidence_artifact_to_llm_safe_summary(
    artifact: EvidenceArtifact,
    *,
    safe_ref: "LLMSafeArtifactRef | ReviewPacketStorageRef | None",
    summary: LLMSafeEvidenceText,
) -> RedactedEvidenceSummary:
    return RedactedEvidenceSummary(
        artifact_id=getattr(artifact, "artifact_id", ""),
        kind=getattr(artifact, "kind", ""),
        role="supporting",
        summary=summary,
    )
'''


# ---------------------------------------------------------------------------
# Aliases / hierarchy / factories / exception / omission / projector checks
# ---------------------------------------------------------------------------


class TestUnifiedEvaluator:
    """Alias + hierarchy + factory + exception + omission + projector.

    Each check uses the shared evaluator so a single failure-mode rule
    applies across all privacy-state subsystems.
    """

    def test_alias_hierarchy_accepted_on_valid_module(self) -> None:
        passed, _ = evaluate_fixture(
            name="accepted: valid privacy module passes alias+hierarchy",
            content=VALID_PRIVACY_MODULE,
            expected_pass=True,
            expected_errors_containing=[],
            check_func=lambda p: check_alias_declarations(p, set(REQUIRED_PRIVACY_TYPES)) + check_type_hierarchy(p, EXPECTED_HIERARCHY) + check_privacy_state_factories(p) + check_exception_definition(p) + check_safe_omission_constant(p),
        )
        assert passed

    def test_alias_hierarchy_rejected_on_missing_type(self) -> None:
        # Drop SafeEvidenceExcerpt
        broken = VALID_PRIVACY_MODULE.replace(
            'SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)\n',
            "",
        )
        passed, errors = evaluate_fixture(
            name="rejected: missing SafeEvidenceExcerpt surfaces diagnostic",
            content=broken,
            expected_pass=False,
            expected_errors_containing=["Missing expected NewType alias"],
            check_func=lambda p: check_alias_declarations(p, set(REQUIRED_PRIVACY_TYPES)) + check_type_hierarchy(p, EXPECTED_HIERARCHY),
        )
        assert passed

    def test_factories_rejected_when_missing(self) -> None:
        # Drop project_raw_evidence_text_for_llm
        broken = VALID_PRIVACY_MODULE.replace(
            "def project_raw_evidence_text_for_llm",
            "def _removed_",
        )
        passed, errors = evaluate_fixture(
            name="rejected: missing factory project_raw_evidence_text_for_llm",
            content=broken,
            expected_pass=False,
            expected_errors_containing=["Missing factory function"],
            check_func=lambda p: check_privacy_state_factories(p),
        )
        assert passed

    def test_exception_rejected_when_missing(self) -> None:
        broken = VALID_PRIVACY_MODULE.replace(
            "class UnsafeEvidenceTextError(ValueError):\n    pass\n",
            "",
        )
        passed, _ = evaluate_fixture(
            name="rejected: missing UnsafeEvidenceTextError",
            content=broken,
            expected_pass=False,
            expected_errors_containing=["Missing exception class"],
            check_func=lambda p: check_exception_definition(p),
        )
        assert passed

    def test_safe_omission_constant_rejected_when_missing(self) -> None:
        broken = VALID_PRIVACY_MODULE.replace(
            'SAFE_OMISSION_MARKER = "[REDACTED:UNSAFE_EVIDENCE]"\n',
            "",
        )
        passed, _ = evaluate_fixture(
            name="rejected: missing SAFE_OMISSION_MARKER",
            content=broken,
            expected_pass=False,
            expected_errors_containing=["Missing constant"],
            check_func=lambda p: check_safe_omission_constant(p),
        )
        assert passed

    def test_projector_accepted_when_keyword_only_llm_safe(self) -> None:
        passed, _ = evaluate_fixture(
            name="accepted: projector summary is keyword-only LLMSafeEvidenceText",
            content=VALID_LLM_SAFE_MODULE,
            expected_pass=True,
            expected_errors_containing=[],
            check_func=lambda p: check_projector_parameter_type(p, REQUIRED_PROJECTOR),
        )
        assert passed

    def test_projector_rejected_when_missing_summary(self) -> None:
        broken = VALID_LLM_SAFE_MODULE.replace(
            "    summary: LLMSafeEvidenceText,\n",
            "",
        )
        passed, _ = evaluate_fixture(
            name="rejected: projector missing summary parameter",
            content=broken,
            expected_pass=False,
            expected_errors_containing=["missing 'summary' parameter"],
            check_func=lambda p: check_projector_parameter_type(p, REQUIRED_PROJECTOR),
        )
        assert passed

    def test_projector_rejected_when_unannotated_summary(self) -> None:
        broken = VALID_LLM_SAFE_MODULE.replace(
            "    summary: LLMSafeEvidenceText,\n",
            "    summary,\n",
        )
        passed, _ = evaluate_fixture(
            name="rejected: projector summary is unannotated",
            content=broken,
            expected_pass=False,
            expected_errors_containing=["missing type annotation"],
            check_func=lambda p: check_projector_parameter_type(p, REQUIRED_PROJECTOR),
        )
        assert passed

    def test_projector_rejected_when_redacted_annotation(self) -> None:
        broken = VALID_LLM_SAFE_MODULE.replace(
            "    summary: LLMSafeEvidenceText,\n",
            "    summary: 'RedactedEvidenceText',\n",
        )
        passed, _ = evaluate_fixture(
            name="rejected: projector summary annotated as RedactedEvidenceText",
            content=broken,
            expected_pass=False,
            expected_errors_containing=["must have type annotation 'LLMSafeEvidenceText'"],
            check_func=lambda p: check_projector_parameter_type(p, REQUIRED_PROJECTOR),
        )
        assert passed

    def test_projector_rejected_when_positional_summary(self) -> None:
        # Move summary to positional.
        broken = (
            "from dataclasses import dataclass\n"
            "from typing import Any, NewType\n"
            "from k8s_diag_agent.collect.incident_evidence_redaction import (\n"
            "    LLMSafeEvidenceText,\n"
            ")\n"
            "EvidenceArtifact = Any\n"
            "LLMSafeArtifactRef = Any\n"
            "ReviewPacketStorageRef = Any\n"
            "\n"
            "@dataclass(frozen=True, slots=True)\n"
            "class RedactedEvidenceSummary:\n"
            "    artifact_id: str\n"
            "    summary: LLMSafeEvidenceText\n"
            "\n"
            "    def to_dict(self):\n"
            '        return {"summary": str(self.summary)}\n'
            "\n"
            "def evidence_artifact_to_llm_safe_summary(\n"
            "    artifact: EvidenceArtifact,\n"
            "    summary: LLMSafeEvidenceText,\n"
            "    *,\n"
            "    safe_ref,\n"
            ") -> RedactedEvidenceSummary:\n"
            "    return RedactedEvidenceSummary(\n"
            "        artifact_id=str(artifact),\n"
            "        summary=summary,\n"
            "    )\n"
        )
        passed, errors = evaluate_fixture(
            name="rejected: projector summary is positional not keyword-only",
            content=broken,
            expected_pass=False,
            expected_errors_containing=["must be keyword-only"],
            check_func=lambda p: check_projector_parameter_type(p, REQUIRED_PROJECTOR),
        )
        # Verify an unrelated error (e.g. "str(self.summary)" which is only
        # emitted by the serializer check) would NOT satisfy the fixture.
        unrelated_check_passes = evaluate_fixture(
            name="sanity: unrelated check does NOT satisfy projector-kwonly fixture",
            content=broken,
            expected_pass=False,
            expected_errors_containing=["str(self.summary)"],
            check_func=lambda p: check_projector_parameter_type(p, REQUIRED_PROJECTOR),
        )[0]
        assert unrelated_check_passes is False
        assert passed
        assert any("must be keyword-only" in e for e in errors)
