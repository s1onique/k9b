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

from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
    SUMMARY_REQUIRED_TYPE,
    check_llm_safe_canonical_imports,
    check_llm_safe_dataclass,
    check_llm_safe_helper_signatures,
)

REPO_ROOT = Path(__file__).parent.parent.parent
# EVIDENCE_MODULE is the facade (re-export module) - used for backward-compat tests
EVIDENCE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence.py"
# EVIDENCE_LLM_SAFE_MODULE is the facade that re-exports canonical identities.
EVIDENCE_LLM_SAFE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_llm_safe.py"
# EVIDENCE_REDACTION_MODULE is the canonical privacy-state hierarchy source.
EVIDENCE_REDACTION_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_redaction.py"


class TestCheckSafeRefTypeClosure:
    """Tests for strict safe_ref type closure in dataclass and helper signatures.

    R3/R4: Verifier must reject unknown types and enforce exact closure:
    - Allowed: LLMSafeArtifactRef | ReviewPacketStorageRef | None
    - Rejected: str | None, int | None, SomeOtherRef | None, LocalArtifactPath | None, ExternalStorageRef | None
    """

    def test_dataclass_passes_for_valid_safe_ref_types(self) -> None:
        """Dataclass passes when safe_ref uses only allowed types and summary is LLMSafe."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("ReviewPacketStorageRef = NewType('ReviewPacketStorageRef', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: LLMSafeEvidenceText\n")
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
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: LLMSafeEvidenceText\n")
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
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("LocalArtifactPath = NewType('LocalArtifactPath', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: LLMSafeEvidenceText\n")
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
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("ExternalStorageRef = NewType('ExternalStorageRef', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: LLMSafeEvidenceText\n")
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
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("SomeOtherRef = NewType('SomeOtherRef', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: LLMSafeEvidenceText\n")
            f.write("    safe_ref: LLMSafeArtifactRef | SomeOtherRef | None = None\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert len(errors) > 0, "Should reject unknown type SomeOtherRef"
            assert any("unknown type" in e.lower() or "SomeOtherRef" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_dataclass_rejects_summary_typed_as_redacted_evidence_text(self) -> None:
        """Negative proof: summary as RedactedEvidenceText regresses to redacted state."""
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
                f"Should reject RedactedEvidenceText and demand {SUMMARY_REQUIRED_TYPE}; "
                f"got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_dataclass_rejects_plain_str_summary(self) -> None:
        """Negative proof: plain str is not a privacy-state type."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: str\n")
            f.write("    safe_ref: LLMSafeArtifactRef | None = None\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert any(SUMMARY_REQUIRED_TYPE in e for e in errors), (
                f"Should demand {SUMMARY_REQUIRED_TYPE}; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()



class TestCheckLLMSafeHelperSignatures:
    """Tests for evidence_artifact_to_llm_safe_summary helper signature verification."""

    def test_passes_for_actual_facade(self) -> None:
        """Actual incident_evidence_llm_safe.py passes helper signature checks."""
        errors = check_llm_safe_helper_signatures(str(EVIDENCE_LLM_SAFE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_rejects_str_safe_ref_in_helper(self) -> None:
        """Helper fails when safe_ref parameter uses str."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("def evidence_artifact_to_llm_safe_summary(\n")
            f.write("    artifact,\n")
            f.write("    *,\n")
            f.write("    safe_ref: str | None = None,\n")
            f.write("    summary: LLMSafeEvidenceText,\n")
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
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("LocalArtifactPath = NewType('LocalArtifactPath', str)\n")
            f.write("def evidence_artifact_to_llm_safe_summary(\n")
            f.write("    artifact,\n")
            f.write("    *,\n")
            f.write("    safe_ref: LocalArtifactPath | None = None,\n")
            f.write("    summary: LLMSafeEvidenceText,\n")
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
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("ExternalStorageRef = NewType('ExternalStorageRef', str)\n")
            f.write("def evidence_artifact_to_llm_safe_summary(\n")
            f.write("    artifact,\n")
            f.write("    *,\n")
            f.write("    safe_ref: ExternalStorageRef | None = None,\n")
            f.write("    summary: LLMSafeEvidenceText,\n")
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
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("SomeOtherRef = NewType('SomeOtherRef', str)\n")
            f.write("def evidence_artifact_to_llm_safe_summary(\n")
            f.write("    artifact,\n")
            f.write("    *,\n")
            f.write("    safe_ref: LLMSafeArtifactRef | SomeOtherRef | None = None,\n")
            f.write("    summary: LLMSafeEvidenceText,\n")
            f.write("):\n")
            f.write("    pass\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert len(errors) > 0, "Should reject unknown type SomeOtherRef"
            assert any("unknown type" in e.lower() or "SomeOtherRef" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_rejects_summary_typed_as_redacted_evidence_text_in_helper(self) -> None:
        """Negative proof: helper summary parameter as RedactedEvidenceText is rejected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("def evidence_artifact_to_llm_safe_summary(\n")
            f.write("    artifact,\n")
            f.write("    *,\n")
            f.write("    safe_ref: LLMSafeArtifactRef | None = None,\n")
            f.write("    summary: RedactedEvidenceText,\n")
            f.write("):\n")
            f.write("    pass\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert any(SUMMARY_REQUIRED_TYPE in e for e in errors), (
                f"Should demand {SUMMARY_REQUIRED_TYPE} and reject RedactedEvidenceText; "
                f"got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_rejects_helper_with_missing_summary_param(self) -> None:
        """Negative proof: ``evidence_artifact_to_llm_safe_summary`` MUST declare a
        ``summary`` parameter typed as ``LLMSafeEvidenceText``. A function
        with no ``summary`` at all leaks raw text to the LLM.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write("def evidence_artifact_to_llm_safe_summary(\n")
            f.write("    artifact,\n")
            f.write("    *,\n")
            f.write("    safe_ref: LLMSafeArtifactRef | None = None,\n")
            f.write("):\n")
            f.write("    pass\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert any(
                "summary" in e and ("declare" in e or "must" in e)
                for e in errors
            ), f"Expected missing-summary rejection; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_when_facade_rebinds_canonical_name(self) -> None:
        """Negative proof: ``from canonical import X; X = str`` is rejected.

        The canonical import is present, but a top-level rebinding
        replaces the privacy-state identity with an ordinary string,
        silently leaking raw text to the LLM.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Rebinding attempt."""\n')
            f.write(
                "from k8s_diag_agent.collect.incident_evidence_redaction import (\n"
                "    LLMSafeEvidenceText,\n"
                "    RawEvidenceText,\n"
                "    RedactedEvidenceText,\n"
                "    SafeEvidenceExcerpt,\n"
                ")\n"
                "\n"
                "RawEvidenceText = str\n"
            )
            temp_path = f.name
        try:
            errors = check_llm_safe_canonical_imports(temp_path)
            assert any("rebinds" in e.lower() for e in errors), (
                f"Expected rebinding rejection for RawEvidenceText; "
                f"got: {errors}"
            )
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
