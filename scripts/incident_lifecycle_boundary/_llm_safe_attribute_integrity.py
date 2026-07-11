"""Attribute mutation detection for LLM-safe provenance walker.

This module hosts the small set of helpers that detect module-scope
attribute mutation on provenance-sensitive names
(``typing.NewType = X``, ``del typing.NewType``,
``setattr(typing, "NewType", ...)``, etc.). Such mutations cannot be
statically resolved to a trusted module, so the source-order walker
emits an immediate diagnostic AND installs the
:data:`REBINDING_SENTINEL` on the base name so any subsequent
``typing.NewType(...)`` call fails closed.

Splitting these helpers out keeps the main walker module under the
LLM-friendly file size threshold.

Public surface:

* :func:`iter_attribute_targets` - yield ``(base, attr)`` for
  ``Name.attr`` targets.
* :func:`classify_sensitive_attribute_mutation` - return a string
  describing the mutation form (``"assign"``, ``"augassign"``,
  ``"annassign"``, ``"delete"``) for a statement that mutates an
  attribute of a sensitive name, or ``None`` if the statement does
  not mutate such an attribute.
* :func:`detect_setattr_sensitive` - return a string describing the
  setattr form (``"literal"`` for ``setattr(typing, "NewType", ...)``,
  ``"dynamic"`` for ``setattr(typing, <non-literal>, ...)`` and any
  attribute access via ``builtins.setattr``/``__builtins__.setattr``,
  or ``None`` if the statement is not a sensitive setattr.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator

from scripts.incident_lifecycle_boundary._llm_safe_provenance_types import (
    PROVENANCE_SENSITIVE_NAMES,
)


def iter_attribute_targets(target: ast.AST) -> Iterator[tuple[str, str]]:
    """Yield ``(base_name, attr_name)`` for attribute targets on ``Name`` bases.

    Only handles the ``Name.attr`` shape (e.g. ``typing.NewType``);
    nested attribute targets (``a.b.c``) are not yielded because
    they cannot target a sensitive module-scope name directly.
    """
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        yield (target.value.id, target.attr)


def classify_sensitive_attribute_mutation(stmt: ast.stmt) -> str | None:
    """Return the mutation form if ``stmt`` mutates an attribute of a
    provenance-sensitive name, otherwise ``None``.

    Returns one of:
    * ``"assign"`` for ``typing.NewType = X``
    * ``"augassign"`` for ``typing.NewType += X``
    * ``"annassign"`` for ``typing.NewType: T = X``
    * ``"delete"`` for ``del typing.NewType``

    The returned string drives the diagnostic message emitted by the
    walker; the walker also installs the :data:`REBINDING_SENTINEL` so
    any subsequent ``typing.NewType(...)`` call fails closed.
    """
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            for base, _attr in iter_attribute_targets(target):
                if base in PROVENANCE_SENSITIVE_NAMES:
                    return "assign"
        return None
    if isinstance(stmt, ast.AugAssign):
        for base, _attr in iter_attribute_targets(stmt.target):
            if base in PROVENANCE_SENSITIVE_NAMES:
                return "augassign"
        return None
    if isinstance(stmt, ast.AnnAssign):
        for base, _attr in iter_attribute_targets(stmt.target):
            if base in PROVENANCE_SENSITIVE_NAMES:
                return "annassign"
        return None
    if isinstance(stmt, ast.Delete):
        for target in stmt.targets:
            for base, _attr in iter_attribute_targets(target):
                if base in PROVENANCE_SENSITIVE_NAMES:
                    return "delete"
        return None
    return None


def detect_setattr_sensitive(stmt: ast.stmt) -> str | None:
    """Return the setattr form if ``stmt`` is a sensitive setattr, else ``None``.

    Returns:
    * ``"literal"`` for ``setattr(typing, "NewType", ...)`` where the
      attribute is a string literal equal to ``"NewType"`` or
      ``"typing"``.
    * ``"dynamic"`` for any module-scope ``setattr(typing, ...)``
      call where the attribute name is not a literal string, or where
      the call is reached through ``builtins.setattr`` /
      ``__builtins__.setattr`` (an aliased setattr cannot be
      statically proven harmless).
    * ``None`` otherwise.

    The walker emits an immediate diagnostic on any non-``None``
    result; the ``"literal"`` form also installs the sentinel on the
    base name for any subsequent call.
    """
    if not isinstance(stmt, ast.Expr):
        return None
    call = stmt.value
    if not isinstance(call, ast.Call):
        return None
    func = call.func

    # ``setattr(typing, "NewType", ...)`` form: ``func`` is a ``Name``.
    if isinstance(func, ast.Name) and func.id == "setattr":
        if len(call.args) < 2:
            return None
        base_arg, _value_arg = call.args[0], call.args[1]
        if not isinstance(base_arg, ast.Name):
            return None
        if base_arg.id not in PROVENANCE_SENSITIVE_NAMES:
            return None
        attr_arg = call.args[1]
        if (
            isinstance(attr_arg, ast.Constant)
            and isinstance(attr_arg.value, str)
        ):
            if attr_arg.value in PROVENANCE_SENSITIVE_NAMES:
                return "literal"
            # Literal attribute name but not a sensitive attribute;
            # still safer to reject because the target type is
            # sensitive and any mutation is unresolvable.
            return "literal"
        # Non-literal attribute name on a sensitive base: dynamic.
        return "dynamic"

    # ``builtins.setattr(typing, ...)`` or ``__builtins__.setattr(...)``.
    # Aliased setattr cannot be statically proven harmless.
    if isinstance(func, ast.Attribute) and func.attr == "setattr":
        if isinstance(func.value, ast.Name) and func.value.id in {
            "builtins",
            "__builtins__",
        }:
            if len(call.args) < 2:
                return None
            base_arg = call.args[0]
            if not isinstance(base_arg, ast.Name):
                return None
            if base_arg.id not in PROVENANCE_SENSITIVE_NAMES:
                return None
            attr_arg = call.args[1]
            if (
                isinstance(attr_arg, ast.Constant)
                and isinstance(attr_arg.value, str)
            ):
                if attr_arg.value in PROVENANCE_SENSITIVE_NAMES:
                    return "literal"
                return "literal"
            return "dynamic"

    return None


__all__ = [
    "classify_sensitive_attribute_mutation",
    "detect_setattr_sensitive",
    "iter_attribute_targets",
]
