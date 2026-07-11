"""R10 negative-proof tests for the LLM-safe evidence boundary verifier.

These tests close the bypass class that R9 left open because its
binding tuple recorded only ``(source_module, original_name)``. An
attacker could pass the R9 check by writing::

    from typing import Any as NewType

because the verifier saw ``source_module == "typing"`` and accepted
the call. R10 records an exact 4-tuple ``(kind, module,
original_name, local_name)`` for every binding and rejects any call
whose binding does not match the canonical trusted shape exactly.

The R10 invariant: a ``NewType(...)`` call site is accepted ONLY if
its binding is exactly:

    Binding(kind="from-import", module="typing",
            original_name="NewType", local_name="NewType")  # bare form

    Binding(kind="import", module="typing",
            original_name="typing", local_name="typing")  # qualified form

The negative proofs (each MUST reject the offending source):

1. **Aliased non-``NewType`` symbols from ``typing``**:
   - ``from typing import Any as NewType`` (Any is not NewType)
   - ``import typing as NewType`` (typing module, not NewType)
   - ``from typing import Any as typing`` (Any is not the typing module)
   - ``from typing import NewType as typing`` (NewType is not typing module)

2. **Same-module / wrong-symbol under qualified call form**:
   ``import typing`` followed by ``from typing import NewType as
   typing``. R9 saw ``typing`` resolve to ``typing.NewType`` (the
   function), not the ``typing`` module; the qualified call would
   resolve to ``NewType.NewType(...)`` and not to ``typing.NewType``.

3. **Order-of-evaluation regression**: a rebinding assignment that
   ALSO has a ``NewType(...)`` right-hand side must validate the
   right-hand side against the OLD binding, not the post-rebind
   sentinel::

       from typing import NewType
       NewType = NewType("NewType", str)

   The right-hand ``NewType("NewType", str)`` MUST be evaluated
   against the trusted import, and the assignment to ``NewType``
   MUST then install the sentinel. R9's wrong order silently
   approved the wrong snapshot; R10 fixes this.

4. **Sanity regressions**: legitimate modules with bare or qualified
   forms continue to pass after the stricter check.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
    TRUSTED_BARE_NEWTYPE_BINDING,
    TRUSTED_QUALIFIED_TYPING_BINDING,
    Binding,
    check_newtype_provenance,
)
from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
    check_canonical_redaction_aliases,
)

# ---------------------------------------------------------------------------
# R10.1 — Exact (import kind, module, original symbol, local name) proofs
# ---------------------------------------------------------------------------


class TestExactBindingProvenance:
    """Negative proofs for the exact-binding provenance check.

    R10 stores an exact 4-tuple ``Binding(kind, module,
    original_name, local_name)`` for every import and rejects any
    call whose binding is not one of the two trusted shapes.
    Each test below targets a specific aliasing bypass.
    """

    def test_bare_newtype_rejects_typing_any_aliased(self) -> None:
        """``from typing import Any as NewType`` is rejected.

        The binding is ``Binding(kind="from-import", module="typing",
        original_name="Any", local_name="NewType")``. R9 saw
        ``source_module == "typing"`` and accepted the call. R10
        requires ``original_name == "NewType"`` exactly.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Any aliased as NewType."""\n')
            f.write("from typing import Any as NewType\n\n")
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
                "Expected Any-as-NewType rejection; got empty errors"
            )
            assert any(
                "'Any'" in e or "Any" in e and "NewType" in e
                for e in errors
            ), f"Expected provenance error naming 'Any'; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_bare_newtype_rejects_typing_module_aliased(self) -> None:
        """``import typing as NewType`` is rejected.

        The binding is ``Binding(kind="import", module="typing",
        original_name="typing", local_name="NewType")``. The
        bare ``NewType(...)`` call requires ``kind="from-import"``
        so the wrong import form fails even though ``module`` is
        correct.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""typing module aliased as NewType."""\n')
            f.write("import typing as NewType\n\n")
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
                "Expected typing-as-NewType rejection; got empty errors"
            )
            assert any(
                "kind=" in e and ("'import'" in e or "import" in e)
                for e in errors
            ), f"Expected kind-mismatch error; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_qualified_typing_rejects_any_aliased_as_typing(self) -> None:
        """``from typing import Any as typing`` is rejected.

        The binding is ``Binding(kind="from-import", module="typing",
        original_name="Any", local_name="typing")``. The qualified
        ``typing.NewType(...)`` call requires ``kind="import"`` and
        ``original_name="typing"``; ``Any`` is neither. R9 saw
        ``module == "typing"`` and would have approved this.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Any aliased as typing."""\n')
            f.write("from typing import Any as typing\n\n")
            f.write("RawEvidenceText = typing.NewType('RawEvidenceText', str)\n")
            f.write(
                "RedactedEvidenceText = typing.NewType('RedactedEvidenceText', str)\n"
            )
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
                "Expected Any-as-typing rejection; got empty errors"
            )
            assert any(
                "'Any'" in e or ("Any" in e and "typing" in e)
                for e in errors
            ), f"Expected provenance error naming 'Any'; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_qualified_typing_rejects_newtype_aliased_as_typing(self) -> None:
        """``from typing import NewType as typing`` is rejected.

        The binding is ``Binding(kind="from-import", module="typing",
        original_name="NewType", local_name="typing")``. The
        qualified call requires ``kind="import"`` and
        ``original_name="typing"``; ``NewType`` is neither. R9 saw
        ``module == "typing"`` and would have approved this. The
        call would in fact resolve to ``NewType.NewType(...)`` at
        runtime, which does not exist.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""NewType aliased as typing."""\n')
            f.write("from typing import NewType as typing\n\n")
            f.write("RawEvidenceText = typing.NewType('RawEvidenceText', str)\n")
            f.write(
                "RedactedEvidenceText = typing.NewType('RedactedEvidenceText', str)\n"
            )
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
                "Expected NewType-as-typing rejection; got empty errors"
            )
            assert any(
                "kind=" in e or "original_name=" in e
                for e in errors
            ), f"Expected provenance kind/original mismatch error; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_bare_newtype_rejects_late_aliased_import(self) -> None:
        """A late ``from typing import Any as NewType`` rebinds the
        local name ``NewType`` away from the trusted binding. The
        previous trusted calls already in scope remain valid
        against their own snapshot; the binding is now non-trusted
        for subsequent calls (which the canonical module does not
        emit but the negative proof constructs explicitly).
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Trusted then aliased same-module import."""\n')
            f.write("from typing import NewType\n")
            f.write("from typing import Any as NewType  # noqa: F401\n\n")
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
                "Expected late-aliased-import rejection; got empty errors"
            )
            assert any(
                "'Any'" in e or "Any" in e and "NewType" in e
                for e in errors
            ), f"Expected provenance error naming 'Any'; got: {errors}"
        finally:
            Path(temp_path).unlink()


# ---------------------------------------------------------------------------
# R10.2 — Assignment evaluation order proofs
# ---------------------------------------------------------------------------


class TestAssignmentEvaluationOrder:
    """Negative proof for the right-hand-side evaluation order fix.

    R10 swaps the order in :func:`_walk_with_source_order` so the
    right-hand side of an assignment is validated against the
    binding snapshot that was active BEFORE the assignment. This
    matches Python's actual evaluation semantics: the RHS is
    evaluated first, then the result is assigned to the target.
    """

    def test_self_rebinding_with_newtype_call_validates_rhs_first(self) -> None:
        """``from typing import NewType`` then ``NewType = NewType('NewType', str)``.

        The right-hand ``NewType('NewType', str)`` is evaluated
        against the trusted binding because the binding update for
        the LHS happens AFTER the RHS validation. The walk must
        ACCEPT the RHS call. The post-assignment sentinel then
        invalidates any subsequent ``NewType(...)`` call.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Self-rebinding NewType with trusted RHS."""\n')
            f.write("from typing import NewType\n\n")
            f.write("NewType = NewType('NewType', str)\n\n")
            f.write(
                "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            )
            temp_path = f.name
        try:
            # The RHS ``NewType('NewType', str)`` is accepted; only
            # the post-rebind ``NewType('RawEvidenceText', str)``
            # is rejected because the sentinel is installed after
            # the first assignment.
            errors = check_newtype_provenance(
                __import__("ast").parse(
                    Path(temp_path).read_text(encoding="utf-8"),
                    filename=temp_path,
                ),
                temp_path,
            )
            assert any(
                "rebound" in e.lower() or "sentinel" in e.lower() or "no longer resolves" in e.lower()
                for e in errors
            ), f"Expected post-rebind rejection for second call; got: {errors}"
            # The first RHS must NOT itself produce an error.
            assert not any(
                "RawEvidenceText" in e and ("non-trusted" in e or "Any" in e)
                for e in errors
            ), f"RHS validation incorrectly rejected the trusted call; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_trusted_assignment_remains_valid_after_walk(self) -> None:
        """After ``NewType = NewType('NewType', str)`` the binding is
        the sentinel, so any further call must be rejected - but
        the RHS of that same assignment MUST be allowed.

        This bypasses :func:`check_canonical_redaction_aliases`
        (which fires its own hierarchy-mismatch errors first) and
        uses the lower-level :func:`check_newtype_provenance`
        directly so the post-rebind rejection is the only error
        observed.
        """
        import ast as _ast

        source = (
            '"""Verify RHS-vs-LHS split."""\n'
            "from typing import NewType\n"
            "NewType = NewType('NewType', str)\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
        )
        tree = _ast.parse(source)
        errors = check_newtype_provenance(tree, "<synthetic>")
        # The single canonical rebind error proves:
        #   1. The RHS of ``NewType = NewType('NewType', str)`` was
        #      ACCEPTED against the trusted binding snapshot (R10
        #      validates the RHS first).
        #   2. The second call ``NewType('RawEvidenceText', str)``
        #      was rejected because the post-rebind sentinel is in
        #      effect.
        # If the buggy R9 order were still active, the walker would
        # also (or only) reject the first RHS because the sentinel
        # would be installed before validation.
        assert len(errors) == 1, (
            f"Expected exactly one post-rebind error; got {len(errors)}: {errors}"
        )
        assert (
            "rebound" in errors[0].lower()
            or "no longer resolves" in errors[0].lower()
        ), f"Expected rebind message; got: {errors[0]}"


# ---------------------------------------------------------------------------
# R10.3 — Positive regression: legitimate modules still pass
# ---------------------------------------------------------------------------


class TestLegitimateExactBindings:
    """Sanity proofs that the exact-binding check does not regress
    legitimate modules.
    """

    def test_trusted_bare_binding_constant_matches_canonical_import(self) -> None:
        """The trusted bare-call binding is exactly what
        ``from typing import NewType`` produces.
        """
        import ast as _ast

        from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
            build_newtype_bindings,
        )
        tree = _ast.parse("from typing import NewType\n")
        bindings = build_newtype_bindings(tree)
        assert bindings["NewType"] == TRUSTED_BARE_NEWTYPE_BINDING
        assert TRUSTED_BARE_NEWTYPE_BINDING == Binding(
            kind="from-import",
            module="typing",
            level=0,
            original_name="NewType",
            local_name="NewType",
        )

    def test_trusted_qualified_binding_constant_matches_canonical_import(self) -> None:
        """The trusted qualified-call binding is exactly what
        ``import typing`` produces.
        """
        import ast as _ast

        from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
            build_newtype_bindings,
        )
        tree = _ast.parse("import typing\n")
        bindings = build_newtype_bindings(tree)
        assert bindings["typing"] == TRUSTED_QUALIFIED_TYPING_BINDING
        assert TRUSTED_QUALIFIED_TYPING_BINDING == Binding(
            kind="import",
            module="typing",
            level=0,
            original_name="typing",
            local_name="typing",
        )

    def test_aliased_import_builds_non_trusted_binding(self) -> None:
        """``from typing import Any as NewType`` builds a binding that
        is NOT equal to the trusted bare binding.
        """
        import ast as _ast

        from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
            build_newtype_bindings,
        )
        tree = _ast.parse("from typing import Any as NewType\n")
        bindings = build_newtype_bindings(tree)
        assert bindings["NewType"] == Binding(
            kind="from-import",
            module="typing",
            level=0,
            original_name="Any",
            local_name="NewType",
        )
        assert bindings["NewType"] != TRUSTED_BARE_NEWTYPE_BINDING

    def test_legitimate_canonical_module_passes_after_r10(self) -> None:
        """Plain ``from typing import NewType`` + canonical calls still passes."""
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
            assert errors == [], (
                f"Legitimate canonical module must pass after R10: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_legitimate_qualified_canonical_module_passes_after_r10(self) -> None:
        """``import typing`` + qualified calls still pass after R10."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Legitimate canonical module (qualified)."""\n')
            f.write("import typing\n\n")
            f.write("RawEvidenceText = typing.NewType('RawEvidenceText', str)\n")
            f.write(
                "RedactedEvidenceText = typing.NewType('RedactedEvidenceText', str)\n"
            )
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
                f"Legitimate qualified canonical module must pass after R10: {errors}"
            )
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
