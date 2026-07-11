"""R14 negative-proof tests for the LLM-safe evidence boundary verifier.

R14 closes four bypasses that the R12/R13 implementation silently
accepted:

1. **Source-root vs repository-root path contract** (R14 #1):
   ``check_llm_safe_evidence_contract`` previously hard-coded the
   canonical path as ``<repo>/src/k8s_diag_agent/collect/...`` even
   when ``repo_root`` was already the Python source root. The
   negative-proofs harness in
   :mod:`scripts.incident_lifecycle_boundary.redaction_full_gate_negative_proofs`
   creates a tree at ``<temp>/k8s_diag_agent/...`` (source-root
   shape, NOT ``<temp>/src/k8s_diag_agent/...``) and the aggregate
   verifier silently resolved the canonical path to a non-existent
   file. R14 introduces :func:`_resolve_source_root` that auto-
   detects both layouts.

2. **Conditional ``AugAssign``/``Delete`` rebinding** (R14 #3):
   ``_statement_rebinds_provenance_sensitive()`` previously matched
   ``Assign``/``AnnAssign`` but NOT ``AugAssign`` or ``Delete``;
   the conditional scanner silently accepted rebindings of those
   forms.

3. **Duplicate canonical-alias declarations** (R14 #4):
   :func:`validate_canonical_alias_super_types` previously let two
   top-level ``RawEvidenceText = NewType("RawEvidenceText", str)``
   assignments coexist; the second binding silently overwrote the
   first.

4. **Post-declaration rebinding of canonical aliases** (R14 #4):
   ``RawEvidenceText = NewType(...)`` followed by
   ``RawEvidenceText = int`` was only detected when a LATER alias
   consumed ``RawEvidenceText`` as a supertype; an unreferenced
   rebinding was silently accepted.

5. **Module-scope conditional shadowing of ``str`` and canonical
   alias names** (R14 #5):
   ``if condition: RedactedEvidenceText = int`` before the
   canonical chain was silently accepted when no later alias
   referenced ``RedactedEvidenceText`` after the rebinding.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary._llm_safe_alias_supertypes import (
    validate_canonical_alias_super_types,
)
from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
    check_newtype_provenance,
)

REPO_ROOT = Path(__file__).parent.parent.parent
EXPECTED_ALIASES = frozenset(
    {
        "RawEvidenceText",
        "RedactedEvidenceText",
        "LLMSafeEvidenceText",
        "SafeEvidenceExcerpt",
    }
)


def _parse(source: str):
    """Helper: parse ``source`` into an ``ast.Module``."""
    import ast as _ast

    return _ast.parse(source)


def _provenance_errors(source: str) -> list[str]:
    """Run the per-call-site provenance check on ``source``."""
    return check_newtype_provenance(_parse(source), "<synthetic>")


def _supertype_errors(source: str) -> list[str]:
    """Run the canonical alias supertype validator on ``source``."""
    return validate_canonical_alias_super_types(
        _parse(source), "<synthetic>", EXPECTED_ALIASES
    )


class TestConditionalAugAssignDeleteIsRejected:
    """R14 #3: ``AugAssign`` / ``Delete`` inside conditionals fail closed."""

    def test_conditional_augassign_of_typing_is_rejected(self) -> None:
        """``if cond: typing += X`` is rejected (no later call follows)."""
        source = (
            '"""AugAssign rebinding of typing inside if."""\n'
            "import typing\n"
            "if True:\n"
            "    typing += 1\n"
        )
        errors = _provenance_errors(source)
        assert any(
            "module-scope rebinding" in e.lower()
            and "conditional" in e.lower()
            for e in errors
        ), f"Expected conditional AugAssign rejection; got: {errors}"

    def test_conditional_del_of_newtype_is_rejected(self) -> None:
        """``if cond: del NewType`` is rejected."""
        source = (
            '"""Delete of NewType inside if."""\n'
            "from typing import NewType\n"
            "if True:\n"
            "    del NewType\n"
        )
        errors = _provenance_errors(source)
        assert any(
            "module-scope rebinding" in e.lower()
            and "conditional" in e.lower()
            for e in errors
        ), f"Expected conditional Delete rejection; got: {errors}"

    def test_try_finally_del_typing_is_rejected(self) -> None:
        """``finally: del typing`` is rejected."""
        source = (
            '"""Delete of typing in try/finally."""\n'
            "import typing\n"
            "try:\n"
            "    pass\n"
            "finally:\n"
            "    del typing\n"
        )
        errors = _provenance_errors(source)
        assert any(
            "module-scope rebinding" in e.lower()
            and "conditional" in e.lower()
            for e in errors
        ), f"Expected conditional Delete rejection; got: {errors}"


class TestDuplicateCanonicalAliasDeclIsRejected:
    """R14 #4: ``Name = NewType(... Name ...)`` twice in one module fails."""

    def test_duplicate_raw_evidence_text_decl_is_rejected(self) -> None:
        source = (
            '"""Duplicate RawEvidenceText declaration."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "raw" in e.lower()
            and ("more than once" in e.lower() or "duplicate" in e.lower())
            for e in errors
        ), f"Expected duplicate-declaration rejection; got: {errors}"

    def test_post_declaration_rebinding_is_rejected(self) -> None:
        """Rebinding a canonical alias after declaration emits a diagnostic."""
        source = (
            '"""Post-declaration rebinding."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RawEvidenceText = int\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "raw" in e.lower() and "rebound" in e.lower()
            for e in errors
        ), f"Expected post-declaration rebinding rejection; got: {errors}"


class TestConditionalSuperTypeShadowingIsRejected:
    """R14 #5: conditional rebinding of ``str`` or canonical aliases fails."""

    def test_conditional_str_shadowing_is_rejected(self) -> None:
        """``if cond: str = int`` before canonical declarations fails."""
        source = (
            '"""Conditional str shadowing."""\n'
            "from typing import NewType\n"
            "if True:\n"
            "    str = int\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "conditional rebinding" in e.lower() and "str" in e.lower()
            for e in errors
        ), f"Expected conditional str-rebinding rejection; got: {errors}"

    def test_conditional_redacted_shadowing_is_rejected(self) -> None:
        """``if cond: RedactedEvidenceText = int`` is rejected."""
        source = (
            '"""Conditional RedactedEvidenceText shadowing."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "if True:\n"
            "    RedactedEvidenceText = int\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "conditional rebinding" in e.lower()
            and "redacted" in e.lower()
            for e in errors
        ), f"Expected conditional RedactedEvidenceText rebinding rejection; got: {errors}"


class TestAggregateTempTreeRegression:
    """R14 #1: ``check_llm_safe_evidence_contract`` against a source-root tree.

    The negative-proofs harness in
    :mod:`scripts.incident_lifecycle_boundary.redaction_full_gate_negative_proofs`
    creates a Python source-root-shaped temp tree directly under
    ``<temp>/k8s_diag_agent/...`` (no ``src/``) and passes ``<temp>``
    as ``--repo-root``. The aggregate verifier must resolve the
    canonical privacy-state module regardless of whether ``repo_root``
    is the repository root (containing ``.git`` and ``src/``) or the
    source root (containing ``k8s_diag_agent/`` directly).
    """

    def _copy_real_canonical_to(self, target_root: Path) -> None:
        """Copy the real canonical privacy-state module to ``<target>/collect``."""
        collect = target_root / "k8s_diag_agent" / "collect"
        collect.mkdir(parents=True, exist_ok=True)
        src_collect = REPO_ROOT / "src" / "k8s_diag_agent" / "collect"
        for name in (
            "incident_evidence_redaction.py",
            "incident_evidence_llm_safe.py",
            "incident_evidence_types.py",
        ):
            shutil.copyfile(src_collect / name, collect / name)
        (target_root / "k8s_diag_agent" / "__init__.py").write_text("", encoding="utf-8")
        (collect / "__init__.py").write_text("", encoding="utf-8")

    def test_aggregate_path_resolves_source_root_layout(self) -> None:
        """check_llm_safe_evidence_contract accepts a source-root temp tree."""
        from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
            check_llm_safe_evidence_contract,
        )

        temp_dir = tempfile.mkdtemp(prefix="r14_aggregate_")
        try:
            temp_root = Path(temp_dir)
            self._copy_real_canonical_to(temp_root)
            evidence_path = (
                temp_root / "k8s_diag_agent" / "collect" / "incident_evidence_llm_safe.py"
            )
            errors = check_llm_safe_evidence_contract(
                evidence_filepath=str(evidence_path),
                repo_root=temp_root,
            )
            assert errors == [], (
                f"Aggregate check must resolve source-root layout; got: {errors}"
            )
        finally:
            os.unlink(temp_dir) if os.path.isfile(temp_dir) else shutil.rmtree(
                temp_dir, ignore_errors=True
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
