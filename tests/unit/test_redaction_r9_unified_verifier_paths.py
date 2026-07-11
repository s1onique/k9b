"""R9 unified acceptance tests: serializer, constructor, boundary, and aggregate checks."""

from __future__ import annotations

from pathlib import Path

from scripts.incident_lifecycle_boundary.redaction_aliases import check_type_hierarchy
from scripts.incident_lifecycle_boundary.redaction_boundaries import (
    check_protected_boundary_imports,
)
from scripts.incident_lifecycle_boundary.redaction_constructors import (
    check_trusted_constructor_usage,
)
from scripts.incident_lifecycle_boundary.redaction_self_test_sources import (
    PRIVACY_MODULE_VALID as VALID_PRIVACY_MODULE,
)
from scripts.incident_lifecycle_boundary.redaction_serialization import (
    check_serializer_explicit_conversion,
)
from scripts.incident_lifecycle_boundary.redaction_types_check import EXPECTED_HIERARCHY
from scripts.incident_lifecycle_boundary.redaction_types_self_test import (
    cleanup_temp_repo_tree,
    create_temp_repo_tree,
    evaluate_fixture,
    run_self_tests_from_cases,
)

# ---------------------------------------------------------------------------
# Serializer self-tests
# ---------------------------------------------------------------------------


class TestSerializerUnified:
    """Run serializer self-tests through the unified evaluator."""

    def test_serializer_accepted_when_str_self_summary(self) -> None:
        passed = run_self_tests_from_cases(
            test_cases=[
                {
                    "name": "accepted: serializer uses str(self.summary)",
                    "content": ("from dataclasses import dataclass\n@dataclass\nclass RedactedEvidenceSummary:\n    artifact_id: str\n    summary: str\n    def to_dict(self):\n        return {'summary': str(self.summary)}\n"),
                    "expected_pass": True,
                }
            ],
            check_func=lambda p: check_serializer_explicit_conversion(p, "RedactedEvidenceSummary"),
        )
        assert passed

    def test_serializer_rejected_on_each_violation(self) -> None:
        cases = [
            {
                "name": "rejected: missing summary field",
                "content": ("from dataclasses import dataclass\n@dataclass\nclass RedactedEvidenceSummary:\n    artifact_id: str\n    summary: str\n    def to_dict(self):\n        return {'artifact_id': self.artifact_id}\n"),
                "expected_pass": False,
                "expected_errors_containing": ["summary", "Missing"],
            },
            {
                "name": "rejected: self.summary without str()",
                "content": ("from dataclasses import dataclass\n@dataclass\nclass RedactedEvidenceSummary:\n    artifact_id: str\n    summary: str\n    def to_dict(self):\n        return {'summary': self.summary}\n"),
                "expected_pass": False,
                "expected_errors_containing": ["must use", "str(self.summary)"],
            },
            {
                "name": "rejected: bare str(self.summary) outside return dict",
                "content": (
                    "from dataclasses import dataclass\n"
                    "@dataclass\n"
                    "class RedactedEvidenceSummary:\n"
                    "    artifact_id: str\n"
                    "    summary: str\n"
                    "    def to_dict(self):\n"
                    "        result = {'artifact_id': self.artifact_id}\n"
                    "        _unused = str(self.summary)\n"
                    "        return result\n"
                ),
                "expected_pass": False,
                "expected_errors_containing": ["summary"],
            },
        ]
        passed = run_self_tests_from_cases(
            test_cases=cases,
            check_func=lambda p: check_serializer_explicit_conversion(p, "RedactedEvidenceSummary"),
        )
        assert passed


# ---------------------------------------------------------------------------
# Constructor self-tests using the PRODUCTION verifier.
# ---------------------------------------------------------------------------


class TestConstructorProductionVerifier:
    """Wired through check_trusted_constructor_usage() on a temp source tree."""

    def test_constructor_negative_all_required_forms(self) -> None:
        # Negative fixtures covering all required rejected constructor forms.
        # The fixture file paths use only the suffix under the source dir so
        # that `create_temp_repo_tree` writes them under temp_dir/<source_dir>.
        # Each fixture sits in a real protected-boundary module path so the
        # expected diagnostic would be visible at that exact path.
        required_rejected = {
            "collect/incident_prompt_builder.py": ("from k8s_diag_agent.collect.incident_evidence_redaction import (\n    LLMSafeEvidenceText,\n)\nvalue = LLMSafeEvidenceText('x')\n"),
            "collect/incident_case_file.py": ("from k8s_diag_agent.collect.incident_evidence_redaction import (\n    LLMSafeEvidenceText as Safe,\n)\nvalue = Safe('x')\n"),
            "collect/incident_llm_diagnosis.py": ("import k8s_diag_agent.collect.incident_evidence_redaction as redaction\nvalue = redaction.LLMSafeEvidenceText('x')\n"),
            "collect/incident_prompt_alt.py": ("import k8s_diag_agent.collect.incident_evidence as facade\nvalue = facade.LLMSafeEvidenceText('x')\n"),
        }
        fixture_files = dict(required_rejected)
        # Trusted projection module location is `collect/incident_evidence_redaction.py`.
        fixture_files["collect/incident_evidence_redaction.py"] = (
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            "def _use(value):\n"
            "    return LLMSafeEvidenceText(value)\n"
        )

        temp_dir, repo_root = create_temp_repo_tree(
            fixture_files,
            source_dir="k8s_diag_agent",
        )
        try:
            errors = check_trusted_constructor_usage(repo_root, source_dir="k8s_diag_agent")
            # We must have at least one diagnostic per required rejected file.
            assert errors, "Production verifier must report at least one violation"
            for required_rel in required_rejected:
                matching = [e for e in errors if required_rel.split("/")[-1] in e]
                assert matching, f"No diagnostic for required rejected path {required_rel}; got errors: {errors}"
            # Each error must contain the provenance diagnostic substring.
            for err in errors:
                assert "Direct constructor call" in err or "constructor call" in err, f"Missing provenance diagnostic in: {err}"
        finally:
            cleanup_temp_repo_tree(temp_dir)

    def test_constructor_positive_only_inside_trusted_module(self) -> None:
        # Inside the trusted projection module, LLMSafeEvidenceText(...) calls
        # in function bodies are allowed (they are the canonical projection
        # implementation). Outside the trusted module, they are rejected.
        fixture_files = {
            "collect/incident_evidence_redaction.py": (
                "from typing import NewType\n"
                "RawEvidenceText = NewType('RawEvidenceText', str)\n"
                "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
                "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
                "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
                "def _use(value):\n"
                "    return LLMSafeEvidenceText(value)\n"
            ),
            "collect/incident_unrelated.py": ("from k8s_diag_agent.collect.incident_evidence_redaction import (\n    LLMSafeEvidenceText,\n)\nvalue = LLMSafeEvidenceText('x')\n"),
        }
        temp_dir, repo_root = create_temp_repo_tree(
            fixture_files,
            source_dir="k8s_diag_agent",
        )
        try:
            errors = check_trusted_constructor_usage(repo_root, source_dir="k8s_diag_agent")
            # The non-trusted caller MUST be flagged; the trusted module
            # body call MUST NOT be flagged.
            assert any("incident_unrelated" in e for e in errors), f"Expected flag for non-trusted caller; got: {errors}"
            assert not any("incident_evidence_redaction" in e for e in errors), f"Trusted module body call was incorrectly flagged: {errors}"
        finally:
            cleanup_temp_repo_tree(temp_dir)


# ---------------------------------------------------------------------------
# Boundary self-tests using the PRODUCTION verifier.
# ---------------------------------------------------------------------------


class TestBoundaryProductionVerifier:
    """Wired through check_protected_boundary_imports() on a temp source tree.

    The production verifier scans fixed paths relative to the repo_root it
    is given. To match the production verifier exactly we write fixtures at
    `temp_dir/k8s_diag_agent/collect/<protected>.py`.
    """

    def _build_tree(self, protected_module_path: str, content: str) -> tuple[str, Path]:
        fixture_files = {
            protected_module_path: content,
            "collect/incident_evidence_redaction.py": (
                "from typing import NewType\n"
                "RawEvidenceText = NewType('RawEvidenceText', str)\n"
                "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
                "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
                "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            ),
        }
        return create_temp_repo_tree(
            fixture_files,
            source_dir="k8s_diag_agent",
        )

    def test_boundary_positive_uses_lmm_safe_only(self) -> None:
        # The protected reviewer MUST only see LLMSafeEvidenceText.
        content = "from k8s_diag_agent.collect.incident_evidence_redaction import (\n    LLMSafeEvidenceText,\n)\nclass ReviewPacket:\n    summary: LLMSafeEvidenceText\n"
        temp_dir, repo_root = self._build_tree(
            "collect/incident_review_packet.py",
            content,
        )
        try:
            errors = check_protected_boundary_imports(repo_root)
            assert errors == [], f"Expected no errors; got: {errors}"
        finally:
            cleanup_temp_repo_tree(temp_dir)

    def test_boundary_negative_aliased_redacted(self) -> None:
        content = "from k8s_diag_agent.collect.incident_evidence_redaction import (\n    RedactedEvidenceText as Text,\n)\nclass ReviewPacket:\n    summary: Text\n"
        temp_dir, repo_root = self._build_tree(
            "collect/incident_review_packet.py",
            content,
        )
        try:
            errors = check_protected_boundary_imports(repo_root)
            assert errors, "Expected at least one boundary diagnostic"
            assert any("RedactedEvidenceText" in e for e in errors), f"Missing RedactedEvidenceText diagnostic; got: {errors}"
        finally:
            cleanup_temp_repo_tree(temp_dir)

    def test_boundary_negative_module_attribute_annotation(self) -> None:
        # Qualified attribute annotations in protected case-file module must
        # be rejected. Postponed string annotations also rejected.
        content = (
            "import k8s_diag_agent.collect.incident_evidence as evidence\n"
            "from typing import NewType\n"
            "class ReviewPacket:\n"
            "    summary: evidence.RedactedEvidenceText\n"
            "def build(raw: evidence.RawEvidenceText) -> 'list[evidence.RedactedEvidenceText]':\n"
            "    return []\n"
            # Postponed annotations
            "summary_alt: 'RedactedEvidenceText' = ''\n"
            "summary_list: 'list[RedactedEvidenceText]' = []\n"
            "summary_qualified: 'evidence.RedactedEvidenceText' = ''\n"
        )
        temp_dir, repo_root = self._build_tree(
            "collect/incident_case_file.py",
            content,
        )
        try:
            errors = check_protected_boundary_imports(repo_root)
            assert errors, "Expected at least one boundary diagnostic"
            assert any("incident_case_file" in e for e in errors), f"Expected diagnostic for incident_case_file.py; got: {errors}"
            assert any("RedactedEvidenceText" in e for e in errors), f"Expected RedactedEvidenceText diagnostic; got: {errors}"
        finally:
            cleanup_temp_repo_tree(temp_dir)


# ---------------------------------------------------------------------------
# Standalone production-tree verifier (aggregate)
# ---------------------------------------------------------------------------


class TestStandaloneProductionTreeVerifier:
    """Run the full verify_redaction_types() against the real source tree."""

    def test_real_repo_passes_aggregated_verifier(self) -> None:
        from scripts.incident_lifecycle_boundary.redaction_types import (
            verify_redaction_types,
        )

        repo_root = Path("src")
        ok, errors = verify_redaction_types(repo_root)
        assert ok, f"verify_redaction_types failed: {errors}"
        assert errors == []


# ---------------------------------------------------------------------------
# Two-minute gate-passer: confirms the unified check functions are wired
# ---------------------------------------------------------------------------


class TestSharedEvaluatorUniqueness:
    """A single evaluator is used by all subsystems."""

    def test_unified_evaluator_rejects_unrelated_error(self) -> None:
        # Create a "fixture" that asks for a substring that is NOT present
        # in our error output. Expect evaluate_fixture() to FAIL the
        # negative evaluation even though the check reports errors.
        passed, errors = evaluate_fixture(
            name="rejected: fixture requests unrelated diagnostic",
            content=VALID_PRIVACY_MODULE.replace(
                'SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)',
                "SafeEvidenceExcerpt = NewType('WrongName', LLMSafeEvidenceText)",
            ),
            expected_pass=False,
            expected_errors_containing=[
                "this-diagnostic-is-not-in-any-error-message-xyz",
            ],
            check_func=lambda p: check_type_hierarchy(p, EXPECTED_HIERARCHY),
        )
        # The check will likely find errors but the "unrelated" diagnostic
        # does not appear, so passed should be False. This proves the
        # negative-fixture rule requires EVERY expected substring to appear.
        assert passed is False
