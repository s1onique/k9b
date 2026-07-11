"""Rebinding helpers for the canonical alias source-order walker.

R16 invariant: every Python construct that can introduce a name
binding at module scope is covered by :func:`apply_alias_rebinding`
and :func:`iter_alias_rebinding_names`:

* ``Assign``, ``AnnAssign``, ``AugAssign``, ``Delete``
* ``FunctionDef`` / ``AsyncFunctionDef``
* ``ClassDef``
* ``For`` / ``AsyncFor`` loop **targets** (R16)
* ``With`` / ``AsyncWith`` item ``as <name>`` **targets** (R16)
* ``Match`` case patterns (R16)
* ``ExceptHandler.name`` aliases (R16)

Splitting these helpers out keeps the main verifier module under
the LLM-friendly file size threshold (500 lines fail / 300 warn).
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable

from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    CANONICAL_ALIAS_SENSITIVE_NAMES,
)
from scripts.incident_lifecycle_boundary._llm_safe_traversal import (
    _iter_match_pattern_names,
    _iter_target_names,
)


def iter_alias_rebinding_names(stmt: ast.stmt) -> Iterable[str]:
    """Yield every module-scope name that ``stmt`` rebinds.

    Covers plain assignments, ``def``/``class`` definitions, and
    (R16) BINDING TARGETS on ``for``/``async for`` loop targets,
    ``with``/``async with`` ``as <name>`` items, ``match`` case
    patterns, and exception-handler ``as <name>`` aliases. Imports
    are NOT covered here; the import-as-rebinding case is
    detected by :func:`scan_module_scope_conditional_shadowing`
    and the dedicated walker in
    :mod:`_llm_safe_conditional_rebindings`.
    """
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            for name in _iter_target_names(target):
                yield name
    elif isinstance(stmt, ast.AnnAssign):
        for name in _iter_target_names(stmt.target):
            yield name
    elif isinstance(stmt, ast.AugAssign):
        for name in _iter_target_names(stmt.target):
            yield name
    elif isinstance(stmt, ast.Delete):
        for target in stmt.targets:
            for name in _iter_target_names(target):
                yield name
    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        yield stmt.name
    elif isinstance(stmt, ast.ClassDef):
        yield stmt.name
    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
        for name in _iter_target_names(stmt.target):
            yield name
    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
        for item in stmt.items:
            ctx = item.optional_vars
            if ctx is None:
                continue
            for name in _iter_target_names(ctx):
                yield name
    elif isinstance(stmt, ast.Match):
        for case in stmt.cases:
            if case.pattern is None:
                continue
            for name in _iter_match_pattern_names(case.pattern):
                yield name
    elif isinstance(stmt, (ast.Try, ast.TryStar)):
        for handler in stmt.handlers:
            if handler.name:
                yield handler.name


def apply_alias_rebinding(
    stmt: ast.stmt,
    install_sentinel: Callable[[str], None]
) -> None:
    """Apply the rebinding effect of ``stmt`` via ``install_sentinel(name)``.

    Covers every rebinding form (see :func:`iter_alias_rebinding_names`).
    On every canonical-sensitive name that ``stmt`` rebinds,
    ``install_sentinel(name)`` is invoked so the source-order
    walker can install :data:`REBINDING_SENTINEL` (or any other
    marker) for that name.
    """
    for name in iter_alias_rebinding_names(stmt):
        if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
            install_sentinel(name)


__all__ = [
    "apply_alias_rebinding",
    "iter_alias_rebinding_names",
]
