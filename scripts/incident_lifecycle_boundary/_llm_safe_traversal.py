"""Module-scope AST traversal helpers for LLM-safe verifier.

This module hosts the low-level walkers used by the privacy-state
contract verifier to reason about module-level control flow. The
NewType-provenance checks live in
:mod:`scripts.incident_lifecycle_boundary._llm_safe_provenance` and
import the primitives from this module so the source-order provenance
walker and the rebinding walker share a single definition of what
"module scope" means.

Public surface:

* :func:`iter_module_scope_statements` - recursive walker that descends
  into ``if``/``try``/``for``/``while``/``with``/``match`` but stops at
  function and class scopes.
* :func:`collect_module_scope_rebindings` - rebinding detection for
  protected canonical names using the walker.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator


def iter_module_scope_statements(tree: ast.AST) -> Iterator[ast.stmt]:
    """Yield every module-scope statement, descending into control flow.

    A naive ``for node in tree.body`` skips bindings declared inside
    module-scope control flow blocks, for example::

        from canonical import RawEvidenceText
        if True:
            RawEvidenceText = str

    These assignments execute in the module namespace at import time
    and would silently replace the privacy-state identity with an
    ordinary Python object.

    The walker descends into:

    * ``If`` / body and orelse
    * ``Try`` / ``TryStar`` body, handlers, orelse, finalbody
    * ``For`` / ``AsyncFor`` body and orelse
    * ``While`` body and orelse
    * ``With`` / ``AsyncWith`` body
    * ``Match`` cases

    It STOPS at function (``FunctionDef``, ``AsyncFunctionDef``) and
    class (``ClassDef``) scopes because those introduce a new local
    namespace. Lambda bodies are also excluded.

    Args:
        tree: Parsed AST (typically an :class:`ast.Module`).

    Yields:
        Each statement that lives in the module namespace.
    """

    def _walk(stmts: Iterable[ast.stmt]) -> Iterator[ast.stmt]:
        for stmt in stmts:
            yield stmt
            if isinstance(stmt, ast.If):
                yield from _walk(stmt.body)
                yield from _walk(stmt.orelse)
            elif isinstance(stmt, (ast.Try, ast.TryStar)):
                yield from _walk(stmt.body)
                for handler in stmt.handlers:
                    yield from _walk(handler.body)
                yield from _walk(stmt.orelse)
                yield from _walk(stmt.finalbody)
            elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
                yield from _walk(stmt.body)
                yield from _walk(stmt.orelse)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                yield from _walk(stmt.body)
            elif isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    yield from _walk(case.body)
            # FunctionDef / AsyncFunctionDef / ClassDef are NOT recursed:
            # they introduce a new local namespace.

    if isinstance(tree, ast.Module):
        yield from _walk(tree.body)


def _iter_target_names(target: ast.AST) -> Iterator[str]:
    """Yield name strings from an assignment target (handles tuples)."""
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _iter_target_names(elt)
    elif isinstance(target, ast.Starred):
        yield from _iter_target_names(target.value)


def _iter_match_pattern_names(pattern: ast.AST) -> Iterator[str]:
    """Yield binding names from a match-case pattern (PEP 634)."""
    if isinstance(pattern, (ast.MatchValue, ast.MatchSingleton)):
        return
    if isinstance(pattern, ast.MatchStar):
        if pattern.name is not None:
            yield pattern.name
        return
    if isinstance(pattern, ast.MatchMapping):
        for key in pattern.keys:
            yield from _iter_match_pattern_names(key)
        if pattern.rest is not None:
            yield pattern.rest
        return
    if isinstance(pattern, ast.MatchClass):
        for sub in pattern.patterns:
            yield from _iter_match_pattern_names(sub)
        for kwd in pattern.kwd_patterns:
            yield from _iter_match_pattern_names(kwd)
        return
    if isinstance(pattern, ast.MatchSequence):
        for sub in pattern.patterns:
            yield from _iter_match_pattern_names(sub)
        return
    if isinstance(pattern, ast.MatchAs):
        if pattern.name is not None:
            yield pattern.name
        if pattern.pattern is not None:
            yield from _iter_match_pattern_names(pattern.pattern)
        return
    if isinstance(pattern, ast.MatchOr):
        for sub in pattern.patterns:
            yield from _iter_match_pattern_names(sub)
        return


def collect_module_scope_rebindings(
    tree: ast.AST,
    protected_names: frozenset[str],
    *,
    exclude_imports_from: str | None = None,
) -> set[str]:
    """Collect every module-scope rebinding of any protected name.

    Rebindings can take many forms beyond ``Assign``:

    * ``Assign`` and ``AnnAssign`` (most common forms)
    * ``AugAssign`` (``name += other``, ``name -= other``)
    * ``FunctionDef`` / ``AsyncFunctionDef`` (a function with the
      same name as the protected alias)
    * ``ClassDef`` (a class with the same name)
    * ``Import`` / ``ImportFrom`` (a later import rebinding the
      protected name to a different module)
    * ``for`` / ``async for`` / ``while`` loop targets
    * ``with`` / ``async with`` item targets
    * ``except ... as <name>`` handlers
    * ``match`` case patterns

    The walker descends into module-scope control flow (``if``,
    ``try``/``except``/``else``/``finally``, ``for``, ``while``,
    ``with``, ``match``) so rebindings that execute at import time
    inside such blocks are surfaced.

    It STOPS at function and class scopes because those introduce a
    new local namespace and cannot rebind the module-level identity.

    Args:
        tree: Parsed AST (typically an :class:`ast.Module`).
        protected_names: Set of names whose rebindings must be detected.
        exclude_imports_from: Optional module path. If set, rebindings
            that come from ``from <exclude_imports_from> import``
            statements are NOT recorded (because those are the
            legitimate canonical re-export bindings).

    Returns:
        Set of protected names that have at least one module-scope
        rebinding, excluding canonical re-exports if
        ``exclude_imports_from`` was supplied.
    """
    rebindings: set[str] = set()

    for stmt in iter_module_scope_statements(tree):
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                for name in _iter_target_names(target):
                    if name in protected_names:
                        rebindings.add(name)
        elif isinstance(stmt, ast.AnnAssign):
            for name in _iter_target_names(stmt.target):
                if name in protected_names:
                    rebindings.add(name)
        elif isinstance(stmt, ast.AugAssign):
            for name in _iter_target_names(stmt.target):
                if name in protected_names:
                    rebindings.add(name)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if stmt.name in protected_names:
                rebindings.add(stmt.name)
        elif isinstance(stmt, ast.ClassDef):
            if stmt.name in protected_names:
                rebindings.add(stmt.name)
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                local_name = alias.asname or alias.name
                if local_name in protected_names:
                    rebindings.add(local_name)
        elif isinstance(stmt, ast.ImportFrom):
            if exclude_imports_from and stmt.module == exclude_imports_from:
                # The canonical ``from <exclude_imports_from> import``
                # statement is the ONE allowed top-level binding.
                continue
            for alias in stmt.names:
                local_name = alias.asname or alias.name
                if local_name in protected_names:
                    rebindings.add(local_name)
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            for name in _iter_target_names(stmt.target):
                if name in protected_names:
                    rebindings.add(name)
        elif isinstance(stmt, ast.While):
            # while binds nothing by itself; control flow only.
            continue
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                ctx = item.optional_vars
                if ctx is not None:
                    for name in _iter_target_names(ctx):
                        if name in protected_names:
                            rebindings.add(name)
        elif isinstance(stmt, (ast.Try, ast.TryStar)):
            for handler in stmt.handlers:
                if handler.name and handler.name in protected_names:
                    rebindings.add(handler.name)
        elif isinstance(stmt, ast.Match):
            for case in stmt.cases:
                if case.pattern is not None:
                    for name in _iter_match_pattern_names(case.pattern):
                        if name in protected_names:
                            rebindings.add(name)

    return rebindings


__all__ = [
    "collect_module_scope_rebindings",
    "iter_module_scope_statements",
]