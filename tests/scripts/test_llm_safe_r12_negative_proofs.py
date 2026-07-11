"""R12 negative-proof tests for the LLM-safe evidence boundary verifier.

These tests close the remaining R10/R11 bypasses:

1. **Immediate attribute-mutation diagnostics** (R12 #3):
   R10/R11 only installed :data:`REBINDING_SENTINEL` for
   ``typing.NewType = X`` and rejected the next call; the mutation
   itself was silent when no call followed. R12 emits an immediate
   diagnostic for every such mutation (Assign, AugAssign, AnnAssign,
   Delete on ``typing.<attr>`` and ``NewType.<attr>``), every
   ``setattr(typing, "NewType", X)`` call (literal), every dynamic
   ``setattr(typing, <non-literal>, X)`` call, every
   ``builtins.setattr(typing, ...)`` call (literal or dynamic), and
   every ``__builtins__.setattr(typing, ...)`` call.

2. **Canonical alias supertype identity** (R12 #2):
   R10/R11 checked only the lexical spelling of each canonical
   alias's supertype. R12 rejects:
   - string-literal supertypes such as ``NewType("Foo", "str")``
     (must be a ``Name`` referencing a real identity);
   - rebinding of canonical alias names (``RawEvidenceText``,
     ``RedactedEvidenceText``, ``LLMSafeEvidenceText``,
     ``SafeEvidenceExcerpt``) and of ``str`` at module scope
     (the trusted primitive supertype);
   - canonical aliases whose declared supertype resolves to a
     different identity than the canonical contract (e.g.
     ``LLMSafeEvidenceText = NewType("...", RedactedEvidenceText)``
     followed by ``RedactedEvidenceText = int``).

Negative proofs (each MUST reject the offending source):

* ``typing.NewType = fake.NewType`` (no call follows) -> FAIL
* ``del typing.NewType`` (no call follows) -> FAIL
* ``setattr(typing, attr_name, X)`` where ``attr_name`` is not a literal
  -> FAIL
* ``builtins.setattr(typing, "NewType", fake.NewType)`` -> FAIL
* ``str = int`` followed by canonical ``NewType`` declarations -> FAIL
* ``NewType("RawEvidenceText", "str")`` (string literal supertype)
  -> FAIL
* ``RedactedEvidenceText = int`` followed by ``NewType(..., RedactedEvidenceText)``
  -> FAIL

Sanity proofs:

* All R10/R11 negative-proof tests still pass.
* Legitimate canonical module still passes.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
    check_newtype_provenance,
)


def _synthetic_provenance_errors(source: str) -> list[str]:
    """Run the per-call-site provenance check on a synthetic source."""
    import ast as _ast

    tree = _ast.parse(source)
    return check_newtype_provenance(tree, "<synthetic>")


def _synthetic_canonical_errors(source: str) -> list[str]:
    """Run the canonical alias check (provenance + supertype identity)."""
    import ast as _ast

    from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
        check_canonical_redaction_aliases,
    )

    path = _temp_module(source)
    try:
        return check_canonical_redaction_aliases(str(path))
    finally:
        _cleanup(path)
    return []
    # Unreachable but the function signature is preserved.
    _ = _ast.parse


def _temp_module(source: str) -> Path:
    path_obj = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    path_obj.write(source)
    path_obj.close()
    return Path(path_obj.name)


def _cleanup(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


class TestImmediateAttributeMutationDiagnostics:
    """R12 #3: attribute mutations emit an immediate diagnostic."""

    def test_typing_newtype_assign_emits_immediate_error_without_followup_call(self) -> None:
        """``typing.NewType = X`` with no subsequent call still emits an error."""
        source = (
            '"""typing.NewType rebind with no followup call."""\n'
            "import typing\n"
            "import fake\n"
            "typing.NewType = fake.NewType\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "attribute assign" in e.lower() or "forbidden" in e.lower()
            for e in errors
        ), f"Expected immediate attribute-assign diagnostic; got: {errors}"

    def test_typing_newtype_delete_emits_immediate_error_without_followup_call(self) -> None:
        """``del typing.NewType`` with no subsequent call still emits an error."""
        source = (
            '"""del typing.NewType with no followup call."""\n'
            "import typing\n"
            "del typing.NewType\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "attribute delete" in e.lower() or "forbidden" in e.lower()
            for e in errors
        ), f"Expected immediate attribute-delete diagnostic; got: {errors}"

    def test_setattr_typing_dynamic_attribute_name_emits_immediate_error(self) -> None:
        """``setattr(typing, attr_var, X)`` (non-literal) is rejected."""
        source = (
            '"""dynamic setattr on typing."""\n'
            "import typing\n"
            "attr_name = 'NewType'\n"
            "setattr(typing, attr_name, lambda *a: None)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "dynamic" in e.lower() and "setattr" in e.lower()
            for e in errors
        ), f"Expected dynamic-setattr diagnostic; got: {errors}"

    def test_builtins_setattr_typing_literal_attribute_emits_immediate_error(self) -> None:
        """``builtins.setattr(typing, "NewType", X)`` is rejected."""
        source = (
            '"""builtins.setattr on typing with literal attribute."""\n'
            "import builtins\n"
            "import typing\n"
            "import fake\n"
            "builtins.setattr(typing, 'NewType', fake.NewType)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "setattr" in e.lower() and ("literal" in e.lower() or "builtins" in e.lower())
            for e in errors
        ), f"Expected builtins.setattr diagnostic; got: {errors}"

    def test_builtins_setattr_typing_dynamic_attribute_emits_immediate_error(self) -> None:
        """``builtins.setattr(typing, attr_var, X)`` is rejected."""
        source = (
            '"""builtins.setattr on typing with dynamic attribute."""\n'
            "import builtins\n"
            "import typing\n"
            "attr_name = 'NewType'\n"
            "builtins.setattr(typing, attr_name, lambda *a: None)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "dynamic" in e.lower() and "setattr" in e.lower()
            for e in errors
        ), f"Expected builtins.dynamic-setattr diagnostic; got: {errors}"


class TestCanonicalAliasSupertypeIdentity:
    """R12 #2: canonical alias supertype validation by active identity."""

    def test_str_rebinding_is_rejected(self) -> None:
        """``str = int`` then a canonical ``NewType(... str ...)`` declaration fails.

        The walker installs the sentinel for ``str``; the canonical
        alias contract checks that the supertype's active binding at
        the alias declaration is NOT the sentinel.
        """
        source = (
            '"""str rebinding then canonical NewType."""\n'
            "from typing import NewType\n"
            "str = int\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _synthetic_canonical_errors(source)
        assert any(
            "str" in e.lower()
            and ("rebound" in e.lower() or "sentinel" in e.lower())
            for e in errors
        ), f"Expected str-rebinding rejection; got: {errors}"

    def test_redacted_rebinding_after_canonical_use_is_rejected(self) -> None:
        """Rebinding ``RedactedEvidenceText`` after it is used as a supertype fails."""
        source = (
            '"""RedactedEvidenceText rebinding after canonical use."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "RedactedEvidenceText = int\n"
            # The following alias uses ``RedactedEvidenceText`` directly
            # as its supertype; the rebinding at the previous line
            # must therefore invalidate this declaration.
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', RedactedEvidenceText)\n"
        )
        errors = _synthetic_canonical_errors(source)
        assert any(
            "redacted" in e.lower() or "rebound" in e.lower()
            for e in errors
        ), f"Expected RedactedEvidenceText rebind rejection; got: {errors}"

    def test_string_literal_supertype_is_rejected(self) -> None:
        """``NewType('RawEvidenceText', 'str')`` with a string-literal supertype fails."""
        source = (
            '"""string literal supertype."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', 'str')\n"
        )
        errors = _synthetic_canonical_errors(source)
        assert any(
            "literal" in e.lower() or "string" in e.lower()
            for e in errors
        ), f"Expected string-literal-supertype rejection; got: {errors}"


class TestR12SanityRegressions:
    """Sanity proofs: R12 does not regress legitimate modules."""

    def test_legitimate_canonical_module_still_passes(self) -> None:
        """The actual canonical module passes under R12."""
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
            f"Legitimate canonical module must pass under R12: {errors}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
