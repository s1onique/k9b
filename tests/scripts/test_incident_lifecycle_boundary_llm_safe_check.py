"""Tests for LLM-safe evidence boundary check functions.

ACT-K9B-HULK-LLM-SAFE-EVIDENCE-BOUNDARY01.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    LLM_REVIEW_MODULES,
)
from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
    check_llm_review_unsafe_access,
    check_llm_safe_dataclass,
    check_llm_safe_evidence_contract,
    check_llm_safe_helper_signatures,
    check_llm_safe_helpers,
    check_llm_safe_type_aliases,
)

REPO_ROOT = Path(__file__).parent.parent.parent
# EVIDENCE_MODULE is the facade (re-export module) - used for backward-compat tests
EVIDENCE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence.py"
# EVIDENCE_LLM_SAFE_MODULE is the actual defining module for LLM-safe types
EVIDENCE_LLM_SAFE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_llm_safe.py"


class TestCheckLLMSafeTypeAliases:
    """Tests for LLM-safe type alias verification."""

    def test_passes_for_actual_llm_safe_module(self) -> None:
        """Actual incident_evidence_llm_safe.py passes alias checks."""
        errors = check_llm_safe_type_aliases(str(EVIDENCE_LLM_SAFE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_redacted_evidence_text_missing(self) -> None:
        """Fails if RedactedEvidenceText alias is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', str)\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_type_aliases(temp_path)
            assert len(errors) > 0
            assert any("RedactedEvidenceText" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_safe_evidence_excerpt_missing(self) -> None:
        """Fails if SafeEvidenceExcerpt alias is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_type_aliases(temp_path)
            assert len(errors) > 0
            assert any("SafeEvidenceExcerpt" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_alias_not_based_on_str(self) -> None:
        """Fails if alias is not based on str."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', int)\n")
            f.write("SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', str)\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_type_aliases(temp_path)
            assert len(errors) > 0
        finally:
            Path(temp_path).unlink()


class TestCheckLLMSafeDataclass:
    """Tests for RedactedEvidenceSummary dataclass verification."""

    def test_passes_for_actual_llm_safe_module(self) -> None:
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
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
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


class TestCheckLLMSafeHelpers:
    """Tests for helper function verification."""

    def test_passes_for_actual_llm_safe_module(self) -> None:
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
            # LLM_REVIEW_MODULES paths are relative to src/, so pass src as repo_root
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
                # Write clean module (no unsafe patterns)
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

    def test_passes_for_actual_llm_safe_module(self) -> None:
        """Actual incident_evidence_llm_safe.py passes complete contract check."""
        errors = check_llm_safe_evidence_contract(
            evidence_filepath=str(EVIDENCE_LLM_SAFE_MODULE),
            repo_root=REPO_ROOT,
        )
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_for_invalid_module(self) -> None:
        """Fails for module with missing type definitions."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("# Missing all types and helpers\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_evidence_contract(
                evidence_filepath=temp_path,
                repo_root=REPO_ROOT,
            )
            assert len(errors) > 0
        finally:
            Path(temp_path).unlink()

    def test_cli_fails_when_checker_returns_errors(self) -> None:
        """CLI should fail when LLM-safe checker returns errors."""
        # This is tested indirectly by checking that check_llm_safe_evidence_contract
        # returns non-empty errors for invalid modules
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Invalid module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("# Missing everything\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_evidence_contract(
                evidence_filepath=temp_path,
                repo_root=REPO_ROOT,
            )
            assert len(errors) > 0, "Should return errors for invalid module"
        finally:
            Path(temp_path).unlink()


class TestCheckSafeRefTypeClosure:
    """Tests for strict safe_ref type closure in dataclass and helper signatures.

    R3/R4: Verifier must reject unknown types and enforce exact closure:
    - Allowed: LLMSafeArtifactRef | ReviewPacketStorageRef | None
    - Rejected: str | None, int | None, SomeOtherRef | None, LocalArtifactPath | None, ExternalStorageRef | None
    """

    def test_dataclass_passes_for_valid_safe_ref_types(self) -> None:
        """Dataclass passes when safe_ref uses only allowed types."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("ReviewPacketStorageRef = NewType('ReviewPacketStorageRef', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: RedactedEvidenceText\n")
            f.write("    safe_ref: LLMSafeArtifactRef | ReviewPacketStorageRef | None = None\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert errors == [], f"Should pass for valid types: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_dataclass_rejects_str_safe_ref(self) -> None:
        """Dataclass fails when safe_ref uses str."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: RedactedEvidenceText\n")
            f.write("    safe_ref: str | None = None\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert len(errors) > 0, "Should reject str | None"
            assert any("unknown type" in e.lower() or "str" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_dataclass_rejects_local_artifact_path(self) -> None:
        """Dataclass fails when safe_ref uses LocalArtifactPath."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LocalArtifactPath = NewType('LocalArtifactPath', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: RedactedEvidenceText\n")
            f.write("    safe_ref: LocalArtifactPath | None = None\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert len(errors) > 0, "Should reject LocalArtifactPath | None"
            assert any("LocalArtifactPath" in e or "unsafe" in e.lower() for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_dataclass_rejects_external_storage_ref(self) -> None:
        """Dataclass fails when safe_ref uses ExternalStorageRef."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("ExternalStorageRef = NewType('ExternalStorageRef', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: RedactedEvidenceText\n")
            f.write("    safe_ref: ExternalStorageRef | None = None\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert len(errors) > 0, "Should reject ExternalStorageRef | None"
            assert any("ExternalStorageRef" in e or "unsafe" in e.lower() for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_dataclass_rejects_unknown_type_in_union(self) -> None:
        """Dataclass fails when safe_ref has unknown type in union."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("SomeOtherRef = NewType('SomeOtherRef', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: RedactedEvidenceText\n")
            f.write("    safe_ref: LLMSafeArtifactRef | SomeOtherRef | None = None\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert len(errors) > 0, "Should reject unknown type SomeOtherRef"
            assert any("unknown type" in e.lower() or "SomeOtherRef" in e for e in errors)
        finally:
            Path(temp_path).unlink()




class TestCheckLLMSafeHelperSignatures:
    """Tests for evidence_artifact_to_llm_safe_summary helper signature verification."""

    def test_passes_for_actual_llm_safe_module(self) -> None:
        """Actual incident_evidence_llm_safe.py passes helper signature checks."""
        errors = check_llm_safe_helper_signatures(str(EVIDENCE_LLM_SAFE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_rejects_str_safe_ref_in_helper(self) -> None:
        """Helper fails when safe_ref parameter uses str."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("def evidence_artifact_to_llm_safe_summary(\n")
            f.write("    artifact,\n")
            f.write("    *,\n")
            f.write("    safe_ref: str | None = None,\n")
            f.write("    summary: RedactedEvidenceText,\n")
            f.write("):\n")
            f.write("    pass\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert len(errors) > 0, "Should reject str | None in helper"
            assert any("unknown type" in e.lower() or "str" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_rejects_local_artifact_path_in_helper(self) -> None:
        """Helper fails when safe_ref parameter uses LocalArtifactPath."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LocalArtifactPath = NewType('LocalArtifactPath', str)\n")
            f.write("def evidence_artifact_to_llm_safe_summary(\n")
            f.write("    artifact,\n")
            f.write("    *,\n")
            f.write("    safe_ref: LocalArtifactPath | None = None,\n")
            f.write("    summary: RedactedEvidenceText,\n")
            f.write("):\n")
            f.write("    pass\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert len(errors) > 0, "Should reject LocalArtifactPath | None"
            assert any("LocalArtifactPath" in e or "unsafe" in e.lower() for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_rejects_external_storage_ref_in_helper(self) -> None:
        """Helper fails when safe_ref parameter uses ExternalStorageRef."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("ExternalStorageRef = NewType('ExternalStorageRef', str)\n")
            f.write("def evidence_artifact_to_llm_safe_summary(\n")
            f.write("    artifact,\n")
            f.write("    *,\n")
            f.write("    safe_ref: ExternalStorageRef | None = None,\n")
            f.write("    summary: RedactedEvidenceText,\n")
            f.write("):\n")
            f.write("    pass\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert len(errors) > 0, "Should reject ExternalStorageRef | None"
            assert any("ExternalStorageRef" in e or "unsafe" in e.lower() for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_rejects_unknown_type_in_helper_union(self) -> None:
        """Helper fails when safe_ref has unknown type in union."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("SomeOtherRef = NewType('SomeOtherRef', str)\n")
            f.write("def evidence_artifact_to_llm_safe_summary(\n")
            f.write("    artifact,\n")
            f.write("    *,\n")
            f.write("    safe_ref: LLMSafeArtifactRef | SomeOtherRef | None = None,\n")
            f.write("    summary: RedactedEvidenceText,\n")
            f.write("):\n")
            f.write("    pass\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert len(errors) > 0, "Should reject unknown type SomeOtherRef"
            assert any("unknown type" in e.lower() or "SomeOtherRef" in e for e in errors)
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
