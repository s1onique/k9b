"""Tests for LLM-safe evidence boundary check functions.

ACT-K9B-HULK-LLM-SAFE-EVIDENCE-BOUNDARY01.

The verifier enforces three independent contracts:

1. **Canonical privacy-state hierarchy** lives in
   ``incident_evidence_redaction.py``. The four canonical aliases
   (RawEvidenceText, RedactedEvidenceText, LLMSafeEvidenceText,
   SafeEvidenceExcerpt) MUST be declared there as NewType assignments
   with the exact expected supertype chain. Edge reshuffling (e.g.
   ``LLMSafeEvidenceText -> RawEvidenceText``) is rejected even when
   the chain still terminates at ``str``.

2. **Facade re-export contract**: ``incident_evidence_llm_safe.py``
   re-exports the canonical identities rather than redefining them.
   Duplicating a ``NewType`` with the same name would mint a new,
   statically distinct type and weaken privacy guarantees. The facade
   MUST also import each canonical name from the canonical module via
   a top-level ``from <canonical_module> import <name>`` statement.

3. **Strengthened dataclass contract**:
   ``RedactedEvidenceSummary.summary`` MUST be typed as
   ``LLMSafeEvidenceText`` (not ``RedactedEvidenceText``). Redacted
   text is not automatically approved for LLM exposure.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    LLM_REVIEW_MODULES,
)
from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
    SUMMARY_REQUIRED_TYPE,
    check_llm_review_unsafe_access,
    check_llm_safe_dataclass,
    check_llm_safe_evidence_contract,
    check_llm_safe_helpers,
)

REPO_ROOT = Path(__file__).parent.parent.parent
# EVIDENCE_MODULE is the facade (re-export module) - used for backward-compat tests
EVIDENCE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence.py"
# EVIDENCE_LLM_SAFE_MODULE is the facade that re-exports canonical identities.
EVIDENCE_LLM_SAFE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_llm_safe.py"
# EVIDENCE_REDACTION_MODULE is the canonical privacy-state hierarchy source.
EVIDENCE_REDACTION_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_redaction.py"


class TestCheckLLMSafeDataclass:
    """Tests for RedactedEvidenceSummary dataclass verification."""

    def test_passes_for_actual_facade(self) -> None:
        """Actual incident_evidence_llm_safe.py passes dataclass checks."""
        errors = check_llm_safe_dataclass(str(EVIDENCE_LLM_SAFE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_dataclass_missing(self) -> None:
        """Fails if RedactedEvidenceSummary dataclass is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert len(errors) > 0
            assert any("RedactedEvidenceSummary" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_summary_field_missing(self) -> None:
        """Fails if summary field is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    safe_ref: LLMSafeArtifactRef | None = None\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert len(errors) > 0
            assert any("summary" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_summary_is_just_redacted_evidence_text(self) -> None:
        """Negative proof: summary typed as RedactedEvidenceText is rejected.

        Redacted is not LLM-safe; only ``LLMSafeEvidenceText`` crosses the LLM boundary.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: RedactedEvidenceText\n")
            f.write("    safe_ref: LLMSafeArtifactRef | None = None\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert any(SUMMARY_REQUIRED_TYPE in e for e in errors), (
                f"Expected error demanding {SUMMARY_REQUIRED_TYPE}; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_if_summary_is_plain_str(self) -> None:
        """Negative proof: plain str is not a privacy-state type."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: str\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert any(SUMMARY_REQUIRED_TYPE in e for e in errors), (
                f"Expected error demanding {SUMMARY_REQUIRED_TYPE}; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()



class TestCheckLLMSafeHelpers:
    """Tests for helper function verification."""

    def test_passes_for_actual_facade(self) -> None:
        """Actual incident_evidence_llm_safe.py passes helper checks."""
        errors = check_llm_safe_helpers(str(EVIDENCE_LLM_SAFE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_helper_missing(self) -> None:
        """Fails if required helper function is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("def make_redacted_evidence_text(value: str):\n")
            f.write("    pass\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_helpers(temp_path)
            assert len(errors) > 0
            assert any("make_safe_evidence_excerpt" in e for e in errors)
        finally:
            Path(temp_path).unlink()



class TestCheckLLMReviewUnsafeAccess:
    """Tests for unsafe access pattern detection in LLM/review modules."""

    def test_detects_local_artifact_path_in_llm_module(self) -> None:
        """Detects LocalArtifactPath usage in LLM/review modules.

        Uses Path('src') as REPO_ROOT to simulate CLI/common.py behavior.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            src_root = tmp_root / "src"
            fake_llm_path = src_root / "k8s_diag_agent" / "collect" / "incident_llm_diagnosis.py"
            fake_llm_path.parent.mkdir(parents=True, exist_ok=True)
            fake_llm_path.write_text(
                '"""Fake LLM diagnosis module."""\n\n'
                'from typing import NewType\n'
                "LocalArtifactPath = NewType('LocalArtifactPath', str)\n"
                "path: LocalArtifactPath = '/var/lib/k9b/secret'\n"
            )
            errors = check_llm_review_unsafe_access(src_root)
            assert len(errors) >= 1, "Should detect LocalArtifactPath in LLM/review modules"
            assert any("incident_llm_diagnosis.py" in e for e in errors)

    def test_detects_direct_storage_ref_access(self) -> None:
        """Detects direct .storage_ref access in LLM/review modules.

        Uses Path('src') as REPO_ROOT to simulate CLI/common.py behavior.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            src_root = tmp_root / "src"
            fake_llm_path = src_root / "k8s_diag_agent" / "collect" / "incident_case_file.py"
            fake_llm_path.parent.mkdir(parents=True, exist_ok=True)
            fake_llm_path.write_text(
                '"""Fake case file module."""\n\n'
                'def build_case_file(artifact):\n'
                '    path = artifact.storage_ref\n'
                '    return path\n'
            )
            errors = check_llm_review_unsafe_access(src_root)
            assert len(errors) >= 1, "Should detect .storage_ref access"
            assert any("storage_ref" in e for e in errors)

    def test_no_violation_when_llm_modules_are_clean(self) -> None:
        """No violations when LLM modules don't use unsafe patterns.

        Uses Path('src') as REPO_ROOT to simulate CLI/common.py behavior.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            src_root = tmp_root / "src"
            for module_path in LLM_REVIEW_MODULES:
                full_path = src_root / module_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(
                    '"""Clean module."""\n\n'
                    "safe_ref = 'relative/path/to/artifact'\n"
                    "summary = 'Redacted evidence summary'\n"
                )
            errors = check_llm_review_unsafe_access(src_root)
            assert not any("LocalArtifactPath" in e for e in errors)
            assert not any("ExternalStorageRef" in e for e in errors)



class TestCheckLLMSafeEvidenceContract:
    """Tests for complete LLM-safe evidence contract check."""

    def test_passes_for_actual_modules(self) -> None:
        """Actual facade + canonical modules pass the complete contract check."""
        errors = check_llm_safe_evidence_contract(
            evidence_filepath=str(EVIDENCE_LLM_SAFE_MODULE),
            repo_root=REPO_ROOT,
        )
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_for_invalid_facade(self) -> None:
        """Fails for a facade that redefines canonical aliases."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("# Redefines RedactedEvidenceText locally - forbidden.\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_evidence_contract(
                evidence_filepath=temp_path,
                repo_root=REPO_ROOT,
            )
            assert len(errors) > 0
        finally:
            Path(temp_path).unlink()




if __name__ == "__main__":
    pytest.main([__file__, "-v"])
