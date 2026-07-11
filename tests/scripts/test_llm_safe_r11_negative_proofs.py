"""R11 negative-proof tests for the LLM-safe evidence boundary verifier.

These tests close two remaining R10 bypasses:

1. **Relative-import provenance** (closure requirement R11 #4):
   ``from .typing import NewType`` and ``from ..typing import NewType``
   resolve to a different (parent package's) ``typing`` module at
   runtime, but the R10 binding tuple recorded only ``module`` and
   not the relative-import level. R11 extends the binding identity
   with ``level`` and the trusted bindings REQUIRE ``level == 0``
   so relative imports cannot smuggle a trusted local name from a
   different package.

2. **Attribute integrity** (closure requirement R11 #5):
   The R10 verifier proved the local name ``typing`` came from
   ``import typing``, but did not protect the ``NewType`` attribute
   itself. An attacker could write
   ``typing.NewType = fake.NewType`` so subsequent
   ``typing.NewType(...)`` calls resolve to the untrusted
   replacement. R11 detects mutation/deletion of the
   ``typing.NewType`` attribute (and the symmetric
   ``typing.typing`` case) and fails closed.

Negative proofs (each MUST reject the offending source):

* ``from .typing import NewType`` -> FAIL
* ``from ..typing import NewType`` -> FAIL
* ``from typing import NewType`` followed by
  ``typing.NewType = fake.NewType`` followed by a
  ``typing.NewType(...)`` call -> FAIL
* ``import typing`` followed by ``typing.NewType: object = X`` -> FAIL
* ``import typing`` followed by ``typing.NewType += X`` -> FAIL
* ``import typing`` followed by ``del typing.NewType`` -> FAIL
* ``import typing`` followed by
  ``setattr(typing, "NewType", fake.NewType)`` -> FAIL

Sanity proofs:

* ``from typing import NewType`` + canonical calls -> PASS (R11
  preserves R10 legitimate behaviour)
* ``from typing import NewType`` + bare
  ``typing.NewType = NewType('NewType', str)`` self-rebind -> FAIL
  only on the post-rebind call (R11 preserves R10 evaluation order)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
    REBINDING_SENTINEL,
    TRUSTED_BARE_NEWTYPE_BINDING,
    Binding,
    build_newtype_bindings,
    check_newtype_provenance,
)


def _synthetic_provenance_errors(source: str) -> list[str]:
    """Run the per-call-site provenance check on a synthetic source."""
    import ast as _ast

    tree = _ast.parse(source)
    return check_newtype_provenance(tree, "<synthetic>")


class TestRelativeImportProvenance:
    """R11 #4: ``ImportFrom.level`` is encoded in the binding identity.

    Python represents ``from .typing import NewType`` as an
    ``ImportFrom`` whose ``module`` is still ``"typing"`` but whose
    ``level`` is ``1``. R10 saw ``module == "typing"`` and
    accepted the call. R11 requires ``level == 0`` for the trusted
    binding so the same-named ``typing`` symbol from a different
    package cannot bypass the per-call-site check.
    """

    def test_relative_level_one_typing_newtype_is_rejected(self) -> None:
        """``from .typing import NewType`` must fail closed.

        The binding is ``Binding(kind="from-import",
        module="typing", level=1, original_name="NewType",
        local_name="NewType")``. R11 requires ``level == 0`` for
        the trusted bare-call form.
        """
        source = (
            '"""Relative level=1 typing import."""\n'
            "from .typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            temp_path = f.name
        try:
            errors = _synthetic_provenance_errors(source)
            assert len(errors) > 0, (
                "Expected relative level=1 import rejection; got empty errors"
            )
            # Every emitted error is a rejection (the walk emits
            # one per NewType call site, all of which fail).
            assert any(
                "kind=" in e or "level" in e or "original_name=" in e
                for e in errors
            ), f"Expected exact-binding mismatch error; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_relative_level_two_typing_newtype_is_rejected(self) -> None:
        """``from ..typing import NewType`` must fail closed."""
        source = (
            '"""Relative level=2 typing import."""\n'
            "from ..typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert len(errors) > 0, (
            "Expected relative level=2 import rejection; got empty errors"
        )

    def test_absolute_import_records_level_zero(self) -> None:
        """``from typing import NewType`` records ``level=0`` in the
        binding identity.
        """
        import ast as _ast

        tree = _ast.parse("from typing import NewType\n")
        bindings = build_newtype_bindings(tree)
        assert bindings["NewType"] == TRUSTED_BARE_NEWTYPE_BINDING
        assert bindings["NewType"].level == 0
        # Sanity: a hand-constructed binding with the same fields
        # matches the trusted constant.
        assert Binding(
            kind="from-import",
            module="typing",
            level=0,
            original_name="NewType",
            local_name="NewType",
        ) == TRUSTED_BARE_NEWTYPE_BINDING


class TestAttributeIntegrityMutation:
    """R11 #5: attribute mutation/deletion of ``typing.NewType`` fails closed.

    R10 proved that ``typing`` came from ``import typing`` but did
    not protect the ``NewType`` attribute subsequently invoked.
    R11 installs the :data:`REBINDING_SENTINEL` on the base name
    (``typing``) when any attribute mutation form targets a
    sensitive attribute, and the post-mutation call fails closed.
    """

    def test_typing_newtype_assign_attribute_fails_closed(self) -> None:
        """``typing.NewType = fake.NewType`` then
        ``typing.NewType('Foo', str)`` is rejected.
        """
        source = (
            '"""typing.NewType attribute rebind."""\n'
            "import typing\n"
            "import fake\n"
            "typing.NewType = fake.NewType\n"
            "RawEvidenceText = typing.NewType('RawEvidenceText', str)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "rebound" in e.lower() or "no longer resolves" in e.lower()
            for e in errors
        ), f"Expected attribute-mutation rejection; got: {errors}"

    def test_typing_newtype_annassign_attribute_fails_closed(self) -> None:
        """``typing.NewType: object = fake.NewType`` then
        ``typing.NewType('Foo', str)`` is rejected.
        """
        source = (
            '"""typing.NewType annotated attribute rebind."""\n'
            "import typing\n"
            "import fake\n"
            "typing.NewType: object = fake.NewType\n"
            "RawEvidenceText = typing.NewType('RawEvidenceText', str)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "rebound" in e.lower() or "no longer resolves" in e.lower()
            for e in errors
        ), f"Expected AnnAssign-attribute-mutation rejection; got: {errors}"

    def test_typing_newtype_augassign_attribute_fails_closed(self) -> None:
        """``typing.NewType += X`` then a later call is rejected.

        The AugAssign itself installs the sentinel because it
        mutates the attribute; the call after it fails closed.
        """
        source = (
            '"""typing.NewType augmented attribute rebind."""\n'
            "import typing\n"
            "typing.NewType += lambda *a: None\n"
            "RawEvidenceText = typing.NewType('RawEvidenceText', str)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "rebound" in e.lower() or "no longer resolves" in e.lower()
            for e in errors
        ), f"Expected AugAssign-attribute-mutation rejection; got: {errors}"

    def test_typing_newtype_delete_fails_closed(self) -> None:
        """``del typing.NewType`` then ``typing.NewType('Foo', str)``
        is rejected.
        """
        source = (
            '"""typing.NewType deletion."""\n'
            "import typing\n"
            "del typing.NewType\n"
            "RawEvidenceText = typing.NewType('RawEvidenceText', str)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "rebound" in e.lower() or "no longer resolves" in e.lower()
            for e in errors
        ), f"Expected attribute-deletion rejection; got: {errors}"

    def test_setattr_typing_newtype_fails_closed(self) -> None:
        """``setattr(typing, "NewType", fake.NewType)`` then a later
        call is rejected.
        """
        source = (
            '"""typing.NewType setattr."""\n'
            "import typing\n"
            "import fake\n"
            "setattr(typing, 'NewType', fake.NewType)\n"
            "RawEvidenceText = typing.NewType('RawEvidenceText', str)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "rebound" in e.lower() or "no longer resolves" in e.lower()
            for e in errors
        ), f"Expected setattr-mutation rejection; got: {errors}"

    def test_bare_newtype_attribute_mutation_is_rejected(self) -> None:
        """``NewType.attr = X`` at module scope also fails closed.

        The walker installs the sentinel on the base name
        (``NewType``) and any subsequent use of that base name
        fails closed.
        """
        source = (
            '"""NewType attribute rebind."""\n'
            "from typing import NewType\n"
            "import fake\n"
            "NewType.something = fake.NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert any(
            "rebound" in e.lower() or "no longer resolves" in e.lower()
            for e in errors
        ), f"Expected bare-Name attribute-mutation rejection; got: {errors}"


class TestR11SanityRegressions:
    """Sanity proofs: R11 does not regress the R10 positive cases."""

    def test_legitimate_absolute_import_still_passes(self) -> None:
        """``from typing import NewType`` + bare canonical calls
        still produce zero errors.
        """
        source = (
            '"""Legitimate canonical module."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert errors == [], (
            f"Legitimate absolute import must pass after R11: {errors}"
        )

    def test_self_rebinding_still_fails_only_post_rebind(self) -> None:
        """``from typing import NewType`` then
        ``NewType = NewType('NewType', str)`` still accepts the RHS
        and only rejects the post-rebind call.
        """
        source = (
            '"""Self-rebinding NewType."""\n'
            "from typing import NewType\n"
            "NewType = NewType('NewType', str)\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
        )
        errors = _synthetic_provenance_errors(source)
        assert len(errors) == 1, (
            f"Expected exactly one post-rebind error; got {len(errors)}: {errors}"
        )


# Direct sanity check that the sentinel binding identity is what
# the walker actually installs. Run as a module-level assertion so a
# regression in the sentinel shape fails the test module immediately.
def test_sentinel_binding_shape() -> None:
    """The sentinel must be the singleton REBINDING_SENTINEL with the
    ``<rebinding>`` kind so ``is`` comparisons in the walker hold.
    """
    assert REBINDING_SENTINEL.kind == "<rebinding>"
    assert REBINDING_SENTINEL.module == "<unknown>"
    assert REBINDING_SENTINEL.original_name == "<unknown>"
    assert REBINDING_SENTINEL.local_name == "<unknown>"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
