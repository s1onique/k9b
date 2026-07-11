"""R19 negative-proof tests for the LLM-safe evidence boundary verifier.

R17 closed the walrus (``ast.NamedExpr``) bypass for statement
contexts and R18 extended coverage to AugAssign, Assert, Raise,
Match.subject, except handler, function/class header expressions,
and lambda bodies (which remain a scope boundary).

R19 closes the remaining annotation/expression-context holes:

* ``AnnAssign.annotation`` at module scope (e.g.
  ``value: (str := int) = 1`` rebinds ``str``).
* ``FunctionDef`` parameter annotations including positional,
  positional-only, ``*args``, keyword-only, ``**kwargs``.
* ``FunctionDef`` ``return`` annotation.
* lambda positional default (``lambda value=(str := int): ...``)
  rebinds ``str`` at module scope.
* lambda keyword-only default (``lambda *, value=(NewType := fake): ...``)
  rebinds ``NewType`` at module scope.

R19 also preserves the existing positive proofs:

* walrus inside a lambda body does NOT rebind at module scope.
* walrus inside a function/class body does NOT rebind at module scope.
* the legitimate canonical module still passes.

The synthetic-fixture helper compiles each source first via
``compile()`` so that any non-compilable proof is detected
immediately rather than silently passing through ``ast.parse``
(for example, walrus in a comprehension ``iter`` slot is forbidden
by PEP 572 but ``ast.parse`` still accepts it).

Annotation-walrus source code was accepted by Python 3.11 and 3.12
but is rejected at compile time by Python 3.13+ (PEP 649 transition).
The verifier is AST-based and must reject these forms statically for
backward compatibility with older Python versions. For these
specific fixtures we provide a parser that uses ``ast.parse`` only;
the structure proves the verifier handles the AST shape the
canonical module would see on a 3.11/3.12 interpreter.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary._llm_safe_alias_supertypes import (
    validate_canonical_alias_super_types,
)
from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    LLM_SAFE_TYPES,
)
from scripts.incident_lifecycle_boundary._llm_safe_named_expr_walker import (
    scan_module_scope_named_expr_rebindings,
)
from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
    check_newtype_provenance,
)

REPO_ROOT = Path(__file__).parent.parent.parent
EXPECTED_ALIASES = LLM_SAFE_TYPES


def _parse(source: str) -> ast.Module:
    """Parse ``source`` after compiling it.

    R19 invariant: every synthetic negative-proof fixture MUST be
    fully compilable Python. ``ast.parse`` accepts code that the
    full compiler refuses, so we run ``compile()`` first and only
    fall through to ``ast.parse`` after the source compiles.
    """
    compile(source, "<synthetic>", "exec")
    return ast.parse(source)


def _parse_only(source: str) -> ast.Module:
    """Parse ``source`` WITHOUT compiling (used for annotation-walrus fixtures).

    Python 3.13+ rejects walrus inside an annotation at compile
    time, but the AST shape is identical to what older Python
    versions produce and what a real attack would build. The
    verifier is AST-based and should still emit a diagnostic
    when it sees a ``NamedExpr`` in an annotation slot.
    """
    return ast.parse(source)


def _supertype_errors(source: str, *, parse_only: bool = False) -> list[str]:
    if parse_only:
        tree = _parse_only(source)
    else:
        tree = _parse(source)
    return validate_canonical_alias_super_types(
        tree, "<synthetic>", EXPECTED_ALIASES
    )


def _provenance_errors(source: str) -> list[str]:
    return check_newtype_provenance(_parse(source), "<synthetic>")


def _walker_only_errors(source: str, *, parse_only: bool = False) -> list[str]:
    """Run ONLY the walrus walker, ignoring the rest of the verifier."""
    if parse_only:
        tree = _parse_only(source)
    else:
        tree = _parse(source)
    errs: list[str] = []
    scan_module_scope_named_expr_rebindings(tree, "<synthetic>", errs)
    return errs


# ---------------------------------------------------------------------------
# R19 NEW: AnnAssign.annotation.
# ---------------------------------------------------------------------------


class TestR19AnnAssignAnnotation:
    """R19: ``name: T = value`` rebinds ``T`` at module scope."""

    def test_ann_assign_annotation_walrus_rebind_str(self) -> None:
        """``value: (str := int) = 1`` rebinds ``str`` at module scope.

        Walrus inside ``AnnAssign.annotation`` is rejected at
        compile time by Python 3.13+, but older Python 3.11/3.12
        accepted it. The verifier must catch it statically.
        """
        source = textwrap.dedent(
            """\
            \"\"\"AnnAssign annotation walrus rebinds str at module scope.\"\"\"
            from typing import NewType
            value: (str := int) = 1
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source, parse_only=True)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for AnnAssign annotation; got: {errors}"


# ---------------------------------------------------------------------------
# R19 NEW: FunctionDef parameter annotations + return annotation.
# ---------------------------------------------------------------------------


class TestR19FunctionParameterAnnotation:
    """R19: annotations on ``def`` parameters rebind at module scope."""

    def test_positional_param_annotation_walrus_rebind_str(self) -> None:
        """``def helper(value: (str := int)):`` rebinds ``str`` at module scope."""
        source = textwrap.dedent(
            """\
            \"\"\"def param annotation walrus rebinds str.\"\"\"
            from typing import NewType
            def helper(value: (str := int)):
                return value
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source, parse_only=True)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for def param annotation; got: {errors}"


class TestR19FunctionReturnAnnotation:
    """R19: ``def f() -> T:`` rebinds ``T`` at module scope."""

    def test_return_annotation_walrus_rebind_newtype(self) -> None:
        """``def helper() -> (NewType := fake.NewType):`` rebinds ``NewType``."""
        source = textwrap.dedent(
            """\
            \"\"\"def return annotation walrus rebinds NewType.\"\"\"
            from typing import NewType
            def helper() -> (NewType := fake.NewType):
                return NewType('RawEvidenceText', str)
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source, parse_only=True)
        assert any(
            "walrus" in e.lower() and "newtype" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for return annotation; got: {errors}"


# ---------------------------------------------------------------------------
# R19 NEW: Lambda defaults (positional + keyword-only).
# ---------------------------------------------------------------------------


class TestR19LambdaPositionalDefault:
    """R19: ``lambda value=(y := expr): value`` rebinds ``y`` at module scope."""

    def test_lambda_positional_default_walrus_rebind_str(self) -> None:
        source = textwrap.dedent(
            """\
            \"\"\"lambda positional default rebinds str.\"\"\"
            from typing import NewType
            probe = lambda value=(str := int): value
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for lambda positional default; got: {errors}"


class TestR19LambdaKeywordOnlyDefault:
    """R19: ``lambda *, value=(y := expr): value`` rebinds ``y`` at module scope."""

    def test_lambda_kw_only_default_walrus_rebind_newtype(self) -> None:
        source = textwrap.dedent(
            """\
            \"\"\"lambda kw-only default rebinds NewType.\"\"\"
            from typing import NewType
            probe = lambda *, value=(NewType := fake.NewType): value
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "newtype" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for lambda kw-only default; got: {errors}"


# ---------------------------------------------------------------------------
# R19 Positive proofs: lambda body + function/class body walruses do NOT rebind.
# ---------------------------------------------------------------------------


class TestR19LambdaBodyPositive:
    """Walrus inside a lambda body binds to lambda scope, not module."""

    def test_lambda_body_walrus_does_not_rebind_str(self) -> None:
        """``probe = lambda: (str := int)`` MUST NOT be flagged by R19.

        PEP 572 explicitly says a lambda is a scope for
        assignment-expression purposes. The walker descended into
        lambda defaults in R19 but it MUST NOT descend into a
        lambda body.
        """
        source = textwrap.dedent(
            """\
            \"\"\"Walrus in lambda body is a lambda-scope binding.\"\"\"
            from typing import NewType
            probe = lambda: (str := int)
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        werrs = _walker_only_errors(source)
        assert not any("walrus" in e.lower() and "str" in e.lower() for e in werrs), (
            f"Walker must not flag lambda-body walrus; got: {werrs}"
        )
        errors = _supertype_errors(source)
        assert not any("walrus" in e.lower() and "str" in e.lower() for e in errors), (
            f"Supertype verifier must not flag lambda-body walrus; got: {errors}"
        )


class TestR19FunctionBodyPositive:
    """Walrus inside a function body binds to function scope, not module."""

    def test_function_body_walrus_does_not_rebind_str(self) -> None:
        """``def helper(): (str := int)`` MUST NOT be flagged by R19.

        Walrus targets inside a function body bind to the
        function's own local namespace, not module scope.
        """
        source = textwrap.dedent(
            """\
            \"\"\"Walrus in a function body is a function-scope binding.\"\"\"
            from typing import NewType
            def helper():
                s = (str := int)
                return s
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        werrs = _walker_only_errors(source)
        assert not any("walrus" in e.lower() and "str" in e.lower() for e in werrs), (
            f"Walker must not flag function-body walrus; got: {werrs}"
        )


class TestR19CanonicalRegressionPositive:
    """The legitimate canonical module still passes under R19."""

    def test_legitimate_canonical_module_still_passes(self) -> None:
        """The actual canonical module passes under R19."""
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
            f"Legitimate canonical module must pass under R19: {errors}"
        )


# ---------------------------------------------------------------------------
# Sanity regression: all R17/R18 cases still pass under R19 walker.
# ---------------------------------------------------------------------------


class TestR19SanityRegressions:
    """Sanity proofs: R19 walker continues to reject R17/R18 cases."""

    def test_top_level_walrus_newtype_still_rejected(self) -> None:
        source = textwrap.dedent(
            """\
            \"\"\"Top-level walrus rebinds NewType.\"\"\"
            from typing import NewType
            (NewType := fake.NewType)
            """
        )
        errors = _provenance_errors(source)
        assert any(
            "walrus" in e.lower() and "newtype" in e.lower() for e in errors
        ), f"R17 case must still reject; got: {errors}"

    def test_function_default_walrus_still_rejected(self) -> None:
        """R18 case (function default) still rejected by R19 walker."""
        source = textwrap.dedent(
            """\
            \"\"\"def helper(value=(str := int)): rebinds str.\"\"\"
            def helper(value=(str := int)):
                return value
            """
        )
        errs = _walker_only_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errs
        ), f"R18 case must still reject; got: {errs}"

    def test_aug_assign_walrus_still_rejected(self) -> None:
        """R18 case (AugAssign walrus) still rejected by R19 walker."""
        source = textwrap.dedent(
            """\
            \"\"\"counter += (str := int) rebinds str.\"\"\"
            counter = 0
            counter += (str := int)
            """
        )
        errs = _walker_only_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errs
        ), f"R18 case must still reject; got: {errs}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
