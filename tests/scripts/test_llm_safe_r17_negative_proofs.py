"""R17 negative-proof tests for the LLM-safe evidence boundary verifier.

R17 closes the walrus (``ast.NamedExpr``) bypass that the R12-R16
helpers did not detect: Python's walrus operator
``(name := value)`` at module scope rebinds ``name`` to ``value``
at that expression's location, and the existing rebinding-detection
helpers (which only inspect ``ast.Assign``/``AnnAssign``/``For``/
``With``/``Match``/``except``/Import forms) miss it.

``(NewType := fake.NewType)`` at module scope lets an attacker
replace the trusted ``typing.NewType`` import with a fake, so
subsequent ``NewType("...", str)`` calls use ``fake.NewType`` -
silently minting canonical aliases through an unauthorized binding
chain. ``(str := int)`` does the same for the builtin primitive
supertype.

R17 walks the module body, recursing into control-flow bodies but
stopping at function/class scopes (where walrus targets bind to
the enclosing function/class scope, not module scope), and emits
an immediate diagnostic for every walrus target that names a
canonical-sensitive or provenance-sensitive name.

Negative proofs (each MUST reject the offending source):

* top-level ``(NewType := fake.NewType)`` - provenance bypass.
* top-level ``(typing := fake)`` - provenance bypass.
* top-level ``(str := int)`` - supertype bypass.
* top-level ``(RawEvidenceText := int)`` AFTER declarations.
* ``if (NewType := fake.NewType)`` (test expression rebind).
* ``while (str := int)`` (test expression rebind).
* module-level comprehension walrus that binds a sensitive name.

Sanity proofs:

* All R10-R16 negative-proof tests still pass.
* Legitimate canonical module still passes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary._llm_safe_alias_supertypes import (
    validate_canonical_alias_super_types,
)
from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    LLM_SAFE_TYPES,
)
from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
    check_newtype_provenance,
)

REPO_ROOT = Path(__file__).parent.parent.parent
EXPECTED_ALIASES = LLM_SAFE_TYPES


def _parse(source: str):
    return ast.parse(source)


def _supertype_errors(source: str) -> list[str]:
    return validate_canonical_alias_super_types(
        _parse(source), "<synthetic>", EXPECTED_ALIASES
    )


def _provenance_errors(source: str) -> list[str]:
    return check_newtype_provenance(_parse(source), "<synthetic>")


class TestTopLevelWalrusBypass:
    """R17: top-level walrus rebinds a sensitive name."""

    def test_top_level_walrus_newtype_rebind_emits_provenance_diagnostic(self) -> None:
        """``(NewType := fake.NewType)`` at top level is rejected."""
        source = (
            '"""Walrus rebinds NewType at module scope."""\n'
            "(NewType := fake.NewType)\n"
            "from typing import NewType as _RealNewType\n"
        )
        errors = _provenance_errors(source)
        assert any(
            "walrus" in e.lower() and "newtype" in e.lower() for e in errors
        ), f"Expected walrus provenance diagnostic for 'NewType'; got: {errors}"

    def test_top_level_walrus_typing_rebind_emits_provenance_diagnostic(self) -> None:
        """``(typing := fake)`` at top level is rejected."""
        source = (
            '"""Walrus rebinds typing at module scope."""\n'
            "import typing\n"
            "(typing := fake)\n"
        )
        errors = _provenance_errors(source)
        assert any(
            "walrus" in e.lower() and "typing" in e.lower() for e in errors
        ), f"Expected walrus provenance diagnostic for 'typing'; got: {errors}"

    def test_top_level_walrus_str_rebind_emits_supertype_diagnostic(self) -> None:
        """``(str := int)`` at top level is rejected (canonical supertype)."""
        source = (
            '"""Walrus rebinds str at module scope."""\n'
            "from typing import NewType\n"
            "(str := int)\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus canonical-supertype diagnostic for 'str'; got: {errors}"

    def test_top_level_walrus_redeclared_alias_rebind_after_declaration(self) -> None:
        """``(RawEvidenceText := int)`` AFTER declarations is rejected."""
        source = (
            '"""Walrus redeclaration of RawEvidenceText."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            "(RawEvidenceText := int)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "raw" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for redeclared Raw; got: {errors}"


class TestConditionalExpressionWalrus:
    """R17: walrus inside ``if``/``while`` test rebinds at module scope."""

    def test_if_test_walrus_newtype_rebind_is_rejected(self) -> None:
        """``if (NewType := fake.NewType):`` rebinds at module scope."""
        source = (
            '"""if-test walrus rebinds NewType."""\n'
            "if (NewType := fake.NewType):\n"
            "    pass\n"
        )
        errors = _provenance_errors(source)
        assert any(
            "walrus" in e.lower() and "newtype" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for if-test rebind; got: {errors}"

    def test_while_test_walrus_str_rebind_is_rejected(self) -> None:
        """``while (str := int):`` rebinds at module scope."""
        source = (
            '"""while-test walrus rebinds str."""\n'
            "while (str := int):\n"
            "    break\n"
        )
        errors = _provenance_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for while-test rebind; got: {errors}"


class TestModuleLevelComprehensionWalrus:
    """R17: walrus inside a comprehension's iter binds at module scope (PEP 572)."""

    def test_list_comprehension_walrus_binds_at_module_scope(self) -> None:
        """``[str for x in (str := iter([1]))]`` rebinds ``str`` at module scope."""
        source = (
            '"""Comprehension walrus rebinds str at module scope."""\n'
            "from typing import NewType\n"
            "[str for x in (str := iter([1]))]\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for comprehension rebind; got: {errors}"


class TestR17SanityRegressions:
    """Sanity proofs: R17 does not regress legitimate modules."""

    def test_legitimate_canonical_module_still_passes(self) -> None:
        """The actual canonical module passes under R17."""
        from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
            check_canonical_redaction_aliases,
        )

        path = (
            Path(__file__)
            .resolve()
            .parents[2]
            .joinpath(
                "src",
                "k8s_diag_agent",
                "collect",
                "incident_evidence_redaction.py",
            )
        )
        errors = check_canonical_redaction_aliases(str(path))
        assert errors == [], (
            f"Legitimate canonical module must pass under R17: {errors}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
