"""R15 negative-proof tests for the LLM-safe evidence boundary verifier.

R15 closes three bypasses that the R14 implementation silently
accepted:

1. **Qualified ``typing.NewType(...)`` declarations** (R15 #1):
   :func:`_is_newtype_assignment` previously only recognized the
   bare ``NewType(...)`` form, so a module that used the qualified
   form throughout would not trigger per-call-site provenance
   checks at all and could pass a fake ``str`` rebinding through
   unscathed. R15 accepts the qualified form so the source-order
   walker evaluates it against the binding snapshot for ``typing``.
   The provenance check rejects any qualifier that does not
   resolve to ``import typing`` at the call's source position.

2. **Conditional binding-target rebindings** (R15 #2):
   :func:`scan_module_scope_conditional_shadowing` previously
   inspected only statement BODIES, NOT the BINDING TARGETS of
   ``for``/``async for`` loop targets, ``with``/``async with``
   ``as <name>`` items, ``except ... as <name>`` aliases, and
   ``match`` case patterns (``as <name>`` and
   ``MatchMapping.rest``). R15 inspects all of these.

3. **Top-level ``Import`` rebinding of canonical aliases after
   declaration** (R15 #3): the post-declaration rebinding check
   previously EXCLUDED imports. A late
   ``from builtins import int as RawEvidenceText`` AFTER the
   canonical declaration silently replaced the alias identity
   without any diagnostic. R15 includes imports in the
   post-declaration check.
"""

from __future__ import annotations

import ast
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
    return ast.parse(source)


def _provenance_errors(source: str) -> list[str]:
    return check_newtype_provenance(_parse(source), "<synthetic>")


def _supertype_errors(source: str) -> list[str]:
    return validate_canonical_alias_super_types(
        _parse(source), "<synthetic>", EXPECTED_ALIASES
    )


class TestQualifiedTypingNewTypeForm:
    """R15 #1: ``typing.NewType(...)`` form is also checked."""

    def test_qualified_typing_NewType_with_fake_str_is_rejected(self) -> None:
        """``typing.NewType(..., str)`` after rebinding ``str = int`` is rejected.

        The textual hierarchy is correct, and ``typing`` has trusted
        provenance (only ``import typing``), but the actual primitive
        supertype is ``int``. R15 closes the bypass by feeding the
        qualified call through the same source-order walker.
        """
        source = (
            '"""Qualified NewType form with rebound str."""\n'
            "import typing\n"
            "str = int\n"
            "RawEvidenceText = typing.NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = typing.NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = typing.NewType(\n"
            "    'LLMSafeEvidenceText',\n"
            "    RedactedEvidenceText,\n"
            ")\n"
            "SafeEvidenceExcerpt = typing.NewType(\n"
            "    'SafeEvidenceExcerpt',\n"
            "    LLMSafeEvidenceText,\n"
            ")\n"
        )
        errors = _supertype_errors(source)
        # R15 fix exposes the qualified-form bypass: the validator
        # now rejects the supertype identity for ALL aliases that
        # depend on the rebound ``str`` (RawEvidenceText,
        # RedactedEvidenceText). The remaining downstream aliases
        # (LLMSafeEvidenceText, SafeEvidenceExcerpt) are validated
        # against their sentinel bindings, which are themselves
        # unaffected by ``str`` rebinding.
        assert len(errors) >= 1, (
            f"Expected supertype-identity rejection on qualified-form "
            f"bypass; got: {errors}"
        )
        assert any(
            "binding identity" in e.lower() or "shadown" in e.lower()
            for e in errors
        ), f"Expected binding-identity mismatch; got: {errors}"

    def test_qualified_typing_NewType_legitimate_passes(self) -> None:
        """A legitimate ``typing.NewType(...)`` chain still passes."""
        source = (
            '"""Legitimate qualified NewType chain."""\n'
            "import typing\n"
            "RawEvidenceText = typing.NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = typing.NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = typing.NewType(\n"
            "    'LLMSafeEvidenceText',\n"
            "    RedactedEvidenceText,\n"
            ")\n"
            "SafeEvidenceExcerpt = typing.NewType(\n"
            "    'SafeEvidenceExcerpt',\n"
            "    LLMSafeEvidenceText,\n"
            ")\n"
        )
        errors = _supertype_errors(source)
        assert errors == [], f"Legitimate qualified chain must pass: {errors}"


class TestConditionalBindingTargetsAreDetected:
    """R15 #2: ``for``/``with``/``except``/``match`` binding targets."""

    def test_conditional_for_str_in_int_is_rejected(self) -> None:
        """``if cond: for str in (int,): pass`` rebinds module ``str``."""
        source = (
            '"""Conditional for-target rebind of str."""\n'
            "from typing import NewType\n"
            "if True:\n"
            "    for str in (int,):\n"
            "        pass\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "conditional rebinding" in e.lower() and "str" in e.lower()
            for e in errors
        ), f"Expected conditional for-target str rebinding rejection; got: {errors}"

    def test_conditional_with_as_str_is_rejected(self) -> None:
        """``if cond: with manager as str: pass`` rebinds module ``str``."""
        # We simulate ``manager`` with a no-op CM that yields None.
        source = (
            '"""Conditional with-target rebind of str."""\n'
            "from contextlib import nullcontext\n"
            "from typing import NewType\n"
            "if True:\n"
            "    with nullcontext() as str:\n"
            "        pass\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "conditional rebinding" in e.lower() and "str" in e.lower()
            for e in errors
        ), f"Expected conditional with-target str rebinding rejection; got: {errors}"


class TestTopLevelImportRebindsCanonicalAlias:
    """R15 #3: post-declaration ``Import`` rebinding of canonical alias is rejected."""

    def test_top_level_import_rebinding_raw_evidence_text_is_rejected(self) -> None:
        """``from builtins import int as RawEvidenceText`` after decl fails."""
        source = (
            '"""Post-decl import rebind of RawEvidenceText."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            "from builtins import int as RawEvidenceText\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "raw" in e.lower() and "rebound" in e.lower()
            for e in errors
        ), f"Expected post-decl import rebinding rejection; got: {errors}"

    def test_top_level_import_rebinding_redacted_is_rejected(self) -> None:
        """``import builtins.int as RedactedEvidenceText`` after decl fails."""
        source = (
            '"""Post-decl import rebind of RedactedEvidenceText."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "from builtins import int as RedactedEvidenceText\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "redacted" in e.lower() and "rebound" in e.lower()
            for e in errors
        ), f"Expected post-decl import rebinding rejection; got: {errors}"


class TestR15SanityRegressions:
    """Sanity proofs: R15 does not regress legitimate modules."""

    def test_legitimate_canonical_module_still_passes(self) -> None:
        """The actual canonical module passes under R15."""
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
            f"Legitimate canonical module must pass under R15: {errors}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
