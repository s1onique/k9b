"""Conditional supertype-shadowing helpers for canonical alias verifier.

R14 invariant: the verifier rejects module-scope conditional
rebindings of ``str`` or any canonical alias name. This module
hosts the small set of helpers that detect such rebindings; the
public entry point is :func:`validate_canonical_alias_super_types`
in :mod:`_llm_safe_alias_supertypes`.

Splitting these helpers out keeps the main verifier module under
the LLM-friendly file size threshold (500 lines fail / 300 warn).

Public surface:

* :func:`scan_module_scope_conditional_shadowing` - fail-closed
  scan that walks ``tree.body`` and recursively descends into
  module-scope ``if``/``try``/``for``/``while``/``with``/``match``
  blocks. Any rebinding of a :data:`CANONICAL_ALIAS_SENSITIVE_NAMES`
  member on a binding target, inside such a block, OR at module
  scope itself, is recorded as an error.

R16 invariant: the walker rejects ANY direct module-level binding
target on a ``for``/``with``/``match``/``except`` construct that
names a canonical-sensitive name, even when the construct sits at
the top of the module and NOT inside another conditional. The
``inside_conditional`` flag in this walker now controls only the
scanning of plain assignment-style rebindings inside NESTED
bodies; BINDING TARGETS on top-level control statements are
treated as forbidden whenever they introduce a canonical-sensitive
name (because at module scope those BIND the module-level name).
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    CANONICAL_ALIAS_SENSITIVE_NAMES,
)
from scripts.incident_lifecycle_boundary._llm_safe_traversal import (
    _iter_match_pattern_names,
    _iter_target_names,
)


def _statement_rebinds_canonical_sensitive(stmt: ast.stmt) -> bool:
    """Return ``True`` if a leaf-level statement rebinds a canonical-sensitive name.

    Mirrors :func:`_apply_rebinding` form coverage: ``Assign``,
    ``AnnAssign``, ``AugAssign``, ``Delete``,
    ``FunctionDef``/``AsyncFunctionDef``, ``ClassDef``, and
    ``Import``/``ImportFrom`` rebinding a canonical-sensitive name.
    """
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            for name in _iter_target_names(target):
                if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                    return True
        return False
    if isinstance(stmt, ast.AnnAssign):
        for name in _iter_target_names(stmt.target):
            if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                return True
        return False
    if isinstance(stmt, ast.AugAssign):
        for name in _iter_target_names(stmt.target):
            if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                return True
        return False
    if isinstance(stmt, ast.Delete):
        for target in stmt.targets:
            for name in _iter_target_names(target):
                if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                    return True
        return False
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return stmt.name in CANONICAL_ALIAS_SENSITIVE_NAMES
    if isinstance(stmt, ast.ClassDef):
        return stmt.name in CANONICAL_ALIAS_SENSITIVE_NAMES
    if isinstance(stmt, ast.ImportFrom):
        for alias in stmt.names:
            local_name = alias.asname or alias.name
            if local_name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                return True
        return False
    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            local_name = alias.asname or alias.name
            if local_name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                return True
        return False
    return False


def _statement_binds_canonical_sensitive(stmt: ast.stmt) -> bool:
    """Return ``True`` if ``stmt`` BINDs (introduces) a canonical-sensitive name.

    R15 + R16 invariant: the conditional scanner now also inspects
    BINDING TARGETS on construct names that introduce new
    bindings via Python's execution model: ``for``/``async for``
    loop targets, ``with``/``async with`` ``as <name>`` items,
    match patterns (including ``as`` captures and
    ``MatchMapping.rest``), and exception-handler ``as <name>``
    aliases. R16 extends this to module scope: even when the
    construct sits at the top of the module and NOT inside
    another conditional, the binding target still introduces a
    name binding that the rest of the verifier must observe.

    Examples:

    * ``for str in (int,): pass`` -> ``str`` rebound (R15/R16).
    * ``with manager as str: pass`` -> ``str`` rebound (R15/R16).
    * ``match v: case int() as str: pass`` -> ``str`` rebound.
    * ``try: ... except Exception as str: pass`` -> ``str`` rebound.
    """
    if isinstance(stmt, (ast.For, ast.AsyncFor)):
        for name in _iter_target_names(stmt.target):
            if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                return True
        return False
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        for item in stmt.items:
            ctx = item.optional_vars
            if ctx is None:
                continue
            for name in _iter_target_names(ctx):
                if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                    return True
        return False
    if isinstance(stmt, ast.Match):
        for case in stmt.cases:
            if case.pattern is None:
                continue
            for name in _iter_match_pattern_names(case.pattern):
                if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                    return True
        return False
    if isinstance(stmt, (ast.Try, ast.TryStar)):
        for handler in stmt.handlers:
            if handler.name and handler.name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                return True
        return False
    return False


def _collect_rebinding_names(stmt: ast.stmt) -> Iterable[str]:
    """Yield the canonical-sensitive names that ``stmt`` rebinds or binds."""
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            for name in _iter_target_names(target):
                if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                    yield name
    elif isinstance(stmt, ast.AnnAssign):
        for name in _iter_target_names(stmt.target):
            if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                yield name
    elif isinstance(stmt, ast.AugAssign):
        for name in _iter_target_names(stmt.target):
            if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                yield name
    elif isinstance(stmt, ast.Delete):
        for target in stmt.targets:
            for name in _iter_target_names(target):
                if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                    yield name
    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if stmt.name in CANONICAL_ALIAS_SENSITIVE_NAMES:
            yield stmt.name
    elif isinstance(stmt, ast.ClassDef):
        if stmt.name in CANONICAL_ALIAS_SENSITIVE_NAMES:
            yield stmt.name
    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
        for name in _iter_target_names(stmt.target):
            if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                yield name
    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
        for item in stmt.items:
            ctx = item.optional_vars
            if ctx is None:
                continue
            for name in _iter_target_names(ctx):
                if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                    yield name
    elif isinstance(stmt, ast.Match):
        for case in stmt.cases:
            if case.pattern is None:
                continue
            for name in _iter_match_pattern_names(case.pattern):
                if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                    yield name
    elif isinstance(stmt, (ast.Try, ast.TryStar)):
        for handler in stmt.handlers:
            if handler.name and handler.name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                yield handler.name
    elif isinstance(stmt, ast.ImportFrom):
        for alias in stmt.names:
            local_name = alias.asname or alias.name
            if local_name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                yield local_name
    elif isinstance(stmt, ast.Import):
        for alias in stmt.names:
            local_name = alias.asname or alias.name
            if local_name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                yield local_name


def scan_module_scope_conditional_shadowing(
    tree: ast.AST,
    filepath: str,
    errors: list[str],
) -> None:
    """Fail-closed scan for module-scope rebindings of sensitive names.

    R14 + R15 + R16 invariant: any rebinding of ``str`` or a
    canonical alias name via a construct's BINDING TARGET -
    ``for``/``async for`` loop targets, ``with``/``async with``
    item ``as <name>`` targets, ``match`` case patterns, and
    ``except ... as <name>`` aliases - fails closed whether the
    construct is hidden inside a module-scope ``if``/``try``/
    ``for``/``while``/``with``/``match`` block OR sits directly at
    the top of the module. R16 closes the bypass where a top-level
    ``for str in (int,): pass`` would escape the conditional
    scanner because the construct itself was not inside another
    conditional.

    Path-sensitive analysis is intractable, so ANY such rebinding
    is rejected; legitimate modules do not need rebindings of
    these names via binding targets.

    The walker descends into module-scope control flow but stops
    at function and class scopes (those introduce a new local
    namespace and cannot rebind the module-level identity).
    """

    def _emit(names: Iterable[str]) -> None:
        sorted_names = sorted(set(names))
        names_repr = ", ".join(sorted_names)
        errors.append(
            f"{filepath}: module-scope conditional rebinding of "
            f"canonical-sensitive name(s) ({names_repr}) is forbidden "
            f"(R14+R15+R16 fail-closed). A rebinding of 'str' or any "
            f"canonical alias name via a binding target on "
            f"for/with/match/except cannot be statically proven safe; "
            f"remove the rebinding."
        )

    def _walk(
        stmts: Iterable[ast.stmt],
        *,
        inside_conditional: bool,
    ) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                _walk(stmt.body, inside_conditional=True)
                _walk(stmt.orelse, inside_conditional=True)
            elif isinstance(stmt, (ast.Try, ast.TryStar)):
                # R16: ``except ... as <name>`` is a binding target
                # at module scope too, not just inside conditionals.
                if _statement_binds_canonical_sensitive(stmt):
                    _emit(_collect_rebinding_names(stmt))
                _walk(stmt.body, inside_conditional=True)
                for handler in stmt.handlers:
                    _walk(handler.body, inside_conditional=True)
                _walk(stmt.orelse, inside_conditional=True)
                _walk(stmt.finalbody, inside_conditional=True)
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                # R16: ``for target in ...`` is a binding target at
                # module scope too.
                if _statement_binds_canonical_sensitive(stmt):
                    _emit(_collect_rebinding_names(stmt))
                _walk(stmt.body, inside_conditional=True)
                _walk(stmt.orelse, inside_conditional=True)
            elif isinstance(stmt, ast.While):
                # ``while`` itself does not bind (only its body
                # might rebind); if the body rebinds a sensitive
                # name, the recursive descent will catch it.
                _walk(stmt.body, inside_conditional=True)
                _walk(stmt.orelse, inside_conditional=True)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                # R16: ``with ... as <name>`` is a binding target at
                # module scope too.
                if _statement_binds_canonical_sensitive(stmt):
                    _emit(_collect_rebinding_names(stmt))
                _walk(stmt.body, inside_conditional=True)
            elif isinstance(stmt, ast.Match):
                # R16: match-case patterns are binding targets at
                # module scope too.
                if _statement_binds_canonical_sensitive(stmt):
                    _emit(_collect_rebinding_names(stmt))
                for case in stmt.cases:
                    _walk(case.body, inside_conditional=True)
            elif inside_conditional and _statement_rebinds_canonical_sensitive(stmt):
                # Plain assignment-style rebindings inside a
                # conditional require the surrounding ``if``/``try``/
                # ``for``/``while``/``with``/``match``. Top-level
                # (``inside_conditional=False``) assignment-style
                # rebindings are captured by the source-order
                # walker in :func:`validate_canonical_alias_super_types`
                # so the legitimate canonical alias declarations
                # themselves don't trigger this scanner.
                _emit(_collect_rebinding_names(stmt))

    if not isinstance(tree, ast.Module):
        return
    _walk(tree.body, inside_conditional=False)


__all__ = ["scan_module_scope_conditional_shadowing"]
