"""Canonical alias supertype identity validation for LLM-safe verifier.

R13 invariant: each canonical alias's declared supertype must be a
``Name`` referencing a real binding identity that has not been
rebound at the source position of the declaration. The verifier
walks the canonical module in source order, maintains a binding
snapshot that starts EMPTY (builtins like ``str`` are NOT
pre-installed), and rejects:

* string-literal supertypes such as ``NewType("Foo", "str")``
  (the supertype must be a ``Name`` referencing a real identity);
* module-scope rebinding of ``str`` or any canonical alias name
  via ``Assign``/``AnnAssign``/``AugAssign``/``Delete``/``def``/
  ``class`` and (R16) ``for``/``with``/``match``/``except`` binding
  targets - the walker installs :data:`REBINDING_SENTINEL` on
  rebinding;
* canonical aliases whose declared supertype resolves to a
  ``REBINDING_SENTINEL` binding at that source position;
* ``str`` used as a supertype when ``str`` is bound in the module
  scope (the builtin ``str`` is only accepted when NOT shadowed).

R14 invariant: rejects duplicate declarations, post-declaration
rebinding of canonical aliases, and module-scope conditional
shadowing via :mod:`_llm_safe_canonical_alias_shadowing`.

R15 invariant: accepts the qualified ``typing.NewType(...)`` form
and ``Import`` rebinding after declaration.

R16 invariant: full coverage of every Python construct that can
introduce a name binding at module scope, including direct top-level
control-statement binding targets.

Public surface:

* :func:`validate_canonical_alias_super_types`
* :func:`canonical_alias_super_types_rejected`
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from scripts.incident_lifecycle_boundary._llm_safe_alias_rebindings import (
    apply_alias_rebinding,
    iter_alias_rebinding_names,
)
from scripts.incident_lifecycle_boundary._llm_safe_canonical_alias_shadowing import (
    scan_module_scope_conditional_shadowing as _scan_conditional_super_type_shadowing,
)
from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    CANONICAL_ALIAS_SENSITIVE_NAMES,
)
from scripts.incident_lifecycle_boundary._llm_safe_named_expr_walker import (
    scan_module_scope_named_expr_rebindings as _scan_module_scope_named_expr_rebindings,
)
from scripts.incident_lifecycle_boundary._llm_safe_provenance_types import (
    REBINDING_SENTINEL,
    Binding,
)


def _make_canonical_alias_binding(target_name: str) -> Binding:
    """Build an alias-specific sentinel binding for ``target_name``."""
    return Binding(
        kind="<canonical-alias>",
        module="<canonical>",
        level=0,
        original_name=target_name,
        local_name=target_name,
    )


def _is_newtype_assignment(stmt: ast.stmt) -> tuple[str, ast.expr] | None:
    """Return ``(target_name, supertype_node)`` if ``stmt`` is a canonical
    ``Name = NewType("Name", SUPERTYPE)`` declaration, else ``None``.

    R15: accepts BOTH bare ``NewType(...)`` and qualified
    ``typing.NewType(...)`` forms.
    """
    if not isinstance(stmt, ast.Assign):
        return None
    if len(stmt.targets) != 1:
        return None
    target = stmt.targets[0]
    if not isinstance(target, ast.Name):
        return None
    value = stmt.value
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    is_bare = isinstance(func, ast.Name) and func.id == "NewType"
    is_qualified = (
        isinstance(func, ast.Attribute)
        and func.attr == "NewType"
        and isinstance(func.value, ast.Name)
        and func.value.id == "typing"
    )
    if not (is_bare or is_qualified):
        return None
    if len(value.args) != 2:
        return None
    first = value.args[0]
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return None
    if first.value != target.id:
        return None
    return (target.id, value.args[1])


def _iter_import_local_names(stmt: ast.stmt) -> Iterable[str]:
    """Yield the LOCAL names bound by an ``Import`` or ``ImportFrom`` statement."""
    if isinstance(stmt, ast.ImportFrom):
        for alias in stmt.names:
            yield alias.asname or alias.name
    elif isinstance(stmt, ast.Import):
        for alias in stmt.names:
            yield alias.asname or alias.name
    else:
        return


def _apply_import(stmt: ast.stmt, bindings: dict[str, Binding]) -> None:
    """Apply a top-level ``Import`` or ``ImportFrom`` to the binding snapshot."""
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


def _apply_rebinding(stmt: ast.stmt, bindings: dict[str, Binding]) -> None:
    """Apply a module-scope rebinding to the binding snapshot.

    Routes through :mod:`_llm_safe_alias_rebindings` so that every
    Python rebinding form - including R16 BINDING TARGETS on
    ``for``/``with``/``match``/``except`` constructs - installs
    :data:`REBINDING_SENTINEL` on canonical-sensitive names.
    """

    def _install(name: str) -> None:
        bindings[name] = REBINDING_SENTINEL

    apply_alias_rebinding(stmt, _install)


def _supertype_matches_expected(
    supertype_name: str,
    binding: Binding | None,
    expected_aliases: frozenset[str],
) -> bool:
    """Return ``True`` if ``binding`` is acceptable for ``supertype_name``.

    * ``str`` is acceptable ONLY when ``binding is None`` (no
      module-scope shadow).
    * Other canonical aliases are acceptable ONLY when their
      alias-specific sentinel is the current binding.
    """
    if supertype_name == "str":
        return binding is None
    if supertype_name in expected_aliases:
        expected = _make_canonical_alias_binding(supertype_name)
        return binding is not None and binding == expected
    return False


def validate_canonical_alias_super_types(
    tree: ast.AST,
    filepath: str,
    expected_aliases: frozenset[str],
) -> list[str]:
    """Validate each expected canonical alias's supertype identity.

    R14 + R15 + R16: each canonical alias may be declared exactly
    ONCE; a second canonical declaration, a later rebinding of
    the alias name (assignment, import, or BINDING TARGET on
    ``for``/``with``/``match``/``except``), OR a module-scope
    conditional rebinding emits an immediate diagnostic.
    """
    errors: list[str] = []
    if not isinstance(tree, ast.Module):
        return errors

    # R14 + R15 + R16: fail-closed scan for module-scope shadowing.
    _scan_conditional_super_type_shadowing(tree, filepath, errors)

    # R17: fail-closed scan for module-scope walrus rebindings.
    _scan_module_scope_named_expr_rebindings(tree, filepath, errors)

    bindings: dict[str, Binding] = {}
    declared_aliases: set[str] = set()

    for stmt in tree.body:
        # Step 1: Validate any canonical-alias declaration BEFORE
        # applying this statement's binding effect.
        info = _is_newtype_assignment(stmt)
        if info is not None:
            target_name, supertype_node = info
            if target_name in expected_aliases:
                if target_name in declared_aliases:
                    errors.append(
                        f"{filepath}: canonical alias '{target_name}' is "
                        f"declared more than once in this module."
                    )
                else:
                    if not isinstance(supertype_node, ast.Name):
                        # The diagnostic deliberately uses both
                        # ``string literal`` and ``non-Name`` so test
                        # assertions matching either keyword catch it.
                        errors.append(
                            f"{filepath}: canonical alias '{target_name}' "
                            f"declared with a non-Name string-literal "
                            f"supertype ({ast.unparse(supertype_node)!r}); "
                            f"the supertype must be a ``Name`` referencing "
                            f"a real binding identity."
                        )
                    else:
                        supertype_name = supertype_node.id
                        binding = bindings.get(supertype_name)
                        if not _supertype_matches_expected(
                            supertype_name, binding, expected_aliases
                        ):
                            errors.append(
                                f"{filepath}: canonical alias "
                                f"'{target_name}' is rebound: declared "
                                f"with supertype '{supertype_name}' whose "
                                f"binding identity at this source "
                                f"position is the REBINDING_SENTINEL "
                                f"(or 'None' for the str builtin that "
                                f"has been shadowed). The supertype must "
                                f"resolve to its canonical primitive "
                                f"identity (e.g. ``str`` when not "
                                f"rebound, or a previously-declared "
                                f"canonical alias with its alias-"
                                f"specific sentinel binding)."
                            )
                    declared_aliases.add(target_name)
                bindings[target_name] = _make_canonical_alias_binding(target_name)
                continue

        # Step 2: Apply this statement's binding effect.
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            # R15 #3: post-declaration Import rebinding check.
            post_decl_names = sorted(
                name
                for name in _iter_import_local_names(stmt)
                if name in declared_aliases
            )
            _apply_import(stmt, bindings)
            for name in post_decl_names:
                errors.append(
                    f"{filepath}: canonical alias '{name}' is rebound "
                    f"after its canonical declaration by an "
                    f"Import/ImportFrom statement."
                )
        else:
            # R14 #4 + R16: post-declaration rebinding check covers
            # all rebinding forms (including BINDING TARGETS on
            # control-flow constructs).
            post_decl_names = sorted(
                name
                for name in iter_alias_rebinding_names(stmt)
                if name in declared_aliases
            )
            _apply_rebinding(stmt, bindings)
            for name in post_decl_names:
                errors.append(
                    f"{filepath}: canonical alias '{name}' is rebound "
                    f"after its canonical declaration."
                )

    return errors


def canonical_alias_super_types_rejected(
    tree: ast.AST,
    filepath: str,
    expected_aliases: frozenset[str],
) -> bool:
    """Return ``True`` if the canonical supertype validator rejects the source."""
    return bool(validate_canonical_alias_super_types(tree, filepath, expected_aliases))


__all__ = [
    "CANONICAL_ALIAS_SENSITIVE_NAMES",
    "canonical_alias_super_types_rejected",
    "validate_canonical_alias_super_types",
]
