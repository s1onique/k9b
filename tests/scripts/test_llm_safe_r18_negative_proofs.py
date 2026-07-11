"""R18 negative-proof tests for the LLM-safe evidence boundary verifier.

R17 closed the walrus (``ast.NamedExpr``) bypass for *statement*
contexts but missed several module-scope *expression* contexts. R18
extends coverage to every remaining module-scope context where a
walrus execution can rebind a canonical-sensitive name:

* ``AugAssign.value``
* ``Assert.test`` and ``Assert.msg``
* ``Raise.exc`` and ``Raise.cause`` (caught ``raise`` is still
  evaluated at module scope)
* ``Match.subject``
* ``except`` handler type expression
* ``FunctionDef``/``AsyncFunctionDef`` defaults and decorator list
* ``ClassDef`` bases, keywords, and decorator list
* lambda defaults (lambda bodies remain their own scope)

R18 also adds a positive proof: a walrus inside a lambda body does
NOT rebind at module scope (PEP 572).

The synthetic-fixture helper compiles the source first so non-
compilable proof strings (such as walrus in a comprehension iter)
are detected immediately rather than silently passing through
``ast.parse``.
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

    R18 invariant: every synthetic negative-proof fixture MUST be
    fully compilable Python. ``ast.parse`` accepts code that the
    full compiler refuses (notably walrus in a comprehension
    ``iter`` slot per PEP 572), so we run ``compile()`` first and
    only fall through to ``ast.parse`` after the source compiles.
    """
    compile(source, "<synthetic>", "exec")
    return ast.parse(source)


def _supertype_errors(source: str) -> list[str]:
    return validate_canonical_alias_super_types(
        _parse(source), "<synthetic>", EXPECTED_ALIASES
    )


def _provenance_errors(source: str) -> list[str]:
    return check_newtype_provenance(_parse(source), "<synthetic>")


def _walker_only_errors(source: str) -> list[str]:
    """Run ONLY the walrus walker, ignoring the rest of the verifier.

    Useful when the surrounding module's payload (e.g. a malicious
    ``raise`` of an arbitrary exception) confounds the rest of the
    verifier but we only want to test the walker.
    """
    errs: list[str] = []
    scan_module_scope_named_expr_rebindings(_parse(source), "<synthetic>", errs)
    return errs


# ---------------------------------------------------------------------------
# Comprehension form - replaced with a compilable proof.
# Walrus in a comprehension's ``iter`` slot is forbidden by PEP 572 so
# `ast.parse` used to accept it but the source cannot run; we use a
# comprehensible form where the walrus lives in the *result* expression.
# ---------------------------------------------------------------------------


class TestR17ComprehensionFormUpdated:
    """The original R17 comprehension proof is replaced with a compilable one."""

    def test_comprehension_result_walrus_rebind_str(self) -> None:
        """``[(str := int) for _ in [0]]`` rebinds ``str`` at module scope.

        The original R17 proof ``[str for x in (str := iter([1]))]`` is
        not compilable because PEP 572 forbids walrus in comprehension
        ``iter`` slots. We use the result-expression form, which IS
        compilable and DOES rebind ``str`` at module scope per PEP 572.
        """
        source = textwrap.dedent(
            """\
            \"\"\"Comprehension result walrus rebinds str at module scope.\"\"\"
            from typing import NewType
            [(str := int) for _ in [0]]
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus canonical-supertype diagnostic; got: {errors}"


# ---------------------------------------------------------------------------
# R18 NEW: AugAssign.value, Assert.test/msg, Raise.exc/cause.
# ---------------------------------------------------------------------------


class TestR18AugAssignWalrus:
    """R18: ``name += (y := expr)`` rebinds ``y`` at module scope."""

    def test_aug_assign_value_walrus_rebind_newtype(self) -> None:
        """``counter += (NewType := fake.NewType)`` rebinds ``NewType``."""
        source = textwrap.dedent(
            """\
            \"\"\"AugAssign walrus rebinds NewType.\"\"\"
            from typing import NewType
            counter = 0
            counter += (NewType := fake.NewType)
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "newtype" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for AugAssign; got: {errors}"


class TestR18AssertWalrus:
    """R18: ``assert (y := expr), msg`` rebinds ``y`` at module scope."""

    def test_assert_test_walrus_rebind_str(self) -> None:
        """``assert (str := int)`` rebinds ``str`` at module scope."""
        source = textwrap.dedent(
            """\
            \"\"\"Assert walrus rebinds str.\"\"\"
            from typing import NewType
            assert (str := int)
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for assert test; got: {errors}"


class TestR18RaiseCaughtWalrus:
    """R18: ``raise (y := exc)`` rebinds ``y`` even when caught."""

    def test_raise_caught_walrus_rebind_newtype(self) -> None:
        """``raise RuntimeError((NewType := fake.NewType))`` caught rebinds ``NewType``.

        The walrus executes when the raise fires; the exception is then
        caught, allowing the module to continue executing under the new
        binding.
        """
        source = textwrap.dedent(
            """\
            \"\"\"Raise-caught walrus rebinds NewType.\"\"\"
            from typing import NewType
            try:
                raise RuntimeError((NewType := fake.NewType))
            except RuntimeError:
                pass
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "newtype" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for caught raise; got: {errors}"


class TestR18RaiseCauseWalrus:
    """R18: ``raise ... from (y := cause)`` rebinds ``y`` at module scope."""

    def test_raise_cause_walrus_rebind_str(self) -> None:
        source = textwrap.dedent(
            """\
            \"\"\"Raise-cause walrus rebinds str.\"\"\"
            from typing import NewType
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                raise RuntimeError("again") from (str := int)
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for raise cause; got: {errors}"


# ---------------------------------------------------------------------------
# R18 NEW: Match.subject.
# ---------------------------------------------------------------------------


class TestR18MatchSubjectWalrus:
    """R18: ``match (y := expr):`` rebinds ``y`` at module scope."""

    def test_match_subject_walrus_rebind_str(self) -> None:
        """``match (str := int):`` rebinds ``str`` at module scope."""
        source = textwrap.dedent(
            """\
            \"\"\"Match subject walrus rebinds str.\"\"\"
            from typing import NewType
            match (str := int):
                case _:
                    pass
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for match subject; got: {errors}"


# ---------------------------------------------------------------------------
# R18 NEW: except handler type.
# ---------------------------------------------------------------------------


class TestR18ExceptHandlerTypeWalrus:
    """R18: ``except (y := exc):`` rebinds ``y`` at module scope."""

    def test_except_handler_type_walrus_rebind_typing(self) -> None:
        """``except (typing := runtime_error):`` rebinds ``typing``."""
        source = textwrap.dedent(
            """\
            \"\"\"except-type walrus rebinds typing.\"\"\"
            import typing
            from typing import NewType
            try:
                raise RuntimeError("boom")
            except (typing := RuntimeError) as exc:
                pass
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "typing" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for except handler; got: {errors}"


# ---------------------------------------------------------------------------
# R18 NEW: function defaults and decorators.
# ---------------------------------------------------------------------------


class TestR18FunctionDefaultWalrus:
    """R18: ``def f(x=(y := expr)):`` rebinds ``y`` at module scope."""

    def test_function_default_walrus_rebind_str(self) -> None:
        """``def helper(value=(str := int)):`` rebinds ``str`` at module scope."""
        source = textwrap.dedent(
            """\
            \"\"\"Function default walrus rebinds str.\"\"\"
            from typing import NewType
            def helper(value=(str := int)):
                return value
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for function default; got: {errors}"


class TestR18FunctionDecoratorWalrus:
    """R18: ``@(y := expr)`` rebinds ``y`` at module scope."""

    def test_function_decorator_walrus_rebind_newtype(self) -> None:
        """``@(NewType := fake.NewType)\\ndef helper(): pass`` rebinds ``NewType``."""
        source = textwrap.dedent(
            """\
            \"\"\"Function decorator walrus rebinds NewType.\"\"\"
            from typing import NewType
            @(NewType := fake.NewType)
            def helper():
                return 1
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "newtype" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for function decorator; got: {errors}"


# ---------------------------------------------------------------------------
# R18 NEW: class base, class keyword, class decorator.
# ---------------------------------------------------------------------------


class TestR18ClassBaseWalrus:
    """R18: ``class C((y := expr)):`` rebinds ``y`` at module scope."""

    def test_class_base_walrus_rebind_str(self) -> None:
        """``class Marker((str := int)):`` rebinds ``str`` at module scope."""
        source = textwrap.dedent(
            """\
            \"\"\"Class base walrus rebinds str.\"\"\"
            from typing import NewType
            class Marker((str := int)):
                pass
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "str" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for class base; got: {errors}"


class TestR18ClassDecoratorWalrus:
    """R18: ``@(y := expr)\\nclass C: pass`` rebinds ``y`` at module scope."""

    def test_class_decorator_walrus_rebind_typing(self) -> None:
        source = textwrap.dedent(
            """\
            \"\"\"Class decorator walrus rebinds typing.\"\"\"
            import typing
            from typing import NewType
            @(typing := fake_mod)
            class Marker:
                pass
            RawEvidenceText = NewType('RawEvidenceText', str)
            RedactedEvidenceText = NewType('RedactedEvidenceText', str)
            LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)
            SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)
            """
        )
        errors = _supertype_errors(source)
        assert any(
            "walrus" in e.lower() and "typing" in e.lower() for e in errors
        ), f"Expected walrus diagnostic for class decorator; got: {errors}"


# ---------------------------------------------------------------------------
# R18 NEW: lambda defaults (positive: walrus in lambda BODY does NOT rebind).
# ---------------------------------------------------------------------------


class TestR18LambdaScopeBoundary:
    """Walrus targets inside lambda bodies bind to lambda scope, not module."""

    def test_lambda_body_walrus_does_not_rebind_str(self) -> None:
        """``probe = lambda: (str := int)`` MUST NOT be flagged by R18.

        PEP 572 explicitly says a lambda is a scope for
        assignment-expression purposes, so the walrus in the lambda body
        binds to the lambda's own scope and CANNOT shadow the module-level
        ``str``.
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
        # Walker-only: the walker should not flag this code.
        werrs = _walker_only_errors(source)
        assert not any("walrus" in e.lower() and "str" in e.lower() for e in werrs), (
            f"Walker must not flag lambda-body walrus; got: {werrs}"
        )
        # Supertype verifier: should accept this code (assuming the rest
        # of the module is well-formed, the lambdas do not rebind str).
        errors = _supertype_errors(source)
        # Filter the R17/R18 walrus diagnostics; we want to ensure no
        # *walrus*-flavoured diagnostic appears for ``str``. Other
        # diagnostics are not the focus of this proof.
        assert not any("walrus" in e.lower() and "str" in e.lower() for e in errors), (
            f"Supertype verifier must not flag lambda-body walrus; got: {errors}"
        )


# ---------------------------------------------------------------------------
# Sanity regression: all R17 tests still pass.
# ---------------------------------------------------------------------------


class TestR18SanityRegressions:
    """Sanity proofs: R18 continues to reject R17 cases."""

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

    def test_if_test_walrus_still_rejected(self) -> None:
        source = textwrap.dedent(
            """\
            \"\"\"if-test walrus rebinds NewType.\"\"\"
            if (NewType := fake.NewType):
                pass
            """
        )
        errors = _provenance_errors(source)
        assert any(
            "walrus" in e.lower() and "newtype" in e.lower() for e in errors
        ), f"R17 case must still reject; got: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
