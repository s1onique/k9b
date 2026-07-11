"""Conditional rebinding detector for the LLM-safe provenance walker.

This module hosts the fail-closed detector that scans every
``if``/``try``/``for``/``while``/``with``/``match`` block at module
scope for rebindings of provenance-sensitive names (``NewType``,
``typing``). Path-sensitive analysis of every branch is intractable
for adversarial source, so the conservative shortcut is to reject
the module outright. The detector is split out from the main
provenance walker so each module stays under the LLM-friendly file
size threshold.

Public surface:

* :func:`detect_conditional_provenance_rebindings` - fail-closed
  walker that descends into module-scope control flow and records a
  diagnostic for every rebinding of a provenance-sensitive name
  inside such a block.

The walker primitives used here (``_iter_target_names``,
``_iter_match_pattern_names``) live in
:mod:`scripts.incident_lifecycle_boundary._llm_safe_traversal` and
are imported so the walker and the rebinding detector share one
definition of "module scope".
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from scripts.incident_lifecycle_boundary._llm_safe_provenance_types import (
    PROVENANCE_SENSITIVE_NAMES,
)
from scripts.incident_lifecycle_boundary._llm_safe_traversal import (
    _iter_match_pattern_names,
    _iter_target_names,
)


def _statement_rebinds_provenance_sensitive(stmt: ast.stmt) -> bool:
    """Return True if a leaf-level statement rebinds any provenance-sensitive name.

    R14 invariant: all rebinding forms MUST be detected here so the
    fail-closed conditional scanner reports them immediately, even
    when no later ``NewType(...)`` call follows. Rebinding forms
    covered:

    * ``Assign`` (plain assignment)
    * ``AnnAssign`` (annotated assignment)
    * ``AugAssign`` (augmented assignment ``+=``/``-=``/...)
    * ``Delete`` (``del <name>``)
    * ``FunctionDef`` / ``AsyncFunctionDef``
    * ``ClassDef``
    * ``Import`` / ``ImportFrom`` rebinding a sensitive name
    """
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            for name in _iter_target_names(target):
                if name in PROVENANCE_SENSITIVE_NAMES:
                    return True
        return False
    if isinstance(stmt, ast.AnnAssign):
        for name in _iter_target_names(stmt.target):
            if name in PROVENANCE_SENSITIVE_NAMES:
                return True
        return False
    if isinstance(stmt, ast.AugAssign):
        for name in _iter_target_names(stmt.target):
            if name in PROVENANCE_SENSITIVE_NAMES:
                return True
        return False
    if isinstance(stmt, ast.Delete):
        for target in stmt.targets:
            for name in _iter_target_names(target):
                if name in PROVENANCE_SENSITIVE_NAMES:
                    return True
        return False
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return stmt.name in PROVENANCE_SENSITIVE_NAMES
    if isinstance(stmt, ast.ClassDef):
        return stmt.name in PROVENANCE_SENSITIVE_NAMES
    if isinstance(stmt, ast.ImportFrom):
        for alias in stmt.names:
            local_name = alias.asname or alias.name
            if local_name in PROVENANCE_SENSITIVE_NAMES:
                return True
        return False
    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            local_name = alias.asname or alias.name
            if local_name in PROVENANCE_SENSITIVE_NAMES:
                return True
        return False
    return False


def _conditional_with_rebinds_sensitive(stmt: ast.stmt) -> bool:
    """Return True if a ``with``/``async with`` rebinds a sensitive name via its ``as`` target."""
    if not isinstance(stmt, (ast.With, ast.AsyncWith)):
        return False
    for item in stmt.items:
        ctx = item.optional_vars
        if ctx is None:
            continue
        for name in _iter_target_names(ctx):
            if name in PROVENANCE_SENSITIVE_NAMES:
                return True
    return False


def _conditional_match_rebinds_sensitive(stmt: ast.stmt) -> bool:
    """Return True if a ``match`` rebinds a sensitive name via a case pattern."""
    if not isinstance(stmt, ast.Match):
        return False
    for case in stmt.cases:
        if case.pattern is None:
            continue
        for name in _iter_match_pattern_names(case.pattern):
            if name in PROVENANCE_SENSITIVE_NAMES:
                return True
    return False


def detect_conditional_provenance_rebindings(
    stmts: Iterable[ast.stmt],
    filepath: str,
    errors: list[str],
    *,
    inside_conditional: bool = False,
) -> None:
    """Detect rebindings of ``NewType`` or ``typing`` inside module-scope control flow.

    Per the R9 contract, ANY rebinding of a
    :data:`PROVENANCE_SENSITIVE_NAMES` member inside an
    ``if``/``try``/``for``/``while``/``with``/``match`` block at
    module scope fails closed. Path-sensitive analysis of every
    branch is intractable for adversarial source, so the
    conservative shortcut is to reject the module outright.

    The walker descends into module-scope control flow (``if``,
    ``try``/``except``/``else``/``finally``, ``for``, ``while``,
    ``with``, ``match``) so rebindings that execute at import time
    inside such blocks are surfaced. It STOPS at function and class
    scopes because those introduce a new local namespace and cannot
    rebind the module-level identity.

    Rebinding forms scanned at every nesting level:

    * Plain assignment, augmented assignment, annotated assignment
    * ``def`` / ``async def`` and ``class`` definitions
    * ``Import`` / ``ImportFrom`` rebinding a sensitive name
    * ``with`` / ``async with`` ``as <name>`` targets
    * ``match`` case patterns (``as <name>`` and ``MatchMapping.rest``)
    * ``for`` / ``async for`` loop targets
    * ``except ... as <name>`` handlers
    * ``try * ... as <name>`` (PEP 654)

    Top-level statements (those NOT nested inside a conditional) are
    NOT reported here because they are processed by the source-order
    snapshot walk in :func:`check_newtype_provenance`; their rebinding
    effect is captured there. The conditional fail-closed check only
    fires when the rebinding is hidden inside a control flow block.

    Args:
        stmts: Iterable of module-scope statements to inspect.
        filepath: Source path for diagnostic messages.
        errors: List to append diagnostic messages to.
        inside_conditional: True when called from inside a conditional
            block; only then are rebindings reported as failures.
    """
    def _emit() -> None:
        errors.append(
            f"{filepath}: module-scope rebinding of "
            f"provenance-sensitive name inside a conditional "
            f"control-flow block is forbidden (R9 fail-closed). "
            f"A rebinding of 'NewType' or 'typing' inside "
            f"if/try/for/while/with/match cannot be statically "
            f"proven safe; use an unconditional import or "
            f"isolate the rebinding inside a function/class."
        )

    for stmt in stmts:
        if isinstance(stmt, ast.If):
            detect_conditional_provenance_rebindings(
                stmt.body, filepath, errors, inside_conditional=True,
            )
            detect_conditional_provenance_rebindings(
                stmt.orelse, filepath, errors, inside_conditional=True,
            )
        elif isinstance(stmt, (ast.Try, ast.TryStar)):
            detect_conditional_provenance_rebindings(
                stmt.body, filepath, errors, inside_conditional=True,
            )
            for handler in stmt.handlers:
                if (
                    handler.name
                    and handler.name in PROVENANCE_SENSITIVE_NAMES
                ):
                    _emit()
                detect_conditional_provenance_rebindings(
                    handler.body, filepath, errors, inside_conditional=True,
                )
            detect_conditional_provenance_rebindings(
                stmt.orelse, filepath, errors, inside_conditional=True,
            )
            detect_conditional_provenance_rebindings(
                stmt.finalbody, filepath, errors, inside_conditional=True,
            )
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            for name in _iter_target_names(stmt.target):
                if name in PROVENANCE_SENSITIVE_NAMES:
                    _emit()
                    break
            detect_conditional_provenance_rebindings(
                stmt.body, filepath, errors, inside_conditional=True,
            )
            detect_conditional_provenance_rebindings(
                stmt.orelse, filepath, errors, inside_conditional=True,
            )
        elif isinstance(stmt, ast.While):
            detect_conditional_provenance_rebindings(
                stmt.body, filepath, errors, inside_conditional=True,
            )
            detect_conditional_provenance_rebindings(
                stmt.orelse, filepath, errors, inside_conditional=True,
            )
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            if _conditional_with_rebinds_sensitive(stmt):
                _emit()
            detect_conditional_provenance_rebindings(
                stmt.body, filepath, errors, inside_conditional=True,
            )
        elif isinstance(stmt, ast.Match):
            if _conditional_match_rebinds_sensitive(stmt):
                _emit()
            for case in stmt.cases:
                detect_conditional_provenance_rebindings(
                    case.body, filepath, errors, inside_conditional=True,
                )
        elif inside_conditional and _statement_rebinds_provenance_sensitive(stmt):
            _emit()


__all__ = ["detect_conditional_provenance_rebindings"]
