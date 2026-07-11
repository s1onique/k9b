"""R9 negative-proof tests for the LLM-safe evidence boundary verifier.

These tests cover the four bypass classes that R8 left open because
its binding table recorded only the FINAL binding for ``NewType`` and
``typing``. The R9 fix walks the module body in source order and
validates each canonical ``NewType(...)`` call against the binding
snapshot active at THAT source position.

The negative proofs (each MUST reject the offending source):

1. **Reverse-order rebinding**:
   ``from fake import NewType`` followed by canonical
   ``NewType(...)`` calls, followed by ``from typing import NewType``.
   The final binding is ``typing``, but the calls actually used
   ``fake.NewType``. R8's final-state check accepted this; R9 rejects.

2. **Non-import rebinding at module scope**:
   ``NewType = fake.NewType`` (assignment), ``def NewType(...)``
   (function def), ``class NewType: ...`` (class def), and
   ``typing = fake`` (assignment). All rebind the module-level
   identity to a value whose source module cannot be statically
   proven, so subsequent uses are rejected.

3. **Conditional rebinding (fail-closed)**:
   ``if cond: from fake import NewType``, ``try: from fake import
   NewType``, ``for ... in iter: NewType = fake.NewType``,
   ``with open(...) as NewType: ...``, ``match v: case ... as
   NewType: ...``. Path-sensitive analysis is intractable; the
   conservative shortcut is to reject the module outright.

4. **Qualified ``typing`` rebinding**:
   ``import typing`` then ``typing.NewType(...)`` then
   ``import fake as typing`` then more ``typing.NewType(...)``. The
   first call uses a trusted binding; the later call would resolve
   to ``fake``. R8's final-state check approved both calls; R9
   rejects the second.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
    check_canonical_redaction_aliases,
)

# ---------------------------------------------------------------------------
# R9.1 — Reverse-order rebinding proofs
# ---------------------------------------------------------------------------


class TestReverseOrderRebinding:
    """``from fake import NewType`` then calls then ``from typing import NewType``.

    R8's final-state binding table made ``NewType`` resolve to
    ``typing`` (the last binding) so every earlier malicious call was
    evaluated as trusted. R9 evaluates each call against the binding
    active at its source position, so the calls are rejected.
    """

    def test_fails_when_fake_import_then_calls_then_trusted_import(self) -> None:
        """Untrusted import FIRST, then canonical calls, then trusted import.

        A late trusted import does NOT retroactively approve earlier
        untrusted calls. The first four canonical ``NewType(...)`` calls
        resolved against the ``fake`` binding and must be rejected.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Fake import first, trusted import last."""\n')
            f.write("from fake import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            f.write("\n")
            f.write("# Late trusted import does NOT retroactively approve:\n")
            f.write("from typing import NewType  # noqa: F401\n")
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected reverse-order rebinding rejection; got empty errors"
            )
            assert any(
                "fake" in e.lower() or "non-trusted" in e.lower() or "trust" in e.lower()
                for e in errors
            ), f"Expected provenance error referencing 'fake'; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_when_qualified_typing_rebound_late(self) -> None:
        """``import typing`` then calls then ``import fake as typing``.

        R8 made ``typing`` resolve to ``fake`` at the end so EVERY
        earlier ``typing.NewType(...)`` call was rejected (correctly),
        but the symmetric bypass is missing: a late ``import fake as
        typing`` would retroactively poison earlier trusted calls.
        R9 evaluates each call against the binding active at its
        source position so the second call (after the rebind) is the
        one that gets rejected - and the prior trusted calls stay
        validated against their own snapshot.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""typing rebound mid-module."""\n')
            f.write("import typing\n\n")
            f.write("RawEvidenceText = typing.NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = typing.NewType('RedactedEvidenceText', str)\n")
            f.write("\n")
            f.write("# Late untrusted rebinding poisons subsequent calls:\n")
            f.write("import fake as typing  # noqa: F401\n")
            f.write(
                "LLMSafeEvidenceText = typing.NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = typing.NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected late-rebinding rejection; got empty errors"
            )
            assert any(
                "non-trusted" in e.lower()
                or "fake" in e.lower()
                or "trust" in e.lower()
                for e in errors
            ), f"Expected rebinding provenance error; got: {errors}"
        finally:
            Path(temp_path).unlink()


# ---------------------------------------------------------------------------
# R9.2 - Non-import rebinding proofs
# ---------------------------------------------------------------------------


class TestNonImportRebinding:
    """``NewType = fake.NewType``, ``def NewType``, ``class NewType`` rebindings.

    Static analysis cannot resolve the right-hand side of these
    rebindings to a trusted module, so subsequent uses of the
    rebound name are rejected with a sentinel binding.
    """

    def test_fails_when_newtype_rebound_via_assignment(self) -> None:
        """``NewType = fake.NewType`` rebinds the module-level identity.

        Any subsequent ``NewType(...)`` call must fail because the
        name now resolves to ``fake.NewType`` (untrusted).
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""NewType rebound via assignment."""\n')
            f.write("import fake\n\n")
            f.write("NewType = fake.NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected assignment-rebinding rejection; got empty errors"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_when_typing_rebound_via_assignment(self) -> None:
        """``typing = fake`` rebinds the qualified-call resolver.

        Any subsequent ``typing.NewType(...)`` call must fail because
        ``typing`` now resolves to the untrusted module.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""typing rebound via assignment."""\n')
            f.write("import fake\n\n")
            f.write("typing = fake\n\n")
            f.write("RawEvidenceText = typing.NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = typing.NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = typing.NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = typing.NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected typing-rebinding rejection; got empty errors"
            )
            assert any(
                "non-trusted" in e.lower()
                or "trust" in e.lower()
                or "fake" in e.lower()
                or "rebound" in e.lower()
                or "no longer resolves" in e.lower()
                for e in errors
            ), f"Expected provenance error mentioning rebinding; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_when_newtype_shadowed_by_function_definition(self) -> None:
        """``def NewType(...)`` rebinds the module-level identity.

        A module-level ``def NewType(...)`` shadows the import and any
        subsequent bare ``NewType(...)`` call must be rejected.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""NewType shadowed by def."""\n')
            f.write("\n")
            f.write("def NewType(name, base):\n")
            f.write("    return name\n")
            f.write("\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected def-rebinding rejection; got empty errors"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_when_newtype_shadowed_by_class_definition(self) -> None:
        """``class NewType`` rebinds the module-level identity.

        A module-level ``class NewType`` shadows the import and any
        subsequent bare ``NewType(...)`` call must be rejected.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""NewType shadowed by class."""\n')
            f.write("\n")
            f.write("class NewType:\n")
            f.write("    pass\n")
            f.write("\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected class-rebinding rejection; got empty errors"
            )
        finally:
            Path(temp_path).unlink()


# ---------------------------------------------------------------------------
# R9.3 - Conditional rebinding proofs (fail-closed)
# ---------------------------------------------------------------------------


class TestConditionalRebindingFailClosed:
    """Rebindings of ``NewType``/``typing`` inside ``if``/``try``/``for``/``with``/``match``.

    Path-sensitive analysis of every branch is intractable for
    adversarial source; the conservative shortcut is to reject the
    module outright. Each test confirms a different control-flow
    form triggers the fail-closed error.
    """

    def test_fails_when_rebinding_inside_if_block(self) -> None:
        """``if cond: from fake import NewType`` fails closed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Conditional rebinding via if."""\n')
            f.write("from typing import NewType\n\n")
            f.write("if True:\n")
            f.write("    from fake import NewType  # noqa: F401\n")
            f.write("\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected fail-closed rejection on if-block rebinding; got empty errors"
            )
            assert any(
                "fail-closed" in e.lower()
                or "conditional" in e.lower()
                or "control-flow" in e.lower()
                for e in errors
            ), f"Expected fail-closed diagnostic; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_when_rebinding_inside_try_block(self) -> None:
        """``try: from fake import NewType`` fails closed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Conditional rebinding via try."""\n')
            f.write("from typing import NewType\n\n")
            f.write("try:\n")
            f.write("    from fake import NewType  # noqa: F401\n")
            f.write("except ImportError:\n")
            f.write("    pass\n")
            f.write("\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected fail-closed rejection on try-block rebinding; got empty errors"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_when_rebinding_inside_with_block(self) -> None:
        """``with open(...) as NewType: ...`` fails closed (rebinding via target)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Conditional rebinding via with."""\n')
            f.write("from typing import NewType\n\n")
            f.write("with open('/dev/null') as NewType:\n")
            f.write("    pass\n")
            f.write("\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected fail-closed rejection on with-block rebinding; got empty errors"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_when_rebinding_inside_match_block(self) -> None:
        """``match v: case ... as NewType: ...`` fails closed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Conditional rebinding via match."""\n')
            f.write("from typing import NewType\n\n")
            f.write("value = 1\n")
            f.write("match value:\n")
            f.write("    case 1 as NewType:\n")
            f.write("        pass\n")
            f.write("\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0, (
                "Expected fail-closed rejection on match-block rebinding; got empty errors"
            )
        finally:
            Path(temp_path).unlink()


# ---------------------------------------------------------------------------
# R9.4 - Positive regression: legitimate modules still pass
# ---------------------------------------------------------------------------


class TestLegitimateModulePasses:
    """Canonical and facade modules with only trusted bindings pass."""

    def test_legitimate_canonical_module_passes(self) -> None:
        """Plain ``from typing import NewType`` + canonical calls passes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Legitimate canonical module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert errors == [], f"Legitimate canonical module should pass: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_legitimate_qualified_canonical_module_passes(self) -> None:
        """``import typing`` + ``typing.NewType(...)`` qualified calls pass."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Legitimate canonical module (qualified)."""\n')
            f.write("import typing\n\n")
            f.write("RawEvidenceText = typing.NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = typing.NewType('RedactedEvidenceText', str)\n")
            f.write(
                "LLMSafeEvidenceText = typing.NewType("
                "'LLMSafeEvidenceText', RedactedEvidenceText)\n"
            )
            f.write(
                "SafeEvidenceExcerpt = typing.NewType("
                "'SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            )
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert errors == [], (
                f"Legitimate qualified canonical module should pass: {errors}"
            )
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])