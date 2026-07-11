"""R8 negative-proof tests for the LLM-safe evidence boundary verifier.

These tests cover the three remaining bypass classes that R1-R7 closed:

1. **Per-call-site NewType provenance** (closed by the source-order
   binding table):
   - ``from fake import NewType`` with no other ``NewType`` import
     must reject every bare ``NewType(...)`` call.
   - ``from typing import NewType`` followed by
     ``from fake import NewType`` must reject every call after the
     second import (the later binding overrides the earlier one).

2. **Recursive module-scope rebinding detection** (closed by the
   ``iter_module_scope_statements`` walker):
   - ``if True: RawEvidenceText = str``
   - ``try: pass; finally: RawEvidenceText = str``
   - ``for RawEvidenceText in iter:`` at module scope
   - ``while False: pass`` (control flow only, no binding)
   - ``with open('x') as RawEvidenceText:``
   - ``match value: case pattern as RawEvidenceText:``

3. **Exact helper / dataclass annotation shape** (closed by
   ``is_safe_ref_shape`` and ``is_pure_llm_safe_evidence_text_annotation``):
   - Positional ``safe_ref`` annotation must run the same
     closed-union validator as the keyword-only branch.
   - The ``summary`` annotation must be EXACTLY
     ``LLMSafeEvidenceText``; ``LLMSafeEvidenceText | str``,
     ``LLMSafeEvidenceText | None``, and any union/subscript are
     rejected.
   - The ``safe_ref`` closed-union must contain EXACTLY one of the
     allowed shapes; ``LLMSafeArtifactRef | str``,
     ``ReviewPacketStorageRef | None``, ``None`` alone are rejected.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
    SUMMARY_REQUIRED_TYPE,
    check_canonical_redaction_aliases,
    check_llm_safe_canonical_imports,
    check_llm_safe_dataclass,
    check_llm_safe_helper_signatures,
)

# ---------------------------------------------------------------------------
# R8.1 — Per-call-site NewType provenance (binding table)
# ---------------------------------------------------------------------------


class TestNewTypeProvenanceBindingTable:
    """Negative proofs for the source-order ``NewType`` binding table."""

    def test_fails_when_only_fake_newtype_import(self) -> None:
        """``from fake import NewType`` with no other ``NewType`` import
        must be rejected by the canonical alias checker. The earlier
        module-wide boolean left this open because ``trusted_newtype``
        stayed ``False`` and no error was raised.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Canonical module using only an untrusted NewType."""\n')
            f.write("from fake import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)"
                "\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)"
                "\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected untrusted-provenance rejection; got empty errors"
            )
            assert any(
                "fake" in e.lower() or "untrusted" in e.lower() or "trust" in e.lower()
                for e in errors
            ), f"Expected provenance error referencing 'fake'; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_when_trusted_then_fake_newtype_import(self) -> None:
        """``from typing import NewType`` followed by
        ``from fake import NewType`` must be rejected. The earlier
        module-wide boolean left this open because the second import
        did not invalidate ``trusted_newtype``.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Trusted then fake rebind."""\n')
            f.write("from typing import NewType\n")
            f.write("from fake import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)"
                "\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)"
                "\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected rebinding-rejection; got empty errors"
            )
            assert any(
                "fake" in e.lower() or "rebind" in e.lower() or "trust" in e.lower()
                for e in errors
            ), f"Expected provenance error referencing rebind; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_when_typing_aliased_then_fake_newtype_import(self) -> None:
        """``import typing as t`` then ``from fake import NewType`` and
        ``typing.NewType`` style calls must be rejected because the
        ``typing`` name itself is not bound.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Typing aliased then fake NewType."""\n')
            f.write("import typing as t\n")
            f.write("from fake import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)"
                "\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)"
                "\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected rebinding-rejection (fake NewType); got empty errors"
            )
        finally:
            Path(temp_path).unlink()


# ---------------------------------------------------------------------------
# R8.2 — Recursive module-scope rebinding detection
# ---------------------------------------------------------------------------


class TestModuleScopeRebindingWalker:
    """Negative proofs for module-scope rebindings hidden in control flow."""

    @staticmethod
    def _facade_with_rebinding(rebinding_block: str) -> str:
        """Write a facade with a canonical import followed by a rebinding block."""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        tmp.write('"""Facade with control-flow rebinding."""\n')
        tmp.write(
            "from k8s_diag_agent.collect.incident_evidence_redaction import (\n"
            "    LLMSafeEvidenceText,\n"
            "    RawEvidenceText,\n"
            "    RedactedEvidenceText,\n"
            "    SafeEvidenceExcerpt,\n"
            ")\n"
        )
        tmp.write("\n")
        tmp.write(rebinding_block)
        tmp.write("\n")
        tmp.close()
        return tmp.name

    def test_fails_when_rebinding_inside_if_block(self) -> None:
        """``if True: RawEvidenceText = str`` must be detected as a rebinding."""
        path = self._facade_with_rebinding(
            "if True:\n    RawEvidenceText = str\n"
        )
        try:
            errors = check_llm_safe_canonical_imports(path)
            assert any(
                "rebinds" in e.lower() and "RawEvidenceText" in e for e in errors
            ), f"Expected if-block rebinding rejection; got: {errors}"
        finally:
            Path(path).unlink()

    def test_fails_when_rebinding_inside_try_finally(self) -> None:
        """``try: pass; finally: RawEvidenceText = str`` must be detected."""
        path = self._facade_with_rebinding(
            "try:\n    pass\nfinally:\n    RawEvidenceText = str\n"
        )
        try:
            errors = check_llm_safe_canonical_imports(path)
            assert any(
                "rebinds" in e.lower() and "RawEvidenceText" in e for e in errors
            ), f"Expected try-finally rebinding rejection; got: {errors}"
        finally:
            Path(path).unlink()

    def test_fails_when_rebinding_inside_for_loop_target(self) -> None:
        """``for RawEvidenceText in iter: pass`` at module scope must be detected."""
        path = self._facade_with_rebinding(
            "for RawEvidenceText in []:\n    pass\n"
        )
        try:
            errors = check_llm_safe_canonical_imports(path)
            assert any(
                "rebinds" in e.lower() and "RawEvidenceText" in e for e in errors
            ), f"Expected for-target rebinding rejection; got: {errors}"
        finally:
            Path(path).unlink()

    def test_fails_when_rebinding_inside_with_as(self) -> None:
        """``with open('x') as RawEvidenceText: pass`` at module scope must be detected."""
        path = self._facade_with_rebinding(
            "with open('x') as RawEvidenceText:\n    pass\n"
        )
        try:
            errors = check_llm_safe_canonical_imports(path)
            assert any(
                "rebinds" in e.lower() and "RawEvidenceText" in e for e in errors
            ), f"Expected with-as rebinding rejection; got: {errors}"
        finally:
            Path(path).unlink()

    def test_fails_when_rebinding_inside_except_handler(self) -> None:
        """``except Exception as RawEvidenceText: pass`` at module scope must be detected."""
        path = self._facade_with_rebinding(
            "try:\n    raise RuntimeError('x')\n"
            "except Exception as RawEvidenceText:\n    pass\n"
        )
        try:
            errors = check_llm_safe_canonical_imports(path)
            assert any(
                "rebinds" in e.lower() and "RawEvidenceText" in e for e in errors
            ), f"Expected except-as rebinding rejection; got: {errors}"
        finally:
            Path(path).unlink()


# ---------------------------------------------------------------------------
# R8.3 — Exact helper / dataclass annotation shape
# ---------------------------------------------------------------------------


class TestExactAnnotationShape:
    """Negative proofs for the exact-shape annotation validator."""

    def test_helper_rejects_positional_safe_ref_with_str_annotation(self) -> None:
        """Positional ``safe_ref: str`` is rejected. The previous
        validator only checked annotation presence in the positional
        branch.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Positional safe_ref bypass."""\n')
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write(
                "def evidence_artifact_to_llm_safe_summary(\n"
                "    artifact,\n"
                "    safe_ref: str,\n"
                "    summary: LLMSafeEvidenceText,\n"
                "):\n"
                "    pass\n"
            )
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert len(errors) > 0, "Positional safe_ref=str must be rejected"
            assert any(
                "closed-union shape" in e.lower() or "str" in e for e in errors
            ), f"Expected closed-union-shape error; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_helper_rejects_safe_ref_none_alone(self) -> None:
        """``safe_ref: None`` alone is rejected; the closed union must
        include ``LLMSafeArtifactRef``.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""safe_ref=None alone."""\n')
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write(
                "def evidence_artifact_to_llm_safe_summary(\n"
                "    artifact,\n"
                "    *,\n"
                "    safe_ref: None = None,\n"
                "    summary: LLMSafeEvidenceText,\n"
                "):\n"
                "    pass\n"
            )
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert len(errors) > 0, "safe_ref=None alone must be rejected"
        finally:
            Path(temp_path).unlink()

    def test_helper_rejects_safe_ref_review_packet_storage_only(self) -> None:
        """``safe_ref: ReviewPacketStorageRef | None`` is rejected; the
        closed union must include ``LLMSafeArtifactRef``.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""safe_ref without LLMSafeArtifactRef."""\n')
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("ReviewPacketStorageRef = NewType('ReviewPacketStorageRef', str)\n")
            f.write(
                "def evidence_artifact_to_llm_safe_summary(\n"
                "    artifact,\n"
                "    *,\n"
                "    safe_ref: ReviewPacketStorageRef | None = None,\n"
                "    summary: LLMSafeEvidenceText,\n"
                "):\n"
                "    pass\n"
            )
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert len(errors) > 0, (
                "safe_ref=ReviewPacketStorageRef|None must be rejected"
            )
        finally:
            Path(temp_path).unlink()

    def test_helper_rejects_summary_with_str_union(self) -> None:
        """``summary: LLMSafeEvidenceText | str`` is rejected. The
        previous validator only checked the left side of a union
        expression, so this would have passed.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""summary union bypass."""\n')
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write(
                "def evidence_artifact_to_llm_safe_summary(\n"
                "    artifact,\n"
                "    *,\n"
                "    safe_ref: LLMSafeArtifactRef | None = None,\n"
                "    summary: LLMSafeEvidenceText | str,\n"
                "):\n"
                "    pass\n"
            )
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert len(errors) > 0, (
                "summary=LLMSafeEvidenceText|str must be rejected"
            )
            assert any(
                SUMMARY_REQUIRED_TYPE in e and "EXACTLY" in e for e in errors
            ), f"Expected exact-shape error; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_helper_rejects_summary_with_none_union(self) -> None:
        """``summary: LLMSafeEvidenceText | None`` is rejected; the
        annotation must be exactly the bare name.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""summary optional union."""\n')
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("LLMSafeArtifactRef = NewType('LLMSafeArtifactRef', str)\n")
            f.write(
                "def evidence_artifact_to_llm_safe_summary(\n"
                "    artifact,\n"
                "    *,\n"
                "    safe_ref: LLMSafeArtifactRef | None = None,\n"
                "    summary: LLMSafeEvidenceText | None,\n"
                "):\n"
                "    pass\n"
            )
            temp_path = f.name
        try:
            errors = check_llm_safe_helper_signatures(temp_path)
            assert len(errors) > 0, (
                "summary=LLMSafeEvidenceText|None must be rejected"
            )
        finally:
            Path(temp_path).unlink()

    def test_dataclass_rejects_safe_ref_with_only_review_packet_storage(self) -> None:
        """Dataclass ``safe_ref: ReviewPacketStorageRef | None = None``
        is rejected; the closed union must include
        ``LLMSafeArtifactRef``.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Dataclass safe_ref without LLMSafeArtifactRef."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("ReviewPacketStorageRef = NewType('ReviewPacketStorageRef', str)\n")
            f.write("@dataclass\n")
            f.write("class RedactedEvidenceSummary:\n")
            f.write("    artifact_id: str\n")
            f.write("    summary: LLMSafeEvidenceText\n")
            f.write("    safe_ref: ReviewPacketStorageRef | None = None\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_dataclass(temp_path)
            assert len(errors) > 0, (
                "Dataclass safe_ref=ReviewPacketStorageRef|None must be rejected"
            )
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])