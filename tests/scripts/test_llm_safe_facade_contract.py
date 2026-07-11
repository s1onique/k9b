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
    check_llm_safe_canonical_imports,
    check_llm_safe_type_aliases,
)

REPO_ROOT = Path(__file__).parent.parent.parent
# EVIDENCE_MODULE is the facade (re-export module) - used for backward-compat tests
EVIDENCE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence.py"
# EVIDENCE_LLM_SAFE_MODULE is the facade that re-exports canonical identities.
EVIDENCE_LLM_SAFE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_llm_safe.py"
# EVIDENCE_REDACTION_MODULE is the canonical privacy-state hierarchy source.
EVIDENCE_REDACTION_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_redaction.py"


class TestCheckLLMSafeTypeAliases:
    """Tests for the facade no-local-NewType contract."""

    def test_passes_for_actual_facade(self) -> None:
        """Actual incident_evidence_llm_safe.py is a pure facade (no local NewType)."""
        errors = check_llm_safe_type_aliases(str(EVIDENCE_LLM_SAFE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_facade_redefines_canonical_alias_locally(self) -> None:
        """Negative proof: defining RedactedEvidenceText as a local NewType fails."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_type_aliases(temp_path)
            assert any("RedactedEvidenceText" in e for e in errors), (
                f"Expected error about RedactedEvidenceText; got: {errors}"
            )
            assert any("facade must NOT redefine" in e for e in errors), (
                f"Expected redefinition-specific error; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_if_facade_redefines_safe_evidence_excerpt_locally(self) -> None:
        """Negative proof: SafeEvidenceExcerpt cannot be re-defined in the facade."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', str)\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_type_aliases(temp_path)
            assert any("SafeEvidenceExcerpt" in e for e in errors), (
                f"Expected error about SafeEvidenceExcerpt; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_if_facade_redefines_llm_safe_evidence_text(self) -> None:
        """Negative proof: LLMSafeEvidenceText is also a canonical identity."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_type_aliases(temp_path)
            assert any("LLMSafeEvidenceText" in e for e in errors), (
                f"Expected error about LLMSafeEvidenceText; got: {errors}"
            )
            assert any("RedactedEvidenceText" in e for e in errors), (
                f"Expected error about RedactedEvidenceText; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_if_facade_uses_untrusted_newtype_source(self) -> None:
        """Negative proof: ``from fake import NewType`` is rejected.

        The bare ``NewType`` name must trace to a trusted import
        (``typing``). A facade that imports ``NewType`` from an
        arbitrary module cannot prove provenance of the privacy-state
        constructor.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Smuggled NewType from untrusted source."""\n')
            f.write("from fake import NewType\n\n")
            f.write("Foo = NewType('Foo', str)\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_type_aliases(temp_path)
            assert any(
                "untrusted" in e.lower() or "typing" in e.lower()
                for e in errors
            ), (
                f"Expected untrusted-source rejection; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_passes_for_pure_import_facade(self) -> None:
        """A facade that only re-exports (no local NewType declarations) passes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from somewhere import RedactedEvidenceText\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_type_aliases(temp_path)
            assert errors == [], f"Pure-import facade should pass: {errors}"
        finally:
            Path(temp_path).unlink()



class TestCheckLLMSafeCanonicalImports:
    """Tests for the facade canonical-import contract."""

    def test_passes_for_actual_facade(self) -> None:
        """Actual incident_evidence_llm_safe.py imports from canonical module."""
        errors = check_llm_safe_canonical_imports(str(EVIDENCE_LLM_SAFE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_facade_has_no_canonical_imports(self) -> None:
        """Negative proof: a facade with no imports fails."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("import os\n")
            temp_path = f.name
        try:
            errors = check_llm_safe_canonical_imports(temp_path)
            assert len(errors) >= 4, (
                f"Expected errors for all four canonical aliases; got: {errors}"
            )
            for canonical_name in (
                "RawEvidenceText",
                "RedactedEvidenceText",
                "LLMSafeEvidenceText",
                "SafeEvidenceExcerpt",
            ):
                assert any(canonical_name in e for e in errors), (
                    f"Expected error about {canonical_name}; got: {errors}"
                )
        finally:
            Path(temp_path).unlink()

    def test_fails_if_facade_imports_canonical_from_wrong_module(self) -> None:
        """Negative proof: importing from the wrong module is rejected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write(
                "from some.unrelated.module import (\n"
                "    LLMSafeEvidenceText,\n"
                "    RawEvidenceText,\n"
                "    RedactedEvidenceText,\n"
                "    SafeEvidenceExcerpt,\n"
                ")\n"
            )
            temp_path = f.name
        try:
            errors = check_llm_safe_canonical_imports(temp_path)
            assert len(errors) >= 1, (
                f"Expected wrong-source errors; got: {errors}"
            )
            assert any("some.unrelated.module" in e for e in errors), (
                f"Expected error referencing wrong module; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_passes_when_all_canonical_names_imported_from_canonical_module(self) -> None:
        """A facade that imports every canonical name from the canonical module passes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write(
                "from k8s_diag_agent.collect.incident_evidence_redaction import (\n"
                "    LLMSafeEvidenceText,\n"
                "    RawEvidenceText,\n"
                "    RedactedEvidenceText,\n"
                "    SafeEvidenceExcerpt,\n"
                ")\n"
            )
            temp_path = f.name
        try:
            errors = check_llm_safe_canonical_imports(temp_path)
            assert errors == [], f"Canonical-import facade should pass: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_rejects_alias_bypass_via_asname(self) -> None:
        """``from canonical import SomethingElse as RawEvidenceText`` is rejected.

        Preserving ``original_name`` defeats the alias-as-bypass: the local
        name ``RawEvidenceText`` would otherwise look canonical, but the
        actual imported symbol is ``SomethingElse``.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Alias bypass attempt."""\n')
            f.write(
                "from k8s_diag_agent.collect.incident_evidence_redaction import (\n"
                "    SomethingElse as LLMSafeEvidenceText,\n"
                "    SomethingElse as RawEvidenceText,\n"
                "    SomethingElse as RedactedEvidenceText,\n"
                "    SomethingElse as SafeEvidenceExcerpt,\n"
                ")\n"
            )
            temp_path = f.name
        try:
            errors = check_llm_safe_canonical_imports(temp_path)
            assert len(errors) >= 4, (
                f"Expected alias-bypass to be rejected for all four canonical "
                f"names; got: {errors}"
            )
            for canonical_name in (
                "LLMSafeEvidenceText",
                "RawEvidenceText",
                "RedactedEvidenceText",
                "SafeEvidenceExcerpt",
            ):
                assert any(
                    canonical_name in e and "SomethingElse" in e
                    for e in errors
                ), (
                    f"Expected error about {canonical_name} aliasing from "
                    f"SomethingElse; got: {errors}"
                )
        finally:
            Path(temp_path).unlink()

    def test_partial_canonical_imports_surface_missing_names(self) -> None:
        """A facade that imports some but not all canonical names fails for the rest."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Partial canonical imports."""\n')
            f.write(
                "from k8s_diag_agent.collect.incident_evidence_redaction import (\n"
                "    LLMSafeEvidenceText,\n"
                "    RedactedEvidenceText,\n"
                ")\n"
            )
            temp_path = f.name
        try:
            errors = check_llm_safe_canonical_imports(temp_path)
            missing_names = {"RawEvidenceText", "SafeEvidenceExcerpt"}
            surfaced = {
                name for name in missing_names if any(name in e for e in errors)
            }
            assert surfaced == missing_names, (
                f"Expected errors for {missing_names}; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()




if __name__ == "__main__":
    pytest.main([__file__, "-v"])
