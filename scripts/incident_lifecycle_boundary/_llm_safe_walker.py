"""Source-order walker for the LLM-safe provenance walker.

R12 invariant: the walker descends through module-scope control
flow (``if``/``try``/``for``/``while``/``with``/``match``) and
walks statements in source order, validating each canonical
``NewType(...)`` call against the binding snapshot that was active
BEFORE the assignment, and only then applying the binding update
introduced by the statement. The walk order matches Python's actual
evaluation semantics.

The walker lives in its own module so the walker file stays under
the LLM-friendly file size threshold.

Public surface:

* :func:`walk_with_source_order` - walk statements in source order,
  applying the binding update for each statement AFTER validating
  any ``NewType(...)`` call in its right-hand side.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from scripts.incident_lifecycle_boundary._llm_safe_attribute_integrity import (
    classify_sensitive_attribute_mutation as _classify_sensitive_attribute_mutation,
)
from scripts.incident_lifecycle_boundary._llm_safe_attribute_integrity import (
    detect_setattr_sensitive as _detect_setattr_sensitive,
)
from scripts.incident_lifecycle_boundary._llm_safe_attribute_integrity import (
    iter_attribute_targets as _iter_attribute_targets,
)
from scripts.incident_lifecycle_boundary._llm_safe_diagnostics import (
    attribute_mutation_targets as _attribute_mutation_targets,
)
from scripts.incident_lifecycle_boundary._llm_safe_diagnostics import (
    describe_attribute_mutation as _describe_attribute_mutation,
)
from scripts.incident_lifecycle_boundary._llm_safe_diagnostics import (
    describe_setattr as _describe_setattr,
)
from scripts.incident_lifecycle_boundary._llm_safe_provenance_types import (
    PROVENANCE_SENSITIVE_NAMES,
    REBINDING_SENTINEL,
    Binding,
)
from scripts.incident_lifecycle_boundary._llm_safe_traversal import (
    _iter_target_names,
)

# Imported from the dedicated validation module so the walker and
# the public entry point share the same validation helper without
# a circular import. The walker validates each canonical
# ``Name = NewType(...)`` call's right-hand side AGAINST the binding
# snapshot that was active BEFORE the assignment - matching
# Python's evaluation semantics.
from scripts.incident_lifecycle_boundary._llm_safe_validate import (
    validate_newtype_call as _validate_newtype_call,
)


def _is_newtype_call_node(node: ast.AST) -> bool:
    """Return True if ``node`` is a ``NewType(...)`` call (bare or qualified)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "NewType":
        return True
    if isinstance(func, ast.Name) and func.id == "NewType":
        return True
    return False


def _apply_binding_update(
    stmt: ast.stmt,
    bindings: dict[str, Binding],
    filepath: str,
    errors: list[str],
) -> None:
    """Update ``bindings`` in-place based on the effect of ``stmt``.

    Handles:

    * ``Import`` / ``ImportFrom`` (the standard module-level bindings)
    * ``Assign`` / ``AnnAssign`` (rebinding via assignment)
    * ``AugAssign`` (rebinding via ``+=`` / ``-=`` style mutation)
    * ``Delete`` (rebinding via ``del``)
    * ``setattr(...)`` and ``builtins.setattr(...)`` (rebinding
      through attribute reflection)
    * ``FunctionDef`` / ``AsyncFunctionDef`` (rebinding via def)
    * ``ClassDef`` (rebinding via class statement)

    R10 invariant: rebindings of :data:`PROVENANCE_SENSITIVE_NAMES`
    are recorded as :data:`REBINDING_SENTINEL`; any subsequent use of
    the name is rejected. R12 invariant: module-scope attribute
    mutations on a sensitive name (``typing.NewType = X``,
    ``del typing.NewType``, ``typing.NewType += X``, etc.) and any
    ``setattr(typing, ...)`` call with either a literal or a
    dynamic attribute name ALSO emit an immediate diagnostic. The
    sentinel is still installed so any subsequent call fails closed.
    """
    if isinstance(stmt, ast.ImportFrom):
        module = stmt.module or ""
        level = stmt.level
        for alias in stmt.names:
            local_name = alias.asname or alias.name
            bindings[local_name] = Binding(
                kind="from-import",
                module=module,
                level=level,
                original_name=alias.name,
                local_name=local_name,
            )
    elif isinstance(stmt, ast.Import):
        for alias in stmt.names:
            local_name = alias.asname or alias.name
            bindings[local_name] = Binding(
                kind="import",
                module=alias.name,
                level=0,
                original_name=alias.name,
                local_name=local_name,
            )
    elif _classify_sensitive_attribute_mutation(stmt) is not None:
        # Attribute mutation on a sensitive name (e.g.
        # ``typing.NewType = X``). R12 invariant: emit an immediate
        # diagnostic AND install the sentinel on the base name.
        errors.append(_describe_attribute_mutation(stmt, filepath=filepath))
        for target in _attribute_mutation_targets(stmt):
            for base, _attr in _iter_attribute_targets(target):
                if base in PROVENANCE_SENSITIVE_NAMES:
                    bindings[base] = REBINDING_SENTINEL
    elif (setattr_form := _detect_setattr_sensitive(stmt)) is not None:
        # ``setattr(typing, "NewType", ...)`` (literal) or
        # ``setattr(typing, <non-literal>, ...)`` (dynamic) or
        # ``builtins.setattr(typing, ...)``. R12 invariant: emit an
        # immediate diagnostic. The literal form also installs the
        # sentinel on the base name; the dynamic form rejects the
        # call outright because the attribute is not provable.
        errors.append(_describe_setattr(stmt, setattr_form, filepath=filepath))
        if setattr_form == "literal":
            call = stmt.value
            assert isinstance(call, ast.Call)
            base_arg = call.args[0]
            assert isinstance(base_arg, ast.Name)
            bindings[base_arg.id] = REBINDING_SENTINEL
    elif isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            for name in _iter_target_names(target):
                if name in PROVENANCE_SENSITIVE_NAMES:
                    bindings[name] = REBINDING_SENTINEL
    elif isinstance(stmt, ast.AnnAssign):
        for name in _iter_target_names(stmt.target):
            if name in PROVENANCE_SENSITIVE_NAMES:
                bindings[name] = REBINDING_SENTINEL
    elif isinstance(stmt, ast.AugAssign):
        for name in _iter_target_names(stmt.target):
            if name in PROVENANCE_SENSITIVE_NAMES:
                bindings[name] = REBINDING_SENTINEL
    elif isinstance(stmt, ast.Delete):
        for target in stmt.targets:
            for name in _iter_target_names(target):
                if name in PROVENANCE_SENSITIVE_NAMES:
                    bindings[name] = REBINDING_SENTINEL
    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if stmt.name in PROVENANCE_SENSITIVE_NAMES:
            bindings[stmt.name] = REBINDING_SENTINEL
    elif isinstance(stmt, ast.ClassDef):
        if stmt.name in PROVENANCE_SENSITIVE_NAMES:
            bindings[stmt.name] = REBINDING_SENTINEL


def walk_with_source_order(
    stmts: Iterable[ast.stmt],
    bindings: dict[str, Binding],
    filepath: str,
    errors: list[str],
) -> None:
    """Walk statements in source order, validating calls BEFORE applying binding updates.

    R10 fix: for a normal ``Name = expr`` assignment, Python evaluates
    the right-hand side FIRST and then assigns the result to the
    target. The previous R9 walker applied the binding update first
    and then validated the right-hand call against the post-update
    snapshot, which silently approved malicious rebindings such as::

        from typing import NewType
        NewType = NewType("NewType", str)

    In the buggy order, the walker first recorded ``NewType`` as the
    sentinel rebinding, then validated ``NewType("NewType", str)``
    against the sentinel and rejected it - so an attacker could
    bypass the sentinel check by giving the RHS call a benign
    appearance while the actual import was already rebound. More
    importantly, the wrong order contradicts Python's own evaluation
    semantics.

    The corrected order is::

        for stmt in stmts:
            validate_calls_evaluated_by(stmt, bindings)
            apply_statement_bindings(stmt, bindings)

    Imports are binding operations themselves, so for ``Import`` /
    ``ImportFrom`` statements there is no right-hand call to validate
    and the binding update happens first; for ``Assign`` /
    ``AnnAssign`` statements the right-hand call is validated against
    the binding snapshot that was active BEFORE the assignment.
    """
    for stmt in stmts:
        # Step 1: Validate calls evaluated BY the right-hand side
        # using the binding snapshot that is currently active
        # (i.e. the state established by every prior module-level
        # statement). This matches Python's actual evaluation order.
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Call)
            and _is_newtype_call_node(stmt.value)
        ):
            _validate_newtype_call(stmt.value, bindings, filepath, errors)

        # Step 2: Apply the binding update introduced by this
        # statement. R12 invariant: this also emits an immediate
        # diagnostic for any attribute-mutation or setattr form
        # targeting a provenance-sensitive name, regardless of
        # whether a subsequent call follows.
        _apply_binding_update(stmt, bindings, filepath, errors)

        if isinstance(stmt, ast.If):
            walk_with_source_order(stmt.body, bindings, filepath, errors)
            walk_with_source_order(stmt.orelse, bindings, filepath, errors)
        elif isinstance(stmt, (ast.Try, ast.TryStar)):
            walk_with_source_order(stmt.body, bindings, filepath, errors)
            for handler in stmt.handlers:
                walk_with_source_order(handler.body, bindings, filepath, errors)
            walk_with_source_order(stmt.orelse, bindings, filepath, errors)
            walk_with_source_order(stmt.finalbody, bindings, filepath, errors)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            walk_with_source_order(stmt.body, bindings, filepath, errors)
            walk_with_source_order(stmt.orelse, bindings, filepath, errors)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            walk_with_source_order(stmt.body, bindings, filepath, errors)
        elif isinstance(stmt, ast.Match):
            for case in stmt.cases:
                walk_with_source_order(case.body, bindings, filepath, errors)


__all__ = [
    "walk_with_source_order",
]
